#!/usr/bin/env python3
"""MRE-005: exact repair decisions under delayed, out-of-order, or missing evidence.

The hidden shared channel is represented by its full finite history path so a
late sensor report can condition on the state it actually measured. Reports
carry sequence numbers, measurement epochs, arrival epochs, and delivery
outcomes. A report that arrives late conditions its historical state coordinate
and the current posterior is then recomputed through the retained path; it is
never relabelled as a measurement of the current state.

This is a small exact reference model, not a network measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from functools import lru_cache
from math import comb
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

MAX_SLOTS = 6
MAX_HORIZON = 5
MAX_DECISION_NODES = 100_000


class DelayedEvidenceError(ValueError):
    """Invalid delayed-evidence model, policy, or reconstructed report."""


def _fraction(value: object, label: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Fraction)):
        raise DelayedEvidenceError(f"{label} must be an integer, decimal, or rational string")
    try:
        result = value if isinstance(value, Fraction) else Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError, OverflowError) as error:
        raise DelayedEvidenceError(f"{label} is not a valid finite rational") from error
    return result


def _probability(value: object, label: str) -> Fraction:
    result = _fraction(value, label)
    if not 0 <= result <= 1:
        raise DelayedEvidenceError(f"{label} must be in [0, 1]")
    return result


def _cost(value: object, label: str) -> Fraction:
    result = _fraction(value, label)
    if result < 0:
        raise DelayedEvidenceError(f"{label} must be non-negative")
    return result


def _positive_int(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise DelayedEvidenceError(f"{label} must be an integer in [1, {maximum}]")
    return value


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _decimal_text(value: Fraction) -> str:
    return f"{float(value):.8f}"


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise DelayedEvidenceError(f"value is not finite canonical JSON: {error}") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _belief_key(belief: Mapping[Tuple[int, ...], Fraction]) -> Tuple[Tuple[Tuple[int, ...], int, int], ...]:
    return tuple(
        (path, mass.numerator, mass.denominator)
        for path, mass in sorted(belief.items())
        if mass
    )


def _belief_from_key(
    key: Tuple[Tuple[Tuple[int, ...], int, int], ...]
) -> Dict[Tuple[int, ...], Fraction]:
    return {path: Fraction(numerator, denominator) for path, numerator, denominator in key}


def _belief_digest(belief: Mapping[Tuple[int, ...], Fraction]) -> str:
    return _digest([
        {"channel_path": list(path), "probability": _fraction_text(mass)}
        for path, mass in sorted(belief.items())
        if mass
    ])


def _marginal_bad_probability(
    belief: Mapping[Tuple[int, ...], Fraction], epoch_index: int
) -> Fraction:
    return sum(
        (mass for path, mass in belief.items() if path[epoch_index] == 1),
        Fraction(0),
    )


@lru_cache(maxsize=128)
def _binomial_pmf(trials: int, survive_probability: Fraction) -> Tuple[Fraction, ...]:
    loss_probability = 1 - survive_probability
    return tuple(
        Fraction(comb(trials, survivors))
        * survive_probability ** survivors
        * loss_probability ** (trials - survivors)
        for survivors in range(trials + 1)
    )


def _validate_model(
    *,
    slots: int,
    recovery_threshold: int,
    horizon: int,
    good_loss_probability: object,
    bad_loss_probability: object,
    good_to_bad_probability: object,
    bad_to_good_probability: object,
    initial_bad_probability: object,
    repair_cost: object,
    sensor_reports: object,
) -> Dict[str, Any]:
    n = _positive_int(slots, "slots", MAX_SLOTS)
    threshold = _positive_int(recovery_threshold, "recovery_threshold", n)
    h = _positive_int(horizon, "horizon", MAX_HORIZON)
    p_good = _probability(good_loss_probability, "good_loss_probability")
    p_bad = _probability(bad_loss_probability, "bad_loss_probability")
    alpha = _probability(good_to_bad_probability, "good_to_bad_probability")
    beta = _probability(bad_to_good_probability, "bad_to_good_probability")
    initial_bad = _probability(initial_bad_probability, "initial_bad_probability")
    cost = _cost(repair_cost, "repair_cost")
    if p_good > p_bad:
        raise DelayedEvidenceError("good_loss_probability must not exceed bad_loss_probability")
    if not isinstance(sensor_reports, (list, tuple)):
        raise DelayedEvidenceError("sensor_reports must be a list")

    reports = []
    seen_ids = set()
    seen_sequences = set()
    seen_measurement_epochs = set()
    for index, raw in enumerate(sensor_reports):
        if not isinstance(raw, Mapping):
            raise DelayedEvidenceError(f"sensor_reports[{index}] must be an object")
        message_id = raw.get("message_id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise DelayedEvidenceError(f"sensor_reports[{index}].message_id must be non-empty text")
        sequence = raw.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise DelayedEvidenceError(f"sensor_reports[{index}].sequence must be a positive integer")
        measurement_epoch = raw.get("measurement_epoch")
        arrival_epoch = raw.get("arrival_epoch")
        for value, label in (
            (measurement_epoch, "measurement_epoch"),
            (arrival_epoch, "arrival_epoch"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise DelayedEvidenceError(f"sensor_reports[{index}].{label} must be an integer")
        if not 0 <= measurement_epoch < h:
            raise DelayedEvidenceError(
                f"sensor_reports[{index}].measurement_epoch must be inside the horizon"
            )
        if not measurement_epoch <= arrival_epoch < h:
            raise DelayedEvidenceError(
                f"sensor_reports[{index}].arrival_epoch must be between its measurement epoch and horizon"
            )
        if message_id in seen_ids or sequence in seen_sequences:
            raise DelayedEvidenceError("sensor message IDs and sequence numbers must be unique")
        if measurement_epoch in seen_measurement_epochs:
            raise DelayedEvidenceError("this reference model allows at most one sensor sample per epoch")
        seen_ids.add(message_id)
        seen_sequences.add(sequence)
        seen_measurement_epochs.add(measurement_epoch)
        reports.append({
            "message_id": message_id,
            "sequence": sequence,
            "measurement_epoch": measurement_epoch,
            "arrival_epoch": arrival_epoch,
            "delivery_probability": _probability(
                raw.get("delivery_probability"), f"sensor_reports[{index}].delivery_probability"
            ),
            "sensor_sensitivity": _probability(
                raw.get("sensor_sensitivity"), f"sensor_reports[{index}].sensor_sensitivity"
            ),
            "sensor_false_positive_rate": _probability(
                raw.get("sensor_false_positive_rate"),
                f"sensor_reports[{index}].sensor_false_positive_rate",
            ),
        })

    reports.sort(key=lambda item: item["measurement_epoch"])
    if [item["sequence"] for item in reports] != sorted(item["sequence"] for item in reports):
        raise DelayedEvidenceError(
            "sequence numbers must increase with measurement_epoch; arrival order may differ"
        )
    return {
        "slots": n,
        "recovery_threshold": threshold,
        "horizon": h,
        "good_loss_probability": p_good,
        "bad_loss_probability": p_bad,
        "good_to_bad_probability": alpha,
        "bad_to_good_probability": beta,
        "initial_bad_probability": initial_bad,
        "repair_cost": cost,
        "sensor_reports": tuple(reports),
    }


def _sensor_likelihood(
    signal: str, hidden_state: int, report: Mapping[str, Any]
) -> Fraction:
    sensitivity = report["sensor_sensitivity"]
    false_positive = report["sensor_false_positive_rate"]
    if signal == "bad":
        return sensitivity if hidden_state == 1 else false_positive
    if signal == "good":
        return 1 - sensitivity if hidden_state == 1 else 1 - false_positive
    raise DelayedEvidenceError(f"unsupported sensor signal: {signal}")


def _condition_on_signal(
    belief: Mapping[Tuple[int, ...], Fraction],
    report: Mapping[str, Any],
    signal: str,
) -> Tuple[Fraction, Dict[Tuple[int, ...], Fraction]]:
    measurement_epoch = report["measurement_epoch"]
    weighted = {
        path: mass * _sensor_likelihood(signal, path[measurement_epoch], report)
        for path, mass in belief.items()
    }
    probability = sum(weighted.values(), Fraction(0))
    if probability == 0:
        return Fraction(0), {}
    return probability, {
        path: mass / probability for path, mass in weighted.items() if mass
    }


def _evidence_event(
    *,
    report: Mapping[str, Any],
    arrival_epoch: int,
    status: str,
    signal: Optional[str],
    before: Mapping[Tuple[int, ...], Fraction],
    after: Mapping[Tuple[int, ...], Fraction],
) -> Dict[str, Any]:
    measurement_epoch = report["measurement_epoch"]
    body = {
        "format": "in-formation.delayed-sensor-arrival/0.1",
        "message_id": report["message_id"],
        "sequence": report["sequence"],
        "measurement_epoch": measurement_epoch,
        "arrival_epoch": arrival_epoch,
        "age_epochs": arrival_epoch - measurement_epoch,
        "delivery_status": status,
        "signal": signal,
        "delivery_probability": _fraction_text(report["delivery_probability"]),
        "sensor_sensitivity": _fraction_text(report["sensor_sensitivity"]),
        "sensor_false_positive_rate": _fraction_text(report["sensor_false_positive_rate"]),
        "belief_digest_before": _belief_digest(before),
        "belief_digest_after": _belief_digest(after),
        "measurement_state_bad_probability_before": _fraction_text(
            _marginal_bad_probability(before, measurement_epoch)
        ),
        "measurement_state_bad_probability_after": _fraction_text(
            _marginal_bad_probability(after, measurement_epoch)
        ),
        "current_state_bad_probability_before": _fraction_text(
            _marginal_bad_probability(before, arrival_epoch)
        ),
        "current_state_bad_probability_after": _fraction_text(
            _marginal_bad_probability(after, arrival_epoch)
        ),
    }
    return {**body, "evidence_digest_sha256": _digest(body)}


def _arrival_branches(
    *,
    time_index: int,
    belief: Mapping[Tuple[int, ...], Fraction],
    model: Mapping[str, Any],
) -> Tuple[Tuple[Fraction, Dict[Tuple[int, ...], Fraction], Tuple[str, ...]], ...]:
    """Apply all reports arriving now, preserving their measurement coordinates."""
    branches = [(Fraction(1), dict(belief), ())]
    arriving = [
        report for report in model["sensor_reports"]
        if report["arrival_epoch"] == time_index
    ]
    for report in arriving:
        expanded = []
        delivery = report["delivery_probability"]
        for branch_probability, prior, prior_events in branches:
            if delivery < 1:
                timeout_event = _evidence_event(
                    report=report,
                    arrival_epoch=time_index,
                    status="timeout",
                    signal=None,
                    before=prior,
                    after=prior,
                )
                expanded.append((
                    branch_probability * (1 - delivery),
                    prior,
                    prior_events + (_canonical(timeout_event),),
                ))
            if delivery > 0:
                for signal in ("good", "bad"):
                    signal_probability, posterior = _condition_on_signal(
                        prior, report, signal
                    )
                    if signal_probability == 0:
                        continue
                    event = _evidence_event(
                        report=report,
                        arrival_epoch=time_index,
                        status="delivered",
                        signal=signal,
                        before=prior,
                        after=posterior,
                    )
                    expanded.append((
                        branch_probability * delivery * signal_probability,
                        posterior,
                        prior_events + (_canonical(event),),
                    ))
        branches = expanded
    total = sum((probability for probability, _belief, _events in branches), Fraction(0))
    if total != 1:
        raise ArithmeticError(f"arrival branches at epoch {time_index} sum to {total}, not 1")
    return tuple(branch for branch in branches if branch[0])


def _survivor_branches(
    *,
    starting_packets: int,
    belief: Mapping[Tuple[int, ...], Fraction],
    model: Mapping[str, Any],
) -> Tuple[Tuple[int, Fraction, Dict[Tuple[int, ...], Fraction]], ...]:
    """Propagate hidden channel history through losses and the next Markov step."""
    alpha = model["good_to_bad_probability"]
    beta = model["bad_to_good_probability"]
    transition = ((1 - alpha, alpha), (beta, 1 - beta))
    pmf_good = _binomial_pmf(
        starting_packets, 1 - model["good_loss_probability"]
    )
    pmf_bad = _binomial_pmf(
        starting_packets, 1 - model["bad_loss_probability"]
    )
    raw_by_survivors: Dict[int, Dict[Tuple[int, ...], Fraction]] = {}
    for path, mass in belief.items():
        current_state = path[-1]
        pmf = pmf_good if current_state == 0 else pmf_bad
        for survivors, loss_probability in enumerate(pmf):
            if not loss_probability:
                continue
            for next_state in (0, 1):
                probability = loss_probability * transition[current_state][next_state]
                if not probability:
                    continue
                new_path = path + (next_state,)
                bucket = raw_by_survivors.setdefault(survivors, {})
                bucket[new_path] = bucket.get(new_path, Fraction(0)) + mass * probability

    result = []
    for survivors, raw in sorted(raw_by_survivors.items()):
        probability = sum(raw.values(), Fraction(0))
        posterior = {path: mass / probability for path, mass in raw.items()}
        result.append((survivors, probability, posterior))
    total = sum((probability for _survivors, probability, _belief in result), Fraction(0))
    if total != 1:
        raise ArithmeticError(f"survivor/channel transition branches sum to {total}, not 1")
    return tuple(result)


def _event_documents(history_key: Tuple[str, ...]) -> list[Dict[str, Any]]:
    return [json.loads(item) for item in history_key]


def _decision_id(
    time_index: int,
    survivors: int,
    belief_key: Tuple[Tuple[Tuple[int, ...], int, int], ...],
    history_key: Tuple[str, ...],
) -> str:
    return _digest({
        "time_index": time_index,
        "surviving_packets": survivors,
        "belief": [
            {"channel_path": list(path), "probability": f"{numerator}/{denominator}"}
            for path, numerator, denominator in belief_key
        ],
        "evidence_history": list(history_key),
    })


def _validate_parameters_for_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, Mapping):
        raise DelayedEvidenceError("report must be an object")
    model = report.get("model")
    if not isinstance(model, Mapping):
        raise DelayedEvidenceError("report model must be an object")
    return build_delayed_evidence_report(
        scenario_name=report.get("scenario_name"),
        slots=model.get("slots"),
        recovery_threshold=model.get("recovery_threshold"),
        horizon=model.get("horizon"),
        good_loss_probability=model.get("good_loss_probability"),
        bad_loss_probability=model.get("bad_loss_probability"),
        good_to_bad_probability=model.get("good_to_bad_probability"),
        bad_to_good_probability=model.get("bad_to_good_probability"),
        initial_bad_probability=model.get("initial_bad_probability"),
        repair_cost=model.get("repair_cost"),
        sensor_reports=model.get("sensor_reports"),
    )


def build_delayed_evidence_report(
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
    repair_cost: object,
    sensor_reports: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Optimize repairs when sensor messages can arrive late, out of order, or time out."""
    if not isinstance(scenario_name, str) or not scenario_name.strip():
        raise DelayedEvidenceError("scenario_name must be non-empty text")
    model = _validate_model(
        slots=slots,
        recovery_threshold=recovery_threshold,
        horizon=horizon,
        good_loss_probability=good_loss_probability,
        bad_loss_probability=bad_loss_probability,
        good_to_bad_probability=good_to_bad_probability,
        bad_to_good_probability=bad_to_good_probability,
        initial_bad_probability=initial_bad_probability,
        repair_cost=repair_cost,
        sensor_reports=sensor_reports,
    )
    initial_belief = {
        (0,): 1 - model["initial_bad_probability"],
        (1,): model["initial_bad_probability"],
    }
    initial_key = _belief_key(initial_belief)
    decision_nodes: Dict[str, Dict[str, Any]] = {}

    def continuation_value(
        *,
        time_index: int,
        survivors: int,
        starting_packets: int,
        belief: Mapping[Tuple[int, ...], Fraction],
        evidence_history: Tuple[str, ...],
    ) -> Fraction:
        total = Fraction(0)
        for next_survivors, probability, next_belief in _survivor_branches(
            starting_packets=starting_packets,
            belief=belief,
            model=model,
        ):
            if next_survivors >= model["recovery_threshold"]:
                total += probability * solve(
                    time_index + 1,
                    next_survivors,
                    _belief_key(next_belief),
                    evidence_history,
                )
        return total

    @lru_cache(maxsize=None)
    def solve(
        time_index: int,
        survivors: int,
        prior_belief_key: Tuple[Tuple[Tuple[int, ...], int, int], ...],
        prior_history_key: Tuple[str, ...],
    ) -> Fraction:
        if survivors < model["recovery_threshold"]:
            return Fraction(0)
        if time_index == model["horizon"]:
            return Fraction(1)
        if len(decision_nodes) >= MAX_DECISION_NODES:
            raise DelayedEvidenceError(
                f"decision-node cap {MAX_DECISION_NODES} reached; reduce slots or horizon"
            )

        prior_belief = _belief_from_key(prior_belief_key)
        total_value = Fraction(0)
        for observation_probability, posterior, new_events in _arrival_branches(
            time_index=time_index,
            belief=prior_belief,
            model=model,
        ):
            history_key = prior_history_key + new_events
            posterior_key = _belief_key(posterior)
            wait_value = continuation_value(
                time_index=time_index,
                survivors=survivors,
                starting_packets=survivors,
                belief=posterior,
                evidence_history=history_key,
            )
            repair_value: Optional[Fraction] = None
            if survivors < model["slots"]:
                repair_value = (
                    continuation_value(
                        time_index=time_index,
                        survivors=survivors,
                        starting_packets=model["slots"],
                        belief=posterior,
                        evidence_history=history_key,
                    )
                    - model["repair_cost"]
                )
            if repair_value is not None and repair_value > wait_value:
                selected_action = "repair"
                selected_value = repair_value
            else:
                selected_action = "wait"
                selected_value = wait_value

            node_id = _decision_id(
                time_index, survivors, posterior_key, history_key
            )
            node = {
                "decision_id": node_id,
                "time_index": time_index,
                "surviving_packets": survivors,
                "current_bad_probability": _fraction_text(
                    _marginal_bad_probability(posterior, time_index)
                ),
                "belief_digest_sha256": _belief_digest(posterior),
                "evidence_history": _event_documents(history_key),
                "evidence_history_digest_sha256": _digest(list(history_key)),
                "wait_value": _fraction_text(wait_value),
                "repair_value": (
                    None if repair_value is None else _fraction_text(repair_value)
                ),
                "selected_action": selected_action,
                "selected_value": _fraction_text(selected_value),
            }
            decision_nodes[node_id] = node
            total_value += observation_probability * selected_value
        return total_value

    initial_value = solve(0, model["slots"], initial_key, ())
    ordered_nodes = sorted(
        decision_nodes.values(),
        key=lambda item: (
            item["time_index"],
            item["surviving_packets"],
            item["belief_digest_sha256"],
            item["evidence_history_digest_sha256"],
        ),
    )

    # Independent forward policy evaluation over probability mass. It follows
    # the retained decisions and rebuilds each arrival and transition branch.
    forward_mass: Dict[
        Tuple[int, Tuple[Tuple[Tuple[int, ...], int, int], ...], Tuple[str, ...]],
        Fraction,
    ] = {(model["slots"], initial_key, ()): Fraction(1)}
    expected_repairs = Fraction(0)
    expected_deliveries = Fraction(0)
    expected_timeouts = Fraction(0)
    expected_late_deliveries = Fraction(0)
    expected_out_of_order_deliveries = Fraction(0)

    for time_index in range(model["horizon"]):
        next_mass: Dict[
            Tuple[int, Tuple[Tuple[Tuple[int, ...], int, int], ...], Tuple[str, ...]],
            Fraction,
        ] = {}
        for (survivors, prior_key, prior_history), state_mass in forward_mass.items():
            prior_belief = _belief_from_key(prior_key)
            for observation_probability, posterior, new_events in _arrival_branches(
                time_index=time_index,
                belief=prior_belief,
                model=model,
            ):
                history_key = prior_history + new_events
                posterior_key = _belief_key(posterior)
                node_id = _decision_id(
                    time_index, survivors, posterior_key, history_key
                )
                try:
                    action = decision_nodes[node_id]["selected_action"]
                except KeyError as error:
                    raise ArithmeticError("forward pass reached an unrecorded decision node") from error

                branch_mass = state_mass * observation_probability
                if action == "repair":
                    expected_repairs += branch_mass
                previous_sequences = [
                    event["sequence"]
                    for event in _event_documents(prior_history)
                    if event["delivery_status"] == "delivered"
                ]
                highest_previous_sequence = max(previous_sequences, default=0)
                for event_text in new_events:
                    event = json.loads(event_text)
                    if event["delivery_status"] == "delivered":
                        expected_deliveries += branch_mass
                        if event["age_epochs"] > 0:
                            expected_late_deliveries += branch_mass
                        if event["sequence"] < highest_previous_sequence:
                            expected_out_of_order_deliveries += branch_mass
                        highest_previous_sequence = max(
                            highest_previous_sequence, event["sequence"]
                        )
                    else:
                        expected_timeouts += branch_mass

                starting_packets = model["slots"] if action == "repair" else survivors
                for next_survivors, transition_probability, next_belief in _survivor_branches(
                    starting_packets=starting_packets,
                    belief=posterior,
                    model=model,
                ):
                    if next_survivors < model["recovery_threshold"]:
                        continue
                    next_key = (
                        next_survivors,
                        _belief_key(next_belief),
                        history_key,
                    )
                    next_mass[next_key] = (
                        next_mass.get(next_key, Fraction(0))
                        + branch_mass * transition_probability
                    )
        forward_mass = next_mass

    survival_probability = sum(forward_mass.values(), Fraction(0))
    expected_utility = survival_probability - model["repair_cost"] * expected_repairs
    forward = {
        "survival_probability": survival_probability,
        "expected_repair_count": expected_repairs,
        "expected_delivered_report_count": expected_deliveries,
        "expected_timeout_report_count": expected_timeouts,
        "expected_late_report_count": expected_late_deliveries,
        "expected_out_of_order_delivery_count": expected_out_of_order_deliveries,
        "expected_repair_cost": model["repair_cost"] * expected_repairs,
        "expected_utility": expected_utility,
    }
    if expected_utility != initial_value:
        raise ArithmeticError(
            "backward-induction value differs from independent forward policy reconstruction"
        )

    model_document = {
        key: (
            _fraction_text(value)
            if isinstance(value, Fraction)
            else [
                {
                    report_key: (
                        _fraction_text(report_value)
                        if isinstance(report_value, Fraction)
                        else report_value
                    )
                    for report_key, report_value in report.items()
                }
                for report in value
            ]
            if key == "sensor_reports"
            else value
        )
        for key, value in model.items()
    }
    policy_payload = {"model": model_document, "decision_nodes": ordered_nodes}
    return {
        "format": "in-formation.in-transit-delayed-evidence-repair",
        "schema": "in-formation.in-transit-delayed-evidence-repair/0.1",
        "experiment_id": "MRE-005",
        "scenario_name": scenario_name,
        "model": model_document,
        "objective": "terminal_survival_probability - repair_cost * expected_repair_count",
        "controller": {
            "belief_state": "exact posterior over the retained hidden channel-state path",
            "decision_node_count": len(ordered_nodes),
            "initial_value_from_backward_induction": _fraction_text(initial_value),
            "policy_digest_sha256": _digest(policy_payload),
            "forward_reconstruction": {
                key: _fraction_text(value) for key, value in forward.items()
            },
            "decision_nodes": ordered_nodes,
        },
        "interpretation_limits": [
            "All channel, sensor, and delivery probabilities are exact rational inputs to small synthetic finite models; they are not fitted to observed network data.",
            "The hidden shared channel follows a two-state Markov chain; packet losses occur in the current state and the channel transitions after those losses.",
            "The controller observes the surviving-packet count exactly. Delayed sensor messages condition the historical channel state at measurement_epoch, not the current state at arrival_epoch.",
            "Sequence numbers increase with measurement epochs. Arrival order can differ; the retained evidence history records both coordinates and the age in logical epochs.",
            "A timeout means the message did not arrive by its declared arrival epoch. The model does not infer whether a real transport would deliver it later.",
            "Delivery loss is independent of the hidden channel and sensor signal. Sensor errors are conditionally independent given the measured channel state.",
            "The controller retains the full hidden-state path posterior. This exact reference representation grows exponentially with horizon and is not a scalable general POMDP solver.",
            "The model uses logical epoch indices, not wall clocks or cross-host clock comparisons. It does not model clock uncertainty, transport latency distributions, or physical time.",
            "No network authentication, quorum, observation-path authorization, telemetry cost, calibration drift, adversarial message, or E-CPU deployment is represented.",
            "Repair instantly reconstructs all packets but does not reset or reveal the hidden channel state.",
        ],
    }


