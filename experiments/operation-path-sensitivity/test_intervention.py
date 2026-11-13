import copy
import unittest

from intervention import (run_experiment, validate_bundle, settings, compare,
                          inspect_trial, delays, _digest)
from operation_path_criticality import build_operation_path_trace


def rehash(bundle):
    bundle["bundle_digest"] = _digest({k: v for k, v in bundle.items() if k != "bundle_digest"})
    return bundle


class InterventionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise real threads and clocks, but assert no timing thresholds.
        cls.bundle = run_experiment(blocks=2, baseline_ns=3_000_000,
                                    reduced_ns=1_000_000, join_ns=1_000_000, seed=17)

    def test_live_evidence_reconstructs_without_speed_threshold(self):
        bundle = self.bundle
        self.assertEqual(validate_bundle(bundle), bundle)
        rows = bundle["analysis"]["paired_comparisons"]
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertEqual(row["observed_root_gain_ns"],
                             row["observed_path_gain_ns"] + row["observed_slack_gain_ns"])
            if row["variant"] == "control":
                self.assertEqual(row["predicted_path_gain_ns"], 0)

    def test_slowdowns_and_prediction_error_keep_their_sign(self):
        baseline = dict(known_dependency_path_ns=10, root_elapsed_ns=15, root_slack_ns=5)
        observed = dict(known_dependency_path_ns=12, root_elapsed_ns=20, root_slack_ns=8)
        row = compare(baseline, observed, {"counterfactual_benefit_ns": 4})
        self.assertEqual(row, dict(predicted_path_gain_ns=4, observed_path_gain_ns=-2,
            observed_root_gain_ns=-5, observed_slack_gain_ns=-3, path_prediction_error_ns=-6))

    def test_rehashed_summary_forgery_is_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["analysis"]["paired_comparisons"][0]["observed_root_gain_ns"] += 1
        with self.assertRaisesRegex(ValueError, "analysis differs"):
            validate_bundle(rehash(bundle))

    def test_rehashed_prediction_forgery_is_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        prediction = bundle["blocks"][0]["variants"]["a"]["prediction"]
        prediction["counterfactual_benefit_ns"] += 1
        prediction["report_digest"] = _digest({k: v for k, v in prediction.items() if k != "report_digest"})
        with self.assertRaisesRegex(ValueError, "prediction differs"):
            validate_bundle(rehash(bundle))

    def test_missing_dependency_is_rejected_even_with_valid_trace_digest(self):
        trial = copy.deepcopy(self.bundle["blocks"][0]["baseline"])
        t = trial["trace"]
        trial["trace"] = build_operation_path_trace(path_id=t["path_id"], attempt_id=t["attempt_id"],
            root_span_digest=t["root_span_digest"], operation_span_digests=t["operation_span_digests"],
            must_complete_before=t["must_complete_before"][:1])
        with self.assertRaisesRegex(ValueError, "fixed fork/join"):
            inspect_trial(trial, delays(self.bundle["config"], "baseline"))

    def test_changed_schedule_or_duplicate_trial_is_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["blocks"][0]["order"].reverse()
        with self.assertRaisesRegex(ValueError, "order or coverage"):
            validate_bundle(rehash(bundle))
        bundle = copy.deepcopy(self.bundle)
        bundle["blocks"][0]["variants"]["control"]["trial"] = bundle["blocks"][0]["baseline"]
        with self.assertRaisesRegex(ValueError, "duplicate trial"):
            validate_bundle(rehash(bundle))

    def test_plan_and_evidence_cannot_silently_diverge(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["blocks"][0]["variants"]["both"]["trial"]["requested_sleep_ns"]["a"] += 1
        with self.assertRaisesRegex(ValueError, "delays differ"):
            validate_bundle(rehash(bundle))

    def test_invalid_settings(self):
        valid = dict(blocks=1, baseline_ns=10, reduced_ns=2, join_ns=1, seed=0)
        for changes in [dict(blocks=0), dict(blocks=True), dict(join_ns=-1),
                        dict(baseline_ns=2), dict(reduced_ns=10), dict(seed=1.0)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                settings(**{**valid, **changes})


if __name__ == "__main__":
    unittest.main()
