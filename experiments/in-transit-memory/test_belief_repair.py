import copy
import json
import unittest
from fractions import Fraction
from pathlib import Path

from adaptive_repair import build_adaptive_repair_report
from belief_repair import (
    DEFAULT_SCENARIOS,
    BeliefRepairError,
    _sensor_branches,
    _transition_outcomes,
    build_belief_repair_report,
    build_default_sweep,
    summarize_default_sweep,
    validate_belief_repair_report,
)


class BeliefRepairTests(unittest.TestCase):
    def parameters(self, **overrides):
        result = {
            "scenario_name": "belief-unit-test",
            "slots": 5,
            "recovery_threshold": 3,
            "horizon": 4,
            "good_loss_probability": "1/100",
            "bad_loss_probability": "9/20",
            "good_to_bad_probability": "3/25",
            "bad_to_good_probability": "3/10",
            "initial_bad_probability": "2/21",
            "sensor_sensitivity": "4/5",
            "sensor_false_positive_rate": "1/10",
            "repair_cost": "1/20",
            "sensing_cost": "1/100",
        }
        result.update(overrides)
        return result

    def test_bayes_sensor_branches_preserve_total_probability(self):
        model = {
            "sensor_sensitivity": Fraction(4, 5),
            "sensor_false_positive_rate": Fraction(1, 10),
        }
        branches = _sensor_branches(Fraction(2, 21), model)
        self.assertEqual(sum((item[1] for item in branches), Fraction(0)), Fraction(1))
        self.assertEqual({item[0] for item in branches}, {"good", "bad"})
        self.assertGreater(
            next(item[2] for item in branches if item[0] == "bad"),
            Fraction(2, 21),
        )
        self.assertLess(
            next(item[2] for item in branches if item[0] == "good"),
            Fraction(2, 21),
        )

    def test_backward_induction_matches_independent_forward_reconstruction(self):
        report = build_belief_repair_report(**self.parameters())
        controller = report["controller"]
        forward = controller["forward_reconstruction"]
        self.assertEqual(controller["initial_value_from_backward_induction"], forward["expected_utility"])
        self.assertEqual(
            Fraction(forward["expected_utility"]),
            Fraction(forward["survival_probability"])
            - Fraction(report["model"]["repair_cost"]) * Fraction(forward["expected_repair_count"])
            - Fraction(report["model"]["sensing_cost"]) * Fraction(forward["expected_sensing_count"]),
        )

    def test_uninformative_positive_cost_sensor_is_never_selected(self):
        report = build_belief_repair_report(**self.parameters(
            sensor_sensitivity="1/2",
            sensor_false_positive_rate="1/2",
            sensing_cost="1/1000",
        ))
        self.assertTrue(all(
            node["selected_observation_action"] == "skip"
            for node in report["controller"]["decision_nodes"]
        ))
        self.assertEqual(
            report["controller"]["forward_reconstruction"]["expected_sensing_count"],
            "0/1",
        )

    def test_perfect_free_sensor_matches_fully_observed_mre003(self):
        params = self.parameters(
            sensor_sensitivity="1",
            sensor_false_positive_rate="0",
            sensing_cost="0",
            repair_cost="1/20",
            horizon=4,
        )
        belief = build_belief_repair_report(**params)
        fully_observed = build_adaptive_repair_report(
            scenario_name="fully-observed-reference",
            slots=params["slots"],
            recovery_threshold=params["recovery_threshold"],
            horizon=params["horizon"],
            good_loss_probability=float(Fraction(params["good_loss_probability"])),
            bad_loss_probability=float(Fraction(params["bad_loss_probability"])),
            good_to_bad_probability=float(Fraction(params["good_to_bad_probability"])),
            bad_to_good_probability=float(Fraction(params["bad_to_good_probability"])),
            initial_bad_probability=float(Fraction(params["initial_bad_probability"])),
            repair_cost=float(Fraction(params["repair_cost"])),
        )
        belief_value = float(Fraction(belief["controller"]["initial_value_from_backward_induction"]))
        observed_value = fully_observed["adaptive_policy"]["expected_utility"]
        self.assertAlmostEqual(belief_value, observed_value, places=12)

    def test_positive_sensing_cost_cannot_improve_over_same_model_at_zero_cost(self):
        free = build_belief_repair_report(**self.parameters(sensing_cost="0"))
        costly = build_belief_repair_report(**self.parameters(sensing_cost="1/10"))
        self.assertGreaterEqual(
            Fraction(free["controller"]["initial_value_from_backward_induction"]),
            Fraction(costly["controller"]["initial_value_from_backward_induction"]),
        )

    def test_report_reconstructs_exactly_and_detects_tampering(self):
        report = build_belief_repair_report(**self.parameters())
        self.assertEqual(validate_belief_repair_report(report), report)
        altered = copy.deepcopy(report)
        altered["controller"]["decision_nodes"][0]["selected_observation_action"] = "sense"
        with self.assertRaisesRegex(ValueError, "reconstruction mismatch"):
            validate_belief_repair_report(altered)

    def test_default_sweep_digest_and_coverage_reconstruct(self):
        sweep = build_default_sweep()
        self.assertEqual(len(sweep["reports"]), len(DEFAULT_SCENARIOS))
        core = {key: value for key, value in sweep.items() if key != "sweep_digest_sha256"}
        from belief_repair import _digest
        self.assertEqual(sweep["sweep_digest_sha256"], _digest(core))
        receipt_path = Path(__file__).with_name("results") / "belief-repair-scan-summary.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        expected_receipt = summarize_default_sweep(sweep)
        self.assertEqual(set(receipt), set(expected_receipt))
        for field in sorted(expected_receipt):
            self.assertEqual(
                receipt[field],
                expected_receipt[field],
                msg=f"checked-in receipt differs from reconstructed field: {field}",
            )
        for spec, report, summary in zip(DEFAULT_SCENARIOS, sweep["reports"], sweep["summary"]):
            self.assertEqual(validate_belief_repair_report(report), report)
            self.assertEqual(report["scenario_name"], spec["scenario_name"])
            self.assertGreaterEqual(Fraction(summary["utility_gain_over_no_sensing"]), 0)
            self.assertEqual(summary["scenario_name"], spec["scenario_name"])

    def test_survivor_count_updates_belief_about_the_next_channel_state(self):
        model = {
            "good_loss_probability": Fraction(1, 100),
            "bad_loss_probability": Fraction(9, 20),
            "good_to_bad_probability": Fraction(3, 25),
            "bad_to_good_probability": Fraction(3, 10),
        }
        outcomes = _transition_outcomes(
            starting_packets=5, bad_belief=Fraction(1, 5), model=model
        )
        next_beliefs = {survivors: belief for survivors, _probability, belief in outcomes}
        self.assertLess(next_beliefs[5], next_beliefs[1])

    def test_informative_paid_sensor_can_improve_utility_over_no_sensing(self):
        informed = build_belief_repair_report(**self.parameters())
        no_sensor = build_belief_repair_report(**self.parameters(
            sensor_sensitivity="1/2",
            sensor_false_positive_rate="1/2",
            sensing_cost="0",
        ))
        informed_value = Fraction(informed["controller"]["initial_value_from_backward_induction"])
        no_sensor_value = Fraction(no_sensor["controller"]["initial_value_from_backward_induction"])
        self.assertGreater(informed_value, no_sensor_value)
        self.assertGreater(
            Fraction(informed["controller"]["forward_reconstruction"]["expected_sensing_count"]),
            0,
        )

    def test_invalid_probabilities_and_horizon_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "good_loss_probability"):
            build_belief_repair_report(**self.parameters(good_loss_probability="2"))
        with self.assertRaisesRegex(ValueError, "horizon"):
            build_belief_repair_report(**self.parameters(horizon=11))
        with self.assertRaisesRegex(ValueError, "sensing_cost"):
            build_belief_repair_report(**self.parameters(sensing_cost="-1/2"))


if __name__ == "__main__":
    unittest.main()
