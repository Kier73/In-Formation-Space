#!/usr/bin/env python3
"""MRE-004: finite-horizon repair with hidden channel state and optional sensing.

The channel is a two-state Markov chain. The controller knows the current
surviving-packet count, but not the channel state. It maintains an exact
posterior probability that the channel is bad. Before each circulation it may
pay for a binary noisy sensor reading, then choose WAIT or REPAIR. Repair
reconstructs all packets but does not reset the hidden channel state.

All probabilities and costs are represented as fractions. The objective is
terminal survival probability minus repair_cost * expected repairs minus
sensing_cost * expected readings. This is a finite, synthetic decision model,
not a measured controller or network reliability prediction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from functools import lru_cache
from math import comb
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

MAX_SLOTS = 8
MAX_HORIZON = 5
MAX_BELIEF_NODES = 50_000


class BeliefRepairError(ValueError):
    """Invalid belief-repair model or reconstructed report."""


def _fraction(value: object, label: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Fraction)):
        raise BeliefRepairError(f"{label} must be an integer, decimal, or rational string")
    try:
        result = value if isinstance(value, Fraction) else Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError, OverflowError) as error:
        raise BeliefRepairError(f"{label} is not a valid finite rational") from error
    return result


def _probability(value: object, label: str) -> Fraction:
    result = _fraction(value, label)
    if not 0 <= result <= 1:
        raise BeliefRepairError(f"{label} must be in [0, 1]")
    return result


def _cost(value: object, label: str) -> Fraction:
    result = _fraction(value, label)
    if result < 0:
        raise BeliefRepairError(f"{label} must be non-negative")
    return result


def _positive_int(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise BeliefRepairError(f"{label} must be an integer in [1, {maximum}]")
    return value


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise BeliefRepairError(f"value is not finite canonical JSON: {error}") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _binomial_pmf(trials: int, survive_probability: Fraction) -> Tuple[Fraction, ...]:
    loss_probability = 1 - survive_probability
    return tuple(
        Fraction(comb(trials, survivors))
        * survive_probability ** survivors
        * loss_probability ** (trials - survivors)
        for survivors in range(trials + 1)
    )


@lru_cache(maxsize=128)
def _cached_survivor_pmfs(
    starting_packets: int, good_survival: Fraction, bad_survival: Fraction
) -> Tuple[Tuple[Fraction, ...], Tuple[Fraction, ...]]:
    return (
        _binomial_pmf(starting_packets, good_survival),
        _binomial_pmf(starting_packets, bad_survival),
    )


def _validate_model(
    *,
    slots: int, recovery_threshold: int, horizon: int,
    good_loss_probability: object, bad_loss_probability: object,
    good_to_bad_probability: object, bad_to_good_probability: object,
    initial_bad_probability: object, sensor_sensitivity: object,
    sensor_false_positive_rate: object, repair_cost: object, sensing_cost: object,
) -> Dict[str, Any]:
    n = _positive_int(slots, "slots", MAX_SLOTS)
    k = _positive_int(recovery_threshold, "recovery_threshold", n)
    h = _positive_int(horizon, "horizon", MAX_HORIZON)
    p_good = _probability(good_loss_probability, "good_loss_probability")
    p_bad = _probability(bad_loss_probability, "bad_loss_probability")
    alpha = _probability(good_to_bad_probability, "good_to_bad_probability")
    beta = _probability(bad_to_good_probability, "bad_to_good_probability")
    initial_bad = _probability(initial_bad_probability, "initial_bad_probability")
    sensitivity = _probability(sensor_sensitivity, "sensor_sensitivity")
    false_positive = _probability(sensor_false_positive_rate, "sensor_false_positive_rate")
    repair = _cost(repair_cost, "repair_cost")
    sense = _cost(sensing_cost, "sensing_cost")
    if p_good > p_bad:
        raise BeliefRepairError("good_loss_probability must not exceed bad_loss_probability")
    return {
        "slots": n,
        "recovery_threshold": k,
        "horizon": h,
        "good_loss_probability": p_good,
        "bad_loss_probability": p_bad,
        "good_to_bad_probability": alpha,
        "bad_to_good_probability": beta,
        "initial_bad_probability": initial_bad,
        "sensor_sensitivity": sensitivity,
        "sensor_false_positive_rate": false_positive,
        "repair_cost": repair,
        "sensing_cost": sense,
    }


def _sensor_branches(
    bad_belief: Fraction, model: Mapping[str, Any]
) -> Tuple[Tuple[str, Fraction, Fraction], ...]:
    """Return (signal, signal probability, posterior bad probability)."""
    sensitivity = model["sensor_sensitivity"]
    false_positive = model["sensor_false_positive_rate"]
    bad_signal_probability = (
        bad_belief * sensitivity + (1 - bad_belief) * false_positive
    )
    good_signal_probability = 1 - bad_signal_probability
    branches = []
    if good_signal_probability:
        numerator = bad_belief * (1 - sensitivity)
        branches.append(("good", good_signal_probability,
                         numerator / good_signal_probability))
    if bad_signal_probability:
        numerator = bad_belief * sensitivity
        branches.append(("bad", bad_signal_probability,
                         numerator / bad_signal_probability))
    return tuple(branches)


def _transition_outcomes(
    *,
    starting_packets: int,
    bad_belief: Fraction,
    model: Mapping[str, Any],
) -> Tuple[Tuple[int, Fraction, Fraction], ...]:
    """Return (next survivor count, probability, next bad-state belief).

    The current hidden state governs packet survival. The Markov channel
    transition occurs after loss. Conditioning on the observed survivor count
    therefore updates the posterior for the next channel state.
    """
    pmf_good, pmf_bad = _cached_survivor_pmfs(
        starting_packets,
        1 - model["good_loss_probability"],
        1 - model["bad_loss_probability"],
    )
    alpha = model["good_to_bad_probability"]
    beta = model["bad_to_good_probability"]
    good_prior = 1 - bad_belief
    outcomes = []
    for survivors in range(starting_packets + 1):
        from_good = good_prior * pmf_good[survivors]
        from_bad = bad_belief * pmf_bad[survivors]
        next_good_mass = from_good * (1 - alpha) + from_bad * beta
        next_bad_mass = from_good * alpha + from_bad * (1 - beta)
        probability = next_good_mass + next_bad_mass
        if probability:
            outcomes.append((survivors, probability, next_bad_mass / probability))
    return tuple(outcomes)


def _action_values(
    *,
    time_index: int,
    survivors: int,
    bad_belief: Fraction,
    model: Mapping[str, Any],
    solve: Any,
) -> Tuple[Fraction, str, Fraction, Optional[Fraction]]:
    """Return best value/action plus WAIT and optional REPAIR values."""
    threshold = model["recovery_threshold"]
    slots = model["slots"]
    next_time = time_index + 1

    def continuation(starting_packets: int) -> Fraction:
        terms = []
        for next_survivors, probability, next_belief in _transition_outcomes(
            starting_packets=starting_packets,
            bad_belief=bad_belief,
            model=model,
        ):
            if next_survivors >= threshold:
                terms.append(probability * solve(next_time, next_survivors, next_belief))
        return sum(terms, Fraction(0))

    wait_value = continuation(survivors)
    repair_value: Optional[Fraction] = None
    if survivors < slots:
        repair_value = continuation(slots) - model["repair_cost"]
    if repair_value is not None and repair_value > wait_value:
        return repair_value, "repair", wait_value, repair_value
    return wait_value, "wait", wait_value, repair_value


def _forward_reconstruct(
    *,
    model: Mapping[str, Any],
    policy: Mapping[Tuple[int, int, Fraction], Mapping[str, Any]],
) -> Dict[str, Fraction]:
    """Evaluate the selected policy by forward probability-mass propagation."""
    slots = model["slots"]
    threshold = model["recovery_threshold"]
    horizon = model["horizon"]
    mass: Dict[Tuple[int, Fraction], Fraction] = {
        (slots, model["initial_bad_probability"]): Fraction(1)
    }
    expected_repairs = Fraction(0)
    expected_sensings = Fraction(0)

    for time_index in range(horizon):
        next_mass: Dict[Tuple[int, Fraction], Fraction] = {}
        for (survivors, prior_bad), state_mass in mass.items():
            node = policy[(time_index, survivors, prior_bad)]
            if node["selected_observation_action"] == "sense":
                expected_sensings += state_mass
                selected = [
                    (signal_probability, posterior_bad, node["signal_actions"][signal])
                    for signal, signal_probability, posterior_bad
                    in _sensor_branches(prior_bad, model)
                ]
            else:
                selected = [(Fraction(1), prior_bad, node["skip_action"])]

            for signal_probability, posterior_bad, action in selected:
                branch_mass = state_mass * signal_probability
                starting_packets = slots if action == "repair" else survivors
                if action == "repair":
                    expected_repairs += branch_mass
                for next_survivors, probability, next_belief in _transition_outcomes(
                    starting_packets=starting_packets,
                    bad_belief=posterior_bad,
                    model=model,
                ):
                    if next_survivors < threshold:
                        continue
                    key = (next_survivors, next_belief)
                    next_mass[key] = next_mass.get(key, Fraction(0)) + branch_mass * probability
        mass = next_mass

    survival = sum(mass.values(), Fraction(0))
    utility = (
        survival
        - model["repair_cost"] * expected_repairs
        - model["sensing_cost"] * expected_sensings
    )
    return {
        "survival_probability": survival,
        "expected_repair_count": expected_repairs,
        "expected_sensing_count": expected_sensings,
        "expected_repair_cost": model["repair_cost"] * expected_repairs,
        "expected_sensing_cost": model["sensing_cost"] * expected_sensings,
        "expected_utility": utility,
    }


def build_belief_repair_report(
    *,
    scenario_name: str,
    slots: int,
    recovery_threshold: int,
    horizon: int,
    good_loss_probability: object,
    bad_loss_probability: object,
    good_to_bad_probability: object,
    bad_to_good_probability: object,
    initial_bad_probability: object,
    sensor_sensitivity: object,
    sensor_false_positive_rate: object,
    repair_cost: object,
    sensing_cost: object,
) -> Dict[str, Any]:
    """Solve one exact finite-horizon partially observed repair problem."""
    if not isinstance(scenario_name, str) or not scenario_name.strip():
        raise BeliefRepairError("scenario_name must be a non-empty string")
    model = _validate_model(
        slots=slots,
        recovery_threshold=recovery_threshold,
        horizon=horizon,
        good_loss_probability=good_loss_probability,
        bad_loss_probability=bad_loss_probability,
        good_to_bad_probability=good_to_bad_probability,
        bad_to_good_probability=bad_to_good_probability,
        initial_bad_probability=initial_bad_probability,
        sensor_sensitivity=sensor_sensitivity,
        sensor_false_positive_rate=sensor_false_positive_rate,
        repair_cost=repair_cost,
        sensing_cost=sensing_cost,
    )
    policy: Dict[Tuple[int, int, Fraction], Dict[str, Any]] = {}
    policy_values: Dict[Tuple[int, int, Fraction], Fraction] = {}

    def solve(time_index: int, survivors: int, bad_belief: Fraction) -> Fraction:
        if survivors < model["recovery_threshold"]:
            return Fraction(0)
        if time_index == model["horizon"]:
            return Fraction(1)
        key = (time_index, survivors, bad_belief)
        if key in policy_values:
            return policy_values[key]
        if len(policy) >= MAX_BELIEF_NODES:
            raise BeliefRepairError(
                f"belief-state cap {MAX_BELIEF_NODES} reached; reduce slots or horizon"
            )

        skip_value, skip_action, skip_wait, skip_repair = _action_values(
            time_index=time_index,
            survivors=survivors,
            bad_belief=bad_belief,
            model=model,
            solve=solve,
        )
        sensing_terms = []
        signal_actions: Dict[str, str] = {}
        signal_values: Dict[str, str] = {}
        for signal, signal_probability, posterior_bad in _sensor_branches(bad_belief, model):
            value, action, _wait_value, _repair_value = _action_values(
                time_index=time_index,
                survivors=survivors,
                bad_belief=posterior_bad,
                model=model,
                solve=solve,
            )
            sensing_terms.append(signal_probability * value)
            signal_actions[signal] = action
            signal_values[signal] = _fraction_text(value)
        sense_value = sum(sensing_terms, Fraction(0)) - model["sensing_cost"]
        # Exact ties choose SKIP, avoiding an unnecessary observation.
        selected_observation_action = "sense" if sense_value > skip_value else "skip"
        selected_value = sense_value if selected_observation_action == "sense" else skip_value
        node = {
            "time_index": time_index,
            "surviving_packets": survivors,
            "prior_bad_probability": _fraction_text(bad_belief),
            "selected_observation_action": selected_observation_action,
            "skip_action": skip_action,
            "skip_value": _fraction_text(skip_value),
            "skip_wait_value": _fraction_text(skip_wait),
            "skip_repair_value": None if skip_repair is None else _fraction_text(skip_repair),
            "sense_value_before_cost": _fraction_text(sense_value + model["sensing_cost"]),
            "sense_value_after_cost": _fraction_text(sense_value),
            "signal_actions": signal_actions,
            "signal_values": signal_values,
            "selected_value": _fraction_text(selected_value),
        }
        policy[key] = node
        policy_values[key] = selected_value
        return selected_value

    initial_value = solve(0, model["slots"], model["initial_bad_probability"])
    reconstructed = _forward_reconstruct(model=model, policy=policy)
    if reconstructed["expected_utility"] != initial_value:
        raise ArithmeticError(
            "backward-induction value differs from independent forward reconstruction"
        )

    ordered_nodes = [
        policy[key] for key in sorted(
            policy,
            key=lambda item: (item[0], item[1], item[2].numerator, item[2].denominator),
        )
    ]
    model_document = {
        key: (_fraction_text(value) if isinstance(value, Fraction) else value)
        for key, value in model.items()
    }
    policy_payload = {"model": model_document, "decision_nodes": ordered_nodes}
    policy_digest = _digest(policy_payload)
    return {
        "format": "in-formation.in-transit-belief-repair",
        "schema": "in-formation.in-transit-belief-repair/0.1",
        "experiment_id": "MRE-004",
        "scenario_name": scenario_name,
        "model": model_document,
        "objective": "terminal_survival_probability - repair_cost * expected_repairs - sensing_cost * expected_sensings",
        "controller": {
            "belief_state": "exact posterior probability that the shared channel is bad",
            "decision_node_count": len(ordered_nodes),
            "initial_value_from_backward_induction": _fraction_text(initial_value),
            "policy_digest_sha256": policy_digest,
            "forward_reconstruction": {
                key: _fraction_text(value) for key, value in reconstructed.items()
            },
            "decision_nodes": ordered_nodes,
        },
        "interpretation_limits": [
            "All probabilities and costs are exact rational inputs to a finite synthetic model; they are not fitted to observed network data.",
            "The shared channel state is hidden. The controller observes the surviving-packet count exactly and maintains a posterior over the next channel state.",
            "At each epoch the controller may skip sensing or pay the declared sensing_cost for one binary sensor result.",
            "Sensor sensitivity and false-positive rate are assumed known and stationary; calibration drift and adversarial sensor behavior are excluded.",
            "Repair instantaneously reconstructs all data packets but does not reset or directly observe the hidden channel state.",
            "The channel transition occurs after the current circulation losses; the next belief is conditioned on the observed survivor count.",
            "The objective scalarizes terminal survival, expected repair count, and expected sensing count using caller-declared costs; it is not a universal optimum.",
            "No sensing latency, network transport cost, observation-path failure, multi-host consensus, or physical repair duration is represented.",
            "The state and horizon caps make this a small exact reference model, not a scalable general POMDP solver.",
        ],
    }


def validate_belief_repair_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Rebuild a report from its declared rational model and check exact equality."""
    if not isinstance(report, Mapping) or report.get("format") != "in-formation.in-transit-belief-repair":
        raise BeliefRepairError("unsupported belief-repair report format")
    model = report.get("model")
    if not isinstance(model, Mapping):
        raise BeliefRepairError("report model must be an object")
    rebuilt = build_belief_repair_report(
        scenario_name=report.get("scenario_name"),
        slots=model.get("slots"),
        recovery_threshold=model.get("recovery_threshold"),
        horizon=model.get("horizon"),
        good_loss_probability=model.get("good_loss_probability"),
        bad_loss_probability=model.get("bad_loss_probability"),
        good_to_bad_probability=model.get("good_to_bad_probability"),
        bad_to_good_probability=model.get("bad_to_good_probability"),
        initial_bad_probability=model.get("initial_bad_probability"),
        sensor_sensitivity=model.get("sensor_sensitivity"),
        sensor_false_positive_rate=model.get("sensor_false_positive_rate"),
        repair_cost=model.get("repair_cost"),
        sensing_cost=model.get("sensing_cost"),
    )
    if _canonical(rebuilt) != _canonical(report):
        raise BeliefRepairError("belief-repair report reconstruction mismatch")
    return rebuilt


