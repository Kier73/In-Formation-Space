"""Exact finite-horizon robust sensor acquisition with one persistent model scenario.

RIV-016 extends RIV-015 from one measurement to an adaptive policy tree. The
model scenario is fixed for the entire run. A single policy tree maps observed
outcome histories to sensor choices or terminal actions and is evaluated under
every scenario. The minimax objective is taken only at the root, not separately
inside each outcome branch.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from fractions import Fraction
from functools import reduce
from operator import mul
from typing import Any, Mapping, Optional, Sequence

from robust_likelihood_acquisition import build_report as _build_riv015_report

FORMAT = "in-formation.robust-sequential-acquisition/0.1"
_MAX_SENSORS = 6
_MAX_SCENARIOS = 8
_MAX_OUTCOMES_PER_SENSOR = 4
_DEFAULT_MAX_DP_STATES = 20_000
_DEFAULT_MAX_FRONTIER_SIZE = 512
_DEFAULT_MAX_POLICY_COMBINATIONS = 50_000


class RobustSequentialError(ValueError):
    """Invalid robust sequential acquisition model or unreconstructable report."""


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
        raise RobustSequentialError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise RobustSequentialError(f"{label} must be finite JSON data") from error


def _fraction(value: object, label: str, *, nonnegative=False) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise RobustSequentialError(
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
        raise RobustSequentialError(f"{label} must be an exact rational") from error
    if nonnegative and result < 0:
        raise RobustSequentialError(f"{label} must be non-negative")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _loss_for_action(
    action: str,
    hypothesis: str,
    loss_matrix: Mapping[str, Mapping[str, int]],
) -> Fraction:
    if action == "A" and hypothesis == "A":
        key = "decide_a_if_hypothesis_a"
    elif action == "A":
        key = "decide_a_if_hypothesis_b"
    elif hypothesis == "A":
        key = "decide_b_if_hypothesis_a"
    else:
        key = "decide_b_if_hypothesis_b"
    return Fraction(**loss_matrix[key])


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Componentwise dominance across all model losses/costs and path resources."""
    comparisons = []
    comparisons.extend(
        a <= b for a, b in zip(left["risk_vector"], right["risk_vector"])
    )
    comparisons.extend(
        a <= b for a, b in zip(left["cost_vector"], right["cost_vector"])
    )
    comparisons.append(left["max_path_cost"] <= right["max_path_cost"])
    comparisons.append(
        left["max_measurements_on_path"] <= right["max_measurements_on_path"]
    )
    return all(comparisons) and any(
        a < b
        for a, b in zip(
            left["risk_vector"] + left["cost_vector"]
            + (left["max_path_cost"], Fraction(left["max_measurements_on_path"])),
            right["risk_vector"] + right["cost_vector"]
            + (right["max_path_cost"], Fraction(right["max_measurements_on_path"])),
        )
    )


def _entry_metrics(entry: Mapping[str, Any]):
    return (
        entry["risk_vector"],
        entry["cost_vector"],
        entry["max_path_cost"],
        entry["max_measurements_on_path"],
    )


def _prune_frontier(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_frontier_size: int,
    metrics: dict[str, int],
) -> list[dict[str, Any]]:
    """Retain risk/cost/path-resource Pareto-incomparable policy trees."""
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            row["risk_vector"],
            row["cost_vector"],
            row["max_path_cost"],
            row["max_measurements_on_path"],
            _canonical(row["policy_tree"]),
        ),
    )
    frontier: list[dict[str, Any]] = []
    for candidate in ordered:
        duplicate_index = next(
            (
                index for index, existing in enumerate(frontier)
                if _entry_metrics(existing) == _entry_metrics(candidate)
            ),
            None,
        )
        if duplicate_index is not None:
            existing = frontier[duplicate_index]
            if _canonical(candidate["policy_tree"]) < _canonical(existing["policy_tree"]):
                frontier[duplicate_index] = candidate
            continue
        if any(_dominates(existing, candidate) for existing in frontier):
            continue
        frontier = [
            existing for existing in frontier
            if not _dominates(candidate, existing)
        ]
        frontier.append(candidate)
        if len(frontier) > max_frontier_size:
            raise RobustSequentialError(
                f"Pareto frontier exceeded declared cap {max_frontier_size}"
            )
    frontier.sort(
        key=lambda row: (
            row["risk_vector"],
            row["cost_vector"],
            row["max_path_cost"],
            row["max_measurements_on_path"],
            _canonical(row["policy_tree"]),
        )
    )
    metrics["maximum_frontier_size"] = max(
        metrics["maximum_frontier_size"], len(frontier)
    )
    return frontier


