"""Execute one prefix of an RIV-011 policy through authorized ObservationPaths.

A policy tree is a plan, not evidence. Each next reference attempt is bound to
the current report, exact posterior state, prior signal prefix, and selected
policy node. Only an admitted, AUTHORIZED, interpreted return advances the
policy and contributes a reference observation to the cumulative RIV-009
calibration report.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from observation_path import ObservationIntent, ObservationPath

FORMAT = "in-formation.finite-horizon-policy-execution/0.1"
RIV011_FORMAT = "in-formation.finite-horizon-reference-acquisition/0.1"
RIV009_FORMAT = "in-formation.reference-calibrated-evidence/0.1"
INTERPRETATION_METHOD = "finite-horizon-reference-signal-v1"
REQUIRED_STAGES = (
    "planned",
    "dispatched",
    "admitted",
    "returned",
    "evidence_authorized",
    "interpreted",
)
RETURN_FIELDS = {
    "encounter_id",
    "payload_digest",
    "canonicalization",
    "policy_report_digest",
    "policy_state_digest",
    "policy_node_digest",
    "history_signal_prefix",
    "candidate_id",
    "sensor_id",
    "dimension",
    "known_hypothesis",
    "reference_standard_ref",
    "reference_standard_sha256",
    "observed_outcome",
}
HEX_256 = re.compile(r"^[0-9a-f]{64}$")


class PolicyExecutionError(ValueError):
    """Invalid policy prefix, path, or cumulative evidence record."""


class PolicyExecutionMismatch(PolicyExecutionError):
    """An executed path does not match the active adaptive policy node."""


class PolicyExecutionStopError(PolicyExecutionError):
    """The policy tree has no further reference action at this prefix."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load required module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ROOT = Path(__file__).resolve().parents[2]
_RIV011 = _load_module(
    "riv012_riv011",
    Path(__file__).resolve().with_name("finite_horizon_reference_policy.py"),
)
_RIV009 = _load_module(
    "riv012_riv009",
    Path(__file__).resolve().with_name("reference_calibrated_evidence.py"),
)
if _RIV011.FORMAT != RIV011_FORMAT:
    raise RuntimeError("RIV-012 requires the declared RIV-011 policy report contract")
if _RIV009.FORMAT != RIV009_FORMAT:
    raise RuntimeError("RIV-012 requires the declared RIV-009 calibration report contract")


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
        raise PolicyExecutionError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise PolicyExecutionError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise PolicyExecutionError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not HEX_256.fullmatch(value):
        raise PolicyExecutionError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _fraction_value(value: object, label: str) -> Fraction:
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        raise PolicyExecutionError(f"{label} must be an exact rational document")
    try:
        numerator, denominator = value["numerator"], value["denominator"]
        if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
            raise ValueError
        return Fraction(numerator, denominator)
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise PolicyExecutionError(f"{label} must be an exact rational document") from error


def _validate_policy_report(raw: object) -> dict[str, Any]:
    try:
        return _RIV011.validate_report(raw)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise PolicyExecutionError(f"RIV-011 policy report failed reconstruction: {error}") from error


def _belief_rows(
    belief: tuple[Fraction, ...],
    calibrations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "calibration_id": calibration["calibration_id"],
            "probability": _fraction_doc(belief[index]),
        }
        for index, calibration in enumerate(calibrations)
    ]


def _policy_state_digest(
    *,
    report_digest: str,
    node: Mapping[str, Any],
    signal_history: Sequence[str],
    belief: tuple[Fraction, ...],
    calibrations: Sequence[Mapping[str, Any]],
    remaining_budget: Fraction,
) -> str:
    return _digest({
        "format": "in-formation.finite-horizon-policy-state/0.1",
        "policy_report_digest": report_digest,
        "policy_node_digest": _digest(node),
        "signal_history": list(signal_history),
        "calibration_posterior": _belief_rows(belief, calibrations),
        "remaining_budget": _fraction_doc(remaining_budget),
    })


