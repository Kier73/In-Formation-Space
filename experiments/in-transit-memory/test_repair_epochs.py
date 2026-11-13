import copy
import itertools
import math
import unittest

from burst_loss import (
    binomial_tail_probability,
    per_packet_retention_curve,
    shared_channel_retention_curve,
)
from repair_epochs import (
    _expected_attempted_epochs,
    _slot_epoch_outcomes,
    _survival_curve,
    build_per_packet_epoch_transition,
    build_repair_sweep,
    build_shared_channel_epoch_transition,
    initial_per_packet_state_distribution,
    simulate_repair_survival,
    validate_repair_sweep,
)


def enumerate_single_slot_outcomes(initial_state, rounds, p_good, p_bad, alpha, beta):
    """Independent path enumeration for (survived, endpoint channel state)."""
    frontier = [(initial_state, True, 1.0)]
    losses = (p_good, p_bad)
    transition = ((1 - alpha, alpha), (beta, 1 - beta))
    for _ in range(rounds):
        following = []
        for state, alive, mass in frontier:
            outcomes = [(alive, 1.0)]
            if alive:
                outcomes = [(True, 1 - losses[state]), (False, losses[state])]
            for next_alive, loss_mass in outcomes:
                for next_state in (0, 1):
                    weight = mass * loss_mass * transition[state][next_state]
                    if weight:
                        following.append((next_state, next_alive, weight))
        frontier = following
    result = [0.0, 0.0, 0.0, 0.0]
    for state, alive, mass in frontier:
        if alive and state == 0:
            result[0] += mass
        elif alive and state == 1:
            result[1] += mass
        elif not alive and state == 0:
            result[2] += mass
        else:
            result[3] += mass
    return tuple(result)


def enumerate_per_packet_epoch_row(initial_states, required, rounds, p_good, p_bad, alpha, beta):
    slot_outcomes = [
        enumerate_single_slot_outcomes(state, rounds, p_good, p_bad, alpha, beta)
        for state in initial_states
    ]
    result = [0.0] * (len(initial_states) + 1)
    for choices in itertools.product(range(4), repeat=len(initial_states)):
        probability = 1.0
        survivors = 0
        endpoint_bad = 0
        for outcome_index, slot_index in zip(choices, range(len(initial_states))):
            probability *= slot_outcomes[slot_index][outcome_index]
            survivors += outcome_index in (0, 1)
            endpoint_bad += outcome_index in (1, 3)
        if survivors >= required:
            result[endpoint_bad] += probability
    return result


def enumerate_shared_epoch_row(initial_state, slots, required, rounds, p_good, p_bad, alpha, beta):
    """Enumerate the 2^rounds shared channel-state paths directly."""
    transition = ((1 - alpha, alpha), (beta, 1 - beta))
    losses = (p_good, p_bad)
    total = [0.0, 0.0]
    for following_states in itertools.product((0, 1), repeat=rounds):
        states = (initial_state,) + following_states
        path_probability = 1.0
        packet_survival = 1.0
        for round_index in range(rounds):
            state = states[round_index]
            path_probability *= transition[state][states[round_index + 1]]
            packet_survival *= 1 - losses[state]
        successful_packets = binomial_tail_probability(slots, required, packet_survival)
        total[following_states[-1]] += path_probability * successful_packets
    return total


