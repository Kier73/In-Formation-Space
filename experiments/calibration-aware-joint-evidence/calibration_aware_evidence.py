"""Exact Bayesian evidence accumulation with a session-shared latent calibration state."""
from __future__ import annotations

import hashlib
import itertools
import json
from fractions import Fraction
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.calibration-aware-evidence/0.1"


class HistoryLimitError(ValueError):
    """Raised when exhaustive history verification exceeds the declared cap."""


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


def _normalize_sensor_schedule(sensor_schedule: Sequence[str]) -> list[str]:
    if not isinstance(sensor_schedule, (tuple, list)) or not sensor_schedule:
        raise ValueError("sensor_schedule must be a non-empty sequence")
    return [_text(sensor_id, "sensor_schedule item") for sensor_id in sensor_schedule]


def _normalize_calibrations(calibrations, sensor_ids: set[str]):
    if not isinstance(calibrations, (tuple, list)) or not calibrations:
        raise ValueError("calibrations must be a non-empty sequence")
    required = {"calibration_id", "prior_probability", "sensor_models"}
    result, seen = [], set()
    for item in calibrations:
        if not isinstance(item, Mapping) or set(item) != required:
            raise ValueError("each calibration needs exactly an ID, prior, and sensor_models")
        ident = _text(item["calibration_id"], "calibration_id")
        if ident in seen:
            raise ValueError(f"duplicate calibration_id: {ident}")
        seen.add(ident)
        sensor_models = item["sensor_models"]
        if not isinstance(sensor_models, Mapping) or set(sensor_models) != sensor_ids:
            raise ValueError(f"{ident}.sensor_models must define every scheduled sensor type exactly once")
        normalized_models = {}
        for sensor_id in sorted(sensor_ids):
            model = sensor_models[sensor_id]
            expected = {"p_signal_a_given_hypothesis_a", "p_signal_a_given_hypothesis_b"}
            if not isinstance(model, Mapping) or set(model) != expected:
                raise ValueError(f"{ident}.sensor_models[{sensor_id}] must define both signal probabilities")
            normalized_models[sensor_id] = {
                "p_signal_a_given_hypothesis_a": _doc(_fraction(
                    model["p_signal_a_given_hypothesis_a"], f"{ident}.{sensor_id}.p_signal_a_given_hypothesis_a"
                )),
                "p_signal_a_given_hypothesis_b": _doc(_fraction(
                    model["p_signal_a_given_hypothesis_b"], f"{ident}.{sensor_id}.p_signal_a_given_hypothesis_b"
                )),
            }
        result.append({
            "calibration_id": ident,
            "prior_probability": _doc(_fraction(item["prior_probability"], f"{ident}.prior_probability")),
            "sensor_models": normalized_models,
        })
    result.sort(key=lambda item: item["calibration_id"])
    total = sum((Fraction(**item["prior_probability"]) for item in result), Fraction(0))
    if total != 1:
        raise ValueError("calibration prior probabilities must sum exactly to 1")
    return result


def _latent_likelihood(calibration, hypothesis: str, sensor_id: str, signal: str) -> Fraction:
    model = calibration["sensor_models"][sensor_id]
    key = "p_signal_a_given_hypothesis_a" if hypothesis == "A" else "p_signal_a_given_hypothesis_b"
    probability_a = Fraction(**model[key])
    return probability_a if signal == "A" else 1 - probability_a


def _normalize_vector(values):
    total = sum(values, Fraction(0))
    if total == 0:
        return None
    return tuple(value / total for value in values)


def _update_joint_belief(belief, calibrations, sensor_id, signal):
    weighted = []
    calibration_count = len(calibrations)
    for index, calibration in enumerate(calibrations):
        weighted.append(belief[index] * _latent_likelihood(calibration, "A", sensor_id, signal))
    for index, calibration in enumerate(calibrations):
        weighted.append(belief[calibration_count + index] * _latent_likelihood(calibration, "B", sensor_id, signal))
    return _normalize_vector(weighted)


def _posterior_a_from_vector(vector, calibration_count):
    return sum(vector[:calibration_count], Fraction(0))


