import copy
import unittest

from contention import (run_experiment, validate_bundle, inspect, derive_resource_trace,
                        make_trace, predict, delays, _digest, RESOURCE)
from test_operation_path_criticality import span


def rehash(bundle):
    bundle["bundle_digest"] = _digest({k: v for k, v in bundle.items() if k != "bundle_digest"})
    return bundle


def rechain(receipts):
    previous = None
    for index, receipt in enumerate(receipts):
        receipt["ordinal"], receipt["previous_digest"] = index, previous
        receipt["receipt_digest"] = _digest({k: v for k, v in receipt.items() if k != "receipt_digest"})
        previous = receipt["receipt_digest"]


def synthetic(order=("a", "b")):
    """Exact oracle: serialized branch work 80+80, join 10, no overhead."""
    spans = [span(span_id="root", operation_id="ops002.root", start=0, end=170)]
    for index, name in enumerate(order):
        s = span(span_id=name, operation_id=f"ops002.{name}", start=index*80, end=(index+1)*80)
        spans.append(s)
    spans.append(span(span_id="join", operation_id="ops002.join", start=160, end=170))
    for s in spans:
        if s["span_id"] != "root":
            s["context"] = {"requested_sleep_ns": 10 if s["span_id"] == "join" else 80}
        s["span_digest"] = _digest({k: v for k, v in s.items() if k != "span_digest"})
    by_id = {s["span_id"]: s for s in spans}
    receipts = []
    for index, name in enumerate(order):
        receipts.append({"schema": "in-formation.mutex-work-receipt/0.1", "resource_id": RESOURCE,
            "attempt_id": "attempt-1", "clock_actor_id": "host-a", "clock_segment_id": "run-1",
            "ordinal": index, "span_digest": by_id[name]["span_digest"], "requested_ns": 0,
            "acquired_ns": index*80, "release_pending_ns": (index+1)*80, "previous_digest": None})
    rechain(receipts)
    trial = {"requested_sleep_ns": {"a": 80, "b": 80, "join": 10}, "spans": spans,
             "trace": make_trace(spans, "attempt-1"), "resource_receipts": receipts}
    trial["resource_trace"], _ = derive_resource_trace(trial)
    return trial


class ContentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = run_experiment(blocks=2, baseline_ns=3_000_000,
                                   reduced_ns=1_000_000, join_ns=1_000_000, seed=19)

    def test_exact_missing_edge_changes_prediction_in_either_resource_order(self):
        config = dict(blocks=1, baseline_ns=80, reduced_ns=20, join_ns=10, seed=0)
        for order in [("a", "b"), ("b", "a")]:
            baseline = synthetic(order)
            reports, actual_order = inspect(baseline, delays(config, "baseline"))
            self.assertEqual(actual_order, list(order))
            self.assertEqual(reports["fork_join"]["root_slack_ns"], 80)
            self.assertEqual(reports["resource_order"]["root_slack_ns"], 0)
            for variant, expected in [("control", (0, 0)), ("a", (0, 60)),
                                      ("b", (0, 60)), ("both", (60, 120))]:
                predicted = predict(baseline, config, variant)
                self.assertEqual(tuple(predicted[m]["counterfactual_benefit_ns"]
                                       for m in ("fork_join", "resource_order")), expected)

    def test_live_bundle_reconstructs_with_no_timing_threshold(self):
        self.assertEqual(validate_bundle(self.bundle), self.bundle)
        rows = self.bundle["analysis"]["paired_comparisons"]
        self.assertEqual(len(rows), 16)
        for row in rows:
            self.assertEqual(row["observed_root_gain_ns"],
                             row["observed_path_gain_ns"] + row["observed_slack_gain_ns"])
            self.assertEqual(row["root_gain_minus_predicted_path_gain_ns"],
                             row["observed_root_gain_ns"] - row["predicted_path_gain_ns"])

    def test_resource_evidence_required_without_falling_back_to_timestamps(self):
        trial = synthetic()
        trial["resource_receipts"] = []
        with self.assertRaisesRegex(ValueError, "two resource"):
            inspect(trial, trial["requested_sleep_ns"])

    def test_reordered_rehashed_chain_cannot_override_span_order(self):
        trial = synthetic()
        trial["resource_receipts"].reverse()
        rechain(trial["resource_receipts"])
        with self.assertRaisesRegex(ValueError, "interval or handoff"):
            derive_resource_trace(trial)

    def test_cross_trial_cross_clock_and_cross_resource_receipts_rejected(self):
        for key, value in [("attempt_id", "other"), ("clock_actor_id", "other"),
                           ("clock_segment_id", "other"), ("resource_id", "other")]:
            trial = synthetic()
            trial["resource_receipts"][0][key] = value
            rechain(trial["resource_receipts"])
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "identity differs"):
                derive_resource_trace(trial)

    def test_duplicate_span_false_coordinates_and_broken_chain_rejected(self):
        for key, value in [("span_digest", "duplicate"), ("acquired_ns", True),
                           ("requested_ns", -1), ("release_pending_ns", 171)]:
            trial = synthetic()
            trial["resource_receipts"][1][key] = (trial["resource_receipts"][0][key]
                if value == "duplicate" else value)
            rechain(trial["resource_receipts"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                derive_resource_trace(trial)
        trial = synthetic()
        trial["resource_receipts"][1]["previous_digest"] = "0" * 64
        receipt = trial["resource_receipts"][1]
        receipt["receipt_digest"] = _digest({k: v for k, v in receipt.items() if k != "receipt_digest"})
        with self.assertRaisesRegex(ValueError, "chain"):
            derive_resource_trace(trial)

    def test_resource_edge_cannot_be_silently_dropped(self):
        trial = synthetic()
        trial["resource_trace"] = trial["trace"]
        with self.assertRaisesRegex(ValueError, "receipt reconstruction"):
            inspect(trial, trial["requested_sleep_ns"])

    def test_rehashed_analysis_and_prediction_tampering_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["analysis"]["paired_comparisons"][0]["root_gain_minus_predicted_path_gain_ns"] += 1
        with self.assertRaisesRegex(ValueError, "analysis differs"):
            validate_bundle(rehash(bundle))
        bundle = copy.deepcopy(self.bundle)
        entry = bundle["blocks"][0]["variants"]["a"]
        entry["predictions"]["resource_order"] = entry["predictions"]["fork_join"]
        with self.assertRaisesRegex(ValueError, "predictions differ"):
            validate_bundle(rehash(bundle))


if __name__ == "__main__":
    unittest.main()
