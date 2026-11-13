import copy
import hashlib
import json
import unittest
from fractions import Fraction

from delayed_evidence import (
    DEFAULT_SCENARIOS,
    DelayedEvidenceError,
    _arrival_branches,
    _belief_from_key,
    _belief_key,
    _marginal_bad_probability,
    build_default_sweep,
    build_delayed_evidence_report,
    validate_delayed_evidence_report,
)


class DelayedEvidenceTests(unittest.TestCase):
    def test_backward_value_matches_independent_forward_reconstruction(self):
        for scenario in DEFAULT_SCENARIOS:
            with self.subTest(scenario=scenario["scenario_name"]):
                report = build_delayed_evidence_report(**scenario)
                controller = report["controller"]
                forward = controller["forward_reconstruction"]
                self.assertEqual(
                    controller["initial_value_from_backward_induction"],
                    forward["expected_utility"],
                )
                self.assertEqual(
                    Fraction(forward["expected_utility"]),
                    Fraction(forward["survival_probability"])
                    - Fraction(report["model"]["repair_cost"])
                    * Fraction(forward["expected_repair_count"]),
                )

    def test_out_of_order_arrival_keeps_measurement_and_arrival_epochs_distinct(self):
        report = build_delayed_evidence_report(**DEFAULT_SCENARIOS[2])
        nodes = report["controller"]["decision_nodes"]
        candidates = [
            node for node in nodes
            if node["time_index"] == 2
            and [event["sequence"] for event in node["evidence_history"]] == [2, 1]
            and all(
                event["delivery_status"] == "delivered"
                for event in node["evidence_history"]
            )
        ]
        self.assertTrue(candidates, "expected a path where sequence 2 arrives before sequence 1")
        stale_events = [
            event for event in candidates[0]["evidence_history"]
            if event["sequence"] == 1
        ]
        self.assertEqual(len(stale_events), 1)
        stale = stale_events[0]
        self.assertEqual(stale["measurement_epoch"], 0)
        self.assertEqual(stale["arrival_epoch"], 2)
        self.assertEqual(stale["age_epochs"], 2)
        self.assertNotEqual(
            stale["measurement_state_bad_probability_after"],
            stale["current_state_bad_probability_after"],
            "late evidence must preserve distinct beliefs about the measured and current states",
        )

    def test_arrival_order_is_not_rewritten_to_sequence_order(self):
        in_order = build_delayed_evidence_report(**DEFAULT_SCENARIOS[1])
        out_of_order = build_delayed_evidence_report(**DEFAULT_SCENARIOS[2])

        in_order_epoch_one = [
            node for node in in_order["controller"]["decision_nodes"]
            if node["time_index"] == 1
            and node["evidence_history"]
        ]
        out_of_order_epoch_one = [
            node for node in out_of_order["controller"]["decision_nodes"]
            if node["time_index"] == 1
            and node["evidence_history"]
        ]
        self.assertTrue(in_order_epoch_one)
        self.assertTrue(out_of_order_epoch_one)
        self.assertTrue(all(
            [event["sequence"] for event in node["evidence_history"]] == [1]
            for node in in_order_epoch_one
        ))
        self.assertTrue(all(
            [event["sequence"] for event in node["evidence_history"]] == [2]
            for node in out_of_order_epoch_one
        ))

        out_of_order_epoch_two = [
            node for node in out_of_order["controller"]["decision_nodes"]
            if node["time_index"] == 2
            and len(node["evidence_history"]) == 2
            and all(event["delivery_status"] == "delivered"
                    for event in node["evidence_history"])
        ]
        self.assertTrue(out_of_order_epoch_two)
        self.assertTrue(all(
            [event["sequence"] for event in node["evidence_history"]] == [2, 1]
            for node in out_of_order_epoch_two
        ))
        self.assertNotEqual(
            in_order["controller"]["policy_digest_sha256"],
            out_of_order["controller"]["policy_digest_sha256"],
        )

    def test_timeout_is_explicit_and_does_not_condition_channel_belief(self):
        report = build_delayed_evidence_report(**DEFAULT_SCENARIOS[3])
        nodes = [
            node for node in report["controller"]["decision_nodes"]
            if node["time_index"] == 2
            and any(event["sequence"] == 1 for event in node["evidence_history"])
        ]
        self.assertTrue(nodes)
        for node in nodes:
            event = next(
                item for item in node["evidence_history"]
                if item["sequence"] == 1
            )
            self.assertEqual(event["delivery_status"], "timeout")
            self.assertIsNone(event["signal"])
            self.assertEqual(event["belief_digest_before"], event["belief_digest_after"])
            self.assertEqual(
                event["measurement_state_bad_probability_before"],
                event["measurement_state_bad_probability_after"],
            )
            self.assertEqual(
                event["current_state_bad_probability_before"],
                event["current_state_bad_probability_after"],
            )

    def test_evidence_digest_covers_the_arrival_and_belief_record(self):
        report = build_delayed_evidence_report(**DEFAULT_SCENARIOS[2])
        events = [
            event
            for node in report["controller"]["decision_nodes"]
            for event in node["evidence_history"]
        ]
        self.assertTrue(events)
        for event in events:
            body = {key: value for key, value in event.items()
                    if key != "evidence_digest_sha256"}
            calculated = hashlib.sha256(
                json.dumps(
                    body, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(event["evidence_digest_sha256"], calculated)

    def test_belief_keys_round_trip_and_are_normalized(self):
        report = build_delayed_evidence_report(**DEFAULT_SCENARIOS[2])
        for node in report["controller"]["decision_nodes"]:
            self.assertEqual(len(node["belief_digest_sha256"]), 64)
            self.assertEqual(len(node["evidence_history_digest_sha256"]), 64)

    def test_each_arrival_epoch_branches_to_total_probability_one(self):
        scenario = DEFAULT_SCENARIOS[2]
        report = build_delayed_evidence_report(**scenario)
        model = report["model"]
        from delayed_evidence import _validate_model
        validated = _validate_model(
            slots=model["slots"],
            recovery_threshold=model["recovery_threshold"],
            horizon=model["horizon"],
            good_loss_probability=model["good_loss_probability"],
            bad_loss_probability=model["bad_loss_probability"],
            good_to_bad_probability=model["good_to_bad_probability"],
            bad_to_good_probability=model["bad_to_good_probability"],
            initial_bad_probability=model["initial_bad_probability"],
            repair_cost=model["repair_cost"],
            sensor_reports=model["sensor_reports"],
        )
        belief = {
            (0,): 1 - validated["initial_bad_probability"],
            (1,): validated["initial_bad_probability"],
        }
        for time_index in range(validated["horizon"]):
            branches = _arrival_branches(
                time_index=time_index, belief=belief, model=validated
            )
            self.assertEqual(
                sum((probability for probability, _posterior, _events in branches),
                    Fraction(0)),
                Fraction(1),
            )

    def test_default_sweep_reconstructs_every_scenario_and_receipt_digest(self):
        sweep = build_default_sweep()
        self.assertEqual(len(sweep["reports"]), 4)
        self.assertEqual(
            [row["scenario_name"] for row in sweep["summary"]],
            [item["scenario_name"] for item in DEFAULT_SCENARIOS],
        )
        self.assertEqual(sweep["summary"][0]["utility_delta_vs_no_reports"], "0.00000000")
        core = {key: value for key, value in sweep.items()
                if key != "sweep_digest_sha256"}
        calculated = hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(sweep["sweep_digest_sha256"], calculated)
        for scenario, report in zip(DEFAULT_SCENARIOS, sweep["reports"]):
            self.assertEqual(validate_delayed_evidence_report(report), report)
            self.assertEqual(report["scenario_name"], scenario["scenario_name"])
        summary = sweep["summary"]
        self.assertGreater(float(summary[2]["expected_out_of_order_delivery_count"]), 0)
        self.assertGreater(float(summary[3]["expected_timeout_report_count"]), 0)

    def test_report_reconstruction_detects_policy_or_evidence_tampering(self):
        report = build_delayed_evidence_report(**DEFAULT_SCENARIOS[2])
        self.assertEqual(validate_delayed_evidence_report(report), report)
        changed = copy.deepcopy(report)
        changed["controller"]["decision_nodes"][0]["selected_action"] = "repair"
        with self.assertRaisesRegex(ValueError, "reconstruction mismatch"):
            validate_delayed_evidence_report(changed)
        changed = copy.deepcopy(report)
        changed["controller"]["decision_nodes"][-1]["evidence_history"][0]["arrival_epoch"] = 99
        with self.assertRaisesRegex(ValueError, "reconstruction mismatch"):
            validate_delayed_evidence_report(changed)

    def test_sequence_order_must_follow_measurement_order_but_arrival_may_differ(self):
        valid = dict(DEFAULT_SCENARIOS[2])
        self.assertEqual(
            build_delayed_evidence_report(**valid)["scenario_name"],
            "out_of_order_delivery",
        )
        invalid = copy.deepcopy(valid)
        invalid["sensor_reports"][0]["sequence"] = 3
        with self.assertRaisesRegex(ValueError, "sequence numbers must increase"):
            build_delayed_evidence_report(**invalid)

    def test_arrival_before_measurement_is_rejected(self):
        invalid = dict(DEFAULT_SCENARIOS[2])
        invalid["sensor_reports"] = [
            {
                "message_id": "impossible",
                "sequence": 1,
                "measurement_epoch": 1,
                "arrival_epoch": 0,
                "delivery_probability": "1",
                "sensor_sensitivity": "4/5",
                "sensor_false_positive_rate": "1/10",
            }
        ]
        with self.assertRaisesRegex(ValueError, "arrival_epoch"):
            build_delayed_evidence_report(**invalid)

    def test_policy_metrics_are_bounded_and_repair_cost_is_explicit(self):
        sweep = build_default_sweep()
        for report in sweep["reports"]:
            forward = report["controller"]["forward_reconstruction"]
            self.assertGreaterEqual(Fraction(forward["survival_probability"]), 0)
            self.assertLessEqual(Fraction(forward["survival_probability"]), 1)
            self.assertGreaterEqual(Fraction(forward["expected_repair_count"]), 0)
            self.assertEqual(
                Fraction(forward["expected_utility"]),
                Fraction(forward["survival_probability"])
                - Fraction(report["model"]["repair_cost"])
                * Fraction(forward["expected_repair_count"]),
            )


if __name__ == "__main__":
    unittest.main()