def _posterior_calibration_from_vector(vector, calibration_count):
    return {
        calibration_index: vector[calibration_index] + vector[calibration_count + calibration_index]
        for calibration_index in range(calibration_count)
    }


def _joint_vector_for_history(history, sensor_schedule, calibrations, prior_a):
    calibration_count = len(calibrations)
    masses = []
    for hypothesis, prior_h in (("A", prior_a), ("B", 1 - prior_a)):
        for calibration in calibrations:
            mass = prior_h * Fraction(**calibration["prior_probability"])
            for signal, sensor_id in zip(history, sensor_schedule):
                mass *= _latent_likelihood(calibration, hypothesis, sensor_id, signal)
            masses.append(mass)
    return _normalize_vector(masses), tuple(masses)


def _redraw_independent_posterior(history, sensor_schedule, calibrations, prior_a):
    """Comparator: redraw calibration independently for each scheduled observation."""
    sensor_means = {}
    for sensor_id in sorted(set(sensor_schedule)):
        mean_alpha = sum((
            Fraction(**calibration["prior_probability"])
            * Fraction(**calibration["sensor_models"][sensor_id]["p_signal_a_given_hypothesis_a"])
            for calibration in calibrations
        ), Fraction(0))
        mean_beta = sum((
            Fraction(**calibration["prior_probability"])
            * Fraction(**calibration["sensor_models"][sensor_id]["p_signal_a_given_hypothesis_b"])
            for calibration in calibrations
        ), Fraction(0))
        sensor_means[sensor_id] = (mean_alpha, mean_beta)
    mass_a, mass_b = prior_a, 1 - prior_a
    for signal, sensor_id in zip(history, sensor_schedule):
        mean_alpha, mean_beta = sensor_means[sensor_id]
        mass_a *= mean_alpha if signal == "A" else 1 - mean_alpha
        mass_b *= mean_beta if signal == "A" else 1 - mean_beta
    normalizer = mass_a + mass_b
    if normalizer == 0:
        return None, "unreachable", sensor_means, mass_a, mass_b
    posterior_a = mass_a / normalizer
    decision = "A" if mass_a >= mass_b else "B"
    return posterior_a, decision, sensor_means, mass_a, mass_b