def _reconstruct_path(raw: object) -> tuple[ObservationPath, dict[str, Any]]:
    if isinstance(raw, ObservationPath):
        snapshot = raw.to_dict()
    elif isinstance(raw, Mapping):
        snapshot = _copy_json(raw, "observation_path")
    else:
        raise TypeError("each observation path must be an ObservationPath or serialized mapping")
    allowed = {"attempt_id", "intent", "status", "terminal", "events"}
    if not isinstance(snapshot, Mapping) or set(snapshot) != allowed:
        raise PolicyExecutionError("observation path has missing or unexpected top-level fields")
    intent_data = snapshot.get("intent")
    intent_fields = {
        "candidate_name", "query", "hypothesis_set_digest", "estimated_cost",
        "plan_ref", "authority_required", "application_required", "sender_ack_required",
    }
    if not isinstance(intent_data, Mapping) or set(intent_data) != intent_fields:
        raise PolicyExecutionError("observation path intent has missing or unexpected fields")
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
            raise PolicyExecutionError("observation path requires a non-empty event list")
        event_fields = {
            "stage", "actor", "clock_value", "clock_domain", "evidence_ref", "details",
        }
        for index, event in enumerate(events[1:], start=1):
            if not isinstance(event, Mapping) or set(event) != event_fields:
                raise PolicyExecutionError(
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
        if isinstance(error, PolicyExecutionError):
            raise
        raise PolicyExecutionError(
            f"observation path failed lifecycle reconstruction: {error}"
        ) from error
    rebuilt = path.to_dict()
    if rebuilt != dict(snapshot):
        raise PolicyExecutionError("observation path differs from independent lifecycle reconstruction")
    return path, rebuilt


def _event(snapshot: Mapping[str, Any], stage: str) -> dict[str, Any]:
    matches = [row for row in snapshot["events"] if row["stage"] == stage]
    if len(matches) != 1:
        raise PolicyExecutionError(f"expected exactly one {stage!r} event")
    return dict(matches[0])


def _posterior_after_signal(
    belief: tuple[Fraction, ...],
    calibrations: Sequence[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    signal: str,
) -> tuple[Fraction, Optional[tuple[Fraction, ...]]]:
    weights = []
    for calibration, prior in zip(calibrations, belief):
        model = calibration["sensor_models"][candidate["sensor_id"]]
        field = (
            "p_signal_a_given_hypothesis_a"
            if candidate["known_hypothesis"] == "A"
            else "p_signal_a_given_hypothesis_b"
        )
        probability_a = Fraction(**model[field])
        likelihood = probability_a if signal == "A" else 1 - probability_a
        weights.append(prior * likelihood)
    predictive = sum(weights, Fraction(0))
    if predictive == 0:
        return predictive, None
    return predictive, tuple(value / predictive for value in weights)


def _branch_for_signal(node: Mapping[str, Any], signal: str) -> Mapping[str, Any]:
    matches = [
        branch for branch in node["branches"]
        if branch["signal"] == signal
    ]
    if len(matches) != 1:
        raise PolicyExecutionMismatch("policy node has no unique branch for observed signal")
    branch = matches[0]
    if not branch["reachable"]:
        raise PolicyExecutionMismatch("observed signal is unreachable under the selected policy node")
    return branch


def _replay_prefix(
    policy_report: Mapping[str, Any],
    observation_paths: Sequence[object],
) -> dict[str, Any]:
    report = _validate_policy_report(policy_report)
    model = report["model"]
    report_digest = report["report_digest"]
    calibrations = model["calibrations_with_current_prior"]
    belief = tuple(
        Fraction(**item["prior_probability"])
        for item in calibrations
    )
    node = report["finite_horizon_policy"]["root"]
    signal_history: list[str] = []
    observations: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    attempt_ids: set[str] = set()
    total_cost = Fraction(0)
    initial_budget = Fraction(**model["cost_budget"])

    for index, raw_path in enumerate(observation_paths):
        if node["action"] is None or node["candidate_id"] is None:
            raise PolicyExecutionStopError(
                f"policy stopped before supplied path index {index}"
            )
        path, snapshot = _reconstruct_path(raw_path)
        if path.status != "interpreted" or path.terminal:
            raise PolicyExecutionError(
                "each policy observation must end at a non-terminal interpreted path"
            )
        stages = tuple(row["stage"] for row in snapshot["events"])
        if stages != REQUIRED_STAGES:
            raise PolicyExecutionError(
                f"policy observation lifecycle must be exactly {REQUIRED_STAGES!r}"
            )
        intent = path.intent
        attempt_id = _text(intent.attempt_id, "attempt_id")
        if attempt_id in attempt_ids:
            raise PolicyExecutionMismatch("attempt IDs must be unique within a policy execution prefix")
        attempt_ids.add(attempt_id)

        candidate_id = node["candidate_id"]
        cost = Fraction(**node["cost"])
        node_digest = _digest(node)
        remaining_budget = initial_budget - total_cost
        state_digest = _policy_state_digest(
            report_digest=report_digest,
            node=node,
            signal_history=signal_history,
            belief=belief,
            calibrations=calibrations,
            remaining_budget=remaining_budget,
        )
        expected_candidate_name = f"finite-horizon-reference:{candidate_id}"
        if intent.candidate_name != expected_candidate_name:
            raise PolicyExecutionMismatch("ObservationPath candidate differs from current policy node")
        if intent.hypothesis_set_digest != state_digest:
            raise PolicyExecutionMismatch("ObservationPath is bound to a different policy state")
        if intent.plan_ref != f"urn:sha256:{state_digest}":
            raise PolicyExecutionMismatch("ObservationPath plan_ref differs from current policy state")
        if not intent.authority_required or intent.application_required or intent.sender_ack_required:
            raise PolicyExecutionError(
                "reference reading requires authority and forbids application/ACK stages"
            )
        if intent.estimated_cost != float(cost):
            raise PolicyExecutionMismatch("ObservationPath estimated cost differs from policy action")

        dispatched = _event(snapshot, "dispatched")
        admitted = _event(snapshot, "admitted")
        returned = _event(snapshot, "returned")
        authorized = _event(snapshot, "evidence_authorized")
        interpreted = _event(snapshot, "interpreted")
        returned_details = returned["details"]
        interpreted_details = interpreted["details"]
        for field in RETURN_FIELDS:
            if field not in returned_details:
                raise PolicyExecutionError(f"returned.details.{field} is required")
        expected = {
            "policy_report_digest": report_digest,
            "policy_state_digest": state_digest,
            "policy_node_digest": node_digest,
            "history_signal_prefix": signal_history,
            "candidate_id": candidate_id,
            "sensor_id": node["sensor_id"],
            "dimension": "calibration-reference",
            "known_hypothesis": node["known_hypothesis"],
            "reference_standard_ref": node["reference_standard_ref"],
            "reference_standard_sha256": node["reference_standard_sha256"],
        }
        for field, expected_value in expected.items():
            if returned_details[field] != expected_value:
                raise PolicyExecutionMismatch(f"returned.details.{field} differs from active policy node")

        signal = returned_details["observed_outcome"]
        if type(signal) is not str or signal not in ("A", "B"):
            raise PolicyExecutionMismatch("observed_outcome must be exactly A or B")
        _sha256(returned_details["payload_digest"], "returned.details.payload_digest")
        if interpreted_details.get("method") != INTERPRETATION_METHOD:
            raise PolicyExecutionError(f"interpretation method must be {INTERPRETATION_METHOD!r}")
        for field, expected_value in {**expected, "observed_outcome": signal}.items():
            if interpreted_details.get(field) != expected_value:
                raise PolicyExecutionMismatch(
                    f"interpreted.details.{field} differs from active policy node"
                )

        candidate = {
            "candidate_id": candidate_id,
            "sensor_id": node["sensor_id"],
            "known_hypothesis": node["known_hypothesis"],
            "reference_standard_ref": node["reference_standard_ref"],
            "reference_standard_sha256": node["reference_standard_sha256"],
            "cost": node["cost"],
        }
        predictive, posterior = _posterior_after_signal(
            belief, calibrations, candidate, signal
        )
        if predictive <= 0 or posterior is None:
            raise PolicyExecutionMismatch("observed signal has zero predictive probability")

        branch = _branch_for_signal(node, signal)
        if predictive != Fraction(**branch["predictive_probability"]):
            raise AssertionError("policy branch predictive probability differs from exact Bayesian update")
        posterior_rows = _belief_rows(posterior, calibrations)
        if posterior_rows != branch["posterior_calibration_probabilities"]:
            raise AssertionError("policy branch posterior differs from exact Bayesian update")

        reference_observation = {
            "observation_id": attempt_id,
            "sensor_id": node["sensor_id"],
            "known_hypothesis": node["known_hypothesis"],
            "signal": signal,
            "reference_standard_ref": node["reference_standard_ref"],
            "reference_standard_sha256": node["reference_standard_sha256"],
            "observation_ref": returned["evidence_ref"],
            "observation_sha256": returned_details["payload_digest"],
            "cost": _fraction_doc(cost),
        }
        observations.append(reference_observation)
        snapshots.append(snapshot)
        total_cost += cost
        manifests.append({
            "attempt_id": attempt_id,
            "policy_node_digest": node_digest,
            "policy_state_digest": state_digest,
            "candidate_id": candidate_id,
            "sensor_id": node["sensor_id"],
            "known_hypothesis": node["known_hypothesis"],
            "signal": signal,
            "predictive_probability": _fraction_doc(predictive),
            "posterior_calibration_probabilities": posterior_rows,
            "dispatch_evidence_ref": dispatched["evidence_ref"],
            "admission_evidence_ref": admitted["evidence_ref"],
            "return_evidence_ref": returned["evidence_ref"],
            "authority_evidence_ref": authorized["evidence_ref"],
            "authority_decision_digest": authorized["details"]["decision_digest"],
            "interpretation_evidence_ref": interpreted["evidence_ref"],
            "observation_path_digest": _digest(snapshot),
            "reference_observation_digest": _digest(reference_observation),
        })
        belief = posterior
        signal_history.append(signal)
        node = branch["child"]
        if node is None:
            raise AssertionError("reachable policy branch must have a child node")

    return {
        "report": report,
        "report_digest": report_digest,
        "calibrations": calibrations,
        "belief": belief,
        "node": node,
        "signal_history": signal_history,
        "observations": observations,
        "snapshots": snapshots,
        "manifests": manifests,
        "total_cost": total_cost,
        "remaining_budget": initial_budget - total_cost,
        "attempt_ids": attempt_ids,
    }


def new_reference_policy_observation_path(
    *,
    policy_report: Mapping[str, Any],
    prior_observation_paths: Sequence[object] = (),
    attempt_id: str,
) -> ObservationPath:
    """Create a planned-only path for the next action at the current policy node."""
    state = _replay_prefix(policy_report, prior_observation_paths)
    node = state["node"]
    if node["action"] is None or node["candidate_id"] is None:
        raise PolicyExecutionStopError(
            f"finite-horizon policy stops here: {node.get('stop_reason')}"
        )
    attempt = _text(attempt_id, "attempt_id")
    if attempt in state["attempt_ids"]:
        raise PolicyExecutionMismatch("attempt_id was already used in this policy execution")
    cost = Fraction(**node["cost"])
    try:
        estimated_cost = float(cost)
    except (OverflowError, ValueError) as error:
        raise PolicyExecutionError("policy action cost cannot be represented by ObservationIntent") from error
    if not math.isfinite(estimated_cost) or estimated_cost <= 0:
        raise PolicyExecutionError("policy action cost must be finite and positive")
    node_digest = _digest(node)
    state_digest = _policy_state_digest(
        report_digest=state["report_digest"],
        node=node,
        signal_history=state["signal_history"],
        belief=state["belief"],
        calibrations=state["calibrations"],
        remaining_budget=state["remaining_budget"],
    )
    intent = ObservationIntent(
        attempt_id=attempt,
        candidate_name=f"finite-horizon-reference:{node['candidate_id']}",
        query=(
            f"Observe sensor {node['sensor_id']!r} against known standard "
            f"{node['known_hypothesis']!r} from {node['reference_standard_ref']!r}"
        ),
        hypothesis_set_digest=state_digest,
        estimated_cost=estimated_cost,
        plan_ref=f"urn:sha256:{state_digest}",
        authority_required=True,
        application_required=False,
        sender_ack_required=False,
    )
    return ObservationPath(intent)


def build_reference_policy_execution_record(
    *,
    policy_report: Mapping[str, Any],
    observation_paths: Sequence[object],
) -> dict[str, Any]:
    """Reconstruct an executed policy prefix and its cumulative RIV-009 update."""
    if not isinstance(observation_paths, (tuple, list)) or not observation_paths:
        raise PolicyExecutionError("at least one executed ObservationPath is required")
    state = _replay_prefix(policy_report, observation_paths)
    report = state["report"]
    model = report["model"]
    try:
        riv009 = _RIV009.build_report(
            prior_hypothesis_a=model["target_prior_hypothesis_a"],
            calibrations=model["calibrations_with_current_prior"],
            target_sensor_schedule=model["target_sensor_schedule"],
            reference_observations=state["observations"],
            max_histories=model["max_histories"],
        )
        _RIV009.validate_report(riv009)
    except (TypeError, ValueError, KeyError, AssertionError) as error:
        raise PolicyExecutionError(f"RIV-009 rejected the cumulative authorized reference history: {error}") from error

    final_posterior = riv009["reference_phase"]["posterior_calibration_probabilities"]
    if final_posterior != _belief_rows(state["belief"], state["calibrations"]):
        raise AssertionError("RIV-009 cumulative posterior differs from policy-tree state")
    target_filter = riv009["target_phase"]["reference_conditioned_filter_report"]
    target_accuracy = target_filter["summary"]["shared_calibration_map_accuracy"]
    if target_accuracy != state["node"]["current_target_map_accuracy"]:
        raise AssertionError("RIV-009 target accuracy differs from current RIV-011 policy node")

    current_node = state["node"]
    remaining_steps = model["max_reference_steps"] - len(state["snapshots"])
    core = {
        "format": FORMAT,
        "schema": FORMAT,
        "policy_report": report,
        "policy_report_digest": state["report_digest"],
        "observation_paths": state["snapshots"],
        "observation_path_digests": [_digest(path) for path in state["snapshots"]],
        "signal_history": state["signal_history"],
        "reference_observations": state["observations"],
        "measurement_manifests": state["manifests"],
        "current_policy_state": {
            "policy_node_digest": _digest(current_node),
            "next_action": current_node["candidate_id"],
            "stop_reason": current_node["stop_reason"],
            "remaining_reference_steps": remaining_steps,
            "remaining_cost_budget": _fraction_doc(state["remaining_budget"]),
            "calibration_posterior": final_posterior,
            "target_map_accuracy": target_accuracy,
        },
        "updated_riv009_report": riv009,
        "execution_status": "authorized_interpreted_policy_prefix",
        "belief_effect": "cumulative_reference_conditioned_calibration_posterior",
        "ground_effect": "none",
        "sensor_model_effect": "none",
        "interpretation_limits": [
            "Every path is independently reconstructed through planned, dispatched, admitted, returned, evidence_authorized, and interpreted stages. The referenced external artifacts are not fetched or authenticated by this module.",
            "AUTHORIZED is accepted as a structurally valid ObservationPath decision. This module does not authenticate the authority actor, signer, policy, quorum members, or signature.",
            "Known standard labels and custody are supplied assumptions; the path binds them to each returned and interpreted event but does not prove physical truth.",
            "The cumulative RIV-009 report is rebuilt from the original calibration prior and every accepted reference observation in this prefix.",
            "The RIV-011 policy is conditional on its finite model, candidate set, target schedule, horizon, and pathwise budget.",
            "Digests provide content identity and reconstruction checks, not signatures or external-source authenticity.",
            "No source Ground or sensor likelihood model is revised by this execution record.",
        ],
    }
    return {**core, "record_digest": _digest(core)}


def validate_reference_policy_execution_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild the path prefix and cumulative RIV-009 report from retained paths."""
    if not isinstance(record, Mapping):
        raise TypeError("policy execution record must be an object")
    supplied = _copy_json(record, "policy execution record")
    digest = supplied.pop("record_digest", None)
    if not isinstance(digest, str) or not HEX_256.fullmatch(digest) or digest != _digest(supplied):
        raise PolicyExecutionError("record_digest does not match contents")
    if supplied.get("format") != FORMAT or supplied.get("schema") != FORMAT:
        raise PolicyExecutionError("unsupported policy execution record format/schema")
    rebuilt = build_reference_policy_execution_record(
        policy_report=supplied.get("policy_report"),
        observation_paths=supplied.get("observation_paths"),
    )
    if rebuilt != dict(record):
        raise PolicyExecutionError(
            "policy execution record differs from independent reconstruction"
        )
    return dict(record)


__all__ = [
    "FORMAT",
    "PolicyExecutionError",
    "PolicyExecutionMismatch",
    "PolicyExecutionStopError",
    "new_reference_policy_observation_path",
    "build_reference_policy_execution_record",
    "validate_reference_policy_execution_record",
]
