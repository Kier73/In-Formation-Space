import hashlib
import itertools
import json
import unittest
from pathlib import Path

import jsonschema
from run_adjudication_space import build_report, digest, validate_report

from review_policy_space import (
    POLICIES,
    PROPOSER,
    REVIEWERS,
    REVIEW_STATES,
    evaluate_review_policy,
    enumerate_review_space,
    review_counts,
    summarize_review_space,
    validate_review_space,
)


class ReviewPolicySpaceTests(unittest.TestCase):
    def test_all_reviewer_presence_vote_and_abstention_patterns_are_enumerated(self):
        records = enumerate_review_space()
        self.assertEqual(len(records), 4 ** len(REVIEWERS))
        self.assertEqual(len({tuple(record["pattern"]) for record in records}), 64)
        self.assertEqual(set(REVIEW_STATES), {"ABSENT", "APPROVE", "REJECT", "ABSTAIN"})
        summary = summarize_review_space(records)
        self.assertEqual(summary["pattern_count"], 64)
        self.assertEqual(summary["policy_count"], len(POLICIES))
        self.assertIsNone(summary["probability_assignment"])
        for policy in POLICIES:
            counts = summary["policies"][policy]["outcome_counts"]
            self.assertEqual(sum(counts.values()), 64)

    def test_proposer_exclusion_changes_eligible_vote_set(self):
        pattern = ("APPROVE", "APPROVE", "ABSENT")
        included = evaluate_review_policy("single_approval_permissive", pattern)
        excluded = evaluate_review_policy("independent_two_of_two", pattern)
        self.assertEqual(included["outcome"], "ACCEPTED")
        self.assertEqual(excluded["outcome"], "INCONCLUSIVE")
        self.assertTrue(included["proposer_vote_counted"])
        self.assertNotIn(PROPOSER, excluded["eligible_reviewers"])

    def test_abstention_counts_as_participation_but_not_approval(self):
        pattern = ("ABSENT", "APPROVE", "ABSTAIN")
        decision = evaluate_review_policy("independent_two_of_two", pattern)
        self.assertEqual(decision["present_eligible_reviewers"], ["R01", "R02"])
        self.assertEqual(decision["approval_count"], 1)
        self.assertEqual(decision["abstention_count"], 1)
        self.assertEqual(decision["outcome"], "INCONCLUSIVE")

    def test_single_approval_and_two_of_three_have_distinct_coverage(self):
        only_proposer = ("APPROVE", "ABSENT", "ABSENT")
        two_approvals = ("APPROVE", "APPROVE", "ABSENT")
        self.assertEqual(
            evaluate_review_policy("single_approval_permissive", only_proposer)["outcome"],
            "ACCEPTED",
        )
        self.assertEqual(
            evaluate_review_policy("simple_majority_three", only_proposer)["outcome"],
            "INCONCLUSIVE",
        )
        self.assertEqual(
            evaluate_review_policy("simple_majority_three", two_approvals)["outcome"],
            "ACCEPTED",
        )

    def test_veto_and_split_thresholds_are_explicit(self):
        # Independent reviewers split one-to-one: neither independent rule
        # reaches its two-vote approval threshold; the veto rule is inconclusive
        # because its one-vote rejection threshold is met and approval is not.
        approve_and_reject = ("ABSENT", "APPROVE", "REJECT")
        veto = evaluate_review_policy("independent_two_of_two_veto", approve_and_reject)
        consensus = evaluate_review_policy("independent_two_of_two", approve_and_reject)
        self.assertEqual(veto["outcome"], "REJECTED")
        self.assertFalse(veto["conflicting_thresholds"])
        self.assertEqual(consensus["outcome"], "INCONCLUSIVE")
        self.assertFalse(consensus["conflicting_thresholds"])

        # Both thresholds are met only when the proposer is eligible and
        # two approvals coexist with one rejection.
        both_thresholds = ("APPROVE", "APPROVE", "REJECT")
        conflicted = evaluate_review_policy("two_approval_veto", both_thresholds)
        self.assertEqual(conflicted["outcome"], "INCONCLUSIVE")
        self.assertTrue(conflicted["conflicting_thresholds"])

        reject_and_abstain = ("ABSENT", "REJECT", "ABSTAIN")
        self.assertEqual(
            evaluate_review_policy("independent_two_of_two_veto", reject_and_abstain)["outcome"],
            "REJECTED",
        )
        self.assertEqual(
            evaluate_review_policy("independent_two_of_two", reject_and_abstain)["outcome"],
            "INCONCLUSIVE",
        )

    def test_unanimity_requires_all_three_and_rejects_any_dissent(self):
        unanimous = ("APPROVE", "APPROVE", "APPROVE")
        dissent = ("APPROVE", "APPROVE", "REJECT")
        self.assertEqual(
            evaluate_review_policy("unanimous_three", unanimous)["outcome"],
            "ACCEPTED",
        )
        self.assertEqual(
            evaluate_review_policy("unanimous_three", dissent)["outcome"],
            "REJECTED",
        )

    def test_no_pattern_without_any_eligible_review_can_be_accepted(self):
        for policy_name, policy in POLICIES.items():
            pattern = ("APPROVE", "ABSENT", "ABSENT")
            result = evaluate_review_policy(policy_name, pattern)
            if not policy["include_proposer"]:
                self.assertEqual(result["outcome"], "INCONCLUSIVE", policy_name)

    def test_policy_space_reconstruction_detects_tampering(self):
        records = enumerate_review_space()
        summary = summarize_review_space(records)
        validate_review_space(records, summary)
        altered = [dict(records[0]), *records[1:]]
        altered[0]["pattern"] = ["APPROVE", "APPROVE", "APPROVE"]
        with self.assertRaisesRegex(ValueError, "reconstruction"):
            validate_review_space(altered, summary)

    def test_policy_schema_rejects_boolean_threshold(self):
        invalid = dict(POLICIES["simple_majority_three"])
        invalid["minimum_distinct_reviewers"] = True
        with self.assertRaisesRegex(ValueError, "positive integer"):
            evaluate_review_policy_with_policy(invalid, ("APPROVE", "APPROVE", "ABSENT"))

    def test_report_digest_and_exhaustive_reconstruction(self):
        report = build_report()
        validate_report(report)
        self.assertEqual(report["state_model"]["pattern_count"], 64)
        self.assertEqual(len(report["policy_ids"]), 7)
        self.assertIsNone(report["state_model"]["probability_assignment"])
        core = {key: value for key, value in report.items() if key != "report_digest"}
        self.assertEqual(report["report_digest"], digest(core))
        tampered = dict(report, policy_ids=list(reversed(report["policy_ids"])))
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_report(tampered)

    def test_summary_schema_accepts_expected_finite_space(self):
        summary = {
            "format": "in-formation.authority-adjudication-review-space-summary",
            "schema": "in-formation.authority-adjudication-review-space/0.1/summary",
            "experiment_id": "authority-adjudication-review-space-v1",
            "pattern_count": 64,
            "policy_count": 7,
            "policy_summary": {name: {} for name in POLICIES},
            "report_digest": "a" * 64,
            "interpretation_limits": ["finite enumeration only"],
            "summary_digest": "b" * 64,
        }
        schema = json.loads(
            Path(__file__).with_name("summary.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(summary, schema)



def evaluate_review_policy_with_policy(policy, pattern):
    from review_policy_space import _validate_policy
    _validate_policy(policy)


if __name__ == "__main__":
    unittest.main()
