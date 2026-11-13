import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from burst_loss import (
    DEFAULT_SCENARIOS,
    binomial_tail_probability,
    half_life_summary,
    iid_baseline_retention_curve,
    main,
    per_packet_retention_curve,
    shared_channel_retention_curve,
    simulate_retention,
    summarize_scenario,
)


def retention_probability(slots, required, loss_probability, rounds):
    survival = (1.0 - loss_probability) ** rounds
    return binomial_tail_probability(slots, required, survival)


def _enumerate_environment_paths(rounds, alpha, beta, initial_bad):
    """Yield (path probability, current-state sequence) for short horizons."""
    paths = []
    for first_bad, first_probability in ((False, 1 - initial_bad), (True, initial_bad)):
        if first_probability == 0:
            continue
        frontier = [(first_probability, (first_bad,))]
        for _ in range(rounds - 1):
            next_frontier = []
            for weight, states in frontier:
                current_bad = states[-1]
                transitions = (
                    ((False, beta), (True, 1 - beta))
                    if current_bad else
                    ((False, 1 - alpha), (True, alpha))
                )
                for next_bad, transition_probability in transitions:
                    if transition_probability:
                        next_frontier.append((weight * transition_probability, states + (next_bad,)))
            frontier = next_frontier
        paths.extend(frontier)
    return paths


def _enumerated_shared_retention(slots, required, p_good, p_bad, alpha, beta, initial_bad, rounds):
    if rounds == 0:
        return 1.0
    total = 0.0
    for path_probability, states in _enumerate_environment_paths(rounds, alpha, beta, initial_bad):
        packet_survival = 1.0
        for state_bad in states:
            packet_survival *= 1 - (p_bad if state_bad else p_good)
        total += path_probability * binomial_tail_probability(slots, required, packet_survival)
    return total


def _enumerated_single_packet_survival(p_good, p_bad, alpha, beta, initial_bad, rounds):
    if rounds == 0:
        return 1.0
    total = 0.0
    for path_probability, states in _enumerate_environment_paths(rounds, alpha, beta, initial_bad):
        packet_survival = 1.0
        for state_bad in states:
            packet_survival *= 1 - (p_bad if state_bad else p_good)
        total += path_probability * packet_survival
    return total


