"""Evidence-gated execution of RIV-016 robust policy-tree prefixes.

The module binds one actual ObservationPath to the current node of a robust
sequential policy, reconstructs its lifecycle, requires an explicit AUTHORIZED
decision before interpreting the returned scalar outcome, and advances only
the declared child branch. It carries unnormalized joint-state masses
separately for each persistent model scenario; it never creates a posterior
over scenario identity or updates the source likelihood models.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[2]
_POLICY_DIR = Path(__file__).resolve().parent
_OBSERVATION_DIR = _ROOT / "bridges" / "observation-path"
for _directory in (_POLICY_DIR, _OBSERVATION_DIR):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from observation_path import ObservationIntent, ObservationPath  # noqa: E402
from robust_sequential_acquisition import (  # noqa: E402
    FORMAT as POLICY_FORMAT,
    validate_report as validate_robust_sequential_report,
)

FORMAT = "in-formation.robust-sequential-policy-execution/0.1"
INTERPRETATION_METHOD = "robust-sequential-outcome-v1"
REQUIRED_STAGES = (
    "planned",
    "dispatched",
    "admitted",
    "returned",
    "evidence_authorized",
    "interpreted",
)
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_SCALAR_TYPES = (str, int, bool, type(None))


class RobustPolicyExecutionError(ValueError):
    """Invalid robust policy execution path or record."""


class RobustPolicyExecutionMismatch(RobustPolicyExecutionError):
    """An executed path does not match the current robust policy node."""


class RobustPolicyExecutionStopError(RobustPolicyExecutionError):
    """The current robust policy node has no further measurement action."""


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
        raise RobustPolicyExecutionError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise RobustPolicyExecutionError(
            f"{label} must be finite JSON data"
        ) from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise RobustPolicyExecutionError(
            f"{label} must be non-empty text without NUL"
        )
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _HEX_256.fullmatch(value) is None:
        raise RobustPolicyExecutionError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _fraction(value: object, label: str, *, nonnegative: bool = False) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise RobustPolicyExecutionError(
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
        raise RobustPolicyExecutionError(
            f"{label} must be an exact rational"
        ) from error
    if nonnegative and result < 0:
        raise RobustPolicyExecutionError(f"{label} must be non-negative")
    return result


def _scalar(value: object, label: str) -> object:
    if type(value) not in _SCALAR_TYPES:
        raise RobustPolicyExecutionError(
            f"{label} must be a string, integer, Boolean, or null"
        )
    _canonical(value)
    return value


def _validate_policy_report(raw: object) -> dict[str, Any]:
    try:
        report = validate_robust_sequential_report(raw)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise RobustPolicyExecutionError(
            f"RIV-016 policy report failed independent reconstruction: {error}"
        ) from error
    if report.get("format") != POLICY_FORMAT:
        raise RobustPolicyExecutionError("unsupported robust sequential policy format")
    return report


def _reconstruct_path(raw: object) -> tuple[ObservationPath, dict[str, Any]]:
    if isinstance(raw, ObservationPath):
        snapshot = raw.to_dict()
    elif isinstance(raw, Mapping):
        snapshot = _copy_json(raw, "observation_path")
    else:
        raise TypeError(
            "each observation path must be an ObservationPath or serialized mapping"
        )
    allowed = {"attempt_id", "intent", "status", "terminal", "events"}
    if not isinstance(snapshot, Mapping) or set(snapshot) != allowed:
        raise RobustPolicyExecutionError(
            "observation path has missing or unexpected top-level fields"
        )
    intent_data = snapshot.get("intent")
    intent_fields = {
        "candidate_name", "query", "hypothesis_set_digest", "estimated_cost",
        "plan_ref", "authority_required", "application_required", "sender_ack_required",
    }
    if not isinstance(intent_data, Mapping) or set(intent_data) != intent_fields:
        raise RobustPolicyExecutionError(
            "observation path intent has missing or unexpected fields"
        )
    try:
        intent = ObservationIntent(
            attempt_id=snapshot["attempt_id"],
            candidate_name=intent_data["candidate_name"],
            query=intent_data["query"],
            hypothesis_set_digest=intent_data["hypothesis_set_digest"],
            estimated_cost=intent_data["estimated_cost"],
            plan_ref=intent_data["plan_ref"],
            authority_required=intent_data["authority_required"],
            application_required=intent_data["application_required"],
            sender_ack_required=intent_data["sender_ack_required"],
        )
        path = ObservationPath(intent)
        events = snapshot["events"]
        if not isinstance(events, list) or not events:
            raise RobustPolicyExecutionError(
                "observation path requires a non-empty event list"
            )
        event_fields = {
            "stage", "actor", "clock_value", "clock_domain", "evidence_ref", "details",
        }
        for index, event in enumerate(events[1:], start=1):
            if not isinstance(event, Mapping) or set(event) != event_fields:
                raise RobustPolicyExecutionError(
                    f"observation path event {index} has missing or unexpected fields"
                )
            path.append(
                event["stage"],
                event["actor"],
                clock_value=event["clock_value"],
                clock_domain=event["clock_domain"],
                evidence_ref=event["evidence_ref"],
                details=event["details"],
            )
    except (TypeError, ValueError, KeyError) as error:
        if isinstance(error, RobustPolicyExecutionError):
            raise
        raise RobustPolicyExecutionError(
            f"observation path failed lifecycle reconstruction: {error}"
        ) from error
    rebuilt = path.to_dict()
    if rebuilt != dict(snapshot):
        raise RobustPolicyExecutionError(
            "observation path differs from independent lifecycle reconstruction"
        )
    return path, rebuilt


def _event(snapshot: Mapping[str, Any], stage: str) -> dict[str, Any]:
    matches = [
        item for item in snapshot["events"]
        if item["stage"] == stage
    ]
    if len(matches) != 1:
        raise RobustPolicyExecutionError(
            f"expected exactly one {stage!r} event; found {len(matches)}"
        )
    return dict(matches[0])


def _mass_rows(
    masses: Mapping[str, Sequence[Fraction]],
    state_keys: Sequence[tuple[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        scenario_id: [
            {
                "hypothesis": hypothesis,
                "context_state": context_state,
                "mass": _fraction_doc(masses[scenario_id][index]),
            }
            for index, (hypothesis, context_state) in enumerate(state_keys)
        ]
        for scenario_id in masses
    }


def _posterior_rows(
    masses: Mapping[str, Sequence[Fraction]],
    state_keys: Sequence[tuple[str, str]],
) -> dict[str, Optional[list[dict[str, Any]]]]:
    result = {}
    for scenario_id, values in masses.items():
        total = sum(values, Fraction(0))
        if total == 0:
            result[scenario_id] = None
        else:
            result[scenario_id] = [
                {
                    "hypothesis": hypothesis,
                    "context_state": context_state,
                    "probability": _fraction_doc(values[index] / total),
                }
                for index, (hypothesis, context_state) in enumerate(state_keys)
            ]
    return result


def _state_digest(
    *,
    report_digest: str,
    node: Mapping[str, Any],
    outcome_history: Sequence[Mapping[str, Any]],
    scenario_masses: Mapping[str, Sequence[Fraction]],
    state_keys: Sequence[tuple[str, str]],
    remaining_budget: Fraction,
    remaining_measurements: int,
    used_sensors: Sequence[str],
) -> str:
    return _digest({
        "format": "in-formation.robust-policy-execution-state/0.1",
        "policy_report_digest": report_digest,
        "policy_node_digest": _digest(node),
        "outcome_history": list(outcome_history),
        "scenario_unnormalized_masses": _mass_rows(scenario_masses, state_keys),
        "remaining_path_cost_budget": _fraction_doc(remaining_budget),
        "remaining_measurements": remaining_measurements,
        "used_sensors": list(used_sensors),
    })


def _scenario_likelihood_map(
    report: Mapping[str, Any],
) -> dict[str, dict[str, dict[str, dict[tuple[str, str], Fraction]]]]:
    result = {}
    for scenario in report["model_scenarios"]:
        by_sensor = {}
        for candidate_model in scenario["candidate_models"]:
            by_outcome = {}
            for outcome_row in candidate_model["outcome_likelihoods"]:
                by_outcome[_canonical(outcome_row["outcome"])] = {
                    (item["hypothesis"], item["context_state"]): Fraction(
                        **item["probability"]
                    )
                    for item in outcome_row["likelihoods"]
                }
            by_sensor[candidate_model["sensor_id"]] = by_outcome
        result[scenario["scenario_id"]] = by_sensor
    return result


def _replay_prefix(
    policy_report: Mapping[str, Any],
    observation_paths: Sequence[object],
) -> dict[str, Any]:
    report = _validate_policy_report(policy_report)
    if not isinstance(observation_paths, (tuple, list)):
        raise TypeError("observation_paths must be a sequence")
    report_digest = report["report_digest"]
    scenario_ids = tuple(report["ambiguity_set"]["scenario_ids"])
    state_keys = tuple(
        (row["hypothesis"], row["context_state"])
        for row in report["joint_belief"]["joint_posterior"]
    )
    prior = tuple(
        Fraction(**row["probability"])
        for row in report["joint_belief"]["joint_posterior"]
    )
    masses = {
        scenario_id: prior
        for scenario_id in scenario_ids
    }
    likelihoods = _scenario_likelihood_map(report)
    candidate_by_id = {
        row["sensor_id"]: row
        for row in report["candidate_sensors"]
    }
    node = report["selected_policy"]["policy_tree"]
    history: list[dict[str, Any]] = []
    used_sensors: list[str] = []
    attempt_ids: set[str] = set()
    snapshots: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    total_cost = Fraction(0)
    initial_budget = Fraction(**report["path_cost_budget"])
    max_measurements = report["max_measurements"]

    for index, raw_path in enumerate(observation_paths):
        if node["node_type"] != "measure":
            raise RobustPolicyExecutionStopError(
                f"policy has no measurement at supplied path index {index}; current node is {node['node_type']}"
            )
        path, snapshot = _reconstruct_path(raw_path)
        if path.status != "interpreted" or path.terminal:
            raise RobustPolicyExecutionError(
                "each executed policy step must end at a non-terminal interpreted ObservationPath"
            )
        stages = tuple(event["stage"] for event in snapshot["events"])
        if stages != REQUIRED_STAGES:
            raise RobustPolicyExecutionError(
                f"policy step lifecycle must be exactly {REQUIRED_STAGES!r}"
            )
        intent = path.intent
        attempt_id = _text(intent.attempt_id, "attempt_id")
        if attempt_id in attempt_ids:
            raise RobustPolicyExecutionMismatch(
                "attempt IDs must be unique within one policy execution"
            )
        attempt_ids.add(attempt_id)

        sensor_id = node["sensor_id"]
        candidate = candidate_by_id.get(sensor_id)
        if candidate is None:
            raise RobustPolicyExecutionError(
                "current policy node references a sensor absent from the validated candidate set"
            )
        cost = Fraction(**node["measurement_cost"])
        remaining_budget = initial_budget - total_cost
        remaining_measurements = max_measurements - len(history)
        if cost > remaining_budget or remaining_measurements <= 0:
            raise RobustPolicyExecutionError(
                "current policy node violates the declared pathwise cost or measurement budget"
            )
        node_digest = _digest(node)
        state_digest = _state_digest(
            report_digest=report_digest,
            node=node,
            outcome_history=history,
            scenario_masses=masses,
            state_keys=state_keys,
            remaining_budget=remaining_budget,
            remaining_measurements=remaining_measurements,
            used_sensors=used_sensors,
        )
        estimated_cost = float(cost)
        if not math.isfinite(estimated_cost) or estimated_cost <= 0:
            raise RobustPolicyExecutionError(
                "exact policy cost cannot be represented as a finite positive ObservationIntent value"
            )
        expected_candidate_name = f"robust-sequential-sensor:{sensor_id}"
        if intent.candidate_name != expected_candidate_name:
            raise RobustPolicyExecutionMismatch(
                "ObservationPath candidate differs from current robust policy node"
            )
        if intent.hypothesis_set_digest != state_digest:
            raise RobustPolicyExecutionMismatch(
                "ObservationPath is bound to a different robust policy state"
            )
        if intent.plan_ref != f"urn:sha256:{state_digest}":
            raise RobustPolicyExecutionMismatch(
                "ObservationPath plan_ref differs from current robust policy state"
            )
        if not intent.authority_required or intent.application_required or intent.sender_ack_required:
            raise RobustPolicyExecutionError(
                "robust sensor observation requires authority and forbids application/ACK stages"
            )
        if intent.estimated_cost != estimated_cost:
            raise RobustPolicyExecutionMismatch(
                "ObservationPath estimated cost differs from the exact policy cost"
            )

        dispatched = _event(snapshot, "dispatched")
        admitted = _event(snapshot, "admitted")
        returned = _event(snapshot, "returned")
        authority = _event(snapshot, "evidence_authorized")
        interpreted = _event(snapshot, "interpreted")
        returned_details = returned["details"]
        authority_details = authority["details"]
        interpreted_details = interpreted["details"]

        required_return_fields = {
            "policy_report_digest",
            "policy_state_digest",
            "policy_node_digest",
            "outcome_history_prefix",
            "sensor_id",
            "dimension",
            "observed_outcome",
            "measurement_cost",
        }
        missing = required_return_fields - set(returned_details)
        if missing:
            raise RobustPolicyExecutionError(
                f"returned.details is missing required fields: {sorted(missing)}"
            )
        returned_outcome = _scalar(
            returned_details["observed_outcome"],
            "returned.details.observed_outcome",
        )
        expected_bindings = {
            "policy_report_digest": report_digest,
            "policy_state_digest": state_digest,
            "policy_node_digest": node_digest,
            "outcome_history_prefix": history,
            "sensor_id": sensor_id,
            "dimension": candidate["dimension"],
            "measurement_cost": _fraction_doc(cost),
        }
        for field, expected_value in expected_bindings.items():
            if returned_details[field] != expected_value:
                raise RobustPolicyExecutionMismatch(
                    f"returned.details.{field} differs from the active policy node or prefix"
                )
        _text(returned_details.get("encounter_id"), "returned.details.encounter_id")
        _sha256(returned_details.get("payload_digest"), "returned.details.payload_digest")
        _text(returned_details.get("canonicalization"), "returned.details.canonicalization")
        if authority_details.get("decision_status") != "AUTHORIZED":
            raise RobustPolicyExecutionMismatch(
                "policy execution advances only after an explicit AUTHORIZED decision"
            )
        _sha256(authority_details.get("policy_digest"), "authority.policy_digest")
        _sha256(authority_details.get("decision_digest"), "authority.decision_digest")

        if interpreted_details.get("method") != INTERPRETATION_METHOD:
            raise RobustPolicyExecutionError(
                f"interpreted.details.method must be {INTERPRETATION_METHOD!r}"
            )
        for field, expected_value in expected_bindings.items():
            if interpreted_details.get(field) != expected_value:
                raise RobustPolicyExecutionMismatch(
                    f"interpreted.details.{field} differs from active policy binding"
                )
        interpreted_outcome = _scalar(
            interpreted_details.get("observed_outcome"),
            "interpreted.details.observed_outcome",
        )
        if _canonical(interpreted_outcome) != _canonical(returned_outcome):
            raise RobustPolicyExecutionMismatch(
                "returned and interpreted outcomes differ exactly"
            )

        matching_branches = [
            branch for branch in node["branches"]
            if _canonical(branch["outcome"]) == _canonical(returned_outcome)
        ]
        if len(matching_branches) != 1:
            raise RobustPolicyExecutionMismatch(
                "observed outcome is outside the policy node's declared branches; "
                "preserve it for append-only model review rather than extending this tree"
            )
        branch = matching_branches[0]
        child = branch["next"]

        masses_after: dict[str, tuple[Fraction, ...]] = {}
        predictive_probabilities: dict[str, Optional[Fraction]] = {}
        posterior_by_scenario: dict[str, Optional[list[dict[str, Any]]]] = {}
        for scenario_id in scenario_ids:
            prior_masses = masses[scenario_id]
            likelihood_map = likelihoods[scenario_id][sensor_id].get(
                _canonical(returned_outcome)
            )
            if likelihood_map is None:
                raise AssertionError(
                    "validated policy branch has no corresponding scenario likelihood row"
                )
            updated = tuple(
                prior_masses[state_index] * likelihood_map[state_key]
                for state_index, state_key in enumerate(state_keys)
            )
            prior_total = sum(prior_masses, Fraction(0))
            updated_total = sum(updated, Fraction(0))
            masses_after[scenario_id] = updated
            predictive_probabilities[scenario_id] = (
                None if prior_total == 0 else updated_total / prior_total
            )
            posterior_by_scenario[scenario_id] = (
                None
                if updated_total == 0
                else [
                    {
                        "hypothesis": hypothesis,
                        "context_state": context_state,
                        "probability": _fraction_doc(updated[state_index] / updated_total),
                    }
                    for state_index, (hypothesis, context_state) in enumerate(state_keys)
                ]
            )

        all_zero = all(
            sum(masses_after[scenario_id], Fraction(0)) == 0
            for scenario_id in scenario_ids
        )
        if all_zero and child["node_type"] != "model_mismatch_stop":
            raise AssertionError(
                "outcome impossible under all scenarios must lead to a model-mismatch stop node"
            )
        if not all_zero and child["node_type"] == "model_mismatch_stop":
            raise AssertionError(
                "model-mismatch stop node is inconsistent with positive predictive probability"
            )

        attempt_history = {
            "sensor_id": sensor_id,
            "outcome": returned_outcome,
        }
        history.append(attempt_history)
        used_sensors.append(sensor_id)
        snapshots.append(snapshot)
        total_cost += cost
        if total_cost > initial_budget:
            raise RobustPolicyExecutionError(
                "executed prefix exceeds the policy's pathwise cost budget"
            )
        manifests.append({
            "attempt_id": attempt_id,
            "policy_report_digest": report_digest,
            "policy_node_digest": node_digest,
            "policy_state_digest": state_digest,
            "history_prefix": history[:-1],
            "sensor_id": sensor_id,
            "dimension": candidate["dimension"],
            "measurement_cost": _fraction_doc(cost),
            "observed_outcome": returned_outcome,
            "dispatch_evidence_ref": dispatched["evidence_ref"],
            "admission_evidence_ref": admitted["evidence_ref"],
            "return_evidence_ref": returned["evidence_ref"],
            "encounter_id": returned_details.get("encounter_id"),
            "payload_digest": returned_details.get("payload_digest"),
            "canonicalization": returned_details.get("canonicalization"),
            "authority_evidence_ref": authority["evidence_ref"],
            "authority_policy_digest": authority_details["policy_digest"],
            "authority_decision_digest": authority_details["decision_digest"],
            "interpretation_evidence_ref": interpreted["evidence_ref"],
            "observation_path_digest": _digest(snapshot),
            "scenario_predictive_probabilities": {
                key: None if value is None else _fraction_doc(value)
                for key, value in predictive_probabilities.items()
            },
            "scenario_joint_posterior_after_outcome": posterior_by_scenario,
        })
        masses = masses_after
        node = child

    return {
        "report": report,
        "report_digest": report_digest,
        "scenario_ids": scenario_ids,
        "state_keys": state_keys,
        "masses": masses,
        "node": node,
        "outcome_history": history,
        "used_sensors": used_sensors,
        "attempt_ids": attempt_ids,
        "paths": snapshots,
        "manifests": manifests,
        "total_cost": total_cost,
        "remaining_budget": initial_budget - total_cost,
        "remaining_measurements": max_measurements - len(history),
        "initial_budget": initial_budget,
        "max_measurements": max_measurements,
    }


def new_robust_policy_observation_path(
    *,
    policy_report: Mapping[str, Any],
    prior_observation_paths: Sequence[object] = (),
    attempt_id: str,
    query: Optional[str] = None,
) -> ObservationPath:
    """Create a planned-only path for the next measurement at the active tree node."""
    state = _replay_prefix(policy_report, prior_observation_paths)
    node = state["node"]
    if node["node_type"] != "measure":
        raise RobustPolicyExecutionStopError(
            f"robust policy stops here: {node.get('disposition', node.get('decision', node.get('reason')))}"
        )
    attempt = _text(attempt_id, "attempt_id")
    if attempt in state["attempt_ids"]:
        raise RobustPolicyExecutionMismatch(
            "attempt_id was already used in this policy execution"
        )
    cost = Fraction(**node["measurement_cost"])
    try:
        estimated_cost = float(cost)
    except (OverflowError, ValueError) as error:
        raise RobustPolicyExecutionError(
            "policy cost cannot be represented in ObservationIntent"
        ) from error
    if not math.isfinite(estimated_cost) or estimated_cost <= 0:
        raise RobustPolicyExecutionError(
            "policy cost must be finite and positive for ObservationIntent"
        )
    state_digest = _state_digest(
        report_digest=state["report_digest"],
        node=node,
        outcome_history=state["outcome_history"],
        scenario_masses=state["masses"],
        state_keys=state["state_keys"],
        remaining_budget=state["remaining_budget"],
        remaining_measurements=state["remaining_measurements"],
        used_sensors=state["used_sensors"],
    )
    sensor_id = node["sensor_id"]
    intent = ObservationIntent(
        attempt_id=attempt,
        candidate_name=f"robust-sequential-sensor:{sensor_id}",
        query=query or (
            f"Observe outcome from robust sensor {sensor_id!r} "
            f"under the current policy node and outcome prefix"
        ),
        hypothesis_set_digest=state_digest,
        estimated_cost=estimated_cost,
        plan_ref=f"urn:sha256:{state_digest}",
        authority_required=True,
        application_required=False,
        sender_ack_required=False,
    )
    return ObservationPath(intent)


def build_robust_policy_execution_record(
    *,
    policy_report: Mapping[str, Any],
    observation_paths: Sequence[object],
) -> dict[str, Any]:
    """Reconstruct an authorized interpreted policy prefix and scenario masses."""
    if not isinstance(observation_paths, (tuple, list)) or not observation_paths:
        raise RobustPolicyExecutionError(
            "at least one executed ObservationPath is required"
        )
    state = _replay_prefix(policy_report, observation_paths)
    node = state["node"]
    if node["node_type"] == "model_mismatch_stop":
        execution_status = "authorized_interpreted_model_mismatch"
        next_sensor = None
        terminal_decision = None
        stop_disposition = node["disposition"]
    elif node["node_type"] == "stop":
        execution_status = "authorized_interpreted_policy_terminal"
        next_sensor = None
        terminal_decision = node["decision"]
        stop_disposition = None
    else:
        execution_status = "authorized_interpreted_policy_prefix"
        next_sensor = node["sensor_id"]
        terminal_decision = None
        stop_disposition = None

    scenario_masses = _mass_rows(state["masses"], state["state_keys"])
    scenario_posteriors = _posterior_rows(state["masses"], state["state_keys"])
    current_node = {
        "node_digest": _digest(node),
        "node_type": node["node_type"],
        "next_sensor_id": next_sensor,
        "terminal_decision": terminal_decision,
        "stop_disposition": stop_disposition,
        "outcome_history": state["outcome_history"],
        "used_sensors": state["used_sensors"],
        "remaining_measurements": state["remaining_measurements"],
        "remaining_path_cost_budget": _fraction_doc(state["remaining_budget"]),
        "total_path_cost": _fraction_doc(state["total_cost"]),
        "scenario_unnormalized_joint_masses": scenario_masses,
        "scenario_conditioned_joint_posteriors": scenario_posteriors,
        "scenario_identity_posterior": None,
    }
    core = {
        "format": FORMAT,
        "schema": FORMAT,
        "policy_report": state["report"],
        "policy_report_digest": state["report_digest"],
        "observation_paths": state["paths"],
        "observation_path_digests": [_digest(path) for path in state["paths"]],
        "outcome_history": state["outcome_history"],
        "measurement_manifests": state["manifests"],
        "current_policy_state": current_node,
        "execution_status": execution_status,
        "belief_effect": "scenario_conditioned_joint_mass_prefix_only",
        "scenario_model_effect": "none",
        "ground_effect": "none",
        "measurement_status": "observed_authorized_and_interpreted",
        "interpretation_limits": [
            "Every path is independently reconstructed through planned, dispatched, admitted, returned, evidence_authorized, and interpreted stages. External artifacts referenced by path evidence URIs are not fetched here.",
            "The path's AUTHORIZED status is structurally checked; this module does not authenticate the authority actor, quorum, signer, trust root, or signature.",
            "Returned and interpreted outcomes must match exactly and must be a declared branch of the active policy node. An undeclared outcome is rejected as a mismatch and is not silently added to the policy.",
            "An outcome assigned zero probability by every declared model scenario leads to a stop-and-review node. The executor does not invent a new model or posterior update.",
            "Scenario-specific masses are retained separately. No probability is assigned to model identity and no posterior over the ambiguity scenarios is formed.",
            "The execution record advances only its evidential policy prefix. It does not revise the supplied joint prior, any candidate likelihood model, the Ground, or the robust policy report.",
            "Measurement cost is taken from the exact policy node and checked against the executed path prefix. It is not measured dispatch, transport, authority, latency, energy, or operation-span cost.",
            "Digests provide content identity and reconstruction checks; they do not authenticate physical source identity, sensor truth, or external artifacts.",
        ],
    }
    return {**core, "record_digest": _digest(core)}


def validate_robust_policy_execution_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the policy prefix, ObservationPaths, and scenario mass vectors."""
    if not isinstance(record, Mapping):
        raise TypeError("robust policy execution record must be an object")
    supplied = _copy_json(record, "robust policy execution record")
    digest = supplied.pop("record_digest", None)
    if not isinstance(digest, str) or _HEX_256.fullmatch(digest) is None or digest != _digest(supplied):
        raise RobustPolicyExecutionError(
            "record_digest does not match execution record contents"
        )
    if supplied.get("format") != FORMAT or supplied.get("schema") != FORMAT:
        raise RobustPolicyExecutionError(
            "unsupported robust policy execution record format/schema"
        )
    rebuilt = build_robust_policy_execution_record(
        policy_report=supplied.get("policy_report"),
        observation_paths=supplied.get("observation_paths"),
    )
    if rebuilt != dict(record):
        raise RobustPolicyExecutionError(
            "robust policy execution record differs from independent reconstruction"
        )
    return dict(record)


__all__ = [
    "FORMAT",
    "RobustPolicyExecutionError",
    "RobustPolicyExecutionMismatch",
    "RobustPolicyExecutionStopError",
    "new_robust_policy_observation_path",
    "build_robust_policy_execution_record",
    "validate_robust_policy_execution_record",
]
