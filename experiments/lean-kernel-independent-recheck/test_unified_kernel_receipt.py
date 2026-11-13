"""Synthetic *contract* tests; mocked GitHub CLI is not live attestation.

Only the separately scheduled main-branch workflow can provide real trusted
GitHub/Sigstore provenance and execute Lean.Kernel.check on serialized Expr.
"""
import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import attested_admission as provenance
import serialized_kernel_evidence as serialized
import term_receipt as term
import unified_kernel_receipt as unified


CONTEXT = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": unified.REPO,
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_REF": unified.MAIN_REF,
    "GITHUB_WORKFLOW_REF": unified.WORKFLOW + "@" + unified.MAIN_REF,
    "GITHUB_JOB": "vgi_unified_admission",
    "GITHUB_SHA": "c" * 40,
    "GITHUB_RUN_ID": "1234567",
    "GITHUB_RUN_ATTEMPT": "1",
}


def host(role):
    return {
        "role": role, "job": role, "repository": unified.REPO,
        "git_sha": CONTEXT["GITHUB_SHA"],
        "run_id": CONTEXT["GITHUB_RUN_ID"],
        "run_attempt": CONTEXT["GITHUB_RUN_ATTEMPT"],
    }


def case_record(export, name):
    payload = serialized._mutant(export, name)
    success = name == "accepted"
    stdout = serialized.ACCEPTED_BANNER + "\n" if success else ""
    stderr = "" if success else "error: expected rejection"
    return {
        "case": name,
        "input_sha256": hashlib.sha256(term.canonical(payload) + b"\n").hexdigest(),
        "process_exit_code": 0 if success else 1,
        "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
        "kernel_accepted_observed": success,
        "stdout_excerpt": stdout,
        "stderr_excerpt": stderr,
    }


class MockGH:
    """Return syntactically verified reports, not actual cryptographic proofs."""
    def __init__(self):
        self.calls = []
        self.bad_subject = None
        self.bad_repository = False
        self.fail = False
        self.version = "gh version 2.103.3 (2026-10-26)"

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv == ["gh", "--version"]:
            return SimpleNamespace(returncode=0, stdout=self.version, stderr="")
        if self.fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="verification failed")
        assert argv[:3] == ["gh", "attestation", "verify"]
        assert "--signer-workflow" not in argv
        path = Path(argv[3])
        if self.bad_subject and path.name == self.bad_subject:
            value = "a" * 64
        else:
            value = hashlib.sha256(path.read_bytes()).hexdigest()
        report = [{
            "verificationResult": {
                "signature": {
                    "certificate": {
                        "sourceRepositoryIdentifier": "1" if self.bad_repository else unified.REPO_ID,
                    },
                },
                "statement": {
                    "predicateType": provenance.PREDICATE,
                    "subject": [{"name": path.name, "digest": {"sha256": value}}],
                },
            },
        }]
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")


class UnifiedContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = Path(self.tmp.name)
        self.paths = {
            "runner": p / "runner.json",
            "checker": p / "checker.json",
            "signed": p / "signed.json",
            "public_key": p / "checker.pem",
            "serialized_kernel": p / "kernel.json",
        }
        self.key = Ed25519PrivateKey.generate()
        export = {
            "format": term.TERM_FORMAT, "theorem": term.THEOREM,
            "type": {"kind": "forallE", "domain": {"kind": "sort"}, "body": {"kind": "bvar", "index": 0}},
            "proof": {"kind": "lam", "domain": {"kind": "sort"}, "body": {"kind": "bvar", "index": 0}},
        }
        env = term.make_environment()
        runner = term.make_observation(export, case_digest="0" * 64,
            host=host("proof_runner"), environment=env)
        checker = term.make_observation(export, case_digest="1" * 64,
            host=host("independent_checker"), environment=env)
        signed = term.recheck(runner, checker, self.key)
        kernel = {
            "format": serialized.FORMAT,
            "status": "serialized_term_kernel_rechecked",
            "theorem": term.THEOREM,
            "toolchain": term.TOOLCHAIN,
            "serialized_expression_profile": term.TERM_FORMAT,
            "checker_source_sha256": serialized.checker_source_sha(),
            "original_runner_observation_digest": runner["document_digest"],
            "proof_term_fingerprint": runner["proof_term_fingerprint"],
            "type_fingerprint": runner["type_fingerprint"],
            "obligation_id": runner["obligation_id"],
            "environment_fingerprint": runner["environment"]["environment_fingerprint"],
            "checker_host": {
                "repository": unified.REPO,
                "git_sha": CONTEXT["GITHUB_SHA"],
                "run_id": CONTEXT["GITHUB_RUN_ID"],
                "run_attempt": CONTEXT["GITHUB_RUN_ATTEMPT"],
                "job": "serialized_kernel_checker",
            },
            "cases": [case_record(export, name) for name in serialized.SAMPLES],
            "vgi_verified_kernel_receipt_issued": False,
            "not_established": ["fixed-theorem experiment"],
        }
        kernel["document_digest"] = term.digest(kernel)
        self.fixtures = {
            "runner": runner, "checker": checker, "signed": signed,
            "serialized_kernel": kernel,
        }
        for name, value in self.fixtures.items():
            term._write(self.paths[name], value)
        self.paths["public_key"].write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.fake = MockGH()

    def run_adapter(self, *, environment=None):
        return unified.attest_and_unify(
            runner_path=self.paths["runner"],
            checker_path=self.paths["checker"],
            signed_path=self.paths["signed"],
            public_key_path=self.paths["public_key"],
            serialized_kernel_path=self.paths["serialized_kernel"],
            env=CONTEXT if environment is None else environment,
            command_runner=self.fake,
        )

    def write_mutant(self, which, mutator):
        obj = copy.deepcopy(self.fixtures[which])
        mutator(obj)
        obj["document_digest"] = term.digest({k: v for k, v in obj.items() if k != "document_digest"})
        term._write(self.paths[which], obj)

    def test_accepts_both_attested_paths_and_only_one_exact_receipt(self):
        result = self.run_adapter()
        self.assertEqual(result["vgi_kernel_status"], "kernel_accepted")
        self.assertEqual(result["verified_kernel_receipt"]["result"], "accepted")
        self.assertEqual(result["obligation_id"], self.fixtures["runner"]["obligation_id"])
        self.assertEqual(result["type_fingerprint"], self.fixtures["runner"]["type_fingerprint"])
        self.assertEqual(result["checker_policy"], unified.CHECKER_POLICY)
        self.assertEqual(len(self.fake.calls), 6)  # gh version + five distinct subjects
        self.assertEqual(set(result["attested_subjects"]), set(unified.SUBJECT_NAMES))
        for args in self.fake.calls[1:]:
            for expected in (
                ("--cert-identity", unified.CERT_IDENTITY),
                ("--source-ref", unified.MAIN_REF),
                ("--source-digest", CONTEXT["GITHUB_SHA"]),
                ("--repo", unified.REPO),
            ):
                self.assertIn(" ".join(expected), " ".join(args))
            self.assertIn("--deny-self-hosted-runners", args)

    def test_wrong_context_cannot_claim_trusted_authority(self):
        for key, value in (("GITHUB_EVENT_NAME", "pull_request"),
                           ("GITHUB_REF", "refs/heads/Main"),
                           ("GITHUB_WORKFLOW_REF", unified.WORKFLOW + "@refs/heads/test"),
                           ("GITHUB_JOB", "independent_checker")):
            with self.assertRaisesRegex(unified.UnifiedReceiptError, "unauthorized"):
                self.run_adapter(environment={**CONTEXT, key: value})
        self.assertEqual(self.fake.calls, [])

    def test_missing_independent_kernel_evidence_is_never_promoted(self):
        self.paths["serialized_kernel"].unlink()
        with self.assertRaises((OSError, ValueError)):
            self.run_adapter()
        self.assertEqual(self.fake.calls, [])

    def test_forged_positive_kernel_decision_is_rejected(self):
        self.write_mutant("serialized_kernel", lambda obj: obj["cases"][0].update(
            kernel_accepted_observed=False
        ))
        with self.assertRaisesRegex(unified.UnifiedReceiptError, "not accepted"):
            self.run_adapter()
        self.assertEqual(self.fake.calls, [])

    def test_forged_negative_case_is_rejected(self):
        self.write_mutant("serialized_kernel", lambda obj: obj["cases"][2].update(
            kernel_accepted_observed=True, process_exit_code=0
        ))
        with self.assertRaisesRegex(unified.UnifiedReceiptError, "counterexample"):
            self.run_adapter()
        self.assertEqual(self.fake.calls, [])

    def test_missing_or_reordered_kernel_controls_are_rejected(self):
        self.write_mutant("serialized_kernel", lambda obj: obj["cases"].reverse())
        with self.assertRaisesRegex(unified.UnifiedReceiptError, "reordered"):
            self.run_adapter()

    def test_reused_kernel_report_from_different_run_is_rejected(self):
        self.write_mutant("serialized_kernel", lambda obj: obj["checker_host"].update(run_id="888"))
        with self.assertRaisesRegex(unified.UnifiedReceiptError, "distinct commit or workflow run"):
            self.run_adapter()
        self.assertEqual(self.fake.calls, [])

    def test_kernel_checker_source_identity_is_pinned(self):
        self.write_mutant("serialized_kernel", lambda obj: obj.update(checker_source_sha256="f" * 64))
        with self.assertRaisesRegex(unified.UnifiedReceiptError, "checker_source_sha256"):
            self.run_adapter()

    def test_changed_vgi_obligation_or_proof_fingerprint_is_rejected(self):
        for key in ("obligation_id", "proof_term_fingerprint", "type_fingerprint", "environment_fingerprint"):
            with self.subTest(key=key):
                term._write(self.paths["serialized_kernel"], self.fixtures["serialized_kernel"])
                self.write_mutant("serialized_kernel", lambda obj: obj.update({key: "e" * 64}))
                with self.assertRaisesRegex(unified.UnifiedReceiptError, key):
                    self.run_adapter()
        self.assertEqual(self.fake.calls, [])

    def test_kernel_input_digest_must_match_exact_export_and_mutants(self):
        self.write_mutant("serialized_kernel", lambda obj: obj["cases"][0].update(input_sha256="a" * 64))
        with self.assertRaisesRegex(unified.UnifiedReceiptError, "input digest"):
            self.run_adapter()

    def test_missing_signer_key_or_wrong_ed25519_key_fails(self):
        replacement = Ed25519PrivateKey.generate()
        self.paths["public_key"].write_bytes(replacement.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        with self.assertRaisesRegex(term.TermReceiptError, "signature"):
            self.run_adapter()

    def test_invalid_source_signature_fails_even_if_kernel_path_is_valid(self):
        self.write_mutant("signed", lambda obj: obj.update(signature_base64="AAAA"))
        with self.assertRaisesRegex(term.TermReceiptError, "signature"):
            self.run_adapter()

    def test_unattested_kernel_subject_is_rejected(self):
        self.fake.bad_subject = self.paths["serialized_kernel"].name
        with self.assertRaises(term.TermReceiptError):
            self.run_adapter()

    def test_bad_source_repository_in_attestation_is_rejected(self):
        self.fake.bad_repository = True
        with self.assertRaises(term.TermReceiptError):
            self.run_adapter()

    def test_unpatched_github_cli_cannot_issue_receipts(self):
        self.fake.version = "gh version 2.101.0 (2026-09-09)"
        with self.assertRaisesRegex(term.TermReceiptError, "unpatched"):
            self.run_adapter()
        self.assertEqual(len(self.fake.calls), 1)

    def test_symlink_attested_subject_fails_closed(self):
        target = self.paths["serialized_kernel"].with_suffix(".source")
        self.paths["serialized_kernel"].rename(target)
        self.paths["serialized_kernel"].symlink_to(target)
        with self.assertRaisesRegex(term.TermReceiptError, "symlinked"):
            self.run_adapter()

    def test_unsupported_forged_case_fields_fail_closed(self):
        self.write_mutant("serialized_kernel", lambda obj: obj["cases"][1].update(debug_trust=True))
        with self.assertRaisesRegex(term.TermReceiptError, "unexpected"):
            self.run_adapter()


if __name__ == "__main__":
    unittest.main()
