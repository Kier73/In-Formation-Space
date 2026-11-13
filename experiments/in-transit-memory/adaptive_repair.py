#!/usr/bin/env python3
"""Finite-horizon adaptive repair for a fully observed shared burst channel.

MRE-003 relaxes periodic repair. At each circulation boundary the controller
observes (surviving data-packet count, shared good/bad channel state) and chooses
between WAIT and instantaneous REPAIR. A repair reconstructs all data packets
but does not reset the shared channel state.

The finite-horizon objective is explicit:
    terminal_survival_probability - repair_cost * expected_repair_count

The repair_cost is measured in units of terminal survival reward. The model
does not hide a scalar weight, infer a universal optimum, or assign an
unmeasured repair duration. Exact observation of both state components is
assumed free in this first model; sensing/telemetry cost and observation error
are excluded and called out in every report.

Channel losses occur during a circulation in the state observed at its start.
The Markov channel transition happens after those losses. Failure below k
survivors is absorbing. At the horizon, survival reward is 1 iff at least k
packets remain.
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

MODELS = ("shared_channel_fully_observed",)
CHANNEL_STATES = ("good", "bad")
MAX_SLOTS = 32
MAX_HORIZON = 100
TIE_TOLERANCE = 1e-12


class AdaptiveRepairError(ValueError):
    """Invalid adaptive-repair model, policy, or reconstructed report."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise AdaptiveRepairError(f"value is not finite canonical JSON: {error}") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _probability(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdaptiveRepairError(f"{label} must be a finite probability")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise AdaptiveRepairError(f"{label} must be a finite probability") from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise AdaptiveRepairError(f"{label} must be in [0, 1]")
    return number


