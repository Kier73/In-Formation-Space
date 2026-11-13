"""Exact Bayesian evidence accumulation for a binary iid observation channel."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from fractions import Fraction
from typing import Any, Mapping

FORMAT = "in-formation.evidence-accumulation-sufficiency/0.1"


class HistoryLimitError(ValueError):
    """Raised when exhaustive raw-history verification exceeds its declared cap."""


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


def _doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _power(probability: Fraction, exponent: int) -> Fraction:
    # Fraction(0) ** 0 is 1, as required for an empty product.
    return probability ** exponent


def _count_row(*, k: int, n: int, prior_a: Fraction,
               p_a_given_a: Fraction, p_a_given_b: Fraction) -> dict[str, Any]:
    q_a, q_b = 1 - p_a_given_a, 1 - p_a_given_b
    likelihood_a = _power(p_a_given_a, k) * _power(q_a, n - k)
    likelihood_b = _power(p_a_given_b, k) * _power(q_b, n - k)
    joint_a = prior_a * likelihood_a
    joint_b = (1 - prior_a) * likelihood_b
    unnormalized = joint_a + joint_b
    if unnormalized == 0:
        posterior = None
        decision = "unreachable"
        tie = False
    else:
        posterior = joint_a / unnormalized
        tie = joint_a == joint_b
        # Deterministic tie rule: choose A. The accuracy is unchanged by tie choice.
        decision = "A" if joint_a >= joint_b else "B"
    sequence_count = math.comb(n, k)
    marginal_count_probability = sequence_count * unnormalized
    correct_mass = sequence_count * max(joint_a, joint_b)
    return {
        "count_A": k,
        "count_B": n - k,
        "ordered_history_count": sequence_count,
        "likelihood_if_A": _doc(likelihood_a),
        "likelihood_if_B": _doc(likelihood_b),
        "joint_mass_for_one_history_if_A": _doc(joint_a),
        "joint_mass_for_one_history_if_B": _doc(joint_b),
        "posterior_A": None if posterior is None else _doc(posterior),
        "map_decision": decision,
        "posterior_tie": tie,
        "marginal_count_probability": _doc(marginal_count_probability),
        "correct_probability_mass": _doc(correct_mass),
    }


def _raw_history_check(*, n: int, prior_a: Fraction, p_a_given_a: Fraction,
                       p_a_given_b: Fraction, count_rows: list[dict[str, Any]],
                       max_histories: int) -> dict[str, Any]:
    history_count = 2 ** n
    if history_count > max_histories:
        raise HistoryLimitError(
            f"raw-history verification needs {history_count} strings; cap is {max_histories}"
        )
    rows = {row["count_A"]: row for row in count_rows}
    q_a, q_b = 1 - p_a_given_a, 1 - p_a_given_b
    raw_accuracy = Fraction(0)
    checked = 0
    count_to_decision: dict[int, str] = {}
    for history in itertools.product(("A", "B"), repeat=n):
        k = history.count("A")
        likelihood_a = math.prod(p_a_given_a if signal == "A" else q_a for signal in history)
        likelihood_b = math.prod(p_a_given_b if signal == "A" else q_b for signal in history)
        joint_a = prior_a * likelihood_a
        joint_b = (1 - prior_a) * likelihood_b
        if joint_a + joint_b > 0:
            raw_decision = "A" if joint_a >= joint_b else "B"
            count_decision = rows[k]["map_decision"]
            if raw_decision != count_decision:
                raise AssertionError(f"count statistic changed MAP decision for history {''.join(history)}")
            count_to_decision[k] = count_decision
            raw_accuracy += max(joint_a, joint_b)
        checked += 1
    count_accuracy = sum(
        (Fraction(**row["correct_probability_mass"]) for row in count_rows),
        Fraction(0),
    )
    if raw_accuracy != count_accuracy:
        raise AssertionError("raw-history and count-statistic MAP accuracy differ")
    return {
        "raw_history_count": history_count,
        "raw_histories_checked": checked,
        "raw_history_accuracy": _doc(raw_accuracy),
        "count_statistic_accuracy": _doc(count_accuracy),
        "exact_decision_equivalence": True,
        "count_class_decisions": [
            {"count_A": k, "decision": decision}
            for k, decision in sorted(count_to_decision.items())
        ],
    }


def build_report(*, observation_count: int, prior_hypothesis_a: Any,
                 p_signal_a_given_hypothesis_a: Any,
                 p_signal_a_given_hypothesis_b: Any,
                 max_histories: int = 1_000_000) -> dict[str, Any]:
    """Build exact MAP inference and prove count-vs-history equivalence on a finite sample.

    Hidden hypothesis H is fixed over the observation window and lies in {A, B}.
    Each observation is A or B. Conditional on H, observations are iid with
    P(signal=A | H=A)=alpha and P(signal=A | H=B)=beta.
    """
    if isinstance(observation_count, bool) or not isinstance(observation_count, int) or observation_count < 1:
        raise ValueError("observation_count must be a positive integer")
    if isinstance(max_histories, bool) or not isinstance(max_histories, int) or max_histories < 1:
        raise ValueError("max_histories must be a positive integer")
    prior_a = _fraction(prior_hypothesis_a, "prior_hypothesis_a")
    alpha = _fraction(p_signal_a_given_hypothesis_a, "p_signal_a_given_hypothesis_a")
    beta = _fraction(p_signal_a_given_hypothesis_b, "p_signal_a_given_hypothesis_b")

    rows = [
        _count_row(k=k, n=observation_count, prior_a=prior_a,
                   p_a_given_a=alpha, p_a_given_b=beta)
        for k in range(observation_count + 1)
    ]
    accuracy = sum(
        (Fraction(**row["correct_probability_mass"]) for row in rows),
        Fraction(0),
    )
    if accuracy > 1:
        raise AssertionError("MAP accuracy exceeded 1")
    # The count accumulator is a deterministic transducer: A increments,
    # B leaves the count unchanged, and END emits the MAP decision for that count.
    accumulator = [
        {
            "memory_state_count_A": k,
            "on_signal_A": k + 1 if k < observation_count else None,
            "on_signal_B": k,
            "on_end_of_stream": rows[k]["map_decision"],
        }
        for k in range(observation_count + 1)
    ]
    raw_check = _raw_history_check(
        n=observation_count, prior_a=prior_a, p_a_given_a=alpha,
        p_a_given_b=beta, count_rows=rows, max_histories=max_histories,
    )
    if Fraction(**raw_check["raw_history_accuracy"]) != accuracy:
        raise AssertionError("reported count accuracy differs from the raw-history check")

    statistic_state_count = observation_count + 1
    raw_history_count = 2 ** observation_count
    report: dict[str, Any] = {
        "format": FORMAT,
        "model": {
            "hidden_hypotheses": ["A", "B"],
            "observation_alphabet": ["A", "B"],
            "prior_A": _doc(prior_a),
            "prior_B": _doc(1 - prior_a),
            "p_signal_A_given_hypothesis_A": _doc(alpha),
            "p_signal_A_given_hypothesis_B": _doc(beta),
            "conditional_independence_assumption": "observations are iid conditional on the fixed hidden hypothesis",
        },
        "observation_count": observation_count,
        "sufficient_statistic": {
            "name": "count_A",
            "definition": "number of A observations in the fixed-length observation sequence",
            "state_count": statistic_state_count,
            "count_classes": rows,
            "factorization": "P(x_1..x_n | H) = p_H^k * (1-p_H)^(n-k), where k=count_A",
        },
        "full_history": raw_check,
        "accumulator": {
            "initial_memory_state": 0,
            "memory_state_count": statistic_state_count,
            "input_contract": "exactly observation_count signals followed by END",
            "transition_and_output_table": accumulator,
        },
        "summary": {
            "map_accuracy": _doc(accuracy),
            "bayes_error_probability": _doc(1 - accuracy),
            "raw_history_count": raw_history_count,
            "sufficient_statistic_state_count": statistic_state_count,
            "raw_histories_per_statistic_state": _doc(Fraction(raw_history_count, statistic_state_count)),
            "raw_history_state_reduction": raw_history_count - statistic_state_count,
        },
        "max_histories": max_histories,
    }
    report["content_digest"] = _sha256(report)
    return report


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute all likelihoods, decisions, and finite history checks."""
    if not isinstance(document, Mapping) or document.get("format") != FORMAT:
        raise ValueError("unsupported evidence-accumulation report")
    model = document.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("report model is missing")
    rebuilt = build_report(
        observation_count=document.get("observation_count"),
        prior_hypothesis_a=model.get("prior_A"),
        p_signal_a_given_hypothesis_a=model.get("p_signal_A_given_hypothesis_A"),
        p_signal_a_given_hypothesis_b=model.get("p_signal_A_given_hypothesis_B"),
        max_histories=document.get("max_histories"),
    )
    if dict(document) != rebuilt:
        raise ValueError("report differs from independent reconstruction")
    return rebuilt
