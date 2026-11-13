"""Exact Bayesian evidence accumulator with a persistent hidden context regime.

RIV-006 extends heterogeneous sensor schedules with a latent Markov operating
regime. The recursive state is the joint posterior over the fixed hypothesis
and the next operating regime. It demonstrates why the hypothesis marginal,
or even the two separate marginals, need not preserve future updates.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from fractions import Fraction
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.context-switching-evidence-accumulator/0.1"
HYPOTHESES = ("A", "B")
REGIMES = ("good", "degraded")
SIGNALS = ("A", "B")
_STATE_ORDER = (
    ("A", "good"),
    ("A", "degraded"),
    ("B", "good"),
    ("B", "degraded"),
)


class HistoryLimitError(ValueError):
    """Raised when exhaustive ordered-history verification exceeds its cap."""


def _fraction(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(
            f"{label} must be an exact rational; floats and booleans are rejected"
        )
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
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_sensors(sensors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(sensors, (tuple, list)) or not sensors:
        raise ValueError("sensors must be a non-empty sequence")
    required = {
        "sensor_id",
        "p_signal_a_given_hypothesis_a_good",
        "p_signal_a_given_hypothesis_b_good",
        "p_signal_a_given_hypothesis_a_degraded",
        "p_signal_a_given_hypothesis_b_degraded",
    }
    result, seen = [], set()
    for index, item in enumerate(sensors):
        if not isinstance(item, Mapping) or set(item) != required:
            raise ValueError(
                "each sensor needs an ID and four exact conditional A-signal probabilities"
            )
        sensor_id = _text(item["sensor_id"], f"sensors[{index}].sensor_id")
        if sensor_id in seen:
            raise ValueError(f"duplicate sensor_id: {sensor_id}")
        seen.add(sensor_id)
        row = {"sensor_id": sensor_id}
        for field in sorted(required - {"sensor_id"}):
            row[field] = _doc(_fraction(item[field], f"{sensor_id}.{field}"))
        result.append(row)
    return result


def _normalize_context_transition(value: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    required = {
        "p_good_next_given_good",
        "p_good_next_given_degraded",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError(
            "context_transition needs p_good_next_given_good and "
            "p_good_next_given_degraded"
        )
    return {
        key: _doc(_fraction(value[key], key))
        for key in sorted(required)
    }


def _initial_belief(prior_a: Fraction, prior_good: Fraction):
    return {
        ("A", "good"): prior_a * prior_good,
        ("A", "degraded"): prior_a * (1 - prior_good),
        ("B", "good"): (1 - prior_a) * prior_good,
        ("B", "degraded"): (1 - prior_a) * (1 - prior_good),
    }


def _probability_a(
    sensor: Mapping[str, Any],
    hypothesis: str,
    regime: str,
) -> Fraction:
    if hypothesis == "A" and regime == "good":
        key = "p_signal_a_given_hypothesis_a_good"
    elif hypothesis == "B" and regime == "good":
        key = "p_signal_a_given_hypothesis_b_good"
    elif hypothesis == "A":
        key = "p_signal_a_given_hypothesis_a_degraded"
    else:
        key = "p_signal_a_given_hypothesis_b_degraded"
    return Fraction(**sensor[key])


def _transition_probability(
    context_transition: Mapping[str, Mapping[str, int]],
    regime_before: str,
    regime_after: str,
) -> Fraction:
    if regime_before == "good":
        p_good = Fraction(**context_transition["p_good_next_given_good"])
    else:
        p_good = Fraction(**context_transition["p_good_next_given_degraded"])
    return p_good if regime_after == "good" else 1 - p_good


def _joint_key(belief: Mapping[tuple[str, str], Fraction]) -> tuple[Fraction, ...]:
    return tuple(belief[key] for key in _STATE_ORDER)


def _joint_document(belief: Mapping[tuple[str, str], Fraction]):
    return [
        {
            "hypothesis": hypothesis,
            "regime": regime,
            "probability": _doc(belief[(hypothesis, regime)]),
        }
        for hypothesis, regime in _STATE_ORDER
    ]


def _belief_id(belief: Mapping[tuple[str, str], Fraction]) -> str:
    return _sha256(_joint_document(belief))


def _marginals(belief: Mapping[tuple[str, str], Fraction]):
    posterior_a = belief[("A", "good")] + belief[("A", "degraded")]
    posterior_good = belief[("A", "good")] + belief[("B", "good")]
    return posterior_a, posterior_good


def _update_joint(
    belief: Mapping[tuple[str, str], Fraction],
    sensor: Mapping[str, Any],
    signal: str,
    context_transition: Mapping[str, Mapping[str, int]],
):
    """Condition on a signal, then predict the next Markov context regime.

    Returns (next joint posterior, signal evidence probability). The hidden
    hypothesis is fixed; the context regime transitions independently of it.
    """
    if signal not in SIGNALS:
        raise ValueError("signal must be A or B")
    weighted = {}
    for hypothesis, regime in _STATE_ORDER:
        p_signal_a = _probability_a(sensor, hypothesis, regime)
        likelihood = p_signal_a if signal == "A" else 1 - p_signal_a
        weighted[(hypothesis, regime)] = belief[(hypothesis, regime)] * likelihood
    evidence_probability = sum(weighted.values(), Fraction(0))
    if evidence_probability == 0:
        return None, Fraction(0)
    posterior_current_regime = {
        key: mass / evidence_probability
        for key, mass in weighted.items()
    }
    predictive_next_regime = {
        key: Fraction(0)
        for key in _STATE_ORDER
    }
    for hypothesis, regime_before in _STATE_ORDER:
        mass = posterior_current_regime[(hypothesis, regime_before)]
        for regime_after in REGIMES:
            transition_probability = _transition_probability(
                context_transition,
                regime_before,
                regime_after,
            )
            predictive_next_regime[(hypothesis, regime_after)] += (
                mass * transition_probability
            )
    return predictive_next_regime, evidence_probability


def _belief_state_record(belief: Mapping[tuple[str, str], Fraction]):
    posterior_a, posterior_good = _marginals(belief)
    return {
        "belief_id": _belief_id(belief),
        "joint_posterior": _joint_document(belief),
        "posterior_hypothesis_a": _doc(posterior_a),
        "posterior_regime_good": _doc(posterior_good),
        "map_decision": "A" if posterior_a >= Fraction(1, 2) else "B",
    }


def _prefix_layer_summary(
    step: int,
    sensor_id: str,
    histories: Mapping[str, tuple[object, Fraction]],
    next_sensor: Mapping[str, Any] | None,
    context_transition: Mapping[str, Mapping[str, int]],
):
    reachable = {
        history: belief
        for history, (belief, _) in histories.items()
        if belief is not None
    }
    joint_groups: dict[tuple[Fraction, ...], list[str]] = {}
    hypothesis_groups: dict[Fraction, list[str]] = {}
    separate_marginal_groups: dict[tuple[Fraction, Fraction], list[str]] = {}
    for history, belief in reachable.items():
        key = _joint_key(belief)
        hypothesis, regime = _marginals(belief)
        joint_groups.setdefault(key, []).append(history)
        hypothesis_groups.setdefault(hypothesis, []).append(history)
        separate_marginal_groups.setdefault((hypothesis, regime), []).append(history)

    def collision_count(groups):
        return sum(
            1
            for histories_in_group in groups.values()
            if len({_joint_key(reachable[h]) for h in histories_in_group}) > 1
        )

    def next_update_divergences(groups, *, group_by_separate_marginals: bool):
        found = []
        if next_sensor is None:
            return found
        for group_key, group_histories in sorted(
            groups.items(),
            key=lambda pair: pair[0],
        ):
            unique: dict[tuple[Fraction, ...], str] = {}
            for history in sorted(group_histories):
                belief = reachable[history]
                unique.setdefault(_joint_key(belief), history)
            if len(unique) < 2:
                continue
            rows = []
            for belief_key, history in sorted(unique.items(), key=lambda item: item[1]):
                belief = reachable[history]
                after_a, evidence_a = _update_joint(
                    belief, next_sensor, "A", context_transition
                )
                after_b, evidence_b = _update_joint(
                    belief, next_sensor, "B", context_transition
                )
                rows.append({
                    "history": history,
                    "joint_posterior": _joint_document(belief),
                    "next_posterior_hypothesis_a_on_signal_a": (
                        None if after_a is None else _doc(_marginals(after_a)[0])
                    ),
                    "next_posterior_hypothesis_a_on_signal_b": (
                        None if after_b is None else _doc(_marginals(after_b)[0])
                    ),
                    "next_signal_a_probability": _doc(evidence_a),
                    "next_signal_b_probability": _doc(evidence_b),
                })
            def rational_identity(value):
                if value is None:
                    return None
                return (value["numerator"], value["denominator"])

            diverges_on_a = len({
                rational_identity(row["next_posterior_hypothesis_a_on_signal_a"])
                for row in rows
            }) > 1
            diverges_on_b = len({
                rational_identity(row["next_posterior_hypothesis_a_on_signal_b"])
                for row in rows
            }) > 1
            if diverges_on_a or diverges_on_b:
                if group_by_separate_marginals:
                    posterior_a, posterior_good = group_key
                else:
                    posterior_a, posterior_good = group_key, None
                found.append({
                    "shared_posterior_hypothesis_a": _doc(posterior_a),
                    "shared_posterior_regime_good": (
                        None if posterior_good is None else _doc(posterior_good)
                    ),
                    "histories": rows,
                    "next_update_diverges_on_signal_a": diverges_on_a,
                    "next_update_diverges_on_signal_b": diverges_on_b,
                })
        return found

    hypothesis_divergences = next_update_divergences(
        hypothesis_groups,
        group_by_separate_marginals=False,
    )
    separate_marginal_divergences = next_update_divergences(
        separate_marginal_groups,
        group_by_separate_marginals=True,
    )

    state_records = sorted(
        (
            _belief_state_record(reachable[histories_in_group[0]])
            for histories_in_group in joint_groups.values()
        ),
        key=lambda item: item["belief_id"],
    )
    return {
        "step": step,
        "sensor_id": sensor_id,
        "raw_prefix_history_count": 2 ** step,
        "reachable_prefix_history_count": len(reachable),
        "unreachable_prefix_history_count": 2 ** step - len(reachable),
        "joint_posterior_state_count": len(joint_groups),
        "hypothesis_marginal_state_count": len(hypothesis_groups),
        "separate_marginals_state_count": len(separate_marginal_groups),
        "same_hypothesis_marginal_different_joint_group_count": collision_count(
            hypothesis_groups
        ),
        "same_separate_marginals_different_joint_group_count": collision_count(
            separate_marginal_groups
        ),
        "joint_posterior_states": state_records,
        "hypothesis_marginal_next_update_divergences": hypothesis_divergences,
        "separate_marginal_next_update_divergences": separate_marginal_divergences,
    }


def build_report(
    *,
    prior_hypothesis_a: Any,
    prior_context_good: Any,
    context_transition: Mapping[str, Any],
    sensors: Sequence[Mapping[str, Any]],
    max_histories: int = 1_000_000,
) -> dict[str, Any]:
    """Build a joint H × context-regime posterior accumulator.

    H is fixed over the schedule. The context regime is a two-state Markov
    process, independent of H's transition (H does not transition), and each
    signal is conditionally independent given H and the current regime.
    The sensor schedule and all likelihood/transition parameters are known.
    """
    prior_a = _fraction(prior_hypothesis_a, "prior_hypothesis_a")
    prior_good = _fraction(prior_context_good, "prior_context_good")
    if (
        isinstance(max_histories, bool)
        or not isinstance(max_histories, int)
        or max_histories < 1
    ):
        raise ValueError("max_histories must be a positive integer")
    normalized_sensors = _normalize_sensors(sensors)
    raw_history_count = 2 ** len(normalized_sensors)
    if raw_history_count > max_histories:
        raise HistoryLimitError(
            f"raw-history verification needs {raw_history_count} strings; "
            f"cap is {max_histories}"
        )
    normalized_transition = _normalize_context_transition(context_transition)

    initial = _initial_belief(prior_a, prior_good)
    layers: list[dict[str, tuple[object, Fraction]]] = [
        {"": (initial, Fraction(1))}
    ]
    for index, sensor in enumerate(normalized_sensors):
        following: dict[str, tuple[object, Fraction]] = {}
        for history, (belief, history_probability) in sorted(layers[-1].items()):
            for signal in SIGNALS:
                child = history + signal
                if belief is None:
                    following[child] = (None, Fraction(0))
                    continue
                next_belief, signal_probability = _update_joint(
                    belief,
                    sensor,
                    signal,
                    normalized_transition,
                )
                following[child] = (
                    next_belief,
                    history_probability * signal_probability,
                )
        layers.append(following)

    layer_summaries = []
    transitions = []
    for step, histories in enumerate(layers):
        if step == 0:
            sensor_id = "before_first_observation"
            next_sensor = normalized_sensors[0]
        else:
            sensor_id = normalized_sensors[step - 1]["sensor_id"]
            next_sensor = (
                normalized_sensors[step]
                if step < len(normalized_sensors)
                else None
            )
        layer_summaries.append(
            _prefix_layer_summary(
                step,
                sensor_id,
                histories,
                next_sensor,
                normalized_transition,
            )
        )
        if next_sensor is not None:
            unique_beliefs = {}
            for belief, _ in histories.values():
                if belief is not None:
                    unique_beliefs.setdefault(_joint_key(belief), belief)
            rows = []
            for belief in sorted(unique_beliefs.values(), key=_belief_id):
                for signal in SIGNALS:
                    next_belief, probability = _update_joint(
                        belief,
                        next_sensor,
                        signal,
                        normalized_transition,
                    )
                    rows.append({
                        "from_belief_id": _belief_id(belief),
                        "signal": signal,
                        "signal_probability": _doc(probability),
                        "to_belief_id": (
                            None if next_belief is None else _belief_id(next_belief)
                        ),
                        "unreachable": next_belief is None,
                    })
            transitions.append({
                "step": step,
                "sensor_id": next_sensor["sensor_id"],
                "transitions": rows,
            })

    final_histories = layers[-1]
    history_rows = []
    accuracy = Fraction(0)
    total_history_probability = Fraction(0)
    terminal_joint_states = set()
    for history, (belief, history_probability) in sorted(final_histories.items()):
        total_history_probability += history_probability
        if belief is None:
            history_rows.append({
                "history": history,
                "reachable": False,
                "history_probability": _doc(Fraction(0)),
                "posterior_hypothesis_a": None,
                "posterior_regime_good": None,
                "joint_posterior": None,
                "map_decision": "unreachable",
                "joint_mass_if_hypothesis_a": _doc(Fraction(0)),
                "joint_mass_if_hypothesis_b": _doc(Fraction(0)),
            })
            continue
        posterior_a, posterior_good = _marginals(belief)
        mass_a = history_probability * posterior_a
        mass_b = history_probability * (1 - posterior_a)
        accuracy += max(mass_a, mass_b)
        terminal_joint_states.add(_joint_key(belief))
        history_rows.append({
            "history": history,
            "reachable": True,
            "history_probability": _doc(history_probability),
            "posterior_hypothesis_a": _doc(posterior_a),
            "posterior_regime_good": _doc(posterior_good),
            "joint_posterior": _joint_document(belief),
            "map_decision": "A" if mass_a >= mass_b else "B",
            "joint_mass_if_hypothesis_a": _doc(mass_a),
            "joint_mass_if_hypothesis_b": _doc(mass_b),
        })

    if total_history_probability != 1:
        raise AssertionError(
            f"full history probabilities sum to {total_history_probability}, not one"
        )

    final_layer = layer_summaries[-1]
    hypothesis_divergences = [
        {"step": layer["step"], **witness}
        for layer in layer_summaries
        for witness in layer["hypothesis_marginal_next_update_divergences"]
    ]
    separate_marginal_divergences = [
        {"step": layer["step"], **witness}
        for layer in layer_summaries
        for witness in layer["separate_marginal_next_update_divergences"]
    ]
    report: dict[str, Any] = {
        "format": FORMAT,
        "model": {
            "hidden_hypotheses": list(HYPOTHESES),
            "context_regimes": list(REGIMES),
            "observation_alphabet": list(SIGNALS),
            "prior_hypothesis_a": _doc(prior_a),
            "prior_context_good": _doc(prior_good),
            "initial_hypothesis_context_independence": True,
            "context_transition": normalized_transition,
            "sensors": normalized_sensors,
            "context_semantics": (
                "the context regime is a hidden two-state Markov process; "
                "the transition is independent of the fixed hidden hypothesis"
            ),
            "emission_semantics": (
                "signals are conditionally independent given the fixed hypothesis "
                "and current context regime"
            ),
        },
        "observation_count": len(normalized_sensors),
        "history_verification": {
            "raw_history_count": raw_history_count,
            "raw_histories_checked": raw_history_count,
            "unreachable_history_count": sum(
                1 for row in history_rows if not row["reachable"]
            ),
            "total_history_probability": _doc(total_history_probability),
            "max_histories": max_histories,
        },
        "joint_posterior_accumulator": {
            "state_definition": (
                "the exact joint posterior P(H, next_context_regime | observed_prefix)"
            ),
            "state_coordinate_order": [
                {"hypothesis": hypothesis, "regime": regime}
                for hypothesis, regime in _STATE_ORDER
            ],
            "update_rule": (
                "condition the joint belief on the next signal using the current "
                "regime-specific sensor likelihoods, then predict the next regime "
                "through the supplied Markov transition matrix"
            ),
            "layers": layer_summaries,
            "transitions": transitions,
            "terminal_joint_posterior_state_count": len(terminal_joint_states),
        },
        "marginal_sufficiency_diagnostic": {
            "hypothesis_marginal_preserves_next_update_under_schedule": (
                not hypothesis_divergences
            ),
            "separate_marginals_preserve_next_update_under_schedule": (
                not separate_marginal_divergences
            ),
            "hypothesis_marginal_next_update_divergences": hypothesis_divergences,
            "separate_marginal_next_update_divergences": separate_marginal_divergences,
            "diagnostic_scope": (
                "one-step continuation under the next scheduled sensor at each prefix; "
                "absence of a one-step divergence is not a proof of sufficiency for all longer continuations"
            ),
            "interpretation": (
                "A shared marginal does not identify the joint association between "
                "hypothesis and context regime. If the same future sensor output "
                "then produces different hypothesis posteriors, the marginals "
                "cannot serve as the recursive filter state."
            ),
        },
        "full_history": {
            "rows": history_rows,
        },
        "summary": {
            "map_accuracy": _doc(accuracy),
            "bayes_error_probability": _doc(1 - accuracy),
            "raw_history_count": raw_history_count,
            "terminal_joint_posterior_state_count": len(terminal_joint_states),
            "terminal_hypothesis_marginal_state_count": (
                final_layer["hypothesis_marginal_state_count"]
            ),
            "terminal_separate_marginal_state_count": (
                final_layer["separate_marginals_state_count"]
            ),
            "terminal_joint_state_reduction": (
                raw_history_count - len(terminal_joint_states)
            ),
            "joint_posterior_state_counts_by_layer": [
                layer["joint_posterior_state_count"] for layer in layer_summaries
            ],
            "hypothesis_marginal_state_counts_by_layer": [
                layer["hypothesis_marginal_state_count"] for layer in layer_summaries
            ],
            "separate_marginal_state_counts_by_layer": [
                layer["separate_marginals_state_count"] for layer in layer_summaries
            ],
            "hypothesis_marginal_next_update_divergence_count": len(hypothesis_divergences),
            "separate_marginal_next_update_divergence_count": len(separate_marginal_divergences),
        },
    }
    report["content_digest"] = _sha256(report)
    return report


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild every filtering state, transition, and history comparison."""
    if not isinstance(document, Mapping) or document.get("format") != FORMAT:
        raise ValueError("unsupported context-switching evidence report")
    model = document.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("report model is missing")
    rebuilt = build_report(
        prior_hypothesis_a=model.get("prior_hypothesis_a"),
        prior_context_good=model.get("prior_context_good"),
        context_transition=model.get("context_transition"),
        sensors=model.get("sensors"),
        max_histories=document.get("history_verification", {}).get("max_histories"),
    )
    if dict(document) != rebuilt:
        raise ValueError(
            "report differs from independent reconstruction from retained inputs"
        )
    return rebuilt


__all__ = ["FORMAT", "HistoryLimitError", "build_report", "validate_report"]