def _history_enumeration(calibrations, sensor_schedule, prior_a, max_histories):
    observation_count = len(sensor_schedule)
    raw_count = 2 ** observation_count
    if raw_count > max_histories:
        raise HistoryLimitError(f"raw history enumeration needs {raw_count} strings; cap is {max_histories}")
    posterior_groups = {}
    raw_rows = []
    shared_accuracy = Fraction(0)
    redraw_accuracy = Fraction(0)
    redraw_policy_accuracy_under_shared_model = Fraction(0)
    disagreement_probability = Fraction(0)
    for history_tuple in itertools.product(("A", "B"), repeat=observation_count):
        history = "".join(history_tuple)
        vector, masses = _joint_vector_for_history(history_tuple, sensor_schedule, calibrations, prior_a)
        calibration_count = len(calibrations)
        mass_a = sum(masses[:calibration_count], Fraction(0))
        mass_b = sum(masses[calibration_count:], Fraction(0))
        normalizer = mass_a + mass_b
        if vector is None:
            posterior_a = None
            shared_decision = "unreachable"
            posterior_cal = None
        else:
            posterior_a = _posterior_a_from_vector(vector, calibration_count)
            shared_decision = "A" if mass_a >= mass_b else "B"
            calibration_marginals = _posterior_calibration_from_vector(vector, calibration_count)
            posterior_cal = {
                calibration["calibration_id"]: _doc(calibration_marginals[index])
                for index, calibration in enumerate(calibrations)
            }
            shared_accuracy += max(mass_a, mass_b)
        naive_posterior, naive_decision, sensor_means, naive_mass_a, naive_mass_b = _redraw_independent_posterior(
            history_tuple, sensor_schedule, calibrations, prior_a
        )
        if naive_posterior is not None:
            redraw_accuracy += max(naive_mass_a, naive_mass_b)
        if naive_decision == "A":
            redraw_policy_accuracy_under_shared_model += mass_a
        elif naive_decision == "B":
            redraw_policy_accuracy_under_shared_model += mass_b
        if vector is not None and naive_posterior is not None and shared_decision != naive_decision:
            disagreement_probability += normalizer
        vector_key = None if vector is None else tuple(vector)
        posterior_groups.setdefault(vector_key, []).append(history)
        raw_rows.append({
            "history": history,
            "posterior_joint_latent_state": None if vector is None else [_doc(value) for value in vector],
            "posterior_A_shared_calibration": None if posterior_a is None else _doc(posterior_a),
            "posterior_calibration_shared_model": posterior_cal,
            "shared_calibration_map_decision": shared_decision,
            "independent_redraw_posterior_A": None if naive_posterior is None else _doc(naive_posterior),
            "independent_redraw_map_decision": naive_decision,
            "joint_mass_shared_if_A": _doc(mass_a),
            "joint_mass_shared_if_B": _doc(mass_b),
            "joint_mass_redraw_if_A": _doc(naive_mass_a),
            "joint_mass_redraw_if_B": _doc(naive_mass_b),
        })
    grouped = []
    for vector, histories in posterior_groups.items():
        if vector is None:
            posterior_a = None
            decision = "unreachable"
        else:
            posterior_a = _posterior_a_from_vector(vector, len(calibrations))
            decision = "A" if posterior_a >= Fraction(1, 2) else "B"
        grouped.append({
            "posterior_joint_latent_state": None if vector is None else [_doc(value) for value in vector],
            "posterior_A": None if posterior_a is None else _doc(posterior_a),
            "map_decision": decision,
            "histories": sorted(histories),
            "history_count": len(histories),
        })
    grouped.sort(key=lambda row: (row["posterior_A"] is not None, str(row["posterior_joint_latent_state"])))
    return {
        "raw_history_count": raw_count,
        "raw_history_rows": raw_rows,
        "posterior_groups": grouped,
        "joint_belief_state_count": sum(vector is not None for vector in posterior_groups),
        "unreachable_history_count": len(posterior_groups.get(None, [])),
        "shared_calibration_accuracy": shared_accuracy,
        "independent_redraw_accuracy_under_its_own_model": redraw_accuracy,
        "independent_redraw_policy_accuracy_under_shared_model": redraw_policy_accuracy_under_shared_model,
        "decision_disagreement_probability_under_shared_model": disagreement_probability,
    }


def _belief_accumulator(calibrations, sensor_schedule, prior_a):
    initial = tuple(
        [prior_a * Fraction(**calibration["prior_probability"]) for calibration in calibrations]
        + [(1 - prior_a) * Fraction(**calibration["prior_probability"]) for calibration in calibrations]
    )
    current = {initial}
    layers = [{"step": 0, "sensor_id": "before_first_observation", "joint_belief_states": [[_doc(value) for value in initial]]}]
    transitions = []
    for step, sensor_id in enumerate(sensor_schedule):
        following = set()
        step_rows = []
        for belief in sorted(current):
            target_a = _update_joint_belief(belief, calibrations, sensor_id, "A")
            target_b = _update_joint_belief(belief, calibrations, sensor_id, "B")
            if target_a is not None:
                following.add(target_a)
            if target_b is not None:
                following.add(target_b)
            step_rows.append({
                "joint_belief_before": [_doc(value) for value in belief],
                "on_signal_A": None if target_a is None else [_doc(value) for value in target_a],
                "on_signal_B": None if target_b is None else [_doc(value) for value in target_b],
            })
        transitions.append({"step": step + 1, "sensor_id": sensor_id, "transitions": step_rows})
        current = following
        layers.append({
            "step": step + 1,
            "sensor_id": sensor_id,
            "joint_belief_states": [[_doc(value) for value in belief] for belief in sorted(current)],
        })
    return initial, layers, transitions