class RepairEpochTests(unittest.TestCase):
    def parameters(self):
        return {
            "slots": 4,
            "good_loss_probability": 0.02,
            "bad_loss_probability": 0.45,
            "good_to_bad_probability": 0.12,
            "bad_to_good_probability": 0.30,
            "initial_bad_probability": 0.12 / 0.42,
        }

    def test_per_packet_epoch_transition_matches_explicit_slot_path_enumeration(self):
        params = self.parameters()
        required = 2
        interval = 3
        matrix = build_per_packet_epoch_transition(
            slots=params["slots"],
            required=required,
            interval_rounds=interval,
            good_loss_probability=params["good_loss_probability"],
            bad_loss_probability=params["bad_loss_probability"],
            good_to_bad_probability=params["good_to_bad_probability"],
            bad_to_good_probability=params["bad_to_good_probability"],
        )
        for initial_bad_count in range(params["slots"] + 1):
            initial_states = [0] * (params["slots"] - initial_bad_count) + [1] * initial_bad_count
            expected = enumerate_per_packet_epoch_row(
                initial_states, required, interval,
                params["good_loss_probability"], params["bad_loss_probability"],
                params["good_to_bad_probability"], params["bad_to_good_probability"],
            )
            for actual, target in zip(matrix[initial_bad_count], expected):
                self.assertAlmostEqual(actual, target, places=12)

    def test_shared_channel_epoch_transition_matches_explicit_channel_path_enumeration(self):
        params = self.parameters()
        required = 2
        interval = 4
        matrix = build_shared_channel_epoch_transition(
            slots=params["slots"],
            required=required,
            interval_rounds=interval,
            good_loss_probability=params["good_loss_probability"],
            bad_loss_probability=params["bad_loss_probability"],
            good_to_bad_probability=params["good_to_bad_probability"],
            bad_to_good_probability=params["bad_to_good_probability"],
        )
        for initial_state in (0, 1):
            expected = enumerate_shared_epoch_row(
                initial_state, params["slots"], required, interval,
                params["good_loss_probability"], params["bad_loss_probability"],
                params["good_to_bad_probability"], params["bad_to_good_probability"],
            )
            for actual, target in zip(matrix[initial_state], expected):
                self.assertAlmostEqual(actual, target, places=12)

    def test_iid_special_case_has_geometric_repair_survival_and_expected_lifetime(self):
        slots, required, interval, loss = 8, 5, 3, 0.07
        success = binomial_tail_probability(slots, required, (1 - loss) ** interval)
        params = self.parameters()
        matrix = build_per_packet_epoch_transition(
            slots=slots, required=required, interval_rounds=interval,
            good_loss_probability=loss, bad_loss_probability=loss,
            good_to_bad_probability=params["good_to_bad_probability"],
            bad_to_good_probability=params["bad_to_good_probability"],
        )
        initial = initial_per_packet_state_distribution(slots, 0.3)
        curve = _survival_curve(initial, matrix, 8)
        for epochs, probability in enumerate(curve):
            self.assertAlmostEqual(probability, success ** epochs, places=11)
        attempts = _expected_attempted_epochs(initial, matrix)
        self.assertIsNotNone(attempts)
        self.assertAlmostEqual(attempts, 1 / (1 - success), places=9)

    def test_no_repair_baseline_is_not_more_reliable_than_repaired_process(self):
        params = self.parameters()
        slots, required, interval = 6, 3, 2
        matrix = build_shared_channel_epoch_transition(
            slots=slots, required=required, interval_rounds=interval,
            good_loss_probability=params["good_loss_probability"],
            bad_loss_probability=params["bad_loss_probability"],
            good_to_bad_probability=params["good_to_bad_probability"],
            bad_to_good_probability=params["bad_to_good_probability"],
        )
        initial = [1 - params["initial_bad_probability"], params["initial_bad_probability"]]
        repaired = _survival_curve(initial, matrix, 3)[3]
        no_repair = shared_channel_retention_curve(
            slots, required, params["good_loss_probability"], params["bad_loss_probability"],
            params["good_to_bad_probability"], params["bad_to_good_probability"],
            params["initial_bad_probability"], interval * 3,
        )[-1]
        self.assertGreaterEqual(repaired + 1e-12, no_repair)

    def test_repair_preserves_channel_state_instead_of_resetting_to_initial_distribution(self):
        params = self.parameters()
        transition = build_shared_channel_epoch_transition(
            slots=6, required=4, interval_rounds=3,
            good_loss_probability=params["good_loss_probability"],
            bad_loss_probability=params["bad_loss_probability"],
            good_to_bad_probability=params["good_to_bad_probability"],
            bad_to_good_probability=params["bad_to_good_probability"],
        )
        initial = [1 - params["initial_bad_probability"], params["initial_bad_probability"]]
        persistent = _survival_curve(initial, transition, 5)
        # A reset-to-initial-state approximation would multiply the first
        # epoch success probability independently at every epoch.
        first_success = sum(
            initial[row] * sum(transition[row]) for row in (0, 1)
        )
        reset_approximation = [first_success ** epoch for epoch in range(6)]
        self.assertTrue(any(
            abs(persistent[epoch] - reset_approximation[epoch]) > 1e-5
            for epoch in range(2, 6)
        ))

    def test_expected_attempts_and_repair_rate_have_correct_geometric_meaning(self):
        success = 0.8
        interval = 4
        attempts = _expected_attempted_epochs([1.0], [[success]])
        self.assertAlmostEqual(attempts, 1 / (1 - success), places=12)
        expected_repairs = attempts - 1
        lifetime = interval * attempts
        repairs_per_100 = 100 * expected_repairs / lifetime
        self.assertAlmostEqual(repairs_per_100, 100 * success / interval, places=12)

    def test_threshold_and_interval_sweep_is_reconstructible(self):
        params = self.parameters()
        report = build_repair_sweep(
            scenario_name="unit-test",
            **params,
            interval_rounds=(1, 2, 4),
            recovery_thresholds=(4, 2, 1),
            max_epochs=12,
        )
        self.assertEqual(report["policy_count"], 9)
        self.assertEqual(validate_repair_sweep(report), report)
        for model in ("iid_marginal", "per_packet_markov", "shared_channel"):
            frontier = report["pareto_frontier"][model]
            self.assertGreaterEqual(len(frontier), 1)
            self.assertTrue(all(item["expected_lifetime_rounds"] > 0 for item in frontier))

    def test_repaired_policy_reports_same_horizon_no_repair_comparison(self):
        params = self.parameters()
        report = build_repair_sweep(
            scenario_name="same-horizon",
            **params,
            interval_rounds=(2,),
            recovery_thresholds=(2,),
            max_epochs=8,
        )
        entry = report["policies"][0]["models"]["shared_channel"]
        self.assertEqual(
            entry["no_repair_survival_at_comparison_horizon"]["rounds"],
            entry["interval_rounds"] * (
                entry["median_failure_epoch"] or entry["max_epochs_checked"]
            ),
        )
        self.assertIsNotNone(entry["no_repair_survival_at_comparison_horizon"]["probability"])

    def test_simulation_is_seeded_and_tracks_shared_channel_exact_transition(self):
        params = self.parameters()
        kwargs = dict(
            model="shared_channel", slots=6, required=3, interval_rounds=2,
            good_loss_probability=params["good_loss_probability"],
            bad_loss_probability=params["bad_loss_probability"],
            good_to_bad_probability=params["good_to_bad_probability"],
            bad_to_good_probability=params["bad_to_good_probability"],
            initial_bad_probability=params["initial_bad_probability"],
            max_epochs=5, trials=30000, seed=505,
        )
        first = simulate_repair_survival(**kwargs)
        second = simulate_repair_survival(**kwargs)
        self.assertEqual(first, second)
        matrix = build_shared_channel_epoch_transition(
            slots=kwargs["slots"], required=kwargs["required"],
            interval_rounds=kwargs["interval_rounds"],
            good_loss_probability=kwargs["good_loss_probability"],
            bad_loss_probability=kwargs["bad_loss_probability"],
            good_to_bad_probability=kwargs["good_to_bad_probability"],
            bad_to_good_probability=kwargs["bad_to_good_probability"],
        )
        initial = [1 - params["initial_bad_probability"], params["initial_bad_probability"]]
        exact = _survival_curve(initial, matrix, kwargs["max_epochs"])
        for epoch, estimate in first["survival_probability_after_epochs"].items():
            self.assertLess(abs(estimate - exact[int(epoch)]), 0.015)

    def test_simulation_is_seeded_and_tracks_per_packet_exact_transition(self):
        params = self.parameters()
        kwargs = dict(
            model="per_packet_markov", slots=6, required=3, interval_rounds=2,
            good_loss_probability=params["good_loss_probability"],
            bad_loss_probability=params["bad_loss_probability"],
            good_to_bad_probability=params["good_to_bad_probability"],
            bad_to_good_probability=params["bad_to_good_probability"],
            initial_bad_probability=params["initial_bad_probability"],
            max_epochs=5, trials=30000, seed=818,
        )
        first = simulate_repair_survival(**kwargs)
        matrix = build_per_packet_epoch_transition(
            slots=kwargs["slots"], required=kwargs["required"],
            interval_rounds=kwargs["interval_rounds"],
            good_loss_probability=kwargs["good_loss_probability"],
            bad_loss_probability=kwargs["bad_loss_probability"],
            good_to_bad_probability=kwargs["good_to_bad_probability"],
            bad_to_good_probability=kwargs["bad_to_good_probability"],
        )
        initial = initial_per_packet_state_distribution(kwargs["slots"], kwargs["initial_bad_probability"])
        exact = _survival_curve(initial, matrix, kwargs["max_epochs"])
        for epoch, estimate in first["survival_probability_after_epochs"].items():
            self.assertLess(abs(estimate - exact[int(epoch)]), 0.015)

    def test_unmodeled_bad_probability_and_invalid_policy_are_rejected(self):
        params = self.parameters()
        with self.assertRaisesRegex(ValueError, "must be in"):
            build_shared_channel_epoch_transition(
                slots=4, required=2, interval_rounds=2,
                good_loss_probability=0.01, bad_loss_probability=1.1,
                good_to_bad_probability=0.1, bad_to_good_probability=0.2,
            )
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            build_per_packet_epoch_transition(
                slots=4, required=2, interval_rounds=2,
                good_loss_probability=0.5, bad_loss_probability=0.2,
                good_to_bad_probability=0.1, bad_to_good_probability=0.2,
            )
        with self.assertRaisesRegex(ValueError, "must be a positive integer"):
            build_repair_sweep(
                scenario_name="bad",
                **params,
                interval_rounds=(0,),
                recovery_thresholds=(2,),
                max_epochs=10,
            )

    def test_report_digest_detects_policy_tampering(self):
        params = self.parameters()
        report = build_repair_sweep(
            scenario_name="tamper",
            **params,
            interval_rounds=(1, 2),
            recovery_thresholds=(4, 2),
            max_epochs=5,
        )
        changed = copy.deepcopy(report)
        changed["policies"][0]["models"]["shared_channel"]["expected_lifetime_rounds"] += 1
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            validate_repair_sweep(changed)

    def test_repair_sweep_rejects_a_self-consistent_but_nonreconstructed_matrix(self):
        params = self.parameters()
        report = build_repair_sweep(
            scenario_name="tamper",
            **params,
            interval_rounds=(1,),
            recovery_thresholds=(2,),
            max_epochs=5,
        )
        changed = copy.deepcopy(report)
        changed["policies"][0]["models"]["shared_channel"]["successful_epoch_transition_matrix"][0][0] += 0.001
        core = dict(changed)
        core.pop("report_digest")
        import hashlib
        import json
        changed["report_digest"] = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "differs from reconstruction"):
            validate_repair_sweep(changed)

    def test_transition_rows_are_substochastic_and_success_probability_is_bounded(self):
        params = self.parameters()
        for matrix in (
            build_per_packet_epoch_transition(
                slots=6, required=3, interval_rounds=4,
                good_loss_probability=params["good_loss_probability"],
                bad_loss_probability=params["bad_loss_probability"],
                good_to_bad_probability=params["good_to_bad_probability"],
                bad_to_good_probability=params["bad_to_good_probability"],
            ),
            build_shared_channel_epoch_transition(
                slots=6, required=3, interval_rounds=4,
                good_loss_probability=params["good_loss_probability"],
                bad_loss_probability=params["bad_loss_probability"],
                good_to_bad_probability=params["good_to_bad_probability"],
                bad_to_good_probability=params["bad_to_good_probability"],
            ),
        ):
            for row in matrix:
                self.assertGreaterEqual(sum(row), 0.0)
                self.assertLessEqual(sum(row), 1.0 + 1e-12)

    def test_slot_epoch_outcomes_match_explicit_markov_loss_enumeration(self):
        expected = enumerate_single_slot_outcomes(
            1, 3, p_good=0.02, p_bad=0.45, alpha=0.12, beta=0.30
        )
        actual = _slot_epoch_outcomes(
            1, interval_rounds=3, good_loss_probability=0.02,
            bad_loss_probability=0.45, good_to_bad_probability=0.12,
            bad_to_good_probability=0.30,
        )
        for left, right in zip(actual, expected):
            self.assertAlmostEqual(left, right, places=12)


if __name__ == "__main__":
    unittest.main()
