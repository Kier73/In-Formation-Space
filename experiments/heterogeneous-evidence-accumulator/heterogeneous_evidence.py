"""Exact Bayesian accumulator for a schedule of heterogeneous binary sensors."""
from __future__ import annotations

import hashlib
import itertools
import json
from fractions import Fraction
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.heterogeneous-evidence-accumulator/0.1"


class HistoryLimitError(ValueError):
    """Raised when exhaustive ordered-history verification exceeds its cap."""


def _fraction(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{label} must be an exact rational; floats and booleans are rejected")
    try:
        if isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
            numerator, denominator = value["numerator"], value["denominator"]
            if isinstance(numerator, bool) or not isinstance(numerator, int):
                raise ValueError
            if isinstance(denominator, bool) or not isinstance(denominator, int) or denominator <= 0:
                raise ValueError
            result = Fraction(numerator, denominator)
        else:
            result = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"{label} must be an exact rational") from exc
    if result < 0 or result > 1:
        raise ValueError(f"{label} must be in [0, 1]")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_sensors(sensors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(sensors, (tuple, list)) or not sensors:
        raise ValueError("sensors must be a non-empty sequence")
    result, seen = [], set()
    required = {
        "sensor_id", "p_signal_a_given_hypothesis_a", "p_signal_a_given_hypothesis_b"
    }
    for item in sensors:
        if not isinstance(item, Mapping) or set(item) != required:
            raise ValueError("each sensor needs exactly sensor_id and both conditional A-signal probabilities")
        sensor_id = _text(item["sensor_id"], "sensor_id")
        if sensor_id in seen:
            raise ValueError(f"duplicate sensor_id: {sensor_id}")
        seen.add(sensor_id)
        result.append({
            "sensor_id": sensor_id,
            "p_signal_a_given_hypothesis_a": _doc(_fraction(
                item["p_signal_a_given_hypothesis_a"], f"{sensor_id}.p_signal_a_given_hypothesis_a"
            )),
            "p_signal_a_given_hypothesis_b": _doc(_fraction(
                item["p_signal_a_given_hypothesis_b"], f"{sensor_id}.p_signal_a_given_hypothesis_b"
            )),
        })
    return result


def _posterior_update(posterior_a: Fraction, sensor: Mapping[str, Any], signal: str) -> Fraction | None:
    alpha = Fraction(**sensor["p_signal_a_given_hypothesis_a"])
    beta = Fraction(**sensor["p_signal_a_given_hypothesis_b"])
    likelihood_a = alpha if signal == "A" else 1 - alpha
    likelihood_b = beta if signal == "A" else 1 - beta
    normalizer = posterior_a * likelihood_a + (1 - posterior_a) * likelihood_b
    if normalizer == 0:
        return None
    return posterior_a * likelihood_a / normalizer


def _history_mass(history: Sequence[str], sensors: Sequence[Mapping[str, Any]], prior_a: Fraction):
    mass_a, mass_b = prior_a, 1 - prior_a
    for signal, sensor in zip(history, sensors):
        alpha = Fraction(**sensor["p_signal_a_given_hypothesis_a"])
        beta = Fraction(**sensor["p_signal_a_given_hypothesis_b"])
        mass_a *= alpha if signal == "A" else 1 - alpha
        mass_b *= beta if signal == "A" else 1 - beta
    return mass_a, mass_b


def _history_digest_classes(sensors, prior_a, max_histories):
    n = len(sensors)
    count = 2 ** n
    if count > max_histories:
        raise HistoryLimitError(f"raw-history verification needs {count} strings; cap is {max_histories}")
    posterior_groups: dict[Fraction | None, list[str]] = {}
    count_groups: dict[int, dict[Fraction | None, list[str]]] = {}
    raw_accuracy = Fraction(0)
    raw_rows = []
    for history_tuple in itertools.product(("A", "B"), repeat=n):
        history = "".join(history_tuple)
        mass_a, mass_b = _history_mass(history_tuple, sensors, prior_a)
        normalizer = mass_a + mass_b
        posterior = None if normalizer == 0 else mass_a / normalizer
        decision = "unreachable" if posterior is None else ("A" if mass_a >= mass_b else "B")
        if posterior is not None:
            raw_accuracy += max(mass_a, mass_b)
        posterior_groups.setdefault(posterior, []).append(history)
        count_groups.setdefault(history.count("A"), {}).setdefault(posterior, []).append(history)
        raw_rows.append({
            "history": history,
            "count_A": history.count("A"),
            "posterior_A": None if posterior is None else _doc(posterior),
            "map_decision": decision,
            "joint_mass_if_A": _doc(mass_a),
            "joint_mass_if_B": _doc(mass_b),
        })
    grouped = []
    for posterior, histories in sorted(posterior_groups.items(), key=lambda pair: (-1 if pair[0] is None else pair[0])):
        if posterior is None:
            decision = "unreachable"
        else:
            decision = "A" if posterior >= Fraction(1, 2) else "B"
        grouped.append({
            "posterior_A": None if posterior is None else _doc(posterior),
            "map_decision": decision,
            "histories": sorted(histories),
            "history_count": len(histories),
        })
    count_diagnostics = []
    count_sufficient_for_posterior = True
    count_sufficient_for_map = True
    for count_a, posterior_map in sorted(count_groups.items()):
        reachable = [posterior for posterior in posterior_map if posterior is not None]
        posteriors = sorted(set(reachable))
        map_decisions = sorted({"A" if posterior >= Fraction(1, 2) else "B" for posterior in posteriors})
        if len(posteriors) > 1:
            count_sufficient_for_posterior = False
        if len(map_decisions) > 1:
            count_sufficient_for_map = False
        count_diagnostics.append({
            "count_A": count_a,
            "history_count": sum(len(items) for items in posterior_map.values()),
            "distinct_reachable_posteriors": [_doc(posterior) for posterior in posteriors],
            "distinct_map_decisions": map_decisions,
            "count_is_posterior_sufficient_here": len(posteriors) <= 1,
            "count_preserves_map_decision_here": len(map_decisions) <= 1,
        })
    return {
        "raw_history_count": count,
        "raw_history_accuracy": raw_accuracy,
        "raw_history_rows": raw_rows,
        "posterior_groups": grouped,
        "posterior_state_count": sum(posterior is not None for posterior in posterior_groups),
        "unreachable_history_count": len(posterior_groups.get(None, [])),
        "count_A_class_count": n + 1,
        "count_A_sufficient_for_posterior": count_sufficient_for_posterior,
        "count_A_sufficient_for_map_decision": count_sufficient_for_map,
        "count_A_diagnostics": count_diagnostics,
    }


def _accumulator_layers(sensors, prior_a):
    current_states = {prior_a}
    layers = [{"step": 0, "sensor_id": "before_first_observation", "posterior_states": [_doc(prior_a)]}]
    transitions = []
    for index, sensor in enumerate(sensors):
        step_transitions = []
        following_states = set()
        for posterior in sorted(current_states):
            target_a = _posterior_update(posterior, sensor, "A")
            target_b = _posterior_update(posterior, sensor, "B")
            if target_a is not None:
                following_states.add(target_a)
            if target_b is not None:
                following_states.add(target_b)
            step_transitions.append({
                "posterior_before": _doc(posterior),
                "on_signal_A": None if target_a is None else _doc(target_a),
                "on_signal_B": None if target_b is None else _doc(target_b),
            })
        transitions.append({
            "step": index + 1,
            "sensor_id": sensor["sensor_id"],
            "transitions": step_transitions,
        })
        current_states = following_states
        layers.append({
            "step": index + 1,
            "sensor_id": sensor["sensor_id"],
            "posterior_states": [_doc(posterior) for posterior in sorted(current_states)],
        })
    return layers, transitions


def build_report(*, prior_hypothesis_a: Any, sensors: Sequence[Mapping[str, Any]],
                 max_histories: int = 1_000_000) -> dict[str, Any]:
    """Compare a posterior accumulator with every ordered history.

    Sensors are conditionally independent given the fixed hidden hypothesis but
    may have different, position-specific response probabilities. The stream
    supplies the scheduled sensor identity with each signal. The accumulator
    stores the exact posterior P(H=A | observations so far).
    """
    prior_a = _fraction(prior_hypothesis_a, "prior_hypothesis_a")
    if isinstance(max_histories, bool) or not isinstance(max_histories, int) or max_histories < 1:
        raise ValueError("max_histories must be a positive integer")
    normalized_sensors = _normalize_sensors(sensors)
    histories = _history_digest_classes(normalized_sensors, prior_a, max_histories)
    layers, transitions = _accumulator_layers(normalized_sensors, prior_a)
    terminal_states = {
        (row["posterior_A"]["numerator"], row["posterior_A"]["denominator"])
        for row in histories["raw_history_rows"] if row["posterior_A"] is not None
    }
    accumulated_terminal = {
        (value["numerator"], value["denominator"])
        for value in layers[-1]["posterior_states"]
    }
    if terminal_states != accumulated_terminal:
        raise AssertionError("posterior accumulator reachability differs from raw-history enumeration")
    accuracy = histories["raw_history_accuracy"]
    layer_state_counts = [len(layer["posterior_states"]) for layer in layers]
    raw_prefix_history_count = sum(2 ** step for step in range(len(normalized_sensors) + 1))
    layered_posterior_state_count = sum(layer_state_counts)
    report: dict[str, Any] = {
        "format": FORMAT,
        "model": {
            "hidden_hypotheses": ["A", "B"],
            "observation_alphabet": ["A", "B"],
            "prior_A": _doc(prior_a),
            "prior_B": _doc(1 - prior_a),
            "sensors": normalized_sensors,
            "conditional_independence_assumption": "signals are independent given the fixed hidden hypothesis; sensor response probabilities may vary by position",
        },
        "observation_count": len(normalized_sensors),
        "full_history": {
            "raw_history_count": histories["raw_history_count"],
            "raw_histories_checked": histories["raw_history_count"],
            "raw_history_accuracy": _doc(accuracy),
            "posterior_state_count": histories["posterior_state_count"],
            "unreachable_history_count": histories["unreachable_history_count"],
            "posterior_groups": histories["posterior_groups"],
            "raw_history_rows": histories["raw_history_rows"],
        },
        "count_A_diagnostic": {
            "class_count": histories["count_A_class_count"],
            "sufficient_for_posterior": histories["count_A_sufficient_for_posterior"],
            "sufficient_for_map_decision": histories["count_A_sufficient_for_map"],
            "classes": histories["count_A_diagnostics"],
        },
        "posterior_accumulator": {
            "initial_posterior_A": _doc(prior_a),
            "update_rule": "p_next = p * P(signal | H=A) / (p * P(signal | H=A) + (1-p) * P(signal | H=B))",
            "sensor_identity_is_supplied_with_each_signal": True,
            "layers": layers,
            "transitions": transitions,
            "terminal_posterior_state_count": len(accumulated_terminal),
        },
        "summary": {
            "map_accuracy": _doc(accuracy),
            "bayes_error_probability": _doc(1 - accuracy),
            "raw_history_count": histories["raw_history_count"],
            "terminal_posterior_state_count": histories["posterior_state_count"],
            "history_states_per_posterior_state": _doc(Fraction(
                histories["raw_history_count"], histories["posterior_state_count"]
            )),
            "raw_history_state_reduction": histories["raw_history_count"] - histories["posterior_state_count"],
            "raw_prefix_history_node_count": raw_prefix_history_count,
            "layered_posterior_accumulator_state_count": layered_posterior_state_count,
            "posterior_state_counts_by_layer": layer_state_counts,
        },
        "max_histories": max_histories,
    }
    report["content_digest"] = _sha256(report)
    return report


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute posterior transitions, groupings, and all MAP decisions."""
    if not isinstance(document, Mapping) or document.get("format") != FORMAT:
        raise ValueError("unsupported heterogeneous evidence report")
    model = document.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("report model is missing")
    rebuilt = build_report(
        prior_hypothesis_a=model.get("prior_A"),
        sensors=model.get("sensors"),
        max_histories=document.get("max_histories"),
    )
    if dict(document) != rebuilt:
        raise ValueError("report differs from independent reconstruction")
    return rebuilt