def build_report(
    *,
    joint_belief: Mapping[str, Any],
    candidate_sensors: Sequence[Mapping[str, Any]],
    model_scenarios: Sequence[Mapping[str, Any]],
    path_cost_budget: object,
    max_measurements: Optional[int] = None,
    loss_matrix: Optional[Mapping[str, Any]] = None,
    max_dp_states: int = _DEFAULT_MAX_DP_STATES,
    max_frontier_size: int = _DEFAULT_MAX_FRONTIER_SIZE,
    max_policy_combinations: int = _DEFAULT_MAX_POLICY_COMBINATIONS,
) -> dict[str, Any]:
    """Optimize an adaptive sensor policy under one persistent unknown model.

    State masses remain unnormalized and scenario-specific after each observed
    history. A model's mass at a history is its probability of that history
    under that model. The dynamic programme sums each scenario's complete
    policy-tree loss vector first, then applies worst-case selection at the
    root. It does not let the adversary switch likelihood models between
    branches.
    """
    try:
        normalized = _build_riv015_report(
            joint_belief=joint_belief,
            candidate_sensors=candidate_sensors,
            model_scenarios=model_scenarios,
            loss_matrix=loss_matrix,
        )
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise RobustSequentialError(
            f"RIV-015 joint belief or likelihood ambiguity set failed reconstruction: {error}"
        ) from error

    belief = normalized["joint_belief"]
    candidates = normalized["candidate_sensors"]
    scenarios = normalized["model_scenarios"]
    losses = normalized["decision_loss_matrix"]
    if len(candidates) > _MAX_SENSORS:
        raise RobustSequentialError(
            f"finite-horizon exact policy supports at most {_MAX_SENSORS} distinct sensors"
        )
    if len(scenarios) > _MAX_SCENARIOS:
        raise RobustSequentialError(
            f"finite-horizon exact policy supports at most {_MAX_SCENARIOS} model scenarios"
        )
    if any(len(candidate["outcomes"]) > _MAX_OUTCOMES_PER_SENSOR for candidate in candidates):
        raise RobustSequentialError(
            f"finite-horizon exact policy supports at most {_MAX_OUTCOMES_PER_SENSOR} outcomes per sensor"
        )

    if max_measurements is None:
        max_measurements = len(candidates)
    if (
        isinstance(max_measurements, bool)
        or not isinstance(max_measurements, int)
        or max_measurements < 0
        or max_measurements > len(candidates)
    ):
        raise RobustSequentialError(
            "max_measurements must be an integer from zero through the number of sensors"
        )
    for value, label in (
        (max_dp_states, "max_dp_states"),
        (max_frontier_size, "max_frontier_size"),
        (max_policy_combinations, "max_policy_combinations"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RobustSequentialError(f"{label} must be a positive integer")

    budget = _fraction(path_cost_budget, "path_cost_budget", nonnegative=True)
    scenario_ids = tuple(row["scenario_id"] for row in scenarios)
    state_rows = belief["joint_posterior"]
    state_keys = tuple(
        (row["hypothesis"], row["context_state"])
        for row in state_rows
    )
    prior_mass = tuple(
        Fraction(**row["probability"])
        for row in state_rows
    )
    initial_masses = tuple(prior_mass for _ in scenarios)
    candidate_by_id = {row["sensor_id"]: row for row in candidates}

    model_lookup: dict[str, dict[str, dict[str, dict[tuple[str, str], Fraction]]]] = {}
    for scenario in scenarios:
        per_sensor = {}
        for model in scenario["candidate_models"]:
            per_outcome = {}
            for outcome in model["outcome_likelihoods"]:
                per_outcome[_canonical(outcome["outcome"])] = {
                    (item["hypothesis"], item["context_state"]): Fraction(
                        **item["probability"]
                    )
                    for item in outcome["likelihoods"]
                }
            per_sensor[model["sensor_id"]] = per_outcome
        model_lookup[scenario["scenario_id"]] = per_sensor

    metrics = {
        "dp_state_count": 0,
        "policy_combination_count": 0,
        "maximum_frontier_size": 0,
    }
    memo: dict[tuple[Any, ...], list[dict[str, Any]]] = {}

    def _memo_key(
        masses: tuple[tuple[Fraction, ...], ...],
        available: tuple[str, ...],
        steps_left: int,
        remaining_budget: Fraction,
    ):
        return (
            masses,
            available,
            steps_left,
            remaining_budget,
        )

    def _solve(
        masses: tuple[tuple[Fraction, ...], ...],
        available: tuple[str, ...],
        steps_left: int,
        remaining_budget: Fraction,
    ) -> list[dict[str, Any]]:
        key = _memo_key(masses, available, steps_left, remaining_budget)
        if key in memo:
            return memo[key]
        metrics["dp_state_count"] += 1
        if metrics["dp_state_count"] > max_dp_states:
            raise RobustSequentialError(
                f"dynamic-program state count exceeded declared cap {max_dp_states}"
            )

        frontier: list[dict[str, Any]] = []
        for action in ("A", "B"):
            risk_vector = []
            for scenario_index in range(len(scenario_ids)):
                risk = sum(
                    (
                        mass
                        * _loss_for_action(action, state_keys[state_index][0], losses)
                        for state_index, mass in enumerate(masses[scenario_index])
                    ),
                    Fraction(0),
                )
                # _loss_for_action expects (action, hypothesis).
                risk_vector.append(risk)
            frontier.append({
                "risk_vector": tuple(risk_vector),
                "cost_vector": tuple(Fraction(0) for _ in scenario_ids),
                "max_path_cost": Fraction(0),
                "max_measurements_on_path": 0,
                "policy_tree": {"node_type": "stop", "decision": action},
            })

        frontier = _prune_frontier(
            frontier,
            max_frontier_size=max_frontier_size,
            metrics=metrics,
        )

        if steps_left > 0:
            for sensor_id in available:
                candidate = candidate_by_id[sensor_id]
                sensor_cost = Fraction(**candidate["cost"])
                if sensor_cost > remaining_budget:
                    continue
                child_available = tuple(
                    item for item in available if item != sensor_id
                )
                branch_frontiers = []
                sensor_model_rows = []
                for outcome in candidate["outcomes"]:
                    outcome_key = _canonical(outcome)
                    child_masses = tuple(
                        tuple(
                            masses[scenario_index][state_index]
                            * model_lookup[scenario_ids[scenario_index]][sensor_id][outcome_key][state_keys[state_index]]
                            for state_index in range(len(state_keys))
                        )
                        for scenario_index in range(len(scenario_ids))
                    )
                    reachable_in_any_scenario = any(
                        sum(row, Fraction(0)) > 0
                        for row in child_masses
                    )
                    if not reachable_in_any_scenario:
                        child_frontier = [{
                            "risk_vector": tuple(Fraction(0) for _ in scenario_ids),
                            "cost_vector": tuple(Fraction(0) for _ in scenario_ids),
                            "max_path_cost": Fraction(0),
                            "max_measurements_on_path": 0,
                            "policy_tree": {
                                "node_type": "model_mismatch_stop",
                                "disposition": "stop_and_review",
                                "reason": "outcome_has_zero_probability_under_every_declared_model_scenario",
                            },
                        }]
                    else:
                        child_frontier = _solve(
                            child_masses,
                            child_available,
                            steps_left - 1,
                            remaining_budget - sensor_cost,
                        )
                    branch_frontiers.append(child_frontier)
                    sensor_model_rows.append({
                        "outcome": outcome,
                        "child_masses": child_masses,
                    })

                combination_count = reduce(
                    mul, (len(rows) for rows in branch_frontiers), 1
                )
                metrics["policy_combination_count"] += combination_count
                if metrics["policy_combination_count"] > max_policy_combinations:
                    raise RobustSequentialError(
                        "policy-tree branch combinations exceeded declared cap "
                        f"{max_policy_combinations}"
                    )

                for chosen_children in itertools.product(*branch_frontiers):
                    risk_vector = tuple(
                        sum(
                            (child["risk_vector"][index] for child in chosen_children),
                            Fraction(0),
                        )
                        for index in range(len(scenario_ids))
                    )
                    current_cost = tuple(
                        sum(masses[index], Fraction(0)) * sensor_cost
                        for index in range(len(scenario_ids))
                    )
                    cost_vector = tuple(
                        current_cost[index]
                        + sum(
                            (child["cost_vector"][index] for child in chosen_children),
                            Fraction(0),
                        )
                        for index in range(len(scenario_ids))
                    )
                    max_path_cost = sensor_cost + max(
                        child["max_path_cost"] for child in chosen_children
                    )
                    max_measurements_on_path = 1 + max(
                        child["max_measurements_on_path"] for child in chosen_children
                    )
                    policy_tree = {
                        "node_type": "measure",
                        "sensor_id": sensor_id,
                        "measurement_cost": _fraction_doc(sensor_cost),
                        "branches": [
                            {
                                "outcome": outcome,
                                "next": child["policy_tree"],
                            }
                            for outcome, child in zip(
                                candidate["outcomes"], chosen_children
                            )
                        ],
                    }
                    frontier.append({
                        "risk_vector": risk_vector,
                        "cost_vector": cost_vector,
                        "max_path_cost": max_path_cost,
                        "max_measurements_on_path": max_measurements_on_path,
                        "policy_tree": policy_tree,
                    })
                frontier = _prune_frontier(
                    frontier,
                    max_frontier_size=max_frontier_size,
                    metrics=metrics,
                )

        memo[key] = frontier
        return frontier

    initial_available = tuple(row["sensor_id"] for row in candidates)
    root_frontier = _solve(
        initial_masses,
        initial_available,
        max_measurements,
        budget,
    )
    baseline_action = normalized["baseline_decision"]["action"]
    baseline_risk = Fraction(
        **normalized["baseline_decision"]["worst_case_no_measurement_risk"]
    )
    selected = min(
        root_frontier,
        key=lambda entry: (
            max(entry["risk_vector"]),
            max(entry["cost_vector"]),
            entry["max_path_cost"],
            entry["max_measurements_on_path"],
            _canonical(entry["policy_tree"]),
        ),
    )
    worst_case_risk = max(selected["risk_vector"])
    robust_value = baseline_risk - worst_case_risk
    if robust_value < 0:
        raise AssertionError(
            "robust sequential policy cannot be worse than the root stop action"
        )
    root_pareto = [
        {
            "scenario_expected_decision_loss": {
                scenario_id: _fraction_doc(value)
                for scenario_id, value in zip(scenario_ids, entry["risk_vector"])
            },
            "scenario_expected_measurement_cost": {
                scenario_id: _fraction_doc(value)
                for scenario_id, value in zip(scenario_ids, entry["cost_vector"])
            },
            "worst_case_expected_decision_loss": _fraction_doc(
                max(entry["risk_vector"])
            ),
            "worst_case_expected_measurement_cost": _fraction_doc(
                max(entry["cost_vector"])
            ),
            "maximum_path_cost": _fraction_doc(entry["max_path_cost"]),
            "maximum_measurements_on_path": entry["max_measurements_on_path"],
            "policy_tree": entry["policy_tree"],
        }
        for entry in root_frontier
    ]
    chosen_scenario_risk = {
        scenario_id: _fraction_doc(value)
        for scenario_id, value in zip(scenario_ids, selected["risk_vector"])
    }
    chosen_scenario_cost = {
        scenario_id: _fraction_doc(value)
        for scenario_id, value in zip(scenario_ids, selected["cost_vector"])
    }
    core = {
        "format": FORMAT,
        "schema": FORMAT,
        "joint_belief": belief,
        "candidate_sensors": candidates,
        "model_scenarios": scenarios,
        "decision_loss_matrix": losses,
        "path_cost_budget": _fraction_doc(budget),
        "max_measurements": max_measurements,
        "search_limits": {
            "max_dp_states": max_dp_states,
            "max_frontier_size": max_frontier_size,
            "max_policy_combinations": max_policy_combinations,
        },
        "ambiguity_set": {
            "scenario_ids": list(scenario_ids),
            "scenario_count": len(scenario_ids),
            "scenario_weights": None,
            "scenario_persistence": "one fixed but unknown model scenario for the entire policy-tree execution",
        },
        "baseline_decision": {
            "action": baseline_action,
            "worst_case_no_measurement_risk": _fraction_doc(baseline_risk),
        },
        "selected_policy": {
            "policy_tree": selected["policy_tree"],
            "scenario_expected_decision_loss": chosen_scenario_risk,
            "scenario_expected_measurement_cost": chosen_scenario_cost,
            "worst_case_expected_decision_loss": _fraction_doc(worst_case_risk),
            "worst_case_expected_measurement_cost": _fraction_doc(
                max(selected["cost_vector"])
            ),
            "maximum_path_cost": _fraction_doc(selected["max_path_cost"]),
            "maximum_measurements_on_path": selected["max_measurements_on_path"],
            "robust_expected_loss_reduction": _fraction_doc(robust_value),
        },
        "root_pareto_frontier": root_pareto,
        "search_metrics": metrics,
        "measurement_status": "policy_proposal_only_not_dispatched",
        "ground_effect": "none",
        "model_effect": "none",
        "interpretation_limits": [
            "The ambiguity scenarios are caller-supplied exact likelihood models; the true persistent model may lie outside the finite set.",
            "No probability is assigned to model identity. The optimizer minimizes the maximum unconditional expected loss over the declared scenarios.",
            "One scenario is fixed across the entire policy execution. The maximum is applied after summing each scenario's complete policy-tree risk; the adversary does not switch models independently at each branch.",
            "Every policy node is a function only of the observed outcome history, not the hidden model scenario.",
            "Unnormalized scenario-specific history masses preserve the probability of each observed prefix under each possible model without manufacturing a posterior over model identity.",
            "An outcome with zero probability under every declared scenario leads to a model-mismatch stop-and-review branch; the optimizer does not invent a successor model.",
            "The pathwise cost budget is enforced on every reachable policy path; scenario expected costs are reported separately.",
            "Each distinct sensor may be used at most once per path, and the number of measurements is bounded by max_measurements.",
            "The exact search is finite and fails closed at the declared state, frontier, and policy-combination limits.",
            "Costs and probabilities are exact caller-supplied rationals; they are not measured transport, admission, authority, latency, energy, or operation-span costs.",
            "The measurement is assumed passive and does not change the target or context state during acquisition.",
            "No measurement is dispatched, no ObservationPath is advanced, and no joint belief or source model is revised.",
            "SHA-256 digests inherited from the input belief identify content but do not authenticate source identity, model truth, reviewer authority, or physical measurement provenance.",
        ],
    }
    return {**core, "report_digest": _digest(core)}


def validate_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the finite-horizon Pareto frontiers and selected policy tree."""
    if not isinstance(document, Mapping):
        raise TypeError("robust sequential report must be an object")
    supplied = _copy_json(document, "robust sequential report")
    digest = supplied.pop("report_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise RobustSequentialError("report digest does not match contents")
    if supplied.get("format") != FORMAT or supplied.get("schema") != FORMAT:
        raise RobustSequentialError("unsupported robust sequential report")
    limits = supplied.get("search_limits", {})
    rebuilt = build_report(
        joint_belief=supplied.get("joint_belief"),
        candidate_sensors=supplied.get("candidate_sensors"),
        model_scenarios=supplied.get("model_scenarios"),
        loss_matrix=supplied.get("decision_loss_matrix"),
        path_cost_budget=supplied.get("path_cost_budget"),
        max_measurements=supplied.get("max_measurements"),
        max_dp_states=limits.get("max_dp_states"),
        max_frontier_size=limits.get("max_frontier_size"),
        max_policy_combinations=limits.get("max_policy_combinations"),
    )
    if rebuilt != dict(document):
        raise RobustSequentialError(
            "report differs from independent reconstruction from retained inputs"
        )
    return dict(document)


__all__ = [
    "FORMAT",
    "RobustSequentialError",
    "build_report",
    "validate_report",
]
