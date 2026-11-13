"""Offline checks of the independent serialized kernel observer contract.

The fake Lean process here is ONLY for failure-path tests. Actual kernel
execution is verified by a separate GitHub-hosted job with Lean 4.15.0.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import term_receipt as t
import serialized_kernel_evidence as s


class FakeLean:
    def __init__(self, reference, *, always_success=False, always_failure=False):
        self.reference = reference
        self.always_success = always_success
        self.always_failure = always_failure
        self.calls = 0

    def __call__(self, args, **kwargs):
        self.calls += 1
        self_ = json.loads((s.ROOT / "term-identity.json").read_text())
        accepted = self_ == self.reference
        if self.always_success:
            accepted = True
        if self.always_failure:
            accepted = False
        if accepted:
            return SimpleNamespace(returncode=0, stdout=s.ACCEPTED_BANNER + "\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="error: rejected\n")


class SerializedKernelEvidenceTests(unittest.TestCase):
    def setUp(self):
        exp = {"format": t.TERM_FORMAT, "theorem": t.THEOREM,
               "type": {"kind": "forallE", "body": {"kind": "bvar", "index": 0}},
               "proof": {"kind": "lam", "body": {"kind": "bvar", "index": 0}}}
        self.exp = exp
        self.runner = t.make_observation(
            exp, case_digest="a" * 64,
            host={"role": "proof_runner", "job": "proof_runner", "repository": "Kier73/In-Formation-Space",
                  "git_sha": "b" * 40, "run_id": "1", "run_attempt": "1"},
            environment=t.make_environment(),
        )
        self.context = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "Kier73/In-Formation-Space",
            "GITHUB_JOB": "serialized_kernel_checker",
            "GITHUB_SHA": "b" * 40,
            "GITHUB_RUN_ID": "1",
            "GITHUB_RUN_ATTEMPT": "1",
        }

    def tearDown(self):
        s.SERIALIZED.unlink(missing_ok=True)

    def test_accepts_one_and_rejects_three(self):
        fake = FakeLean(self.exp)
        result = s.verify(self.runner, run=fake, github_context=self.context)
        self.assertEqual(fake.calls, 4)
        self.assertEqual(result["status"], "serialized_term_kernel_rechecked")
        self.assertEqual([x["kernel_accepted_observed"] for x in result["cases"]], [True, False, False, False])
        self.assertFalse(result["vgi_verified_kernel_receipt_issued"])
        self.assertEqual(result["proof_term_fingerprint"], self.runner["proof_term_fingerprint"])

    def test_rejects_forged_positive_control(self):
        with self.assertRaisesRegex(s.SerializedKernelError, "unknown_constructor"):
            s.verify(self.runner, run=FakeLean(self.exp, always_success=True), github_context=self.context)

    def test_rejects_false_negative_on_valid_proof(self):
        with self.assertRaisesRegex(s.SerializedKernelError, "accepted"):
            s.verify(self.runner, run=FakeLean(self.exp, always_failure=True), github_context=self.context)

    def test_host_run_and_source_mismatch_fails_before_execution(self):
        for k, value in (("GITHUB_SHA", "c" * 40), ("GITHUB_JOB", "another_job"), ("GITHUB_RUN_ID", "2")):
            env = dict(self.context, **{k: value})
            fake = FakeLean(self.exp)
            with self.assertRaisesRegex(s.SerializedKernelError, "correlation"):
                s.verify(self.runner, run=fake, github_context=env)
            self.assertEqual(fake.calls, 0)

    def test_tampered_term_observation_digest_fails(self):
        doc = copy.deepcopy(self.runner)
        doc["export"]["proof"] = {"kind": "bvar", "index": 99}
        fake = FakeLean(self.exp)
        with self.assertRaises(t.TermReceiptError):
            s.verify(doc, run=fake, github_context=self.context)
        self.assertEqual(fake.calls, 0)

    def test_rejects_original_theorem_module_import(self):
        source = s.CHECKER.read_bytes()
        try:
            s.CHECKER.write_bytes(b"import Lean\nimport KernelTrial\n" + source)
            with self.assertRaisesRegex(s.SerializedKernelError, "may not import"):
                s.checker_source_sha()
        finally:
            s.CHECKER.write_bytes(source)


if __name__ == "__main__":
    unittest.main()
