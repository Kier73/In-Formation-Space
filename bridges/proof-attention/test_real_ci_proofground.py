"""USM-011: actual CI regression through VGI ProofGround and IFS attention."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from research_ci_proofground import (
    SOURCE_FILE, RealInvariantError, _digest,
    build_ground, investigate, verify_report,
)
from proof_attention import build_proof_attention_plan
from vgi.proof import ProofEnvironment, ProofGround, ProofObligation


def source_observation():
    return json.loads(SOURCE_FILE.read_text(encoding="utf-8"))


class RealResearchInvariantTests(unittest.TestCase):
    def test_real_failed_python311_ci_is_preserved_as_an_observation(self):
        source = source_observation()
        provenance = source["source"]
        self.assertEqual(provenance["run_id"], 43629648833)
        self.assertEqual(provenance["job_id"], 132553219461)
        self.assertEqual(provenance["head_sha"],
                         "7e7f86d7074eb676e2e022cd620b4b1a814c5873")
        self.assertEqual(provenance["expected"], "0.0")
        self.assertEqual(provenance["observed"], "8.881784197001252e-16")
        self.assertEqual(provenance["failing_depth"], "not emitted by unittest")
        self.assertTrue(provenance["job_url"].startswith("https://github.com/"))

    def test_vgi_ground_records_actual_ci_and_never_invents_kernel_acceptance(self):
        source = source_observation()
        ground, root = build_ground(source)
        self.assertIsInstance(ground, ProofGround)
        self.assertIsInstance(ground.environment, ProofEnvironment)
        self.assertEqual(ground.environment.assistant, "Python unittest")
        self.assertEqual(ground.environment.assistant_version, "3.11.18")
        self.assertEqual(len(ground.obligation_ids), 3)
        self.assertIn(root, ground.obligation_ids)
        self.assertEqual(ground.summary()["kernel_accepted_obligations"], 0)
        self.assertEqual(ground.summary()["unverified_obligations"], 3)
        self.assertEqual(ground.summary()["observed_untrusted_kernel_claims"][0][
            "observed_float"
        ], "8.881784197001252e-16")
        self.assertFalse(ground.receipts)
        self.assertTrue(all(
            ground.kernel_status(item) == "unverified"
            for item in ground.obligation_ids
        ))

    def test_ifs_attention_navigates_two_concrete_exact_arithmetic_checks(self):
        source = source_observation()
        ground, root = build_ground(source)
        plan = build_proof_attention_plan(ground, (root,))
        self.assertEqual(plan["summary"]["active_root_count"], 1)
        self.assertEqual(plan["summary"]["reachable_obligation_count"], 3)
        self.assertEqual(plan["summary"]["candidate_action_count"], 2)
        self.assertEqual(plan["summary"]["kernel_accepted_reachable_count"], 0)
        self.assertEqual(plan["interpretation"]["kernel_authority"],
                         "external_verified_receipt_required")
        tactics = [item["tactic"] for item in plan["candidate_actions"]]
        self.assertEqual(set(tactics), {
            "verify-integer-antisymmetry", "verify-zero-term-projection"
        })
        self.assertTrue(all(
            item["requires_parent_kernel_receipt"] is True
            for item in plan["candidate_actions"]
        ))
        self.assertEqual(len([
            edge for edge in ground.transitions
            if edge.attempt_status == "elaborated" and len(edge.subgoal_ids) == 2
        ]), 1)

    def test_run_repaired_real_computation_and_preserve_reconstructable_report(self):
        source = source_observation()
        report = investigate(source)
        self.assertTrue(verify_report(source, report))
        self.assertEqual(report["observation_digest"], _digest(source))
        self.assertEqual(report["source_head_sha"], source["source"]["head_sha"])
        self.assertEqual(report["native_research_execution"],
                         "VGI ProofGround + IFS proof attention + repaired source call")
        self.assertEqual(report["research_action"],
                         "run-regression-tests-on-python-3.11-and-3.13")
        self.assertFalse(report["external_kernel_receipt_admitted"])
        self.assertFalse(report["merge_authorized"])
        self.assertEqual([case["depth"] for case in report["repair_checks"]],
                         [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(
            case["exact_sine_coefficients"] == []
            and case["numerical_cross"] == 0.0
            and case["identity_holds_at_test_angle"] is True
            for case in report["repair_checks"]
        ))

    def test_forged_ci_failure_cannot_replace_source_evidence(self):
        source = source_observation()
        source["source"]["head_sha"] = "0" * 40
        with self.assertRaisesRegex(RealInvariantError, "inspected failure"):
            build_ground(source)
        source = source_observation()
        source["source"]["observed"] = "0.0"
        with self.assertRaisesRegex(RealInvariantError, "inspected failure"):
            investigate(source)

    def test_unverified_ci_claim_cannot_become_proof_kernel_receipt(self):
        source = source_observation()
        source["classification"]["external_kernel_receipt_available"] = True
        with self.assertRaisesRegex(RealInvariantError, "inspected failure"):
            investigate(source)

    def test_tampered_report_with_new_outer_hash_is_still_refused(self):
        source = source_observation()
        report = investigate(source)
        altered = deepcopy(report)
        altered["repair_checks"][2]["numerical_cross"] = 1e-16
        altered["report_digest"] = _digest({
            k: v for k, v in altered.items() if k != "report_digest"
        })
        self.assertFalse(verify_report(source, altered))

    def test_source_immutability_is_bound_to_report(self):
        source = source_observation()
        report = investigate(source)
        later = deepcopy(source)
        later["classification"]["established_by_ci"] = (
            "A new invented statement, not the observed failure."
        )
        self.assertFalse(verify_report(later, report))


if __name__ == "__main__":
    unittest.main()
