import hashlib
import json
import unittest
from pathlib import Path

from run_authority_matrix import (
    EXPECTED,
    SCENARIOS,
    evidence_partition,
    matrix_conditions,
    validate_attempt_result,
    validate_condition,
)


class AuthorityMatrixTests(unittest.TestCase):
    def test_matrix_crosses_policy_modes_and_evidence_patterns(self):
        conditions = matrix_conditions()
        self.assertEqual(len(conditions), 10)
        self.assertEqual(
            {(item["strict"], item["scenario"]) for item in conditions},
            {(strict, scenario) for strict in (True, False) for scenario in SCENARIOS},
        )
        self.assertTrue(all(item["quorum"] == 2 for item in conditions))

    def test_expected_status_table_separates_quorum_from_authority(self):
        self.assertEqual(EXPECTED[(True, "partial_unanimous")], ("PENDING", "REFUSED"))
        self.assertEqual(EXPECTED[(False, "partial_unanimous")], ("QUORUM", "AUTHORIZED"))
        self.assertEqual(EXPECTED[(True, "majority_dissent")], ("CONFLICT", "CONFLICT"))
        self.assertEqual(EXPECTED[(False, "majority_dissent")], ("QUORUM", "AUTHORIZED"))
        self.assertEqual(EXPECTED[(True, "tied_split")], ("CONFLICT", "CONFLICT"))
        self.assertEqual(EXPECTED[(False, "tied_split")], ("QUORUM", "AUTHORIZED"))
        self.assertEqual(EXPECTED[(False, "subquorum_partial")], ("PENDING", "REFUSED"))

    def test_evidence_partition_retains_missing_and_dissenting_sources(self):
        scenario = SCENARIOS["majority_dissent"]
        fake_payloads = {
            source: ("resolver/v1", 1, source, value)
            for source, value in scenario.items()
        }
        partition = evidence_partition(scenario, fake_payloads)
        self.assertEqual(partition["winner_sources"], ["S00", "S01", "S02"])
        self.assertEqual(partition["dissenting_sources"], ["S03"])
        self.assertEqual(partition["missing_sources"], [])

    def test_tie_is_detected_even_when_canonical_order_selects_a_winner(self):
        scenario = SCENARIOS["tied_split"]
        fake_payloads = {
            source: ("resolver/v1", 1, source, value)
            for source, value in scenario.items()
        }
        partition = evidence_partition(scenario, fake_payloads)
        self.assertTrue(partition["tie_at_top"])
        self.assertEqual(partition["winning_count"], 2)
        self.assertEqual(partition["dissenting_sources"], ["S02", "S03"])

    def test_attempt_contract_rejects_authorization_with_missing_invariants(self):
        valid = {
            "strict": False,
            "scenario": "partial_unanimous",
            "pre_finalization_status": "QUORUM",
            "final_status": "AUTHORIZED",
            "evidence_received_sources": ["S00", "S01"],
            "evidence_received_count": 2,
            "evidence_partition": {
                "observed_sources": ["S00", "S01"],
                "source_count": 2,
                "winner_sources": ["S00", "S01"],
                "dissenting_sources": [],
                "missing_sources": ["S02", "S03"],
                "tie_at_top": False,
            },
            "application_count": 1,
            "representative_source": "S00",
            "applied_source": "S00",
            "consumed_sources": ["S00", "S01"],
            "late_evidence": {
                "direct_policy_rejected": True,
                "transport_admitted_sources": [],
                "snapshot_unchanged": True,
                "post_late_status": "AUTHORIZED",
            },
            "checkpoint_restore_matches": True,
            "restored_final_status": "AUTHORIZED",
            "durable_log_verified": True,
            "policy_authorized_despite_dissent": False,
            "policy_authorized_despite_missing": True,
            "evidence_link_count_after_finalization": 2,
        }
        self.assertEqual(validate_attempt_result(valid), valid)
        invalid = dict(valid, application_count=0)
        with self.assertRaisesRegex(ValueError, "VM application"):
            validate_attempt_result(invalid)
        invalid = dict(
            valid,
            late_evidence={
                **valid["late_evidence"],
                "transport_admitted_sources": ["S02"],
            },
        )
        with self.assertRaisesRegex(ValueError, "late evidence"):
            validate_attempt_result(invalid)

    def test_strict_conditions_reject_invalid_boolean_and_scenario(self):
        with self.assertRaisesRegex(ValueError, "strict"):
            validate_condition({"strict": 1, "scenario": "partial_unanimous", "quorum": 2})
        with self.assertRaisesRegex(ValueError, "scenario"):
            validate_condition({"strict": True, "scenario": "unknown", "quorum": 2})

    def test_first_live_ci_summary_digest_and_outcome_counts(self):
        summary_path = (
            Path(__file__).with_name("results") / "ci-run-310-summary.json"
        )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        core = {
            key: value for key, value in summary.items()
            if key != "summary_digest"
        }
        calculated = hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(summary["summary_digest"], calculated)
        self.assertEqual(summary["workflow"]["run_number"], 310)
        self.assertEqual(summary["matrix"]["condition_count"], 10)
        self.assertEqual(summary["invariants"]["attempt_count"], 30)
        self.assertEqual(summary["invariants"]["evidence_record_count"], 90)
        self.assertEqual(
            summary["invariants"]["final_status_counts"],
            {"AUTHORIZED": 15, "CONFLICT": 6, "REFUSED": 9},
        )
        self.assertEqual(
            summary["invariants"]["tied_split_miss_representative_count"], 3
        )
        self.assertEqual(
            summary["invariants"]["checkpoint_restore_success_count"], 30
        )
        self.assertEqual(
            summary["invariants"]["direct_late_policy_rejection_count"], 30
        )


if __name__ == "__main__":
    unittest.main()