def _same_marginal_future_update_counterexample(calibrations, sensor_schedule, prior_a):
    """Find same marginal P(H=A), different joint beliefs, different next update."""
    if len(sensor_schedule) < 3:
        return None
    prefixes = list(itertools.product(("A", "B"), repeat=2))
    candidates = []
    for prefix in prefixes:
        vector, _ = _joint_vector_for_history(prefix, sensor_schedule[:2], calibrations, prior_a)
        if vector is not None:
            candidates.append(("".join(prefix), vector, _posterior_a_from_vector(vector, len(calibrations))))
    for left_index, (left_history, left_vector, left_marginal) in enumerate(candidates):
        for right_history, right_vector, right_marginal in candidates[left_index + 1:]:
            if left_marginal != right_marginal or left_vector == right_vector:
                continue
            sensor_id = sensor_schedule[2]
            left_after = _update_joint_belief(left_vector, calibrations, sensor_id, "A")
            right_after = _update_joint_belief(right_vector, calibrations, sensor_id, "A")
            if left_after is None or right_after is None:
                continue
            left_redraw, left_redraw_decision, _, _, _ = _redraw_independent_posterior(
                tuple(left_history + "A"), sensor_schedule[:3], calibrations, prior_a
            )
            right_redraw, right_redraw_decision, _, _, _ = _redraw_independent_posterior(
                tuple(right_history + "A"), sensor_schedule[:3], calibrations, prior_a
            )
            return {
                "prefix_length": 2,
                "next_sensor_id": sensor_id,
                "next_signal": "A",
                "left_prefix": left_history,
                "right_prefix": right_history,
                "shared_model_posterior_A_before_next_signal": _doc(left_marginal),
                "left_joint_posterior_before_next_signal": [_doc(value) for value in left_vector],
                "right_joint_posterior_before_next_signal": [_doc(value) for value in right_vector],
                "left_shared_model_posterior_A_after_next_signal": _doc(
                    _posterior_a_from_vector(left_after, len(calibrations))
                ),
                "right_shared_model_posterior_A_after_next_signal": _doc(
                    _posterior_a_from_vector(right_after, len(calibrations))
                ),
                "left_shared_model_map_decision_after_next_signal": (
                    "A" if _posterior_a_from_vector(left_after, len(calibrations)) >= Fraction(1, 2) else "B"
                ),
                "right_shared_model_map_decision_after_next_signal": (
                    "A" if _posterior_a_from_vector(right_after, len(calibrations)) >= Fraction(1, 2) else "B"
                ),
                "left_independent_redraw_posterior_A_after_next_signal": None if left_redraw is None else _doc(left_redraw),
                "right_independent_redraw_posterior_A_after_next_signal": None if right_redraw is None else _doc(right_redraw),
                "left_independent_redraw_map_decision_after_next_signal": left_redraw_decision,
                "right_independent_redraw_map_decision_after_next_signal": right_redraw_decision,
                "interpretation": "the same marginal hypothesis posterior does not identify the joint calibration posterior needed for the next exact update",
            }
    return None


