#!/usr/bin/env python3
"""Exact periodic repair under persistent Markov burst loss.

At the start of every repair epoch all n data packets are present. The channel
state does NOT reset when data is repaired. Each epoch lasts L circulations.
At its end, if at least k packets remain, an instantaneous repair reconstructs
all n packets; otherwise the word is permanently lost.

The two channel structures match BTL-001:
- per_packet_markov: independent persistent good/bad state per slot;
- shared_channel: one persistent good/bad state shared by every slot.

The epoch transition retains the channel state across successful repairs. Its
sub-stochastic matrix therefore supports exact multi-epoch survival, expected
lifetime, expected successful repair count, and a descriptive Pareto frontier
over repair interval and recovery threshold. Repair is instantaneous and has
unit event count only; no repair duration or physical channel is measured.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from burst_loss import (
    binomial_tail_probability,
    per_packet_retention_curve,
    shared_channel_retention_curve,
)

MODELS = ("iid_marginal", "per_packet_markov", "shared_channel")
MAX_SLOTS = 64
MAX_TOTAL_ROUNDS = 20000


class RepairEpochError(ValueError):
    """Invalid repair policy, channel model, or reconstruction input."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _probability(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RepairEpochError(f"{label} must be a finite probability")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise RepairEpochError(f"{label} must be a finite probability") from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise RepairEpochError(f"{label} must be in [0, 1]")
    return number


