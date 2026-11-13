"""Offline adversarial contract tests. These do NOT invoke Lean or authenticate CI hosts."""
import copy
import json
import tempfile
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import term_receipt as t


def host(role):
    return {"role": role, "job": role, "repository": "Kier73/In-Formation-Space",
            "git_sha": "test-commit", "run_id": "test-run", "run_attempt": "1"}


class TermReceiptTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.exp = {"format": t.TERM_FORMAT, "theorem": t.THEOREM,
                    "type": {"kind": "forallE", "body": {"kind": "bvar", "index": 0}},
                    "proof": {"kind": "lam", "body": {"kind": "bvar", "index": 0}}}
        self.env = t.make_environment()
        self.runner = t.make_observation(self.exp, case_digest="a" * 64,
                                         host=host("proof_runner"), environment=self.env)
        self.checker = t.make_observation(self.exp, case_digest="b" * 64,
                                          host=host("independent_checker"), environment=self.env)
        self.signed = t.recheck(self.runner, self.checker, self.key)

    def test_accepts_only_trusted_signature_and_exact_binding(self):
        receipt = t.admit(self.runner, self.checker, self.signed, self.key.public_key())
        self.assertEqual(receipt.result, "accepted")
        self.assertEqual(receipt.obligation_id, self.runner["obligation_id"])
        self.assertEqual(receipt.proof_term_fingerprint, self.runner["proof_term_fingerprint"])

    def test_recheck_rejects_changed_proof_type_and_environment(self):
        for attr, val in [
            ("proof", {"kind": "bvar", "index": 8}),
            ("type", {"kind": "const", "name": "different"}),
        ]:
            changed = copy.deepcopy(self.exp)
            changed[attr] = val
            observation = t.make_observation(changed, case_digest="b" * 64,
                                             host=host("independent_checker"), environment=self.env)
            with self.assertRaises(t.TermReceiptError):
                t.recheck(self.runner, observation, self.key)
        env = copy.deepcopy(self.env.to_dict())
        env["environment_fingerprint"] = "different"
        from vgi.proof import ProofEnvironment
        changed_env = ProofEnvironment(**env)
        fresh = t.make_observation(self.exp, case_digest="b" * 64,
                                   host=host("independent_checker"), environment=changed_env)
        with self.assertRaises(t.TermReceiptError):
            t.recheck(self.runner, fresh, self.key)

    def test_rejects_tampered_signature_and_wrong_signer(self):
        signed = copy.deepcopy(self.signed)
        signed["signature_base64"] = "AAAA"  # malformed Ed25519 signature, valid base64
        signed["document_digest"] = t.digest({k: v for k, v in signed.items() if k != "document_digest"})
        with self.assertRaisesRegex(t.TermReceiptError, "signature"):
            t.admit(self.runner, self.checker, signed, self.key.public_key())
        other = Ed25519PrivateKey.generate()
        with self.assertRaises(t.TermReceiptError):
            t.admit(self.runner, self.checker, self.signed, other.public_key())

    def test_rejects_proof_term_and_runner_replacement(self):
        runner = copy.deepcopy(self.runner)
        runner["export"]["proof"] = {"kind": "bvar", "index": 1}
        runner["proof_term_fingerprint"] = t.digest({"format": t.TERM_FORMAT, "proof": runner["export"]["proof"]})
        runner["document_digest"] = t.digest({k: v for k, v in runner.items() if k != "document_digest"})
        with self.assertRaises(t.TermReceiptError):
            t.admit(runner, self.checker, self.signed, self.key.public_key())
        runner = copy.deepcopy(self.runner)
        runner["kernel_case_observation_digest"] = "c" * 64
        runner["document_digest"] = t.digest({k: v for k, v in runner.items() if k != "document_digest"})
        with self.assertRaises(t.TermReceiptError):
            t.admit(runner, self.checker, self.signed, self.key.public_key())

    def test_rejects_altered_or_substituted_checker_observation(self):
        checker = copy.deepcopy(self.checker)
        checker["kernel_case_observation_digest"] = "e" * 64
        checker["document_digest"] = t.digest({k: v for k, v in checker.items() if k != "document_digest"})
        with self.assertRaisesRegex(t.TermReceiptError, "checker observation substitution"):
            t.admit(self.runner, checker, self.signed, self.key.public_key())
        checker = copy.deepcopy(self.checker)
        checker["host"]["run_id"] = "different-run"
        checker["document_digest"] = t.digest({k: v for k, v in checker.items() if k != "document_digest"})
        with self.assertRaisesRegex(t.TermReceiptError, "different provenance"):
            t.admit(self.runner, checker, self.signed, self.key.public_key())

    def test_rejects_unknown_checker_and_rejected_result(self):
        with self.assertRaises(t.TermReceiptError):
            t.admit(self.runner, self.checker, self.signed, self.key.public_key(),
                    expected_checker_id="different-trusted-checker")
        signed = copy.deepcopy(self.signed)
        signed["payload"]["result"] = "rejected"
        signed["document_digest"] = t.digest({k: v for k, v in signed.items() if k != "document_digest"})
        with self.assertRaises(t.TermReceiptError):
            t.admit(self.runner, self.checker, signed, self.key.public_key())

    def test_rejects_same_job_and_cross_run(self):
        checker = copy.deepcopy(self.checker)
        checker["host"]["job"] = "proof_runner"
        with self.assertRaises(t.TermReceiptError):
            t.recheck(self.runner, checker, self.key)
        checker = copy.deepcopy(self.checker)
        checker["host"]["run_id"] = "another-run"
        with self.assertRaises(t.TermReceiptError):
            t.recheck(self.runner, checker, self.key)

    def test_duplicate_json_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.json"
            src.write_text('{"format":"correct","format":"replacement"}')
            with self.assertRaises(t.TermReceiptError):
                t._read(src)


if __name__ == "__main__":
    unittest.main()
