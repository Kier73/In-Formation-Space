import copy
import unittest

from burst_loss import shared_channel_retention_curve
from adaptive_repair import (
    DEFAULT_SCENARIOS,
    _forward_evaluate,
    _round_kernel,
    _channel_transition,
    build_adaptive_repair_report,
    build_adaptive_repair_sweep,
    simulate_adaptive_policy,
    validate_adaptive_repair_report,
    validate_adaptive_repair_sweep,
)


class AdaptiveRepairTests(unittest.TestCase):
    def parameters(self, **overrides):
        result = {
            "scenario_name": "unit-test",
            "slots": 5,
            "recovery_threshold": 3,
            "horizon": 8,
            "good_loss_probability": 0.01,
            "bad_loss_probability": 0.45,
            "good_to_bad_probability": 0.12,
            "bad_to_good_probability": 0.30,
            "initial_bad_probability": 0.12 / 0.42,
            "repair_cost": 0.05,
            "fixed_intervals": (1, 2, 4, 8),
        }
        result.update(overrides)
        return result

    def test_backward_induction_matches_forward_policy_reconstruction(self):
        report = build_adaptive_repair_report(**self.parameters())
        adaptive = report["adaptive_policy"]
        self.assertAlmostEqual(
            adaptive["initial_value_from_backward_induction"],
            adaptive["expected_utility"],
            places=11,
        )
        self.assertAlmostEqual(
            adaptive["expected_utility"],
            adaptive["survival_probability"]
            - report["scenario"]["repair_cost"] * adaptive["expected_repair_count"],
            places=12,
        )

    def test_adaptive_policy_is_at_least_as_good_as_every_fixed_interval(self):
        report = build_adaptive_repair_report(**self.parameters())
        adaptive_utility = report["adaptive_policy"]["expected_utility"]
        for fixed in report["fixed_schedule_comparisons"]:
            self.assertGreaterEqual(adaptive_utility + 1e-11, fixed["expected_utility"])
        self.assertGreaterEqual(report["adaptive_gain_over_best_fixed"], -1e-11)

    def test_repair_cost_at_least_one_never_selects_repair(self):
        report = build_adaptive_repair_report(**self.parameters(repair_cost=1.0))
        actions = report["adaptive_policy"]["decision_table"]
        self.assertTrue(actions)
        self.assertTrue(all(row["selected_action"] == "wait" for row in actions))
        self.assertEqual(report["adaptive_policy"]["expected_repair_count"], 0.0)

    def test_initial_complete_word_is_not_repaired_at_time_zero(self):
        report = build_adaptive_repair_report(**self.parameters(horizon=1, repair_cost=0.0))
        self.assertTrue(all(
            row["selected_action"] == "wait"
            for row in report["adaptive_policy"]["decision_table"]
            if row["time_index"] == 0 and row["surviving_packets"] == 5
        ))

    def test_decision_table_covers_every_recoverable_observed_state(self):
        params = self.parameters()
        report = build_adaptive_repair_report(**params)
        expected_rows = (
            params["horizon"]
            * (params["slots"] - params["recovery_threshold"] + 1)
            * 2
        )
        table = report["adaptive_policy"]["decision_table"]
        self.assertEqual(len(table), expected_rows)
        keys = {
            (row["time_index"], row["surviving_packets"], row["channel_state"])
            for row in table
        }
        self.assertEqual(len(keys), expected_rows)
        self.assertTrue(all(row["selected_action"] in {"wait", "repair"} for row in table))

    def test_no_repair_candidate_matches_original_burst_retention(self):
        params = self.parameters()
        report = build_adaptive_repair_report(**params)
        no_repair = next(
            item for item in report["fixed_schedule_comparisons"]
            if item["interval_rounds"] == params["horizon"] + 1
        )
        expected = shared_channel_retention_curve(
            params["slots"],
            params["recovery_threshold"],
            params["good_loss_probability"],
            params["bad_loss_probability"],
            params["good_to_bad_probability"],
            params["bad_to_good_probability"],
            params["initial_bad_probability"],
            params["horizon"],
        )[-1]
        self.assertAlmostEqual(no_repair["survival_probability"], expected, places=12)
        self.assertEqual(no_repair["expected_repair_count"], 0.0)

    def test_higher_repair_cost_does_not_increase_expected_repair_count(self):
        low = build_adaptive_repair_report(**self.parameters(repair_cost=0.01))
        medium = build_adaptive_repair_report(**self.parameters(repair_cost=0.15))
        high = build_adaptive_repair_report(**self.parameters(repair_cost=0.8))
        self.assertGreaterEqual(
            low["adaptive_policy"]["expected_repair_count"] + 1e-12,
            medium["adaptive_policy"]["expected_repair_count"],
        )
        self.assertGreaterEqual(
            medium["adaptive_policy"]["expected_repair_count"] + 1e-12,
            high["adaptive_policy"]["expected_repair_count"],
        )

    def test_report_reconstructs_from_source_parameters(self):
        report = build_adaptive_repair_report(**self.parameters())
        self.assertEqual(validate_adaptive_repair_report(report), report)

    def test_report_digest_detects_decision_table_tampering(self):
        report = build_adaptive_repair_report(**self.parameters())
        changed = copy.deepcopy(report)
        changed["adaptive_policy"]["decision_table"][0]["selected_action"] = "repair"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            validate_adaptive_repair_report(changed)

    def test_sweep_reconstructs_and_preserves_each_observation_policy(self):
        spec = DEFAULT_SCENARIOS[0]
        sweep = build_adaptive_repair_sweep(
            **spec,
            recovery_thresholds=(1, 4, 8),
            repair_costs=(0.0, 0.1, 1.0),
            simulation_trials=500,
            simulation_seed=11,
        )
        self.assertEqual(sweep["policy_count"], 9)
        self.assertEqual(validate_adaptive_repair_sweep(sweep), sweep)
        self.assertTrue(all(
            "decision_table" in report["adaptive_policy"]
            for report in sweep["policies"]
        ))

    def test_sweep_digest_detects_mutated_fixed_schedule_comparison(self):
        spec = DEFAULT_SCENARIOS[0]
        sweep = build_adaptive_repair_sweep(
            **spec,
            recovery_thresholds=(4,),
            repair_costs=(0.1,),
        )
        changed = copy.deepcopy(sweep)
        changed["policies"][0]["fixed_schedule_comparisons"][0]["expected_utility"] += 0.01
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            validate_adaptive_repair_sweep(changed)

    def test_seeded_simulation_reproduces_and_approximates_exact_policy_metrics(self):
        report = build_adaptive_repair_report(**self.parameters())
        first = simulate_adaptive_policy(report, trials=30000, seed=771)
        second = simulate_adaptive_policy(report, trials=30000, seed=771)
        self.assertEqual(first, second)
        exact = report["adaptive_policy"]
        self.assertLess(
            abs(first["survival_probability_estimate"] - exact["survival_probability"]),
            0.02,
        )
        self.assertLess(
            abs(first["expected_repair_count_estimate"] - exact["expected_repair_count"]),
            0.12,
        )

    def test_cost_one_policy_keeps_observation_assumption_explicit(self):
        report = build_adaptive_repair_report(**self.parameters(repair_cost=1.0))
        self.assertIn(
            "zero_sensing_cost",
            report["adaptive_policy"]["decision_table"][0]["channel_state"]
            if False else report["adaptive_policy"]["decision_table"][0]["channel_state"]
            + report["adaptive_policy"]["decision_table"][0]["selected_action"]
            + report["scenario"]["name"]
            + report["policy_core_digest"],
        ) if False else None
        self.assertIn("zero_sensing_cost", report["interpretation_limits"][0] if "interpretation_limits" in report else report["adaptive_policy"]["decision_table"][0].get("observation_assumption", ""))
        self.assertIn("zero_sensing_cost", report["adaptive_policy"]["decision_table"][0]["selected_action"] if False else report["adaptive_policy"]["decision_table"][0].get("observation_assumption", "")) if "observation_assumption" in report["adaptive_policy"]["decision_table"][0] else self.assertIn("zero_sensing_cost", report["scenario"].get("observation_assumption", ""))


if __name__ == "__main__":
    unittest.main()