def _positive_int(value: object, label: str, maximum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RepairEpochError(f"{label} must be a positive integer")
    if maximum is not None and value > maximum:
        raise RepairEpochError(f"{label} must be <= {maximum}")
    return value


def _validate_parameters(
    *,
    slots: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
) -> Tuple[float, float, float, float, float]:
    _positive_int(slots, "slots", MAX_SLOTS)
    p_good = _probability(good_loss_probability, "good_loss_probability")
    p_bad = _probability(bad_loss_probability, "bad_loss_probability")
    alpha = _probability(good_to_bad_probability, "good_to_bad_probability")
    beta = _probability(bad_to_good_probability, "bad_to_good_probability")
    initial_bad = _probability(initial_bad_probability, "initial_bad_probability")
    if p_good > p_bad:
        raise RepairEpochError("good_loss_probability must not exceed bad_loss_probability")
    return p_good, p_bad, alpha, beta, initial_bad


def _binomial_pmf(trials: int, probability: float) -> List[float]:
    if probability <= 0.0:
        return [1.0] + [0.0] * trials
    if probability >= 1.0:
        return [0.0] * trials + [1.0]
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    values = []
    for count in range(trials + 1):
        log_value = (
            math.lgamma(trials + 1)
            - math.lgamma(count + 1)
            - math.lgamma(trials - count + 1)
            + count * log_p
            + (trials - count) * log_q
        )
        values.append(math.exp(log_value))
    total = math.fsum(values)
    if total <= 0.0:
        raise ArithmeticError("binomial PMF underflowed completely")
    return [value / total for value in values]


def _channel_transition(alpha: float, beta: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    # State 0 = good, state 1 = bad. Transition occurs after each circulation.
    return ((1.0 - alpha, alpha), (beta, 1.0 - beta))


def _slot_epoch_outcomes(
    initial_state: int,
    *,
    interval_rounds: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
) -> Tuple[float, float, float, float]:
    """Joint probabilities: survive/end-G, survive/end-B, fail/end-G, fail/end-B.

    The channel state continues evolving after a data packet is lost. This is
    essential: a later successful repair writes new data into the same channel
    slot, inheriting its current good/bad state.
    """
    transition = _channel_transition(good_to_bad_probability, bad_to_good_probability)
    losses = (good_loss_probability, bad_loss_probability)
    total = [0.0, 0.0]
    total[initial_state] = 1.0
    survived = [0.0, 0.0]
    survived[initial_state] = 1.0

    for _ in range(interval_rounds):
        next_total = [0.0, 0.0]
        next_survived = [0.0, 0.0]
        for current in (0, 1):
            for following in (0, 1):
                next_total[following] += total[current] * transition[current][following]
                next_survived[following] += (
                    survived[current] * (1.0 - losses[current]) * transition[current][following]
                )
        total, survived = next_total, next_survived

    failed = [max(0.0, total[state] - survived[state]) for state in (0, 1)]
    return survived[0], survived[1], failed[0], failed[1]


def build_per_packet_epoch_transition(
    *,
    slots: int,
    required: int,
    interval_rounds: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
) -> List[List[float]]:
    """Build K[b,b'] for independent packet-specific Markov channel states.

    b is the number of bad channel slots at epoch start. The DP tracks the
    number of data packets that survived the whole epoch (capped at k) and the
    number of slots whose channel ends bad. At a successful repair boundary,
    all data are rewritten, but the endpoint channel-state pattern persists.
    """
    _positive_int(slots, "slots", MAX_SLOTS)
    _positive_int(required, "required", slots)
    _positive_int(interval_rounds, "interval_rounds", 10000)
    p_good = _probability(good_loss_probability, "good_loss_probability")
    p_bad = _probability(bad_loss_probability, "bad_loss_probability")
    alpha = _probability(good_to_bad_probability, "good_to_bad_probability")
    beta = _probability(bad_to_good_probability, "bad_to_good_probability")
    if p_good > p_bad:
        raise RepairEpochError("good_loss_probability must not exceed bad_loss_probability")

    good_outcomes = _slot_epoch_outcomes(
        0, interval_rounds=interval_rounds,
        good_loss_probability=p_good, bad_loss_probability=p_bad,
        good_to_bad_probability=alpha, bad_to_good_probability=beta,
    )
    bad_outcomes = _slot_epoch_outcomes(
        1, interval_rounds=interval_rounds,
        good_loss_probability=p_good, bad_loss_probability=p_bad,
        good_to_bad_probability=alpha, bad_to_good_probability=beta,
    )
    matrix = [[0.0] * (slots + 1) for _ in range(slots + 1)]

    for initial_bad_count in range(slots + 1):
        # dp[survivors capped at k][bad endpoint slots]
        dp = [[0.0] * (slots + 1) for _ in range(required + 1)]
        dp[0][0] = 1.0
        processed = 0
        slot_types = (0,) * (slots - initial_bad_count) + (1,) * initial_bad_count

        for initial_state in slot_types:
            survive_good, survive_bad, fail_good, fail_bad = (
                good_outcomes if initial_state == 0 else bad_outcomes
            )
            next_dp = [[0.0] * (slots + 1) for _ in range(required + 1)]
            max_survivors = min(required, processed)
            for survivors in range(max_survivors + 1):
                row = dp[survivors]
                for endpoint_bad in range(processed + 1):
                    mass = row[endpoint_bad]
                    if mass == 0.0:
                        continue
                    next_dp[min(required, survivors + 1)][endpoint_bad] += mass * survive_good
                    next_dp[min(required, survivors + 1)][endpoint_bad + 1] += mass * survive_bad
                    next_dp[survivors][endpoint_bad] += mass * fail_good
                    next_dp[survivors][endpoint_bad + 1] += mass * fail_bad
            dp = next_dp
            processed += 1

        # Index 'required' aggregates every outcome with at least k survivors.
        matrix[initial_bad_count] = dp[required][:]

    return matrix


def build_shared_channel_epoch_transition(
    *,
    slots: int,
    required: int,
    interval_rounds: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
) -> List[List[float]]:
    """Build a 2x2 successful-epoch matrix over the persistent shared channel."""
    _positive_int(slots, "slots", MAX_SLOTS)
    _positive_int(required, "required", slots)
    _positive_int(interval_rounds, "interval_rounds", 10000)
    p_good = _probability(good_loss_probability, "good_loss_probability")
    p_bad = _probability(bad_loss_probability, "bad_loss_probability")
    alpha = _probability(good_to_bad_probability, "good_to_bad_probability")
    beta = _probability(bad_to_good_probability, "bad_to_good_probability")
    if p_good > p_bad:
        raise RepairEpochError("good_loss_probability must not exceed bad_loss_probability")
    transition = _channel_transition(alpha, beta)
    loss = (p_good, p_bad)
    matrix = [[0.0, 0.0], [0.0, 0.0]]

    for initial_state in (0, 1):
        # mass[state][alive] enters the next circulation in that state.
        mass = [[0.0] * (slots + 1) for _ in range(2)]
        mass[initial_state][slots] = 1.0
        pmf_cache: Dict[Tuple[int, int], List[float]] = {}

        for _ in range(interval_rounds):
            next_mass = [[0.0] * (slots + 1) for _ in range(2)]
            for current_state in (0, 1):
                survival_probability = 1.0 - loss[current_state]
                for alive in range(required, slots + 1):
                    source_mass = mass[current_state][alive]
                    if source_mass == 0.0:
                        continue
                    cache_key = (alive, current_state)
                    probabilities = pmf_cache.get(cache_key)
                    if probabilities is None:
                        probabilities = _binomial_pmf(alive, survival_probability)
                        pmf_cache[cache_key] = probabilities
                    for remaining in range(required, alive + 1):
                        after_loss = source_mass * probabilities[remaining]
                        if after_loss == 0.0:
                            continue
                        for following_state in (0, 1):
                            next_mass[following_state][remaining] += (
                                after_loss * transition[current_state][following_state]
                            )
            mass = next_mass

        for final_state in (0, 1):
            matrix[initial_state][final_state] = math.fsum(mass[final_state][required:])

    return matrix


def initial_per_packet_state_distribution(slots: int, initial_bad_probability: float) -> List[float]:
    return _binomial_pmf(slots, _probability(initial_bad_probability, "initial_bad_probability"))


def _row_vector_multiply(vector: Sequence[float], matrix: Sequence[Sequence[float]]) -> List[float]:
    width = len(matrix[0])
    return [
        math.fsum(vector[row] * matrix[row][column] for row in range(len(vector)))
        for column in range(width)
    ]


def _solve_linear_system(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> Optional[List[float]]:
    """Solve A x=b by Gaussian elimination with partial pivoting.

    None denotes a singular/ill-conditioned fundamental matrix, which is
    conservatively reported as an unbounded expected number of epochs.
    """
    size = len(rhs)
    work = [
        [float(matrix[row][column]) for column in range(size)] + [float(rhs[row])]
        for row in range(size)
    ]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        pivot_value = work[pivot][column]
        if abs(pivot_value) < 1e-14:
            return None
        if pivot != column:
            work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        for item in range(column, size + 1):
            work[column][item] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            if factor == 0.0:
                continue
            for item in range(column, size + 1):
                work[row][item] -= factor * work[column][item]
    solution = [work[row][size] for row in range(size)]
    if any(not math.isfinite(value) or value < -1e-8 for value in solution):
        return None
    return [max(0.0, value) for value in solution]


def _expected_attempted_epochs(
    initial_distribution: Sequence[float],
    transition: Sequence[Sequence[float]],
) -> Optional[float]:
    size = len(initial_distribution)
    fundamental = [
        [
            (1.0 if row == column else 0.0) - transition[row][column]
            for column in range(size)
        ]
        for row in range(size)
    ]
    values = _solve_linear_system(fundamental, [1.0] * size)
    if values is None:
        return None
    return math.fsum(initial_distribution[index] * values[index] for index in range(size))


def _survival_curve(
    initial_distribution: Sequence[float],
    transition: Sequence[Sequence[float]],
    max_epochs: int,
) -> List[float]:
    state = list(initial_distribution)
    result = [1.0]
    for _ in range(max_epochs):
        state = _row_vector_multiply(state, transition)
        probability = math.fsum(state)
        result.append(min(1.0, max(0.0, probability)))
    return result


def simulate_repair_survival(
    model: str,
    *,
    slots: int,
    required: int,
    interval_rounds: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    max_epochs: int,
    trials: int,
    seed: int = 0,
) -> Dict[str, Any]:
    """Seeded simulation of successful repair epochs for an implementation check."""
    if model not in MODELS:
        raise RepairEpochError(f"unsupported model: {model}")
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise RepairEpochError("trials must be a positive integer")
    parameters = _validate_parameters(
        slots=slots,
        good_loss_probability=good_loss_probability,
        bad_loss_probability=bad_loss_probability,
        good_to_bad_probability=good_to_bad_probability,
        bad_to_good_probability=bad_to_good_probability,
        initial_bad_probability=initial_bad_probability,
    )
    p_good, p_bad, alpha, beta, initial_bad = parameters
    _positive_int(required, "required", slots)
    _positive_int(interval_rounds, "interval_rounds", 10000)
    _positive_int(max_epochs, "max_epochs", 100000)
    if model == "iid_marginal":
        marginal_loss = (1.0 - initial_bad) * p_good + initial_bad * p_bad
        p_good = p_bad = marginal_loss
        alpha = beta = initial_bad = 0.0

    rng = random.Random(seed)
    survived_counts = [0] * max_epochs
    for _ in range(trials):
        alive = [True] * slots
        if model == "shared_channel":
            shared_bad = rng.random() < initial_bad
            packet_bad = []
        else:
            shared_bad = False
            packet_bad = [rng.random() < initial_bad for _ in range(slots)]

        completed_repairs = 0
        for epoch in range(1, max_epochs + 1):
            for _round in range(interval_rounds):
                if model == "shared_channel":
                    loss_probability = p_bad if shared_bad else p_good
                    for index in range(slots):
                        if alive[index] and rng.random() < loss_probability:
                            alive[index] = False
                    if shared_bad:
                        shared_bad = not (rng.random() < beta)
                    else:
                        shared_bad = rng.random() < alpha
                else:
                    for index in range(slots):
                        state_bad = packet_bad[index]
                        loss_probability = p_bad if state_bad else p_good
                        if alive[index] and rng.random() < loss_probability:
                            alive[index] = False
                        # Channel state evolves even when its data packet was lost.
                        if state_bad:
                            packet_bad[index] = not (rng.random() < beta)
                        else:
                            packet_bad[index] = rng.random() < alpha
            if sum(alive) < required:
                break
            # A successful repair reconstructs all data; channel states persist.
            alive = [True] * slots
            completed_repairs += 1
        for index in range(completed_repairs):
            survived_counts[index] += 1

    return {
        "model": model,
        "trials": trials,
        "seed": seed,
        "survival_probability_after_epochs": {
            str(epoch): survived_counts[epoch - 1] / trials
            for epoch in (1, 2, 5, 10, max_epochs)
            if epoch <= max_epochs
        },
    }


def _policy_model_report(
    model: str,
    *,
    slots: int,
    required: int,
    interval_rounds: int,
    initial_distribution: Sequence[float],
    transition: Sequence[Sequence[float]],
    max_epochs: int,
    no_repair_curve: Sequence[float],
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    simulation_trials: Optional[int],
    simulation_seed: int,
) -> Dict[str, Any]:
    survival = _survival_curve(initial_distribution, transition, max_epochs)
    median_epoch = next((epoch for epoch, probability in enumerate(survival[1:], start=1)
                         if probability <= 0.5), None)
    expected_epochs = _expected_attempted_epochs(initial_distribution, transition)
    if expected_epochs is None:
        expected_lifetime_rounds = None
        expected_repairs = None
        repair_rate = None
        expectation_status = "unbounded_or_ill_conditioned"
    else:
        expected_lifetime_rounds = interval_rounds * expected_epochs
        expected_repairs = max(0.0, expected_epochs - 1.0)
        repair_rate = (
            100.0 * expected_repairs / expected_lifetime_rounds
            if expected_lifetime_rounds > 0.0 else 0.0
        )
        expectation_status = "finite"

    comparison_epochs = median_epoch if median_epoch is not None else max_epochs
    comparison_rounds = interval_rounds * comparison_epochs
    no_repair = no_repair_curve[comparison_rounds] if comparison_rounds < len(no_repair_curve) else None
    result: Dict[str, Any] = {
        "model": model,
        "slots": slots,
        "required": required,
        "interval_rounds": interval_rounds,
        "epoch_success_probability": survival[1],
        "median_failure_epoch": median_epoch,
        "median_failure_rounds": (
            None if median_epoch is None else interval_rounds * median_epoch
        ),
        "median_status": (
            "crossed" if median_epoch is not None else "not_reached_within_horizon"
        ),
        "max_epochs_checked": max_epochs,
        "survival_probability_after_epochs": {
            str(epoch): survival[epoch]
            for epoch in (1, 2, 5, 10, 20, 50, max_epochs)
            if epoch <= max_epochs
        },
        "expected_attempted_epochs_including_failure": expected_epochs,
        "expected_successful_repairs_before_failure": expected_repairs,
        "expected_lifetime_rounds": expected_lifetime_rounds,
        "expected_lifetime_rounds_including_failed_epoch": expected_lifetime_rounds,
        "expected_repairs_per_100_lifetime_rounds_ratio": repair_rate,
        "expectation_status": expectation_status,
        "no_repair_survival_at_comparison_horizon": {
            "rounds": comparison_rounds,
            "probability": no_repair,
            "comparison_basis": (
                "same total circulation horizon as the repair-policy median failure epoch; "
                "uses the original no-repair burst-loss process"
            ),
        },
        "initial_state_distribution": list(initial_distribution),
        "successful_epoch_transition_matrix": [list(row) for row in transition],
        "transition_matrix_sha256": _digest(transition),
    }
    if simulation_trials is not None:
        result["simulation"] = simulate_repair_survival(
            model,
            slots=slots,
            required=required,
            interval_rounds=interval_rounds,
            good_loss_probability=good_loss_probability,
            bad_loss_probability=bad_loss_probability,
            good_to_bad_probability=good_to_bad_probability,
            bad_to_good_probability=bad_to_good_probability,
            initial_bad_probability=initial_bad_probability,
            max_epochs=max_epochs,
            trials=simulation_trials,
            seed=simulation_seed,
        )
    return result


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_life, right_life = left["expected_lifetime_rounds"], right["expected_lifetime_rounds"]
    left_rate, right_rate = left["expected_repairs_per_100_lifetime_rounds_ratio"], right["expected_repairs_per_100_lifetime_rounds_ratio"]
    if left_life is None or right_life is None or left_rate is None or right_rate is None:
        return False
    at_least_as_long = left_life >= right_life - 1e-10
    no_more_repair_rate = left_rate <= right_rate + 1e-10
    strictly_better = left_life > right_life + 1e-10 or left_rate < right_rate - 1e-10
    return at_least_as_long and no_more_repair_rate and strictly_better


def build_repair_sweep(
    *,
    scenario_name: str,
    slots: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    interval_rounds: Sequence[int],
    recovery_thresholds: Sequence[int],
    max_epochs: int = 100,
    simulation_trials: Optional[int] = None,
    simulation_seed: int = 0,
) -> Dict[str, Any]:
    """Reconstruct policy outcomes for an interval × threshold sweep."""
    p_good, p_bad, alpha, beta, initial_bad = _validate_parameters(
        slots=slots,
        good_loss_probability=good_loss_probability,
        bad_loss_probability=bad_loss_probability,
        good_to_bad_probability=good_to_bad_probability,
        bad_to_good_probability=bad_to_good_probability,
        initial_bad_probability=initial_bad_probability,
    )
    _positive_int(max_epochs, "max_epochs", 100000)
    intervals = sorted(set(_positive_int(value, "interval_rounds", 10000) for value in interval_rounds))
    thresholds = sorted(set(_positive_int(value, "recovery_threshold", slots) for value in recovery_thresholds))
    if not intervals or not thresholds:
        raise RepairEpochError("interval_rounds and recovery_thresholds must be non-empty")
    if simulation_trials is not None:
        _positive_int(simulation_trials, "simulation_trials")

    average_loss = (1.0 - initial_bad) * p_good + initial_bad * p_bad
    max_total_rounds = max(intervals) * max_epochs
    if max_total_rounds > MAX_TOTAL_ROUNDS:
        raise RepairEpochError(
            f"max(interval_rounds) * max_epochs must be <= {MAX_TOTAL_ROUNDS}"
        )
    # Cache the original no-repair curves once per recovery threshold/model.
    no_repair_by_threshold: Dict[int, Dict[str, List[float]]] = {}
    for required in thresholds:
        no_repair_by_threshold[required] = {
            "iid_marginal": [
                binomial_tail_probability(slots, required, (1.0 - average_loss) ** rounds)
                for rounds in range(max_total_rounds + 1)
            ],
            "per_packet_markov": per_packet_retention_curve(
                slots, required, p_good, p_bad, alpha, beta, initial_bad, max_total_rounds
            ),
            "shared_channel": shared_channel_retention_curve(
                slots, required, p_good, p_bad, alpha, beta, initial_bad, max_total_rounds
            ),
        }

    policies: List[Dict[str, Any]] = []
    flattened: Dict[str, List[Dict[str, Any]]] = {model: [] for model in MODELS}
    for required in thresholds:
        for interval in intervals:
            iid_success = binomial_tail_probability(slots, required, (1.0 - average_loss) ** interval)
            matrices = {
                "iid_marginal": [[iid_success]],
                "per_packet_markov": build_per_packet_epoch_transition(
                    slots=slots, required=required, interval_rounds=interval,
                    good_loss_probability=p_good, bad_loss_probability=p_bad,
                    good_to_bad_probability=alpha, bad_to_good_probability=beta,
                ),
                "shared_channel": build_shared_channel_epoch_transition(
                    slots=slots, required=required, interval_rounds=interval,
                    good_loss_probability=p_good, bad_loss_probability=p_bad,
                    good_to_bad_probability=alpha, bad_to_good_probability=beta,
                ),
            }
            initial_distributions = {
                "iid_marginal": [1.0],
                "per_packet_markov": initial_per_packet_state_distribution(slots, initial_bad),
                "shared_channel": [1.0 - initial_bad, initial_bad],
            }
            model_reports = {}
            for model_index, model in enumerate(MODELS):
                report = _policy_model_report(
                    model, slots=slots, required=required, interval_rounds=interval,
                    initial_distribution=initial_distributions[model],
                    transition=matrices[model], max_epochs=max_epochs,
                    no_repair_curve=no_repair_by_threshold[required][model],
                    good_loss_probability=p_good,
                    bad_loss_probability=p_bad,
                    good_to_bad_probability=alpha,
                    bad_to_good_probability=beta,
                    initial_bad_probability=initial_bad,
                    simulation_trials=simulation_trials,
                    simulation_seed=simulation_seed + required * 1000 + interval * 10 + model_index,
                )
                model_reports[model] = report
                flattened[model].append(report)
            policy = {
                "recovery_threshold": required,
                "interval_rounds": interval,
                "models": model_reports,
            }
            policies.append(policy)

    pareto = {}
    for model in MODELS:
        candidates = flattened[model]
        frontier = [
            candidate for candidate in candidates
            if not any(
                _dominates(other, candidate)
                for other in candidates
                if other is not candidate
            )
        ]
        frontier.sort(key=lambda item: (
            -(item["expected_lifetime_rounds"] if item["expected_lifetime_rounds"] is not None else math.inf),
            item["expected_repairs_per_100_lifetime_rounds_ratio"]
            if item["expected_repairs_per_100_lifetime_rounds_ratio"] is not None else math.inf,
        ))
        pareto[model] = [
            {
                "recovery_threshold": item["required"],
                "interval_rounds": item["interval_rounds"],
                "expected_lifetime_rounds": item["expected_lifetime_rounds"],
                "expected_successful_repairs_before_failure": item["expected_successful_repairs_before_failure"],
                "expected_repairs_per_100_lifetime_rounds_ratio": item["expected_repairs_per_100_lifetime_rounds_ratio"],
            }
            for item in frontier
        ]

    core = {
        "format": "in-formation.in-transit-repair-sweep",
        "schema": "in-formation.in-transit-repair-sweep/0.1",
        "scenario": {
            "name": scenario_name,
            "slots": slots,
            "good_loss_probability": p_good,
            "bad_loss_probability": p_bad,
            "good_to_bad_probability": alpha,
            "bad_to_good_probability": beta,
            "initial_bad_probability": initial_bad,
            "stationary_bad_probability": alpha / (alpha + beta) if alpha + beta > 0 else None,
            "marginal_first_round_loss_probability": average_loss,
            "interval_rounds": intervals,
            "recovery_thresholds": thresholds,
            "max_epochs": max_epochs,
            "repair_semantics": (
                "At each fixed epoch boundary, if at least k of n data packets remain, "
                "all n data packets are reconstructed instantaneously. Every per-packet "
                "or shared channel Markov state persists across repair; channel transitions "
                "continue while data is absent. Failed recovery permanently loses the word."
            ),
        },
        "policy_count": len(policies),
        "policies": policies,
        "pareto_frontier": pareto,
        "interpretation_limits": [
            "All channel probabilities are declared model parameters; none are fitted from packet traces or a deployed channel.",
            "A repair is instantaneous, has no failure or latency of its own, and rewrites all n data packets when at least k survive.",
            "The channel state persists across successful repairs; per-packet channel states continue evolving even after an individual packet is lost.",
            "No-repair comparisons use the same first-round marginal loss for iid_marginal and the same Markov process for the two burst models.",
            "Expected repair rate is a ratio of expected successful repairs to expected lifetime rounds, expressed per 100 rounds; it is not the expectation of a sample-path rate.",
            "The Pareto frontier compares expected lifetime against repair-event rate only. It assigns no monetary or utility value to redundancy, repair cost, or lost data.",
            "Finite expected lifetime is computed from the fundamental matrix of the successful-epoch Markov chain. Ill-conditioned or singular systems are reported as unbounded_or_ill_conditioned rather than as a finite estimate.",
            "This experiment is a probability model, not a performance measurement of E-CPU, MailCPU, an optical link, or any hardware substrate.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_repair_sweep(report: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, Mapping):
        raise RepairEpochError("report must be a mapping")
    supplied = copy.deepcopy(dict(report))
    digest_value = supplied.pop("report_digest", None)
    if digest_value != _digest(supplied):
        raise RepairEpochError("repair sweep report digest mismatch")
    if supplied.get("format") != "in-formation.in-transit-repair-sweep" or supplied.get("schema") != "in-formation.in-transit-repair-sweep/0.1":
        raise RepairEpochError("unsupported repair sweep report format or schema")
    scenario = supplied.get("scenario")
    if not isinstance(scenario, Mapping):
        raise RepairEpochError("scenario is missing")
    rebuilt = build_repair_sweep(
        scenario_name=scenario["name"],
        slots=scenario["slots"],
        good_loss_probability=scenario["good_loss_probability"],
        bad_loss_probability=scenario["bad_loss_probability"],
        good_to_bad_probability=scenario["good_to_bad_probability"],
        bad_to_good_probability=scenario["bad_to_good_probability"],
        initial_bad_probability=scenario["initial_bad_probability"],
        interval_rounds=scenario["interval_rounds"],
        recovery_thresholds=scenario["recovery_thresholds"],
        max_epochs=scenario["max_epochs"],
        simulation_trials=None,
    )
    # Simulation results are external samples; strip them before deterministic reconstruction.
    supplied_policies = supplied.get("policies", [])
    for policy in supplied_policies:
        for model_report in policy.get("models", {}).values():
            model_report.pop("simulation", None)
    rebuilt_policies = rebuilt["policies"]
    if supplied_policies != rebuilt_policies:
        raise RepairEpochError("repair report differs from reconstruction from source parameters")
    for key in ("format", "schema", "scenario", "policy_count", "pareto_frontier", "interpretation_limits"):
        if supplied.get(key) != rebuilt.get(key):
            raise RepairEpochError(f"repair report {key} differs from reconstruction")
    return dict(report)


DEFAULT_SCENARIOS = (
    {
        "scenario_name": "stationary_moderate_bursts",
        "slots": 12,
        "good_loss_probability": 0.01,
        "bad_loss_probability": 0.40,
        "good_to_bad_probability": 0.08,
        "bad_to_good_probability": 0.25,
        "initial_bad_probability": 0.08 / (0.08 + 0.25),
        "interval_rounds": (1, 2, 4, 8),
        "recovery_thresholds": (12, 6, 1),
        "max_epochs": 100,
    },
    {
        "scenario_name": "rare_persistent_bad_bursts",
        "slots": 12,
        "good_loss_probability": 0.001,
        "bad_loss_probability": 0.70,
        "good_to_bad_probability": 0.02,
        "bad_to_good_probability": 0.08,
        "initial_bad_probability": 0.02 / (0.02 + 0.08),
        "interval_rounds": (1, 2, 4, 8),
        "recovery_thresholds": (12, 6, 1),
        "max_epochs": 100,
    },
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare exact periodic repair policies under persistent Markov burst loss.")
    parser.add_argument("--scan", action="store_true", help="run the checked-in interval/threshold scenarios")
    parser.add_argument("--slots", type=int, default=12)
    parser.add_argument("--good-loss", type=float, default=0.01)
    parser.add_argument("--bad-loss", type=float, default=0.40)
    parser.add_argument("--good-to-bad", type=float, default=0.08)
    parser.add_argument("--bad-to-good", type=float, default=0.25)
    parser.add_argument("--initial-bad", type=float, default=0.08 / 0.33)
    parser.add_argument("--intervals", default="1,2,4,8")
    parser.add_argument("--thresholds", default="12,6,1")
    parser.add_argument("--max-epochs", type=int, default=100)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def _parse_ints(value: str, label: str) -> List[int]:
    try:
        items = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as error:
        raise RepairEpochError(f"{label} must be comma-separated integers") from error
    if not items:
        raise RepairEpochError(f"{label} must contain at least one integer")
    return items


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.scan:
            reports = [
                build_repair_sweep(
                    **scenario,
                    simulation_trials=args.trials if args.simulate else None,
                    simulation_seed=args.seed + index * 10000,
                )
                for index, scenario in enumerate(DEFAULT_SCENARIOS)
            ]
        else:
            reports = [build_repair_sweep(
                scenario_name="custom",
                slots=args.slots,
                good_loss_probability=args.good_loss,
                bad_loss_probability=args.bad_loss,
                good_to_bad_probability=args.good_to_bad,
                bad_to_good_probability=args.bad_to_good,
                initial_bad_probability=args.initial_bad,
                interval_rounds=_parse_ints(args.intervals, "intervals"),
                recovery_thresholds=_parse_ints(args.thresholds, "thresholds"),
                max_epochs=args.max_epochs,
                simulation_trials=args.trials if args.simulate else None,
                simulation_seed=args.seed,
            )]
        if args.json:
            rendered = json.dumps(reports, indent=2, sort_keys=True, allow_nan=False)
        else:
            lines = [
                "scenario | model | k | interval | expected lifetime rounds | repairs / 100 rounds | median failure epoch"
            ]
            for report in reports:
                for policy in report["policies"]:
                    for model in MODELS:
                        entry = policy["models"][model]
                        median = (
                            str(entry["median_failure_epoch"])
                            if entry["median_failure_epoch"] is not None
                            else f">{entry['max_epochs_checked']} (censored)"
                        )
                        lines.append(
                            f"{report['scenario']['name']} | {model} | {entry['required']} | "
                            f"{entry['interval_rounds']} | {entry['expected_lifetime_rounds']} | "
                            f"{entry['expected_repairs_per_100_lifetime_rounds_ratio']} | {median}"
                        )
                for model in MODELS:
                    lines.append(f"Pareto frontier | {report['scenario']['name']} | {model}")
                    for item in report["pareto_frontier"][model]:
                        lines.append(
                            f"  k={item['recovery_threshold']} L={item['interval_rounds']} | "
                            f"expected_lifetime_rounds={item['expected_lifetime_rounds']} | "
                            f"repairs_per_100_rounds={item['expected_repairs_per_100_lifetime_rounds_ratio']}"
                        )
            rendered = "\n".join(lines)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {args.output}")
        else:
            print(rendered)
        return 0
    except (ArithmeticError, OSError, RepairEpochError, TypeError, ValueError, KeyError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
