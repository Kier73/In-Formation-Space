from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import kernel_evidence as evidence


def fake_lean_process(argv, **kwargs):
    source = argv[-1]
    if source == "--version":
        return subprocess.CompletedProcess(argv, 0, "Lean (version 4.15.0, x86_64)", "")
    if source == "KernelTrial.lean":
        return subprocess.CompletedProcess(
            argv, 0,
            "'KernelTrial.identity' does not depend on any axioms\n", "",
        )
    if source == "KernelTrialSorry.lean":
        return subprocess.CompletedProcess(
            argv, 0,
            "'KernelTrial.sorryTrial' depends on axioms: [sorryAx]\n",
            "warning: declaration uses 'sorry'\n",
        )
    if source == "KernelTrialInvalid.lean":
        return subprocess.CompletedProcess(
            argv, 1, "",
            "error: tactic 'rfl' failed, the goals are not definitionally equal\n",
        )
    if source == "KernelTrialAxiom.lean":
        return subprocess.CompletedProcess(
            argv, 0,
            "'KernelTrial.axiomTrial' depends on axioms: [KernelTrial.fakeProof]\n", "",
        )
    raise AssertionError("unexpected Lean invocation: " + repr(argv))


class KernelEvidenceTests(unittest.TestCase):
    def test_exact_axiom_free_output_is_required(self):
        self.assertTrue(evidence._check_compiler_observation(
            name="KernelTrial.lean", theorem="KernelTrial.identity",
            exit_code=0,
            stdout="'KernelTrial.identity' does not depend on any axioms\n",
            stderr="",
        ))
        self.assertFalse(evidence._check_compiler_observation(
            name="KernelTrial.lean", theorem="KernelTrial.identity",
            exit_code=0, stdout="'Other.identity' does not depend on any axioms\n", stderr="",
        ))

    def test_sorry_custom_axioms_warnings_and_nonzero_exit_are_not_accepted(self):
        for stdout, stderr, exit_code in [
            ("'KernelTrial.identity' depends on axioms: [sorryAx]", "", 0),
            ("'KernelTrial.identity' depends on axioms: [KernelTrial.fakeProof]", "", 0),
            ("'KernelTrial.identity' does not depend on any axioms", "warning: suspect", 0),
            ("'KernelTrial.identity' does not depend on any axioms", "", 1),
        ]:
            self.assertFalse(evidence._check_compiler_observation(
                name="KernelTrial.lean", theorem="KernelTrial.identity",
                exit_code=exit_code, stdout=stdout, stderr=stderr,
            ))

    @patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}, clear=True)
    @patch.object(evidence.subprocess, "run", side_effect=fake_lean_process)
    def test_two_independent_calls_reconstruct_bounded_case_statuses(self, mocked):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner_path = root / "runner.json"
            checker_path = root / "checker.json"
            evidence.produce(runner_path)
            evidence.verify(runner_path, checker_path)
            runner = json.loads(runner_path.read_text(encoding="utf-8"))
            checker = json.loads(checker_path.read_text(encoding="utf-8"))
            self.assertEqual(checker["status"], "independently_rechecked")
            self.assertEqual(checker["accepted_theorem"], "KernelTrial.identity")
            self.assertEqual(len(checker["negative_cases_rejected"]), 3)
            self.assertFalse(checker["vgi_verified_kernel_receipt_issued"])
            self.assertFalse(checker["proof_term_fingerprint_observed"])
            self.assertNotEqual(checker["runner_case_digests"], [])
            self.assertEqual(
                runner["cases"][0]["status"], "checked_without_axioms",
            )
            self.assertTrue(all(
                item["status"] == "not_established"
                for item in runner["cases"][1:]
            ))
            self.assertGreater(mocked.call_count, 8)

    @patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}, clear=True)
    @patch.object(evidence.subprocess, "run", side_effect=fake_lean_process)
    def test_runner_document_digest_mismatch_is_rejected(self, _mocked):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner.json"
            evidence.produce(path)
            report = evidence._read(path)
            report["toolchain"] = "unpinned/lean4"
            evidence._write(path, report)
            with self.assertRaisesRegex(evidence.KernelEvidenceError, "digest mismatch"):
                evidence.verify(path, Path(directory) / "checker.json")

    @patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}, clear=True)
    @patch.object(evidence.subprocess, "run", side_effect=fake_lean_process)
    def test_source_hash_mutation_is_rejected_even_with_recomputed_digests(self, _mocked):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner.json"
            evidence.produce(path)
            report = evidence._read(path)
            altered = report["cases"][0]
            altered["source_sha256"] = "0" * 64
            altered["document_digest"] = evidence._digest({
                key: value for key, value in altered.items() if key != "document_digest"
            })
            report["document_digest"] = evidence._digest({
                key: value for key, value in report.items() if key != "document_digest"
            })
            evidence._write(path, report)
            with self.assertRaisesRegex(evidence.KernelEvidenceError, "not bound to the fixed source"):
                evidence.verify(path, Path(directory) / "checker.json")

    @patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}, clear=True)
    @patch.object(evidence.subprocess, "run", side_effect=fake_lean_process)
    def test_negative_case_cannot_be_promoted_to_accepted(self, _mocked):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runner.json"
            evidence.produce(path)
            report = evidence._read(path)
            negative = report["cases"][1]
            negative["axiom_free_checker_output"] = True
            negative["status"] = "checked_without_axioms"
            negative["document_digest"] = evidence._digest({
                key: value for key, value in negative.items() if key != "document_digest"
            })
            report["document_digest"] = evidence._digest({
                key: value for key, value in report.items() if key != "document_digest"
            })
            evidence._write(path, report)
            with self.assertRaisesRegex(evidence.KernelEvidenceError, "expected rejection"):
                evidence.verify(path, Path(directory) / "checker.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