def build_report(*, prior_hypothesis_a: Any, calibrations: Sequence[Mapping[str, Any]],
                 sensor_schedule: Sequence[str], max_histories: int = 1_000_000) -> dict[str, Any]:
    """Compare session-shared calibration with independently redrawn calibration.

    A calibration state is drawn once and shared through the session. It defines
    the response probabilities of every scheduled sensor type. Signals are
    independent conditional on the fixed hidden hypothesis and shared calibration.
    The comparator redraws calibration independently at each observation.
    """
    if isinstance(max_histories, bool) or not isinstance(max_histories, int) or max_histories < 1:
        raise ValueError("max_histories must be a positive integer")
    prior_a = _fraction(prior_hypothesis_a, "prior_hypothesis_a")
    normalized_schedule = _normalize_sensor_schedule(sensor_schedule)
    normalized = _normalize_calibrations(calibrations, set(normalized_schedule))
    enumeration = _history_enumeration(normalized, normalized_schedule, prior_a, max_histories)
    initial, layers, transitions = _belief_accumulator(normalized, normalized_schedule, prior_a)
    terminal_from_histories = {
        tuple(Fraction(**value) for value in row["posterior_joint_latent_state"])
        for row in enumeration["raw_history_rows"]
        if row["posterior_joint_latent_state"] is not None
    }
    terminal_from_accumulator = {
        tuple(Fraction(**value) for value in vector)
        for vector in layers[-1]["joint_belief_states"]
    }
    if terminal_from_histories != terminal_from_accumulator:
        raise AssertionError("joint-belief accumulator does not reconstruct raw-history posterior states")
    layer_state_counts = [len(layer["joint_belief_states"]) for layer in layers]
    raw_prefix_history_count = sum(2 ** step for step in range(len(normalized_schedule) + 1))
    scalar_counterexample = _same_marginal_future_update_counterexample(
        normalized, normalized_schedule, prior_a
    )
    report: dict[str, Any] = {
        "format": FORMAT,
        "model": {
            "hidden_hypotheses": ["A", "B"],
            "prior_A": _doc(prior_a),
            "prior_B": _doc(1 - prior_a),
            "calibration_prior_independent_of_hidden_hypothesis": True,
            "calibrations": normalized,
            "sensor_schedule": normalized_schedule,
            "calibration_scope": "one calibration state is drawn once and shared across the complete observation session",
            "conditional_independence_assumption": "signals are independent conditional on both hidden hypothesis and shared calibration state",
        },
        "observation_count": len(normalized_schedule),
        "latent_state_order": [
            {"hypothesis": hypothesis, "calibration_id": calibration["calibration_id"]}
            for hypothesis in ("A", "B") for calibration in normalized
        ],
        "shared_calibration_full_history": {
            "raw_history_count": enumeration["raw_history_count"],
            "raw_histories_checked": enumeration["raw_history_count"],
            "joint_belief_state_count": enumeration["joint_belief_state_count"],
            "unreachable_history_count": enumeration["unreachable_history_count"],
            "joint_map_accuracy": _doc(enumeration["shared_calibration_accuracy"]),
            "posterior_groups": enumeration["posterior_groups"],
            "raw_history_rows": enumeration["raw_history_rows"],
        },
        "independent_redraw_comparator": {
            "meaning": "calibration is independently redrawn from its prior for every observation",
            "map_accuracy_under_independent_redraw_model": _doc(enumeration["independent_redraw_accuracy_under_its_own_model"]),
            "redraw_policy_accuracy_if_shared_model_is_true": _doc(
                enumeration["independent_redraw_policy_accuracy_under_shared_model"]
            ),
            "decision_disagreement_probability_if_shared_model_is_true": _doc(
                enumeration["decision_disagreement_probability_under_shared_model"]
            ),
        },
        "joint_belief_accumulator": {
            "initial_joint_belief": [_doc(value) for value in initial],
            "state_semantics": "posterior distribution over (hidden hypothesis, session calibration)",
            "sensor_schedule": normalized_schedule,
            "layers": layers,
            "transitions": transitions,
            "terminal_joint_belief_state_count": len(terminal_from_accumulator),
        },
        "same_marginal_future_update_counterexample": scalar_counterexample,
        "summary": {
            "shared_calibration_map_accuracy": _doc(enumeration["shared_calibration_accuracy"]),
            "independent_redraw_map_accuracy_under_its_own_model": _doc(enumeration["independent_redraw_accuracy_under_its_own_model"]),
            "independent_redraw_policy_accuracy_under_shared_model": _doc(
                enumeration["independent_redraw_policy_accuracy_under_shared_model"]
            ),
            "raw_history_count": enumeration["raw_history_count"],
            "terminal_joint_belief_state_count": enumeration["joint_belief_state_count"],
            "layered_joint_belief_state_count": sum(layer_state_counts),
            "joint_belief_state_counts_by_layer": layer_state_counts,
            "raw_prefix_history_node_count": raw_prefix_history_count,
            "decision_disagreement_probability_under_shared_model": _doc(
                enumeration["decision_disagreement_probability_under_shared_model"]
            ),
        },
        "max_histories": max_histories,
    }
    report["content_digest"] = _sha256(report)
    return report


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the joint posterior trajectory and comparator from retained inputs."""
    if not isinstance(document, Mapping) or document.get("format") != FORMAT:
        raise ValueError("unsupported calibration-aware evidence report")
    model = document.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("report model is missing")
    rebuilt = build_report(
        prior_hypothesis_a=model.get("prior_A"),
        calibrations=model.get("calibrations"),
        sensor_schedule=model.get("sensor_schedule"),
        max_histories=document.get("max_histories"),
    )
    if dict(document) != rebuilt:
        raise ValueError("report differs from independent reconstruction")
    return rebuilt
