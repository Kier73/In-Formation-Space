"""Offline fail-closed policy tests; mocked gh is NOT cryptographic attestation."""
import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import term_receipt as t
import attested_admission as a


SHA = "a" * 40
CTX = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": a.REPO,
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_REF": a.MAIN_REF,
    "GITHUB_WORKFLOW_REF": a.WORKFLOW + "@" + a.MAIN_REF,
    "GITHUB_JOB": "vgi_attested_admission",
    "GITHUB_SHA": SHA,
    "GITHUB_RUN_ID": "123456",
    "GITHUB_RUN_ATTEMPT": "1",
}


def host(role):
    return {"role": role, "job": role, "repository": a.REPO,
            "git_sha": SHA, "run_id": CTX["GITHUB_RUN_ID"],
            "run_attempt": CTX["GITHUB_RUN_ATTEMPT"]}


class MockGitHubVerifier:
    def __init__(self):
        self.calls = []
        self.version = "gh version 2.102.0 (2026-10-01)"
        self.repository_id = a.REPO_ID
        self.source_digest_override = None
        self.emit_digest = "actual"
        self.empty = False
        self.fail = False

    def __call__(self, args, **_kwargs):
        self.calls.append(args)
        if self.fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="untrusted")
        if args == ["gh", "--version"]:
            return SimpleNamespace(returncode=0, stdout=self.version, stderr="")
        if self.empty:
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        name = Path(args[3])
        digest = hashlib.sha256(name.read_bytes()).hexdigest()
        if self.emit_digest != "actual":
            digest = self.emit_digest
        report = [{
            "verificationResult": {
                "signature": {"certificate": {
                    "sourceRepositoryIdentifier": self.repository_id,
                }},
                "statement": {
                    "predicateType": a.PREDICATE,
                    "subject": [{"name": name.name, "digest": {"sha256": digest}}],
                }
            }
        }]
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")


class AttestationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.runner_path = root / "runner.json"
        self.checker_path = root / "checker.json"
        self.signed_path = root / "signed.json"
        self.key_path = root / "checker.pem"
        key = Ed25519PrivateKey.generate()
        proof = {"format": t.TERM_FORMAT, "theorem": t.THEOREM,
                 "type": {"kind": "sort", "level": {"kind": "zero"}},
                 "proof": {"kind": "const", "name": {"kind": "anonymous"}, "levels": []}}
        env = t.make_environment()
        runner_doc = t.make_observation(proof, case_digest="0" * 64,
                                         host=host("proof_runner"), environment=env)
        checker_doc = t.make_observation(proof, case_digest="1" * 64,
                                          host=host("independent_checker"), environment=env)
        signed = t.recheck(runner_doc, checker_doc, key)
        t._write(self.runner_path, runner_doc)
        t._write(self.checker_path, checker_doc)
        t._write(self.signed_path, signed)
        self.key_path.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.fake = MockGitHubVerifier()

    def run_adapter(self, *, env=None):
        return a.attest_and_admit(
            runner_path=self.runner_path, checker_path=self.checker_path,
            signed_path=self.signed_path, public_key_path=self.key_path,
            env=CTX if env is None else env, command_runner=self.fake)

    def test_exact_authority_profile_and_required_subjects(self):
        result = self.run_adapter()
        self.assertEqual(result["status"], "attested_workflow_receipt_admitted")
        self.assertEqual(result["vgi_kernel_status"], "kernel_accepted")
        self.assertEqual(result["repository_id"], a.REPO_ID)
        self.assertEqual(len(self.fake.calls), 4)
        for cmd in self.fake.calls[1:]:
            for constraint in (
                ["--repo", a.REPO],
                ["--source-ref", a.MAIN_REF],
                ["--source-digest", SHA],
                ["--signer-workflow", a.WORKFLOW],
                ["--cert-identity", a.CERT_IDENTITY],
                ["--deny-self-hosted-runners"],
            ):
                self.assertIn(" ".join(constraint), " ".join(cmd))

    def test_rejects_untrusted_context_without_calling_gh(self):
        for field, value in (
            ("GITHUB_REF", "refs/heads/Main"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_JOB", "independent_checker"),
            ("GITHUB_REPOSITORY", "someone/other"),
            ("GITHUB_WORKFLOW_REF", a.WORKFLOW + "@refs/heads/other"),
            ("GITHUB_SHA", "b" * 40),
        ):
            env = dict(CTX, **{field: value})
            if field == "GITHUB_SHA":
                # Changed SHA means host observation mismatch even with valid context.
                with self.assertRaises(t.TermReceiptError):
                    self.run_adapter(env=env)
            else:
                with self.assertRaisesRegex(t.TermReceiptError, "context mismatch"):
                    self.run_adapter(env=env)
        self.assertEqual(self.fake.calls, [])

    def test_rejects_old_gh_verifier(self):
        self.fake.version = "gh version 2.101.0 (2026-09-12)"
        with self.assertRaisesRegex(t.TermReceiptError, "unpatched"):
            self.run_adapter()
        self.assertEqual(len(self.fake.calls), 1)

    def test_rejects_unverified_or_wrong_repo(self):
        for key, value in (("repository_id", "another"), ("emit_digest", "f" * 64),
                           ("empty", True), ("fail", True)):
            self.fake = MockGitHubVerifier()
            setattr(self.fake, key, value)
            with self.assertRaises(t.TermReceiptError):
                self.run_adapter()

    def test_rejects_corrupted_public_key_even_with_mocked_valid_gh(self):
        replacement = Ed25519PrivateKey.generate()
        self.key_path.write_bytes(replacement.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        with self.assertRaisesRegex(t.TermReceiptError, "signature"):
            self.run_adapter()

    def test_rejects_runner_and_checker_from_another_run(self):
        for path in (self.runner_path, self.checker_path):
            original = path.read_bytes()
            doc = json.loads(original)
            doc["host"]["run_id"] = "999"
            doc["document_digest"] = t.digest({k: v for k, v in doc.items() if k != "document_digest"})
            path.write_bytes(t.canonical(doc))
            with self.assertRaisesRegex(t.TermReceiptError, "not bound to verified workflow run"):
                self.run_adapter()
            path.write_bytes(original)
        self.assertEqual(self.fake.calls, [])

    def test_rejects_symlinked_authority_subject(self):
        moved = self.key_path.with_name("other.pem")
        self.key_path.rename(moved)
        self.key_path.symlink_to(moved)
        with self.assertRaisesRegex(t.TermReceiptError, "symlinked"):
            self.run_adapter()


if __name__ == "__main__":
    unittest.main()