class BurstLossTests(unittest.TestCase):
    def common(self, *, slots=12, required=8, good=0.01, bad=0.4,
               alpha=0.08, beta=0.25, initial_bad=0.08 / 0.33, rounds=30):
        return {
            "slots": slots,
            "required": required,
            "good_loss_probability": good,
            "bad_loss_probability": bad,
            "good_to_bad_probability": alpha,
            "bad_to_good_probability": beta,
            "initial_bad_probability": initial_bad,
            "max_rounds": rounds,
        }

    def test_equal_state_loss_reduces_both_models_to_iid_formula(self):
        args = self.common(good=0.07, bad=0.07, alpha=0.13, beta=0.42, rounds=25)
        per_packet = per_packet_retention_curve(**args)
        shared = shared_channel_retention_curve(**args)
        for rounds in (0, 1, 2, 5, 10, 25):
            expected = retention_probability(args["slots"], args["required"], 0.07, rounds)
            self.assertAlmostEqual(per_packet[rounds], expected, places=12)
            self.assertAlmostEqual(shared[rounds], expected, places=12)

    def test_dynamic_program_matches_explicit_shared_environment_path_enumeration(self):
        args = self.common(slots=5, required=3, rounds=5)
        curve = shared_channel_retention_curve(**args)
        for rounds in range(6):
            expected = _enumerated_shared_retention(
                args["slots"], args["required"], args["good_loss_probability"],
                args["bad_loss_probability"], args["good_to_bad_probability"],
                args["bad_to_good_probability"], args["initial_bad_probability"], rounds,
            )
            self.assertAlmostEqual(curve[rounds], expected, places=12)

    def test_per_packet_chain_matches_explicit_single_packet_path_enumeration(self):
        args = self.common(slots=7, required=4, rounds=5)
        curve = per_packet_retention_curve(**args)
        for rounds in range(6):
            single_packet_survival = _enumerated_single_packet_survival(
                args["good_loss_probability"], args["bad_loss_probability"],
                args["good_to_bad_probability"], args["bad_to_good_probability"],
                args["initial_bad_probability"], rounds,
            )
            expected = binomial_tail_probability(args["slots"], args["required"], single_packet_survival)
            self.assertAlmostEqual(curve[rounds], expected, places=12)

    def test_no_loss_never_crosses_half_under_either_model(self):
        args = self.common(slots=16, required=8, good=0.0, bad=0.0, rounds=40)
        report = summarize_scenario(name="no-loss", **args)
        for model in ("per_packet", "shared_channel"):
            self.assertEqual(report["models"][model]["status"], "no_finite_half_life")
            self.assertEqual(report["models"][model]["retention_at_rounds"]["20"], 1.0)

    def test_one_packet_makes_shared_and_independent_state_models_identical(self):
        args = self.common(slots=1, required=1, rounds=50)
        per_packet = per_packet_retention_curve(**args)
        shared = shared_channel_retention_curve(**args)
        for actual, expected in zip(per_packet, shared):
            self.assertAlmostEqual(actual, expected, places=12)

    def test_shared_environment_creates_common_mode_survival(self):
        # A shared good state preserves both packets; a shared bad state loses both.
        # Independent per-packet states split those same starting conditions.
        args = self.common(
            slots=2, required=2, good=0.0, bad=1.0,
            alpha=0.0, beta=1.0, initial_bad=0.5, rounds=2,
        )
        per_packet = per_packet_retention_curve(**args)
        shared = shared_channel_retention_curve(**args)
        self.assertAlmostEqual(per_packet[1], 0.25, places=12)
        self.assertAlmostEqual(shared[1], 0.5, places=12)

    def test_shared_environment_can_reverse_k_of_n_tail_comparison(self):
        args = self.common(
            slots=2, required=1, good=0.0, bad=1.0,
            alpha=0.0, beta=1.0, initial_bad=0.5, rounds=1,
        )
        per_packet = per_packet_retention_curve(**args)
        shared = shared_channel_retention_curve(**args)
        self.assertAlmostEqual(per_packet[1], 0.75, places=12)
        self.assertAlmostEqual(shared[1], 0.5, places=12)

    def test_per_packet_and_shared_curves_are_nonincreasing(self):
        args = self.common(rounds=80)
        for curve in (
            per_packet_retention_curve(**args),
            shared_channel_retention_curve(**args),
            iid_baseline_retention_curve(args["slots"], args["required"], 0.1, args["max_rounds"]),
        ):
            self.assertEqual(curve[0], 1.0)
            for earlier, later in zip(curve, curve[1:]):
                self.assertLessEqual(later, earlier + 1e-14)

    def test_stationary_initialization_matches_same_marginal_first_round_loss(self):
        alpha, beta = 0.04, 0.16
        initial_bad = alpha / (alpha + beta)
        args = self.common(
            slots=20, required=10, good=0.002, bad=0.6,
            alpha=alpha, beta=beta, initial_bad=initial_bad, rounds=1,
        )
        expected = retention_probability(
            args["slots"], args["required"],
            (1 - initial_bad) * 0.002 + initial_bad * 0.6, 1,
        )
        per_packet = per_packet_retention_curve(**args)
        shared = shared_channel_retention_curve(**args)
        self.assertAlmostEqual(per_packet[1], expected, places=12)
        conditional_good = binomial_tail_probability(args["slots"], args["required"], 1 - 0.002)
        conditional_bad = binomial_tail_probability(args["slots"], args["required"], 1 - 0.6)
        shared_expected = (1 - initial_bad) * conditional_good + initial_bad * conditional_bad
        self.assertAlmostEqual(shared[1], shared_expected, places=12)
        self.assertNotAlmostEqual(shared[1], expected, places=6)

    def test_half_life_is_first_integer_round_at_or_below_half(self):
        curve = [1.0, 0.8, 0.6, 0.5, 0.2]
        result = half_life_summary(curve)
        self.assertEqual(result, {"status": "crossed", "first_crossing_round": 3})

    def test_right_censor_is_not_reported_as_infinite_half_life(self):
        result = half_life_summary([1.0, 0.9, 0.8, 0.7])
        self.assertEqual(result["status"], "not_reached_within_horizon")
        self.assertEqual(result["censored_at_round"], 3)
        self.assertIsNone(result["first_crossing_round"])

    def test_loss_free_absorbing_good_state_is_reported_separately(self):
        args = self.common(
            slots=4, required=3, good=0.0, bad=0.2,
            alpha=0.0, beta=0.2, initial_bad=0.3, rounds=20,
        )
        report = summarize_scenario(name="absorbing-good", **args)
        self.assertEqual(report["models"]["shared_channel"]["status"], "no_finite_half_life")
        self.assertEqual(report["models"]["per_packet"]["status"], "no_finite_half_life")

    def test_transient_bad_state_can_recover_without_crossing_half(self):
        # One packet survives a bad-state visit with probability 0.9 and
        # transitions to a loss-free absorbing good state with probability 0.9.
        # Starting-good mass is only 0.2, but eventual survival is > 0.5.
        args = self.common(
            slots=1, required=1, good=0.0, bad=0.1,
            alpha=0.0, beta=0.9, initial_bad=0.8, rounds=100,
        )
        report = summarize_scenario(name="transient-bad", **args)
        for model in ("per_packet", "shared_channel"):
            self.assertEqual(report["models"][model]["status"], "no_finite_half_life")
        limiting_survival = 0.2 + 0.8 * (0.9 * 0.9 / (1.0 - 0.1 * 0.1))
        self.assertAlmostEqual(
            report["models"]["per_packet"]["retention_at_rounds"]["100"],
            limiting_survival,
            places=12,
        )
        self.assertAlmostEqual(
            report["models"]["shared_channel"]["retention_at_rounds"]["100"],
            limiting_survival,
            places=12,
        )

    def test_shared_channel_limit_accounts_for_block_survival_until_recovery(self):
        args = self.common(
            slots=2, required=2, good=0.0, bad=0.1,
            alpha=0.0, beta=0.9, initial_bad=0.8, rounds=100,
        )
        report = summarize_scenario(name="shared-recovery-limit", **args)
        self.assertEqual(
            report["models"]["shared_channel"]["status"],
            "no_finite_half_life",
        )
        # In B, both packets survive one round with probability 0.9^2.
        # The channel then exits B with probability 0.9, or repeats B with
        # probability 0.1. Solve f = 0.9*0.9^2 + 0.1*0.9^2*f.
        bad_to_good_with_both = (0.9 * 0.9**2) / (1.0 - 0.1 * 0.9**2)
        limiting_retention = 0.2 + 0.8 * bad_to_good_with_both
        self.assertAlmostEqual(
            report["models"]["shared_channel"]["retention_at_rounds"]["100"],
            limiting_retention,
            places=12,
        )

    def test_absorbing_good_limit_below_half_still_crosses(self):
        args = self.common(
            slots=1, required=1, good=0.0, bad=0.5,
            alpha=0.0, beta=0.5, initial_bad=0.9, rounds=100,
        )
        report = summarize_scenario(name="finite-recovery", **args)
        limiting_survival = 0.1 + 0.9 * (0.5 * 0.5 / (1.0 - 0.5 * 0.5))
        self.assertLess(limiting_survival, 0.5)
        for model in ("per_packet", "shared_channel"):
            self.assertEqual(report["models"][model]["status"], "crossed")
            self.assertIsNotNone(report["models"][model]["first_crossing_round"])

    def test_simulation_is_seeded_and_tracks_exact_shared_model(self):
        args = self.common(slots=8, required=5, rounds=5)
        exact = shared_channel_retention_curve(**args)[5]
        sim_args = {key: value for key, value in args.items() if key != "max_rounds"}
        first = simulate_retention("shared_channel", **sim_args, rounds=5, trials=30000, seed=778)
        second = simulate_retention("shared_channel", **sim_args, rounds=5, trials=30000, seed=778)
        self.assertEqual(first, second)
        self.assertLess(abs(first - exact), 0.015)

    def test_simulation_tracks_exact_per_packet_model(self):
        args = self.common(slots=8, required=5, rounds=4)
        exact = per_packet_retention_curve(**args)[4]
        sim_args = {key: value for key, value in args.items() if key != "max_rounds"}
        actual = simulate_retention("per_packet", **sim_args, rounds=4, trials=30000, seed=99)
        self.assertLess(abs(actual - exact), 0.015)

    def test_binomial_tail_boundaries(self):
        self.assertEqual(binomial_tail_probability(8, 3, 0.0), 0.0)
        self.assertEqual(binomial_tail_probability(8, 3, 1.0), 1.0)
        self.assertAlmostEqual(binomial_tail_probability(1, 1, 0.37), 0.37, places=12)

    def test_invalid_good_bad_order_and_probabilities_are_rejected(self):
        args = self.common(good=0.4, bad=0.2)
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            per_packet_retention_curve(**args)
        args = self.common(alpha=float("nan"))
        with self.assertRaisesRegex(ValueError, "finite probability"):
            shared_channel_retention_curve(**args)
        args = self.common(rounds=0)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            per_packet_retention_curve(**args)

    def test_summary_keeps_iid_and_burst_models_distinct(self):
        report = summarize_scenario(name="test", **self.common(rounds=20))
        self.assertEqual(set(report["models"]), {"iid_average", "per_packet", "shared_channel"})
        self.assertEqual(report["parameters"]["stationary_bad_probability"], 0.08 / 0.33)
        self.assertIn("marginal first-round loss", " ".join(report["interpretation"]))

    def test_scan_cli_emits_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--scan", "--max-rounds", "80", "--json"])
        self.assertEqual(exit_code, 0)
        rows = json.loads(output.getvalue())
        self.assertEqual(len(rows), len(DEFAULT_SCENARIOS))
        self.assertIn("shared_channel", rows[0]["models"])

    def test_cli_writes_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "burst-scan.json"
            with redirect_stdout(io.StringIO()):
                exit_code = main(["--scan", "--max-rounds", "10", "--json", "--output", str(path)])
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))), len(DEFAULT_SCENARIOS))


if __name__ == "__main__":
    unittest.main()
