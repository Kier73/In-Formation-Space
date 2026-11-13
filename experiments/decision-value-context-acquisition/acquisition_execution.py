"""Evidence-gated execution and exact joint-belief revision for RIV-008.

The value calculator only proposes a context reader. This adapter binds one
selected reader to the existing append-only ObservationPath, requires receiver
admission and an explicit AUTHORIZED decision before interpretation, and
updates the joint posterior only for an outcome in the declared candidate
model with non-zero predictive probability.
"""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from typing import Any, Mapping, Optional

from observation_path import ObservationIntent, ObservationPath
from decision_value_acquisition import (
    build_joint_belief_document,
    validate_report,
)

_FORMAT = "in-formation.decision-value-context-measurement"
_SCHEMA = "in-formation.decision-value-context-measurement/0.1"
_INTERPRETATION_METHOD = "exact-decision-value-context-outcome-v1"
_REQUIRED_STAGES = (
    "planned",
    "dispatched",
    "admitted",
    "returned",
    "evidence_authorized",
    "interpreted",
)
_ALLOWED_SCALARS = (str, int, bool, type(None))


class DecisionValueMeasurementError(ValueError):
    """Invalid acquisition execution evidence or unreconstructable belief update."""


class DecisionValueMeasurementMismatch(DecisionValueMeasurementError):
    """The observed outcome is absent from, or impossible under, the selected model."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise DecisionValueMeasurementError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise DecisionValueMeasurementError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionValueMeasurementError(f"{label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    digest = _text(value, label)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise DecisionValueMeasurementError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _scalar(value: object, label: str) -> object:
    if type(value) not in _ALLOWED_SCALARS:
        raise DecisionValueMeasurementError(
            f"{label} must be a string, integer, Boolean, or null"
        )
    _canonical(value)
    return value


def _fraction_record(raw: object, label: str, *, positive: bool = False) -> Fraction:
    if not isinstance(raw, Mapping) or set(raw) != {"numerator", "denominator"}:
        raise DecisionValueMeasurementError(f"{label} must be an exact rational object")
    numerator, denominator = raw["numerator"], raw["denominator"]
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise DecisionValueMeasurementError(f"{label} has invalid rational components")
    result = Fraction(numerator, denominator)
    if positive and result <= 0:
        raise DecisionValueMeasurementError(f"{label} must be positive")
    return result


def _fraction_doc(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _selected_candidate(report: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        validated = validate_report(report)
    except (TypeError, ValueError, KeyError) as error:
        raise DecisionValueMeasurementError(
            f"decision-value report failed independent reconstruction: {error}"
        ) from error
    selection = validated["selection"]
    selected_id = selection["selected_sensor_id"]
    if selection["status"] != "selected" or selected_id is None:
        raise DecisionValueMeasurementError(
            "decision-value report has no eligible selected sensor to execute"
        )
    matches = [
        candidate for candidate in validated["candidate_sensor_models"]
        if candidate["sensor_id"] == selected_id
    ]
    if len(matches) != 1:
        raise DecisionValueMeasurementError(
            "selected sensor must identify exactly one retained candidate model"
        )
    return validated, dict(matches[0])


def new_acquisition_observation_path(
    *,
    decision_value_report: Mapping[str, Any],
    attempt_id: str,
    query: Optional[str] = None,
) -> ObservationPath:
    """Create a planned-only ObservationPath for the selected RIV-008 sensor.

    No dispatch occurs here. The caller/executor appends real dispatch,
    admission, return, authority, and interpretation evidence.
    """
    report, selected = _selected_candidate(decision_value_report)
    attempt = _text(attempt_id, "attempt_id")
    report_digest = _sha256(report["report_digest"], "report_digest")
    cost = _fraction_record(selected["cost"], "selected candidate cost", positive=True)
    try:
        estimated_cost = float(cost)
    except (OverflowError, ValueError) as error:
        raise DecisionValueMeasurementError("candidate cost cannot be represented by ObservationIntent") from error
    if estimated_cost <= 0.0 or estimated_cost == float("inf"):
        raise DecisionValueMeasurementError(
            "candidate cost is outside the finite positive ObservationIntent range"
        )
    intent = ObservationIntent(
        attempt_id=attempt,
        candidate_name=f"decision-value-context:{selected['sensor_id']}",
        query=query or (
            f"Acquire context dimension {selected['dimension']!r} "
            f"using sensor {selected['sensor_id']!r}"
        ),
        hypothesis_set_digest=report_digest,
        estimated_cost=estimated_cost,
        plan_ref=f"urn:sha256:{report_digest}",
        authority_required=True,
        application_required=False,
        sender_ack_required=False,
    )
    return ObservationPath(intent)


def _reconstruct_path(raw: object) -> tuple[ObservationPath, dict[str, Any]]:
    if isinstance(raw, ObservationPath):
        snapshot = raw.to_dict()
    elif isinstance(raw, Mapping):
        snapshot = _copy_json(raw, "observation_path")
    else:
        raise TypeError("observation_path must be an ObservationPath or serialized mapping")
    allowed = {"attempt_id", "intent", "status", "terminal", "events"}
    if not isinstance(snapshot, Mapping) or set(snapshot) != allowed:
        raise DecisionValueMeasurementError(
            "observation path has missing or unexpected top-level fields"
        )
    intent_data = snapshot.get("intent")
    intent_allowed = {
        "candidate_name", "query", "hypothesis_set_digest", "estimated_cost",
        "plan_ref", "authority_required", "application_required", "sender_ack_required",
    }
    if not isinstance(intent_data, Mapping) or set(intent_data) != intent_allowed:
        raise DecisionValueMeasurementError(
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
            raise DecisionValueMeasurementError("observation path requires a non-empty event list")
        for index, event in enumerate(events[1:], start=1):
            event_allowed = {
                "stage", "actor", "clock_value", "clock_domain", "evidence_ref", "details",
            }
            if not isinstance(event, Mapping) or set(event) != event_allowed:
                raise DecisionValueMeasurementError(
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
        if isinstance(error, DecisionValueMeasurementError):
            raise
        raise DecisionValueMeasurementError(
            f"observation path failed lifecycle reconstruction: {error}"
        ) from error
    rebuilt = path.to_dict()
    if rebuilt != dict(snapshot):
        raise DecisionValueMeasurementError(
            "observation path differs from independent lifecycle reconstruction"
        )
    return path, rebuilt


def _event_snapshot(snapshot: Mapping[str, Any], stage: str) -> dict[str, Any]:
    matches = [event for event in snapshot["events"] if event["stage"] == stage]
    if len(matches) != 1:
        raise DecisionValueMeasurementError(
            f"expected exactly one {stage!r} lifecycle event; found {len(matches)}"
        )
    return dict(matches[0])


def _decision(
    joint_posterior: list[Mapping[str, Any]],
    loss_matrix: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    posterior_a = sum(
        (
            Fraction(**item["probability"])
            for item in joint_posterior
            if item["hypothesis"] == "A"
        ),
        Fraction(0),
    )
    posterior_b = 1 - posterior_a
    loss_a = (
        posterior_a * Fraction(**loss_matrix["decide_a_if_hypothesis_a"])
        + posterior_b * Fraction(**loss_matrix["decide_a_if_hypothesis_b"])
    )
    loss_b = (
        posterior_a * Fraction(**loss_matrix["decide_b_if_hypothesis_a"])
        + posterior_b * Fraction(**loss_matrix["decide_b_if_hypothesis_b"])
    )
    return {
        "posterior_hypothesis_a": _fraction_doc(posterior_a),
        "posterior_hypothesis_b": _fraction_doc(posterior_b),
        "expected_loss_if_decide_a": _fraction_doc(loss_a),
        "expected_loss_if_decide_b": _fraction_doc(loss_b),
        "optimal_decision": "A" if loss_a <= loss_b else "B",
        "bayes_decision_loss": _fraction_doc(min(loss_a, loss_b)),
    }


def _posterior_after_outcome(
    prior: list[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    observed_outcome: object,
) -> tuple[list[dict[str, Any]], Fraction]:
    outcome_key = _canonical(observed_outcome)
    matches = [
        row for row in candidate["outcomes"]
        if _canonical(row["outcome"]) == outcome_key
    ]
    if len(matches) != 1:
        raise DecisionValueMeasurementMismatch(
            "observed outcome is outside the selected sensor's declared outcome set; "
            "retain it as a model mismatch and do not coerce it"
        )
    likelihood_by_state = {
        (item["hypothesis"], item["context_state"]): Fraction(**item["probability"])
        for item in matches[0]["likelihoods"]
    }
    prior_mass = {
        (item["hypothesis"], item["context_state"]): Fraction(**item["probability"])
        for item in prior
    }
    weighted = {
        key: probability * likelihood_by_state[key]
        for key, probability in prior_mass.items()
    }
    predictive_probability = sum(weighted.values(), Fraction(0))
    if predictive_probability == 0:
        raise DecisionValueMeasurementMismatch(
            "observed outcome is declared but has zero predictive probability "
            "under the selected joint belief"
        )
    posterior = [
        {
            "hypothesis": hypothesis,
            "context_state": context_state,
            "probability": _fraction_doc(mass / predictive_probability),
        }
        for (hypothesis, context_state), mass in sorted(weighted.items())
    ]
    return posterior, predictive_probability


def build_acquisition_measurement_record(
    *,
    decision_value_report: Mapping[str, Any],
    observation_path: object,
) -> dict[str, Any]:
    """Create a new joint belief from one authorized, interpreted context reading."""
    report, candidate = _selected_candidate(decision_value_report)
    path, snapshot = _reconstruct_path(observation_path)
    if path.status != "interpreted" or path.terminal:
        raise DecisionValueMeasurementError(
            "acquisition measurement must end at a non-terminal interpreted ObservationPath"
        )
    stages = tuple(event["stage"] for event in snapshot["events"])
    if stages != _REQUIRED_STAGES:
        raise DecisionValueMeasurementError(
            f"acquisition lifecycle must be exactly {_REQUIRED_STAGES!r}"
        )

    report_digest = report["report_digest"]
    intent = path.intent
    cost = _fraction_record(candidate["cost"], "candidate cost", positive=True)
    expected_cost = float(cost)
    if intent.attempt_id == "":
        raise DecisionValueMeasurementError("ObservationPath attempt_id must be non-empty")
    if intent.candidate_name != f"decision-value-context:{candidate['sensor_id']}":
        raise DecisionValueMeasurementError("ObservationPath candidate differs from selected sensor")
    if intent.hypothesis_set_digest != report_digest:
        raise DecisionValueMeasurementError("ObservationPath is not bound to the decision-value report")
    if intent.plan_ref != f"urn:sha256:{report_digest}":
        raise DecisionValueMeasurementError("ObservationPath plan_ref differs from decision-value report")
    if not intent.authority_required or intent.application_required or intent.sender_ack_required:
        raise DecisionValueMeasurementError(
            "context reading requires AUTHORIZED evidence and forbids application/ACK stages"
        )
    if intent.estimated_cost != expected_cost:
        raise DecisionValueMeasurementError("ObservationPath cost differs from selected candidate cost")

    returned = _event_snapshot(snapshot, "returned")
    authorized = _event_snapshot(snapshot, "evidence_authorized")
    interpreted = _event_snapshot(snapshot, "interpreted")
    returned_details = returned["details"]
    authorized_details = authorized["details"]
    interpreted_details = interpreted["details"]
    required_return = (
        "encounter_id", "payload_digest", "canonicalization",
        "sensor_id", "dimension", "decision_value_report_digest", "observed_outcome",
    )
    for field in required_return:
        if field not in returned_details:
            raise DecisionValueMeasurementError(f"returned.details.{field} is required")
    if returned_details["sensor_id"] != candidate["sensor_id"]:
        raise DecisionValueMeasurementError("returned sensor_id differs from selected candidate")
    if returned_details["dimension"] != candidate["dimension"]:
        raise DecisionValueMeasurementError("returned dimension differs from selected candidate")
    if returned_details["decision_value_report_digest"] != report_digest:
        raise DecisionValueMeasurementError("returned evidence is not bound to the decision-value report")
    observed_outcome = _scalar(
        returned_details["observed_outcome"], "returned.details.observed_outcome"
    )
    if interpreted_details.get("method") != _INTERPRETATION_METHOD:
        raise DecisionValueMeasurementError(
            f"interpretation method must be {_INTERPRETATION_METHOD!r}"
        )
    for field, expected in (
        ("sensor_id", candidate["sensor_id"]),
        ("dimension", candidate["dimension"]),
        ("decision_value_report_digest", report_digest),
    ):
        if interpreted_details.get(field) != expected:
            raise DecisionValueMeasurementError(
                f"interpreted.details.{field} differs from selected sensor/report"
            )
    if "observed_outcome" not in interpreted_details or (
        _canonical(_scalar(
            interpreted_details["observed_outcome"],
            "interpreted.details.observed_outcome",
        )) != _canonical(observed_outcome)
    ):
        raise DecisionValueMeasurementError(
            "returned and interpreted outcomes must match exactly, including JSON type"
        )

    prior_belief = report["joint_belief"]
    posterior, predictive_probability = _posterior_after_outcome(
        prior_belief["joint_posterior"], candidate, observed_outcome
    )
    prior_decision = _decision(
        prior_belief["joint_posterior"], report["decision_loss_matrix"]
    )
    posterior_decision = _decision(posterior, report["decision_loss_matrix"])
    realized_risk_change = (
        Fraction(**posterior_decision["bayes_decision_loss"])
        - Fraction(**prior_decision["bayes_decision_loss"])
    )
    posterior_digest = _digest(posterior)
    path_digest = _digest(snapshot)

    manifest = {
        "format": "in-formation.decision-value-measurement-manifest",
        "schema": "in-formation.decision-value-measurement-manifest/0.1",
        "decision_value_report_digest": report_digest,
        "source_joint_belief_digest": prior_belief["belief_digest"],
        "source_joint_state_id": prior_belief["source_state_id"],
        "attempt_id": intent.attempt_id,
        "sensor_id": candidate["sensor_id"],
        "dimension": candidate["dimension"],
        "cost": _fraction_doc(cost),
        "observed_outcome": observed_outcome,
        "predictive_probability": _fraction_doc(predictive_probability),
        "posterior_joint_posterior_digest": posterior_digest,
        "observation_path_digest": path_digest,
        "dispatch_evidence_ref": _event_snapshot(snapshot, "dispatched")["evidence_ref"],
        "admission_evidence_ref": _event_snapshot(snapshot, "admitted")["evidence_ref"],
        "return_evidence_ref": returned["evidence_ref"],
        "encounter_id": returned_details["encounter_id"],
        "payload_digest": returned_details["payload_digest"],
        "canonicalization": returned_details["canonicalization"],
        "authority_evidence_ref": authorized["evidence_ref"],
        "authority_policy_digest": authorized_details["policy_digest"],
        "authority_decision_digest": authorized_details["decision_digest"],
        "authority_decision_status": authorized_details["decision_status"],
        "authority_quorum": authorized_details["quorum"],
        "authority_strict": authorized_details["strict"],
        "authority_observed_sources": authorized_details["observed_sources"],
        "authority_dissenting_sources": authorized_details["dissenting_sources"],
        "authority_missing_sources": authorized_details["missing_sources"],
        "authority_representative_source": authorized_details["representative_source"],
        "interpretation_evidence_ref": interpreted["evidence_ref"],
        "interpretation_method": interpreted_details["method"],
    }
    manifest_digest = _digest(manifest)
    updated_belief = build_joint_belief_document(
        joint_posterior=posterior,
        source_ref=f"urn:sha256:{manifest_digest}",
        source_report_digest=report_digest,
    )
    manifest_with_digest = {
        **manifest,
        "measurement_manifest_digest": manifest_digest,
    }

    core = {
        "format": _FORMAT,
        "schema": _SCHEMA,
        "decision_value_report": report,
        "decision_value_report_digest": report_digest,
        "source_joint_belief_digest": prior_belief["belief_digest"],
        "attempt_id": intent.attempt_id,
        "sensor_id": candidate["sensor_id"],
        "dimension": candidate["dimension"],
        "cost": _fraction_doc(cost),
        "observed_outcome": observed_outcome,
        "outcome_predictive_probability": _fraction_doc(predictive_probability),
        "observation_path": snapshot,
        "observation_path_digest": path_digest,
        "measurement_manifest_digest": manifest_digest,
        "measurement_manifest": manifest_with_digest,
        "prior_decision": prior_decision,
        "posterior_decision": posterior_decision,
        "realized_bayes_risk_change_post_minus_pre": _fraction_doc(realized_risk_change),
        "updated_joint_belief": updated_belief,
        "measurement_status": "interpreted_authorized_observation",
        "belief_effect": "new_immutable_joint_posterior_revision",
        "ground_effect": "none",
        "model_effect": "none",
        "interpretation_limits": [
            "The ObservationPath is reconstructed against the existing append-only lifecycle; it is not proof that referenced external artifacts are authentic or available.",
            "The returned outcome must exactly match a declared sensor outcome and have non-zero predictive probability under the supplied joint belief.",
            "An outcome outside the declared set or an outcome with zero predictive probability is a model mismatch; this module does not coerce, revise likelihoods, or auto-expand the outcome set.",
            "The updated joint belief is an exact Bayesian conditioning step under the supplied candidate likelihoods. It is not a claim that those likelihoods are true.",
            "The realized posterior Bayes risk can be higher or lower than the prior risk for one observed outcome; non-negative EVSI is an expectation over all declared outcomes, not a guarantee for each realized branch.",
            "The manifest digest and report digest bind supplied content but do not authenticate actors, sensors, signatures, authority membership, or external evidence.",
            "No physical Ground or source sensor model is revised. The output is a new joint-belief snapshot tied to this measurement and the prior decision-value report.",
        ],
    }
    return {**core, "record_digest": _digest(core)}


def validate_acquisition_measurement_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild the posterior revision from the embedded report and ObservationPath."""
    if not isinstance(record, Mapping):
        raise TypeError("acquisition measurement record must be an object")
    supplied = _copy_json(record, "acquisition measurement record")
    digest = supplied.pop("record_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise DecisionValueMeasurementError("measurement record digest does not match contents")
    if supplied.get("format") != _FORMAT or supplied.get("schema") != _SCHEMA:
        raise DecisionValueMeasurementError("unsupported acquisition measurement format/schema")
    rebuilt = build_acquisition_measurement_record(
        decision_value_report=supplied.get("decision_value_report"),
        observation_path=supplied.get("observation_path"),
    )
    if rebuilt != dict(record):
        raise DecisionValueMeasurementError(
            "measurement record differs from independent reconstruction"
        )
    return dict(record)


__all__ = [
    "DecisionValueMeasurementError",
    "DecisionValueMeasurementMismatch",
    "new_acquisition_observation_path",
    "build_acquisition_measurement_record",
    "validate_acquisition_measurement_record",
]