def validate_delayed_evidence_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Rebuild the complete policy and exact forward receipt from declared inputs."""
    if report.get("format") != "in-formation.in-transit-delayed-evidence-repair":
        raise DelayedEvidenceError("unsupported delayed-evidence report format")
    rebuilt = _validate_parameters_for_report(report)
    if _canonical(rebuilt) != _canonical(report):
        raise DelayedEvidenceError("delayed-evidence report reconstruction mismatch")
    return rebuilt


_COMMON_SCENARIO = {
    "slots": 4,
    "recovery_threshold": 2,
    "horizon": 3,
    "good_loss_probability": "1/100",
    "bad_loss_probability": "9/20",
    "good_to_bad_probability": "3/25",
    "bad_to_good_probability": "3/10",
    "initial_bad_probability": "1/5",
    "repair_cost": "1/20",
}
_SENSOR_QUALITY = {
    "delivery_probability": "4/5",
    "sensor_sensitivity": "4/5",
    "sensor_false_positive_rate": "1/10",
}


def _sensor_report(
    sequence: int,
    measurement_epoch: int,
    arrival_epoch: int,
    *,
    delivery_probability: str = "4/5",
) -> Dict[str, Any]:
    return {
        "message_id": f"channel-sample-{sequence}",
        "sequence": sequence,
        "measurement_epoch": measurement_epoch,
        "arrival_epoch": arrival_epoch,
        **_SENSOR_QUALITY,
        "delivery_probability": delivery_probability,
    }


DEFAULT_SCENARIOS = (
    {
        **_COMMON_SCENARIO,
        "scenario_name": "no_reports",
        "sensor_reports": [],
    },
    {
        **_COMMON_SCENARIO,
        "scenario_name": "in_order_delivery",
        "sensor_reports": [
            _sensor_report(1, 0, 1),
            _sensor_report(2, 1, 2),
        ],
    },
    {
        **_COMMON_SCENARIO,
        "scenario_name": "out_of_order_delivery",
        "sensor_reports": [
            _sensor_report(1, 0, 2),
            _sensor_report(2, 1, 1),
        ],
    },
    {
        **_COMMON_SCENARIO,
        "scenario_name": "older_report_times_out",
        "sensor_reports": [
            _sensor_report(1, 0, 2, delivery_probability="0"),
            _sensor_report(2, 1, 1),
        ],
    },
)


def build_default_sweep() -> Dict[str, Any]:
    reports = [
        build_delayed_evidence_report(**scenario)
        for scenario in DEFAULT_SCENARIOS
    ]
    baseline = reports[0]["controller"]["forward_reconstruction"]
    baseline_utility = Fraction(baseline["expected_utility"])
    summary = []
    for report in reports:
        controller = report["controller"]
        forward = controller["forward_reconstruction"]
        utility = Fraction(forward["expected_utility"])
        summary.append({
            "scenario_name": report["scenario_name"],
            "survival_probability": _decimal_text(
                Fraction(forward["survival_probability"])
            ),
            "expected_repair_count": _decimal_text(
                Fraction(forward["expected_repair_count"])
            ),
            "expected_delivered_report_count": _decimal_text(
                Fraction(forward["expected_delivered_report_count"])
            ),
            "expected_timeout_report_count": _decimal_text(
                Fraction(forward["expected_timeout_report_count"])
            ),
            "expected_late_report_count": _decimal_text(
                Fraction(forward["expected_late_report_count"])
            ),
            "expected_out_of_order_delivery_count": _decimal_text(
                Fraction(forward["expected_out_of_order_delivery_count"])
            ),
            "expected_utility": _decimal_text(utility),
            "utility_delta_vs_no_reports": _decimal_text(utility - baseline_utility),
            "decision_node_count": controller["decision_node_count"],
            "policy_digest_sha256": controller["policy_digest_sha256"],
        })
    payload = {
        "format": "in-formation.in-transit-delayed-evidence-sweep",
        "schema": "in-formation.in-transit-delayed-evidence-sweep/0.1",
        "reports": reports,
        "summary": summary,
    }
    payload["sweep_digest_sha256"] = _digest(payload)
    return payload


def summarize_default_sweep(sweep: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "format": "in-formation.in-transit-delayed-evidence-scan-summary",
        "schema": "in-formation.in-transit-delayed-evidence-scan-summary/0.1",
        "scenario_count": len(sweep["summary"]),
        "summary": sweep["summary"],
        "sweep_digest_sha256": sweep["sweep_digest_sha256"],
        "interpretation_limits": [
            "The sweep digest binds the full exact policy tables and forward reconstructions for all four delivery schedules.",
            "The summary metrics are rounded to eight decimal places for readability; exact rational values remain in each full report.",
            "All scenarios are synthetic, with a four-packet block and a three-circulation horizon. They are not empirical network reliability estimates.",
            "The no_reports row is the baseline. In-order, out-of-order, and timeout schedules use the same channel and repair costs.",
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true", help="solve the four declared delivery schedules")
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)
    if args.scan:
        result = summarize_default_sweep(build_default_sweep())
    else:
        result = build_delayed_evidence_report(**DEFAULT_SCENARIOS[2])
    print(_canonical(result) if args.json else json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
