"""Finite scenario-robust decision acquisition under likelihood ambiguity.

RIV-015 does not assign probabilities to alternative sensor-response models.
For each candidate it enumerates one outcome-to-action rule shared across the
entire finite ambiguity set, evaluates that rule under every model, and
minimizes worst-case expected decision loss. A no-measurement constant policy
is always available, so robust value cannot be negative.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from fractions import Fraction
from typing import Any, Mapping, Optional, Sequence

FORMAT = "in-formation.robust-likelihood-acquisition/0.1"
BELIEF_FORMAT = "in-formation.joint-context-belief/0.1"
HYPOTHESES = ("A", "B")
ACTIONS = ("A", "B")
_LOSS_KEYS = (
    "decide_a_if_hypothesis_a",
    "decide_a_if_hypothesis_b",
    "decide_b_if_hypothesis_a",
    "decide_b_if_hypothesis_b",
)
_HEX = set("0123456789abcdef")
_MAX_CANDIDATES = 32
_MAX_SCENARIOS = 32
_MAX_OUTCOMES = 8
_MAX_POLICY_EVALUATIONS = 32768


class RobustAcquisitionError(ValueError):
    """Invalid belief, ambiguity set, candidate, or robust acquisition report."""


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
        raise RobustAcquisitionError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise RobustAcquisitionError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise RobustAcquisitionError(
            f"{label} must be non-empty text without NUL"
        )
    return value.strip()


def _sha256(value: object, label: str) -> str:
    digest = _text(value, label)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise RobustAcquisitionError(
            f"{label} must be a lowercase SHA-256 digest"
        )
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
        raise RobustAcquisitionError(
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
        raise RobustAcquisitionError(
            f"{label} must be an exact rational"
        ) from error
    if nonnegative and result < 0:
        raise RobustAcquisitionError(f"{label} must be non-negative")
    if positive and result <= 0:
        raise RobustAcquisitionError(f"{label} must be positive")
    if unit_interval and not 0 <= result <= 1:
        raise RobustAcquisitionError(f"{label} must be in [0, 1]")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _scalar(value: object, label: str) -> object:
    if type(value) not in (str, int, bool, type(None)):
        raise RobustAcquisitionError(
            f"{label} must be a string, integer, Boolean, or null"
        )
    _canonical(value)
    return value


def build_joint_belief_document(
    *,
    joint_posterior: Sequence[Mapping[str, Any]],
    source_ref: str,
    source_report_digest: str,
) -> dict[str, Any]:
    """Build a RIV-008-compatible content-bound joint belief document."""
    if not isinstance(joint_posterior, (tuple, list)) or not joint_posterior:
        raise RobustAcquisitionError("joint_posterior must be a non-empty sequence")
    normalized = []
    seen = set()
    total = Fraction(0)
    for index, item in enumerate(joint_posterior):
        if not isinstance(item, Mapping) or set(item) != {
            "hypothesis", "context_state", "probability"
        }:
            raise RobustAcquisitionError(
                f"joint_posterior[{index}] must contain hypothesis, context_state, probability"
            )
        hypothesis = item["hypothesis"]
        if hypothesis not in HYPOTHESES:
            raise RobustAcquisitionError(
                f"joint_posterior[{index}].hypothesis must be A or B"
            )
        context_state = _text(
            item["context_state"],
            f"joint_posterior[{index}].context_state",
        )
        key = (hypothesis, context_state)
        if key in seen:
            raise RobustAcquisitionError(f"duplicate joint state: {key!r}")
        seen.add(key)
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
        raise RobustAcquisitionError(
            f"joint posterior probabilities must sum exactly to one, got {total}"
        )
    if {row["hypothesis"] for row in normalized} != set(HYPOTHESES):
        raise RobustAcquisitionError("joint posterior must include both hypotheses")
    normalized.sort(key=lambda row: (row["hypothesis"], row["context_state"]))
    posterior_a = sum(
        (
            Fraction(**row["probability"])
            for row in normalized
            if row["hypothesis"] == "A"
        ),
        Fraction(0),
    )
    context_marginals: dict[str, Fraction] = {}
    for row in normalized:
        context = row["context_state"]
        context_marginals[context] = context_marginals.get(context, Fraction(0)) + Fraction(
            **row["probability"]
        )
    core = {
        "format": BELIEF_FORMAT,
        "schema": BELIEF_FORMAT,
        "source_ref": _text(source_ref, "source_ref"),
        "source_report_digest": _sha256(source_report_digest, "source_report_digest"),
        "source_state_id": _digest(normalized),
        "joint_posterior": normalized,
        "posterior_hypothesis_a": _fraction_doc(posterior_a),
        "posterior_context_marginals": {
            key: _fraction_doc(value)
            for key, value in sorted(context_marginals.items())
        },
    }
    return {**core, "belief_digest": _digest(core)}


def _validate_belief(raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError("joint_belief must be an object")
    belief = _copy_json(raw, "joint_belief")
    required = {
        "format", "schema", "source_ref", "source_report_digest",
        "source_state_id", "joint_posterior", "posterior_hypothesis_a",
        "posterior_context_marginals", "belief_digest",
    }
    if set(belief) != required:
        raise RobustAcquisitionError(
            "joint belief has missing or unexpected fields"
        )
    if belief["format"] != BELIEF_FORMAT or belief["schema"] != BELIEF_FORMAT:
        raise RobustAcquisitionError("unsupported joint belief format/schema")
    supplied_digest = _sha256(belief["belief_digest"], "belief_digest")
    core = {key: value for key, value in belief.items() if key != "belief_digest"}
    if supplied_digest != _digest(core):
        raise RobustAcquisitionError("joint belief digest does not match its contents")
    rebuilt = build_joint_belief_document(
        joint_posterior=belief["joint_posterior"],
        source_ref=belief["source_ref"],
        source_report_digest=belief["source_report_digest"],
    )
    if rebuilt != belief:
        raise RobustAcquisitionError(
            "joint belief differs from independent reconstruction"
        )
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
        raise RobustAcquisitionError(
            f"loss_matrix must contain exactly {sorted(_LOSS_KEYS)}"
        )
    return {
        key: _fraction_doc(
            _rational(raw[key], f"loss_matrix.{key}", nonnegative=True)
        )
        for key in _LOSS_KEYS
    }


def _normalize_candidates(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)) or not raw:
        raise RobustAcquisitionError("candidate_sensors must be a non-empty sequence")
    if len(raw) > _MAX_CANDIDATES:
        raise RobustAcquisitionError(
            f"candidate_sensors may contain at most {_MAX_CANDIDATES} methods"
        )
    result = []
    seen = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {
            "sensor_id", "dimension", "cost", "outcomes"
        }:
            raise RobustAcquisitionError(
                f"candidate_sensors[{index}] must contain sensor_id, dimension, cost, outcomes"
            )
        sensor_id = _text(item["sensor_id"], f"candidate_sensors[{index}].sensor_id")
        if sensor_id in seen:
            raise RobustAcquisitionError(f"duplicate candidate sensor_id: {sensor_id}")
        seen.add(sensor_id)
        outcomes = item["outcomes"]
        if not isinstance(outcomes, (tuple, list)) or not outcomes:
            raise RobustAcquisitionError(f"{sensor_id}.outcomes must be non-empty")
        if len(outcomes) > _MAX_OUTCOMES:
            raise RobustAcquisitionError(
                f"{sensor_id}.outcomes may contain at most {_MAX_OUTCOMES} values"
            )
        normalized_outcomes = [
            _scalar(value, f"{sensor_id}.outcomes[{i}]")
            for i, value in enumerate(outcomes)
        ]
        keys = [_canonical(value) for value in normalized_outcomes]
        if len(keys) != len(set(keys)):
            raise RobustAcquisitionError(f"{sensor_id} has duplicate outcome labels")
        result.append({
            "sensor_id": sensor_id,
            "dimension": _text(item["dimension"], f"{sensor_id}.dimension"),
            "cost": _fraction_doc(
                _rational(item["cost"], f"{sensor_id}.cost", positive=True)
            ),
            "outcomes": [
                value for _, value in sorted(zip(keys, normalized_outcomes), key=lambda pair: pair[0])
            ],
        })
    return sorted(result, key=lambda row: row["sensor_id"])


def _state_keys(belief: Mapping[str, Any]):
    return [
        (row["hypothesis"], row["context_state"])
        for row in belief["joint_posterior"]
    ]


def _normalize_scenarios(
    raw: object,
    candidates: Sequence[Mapping[str, Any]],
    belief: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(raw, (tuple, list)) or not raw:
        raise RobustAcquisitionError(
            "model_scenarios must be a non-empty finite ambiguity set"
        )
    if len(raw) > _MAX_SCENARIOS:
        raise RobustAcquisitionError(
            f"model_scenarios may contain at most {_MAX_SCENARIOS} scenarios"
        )
    expected_candidate_ids = {row["sensor_id"] for row in candidates}
    state_keys = _state_keys(belief)
    normalized = []
    seen_scenarios = set()
    candidate_by_id = {row["sensor_id"]: row for row in candidates}
    for index, scenario in enumerate(raw):
        if not isinstance(scenario, Mapping) or set(scenario) != {
            "scenario_id", "candidate_models"
        }:
            raise RobustAcquisitionError(
                f"model_scenarios[{index}] must contain scenario_id and candidate_models"
            )
        scenario_id = _text(
            scenario["scenario_id"],
            f"model_scenarios[{index}].scenario_id",
        )
        if scenario_id in seen_scenarios:
            raise RobustAcquisitionError(f"duplicate scenario_id: {scenario_id}")
        seen_scenarios.add(scenario_id)
        raw_models = scenario["candidate_models"]
        if not isinstance(raw_models, (tuple, list)):
            raise RobustAcquisitionError(
                f"{scenario_id}.candidate_models must be a sequence"
            )
        model_ids = [
            item.get("sensor_id") if isinstance(item, Mapping) else None
            for item in raw_models
        ]
        if len(model_ids) != len(set(model_ids)) or set(model_ids) != expected_candidate_ids:
            raise RobustAcquisitionError(
                f"{scenario_id} must define every candidate sensor exactly once"
            )
        model_rows = []
        for model in raw_models:
            sensor_id = model["sensor_id"]
            if set(model) != {"sensor_id", "outcome_likelihoods"}:
                raise RobustAcquisitionError(
                    f"{scenario_id}.{sensor_id} must contain sensor_id and outcome_likelihoods"
                )
            candidate = candidate_by_id[sensor_id]
            raw_outcomes = model["outcome_likelihoods"]
            if not isinstance(raw_outcomes, (tuple, list)):
                raise RobustAcquisitionError(
                    f"{scenario_id}.{sensor_id}.outcome_likelihoods must be a sequence"
                )
            if len(raw_outcomes) != len(candidate["outcomes"]):
                raise RobustAcquisitionError(
                    f"{scenario_id}.{sensor_id} has the wrong outcome count"
                )
            outcome_map = {}
            for outcome_row in raw_outcomes:
                if not isinstance(outcome_row, Mapping) or set(outcome_row) != {
                    "outcome", "likelihoods"
                }:
                    raise RobustAcquisitionError(
                        f"{scenario_id}.{sensor_id} outcome row is malformed"
                    )
                label = _scalar(
                    outcome_row["outcome"],
                    f"{scenario_id}.{sensor_id}.outcome",
                )
                key = _canonical(label)
                if key in outcome_map:
                    raise RobustAcquisitionError(
                        f"{scenario_id}.{sensor_id} repeats outcome {label!r}"
                    )
                likelihoods = outcome_row["likelihoods"]
                if not isinstance(likelihoods, (tuple, list)) or len(likelihoods) != len(state_keys):
                    raise RobustAcquisitionError(
                        f"{scenario_id}.{sensor_id}.{label!r} must cover every joint state"
                    )
                probabilities = {}
                for likelihood in likelihoods:
                    if not isinstance(likelihood, Mapping) or set(likelihood) != {
                        "hypothesis", "context_state", "probability"
                    }:
                        raise RobustAcquisitionError(
                            f"{scenario_id}.{sensor_id}.{label!r} likelihood is malformed"
                        )
                    state_key = (
                        likelihood["hypothesis"],
                        _text(
                            likelihood["context_state"],
                            f"{scenario_id}.{sensor_id}.{label!r}.context_state",
                        ),
                    )
                    if state_key not in state_keys or state_key in probabilities:
                        raise RobustAcquisitionError(
                            f"{scenario_id}.{sensor_id}.{label!r} has an unknown or duplicate state"
                        )
                    probabilities[state_key] = _rational(
                        likelihood["probability"],
                        f"{scenario_id}.{sensor_id}.{label!r}.probability",
                        unit_interval=True,
                    )
                if set(probabilities) != set(state_keys):
                    raise RobustAcquisitionError(
                        f"{scenario_id}.{sensor_id}.{label!r} must cover each state exactly once"
                    )
                outcome_map[key] = (label, probabilities)
            expected_labels = {_canonical(value) for value in candidate["outcomes"]}
            if set(outcome_map) != expected_labels:
                raise RobustAcquisitionError(
                    f"{scenario_id}.{sensor_id} outcome labels differ from candidate declaration"
                )
            rows = []
            for label in candidate["outcomes"]:
                _, probabilities = outcome_map[_canonical(label)]
                rows.append({
                    "outcome": label,
                    "likelihoods": [
                        {
                            "hypothesis": hypothesis,
                            "context_state": context_state,
                            "probability": _fraction_doc(probabilities[(hypothesis, context_state)]),
                        }
                        for hypothesis, context_state in state_keys
                    ],
                })
            for state_key in state_keys:
                total = sum(
                    (
                        outcome_map[_canonical(label)][1][state_key]
                        for label in candidate["outcomes"]
                    ),
                    Fraction(0),
                )
                if total != 1:
                    raise RobustAcquisitionError(
                        f"{scenario_id}.{sensor_id} outcome likelihoods for {state_key!r} sum to {total}, not one"
                    )
            model_rows.append({"sensor_id": sensor_id, "outcome_likelihoods": rows})
        normalized.append({
            "scenario_id": scenario_id,
            "candidate_models": sorted(model_rows, key=lambda row: row["sensor_id"]),
        })
    return sorted(normalized, key=lambda row: row["scenario_id"])


def _loss_for_action(
    action: str,
    hypothesis: str,
    loss: Mapping[str, Mapping[str, int]],
) -> Fraction:
    if action == "A" and hypothesis == "A":
        key = "decide_a_if_hypothesis_a"
    elif action == "A":
        key = "decide_a_if_hypothesis_b"
    elif hypothesis == "A":
        key = "decide_b_if_hypothesis_a"
    else:
        key = "decide_b_if_hypothesis_b"
    return Fraction(**loss[key])


def _baseline_decision(
    belief: Mapping[str, Any],
    loss: Mapping[str, Mapping[str, int]],
):
    joint = {
        (row["hypothesis"], row["context_state"]): Fraction(**row["probability"])
        for row in belief["joint_posterior"]
    }
    risks = {}
    for action in ACTIONS:
        risks[action] = sum(
            (
                probability * _loss_for_action(action, hypothesis, loss)
                for (hypothesis, _), probability in joint.items()
            ),
            Fraction(0),
        )
    best = min(ACTIONS, key=lambda action: (risks[action], action))
    return {
        "action": best,
        "risk_by_action": {
            action: _fraction_doc(risks[action])
            for action in ACTIONS
        },
        "worst_case_baseline_risk": _fraction_doc(risks[best]),
    }, joint


def _policy_assignments(outcomes: Sequence[object]):
    for actions in itertools.product(ACTIONS, repeat=len(outcomes)):
        yield {
            _canonical(outcome): action
            for outcome, action in zip(outcomes, actions)
        }


def _evaluate_policy(
    *,
    policy: Mapping[str, str],
    candidate: Mapping[str, Any],
    scenario: Mapping[str, Any],
    joint: Mapping[tuple[str, str], Fraction],
    loss: Mapping[str, Mapping[str, int]],
):
    model = next(
        row for row in scenario["candidate_models"]
        if row["sensor_id"] == candidate["sensor_id"]
    )
    total = Fraction(0)
    outcome_rows = []
    for outcome in model["outcome_likelihoods"]:
        label = outcome["outcome"]
        action = policy[_canonical(label)]
        likelihoods = {
            (row["hypothesis"], row["context_state"]): Fraction(**row["probability"])
            for row in outcome["likelihoods"]
        }
        predictive_probability = sum(
            (probability * likelihoods[state] for state, probability in joint.items()),
            Fraction(0),
        )
        expected_loss_contribution = sum(
            (
                probability
                * likelihoods[state]
                * _loss_for_action(action, state[0], loss)
                for state, probability in joint.items()
            ),
            Fraction(0),
        )
        total += expected_loss_contribution
        outcome_rows.append({
            "outcome": label,
            "action": action,
            "predictive_probability": _fraction_doc(predictive_probability),
            "expected_loss_contribution": _fraction_doc(expected_loss_contribution),
        })
    return total, outcome_rows


def _scenario_oracle_risk(
    *,
    candidate: Mapping[str, Any],
    scenario: Mapping[str, Any],
    joint: Mapping[tuple[str, str], Fraction],
    loss: Mapping[str, Mapping[str, int]],
):
    risks = []
    for policy in _policy_assignments(candidate["outcomes"]):
        risk, _ = _evaluate_policy(
            policy=policy,
            candidate=candidate,
            scenario=scenario,
            joint=joint,
            loss=loss,
        )
        risks.append(risk)
    return min(risks)


def _evaluate_candidate(
    *,
    candidate: Mapping[str, Any],
    scenarios: Sequence[Mapping[str, Any]],
    joint: Mapping[tuple[str, str], Fraction],
    loss: Mapping[str, Mapping[str, int]],
    baseline_risk: Fraction,
):
    policy_count = 2 ** len(candidate["outcomes"])
    if policy_count * len(scenarios) > _MAX_POLICY_EVALUATIONS:
        raise RobustAcquisitionError(
            f"{candidate['sensor_id']} requires {policy_count * len(scenarios)} "
            f"policy/scenario evaluations; cap is {_MAX_POLICY_EVALUATIONS}"
        )
    scenario_oracle = {
        scenario["scenario_id"]: _scenario_oracle_risk(
            candidate=candidate,
            scenario=scenario,
            joint=joint,
            loss=loss,
        )
        for scenario in scenarios
    }
    policy_rows = []
    for policy in _policy_assignments(candidate["outcomes"]):
        scenario_rows = []
        for scenario in scenarios:
            risk, outcome_rows = _evaluate_policy(
                policy=policy,
                candidate=candidate,
                scenario=scenario,
                joint=joint,
                loss=loss,
            )
            regret = risk - scenario_oracle[scenario["scenario_id"]]
            if regret < 0:
                raise AssertionError("policy regret cannot be negative")
            scenario_rows.append({
                "scenario_id": scenario["scenario_id"],
                "expected_decision_loss": _fraction_doc(risk),
                "scenario_oracle_risk": _fraction_doc(
                    scenario_oracle[scenario["scenario_id"]]
                ),
                "regret_to_scenario_oracle": _fraction_doc(regret),
                "outcome_evaluations": outcome_rows,
            })
        worst_case_risk = max(
            Fraction(**row["expected_decision_loss"])
            for row in scenario_rows
        )
        worst_case_regret = max(
            Fraction(**row["regret_to_scenario_oracle"])
            for row in scenario_rows
        )
        worst_case_scenarios = sorted(
            row["scenario_id"]
            for row in scenario_rows
            if Fraction(**row["expected_decision_loss"]) == worst_case_risk
        )
        policy_rows.append({
            "outcome_to_action": [
                {
                    "outcome": outcome,
                    "action": policy[_canonical(outcome)],
                }
                for outcome in candidate["outcomes"]
            ],
            "scenario_evaluations": scenario_rows,
            "worst_case_expected_decision_loss": _fraction_doc(worst_case_risk),
            "worst_case_regret_to_scenario_oracle": _fraction_doc(worst_case_regret),
            "worst_case_scenario_ids": worst_case_scenarios,
        })
    chosen = min(
        policy_rows,
        key=lambda row: (
            Fraction(**row["worst_case_expected_decision_loss"]),
            Fraction(**row["worst_case_regret_to_scenario_oracle"]),
            tuple(item["action"] for item in row["outcome_to_action"]),
        ),
    )
    robust_risk = Fraction(**chosen["worst_case_expected_decision_loss"])
    robust_value = baseline_risk - robust_risk
    if robust_value < 0:
        raise AssertionError(
            "robust measurement policy cannot be worse than a constant no-measurement action"
        )
    cost = Fraction(**candidate["cost"])
    return {
        "sensor_id": candidate["sensor_id"],
        "dimension": candidate["dimension"],
        "cost": candidate["cost"],
        "outcomes": candidate["outcomes"],
        "policy_count": policy_count,
        "selected_robust_policy": chosen,
        "worst_case_expected_decision_loss": _fraction_doc(robust_risk),
        "worst_case_regret_to_scenario_oracle": chosen["worst_case_regret_to_scenario_oracle"],
        "worst_case_scenario_ids": chosen["worst_case_scenario_ids"],
        "robust_expected_loss_reduction": _fraction_doc(robust_value),
        "robust_value_per_cost": _fraction_doc(robust_value / cost),
        "scenario_oracle_risks": {
            key: _fraction_doc(value)
            for key, value in sorted(scenario_oracle.items())
        },
        "policy_evaluations": policy_rows,
    }


def _pareto_frontier(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    result = []
    for row in rows:
        cost = Fraction(**row["cost"])
        risk = Fraction(**row["worst_case_expected_decision_loss"])
        dominated = False
        for other in rows:
            if other["sensor_id"] == row["sensor_id"]:
                continue
            other_cost = Fraction(**other["cost"])
            other_risk = Fraction(**other["worst_case_expected_decision_loss"])
            if (
                other_cost <= cost
                and other_risk <= risk
                and (other_cost < cost or other_risk < risk)
            ):
                dominated = True
                break
        if not dominated:
            result.append(row["sensor_id"])
    return sorted(result)


def build_report(
    *,
    joint_belief: Mapping[str, Any],
    candidate_sensors: Sequence[Mapping[str, Any]],
    model_scenarios: Sequence[Mapping[str, Any]],
    loss_matrix: Optional[Mapping[str, Any]] = None,
    cost_budget: Optional[object] = None,
) -> dict[str, Any]:
    """Select one outcome-to-action rule minimizing worst-case expected loss.

    The finite likelihood ambiguity set is unweighted: no scenario probabilities
    are invented. Each candidate uses one action mapping across all scenarios.
    The no-measurement constant action is always available as a comparator.
    """
    belief = _validate_belief(joint_belief)
    candidates = _normalize_candidates(candidate_sensors)
    scenarios = _normalize_scenarios(model_scenarios, candidates, belief)
    if (
        sum(2 ** len(candidate["outcomes"]) * len(scenarios) for candidate in candidates)
        > _MAX_POLICY_EVALUATIONS * len(candidates)
    ):
        raise RobustAcquisitionError("total policy/scenario evaluation count exceeds cap")
    loss = _normalize_loss_matrix(loss_matrix)
    budget = (
        None
        if cost_budget is None
        else _fraction_doc(_rational(cost_budget, "cost_budget", nonnegative=True))
    )
    baseline, joint = _baseline_decision(belief, loss)
    baseline_risk = Fraction(**baseline["worst_case_baseline_risk"])
    evaluations = [
        _evaluate_candidate(
            candidate=candidate,
            scenarios=scenarios,
            joint=joint,
            loss=loss,
            baseline_risk=baseline_risk,
        )
        for candidate in candidates
    ]
    evaluations.sort(key=lambda row: row["sensor_id"])
    eligible = [
        row for row in evaluations
        if budget is None or Fraction(**row["cost"]) <= Fraction(**budget)
    ]
    improving = [
        row for row in eligible
        if Fraction(**row["robust_expected_loss_reduction"]) > 0
    ]
    if improving:
        selected = min(
            improving,
            key=lambda row: (
                -Fraction(**row["robust_value_per_cost"]),
                -Fraction(**row["robust_expected_loss_reduction"]),
                Fraction(**row["cost"]),
                row["sensor_id"],
            ),
        )
        selection = {
            "status": "selected_robust_measurement_policy",
            "selected_sensor_id": selected["sensor_id"],
            "selected_outcome_to_action": selected["selected_robust_policy"]["outcome_to_action"],
        }
    else:
        selection = {
            "status": (
                "no_candidate_within_cost_budget"
                if not eligible
                else "stop_no_positive_worst_case_value"
            ),
            "selected_sensor_id": None,
            "selected_outcome_to_action": None,
        }
    core = {
        "format": FORMAT,
        "schema": FORMAT,
        "joint_belief": belief,
        "source_joint_belief_digest": belief["belief_digest"],
        "source_report_digest": belief["source_report_digest"],
        "source_ref": belief["source_ref"],
        "decision_loss_matrix": loss,
        "ambiguity_set": {
            "scenario_ids": [row["scenario_id"] for row in scenarios],
            "scenario_count": len(scenarios),
            "scenario_weights": None,
            "interpretation": (
                "finite unweighted ambiguity set; every scenario is treated as a plausible "
                "likelihood model and no probability is assigned to model identity"
            ),
        },
        "candidate_sensors": candidates,
        "model_scenarios": scenarios,
        "baseline_decision": {
            "action": baseline["action"],
            "risk_by_action": baseline["risk_by_action"],
            "worst_case_no_measurement_risk": baseline["worst_case_baseline_risk"],
        },
        "candidate_evaluations": evaluations,
        "pareto_frontier_sensor_ids": _pareto_frontier(evaluations),
        "selection": {
            **selection,
            "objective": (
                "for each candidate choose one deterministic outcome-to-action map "
                "minimizing maximum expected loss across all ambiguity scenarios; "
                "rank candidates by worst-case loss reduction per exact cost"
            ),
            "tie_break": (
                "higher robust loss reduction; lower cost; lexical sensor_id; "
                "within a sensor, lower worst-case regret to scenario-oracle policies, "
                "then lexical A/B action mapping"
            ),
            "cost_budget": budget,
            "eligible_sensor_ids": sorted(row["sensor_id"] for row in eligible),
            "improving_sensor_ids": sorted(row["sensor_id"] for row in improving),
        },
        "measurement_status": "proposal_only_not_dispatched",
        "ground_effect": "none",
        "model_effect": "none",
        "interpretation_limits": [
            "The ambiguity scenarios are caller-supplied exact likelihood models; the set does not establish that the true sensor model is included.",
            "No probabilities are assigned to model scenarios. Results are worst-case over the finite declared ambiguity set, not Bayesian model averaging.",
            "Each candidate uses one outcome-to-action policy shared across all scenarios; the decision maker is not told which scenario is true.",
            "Scenario-oracle risks are diagnostic lower bounds that assume the model identity is known; they are not implementable policies under unresolved model ambiguity.",
            "The no-measurement comparator is an action chosen from the same joint belief and loss matrix; constant outcome policies ensure robust loss reduction cannot be negative.",
            "Costs are caller-supplied exact rationals in one common unit. They are not measured dispatch, admission, transport, authority, interpretation, latency, or energy costs.",
            "The experiment assumes a passive observation that does not change the joint state while being acquired.",
            "The result is exact only for the supplied finite joint belief, finite outcome sets, loss matrix, candidate costs, and ambiguity scenarios.",
            "No measurement is dispatched, no ObservationPath is advanced, and no joint belief or source model is revised.",
            "SHA-256 digests provide content identity and reconstruction checks, not authentication of sources, model truth, reviewer authority, or physical measurements.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Independently reconstruct policy enumeration, scenario losses, and selection."""
    if not isinstance(document, Mapping):
        raise TypeError("robust acquisition report must be an object")
    supplied = _copy_json(document, "robust acquisition report")
    digest = supplied.pop("report_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise RobustAcquisitionError("report digest does not match contents")
    if supplied.get("format") != FORMAT or supplied.get("schema") != FORMAT:
        raise RobustAcquisitionError("unsupported robust acquisition report")
    budget_doc = supplied.get("selection", {}).get("cost_budget")
    budget = None if budget_doc is None else _rational(
        budget_doc, "cost_budget", nonnegative=True
    )
    rebuilt = build_report(
        joint_belief=supplied.get("joint_belief"),
        candidate_sensors=supplied.get("candidate_sensors"),
        model_scenarios=supplied.get("model_scenarios"),
        loss_matrix=supplied.get("decision_loss_matrix"),
        cost_budget=budget,
    )
    if rebuilt != dict(document):
        raise RobustAcquisitionError(
            "report differs from independent reconstruction from retained belief and ambiguity set"
        )
    return dict(document)


__all__ = [
    "BELIEF_FORMAT",
    "FORMAT",
    "RobustAcquisitionError",
    "build_joint_belief_document",
    "build_report",
    "validate_report",
]