DEFAULT_SCENARIOS = (
    {
        "scenario_name": "moderate_bursts",
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
    },
    {
        "scenario_name": "persistent_bursts",
        "slots": 5,
        "recovery_threshold": 2,
        "horizon": 4,
        "good_loss_probability": "1/1000",
        "bad_loss_probability": "7/10",
        "good_to_bad_probability": "1/50",
        "bad_to_good_probability": "2/25",
        "initial_bad_probability": "1/5",
        "sensor_sensitivity": "17/20",
        "sensor_false_positive_rate": "1/20",
        "repair_cost": "1/10",
        "sensing_cost": "1/50",
    },
)


def build_default_sweep() -> Dict[str, Any]:
    reports = [build_belief_repair_report(**scenario) for scenario in DEFAULT_SCENARIOS]
    summary = []
    for scenario, report in zip(DEFAULT_SCENARIOS, reports):
        policy = report["controller"]
        forward = policy["forward_reconstruction"]
        no_sensing_scenario = {
            **scenario,
            "sensor_sensitivity": "1/2",
            "sensor_false_positive_rate": "1/2",
            "sensing_cost": "0",
        }
        no_sensing_report = build_belief_repair_report(**no_sensing_scenario)
        no_sensing_utility = no_sensing_report["controller"]["forward_reconstruction"]["expected_utility"]
        utility_gain = (
            Fraction(forward["expected_utility"]) - Fraction(no_sensing_utility)
        )
        summary.append({
            "scenario_name": report["scenario_name"],
            "survival_probability": forward["survival_probability"],
            "expected_repair_count": forward["expected_repair_count"],
            "expected_sensing_count": forward["expected_sensing_count"],
            "expected_utility": forward["expected_utility"],
            "no_sensing_baseline_expected_utility": no_sensing_utility,
            "utility_gain_over_no_sensing": _fraction_text(utility_gain),
            "selected_sense_nodes": sum(
                node["selected_observation_action"] == "sense"
                for node in policy["decision_nodes"]
            ),
            "decision_node_count": policy["decision_node_count"],
            "policy_digest_sha256": policy["policy_digest_sha256"],
        })
    payload = {
        "format": "in-formation.in-transit-belief-repair-sweep",
        "reports": reports,
        "summary": summary,
    }
    payload["sweep_digest_sha256"] = _digest(payload)
    return payload


def summarize_default_sweep(sweep: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a compact receipt while retaining the full policies in the API result."""
    return {
        "format": "in-formation.in-transit-belief-repair-scan-summary",
        "schema": "in-formation.in-transit-belief-repair-scan-summary/0.1",
        "scenario_count": len(sweep["summary"]),
        "summary": sweep["summary"],
        "sweep_digest_sha256": sweep["sweep_digest_sha256"],
        "interpretation_limits": [
            "The digest binds the complete reconstructed reports, including every exact belief-state decision node.",
            "The checked-in summary omits the large decision tables; the source defaults and tests reconstruct them.",
            "All scenarios are finite synthetic models and do not constitute measured network reliability or an empirical sensor calibration.",
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true", help="solve the two declared default scenarios")
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)
    if args.scan:
        result = summarize_default_sweep(build_default_sweep())
    else:
        result = build_belief_repair_report(**DEFAULT_SCENARIOS[0])
    print(_canonical(result) if args.json else json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
