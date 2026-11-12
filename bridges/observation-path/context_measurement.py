"""Bind an executed context observation to its VGI policy and evidence path.

This bridge reconstructs the existing ObservationPath lifecycle, requires an
explicit authority decision before interpreting a context scalar, and creates
a new immutable context-analysis snapshot. It does not change a physical Ground
or Trial 08 transition model.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping, Optional

from context_attention import validate_context_attention_plan
from observation_path import ObservationIntent, ObservationPath
from transition_context import (
    build_transition_context_analysis,
    build_transition_context_assignment,
    validate_transition_context_analysis,
)

_FORMAT = "in-formation.context-measurement-evidence"
_SCHEMA = "in-formation.context-measurement-evidence/0.1"
_INTERPRETATION_METHOD = "exact-context-scalar-v1"
_ALLOWED_SCALARS = (str, int, bool, type(None))
_REQUIRED_STAGES = (
    "planned",
    "dispatched",
    "admitted",
    "returned",
    "evidence_authorized",
    "interpreted",
)


class ContextMeasurementError(ValueError):
    """Invalid context measurement evidence or unreconstructable analysis."""


class ContextMeasurementMismatch(ContextMeasurementError):
    """A returned context value is not among the selected policy's branches."""


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
        raise ContextMeasurementError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise ContextMeasurementError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextMeasurementError(f"{label} must be non-empty text")
    return value


def _sha256(value: object, label: str) -> str:
    digest = _text(value, label)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContextMeasurementError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _scalar(value: object, label: str) -> object:
    if type(value) not in _ALLOWED_SCALARS:
        raise ContextMeasurementError(
            f"{label} must be a string, integer, Boolean, or null"
        )
    _canonical(value)
    return value


