"""Exact one-step decision value of candidate context observations.

The input is a joint posterior over a binary hypothesis and an arbitrary finite
latent-context state. Candidate sensors provide exact outcome likelihoods for
each joint state. The module computes expected Bayes decision-loss reduction,
cost-normalized value, and a deterministic Pareto/ranking report. It does not
dispatch a measurement.
"""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from typing import Any, Mapping, Optional, Sequence

FORMAT = "in-formation.decision-value-context-acquisition/0.1"
BELIEF_FORMAT = "in-formation.joint-context-belief/0.1"
HYPOTHESES = ("A", "B")
_LOSS_KEYS = (
    "decide_a_if_hypothesis_a",
    "decide_a_if_hypothesis_b",
    "decide_b_if_hypothesis_a",
    "decide_b_if_hypothesis_b",
)
_SHA = set("0123456789abcdef")


class DecisionValueError(ValueError):
    """Invalid joint belief, sensor model, or decision-value report."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise DecisionValueError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise DecisionValueError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionValueError(f"{label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    digest = _text(value, label)
    if len(digest) != 64 or any(char not in _SHA for char in digest):
        raise DecisionValueError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _rational(
    value: object,
    label: str,
    *,
    nonnegative: bool = False,
    positive: bool = False,
    unit_interval: bool = False,
) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise DecisionValueError(
            f"{label} must be exact; floats and booleans are rejected"
        )
    try:
        if isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
            numerator, denominator = value["numerator"], value["denominator"]
            if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
                raise ValueError
            result = Fraction(numerator, denominator)
        else:
            result = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise DecisionValueError(f"{label} must be an exact rational") from error
    if nonnegative and result < 0:
        raise DecisionValueError(f"{label} must be non-negative")
    if positive and result <= 0:
        raise DecisionValueError(f"{label} must be positive")
    if unit_interval and not 0 <= result <= 1:
        raise DecisionValueError(f"{label} must be in [0, 1]")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _fraction_key(value: object, label: str) -> Optional[Fraction]:
    if value is None:
        return None
    return _rational(value, label, nonnegative=True)


def _scalar(value: object, label: str) -> object:
    if type(value) not in (str, int, bool, type(None)):
        raise DecisionValueError(
            f"{label} must be a string, integer, Boolean, or null"
        )
    _canonical(value)
    return value


def _normalize_joint_posterior(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)) or not raw:
        raise DecisionValueError("joint_posterior must be a non-empty sequence")
    normalized = []
    seen = set()
    total = Fraction(0)
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {
            "hypothesis", "context_state", "probability"
        }:
            raise DecisionValueError(
                f"joint_posterior[{index}] must contain hypothesis, context_state, probability"
            )
        hypothesis = item["hypothesis"]
        if hypothesis not in HYPOTHESES:
            raise DecisionValueError(
                f"joint_posterior[{index}].hypothesis must be A or B"
            )
        context_state = _text(
            item["context_state"],
            f"joint_posterior[{index}].context_state",
        )
        identity = (hypothesis, context_state)
        if identity in seen:
            raise DecisionValueError(
                f"duplicate joint belief coordinate: {identity!r}"
            )
        seen.add(identity)
        probability = _rational(
            item["probability"],
            f"joint_posterior[{index}].probability",
            unit_interval=True,
        )
        total += probability
        normalized.append({
            "hypothesis": hypothesis,
            "context_state": context_state,
            "probability": _fraction_doc(probability),
        })
    if total != 1:
        raise DecisionValueError(
            f"joint posterior probabilities must sum exactly to one, got {total}"
        )
    if not any(item["hypothesis"] == "A" for item in normalized):
        raise DecisionValueError("joint posterior must include hypothesis A coordinates")
    if not any(item["hypothesis"] == "B" for item in normalized):
        raise DecisionValueError("joint posterior must include hypothesis B coordinates")
    return normalized


def build_joint_belief_document(
    *,
    joint_posterior: Sequence[Mapping[str, Any]],
    source_ref: str,
    source_report_digest: str,
    source_state_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a content-bound joint belief from an upstream filter state.

    source_state_id may be supplied by an upstream filter (for example, RIV-006).
    If supplied, it must equal the digest of the ordered joint-posterior rows.
    This checks content identity, not external authenticity.
    """
    normalized = _normalize_joint_posterior(joint_posterior)
    state_digest = _digest(normalized)
    if source_state_id is not None:
        supplied_state_id = _sha256(source_state_id, "source_state_id")
        if supplied_state_id != state_digest:
            raise DecisionValueError(
                "source_state_id does not match the supplied joint posterior"
            )
    source = _text(source_ref, "source_ref")
    report_digest = _sha256(source_report_digest, "source_report_digest")
    posterior_a = sum(
        (
            Fraction(**item["probability"])
            for item in normalized
            if item["hypothesis"] == "A"
        ),
        Fraction(0),
    )
    context_marginals: dict[str, Fraction] = {}
    for item in normalized:
        label = item["context_state"]
        context_marginals[label] = context_marginals.get(label, Fraction(0)) + Fraction(
            **item["probability"]
        )
    core = {
        "format": BELIEF_FORMAT,
        "schema": "in-formation.joint-context-belief/0.1",
        "source_ref": source,
        "source_report_digest": report_digest,
        "source_state_id": state_digest,
        "joint_posterior": normalized,
        "posterior_hypothesis_a": _fraction_doc(posterior_a),
        "posterior_context_marginals": {
            label: _fraction_doc(value)
            for label, value in sorted(context_marginals.items())
        },
    }
    return {**core, "belief_digest": _digest(core)}