def _nonnegative_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdaptiveRepairError(f"{label} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise AdaptiveRepairError(f"{label} must be a finite non-negative number") from error
    if not math.isfinite(number) or number < 0.0:
        raise AdaptiveRepairError(f"{label} must be a finite non-negative number")
    return number


def _positive_int(value: object, label: str, maximum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AdaptiveRepairError(f"{label} must be a positive integer")
    if maximum is not None and value > maximum:
        raise AdaptiveRepairError(f"{label} must be <= {maximum}")
    return value


def _validate_parameters(
    *,
    slots: int,
    recovery_threshold: int,
    horizon: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    repair_cost: float,
) -> Tuple[float, float, float, float, float, float]:
    _positive_int(slots, "slots", MAX_SLOTS)
    _positive_int(recovery_threshold, "recovery_threshold", slots)
    _positive_int(horizon, "horizon", MAX_HORIZON)
    p_good = _probability(good_loss_probability, "good_loss_probability")
    p_bad = _probability(bad_loss_probability, "bad_loss_probability")
    alpha = _probability(good_to_bad_probability, "good_to_bad_probability")
    beta = _probability(bad_to_good_probability, "bad_to_good_probability")
    initial_bad = _probability(initial_bad_probability, "initial_bad_probability")
    cost = _nonnegative_finite(repair_cost, "repair_cost")
    if p_good > p_bad:
        raise AdaptiveRepairError("good_loss_probability must not exceed bad_loss_probability")
    return p_good, p_bad, alpha, beta, initial_bad, cost


def _binomial_pmf(trials: int, probability: float) -> Tuple[float, ...]:
    if probability <= 0.0:
        return (1.0,) + (0.0,) * trials
    if probability >= 1.0:
        return (0.0,) * trials + (1.0,)
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    values = []
    for successes in range(trials + 1):
        log_value = (
            math.lgamma(trials + 1)
            - math.lgamma(successes + 1)
            - math.lgamma(trials - successes + 1)
            + successes * log_p
            + (trials - successes) * log_q
        )
        values.append(math.exp(log_value))
    total = math.fsum(values)
    if total <= 0.0:
        raise ArithmeticError("binomial PMF underflowed completely")
    return tuple(value / total for value in values)


def _channel_transition(alpha: float, beta: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    # State index 0 = good, 1 = bad. Transition follows current-round losses.
    return ((1.0 - alpha, alpha), (beta, 1.0 - beta))


def _round_kernel(
    slots: int,
    p_good: float,
    p_bad: float,
    alpha: float,
    beta: float,
) -> Dict[Tuple[int, int], Tuple[float, ...]]:
    """Cache survivor-count PMFs by (live packets, current channel state)."""
    return {
        (live, state): _binomial_pmf(live, 1.0 - (p_good if state == 0 else p_bad))
        for live in range(slots + 1)
        for state in (0, 1)
    }


def _expected_next_value(
    *,
    live_packets: int,
    channel_state: int,
    next_values: Sequence[Sequence[float]],
    kernel: Mapping[Tuple[int, int], Sequence[float]],
    transition: Sequence[Sequence[float]],
    recovery_threshold: int,
) -> float:
    probabilities = kernel[(live_packets, channel_state)]
    contributions = []
    for survivors in range(recovery_threshold, live_packets + 1):
        probability = probabilities[survivors]
        if probability == 0.0:
            continue
        for following_state in (0, 1):
            mass = probability * transition[channel_state][following_state]
            if mass:
                contributions.append(mass * next_values[survivors][following_state])
    return math.fsum(contributions)


def _forward_evaluate(
    *,
    slots: int,
    recovery_threshold: int,
    horizon: int,
    initial_bad_probability: float,
    repair_cost: float,
    policy_table: Optional[Sequence[Sequence[Mapping[str, Any]]]],
    fixed_interval: Optional[int],
    kernel: Mapping[Tuple[int, int], Sequence[float]],
    transition: Sequence[Sequence[float]],
) -> Dict[str, float]:
    """Evaluate one deterministic fully observed policy using exact state mass."""
    mass = [[0.0, 0.0] for _ in range(slots + 1)]
    mass[slots][0] = 1.0 - initial_bad_probability
    mass[slots][1] = initial_bad_probability
    expected_repairs = 0.0

    for time_index in range(horizon):
        next_mass = [[0.0, 0.0] for _ in range(slots + 1)]
        repair_mass = 0.0
        for live in range(recovery_threshold, slots + 1):
            for state in (0, 1):
                state_mass = mass[live][state]
                if state_mass == 0.0:
                    continue
                action = "wait"
                if fixed_interval is not None:
                    if (
                        time_index > 0
                        and time_index % fixed_interval == 0
                        and live < slots
                    ):
                        action = "repair"
                elif policy_table is not None:
                    action = policy_table[time_index][live][CHANNEL_STATES[state]]
                if action not in {"wait", "repair"}:
                    raise AdaptiveRepairError(f"unsupported policy action: {action}")
                starting_live = slots if action == "repair" else live
                if action == "repair":
                    repair_mass += state_mass

                probabilities = kernel[(starting_live, state)]
                for survivors in range(recovery_threshold, starting_live + 1):
                    probability = probabilities[survivors]
                    if probability == 0.0:
                        continue
                    for following_state in (0, 1):
                        next_mass[survivors][following_state] += (
                            state_mass * probability * transition[state][following_state]
                        )
        expected_repairs += repair_mass
        mass = next_mass

    survival = math.fsum(math.fsum(row) for row in mass[recovery_threshold:])
    utility = survival - repair_cost * expected_repairs
    return {
        "survival_probability": min(1.0, max(0.0, survival)),
        "expected_repair_count": expected_repairs,
        "repair_cost": repair_cost,
        "expected_repair_cost": repair_cost * expected_repairs,
        "expected_utility": utility,
    }


def _build_adaptive_policy(
    *,
    slots: int,
    recovery_threshold: int,
    horizon: int,
    repair_cost: float,
    kernel: Mapping[Tuple[int, int], Sequence[float]],
    transition: Sequence[Sequence[float]],
) -> Tuple[List[List[Dict[str, str]]], List[List[List[float]]]]:
    """Backward induction; ties choose WAIT to minimize unnecessary repairs."""
    values = [
        [[0.0, 0.0] for _ in range(slots + 1)]
        for _ in range(horizon + 1)
    ]
    actions: List[List[Dict[str, str]]] = [
        [
            {"good": "failed", "bad": "failed"}
            for _ in range(slots + 1)
        ]
        for _ in range(horizon)
    ]

    # Terminal payoff is 1 for any recoverable survivor count and 0 below k.
    for live in range(recovery_threshold, slots + 1):
        values[horizon][live] = [1.0, 1.0]

    for time_index in range(horizon - 1, -1, -1):
        next_values = values[time_index + 1]
        for live in range(recovery_threshold, slots + 1):
            for state in (0, 1):
                wait_value = _expected_next_value(
                    live_packets=live,
                    channel_state=state,
                    next_values=next_values,
                    kernel=kernel,
                    transition=transition,
                    recovery_threshold=recovery_threshold,
                )
                repair_value = -repair_cost + _expected_next_value(
                    live_packets=slots,
                    channel_state=state,
                    next_values=next_values,
                    kernel=kernel,
                    transition=transition,
                    recovery_threshold=recovery_threshold,
                )
                # Repairing a complete block has no physical effect; avoid it.
                if live == slots or repair_value <= wait_value + TIE_TOLERANCE:
                    action = "wait"
                    value = wait_value
                else:
                    action = "repair"
                    value = repair_value
                state_name = CHANNEL_STATES[state]
                actions[time_index][live][state_name] = action
                values[time_index][live][state] = value

    policy_table = [
        [
            {
                "good": actions[t][live]["good"],
                "bad": actions[t][live]["bad"],
            }
            for live in range(slots + 1)
        ]
        for t in range(horizon)
    ]
    return policy_table, values


def _decision_table(
    policy_table: Sequence[Sequence[Mapping[str, str]]],
    *,
    recovery_threshold: int,
    slots: int,
    horizon: int,
    values: Sequence[Sequence[Sequence[float]]],
    repair_cost: float,
    kernel: Mapping[Tuple[int, int], Sequence[float]],
    transition: Sequence[Sequence[float]],
) -> List[Dict[str, Any]]:
    """Portable full state/action table, including WAIT/REPAIR value estimates."""
    table = []
    for time_index in range(horizon):
        next_values = values[time_index + 1]
        for live in range(recovery_threshold, slots + 1):
            for state, state_name in enumerate(CHANNEL_STATES):
                wait_value = _expected_next_value(
                    live_packets=live,
                    channel_state=state,
                    next_values=next_values,
                    kernel=kernel,
                    transition=transition,
                    recovery_threshold=recovery_threshold,
                )
                repair_value = -repair_cost + _expected_next_value(
                    live_packets=slots,
                    channel_state=state,
                    next_values=next_values,
                    kernel=kernel,
                    transition=transition,
                    recovery_threshold=recovery_threshold,
                )
                table.append({
                    "time_index": time_index,
                    "surviving_packets": live,
                    "channel_state": state_name,
                    "wait_value": wait_value,
                    "repair_value": repair_value,
                    "selected_action": policy_table[time_index][live][state_name],
                    "value": values[time_index][live][state],
                })
    return table


def _fixed_schedule_comparisons(
    *,
    slots: int,
    recovery_threshold: int,
    horizon: int,
    initial_bad_probability: float,
    repair_cost: float,
    candidate_intervals: Sequence[int],
    kernel: Mapping[Tuple[int, int], Sequence[float]],
    transition: Sequence[Sequence[float]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    reports = []
    for interval in sorted(set(candidate_intervals)):
        if interval < 1:
            raise AdaptiveRepairError("fixed repair intervals must be positive")
        report = _forward_evaluate(
            slots=slots,
            recovery_threshold=recovery_threshold,
            horizon=horizon,
            initial_bad_probability=initial_bad_probability,
            repair_cost=repair_cost,
            policy_table=None,
            fixed_interval=interval,
            kernel=kernel,
            transition=transition,
        )
        reports.append({
            "interval_rounds": interval,
            **report,
        })
    best = min(
        reports,
        key=lambda item: (
            -item["expected_utility"],
            item["expected_repair_count"],
            item["interval_rounds"],
        ),
    )
    return reports, best


def build_adaptive_repair_report(
    *,
    scenario_name: str,
    slots: int,
    recovery_threshold: int,
    horizon: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    repair_cost: float,
    fixed_intervals: Sequence[int] = (1, 2, 4, 8, 16),
) -> Dict[str, Any]:
    """Optimize one finite-horizon adaptive repair policy and compare fixed schedules."""
    p_good, p_bad, alpha, beta, initial_bad, cost = _validate_parameters(
        slots=slots,
        recovery_threshold=recovery_threshold,
        horizon=horizon,
        good_loss_probability=good_loss_probability,
        bad_loss_probability=bad_loss_probability,
        good_to_bad_probability=good_to_bad_probability,
        bad_to_good_probability=bad_to_good_probability,
        initial_bad_probability=initial_bad_probability,
        repair_cost=repair_cost,
    )
    if not isinstance(scenario_name, str) or not scenario_name.strip():
        raise AdaptiveRepairError("scenario_name must be non-empty text")
    if not isinstance(fixed_intervals, (tuple, list)) or not fixed_intervals:
        raise AdaptiveRepairError("fixed_intervals must be a non-empty sequence")
    intervals = sorted(set(_positive_int(value, "fixed_interval", MAX_HORIZON) for value in fixed_intervals))
    if any(value > horizon for value in intervals):
        # A larger interval is a no-repair candidate; canonicalize to H+1.
        intervals = sorted(set(min(value, horizon + 1) for value in intervals))
    if horizon + 1 not in intervals:
        intervals.append(horizon + 1)
        intervals.sort()

    transition = _channel_transition(alpha, beta)
    kernel = _round_kernel(slots, p_good, p_bad, alpha, beta)
    policy_table, values = _build_adaptive_policy(
        slots=slots,
        recovery_threshold=recovery_threshold,
        horizon=horizon,
        repair_cost=cost,
        kernel=kernel,
        transition=transition,
    )
    adaptive_eval = _forward_evaluate(
        slots=slots,
        recovery_threshold=recovery_threshold,
        horizon=horizon,
        initial_bad_probability=initial_bad,
        repair_cost=cost,
        policy_table=policy_table,
        fixed_interval=None,
        kernel=kernel,
        transition=transition,
    )
    initial_value = (
        (1.0 - initial_bad) * values[0][slots][0]
        + initial_bad * values[0][slots][1]
    )
    if abs(initial_value - adaptive_eval["expected_utility"]) > 1e-9:
        raise ArithmeticError("backward-induction value differs from forward policy reconstruction")

    fixed_reports, best_fixed = _fixed_schedule_comparisons(
        slots=slots,
        recovery_threshold=recovery_threshold,
        horizon=horizon,
        initial_bad_probability=initial_bad,
        repair_cost=cost,
        candidate_intervals=intervals,
        kernel=kernel,
        transition=transition,
    )
    decision_table = _decision_table(
        policy_table,
        recovery_threshold=recovery_threshold,
        slots=slots,
        horizon=horizon,
        values=values,
        repair_cost=cost,
        kernel=kernel,
        transition=transition,
    )
    policy_core = {
        "schema": "in-formation.adaptive-repair-policy/0.1",
        "scenario_name": scenario_name,
        "slots": slots,
        "recovery_threshold": recovery_threshold,
        "horizon": horizon,
        "repair_cost": cost,
        "objective": "terminal_survival_probability_minus_repair_cost_times_expected_repair_count",
        "observation_assumption": "exact_survivor_count_and_shared_channel_state_observed_before_each_decision_at_zero_sensing_cost",
        "decision_table": decision_table,
    }
    policy_digest = _digest(policy_core)
    core = {
        "format": "in-formation.adaptive-repair-report",
        "schema": "in-formation.adaptive-repair-report/0.1",
        "scenario": {
            "name": scenario_name,
            "slots": slots,
            "recovery_threshold": recovery_threshold,
            "horizon": horizon,
            "good_loss_probability": p_good,
            "bad_loss_probability": p_bad,
            "good_to_bad_probability": alpha,
            "bad_to_good_probability": beta,
            "initial_bad_probability": initial_bad,
            "stationary_bad_probability": alpha / (alpha + beta) if alpha + beta else None,
            "repair_cost": cost,
            "fixed_interval_candidates": intervals,
            "channel_timing": "Current state controls this circulation's packet losses; the Markov transition occurs after losses.",
            "repair_timing": "Decision occurs before a circulation. REPAIR reconstructs all data immediately, then the current channel state governs the next circulation.",
        },
        "adaptive_policy": {
            **adaptive_eval,
            "initial_value_from_backward_induction": initial_value,
            "policy_digest": policy_digest,
            "decision_table": decision_table,
        },
        "fixed_schedule_comparisons": fixed_reports,
        "best_fixed_schedule": best_fixed,
        "adaptive_gain_over_best_fixed": adaptive_eval["expected_utility"] - best_fixed["expected_utility"],
        "policy_core_digest": policy_digest,
        "interpretation_limits": [
            "The controller is fully observed: exact surviving-packet count and exact shared good/bad channel state are available before each decision.",
            "Sensing and telemetry are assumed instantaneous and free; no observation error, delay, bandwidth, or admission cost is modelled.",
            "Repair is instantaneous, reconstructs all data packets, and does not reset the shared channel state.",
            "The finite-horizon terminal reward is one if at least k data packets remain after H circulations and zero otherwise.",
            "The objective subtracts the declared dimensionless repair_cost times expected repair count from terminal survival probability; it is a user-specified trade-off, not a universal utility.",
            "The fixed-interval comparator uses the same objective, channel parameters, horizon, observation of recoverability, and repair semantics.",
            "Only a shared channel state is modelled. Per-packet partially observed control would require a larger hidden-state belief model.",
            "Channel parameters are supplied model values, not estimates fitted from live packet traces.",
            "This is not a measurement of E-CPU, MailCPU, a real fibre link, or any physical system.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_adaptive_repair_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, Mapping):
        raise AdaptiveRepairError("report must be a mapping")
    supplied = copy.deepcopy(dict(report))
    digest_value = supplied.pop("report_digest", None)
    if digest_value != _digest(supplied):
        raise AdaptiveRepairError("adaptive repair report digest mismatch")
    if supplied.get("format") != "in-formation.adaptive-repair-report":
        raise AdaptiveRepairError("unsupported adaptive repair format")
    scenario = supplied.get("scenario")
    if not isinstance(scenario, Mapping):
        raise AdaptiveRepairError("scenario is missing")
    rebuilt = build_adaptive_repair_report(
        scenario_name=scenario["name"],
        slots=scenario["slots"],
        recovery_threshold=scenario["recovery_threshold"],
        horizon=scenario["horizon"],
        good_loss_probability=scenario["good_loss_probability"],
        bad_loss_probability=scenario["bad_loss_probability"],
        good_to_bad_probability=scenario["good_to_bad_probability"],
        bad_to_good_probability=scenario["bad_to_good_probability"],
        initial_bad_probability=scenario["initial_bad_probability"],
        repair_cost=scenario["repair_cost"],
        fixed_intervals=scenario["fixed_interval_candidates"],
    )
    if rebuilt != dict(report):
        raise AdaptiveRepairError("adaptive repair report differs from independent source-parameter reconstruction")
    return dict(report)


def simulate_adaptive_policy(
    report: Mapping[str, Any],
    *,
    trials: int,
    seed: int = 0,
) -> Dict[str, Any]:
    """Seeded implementation check for the selected deterministic state policy."""
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise AdaptiveRepairError("trials must be a positive integer")
    scenario = report["scenario"]
    policy = report["adaptive_policy"]["decision_table"]
    slots = scenario["slots"]
    threshold = scenario["recovery_threshold"]
    horizon = scenario["horizon"]
    p_good = scenario["good_loss_probability"]
    p_bad = scenario["bad_loss_probability"]
    alpha = scenario["good_to_bad_probability"]
    beta = scenario["bad_to_good_probability"]
    initial_bad = scenario["initial_bad_probability"]
    rng = random.Random(seed)
    successes = 0
    total_repairs = 0
    for _ in range(trials):
        live = slots
        state = 1 if rng.random() < initial_bad else 0
        for time_index in range(horizon):
            if live < threshold:
                break
            if live < slots:
                # Decision table is ordered by time, live count, then G/B.
                row_index = time_index * (slots - threshold + 1) * 2 + (live - threshold) * 2 + state
                action = policy[row_index]["selected_action"]
                if action == "repair":
                    live = slots
                    total_repairs += 1
            loss_probability = p_bad if state else p_good
            for _packet in range(live):
                if rng.random() < loss_probability:
                    live -= 1
            if state == 0:
                state = 1 if rng.random() < alpha else 0
            else:
                state = 0 if rng.random() < beta else 1
        if live >= threshold:
            successes += 1
    return {
        "trials": trials,
        "seed": seed,
        "survival_probability_estimate": successes / trials,
        "expected_repair_count_estimate": total_repairs / trials,
    }


DEFAULT_SCENARIOS = (
    {
        "scenario_name": "moderate_bursts",
        "slots": 8,
        "good_loss_probability": 0.01,
        "bad_loss_probability": 0.40,
        "good_to_bad_probability": 0.08,
        "bad_to_good_probability": 0.25,
        "initial_bad_probability": 0.08 / 0.33,
        "horizon": 16,
        "recovery_thresholds": (1, 4, 8),
        "repair_costs": (0.0, 0.02, 0.05, 0.10, 0.20, 0.50, 0.90, 1.0),
        "fixed_intervals": (1, 2, 4, 8, 16),
    },
    {
        "scenario_name": "rare_persistent_bursts",
        "slots": 8,
        "good_loss_probability": 0.001,
        "bad_loss_probability": 0.70,
        "good_to_bad_probability": 0.02,
        "bad_to_good_probability": 0.08,
        "initial_bad_probability": 0.20,
        "horizon": 16,
        "recovery_thresholds": (1, 4, 8),
        "repair_costs": (0.0, 0.02, 0.05, 0.10, 0.20, 0.50, 0.90, 1.0),
        "fixed_intervals": (1, 2, 4, 8, 16),
    },
)


def build_adaptive_repair_sweep(
    *,
    scenario_name: str,
    slots: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    horizon: int,
    recovery_thresholds: Sequence[int],
    repair_costs: Sequence[float],
    fixed_intervals: Sequence[int],
    simulation_trials: Optional[int] = None,
    simulation_seed: int = 0,
) -> Dict[str, Any]:
    if not isinstance(recovery_thresholds, (tuple, list)) or not recovery_thresholds:
        raise AdaptiveRepairError("recovery_thresholds must be non-empty")
    if not isinstance(repair_costs, (tuple, list)) or not repair_costs:
        raise AdaptiveRepairError("repair_costs must be non-empty")
    thresholds = sorted(set(_positive_int(k, "recovery_threshold", slots) for k in recovery_thresholds))
    costs = sorted(set(_nonnegative_finite(value, "repair_cost") for value in repair_costs))
    reports = []
    for threshold in thresholds:
        for cost_index, cost in enumerate(costs):
            report = build_adaptive_repair_report(
                scenario_name=scenario_name,
                slots=slots,
                recovery_threshold=threshold,
                horizon=horizon,
                good_loss_probability=good_loss_probability,
                bad_loss_probability=bad_loss_probability,
                good_to_bad_probability=good_to_bad_probability,
                bad_to_good_probability=bad_to_good_probability,
                initial_bad_probability=initial_bad_probability,
                repair_cost=cost,
                fixed_intervals=fixed_intervals,
            )
            if simulation_trials is not None:
                report["adaptive_policy"]["simulation"] = simulate_adaptive_policy(
                    report,
                    trials=simulation_trials,
                    seed=simulation_seed + threshold * 100 + cost_index,
                )
            reports.append(report)
    core = {
        "format": "in-formation.adaptive-repair-sweep",
        "schema": "in-formation.adaptive-repair-sweep/0.1",
        "scenario": {
            "name": scenario_name,
            "slots": slots,
            "good_loss_probability": good_loss_probability,
            "bad_loss_probability": bad_loss_probability,
            "good_to_bad_probability": good_to_bad_probability,
            "bad_to_good_probability": bad_to_good_probability,
            "initial_bad_probability": initial_bad_probability,
            "horizon": horizon,
            "recovery_thresholds": thresholds,
            "repair_costs": costs,
            "fixed_intervals": list(fixed_intervals),
        },
        "policy_count": len(reports),
        "policies": reports,
        "interpretation_limits": [
            "All state and parameter assumptions are supplied model inputs; no live sensor or network data is used.",
            "The controller receives exact survivor count and shared channel state at zero sensing cost.",
            "Repair is instant and leaves the shared channel state unchanged.",
            "Expected utility is survival probability minus repair_cost times expected repair count.",
            "The best fixed schedule is restricted to the declared fixed_intervals, including the no-repair H+1 candidate.",
            "The dynamic programme is exact for this finite, fully observed, shared-channel model; it is not a deployed controller.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_adaptive_repair_sweep(report: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, Mapping):
        raise AdaptiveRepairError("sweep report must be a mapping")
    supplied = copy.deepcopy(dict(report))
    digest_value = supplied.pop("report_digest", None)
    if digest_value != _digest(supplied):
        raise AdaptiveRepairError("adaptive repair sweep digest mismatch")
    scenario = supplied.get("scenario")
    if not isinstance(scenario, Mapping):
        raise AdaptiveRepairError("sweep scenario is missing")
    rebuilt = build_adaptive_repair_sweep(
        scenario_name=scenario["name"],
        slots=scenario["slots"],
        good_loss_probability=scenario["good_loss_probability"],
        bad_loss_probability=scenario["bad_loss_probability"],
        good_to_bad_probability=scenario["good_to_bad_probability"],
        bad_to_good_probability=scenario["bad_to_good_probability"],
        initial_bad_probability=scenario["initial_bad_probability"],
        horizon=scenario["horizon"],
        recovery_thresholds=scenario["recovery_thresholds"],
        repair_costs=scenario["repair_costs"],
        fixed_intervals=scenario["fixed_intervals"],
        simulation_trials=None,
    )
    # Simulation outcomes are stochastic attachments, not reconstructed facts.
    supplied_policies = supplied["policies"]
    rebuilt_policies = rebuilt["policies"]
    if len(supplied_policies) != len(rebuilt_policies):
        raise AdaptiveRepairError("adaptive repair sweep policy count differs from reconstruction")
    for actual, expected in zip(supplied_policies, rebuilt_policies):
        actual["adaptive_policy"].pop("simulation", None)
        if actual != expected:
            raise AdaptiveRepairError("adaptive repair sweep differs from reconstruction from source parameters")
    for key in ("format", "schema", "scenario", "policy_count", "interpretation_limits"):
        if supplied.get(key) != rebuilt.get(key):
            raise AdaptiveRepairError(f"adaptive repair sweep {key} differs from reconstruction")
    return dict(report)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optimize finite-horizon repair under observed shared-channel state.")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--slots", type=int, default=8)
    parser.add_argument("--thresholds", default="1,4,8")
    parser.add_argument("--repair-costs", default="0,0.02,0.05,0.1,0.2,0.5,0.9,1.0")
    parser.add_argument("--good-loss", type=float, default=0.01)
    parser.add_argument("--bad-loss", type=float, default=0.4)
    parser.add_argument("--good-to-bad", type=float, default=0.08)
    parser.add_argument("--bad-to-good", type=float, default=0.25)
    parser.add_argument("--initial-bad", type=float, default=0.08 / 0.33)
    parser.add_argument("--horizon", type=int, default=16)
    parser.add_argument("--fixed-intervals", default="1,2,4,8,16")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--trials", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def _parse_ints(value: str, label: str) -> List[int]:
    try:
        entries = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as error:
        raise AdaptiveRepairError(f"{label} must be comma-separated integers") from error
    if not entries:
        raise AdaptiveRepairError(f"{label} must be non-empty")
    return entries


def _parse_floats(value: str, label: str) -> List[float]:
    try:
        entries = [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as error:
        raise AdaptiveRepairError(f"{label} must be comma-separated numbers") from error
    if not entries:
        raise AdaptiveRepairError(f"{label} must be non-empty")
    return entries


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.scan:
            reports = [
                build_adaptive_repair_sweep(
                    **scenario,
                    simulation_trials=args.trials if args.simulate else None,
                    simulation_seed=args.seed + index * 10000,
                )
                for index, scenario in enumerate(DEFAULT_SCENARIOS)
            ]
        else:
            reports = [build_adaptive_repair_sweep(
                scenario_name="custom",
                slots=args.slots,
                good_loss_probability=args.good_loss,
                bad_loss_probability=args.bad_loss,
                good_to_bad_probability=args.good_to_bad,
                bad_to_good_probability=args.bad_to_good,
                initial_bad_probability=args.initial_bad,
                horizon=args.horizon,
                recovery_thresholds=_parse_ints(args.thresholds, "thresholds"),
                repair_costs=_parse_floats(args.repair_costs, "repair-costs"),
                fixed_intervals=_parse_ints(args.fixed_intervals, "fixed-intervals"),
                simulation_trials=args.trials if args.simulate else None,
                simulation_seed=args.seed,
            )]
        if args.json:
            rendered = json.dumps(reports, indent=2, sort_keys=True, allow_nan=False)
        else:
            lines = [
                "scenario | k | repair_cost | adaptive_survival | adaptive_repairs | adaptive_utility | best_fixed_L | fixed_utility | utility_gain"
            ]
            for sweep in reports:
                for report in sweep["policies"]:
                    adaptive = report["adaptive_policy"]
                    fixed = report["best_fixed_schedule"]
                    lines.append(
                        f"{report['scenario']['name']} | {report['scenario']['recovery_threshold']} | "
                        f"{report['scenario']['repair_cost']} | {adaptive['survival_probability']:.6g} | "
                        f"{adaptive['expected_repair_count']:.6g} | {adaptive['expected_utility']:.6g} | "
                        f"{fixed['interval_rounds']} | {fixed['expected_utility']:.6g} | "
                        f"{report['adaptive_gain_over_best_fixed']:.6g}"
                    )
            rendered = "\n".join(lines)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {args.output}")
        else:
            print(rendered)
        return 0
    except (ArithmeticError, OSError, AdaptiveRepairError, TypeError, ValueError, KeyError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