def _validated_sources(
    *,
    context_analysis: Mapping[str, Any],
    policy_report: Mapping[str, Any],
    model_document: Mapping[str, Any],
    vgi_api: object,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        source = validate_transition_context_analysis(
            context_analysis, model_document=model_document
        )
        policy = validate_context_attention_plan(
            policy_report,
            context_analysis=source,
            model_document=model_document,
            vgi_api=vgi_api,
        )
    except (TypeError, ValueError, KeyError) as error:
        raise ContextMeasurementError(
            f"source context analysis or attention policy failed reconstruction: {error}"
        ) from error

    if policy["source_context_analysis_digest"] != source["analysis_digest"]:
        raise ContextMeasurementError(
            "attention policy is not derived from the supplied context analysis"
        )
    next_measurement = policy.get("next_measurement")
    if not isinstance(next_measurement, Mapping):
        raise ContextMeasurementError("attention policy has no next measurement to execute")
    required = {
        "attempt_id", "method_id", "dimension", "label", "cost",
        "declared_scenario_values", "status",
    }
    if set(next_measurement) != required:
        raise ContextMeasurementError("next_measurement has missing or unexpected fields")
    _text(next_measurement["attempt_id"], "next_measurement.attempt_id")
    _text(next_measurement["method_id"], "next_measurement.method_id")
    _text(next_measurement["dimension"], "next_measurement.dimension")
    _text(next_measurement["label"], "next_measurement.label")
    if next_measurement["status"] not in {"unknown", "not_supplied", "unassigned"}:
        raise ContextMeasurementError(
            "selected next measurement must target unknown, not-supplied, or unassigned context"
        )
    cost = next_measurement["cost"]
    if not isinstance(cost, Mapping) or set(cost) != {"numerator", "denominator"}:
        raise ContextMeasurementError("next measurement cost must be an exact rational object")
    numerator, denominator = cost["numerator"], cost["denominator"]
    if (
        type(numerator) is not int or numerator <= 0
        or type(denominator) is not int or denominator <= 0
    ):
        raise ContextMeasurementError("next measurement cost has invalid rational components")
    values = next_measurement["declared_scenario_values"]
    if not isinstance(values, list) or not values:
        raise ContextMeasurementError("next measurement must declare at least one scenario value")
    normalized = [_scalar(value, f"declared_scenario_values[{index}]")
                  for index, value in enumerate(values)]
    if len({_canonical(value) for value in normalized}) != len(normalized):
        raise ContextMeasurementError("declared context scenario values must be unique")

    matching_records = [
        record for record in source["source_conformance_records"]
        if record["attempt_id"] == next_measurement["attempt_id"]
    ]
    if len(matching_records) != 1:
        raise ContextMeasurementError(
            "selected attempt must bind to exactly one embedded conformance record"
        )
    assignments = [
        item for item in source["source_context_assignments"]
        if item["attempt_id"] == next_measurement["attempt_id"]
    ]
    if len(assignments) > 1:
        raise ContextMeasurementError("selected attempt has duplicate context assignments")
    if assignments:
        descriptor = assignments[0]["dimensions"].get(next_measurement["dimension"])
        if descriptor is not None and descriptor["status"] == "observed":
            raise ContextMeasurementError(
                "selected context dimension is already observed; stale attention policy"
            )
    return source, policy, dict(next_measurement)


def new_context_measurement_path(
    *,
    context_analysis: Mapping[str, Any],
    policy_report: Mapping[str, Any],
    model_document: Mapping[str, Any],
    vgi_api: object,
    query: Optional[str] = None,
) -> ObservationPath:
    """Create a required-authority ObservationPath for the policy's next measurement.

    The returned path is planned only. An executor must append dispatch,
    admission, return, authority, and interpretation events using real evidence.
    """
    _, policy, selected = _validated_sources(
        context_analysis=context_analysis,
        policy_report=policy_report,
        model_document=model_document,
        vgi_api=vgi_api,
    )
    report_digest = _sha256(policy["report_digest"], "policy report_digest")
    cost = Fraction(
        selected["cost"]["numerator"], selected["cost"]["denominator"]
    )
    method_id = selected["method_id"]
    dimension = selected["dimension"]
    attempt_id = selected["attempt_id"]
    intent = ObservationIntent(
        attempt_id=attempt_id,
        candidate_name=f"context-capture:{method_id}",
        query=query or (
            f"Capture context dimension {dimension!r} for attempt {attempt_id!r} "
            f"using method {method_id!r}"
        ),
        hypothesis_set_digest=report_digest,
        estimated_cost=float(cost),
        plan_ref=f"urn:sha256:{report_digest}",
        authority_required=True,
        application_required=False,
        sender_ack_required=False,
    )
    return ObservationPath(intent)


def _reconstruct_observation_path(raw: object) -> tuple[ObservationPath, dict[str, Any]]:
    if isinstance(raw, ObservationPath):
        snapshot = raw.to_dict()
    elif isinstance(raw, Mapping):
        snapshot = _copy_json(raw, "observation_path")
    else:
        raise TypeError("observation_path must be an ObservationPath or serialized mapping")

    if not isinstance(snapshot, Mapping):
        raise ContextMeasurementError("observation path snapshot must be an object")
    allowed = {"attempt_id", "intent", "status", "terminal", "events"}
    if set(snapshot) != allowed:
        raise ContextMeasurementError("observation path has missing or unexpected top-level fields")
    intent_data = snapshot.get("intent")
    if not isinstance(intent_data, Mapping):
        raise ContextMeasurementError("observation path intent must be an object")
    intent_allowed = {
        "candidate_name", "query", "hypothesis_set_digest", "estimated_cost",
        "plan_ref", "authority_required", "application_required", "sender_ack_required",
    }
    if set(intent_data) != intent_allowed:
        raise ContextMeasurementError("observation path intent has missing or unexpected fields")
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
        events = snapshot.get("events")
        if not isinstance(events, list) or not events:
            raise ContextMeasurementError("observation path requires a non-empty event array")
        if not isinstance(events[0], Mapping):
            raise ContextMeasurementError("planned event must be an object")
        for index, event in enumerate(events[1:], start=1):
            if not isinstance(event, Mapping):
                raise ContextMeasurementError(f"observation path event {index} must be an object")
            event_allowed = {
                "stage", "actor", "clock_value", "clock_domain", "evidence_ref", "details",
            }
            if set(event) != event_allowed:
                raise ContextMeasurementError(
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
        if isinstance(error, ContextMeasurementError):
            raise
        raise ContextMeasurementError(f"observation path failed lifecycle reconstruction: {error}") from error

    rebuilt = path.to_dict()
    if rebuilt != dict(snapshot):
        raise ContextMeasurementError(
            "observation path snapshot differs from lifecycle reconstruction"
        )
    return path, rebuilt


def _event(path: ObservationPath, stage: str):
    matches = [event for event in path.events if event.stage == stage]
    if len(matches) != 1:
        raise ContextMeasurementError(
            f"expected exactly one {stage!r} event; found {len(matches)}"
        )
    return matches[0]


def _manifest(
    *,
    source: Mapping[str, Any],
    policy: Mapping[str, Any],
    selected: Mapping[str, Any],
    conformance_record: Mapping[str, Any],
    prior_assignment: Optional[Mapping[str, Any]],
    path_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    stages = {
        stage: _event_from_snapshot(path_snapshot, stage)
        for stage in ("dispatched", "admitted", "returned", "evidence_authorized", "interpreted")
    }
    returned = stages["returned"]
    authority = stages["evidence_authorized"]
    interpreted = stages["interpreted"]
    returned_details = returned["details"]
    authority_details = authority["details"]
    interpreted_details = interpreted["details"]
    prior_digest = prior_assignment.get("assignment_digest") if prior_assignment else None
    prior_source = prior_assignment.get("source_ref") if prior_assignment else None
    return {
        "format": "in-formation.context-measurement-manifest",
        "schema": "in-formation.context-measurement-manifest/0.1",
        "policy_report_digest": policy["report_digest"],
        "source_context_analysis_digest": source["analysis_digest"],
        "attempt_id": selected["attempt_id"],
        "conformance_digest": conformance_record["conformance_digest"],
        "method_id": selected["method_id"],
        "dimension": selected["dimension"],
        "observed_value": interpreted_details["context_value"],
        "observation_path_digest": _digest(path_snapshot),
        "prior_assignment_digest": prior_digest,
        "prior_source_ref": prior_source,
        "dispatch_evidence_ref": stages["dispatched"]["evidence_ref"],
        "admission_evidence_ref": stages["admitted"]["evidence_ref"],
        "return_evidence_ref": returned["evidence_ref"],
        "encounter_id": returned_details["encounter_id"],
        "payload_digest": returned_details["payload_digest"],
        "canonicalization": returned_details["canonicalization"],
        "authority_evidence_ref": authority["evidence_ref"],
        "authority_policy_digest": authority_details["policy_digest"],
        "authority_decision_digest": authority_details["decision_digest"],
        "authority_decision_status": authority_details["decision_status"],
        "authority_quorum": authority_details["quorum"],
        "authority_strict": authority_details["strict"],
        "authority_observed_sources": authority_details["observed_sources"],
        "authority_dissenting_sources": authority_details["dissenting_sources"],
        "authority_missing_sources": authority_details["missing_sources"],
        "authority_representative_source": authority_details["representative_source"],
        "interpretation_evidence_ref": interpreted["evidence_ref"],
        "interpretation_method": interpreted_details["method"],
    }


def _event_from_snapshot(snapshot: Mapping[str, Any], stage: str) -> dict[str, Any]:
    matches = [event for event in snapshot["events"] if event["stage"] == stage]
    if len(matches) != 1:
        raise ContextMeasurementError(
            f"expected exactly one {stage!r} event in observation path"
        )
    return dict(matches[0])


def build_context_measurement_record(
    *,
    context_analysis: Mapping[str, Any],
    policy_report: Mapping[str, Any],
    model_document: Mapping[str, Any],
    observation_path: object,
    vgi_api: object,
) -> dict[str, Any]:
    """Validate one authorized measurement and create the next context-analysis revision."""
    source, policy, selected = _validated_sources(
        context_analysis=context_analysis,
        policy_report=policy_report,
        model_document=model_document,
        vgi_api=vgi_api,
    )
    path, snapshot = _reconstruct_observation_path(observation_path)
    if path.status != "interpreted" or path.terminal:
        raise ContextMeasurementError(
            "context measurement must end at a non-terminal interpreted ObservationPath"
        )
    stages = tuple(event.stage for event in path.events)
    if stages != _REQUIRED_STAGES:
        raise ContextMeasurementError(
            f"context measurement lifecycle must be exactly {_REQUIRED_STAGES!r}"
        )
    intent = path.intent
    report_digest = policy["report_digest"]
    expected_cost = Fraction(selected["cost"]["numerator"], selected["cost"]["denominator"])
    if intent.attempt_id != selected["attempt_id"]:
        raise ContextMeasurementError("ObservationPath attempt_id differs from policy recommendation")
    if intent.candidate_name != f"context-capture:{selected['method_id']}":
        raise ContextMeasurementError("ObservationPath candidate_name differs from policy method")
    if intent.hypothesis_set_digest != report_digest:
        raise ContextMeasurementError("ObservationPath is not bound to the attention report digest")
    if intent.plan_ref != f"urn:sha256:{report_digest}":
        raise ContextMeasurementError("ObservationPath plan_ref differs from attention report")
    if not intent.authority_required or intent.application_required or intent.sender_ack_required:
        raise ContextMeasurementError(
            "context measurement requires authority and does not permit application or sender ACK"
        )
    if intent.estimated_cost != float(expected_cost):
        raise ContextMeasurementError("ObservationPath estimated cost differs from exact policy cost")

    returned = _event(path, "returned")
    authority = _event(path, "evidence_authorized")
    interpreted = _event(path, "interpreted")
    returned_details = returned.details
    interpreted_details = interpreted.details
    for field in (
        "method_id", "dimension", "context_attention_report_digest",
    ):
        _text(returned_details.get(field), f"returned.details.{field}")
    if returned_details["method_id"] != selected["method_id"]:
        raise ContextMeasurementError("returned context method_id differs from policy recommendation")
    if returned_details["dimension"] != selected["dimension"]:
        raise ContextMeasurementError("returned context dimension differs from policy recommendation")
    if returned_details["context_attention_report_digest"] != report_digest:
        raise ContextMeasurementError("returned evidence is not bound to the attention report")
    if interpreted_details.get("method") != _INTERPRETATION_METHOD:
        raise ContextMeasurementError(
            f"interpretation method must be {_INTERPRETATION_METHOD!r}"
        )
    if interpreted_details.get("method_id") != selected["method_id"]:
        raise ContextMeasurementError("interpreted method_id differs from policy recommendation")
    if interpreted_details.get("dimension") != selected["dimension"]:
        raise ContextMeasurementError("interpreted dimension differs from policy recommendation")
    if interpreted_details.get("context_attention_report_digest") != report_digest:
        raise ContextMeasurementError("interpretation is not bound to the attention report")
    observed_value = _scalar(
        interpreted_details.get("context_value"), "interpreted context_value"
    )
    declared = selected["declared_scenario_values"]
    if _canonical(observed_value) not in {_canonical(value) for value in declared}:
        raise ContextMeasurementMismatch(
            "observed context value is outside the declared VGI scenario set; "
            "preserve it as an out-of-model encounter and do not coerce it"
        )
    if "context_value" not in returned_details or (
        _canonical(_scalar(returned_details["context_value"], "returned context_value"))
        != _canonical(observed_value)
    ):
        raise ContextMeasurementError(
            "returned context value and interpreted context value do not match exactly"
        )

    conformance_records = source["source_conformance_records"]
    conformance_record = next(
        record for record in conformance_records
        if record["attempt_id"] == selected["attempt_id"]
    )
    prior_matches = [
        item for item in source["source_context_assignments"]
        if item["attempt_id"] == selected["attempt_id"]
    ]
    prior_assignment = prior_matches[0] if prior_matches else None
    dimensions = dict(prior_assignment["dimensions"]) if prior_assignment else {}
    prior_descriptor = dimensions.get(selected["dimension"])
    if prior_descriptor is not None and prior_descriptor["status"] == "observed":
        raise ContextMeasurementError("cannot overwrite an already observed context dimension")
    dimensions[selected["dimension"]] = {
        "status": "observed",
        "value": observed_value,
    }

    manifest = _manifest(
        source=source,
        policy=policy,
        selected=selected,
        conformance_record=conformance_record,
        prior_assignment=prior_assignment,
        path_snapshot=snapshot,
    )
    manifest_digest = _digest(manifest)
    new_assignment = build_transition_context_assignment(
        attempt_id=selected["attempt_id"],
        conformance_record=conformance_record,
        dimensions=dimensions,
        source_ref=f"urn:sha256:{manifest_digest}",
    )
    assignments = [
        item for item in source["source_context_assignments"]
        if item["attempt_id"] != selected["attempt_id"]
    ]
    assignments.append(new_assignment)
    assignments.sort(key=lambda item: item["attempt_id"])
    updated_analysis = build_transition_context_analysis(
        model_document=model_document,
        conformance_records=conformance_records,
        context_assignments=assignments,
    )
    manifest_with_digest = {
        **manifest,
        "measurement_manifest_digest": manifest_digest,
    }
    core = {
        "format": _FORMAT,
        "schema": _SCHEMA,
        "source_context_analysis_digest": source["analysis_digest"],
        "policy_report_digest": report_digest,
        "attempt_id": selected["attempt_id"],
        "conformance_digest": conformance_record["conformance_digest"],
        "method_id": selected["method_id"],
        "dimension": selected["dimension"],
        "observed_value": observed_value,
        "observation_path": snapshot,
        "observation_path_digest": _digest(snapshot),
        "prior_context_assignment": prior_assignment,
        "context_assignment": new_assignment,
        "measurement_manifest_digest": manifest_digest,
        "measurement_manifest": manifest_with_digest,
        "updated_context_analysis": updated_analysis,
        "execution_status": "interpreted_authorized_context_measurement",
        "context_analysis_effect": "new_immutable_analysis_revision",
        "ground_effect": "none",
        "model_effect": "none",
        "interpretation_limits": [
            "The ObservationPath is reconstructed against the existing append-only lifecycle and includes an explicit AUTHORIZED evidence decision before interpretation.",
            "The Encounter Envelope, state witnesses, decision artifacts, and context source are referenced but not fetched or authenticated by this module.",
            "SHA-256 digests bind the supplied record contents; they do not authenticate actors, signatures, external evidence, or authority membership.",
            "The context value is accepted only when exactly present in the selected policy's declared scenario values; an out-of-set value is a model mismatch, not a nearest-branch approximation.",
            "The updated context analysis is rebuilt from the original independently reconstructed conformance records and the new assignment; the original analysis remains unchanged.",
            "No VGI Ground, Trial 08 transition model, intervention cost, or active attention policy is modified by recording this context measurement.",
            "A newly computed attention policy must be built from the updated context analysis; the previous proposal is not reused as though its evidence snapshot had changed.",
        ],
    }
    return {**core, "record_digest": _digest(core)}


def validate_context_measurement_record(
    record: Mapping[str, Any],
    *,
    context_analysis: Mapping[str, Any],
    policy_report: Mapping[str, Any],
    model_document: Mapping[str, Any],
    vgi_api: object,
) -> dict[str, Any]:
    """Rebuild a measurement record from its source analysis, policy, and embedded path."""
    if not isinstance(record, Mapping):
        raise TypeError("context measurement record must be a mapping")
    supplied = _copy_json(record, "context measurement record")
    digest = supplied.pop("record_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise ContextMeasurementError("context measurement record digest does not match contents")
    if supplied.get("format") != _FORMAT or supplied.get("schema") != _SCHEMA:
        raise ContextMeasurementError("unsupported context measurement record format/schema")
    rebuilt = build_context_measurement_record(
        context_analysis=context_analysis,
        policy_report=policy_report,
        model_document=model_document,
        observation_path=supplied.get("observation_path"),
        vgi_api=vgi_api,
    )
    if rebuilt != dict(record):
        raise ContextMeasurementError(
            "context measurement record differs from independent reconstruction"
        )
    return dict(record)


__all__ = [
    "ContextMeasurementError",
    "ContextMeasurementMismatch",
    "new_context_measurement_path",
    "build_context_measurement_record",
    "validate_context_measurement_record",
]