def _validate_belief_document(raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError("joint belief document must be an object")
    belief = _copy_json(raw, "joint belief document")
    expected = {
        "format", "schema", "source_ref", "source_report_digest",
        "source_state_id", "joint_posterior", "posterior_hypothesis_a",
        "posterior_context_marginals", "belief_digest",
    }
    if set(belief) != expected:
        raise DecisionValueError("joint belief document has missing or unexpected fields")
    if belief["format"] != BELIEF_FORMAT or belief["schema"] != BELIEF_FORMAT:
        # The schema label intentionally matches the versioned belief format.
        raise DecisionValueError("unsupported joint belief format/schema")
    supplied_digest = _sha256(belief["belief_digest"], "belief_digest")
    core = {key: value for key, value in belief.items() if key != "belief_digest"}
    if supplied_digest != _digest(core):
        raise DecisionValueError("joint belief digest does not match its contents")
    rebuilt = build_joint_belief_document(
        joint_posterior=belief["joint_posterior"],
        source_ref=belief["source_ref"],
        source_report_digest=belief["source_report_digest"],
        source_state_id=belief["source_state_id"],
    )
    if rebuilt != belief:
        raise DecisionValueError("joint belief differs from independent reconstruction")
    return belief


def _normalize_loss_matrix(raw: Optional[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    if raw is None:
        raw = {
            "decide_a_if_hypothesis_a": 0,
            "decide_a_if_hypothesis_b": 1,
            "decide_b_if_hypothesis_a": 1,
            "decide_b_if_hypothesis_b": 0,
        }
    if not isinstance(raw, Mapping) or set(raw) != set(_LOSS_KEYS):
        raise DecisionValueError(
            f"loss_matrix must contain exactly {sorted(_LOSS_KEYS)}"
        )
    normalized = {
        key: _fraction_doc(
            _rational(raw[key], f"loss_matrix.{key}", nonnegative=True)
        )
        for key in _LOSS_KEYS
    }
    return normalized


def _belief_map(belief: Mapping[str, Any]):
    return {
        (item["hypothesis"], item["context_state"]): Fraction(**item["probability"])
        for item in belief["joint_posterior"]
    }


def _bayes_decision(
    joint: Mapping[tuple[str, str], Fraction],
    loss: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    posterior_a = sum(
        (probability for (hypothesis, _), probability in joint.items()
         if hypothesis == "A"),
        Fraction(0),
    )
    posterior_b = 1 - posterior_a
    loss_a = (
        posterior_a * Fraction(**loss["decide_a_if_hypothesis_a"])
        + posterior_b * Fraction(**loss["decide_a_if_hypothesis_b"])
    )
    loss_b = (
        posterior_a * Fraction(**loss["decide_b_if_hypothesis_a"])
        + posterior_b * Fraction(**loss["decide_b_if_hypothesis_b"])
    )
    decision = "A" if loss_a <= loss_b else "B"
    return {
        "posterior_hypothesis_a": _fraction_doc(posterior_a),
        "posterior_hypothesis_b": _fraction_doc(posterior_b),
        "expected_loss_if_decide_a": _fraction_doc(loss_a),
        "expected_loss_if_decide_b": _fraction_doc(loss_b),
        "optimal_decision": decision,
        "bayes_decision_loss": _fraction_doc(min(loss_a, loss_b)),
    }


def _normalize_candidates(
    raw: object,
    joint_posterior: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)) or not raw:
        raise DecisionValueError("candidate_sensors must be a non-empty sequence")
    if len(raw) > 64:
        raise DecisionValueError("candidate_sensors may contain at most 64 methods")
    state_keys = [
        (item["hypothesis"], item["context_state"])
        for item in joint_posterior
    ]
    normalized = []
    seen_sensor_ids = set()
    for index, candidate in enumerate(raw):
        if not isinstance(candidate, Mapping) or set(candidate) != {
            "sensor_id", "dimension", "cost", "outcomes"
        }:
            raise DecisionValueError(
                f"candidate_sensors[{index}] must contain sensor_id, dimension, cost, outcomes"
            )
        sensor_id = _text(candidate["sensor_id"], f"candidate_sensors[{index}].sensor_id")
        if sensor_id in seen_sensor_ids:
            raise DecisionValueError(f"duplicate sensor_id: {sensor_id}")
        seen_sensor_ids.add(sensor_id)
        dimension = _text(candidate["dimension"], f"{sensor_id}.dimension")
        cost = _rational(candidate["cost"], f"{sensor_id}.cost", positive=True)
        outcomes = candidate["outcomes"]
        if not isinstance(outcomes, (tuple, list)) or not outcomes:
            raise DecisionValueError(f"{sensor_id}.outcomes must be a non-empty sequence")
        normalized_outcomes = []
        seen_outcomes = set()
        sums = {key: Fraction(0) for key in state_keys}
        for outcome_index, outcome in enumerate(outcomes):
            if not isinstance(outcome, Mapping) or set(outcome) != {
                "outcome", "likelihoods"
            }:
                raise DecisionValueError(
                    f"{sensor_id}.outcomes[{outcome_index}] must contain outcome and likelihoods"
                )
            value = _scalar(
                outcome["outcome"],
                f"{sensor_id}.outcomes[{outcome_index}].outcome",
            )
            value_key = _canonical(value)
            if value_key in seen_outcomes:
                raise DecisionValueError(f"{sensor_id} has duplicate outcome values")
            seen_outcomes.add(value_key)
            likelihoods = outcome["likelihoods"]
            if not isinstance(likelihoods, (tuple, list)) or len(likelihoods) != len(state_keys):
                raise DecisionValueError(
                    f"{sensor_id}.{value!r} must specify a likelihood for every joint state"
                )
            likelihood_rows = []
            seen_states = set()
            for likelihood_index, item in enumerate(likelihoods):
                if not isinstance(item, Mapping) or set(item) != {
                    "hypothesis", "context_state", "probability"
                }:
                    raise DecisionValueError(
                        f"{sensor_id}.{value!r}.likelihoods[{likelihood_index}] is malformed"
                    )
                key = (
                    item["hypothesis"],
                    _text(
                        item["context_state"],
                        f"{sensor_id}.{value!r}.context_state",
                    ),
                )
                if key not in sums:
                    raise DecisionValueError(
                        f"{sensor_id}.{value!r} references a joint state absent from the belief"
                    )
                if key in seen_states:
                    raise DecisionValueError(
                        f"{sensor_id}.{value!r} repeats joint state {key!r}"
                    )
                seen_states.add(key)
                probability = _rational(
                    item["probability"],
                    f"{sensor_id}.{value!r}.likelihood",
                    unit_interval=True,
                )
                sums[key] += probability
                likelihood_rows.append({
                    "hypothesis": key[0],
                    "context_state": key[1],
                    "probability": _fraction_doc(probability),
                })
            if seen_states != set(state_keys):
                raise DecisionValueError(
                    f"{sensor_id}.{value!r} must cover every joint belief state exactly once"
                )
            likelihood_rows.sort(
                key=lambda item: (item["hypothesis"], item["context_state"])
            )
            normalized_outcomes.append({
                "outcome": value,
                "likelihoods": likelihood_rows,
            })
        if any(total != 1 for total in sums.values()):
            invalid = {
                str(key): str(total)
                for key, total in sums.items()
                if total != 1
            }
            raise DecisionValueError(
                f"{sensor_id} outcome likelihoods must sum to one for every joint state: {invalid}"
            )
        normalized_outcomes.sort(key=lambda item: _canonical(item["outcome"]))
        normalized.append({
            "sensor_id": sensor_id,
            "dimension": dimension,
            "cost": _fraction_doc(cost),
            "outcomes": normalized_outcomes,
        })
    return sorted(normalized, key=lambda item: item["sensor_id"])


def _evaluate_candidate(
    belief: Mapping[str, Any],
    candidate: Mapping[str, Any],
    loss: Mapping[str, Mapping[str, int]],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    current_joint = _belief_map(belief)
    branch_rows = []
    expected_posterior_loss = Fraction(0)
    probability_decision_changes = Fraction(0)
    for outcome in candidate["outcomes"]:
        likelihood_map = {
            (item["hypothesis"], item["context_state"]): Fraction(**item["probability"])
            for item in outcome["likelihoods"]
        }
        unnormalized = {
            key: probability * likelihood_map[key]
            for key, probability in current_joint.items()
        }
        outcome_probability = sum(unnormalized.values(), Fraction(0))
        if outcome_probability == 0:
            branch_rows.append({
                "outcome": outcome["outcome"],
                "predictive_probability": _fraction_doc(Fraction(0)),
                "reachable": False,
                "posterior_joint_belief": None,
                "posterior_decision": None,
                "posterior_bayes_decision_loss": None,
                "expected_loss_contribution": _fraction_doc(Fraction(0)),
                "decision_changed": False,
            })
            continue
        posterior = {
            key: probability / outcome_probability
            for key, probability in unnormalized.items()
        }
        decision = _bayes_decision(posterior, loss)
        conditional_loss = Fraction(**decision["bayes_decision_loss"])
        contribution = outcome_probability * conditional_loss
        expected_posterior_loss += contribution
        decision_changed = (
            decision["optimal_decision"] != baseline["optimal_decision"]
        )
        if decision_changed:
            probability_decision_changes += outcome_probability
        branch_rows.append({
            "outcome": outcome["outcome"],
            "predictive_probability": _fraction_doc(outcome_probability),
            "reachable": True,
            "posterior_joint_belief": [
                {
                    "hypothesis": hypothesis,
                    "context_state": context_state,
                    "probability": _fraction_doc(probability),
                }
                for (hypothesis, context_state), probability in sorted(posterior.items())
            ],
            "posterior_decision": decision,
            "posterior_bayes_decision_loss": _fraction_doc(conditional_loss),
            "expected_loss_contribution": _fraction_doc(contribution),
            "decision_changed": decision_changed,
        })
    current_loss = Fraction(**baseline["bayes_decision_loss"])
    value = current_loss - expected_posterior_loss
    if value < 0:
        raise AssertionError("expected information value cannot increase Bayes decision loss")
    cost = Fraction(**candidate["cost"])
    return {
        "sensor_id": candidate["sensor_id"],
        "dimension": candidate["dimension"],
        "cost": candidate["cost"],
        "outcomes": branch_rows,
        "expected_posterior_bayes_decision_loss": _fraction_doc(expected_posterior_loss),
        "expected_bayes_risk_reduction": _fraction_doc(value),
        "expected_value_per_cost": _fraction_doc(value / cost),
        "probability_of_changing_the_current_decision": _fraction_doc(
            probability_decision_changes
        ),
    }


def _frontier(candidate_reports: Sequence[Mapping[str, Any]]) -> list[str]:
    frontier = []
    for candidate in candidate_reports:
        cost = Fraction(**candidate["cost"])
        risk = Fraction(**candidate["expected_posterior_bayes_decision_loss"])
        dominated = False
        for other in candidate_reports:
            if other["sensor_id"] == candidate["sensor_id"]:
                continue
            other_cost = Fraction(**other["cost"])
            other_risk = Fraction(**other["expected_posterior_bayes_decision_loss"])
            if (
                other_cost <= cost
                and other_risk <= risk
                and (other_cost < cost or other_risk < risk)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate["sensor_id"])
    return sorted(frontier)


def build_report(
    *,
    joint_belief: Mapping[str, Any],
    candidate_sensors: Sequence[Mapping[str, Any]],
    loss_matrix: Optional[Mapping[str, Any]] = None,
    cost_budget: Optional[object] = None,
) -> dict[str, Any]:
    """Rank candidate observations by exact expected decision value per cost.

    A candidate observes the current latent-context state without changing it.
    Its finite outcomes are weighted by the caller-supplied conditional
    likelihood model. This is one-step expected value of sample information,
    not a worst-case VGI minimax policy or a multi-step optimal plan.
    """
    belief = _validate_belief_document(joint_belief)
    normalized_loss = _normalize_loss_matrix(loss_matrix)
    normalized_candidates = _normalize_candidates(
        candidate_sensors,
        belief["joint_posterior"],
    )
    budget = (
        None
        if cost_budget is None
        else _fraction_doc(_rational(cost_budget, "cost_budget", nonnegative=True))
    )
    baseline_joint = _belief_map(belief)
    baseline = _bayes_decision(baseline_joint, normalized_loss)
    scored = [
        _evaluate_candidate(
            belief,
            candidate,
            normalized_loss,
            baseline,
        )
        for candidate in normalized_candidates
    ]
    scored.sort(key=lambda item: item["sensor_id"])
    eligible = [
        item for item in scored
        if budget is None or Fraction(**item["cost"]) <= Fraction(**budget)
    ]
    if eligible:
        selected = min(
            eligible,
            key=lambda item: (
                -Fraction(**item["expected_value_per_cost"]),
                -Fraction(**item["expected_bayes_risk_reduction"]),
                Fraction(**item["cost"]),
                item["sensor_id"],
            ),
        )
        selected_id = selected["sensor_id"]
        selection_status = "selected"
    else:
        selected_id = None
        selection_status = "no_candidate_within_cost_budget"
    core = {
        "format": FORMAT,
        "schema": FORMAT,
        "source_joint_belief_digest": belief["belief_digest"],
        "source_report_digest": belief["source_report_digest"],
        "source_ref": belief["source_ref"],
        "source_state_id": belief["source_state_id"],
        "joint_belief": belief,
        "decision_loss_matrix": normalized_loss,
        "baseline_decision": baseline,
        "candidate_sensor_models": normalized_candidates,
        "candidate_evaluations": scored,
        "pareto_frontier_sensor_ids": _frontier(scored),
        "selection": {
            "status": selection_status,
            "objective": (
                "maximize_exact_expected_bayes_risk_reduction_per_cost; "
                "then maximize expected risk reduction; then minimize cost; "
                "then lexical sensor_id"
            ),
            "cost_budget": budget,
            "eligible_sensor_ids": sorted(item["sensor_id"] for item in eligible),
            "selected_sensor_id": selected_id,
        },
        "measurement_status": "proposal_only_not_dispatched",
        "ground_effect": "none",
        "model_effect": "none",
        "interpretation_limits": [
            "Candidate likelihoods are caller-supplied exact models over the supplied joint belief states; they are not observed sensor performance unless independently supported.",
            "Candidate measurements are assumed to read the current latent context without changing it during this one-step evaluation.",
            "The expected value is conditional on the supplied joint posterior, outcome likelihoods, task loss matrix, and candidate costs.",
            "The ranking is one-step expected Bayes decision-loss reduction per cost, not VGI's worst-case unresolved-pair minimax objective and not a multi-step optimal policy.",
            "A high value-per-cost result does not authenticate the sensor, source belief, calibration, or likelihood model.",
            "No measurement is dispatched, no ObservationPath is advanced, and no joint belief or source model is revised.",
            "SHA-256 digests provide content identity and reconstruction checks, not authentication of external evidence or actors.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute candidate likelihood ledgers, posterior branches, and selection."""
    if not isinstance(document, Mapping):
        raise TypeError("decision-value report must be an object")
    supplied = _copy_json(document, "decision-value report")
    digest = supplied.pop("report_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise DecisionValueError("report digest does not match contents")
    if supplied.get("format") != FORMAT or supplied.get("schema") != FORMAT:
        raise DecisionValueError("unsupported decision-value report format/schema")
    rebuilt = build_report(
        joint_belief=supplied.get("joint_belief"),
        candidate_sensors=supplied.get("candidate_sensor_models"),
        loss_matrix=supplied.get("decision_loss_matrix"),
        cost_budget=_fraction_doc_value(supplied.get("selection", {}).get("cost_budget")),
    )
    if rebuilt != dict(document):
        raise DecisionValueError(
            "report differs from independent reconstruction from retained joint belief and candidate models"
        )
    return dict(document)


def _fraction_doc_value(value: object):
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        raise DecisionValueError("cost budget must be an exact rational object or null")
    return _rational(value, "cost_budget", nonnegative=True)


__all__ = [
    "BELIEF_FORMAT",
    "DecisionValueError",
    "build_joint_belief_document",
    "build_report",
    "validate_report",
]
