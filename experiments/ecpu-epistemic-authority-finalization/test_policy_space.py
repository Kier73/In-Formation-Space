import hashlib
import json
import unittest
from pathlib import Path

from run_policy_space import build_report, digest, validate_report
from policy_space import (
    POLICY_NAMES,
    SOURCE_STATES,
    evaluate_policy,
    evidence_counts,
    enumerate_evidence_space,
    summarize_policy_space,
    validate_policy_space,
)


class PolicySpaceTests(unittest.TestCase):
    def test_all_four_source_absent_hit_miss_patterns_are_enumerated(self):
        records = enumerate_evidence_space()
        self.assertEqual(len(records), 3 ** 4)
        self.assertEqual(len({record["pattern"] for record in records}), 81)
        self.assertEqual(set(SOURCE_STATES), {"-", "H", "M"})
        summary = summarize_policy_space(records)
        self.assertEqual(summary["pattern_count"], 81)
        self.assertIsNone(summary["probability_assignment"])
        for name in POLICY_NAMES:
            counts = summary["policies"][name]["state_counts"]
            self.assertEqual(sum(counts.values()), 81)

    def test_known_partial_unanimous_pattern_distinguishes_strict_and_permissive(self):
        counts = evidence_counts(("H", "H", "-", "-"))
        self.assertEqual(
            evaluate_policy("runtime_strict", counts)["status"], "REFUSED"
        )
        self.assertEqual(
            evaluate_policy("runtime_permissive", counts)["status"], "AUTHORIZED"
        )
        self.assertEqual(
            evaluate_policy("observed_unanimity_quorum", counts)["status"], "AUTHORIZED"
        )
        self.assertEqual(
            evaluate_policy("complete_roster_unique_plurality", counts)["status"],
            "REFUSED",
        )

    def test_majority_dissent_and_tied_split_are_separated(self):
        majority = evidence_counts(("H", "H", "H", "M"))
        self.assertEqual(
            evaluate_policy("runtime_permissive", majority)["status"], "AUTHORIZED"
        )
        self.assertEqual(
            evaluate_policy("runtime_strict", majority)["status"], "CONFLICT"
        )
        self.assertEqual(
            evaluate_policy("configured_majority", majority)["status"], "AUTHORIZED"
        )
        self.assertEqual(
            evaluate_policy("observed_unanimity_quorum", majority)["status"], "CONFLICT"
        )

        tied = evidence_counts(("H", "H", "M", "M"))
        self.assertTrue(tied["top_tie"])
        self.assertEqual(
            evaluate_policy("runtime_permissive", tied)["status"], "AUTHORIZED"
        )
        self.assertEqual(
            evaluate_policy("unique_plurality_quorum", tied)["status"], "CONFLICT"
        )
        self.assertEqual(
            evaluate_policy("observed_strict_majority", tied)["status"], "CONFLICT"
        )

    def test_one_source_never_reaches_quorum(self):
        counts = evidence_counts(("H", "-", "-", "-"))
        for name in POLICY_NAMES:
            self.assertNotEqual(
                evaluate_policy(name, counts)["status"], "AUTHORIZED", name
            )

    def test_margin_policy_requires_two_source_lead(self):
        one_margin = evidence_counts(("H", "H", "M", "-"))
        two_margin = evidence_counts(("H", "H", "H", "M"))
        self.assertEqual(
            evaluate_policy("plurality_margin_two", one_margin)["status"],
            "CONFLICT",
        )
        self.assertEqual(
            evaluate_policy("plurality_margin_two", two_margin)["status"],
            "AUTHORIZED",
        )

    def test_exhaustive_records_and_summary_are_reconstructible(self):
        records = enumerate_evidence_space()
        summary = summarize_policy_space(records)
        validate_policy_space(records, summary)
        tampered = [dict(records[0]), *records[1:]]
        tampered[0]["missing_count"] = 99
        with self.assertRaisesRegex(ValueError, "reconstruction"):
            validate_policy_space(tampered, summary)

    def test_policy_space_report_digest_and_reconstruction(self):
        report = build_report()
        validate_report(report)
        self.assertEqual(report["pattern_model"]["pattern_count"], 81)
        self.assertIsNone(report["pattern_model"]["probability_assignment"])
        core = {
            key: value for key, value in report.items()
            if key != "report_digest"
        }
        self.assertEqual(report["report_digest"], digest(core))
        altered = dict(report, policy_names=list(reversed(report["policy_names"])))
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_report(altered)

    def test_first_exhaustive_policy_space_receipt_digest(self):
        receipt_path = (
            Path(__file__).with_name("results")
            / "policy-space-ci-run-329-summary.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        core = {
            key: value for key, value in receipt.items()
            if key != "summary_digest"
        }
        calculated = hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(receipt["summary_digest"], calculated)
        self.assertEqual(receipt["matrix"]["pattern_count"], 81)
        self.assertEqual(receipt["matrix"]["policy_count"], 8)
        self.assertEqual(
            receipt["policy_results"]["runtime_permissive"]["authorized_on_tie"],
            6,
        )


if __name__ == "__main__":
    unittest.main()
