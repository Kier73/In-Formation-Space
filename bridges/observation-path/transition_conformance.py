"""Transition conformance and append-only revision for Trial 08 models.

This bridge compares a completed, admitted, interpreted probe attempt with one
transition in a pinned Trial 08 model. It deliberately separates:
- the model's predicted visible outcome and next state;
- the observed/interpreted outcome;
- an independently referenced before/after state witness;
- measured synchronous operation duration.

An observed mismatch creates no automatic model update. A transition override
must be proposed, explicitly validated, and then activated as a new immutable
model revision. Intervention cost remains unchanged: operation-span duration
is performance evidence, not an estimate in intervention-cost units.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_FORMAT = "in-formation.transition-conformance"
_SCHEMA = "in-formation.transition-conformance/0.1"
_LEDGER_FORMAT = "in-formation.transition-model-ledger"
_LEDGER_SCHEMA = "in-formation.transition-model-ledger/0.1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_TERMINAL = {
    "dispatch_failed", "rejected", "returned_unadmitted", "evidence_refused",
    "no_result", "application_failed", "interpretation_failed",
    "continued", "query_determined", "unresolved",
}
_ALLOWED_NEXT = {
    "planned": {"dispatched", "dispatch_failed"},
    "dispatched": {"admitted", "rejected", "dispatch_failed", "returned_unadmitted"},
    "admitted": {"returned", "no_result"},
    "returned": {"evidence_authorized", "evidence_refused", "interpreted", "interpretation_failed"},
    "evidence_authorized": {"applied", "interpreted", "application_failed", "interpretation_failed"},
    "applied": {"sender_ack_progress", "sender_acknowledged", "interpreted", "application_failed", "interpretation_failed"},
    "sender_ack_progress": {"sender_ack_progress", "sender_acknowledged", "interpretation_failed"},
    "sender_acknowledged": {"interpreted", "interpretation_failed"},
    "interpreted": {"continued", "query_determined", "unresolved"},
}

# The Trial 08 planner remains the authority for model normalization and
# reconstruction. This bridge imports it by repository-relative location.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_TRIAL_08 = _REPOSITORY_ROOT / "experiments" / "description-to-realization" / "trials" / "trial-08-intervention-aware-attention"
if str(_TRIAL_08) not in sys.path:
    sys.path.insert(0, str(_TRIAL_08))
from intervention_attention import (  # noqa: E402
    build_intervention_attention_frontier,
    validate_intervention_attention_document,
)
from operation_spans import validate_operation_span  # noqa: E402


class TransitionConformanceError(ValueError):
    """Invalid model, lifecycle, state witness, or transition revision."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TransitionConformanceError(f"{label} must be non-empty text")
    return value


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise TransitionConformanceError(
            f"value must be finite canonical JSON: {error}"
        ) from error


def _copy_json(value: object, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as error:
        raise TransitionConformanceError(f"{label} must be finite JSON data") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_digest(value: object, label: str) -> str:
    digest = _text(value, label)
    if _SHA256.fullmatch(digest) is None:
        raise TransitionConformanceError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _fraction(value: object, label: str) -> dict[str, int]:
    if isinstance(value, bool) or isinstance(value, float):
        raise TransitionConformanceError(f"{label} must be an exact rational")
    if isinstance(value, Mapping) and set(value) == {"numerator", "denominator"}:
        numerator = value["numerator"]
        denominator = value["denominator"]
        if isinstance(numerator, bool) or not isinstance(numerator, int):
            raise TransitionConformanceError(f"{label}.numerator must be an integer")
        if isinstance(denominator, bool) or not isinstance(denominator, int) or denominator <= 0:
            raise TransitionConformanceError(f"{label}.denominator must be a positive integer")
        # The Trial 08 model builder normalizes rational objects. Reuse its
        # accepted mapping form, then ensure the resulting ratio is canonical.
        from fractions import Fraction
        return {
            "numerator": Fraction(numerator, denominator).numerator,
            "denominator": Fraction(numerator, denominator).denominator,
        }
    from fractions import Fraction
    try:
        parsed = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
        raise TransitionConformanceError(f"{label} must be an exact rational") from error
    return {"numerator": parsed.numerator, "denominator": parsed.denominator}


def _event(path: Mapping[str, Any], stage: str) -> Mapping[str, Any]:
    matches = [event for event in path["events"] if event.get("stage") == stage]
    if len(matches) != 1:
        raise TransitionConformanceError(
            f"observation path must contain exactly one {stage!r} event"
        )
    return matches[0]


def _validate_path(path: Mapping[str, Any], probe_id: str) -> dict[str, Any]:
    if not isinstance(path, Mapping):
        raise TypeError("observation_path must be a mapping")
    if set(path) != {"attempt_id", "intent", "status", "terminal", "events"}:
        raise TransitionConformanceError("observation path has missing or unexpected top-level fields")
    attempt_id = _text(path["attempt_id"], "observation_path.attempt_id")
    intent = path["intent"]
    if not isinstance(intent, Mapping):
        raise TransitionConformanceError("observation_path.intent must be an object")
    if _text(intent.get("candidate_name"), "intent.candidate_name") != probe_id:
        raise TransitionConformanceError("observation candidate does not match probe_id")
    _text(intent.get("query"), "intent.query")
    _text(intent.get("hypothesis_set_digest"), "intent.hypothesis_set_digest")
    plan_ref = _text(intent.get("plan_ref"), "intent.plan_ref")
    if intent.get("application_required", False) and not intent.get("authority_required", False):
        raise TransitionConformanceError("application_required implies authority_required")
    if intent.get("sender_ack_required", False) and not intent.get("application_required", False):
        raise TransitionConformanceError("sender_ack_required implies application_required")

    events = path["events"]
    if not isinstance(events, list) or not events:
        raise TransitionConformanceError("observation_path.events must be a non-empty array")
    stages = []
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise TransitionConformanceError(f"observation_path.events[{index}] must be an object")
        stage = _text(event.get("stage"), f"events[{index}].stage")
        _text(event.get("actor"), f"events[{index}].actor")
        if not isinstance(event.get("details"), Mapping):
            raise TransitionConformanceError(f"events[{index}].details must be an object")
        stages.append(stage)
    if stages[0] != "planned":
        raise TransitionConformanceError("observation path must begin at planned")
    for current, following in zip(stages, stages[1:]):
        if following not in _ALLOWED_NEXT.get(current, set()):
            raise TransitionConformanceError(f"invalid observation lifecycle: {current} -> {following}")
    if path["status"] != stages[-1]:
        raise TransitionConformanceError("observation path status does not match its final event")
    if not isinstance(path["terminal"], bool) or path["terminal"] != (stages[-1] in _TERMINAL):
        raise TransitionConformanceError("observation path terminal flag is inconsistent")
    if stages[-1] not in {"interpreted", "continued", "query_determined", "unresolved"}:
        raise TransitionConformanceError("observation attempt did not complete interpretation")

    required = ("dispatched", "admitted", "returned", "interpreted")
    positions = []
    for stage in required:
        try:
            positions.append(stages.index(stage))
        except ValueError as error:
            raise TransitionConformanceError(f"observation path is missing {stage}") from error
    if positions != sorted(positions):
        raise TransitionConformanceError("dispatch, admission, return, and interpretation are out of order")
    for stage in required:
        _event(path, stage)

    returned = _event(path, "returned")
    returned_details = returned["details"]
    _text(returned.get("evidence_ref"), "returned.evidence_ref")
    _text(returned_details.get("encounter_id"), "returned.encounter_id")
    _text(returned_details.get("payload_digest"), "returned.payload_digest")
    _text(returned_details.get("canonicalization"), "returned.canonicalization")

    interpreted = _event(path, "interpreted")
    interpreted_details = interpreted["details"]
    _text(interpreted.get("evidence_ref"), "interpreted.evidence_ref")
    _text(interpreted_details.get("method"), "interpreted.method")
    if "interpreted_value" not in interpreted_details and "outcome" not in interpreted_details:
        raise TransitionConformanceError(
            "interpreted event must retain interpreted_value or an explicit outcome"
        )

    authority_required = bool(intent.get("authority_required", False))
    application_required = bool(intent.get("application_required", False))
    sender_ack_required = bool(intent.get("sender_ack_required", False))
    if authority_required:
        authorized = _event(path, "evidence_authorized")
        if stages.index("evidence_authorized") <= stages.index("returned"):
            raise TransitionConformanceError("evidence authorization must follow the raw return")
    if application_required:
        applied = _event(path, "applied")
        if stages.index("applied") <= stages.index("evidence_authorized"):
            raise TransitionConformanceError("receiver application must follow evidence authorization")
    if sender_ack_required:
        acknowledged = _event(path, "sender_acknowledged")
        required_stage = "applied"
        if stages.index("sender_acknowledged") <= stages.index(required_stage):
            raise TransitionConformanceError("sender acknowledgement must follow receiver application")
    return {
        "attempt_id": attempt_id,
        "plan_ref": plan_ref,
        "hypothesis_set_digest": intent["hypothesis_set_digest"],
        "returned": returned,
        "interpreted": interpreted,
        "stages": stages,
    }


def _find_transition(model_document: Mapping[str, Any], probe_id: str, current_state: str) -> tuple[dict[str, Any], dict[str, Any]]:
    probes = model_document["model"]["probes"]
    matches = [probe for probe in probes if probe["probe_id"] == probe_id]
    if len(matches) != 1:
        raise TransitionConformanceError(f"probe_id is not uniquely present in the model: {probe_id}")
    probe = matches[0]
    transition = probe["transitions"].get(current_state)
    if transition is None:
        raise TransitionConformanceError(f"model has no transition for {probe_id!r} at {current_state!r}")
    return probe, transition


def _normalize_state_witness(
    *,
    current_state: str,
    observed_next_state: Optional[str],
    before_state_ref: str,
    before_state_digest: str,
    after_state_ref: Optional[str],
    after_state_digest: Optional[str],
    world_states: set[str],
) -> dict[str, Any]:
    current_state = _text(current_state, "current_state")
    if current_state not in world_states:
        raise TransitionConformanceError("current_state is outside the declared Trial 08 world states")
    before = {
        "state": current_state,
        "evidence_ref": _text(before_state_ref, "before_state_ref"),
        "evidence_digest": _require_digest(before_state_digest, "before_state_digest"),
    }
    if observed_next_state is None:
        if after_state_ref is not None or after_state_digest is not None:
            raise TransitionConformanceError("after-state evidence requires observed_next_state")
        after = None
    else:
        observed_next_state = _text(observed_next_state, "observed_next_state")
        if observed_next_state not in world_states:
            raise TransitionConformanceError(
                "observed_next_state is not in the declared state vocabulary; state-space expansion is separate"
            )
        after = {
            "state": observed_next_state,
            "evidence_ref": _text(after_state_ref, "after_state_ref"),
            "evidence_digest": _require_digest(after_state_digest, "after_state_digest"),
        }
    return {"before": before, "after": after}


def build_transition_conformance_record(
    *,
    conformance_id: str,
    model_document: Mapping[str, Any],
    model_ref: str,
    observation_path: Mapping[str, Any],
    probe_id: str,
    current_state: str,
    observed_outcome: Any,
    before_state_ref: str,
    before_state_digest: str,
    observed_next_state: Optional[str] = None,
    after_state_ref: Optional[str] = None,
    after_state_digest: Optional[str] = None,
    operation_span: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Compare one completed observation attempt with a Trial 08 transition.

    An after-state is optional. Without it the record can compare the visible
    outcome only and is never labeled full transition conformance.
    """
    conformance_id = _text(conformance_id, "conformance_id")
    model_ref = _text(model_ref, "model_ref")
    probe_id = _text(probe_id, "probe_id")
    try:
        model = validate_intervention_attention_document(model_document)
    except (TypeError, ValueError, KeyError) as error:
        raise TransitionConformanceError(f"invalid Trial 08 model document: {error}") from error

    path_info = _validate_path(observation_path, probe_id)
    world_states = set(model["model"]["world_states"])
    state_evidence = _normalize_state_witness(
        current_state=current_state,
        observed_next_state=observed_next_state,
        before_state_ref=before_state_ref,
        before_state_digest=before_state_digest,
        after_state_ref=after_state_ref,
        after_state_digest=after_state_digest,
        world_states=world_states,
    )
    probe, predicted = _find_transition(model, probe_id, current_state)
    observed = _copy_json(observed_outcome, "observed_outcome")
    interpreted_details = path_info["interpreted"]["details"]
    path_interpreted = (
        interpreted_details["interpreted_value"]
        if "interpreted_value" in interpreted_details
        else interpreted_details["outcome"]
    )
    if _canonical(path_interpreted) != _canonical(observed):
        raise TransitionConformanceError(
            "observed_outcome does not equal the value retained by the interpreted path event"
        )

    outcome_matches = _canonical(observed) == _canonical(predicted["outcome"])
    observed_state = state_evidence["after"]["state"] if state_evidence["after"] is not None else None
    state_matches = observed_state == predicted["next_state"] if observed_state is not None else None
    if observed_state is None:
        status = "outcome_only_match" if outcome_matches else "outcome_mismatch_state_unknown"
    elif outcome_matches and state_matches:
        status = "matched"
    elif not outcome_matches and state_matches:
        status = "outcome_mismatch"
    elif outcome_matches and not state_matches:
        status = "next_state_mismatch"
    else:
        status = "transition_mismatch"

    returned_details = path_info["returned"]["details"]
    interpreted_event = path_info["interpreted"]
    operation_timing = None
    if operation_span is not None:
        try:
            span = validate_operation_span(operation_span)
        except (TypeError, ValueError, KeyError) as error:
            raise TransitionConformanceError(f"invalid operation span: {error}") from error
        if span["attempt_id"] != path_info["attempt_id"]:
            raise TransitionConformanceError("operation span attempt_id does not match observation path")
        if span["outcome"] != "succeeded" or span["clock_status"] != "measured":
            raise TransitionConformanceError(
                "operation timing must be a successful call with a measured monotonic interval"
            )
        if "probe_id" in span["context"] and span["context"]["probe_id"] != probe_id:
            raise TransitionConformanceError("operation span context probe_id does not match")
        operation_timing = {
            "span": span,
            "elapsed_ns": span["elapsed_ns"],
            "clock_actor_id": span["clock_actor_id"],
            "clock_segment_id": span["clock_segment_id"],
            "measurement_scope": span["measurement_scope"],
            "semantic_role": "performance_only_not_intervention_cost",
        }

    core = {
        "format": _FORMAT,
        "schema": _SCHEMA,
        "conformance_id": conformance_id,
        "attempt_id": path_info["attempt_id"],
        "probe_id": probe_id,
        "model_ref": model_ref,
        "model_digest": model["model_digest"],
        "plan_ref": path_info["plan_ref"],
        "hypothesis_set_digest": path_info["hypothesis_set_digest"],
        "current_state": current_state,
        "predicted_transition": {
            "outcome": _copy_json(predicted["outcome"], "predicted outcome"),
            "next_state": predicted["next_state"],
            "intervention_cost": _fraction(predicted["intervention_cost"], "predicted intervention cost"),
        },
        "observed_transition": {
            "outcome": observed,
            "next_state": observed_state,
        },
        "conformance_status": status,
        "state_evidence": state_evidence,
        "source_evidence": {
            "observation_path_digest": _digest(dict(observation_path)),
            "returned_ref": returned_details and path_info["returned"]["evidence_ref"],
            "encounter_id": returned_details["encounter_id"],
            "payload_digest": returned_details["payload_digest"],
            "canonicalization": returned_details["canonicalization"],
            "interpretation_ref": interpreted_event["evidence_ref"],
            "interpretation_method": interpreted_event["details"]["method"],
        },
        "operation_timing": operation_timing,
        "interpretation_limits": [
            "The observation-path record is checked structurally and by lifecycle order; referenced Encounter Envelopes and state witness artifacts are not fetched or authenticated here.",
            "State labels are caller-supplied identifiers bound to evidence references and digests; this builder does not inspect the referenced state snapshots.",
            "A matched record establishes agreement with this supplied model on this supplied attempt, not universal transition correctness.",
            "An outcome-only record does not establish the hidden next state and is never labeled full transition conformance.",
            "Operation-span duration is retained as performance evidence only and is never converted into intervention_cost.",
            "The Trial 08 intervention_cost remains the supplied model value until a separate, dimensionally compatible calibration is validated.",
            "A mismatch creates a proposal opportunity; it does not automatically update the active model or VGI Ground.",
        ],
    }
    return {**core, "conformance_digest": _digest(core)}


def validate_transition_conformance_record(
    record: Mapping[str, Any],
    *,
    model_document: Mapping[str, Any],
    observation_path: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild a conformance record from the pinned model and source path."""
    if not isinstance(record, Mapping):
        raise TypeError("transition conformance record must be a mapping")
    supplied = dict(record)
    digest = supplied.pop("conformance_digest", None)
    if not isinstance(digest, str) or digest != _digest(supplied):
        raise TransitionConformanceError("transition conformance digest does not match its contents")
    operation_timing = supplied.get("operation_timing")
    operation_span = None if operation_timing is None else operation_timing.get("span")
    state_evidence = supplied.get("state_evidence")
    if not isinstance(state_evidence, Mapping) or not isinstance(state_evidence.get("before"), Mapping):
        raise TransitionConformanceError("state_evidence.before is missing")
    after = state_evidence.get("after")
    rebuilt = build_transition_conformance_record(
        conformance_id=supplied["conformance_id"],
        model_document=model_document,
        model_ref=supplied["model_ref"],
        observation_path=observation_path,
        probe_id=supplied["probe_id"],
        current_state=supplied["current_state"],
        observed_outcome=supplied["observed_transition"]["outcome"],
        before_state_ref=state_evidence["before"]["evidence_ref"],
        before_state_digest=state_evidence["before"]["evidence_digest"],
        observed_next_state=None if after is None else after["state"],
        after_state_ref=None if after is None else after["evidence_ref"],
        after_state_digest=None if after is None else after["evidence_digest"],
        operation_span=operation_span,
    )
    if rebuilt != dict(record):
        raise TransitionConformanceError(
            "transition conformance record differs from independent reconstruction"
        )
    return dict(record)


class TransitionModelRevisionLedger:
    """Append-only ledger for validated, cell-specific Trial 08 transition updates.

    Proposals can change the predicted visible outcome and next-state label for
    one (probe_id, current_state) cell. The model's abstract intervention cost
    is deliberately preserved. Activation requires an explicit supported
    validation result and creates a new Trial 08 model document/revision.
    """

    def __init__(
        self,
        model_document: Mapping[str, Any],
        *,
        initial_revision_id: str = "transition-model-0001",
        author: str = "transition-model-ledger",
    ) -> None:
        initial_revision_id = _text(initial_revision_id, "initial_revision_id")
        author = _text(author, "author")
        try:
            initial = validate_intervention_attention_document(model_document)
        except (TypeError, ValueError, KeyError) as error:
            raise TransitionConformanceError(f"invalid initial Trial 08 model: {error}") from error
        self._current_model = _copy_json(initial, "initial model")
        self._current_revision_id = initial_revision_id
        self._revisions = [self._make_revision(
            initial_revision_id, None, self._current_model, (), author
        )]
        self._candidates: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._append_event("revision_created", author, {
            "revision_id": initial_revision_id,
            "parent_revision_id": None,
            "model_digest": initial["model_digest"],
        })

    @staticmethod
    def _make_revision(
        revision_id: str,
        parent_revision_id: Optional[str],
        model_document: Mapping[str, Any],
        activated_candidate_ids: Sequence[str],
        actor: str,
    ) -> dict[str, Any]:
        core = {
            "revision_id": revision_id,
            "parent_revision_id": parent_revision_id,
            "model_document": _copy_json(model_document, "model_document"),
            "model_digest": model_document["model_digest"],
            "activated_candidate_ids": list(activated_candidate_ids),
            "actor": actor,
        }
        return {**core, "revision_digest": _digest(core)}

    def _append_event(self, event_type: str, actor: str, details: Mapping[str, Any]) -> None:
        event = {
            "event_id": f"transition-event-{len(self._events) + 1:06d}",
            "event_type": event_type,
            "actor": _text(actor, "actor"),
            "details": _copy_json(dict(details), "event details"),
        }
        event["event_digest"] = _digest(event)
        self._events.append(event)

    @property
    def current_model_document(self) -> dict[str, Any]:
        return _copy_json(self._current_model, "current_model_document")

    @property
    def current_revision_id(self) -> str:
        return self._current_revision_id

    @property
    def revisions(self) -> tuple[dict[str, Any], ...]:
        return tuple(_copy_json(item, "revision") for item in self._revisions)

    @property
    def candidates(self) -> tuple[dict[str, Any], ...]:
        return tuple(_copy_json(item, "candidate") for item in self._candidates.values())

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(_copy_json(item, "event") for item in self._events)

    def propose_transition(
        self,
        candidate_id: str,
        conformance_record: Mapping[str, Any],
        *,
        proposer: str,
    ) -> dict[str, Any]:
        candidate_id = _text(candidate_id, "candidate_id")
        proposer = _text(proposer, "proposer")
        if candidate_id in self._candidates:
            raise ValueError(f"candidate_id already exists: {candidate_id}")
        record = _copy_json(conformance_record, "conformance_record")
        digest = record.pop("conformance_digest", None)
        if not isinstance(digest, str) or digest != _digest(record):
            raise TransitionConformanceError("source conformance record digest is invalid")
        if record.get("format") != _FORMAT or record.get("schema") != _SCHEMA:
            raise TransitionConformanceError("unsupported transition conformance record")
        if record.get("model_digest") != self._current_model["model_digest"]:
            raise TransitionConformanceError("stale transition proposal: source model is not active")
        if record.get("conformance_status") not in {
            "outcome_mismatch", "next_state_mismatch", "transition_mismatch"
        }:
            raise TransitionConformanceError(
                "only a full observed transition mismatch can propose a model update"
            )
        observed = record.get("observed_transition")
        if not isinstance(observed, Mapping) or observed.get("next_state") is None:
            raise TransitionConformanceError("model update proposal requires an observed next-state witness")
        if observed["next_state"] not in self._current_model["model"]["world_states"]:
            raise TransitionConformanceError("observed next state is outside the active model vocabulary")
        _find_transition(self._current_model, record["probe_id"], record["current_state"])
        candidate = {
            "candidate_id": candidate_id,
            "status": "proposed",
            "base_revision_id": self._current_revision_id,
            "base_model_digest": self._current_model["model_digest"],
            "probe_id": record["probe_id"],
            "current_state": record["current_state"],
            "proposed_outcome": observed["outcome"],
            "proposed_next_state": observed["next_state"],
            "preserved_intervention_cost": record["predicted_transition"]["intervention_cost"],
            "source_attempt_id": record["attempt_id"],
            "source_conformance_digest": digest,
            "source_model_ref": record["model_ref"],
            "validation_result": None,
            "validation_ref": None,
            "validator": None,
            "activated_revision_id": None,
        }
        self._candidates[candidate_id] = candidate
        self._append_event("transition_proposed", proposer, candidate)
        return _copy_json(candidate, "candidate")

    def validate_candidate(
        self,
        candidate_id: str,
        result: str,
        *,
        validation_ref: str,
        validator: str,
    ) -> dict[str, Any]:
        candidate_id = _text(candidate_id, "candidate_id")
        validation_ref = _text(validation_ref, "validation_ref")
        validator = _text(validator, "validator")
        if result not in {"supported", "rejected", "inconclusive"}:
            raise ValueError("validation result must be supported, rejected, or inconclusive")
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate["validation_result"] is not None:
            raise ValueError("transition candidate already has a validation result")
        if candidate["status"] != "proposed":
            raise ValueError("only a proposed transition candidate can be validated")
        updated = dict(candidate)
        updated["status"] = "validated_" + result
        updated["validation_result"] = result
        updated["validation_ref"] = validation_ref
        updated["validator"] = validator
        self._candidates[candidate_id] = updated
        self._append_event("transition_validated", validator, {
            "candidate_id": candidate_id,
            "result": result,
            "validation_ref": validation_ref,
            "base_model_digest": candidate["base_model_digest"],
        })
        return _copy_json(updated, "candidate")

    def activate_supported(
        self,
        candidate_ids: Sequence[str],
        *,
        revision_id: str,
        actor: str,
    ) -> dict[str, Any]:
        revision_id = _text(revision_id, "revision_id")
        actor = _text(actor, "actor")
        if not isinstance(candidate_ids, (list, tuple)) or not candidate_ids:
            raise ValueError("candidate_ids must be a non-empty sequence")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_ids must be unique")
        if any(revision["revision_id"] == revision_id for revision in self._revisions):
            raise ValueError(f"revision_id already exists: {revision_id}")
        selected = []
        for candidate_id in candidate_ids:
            candidate = self._candidates.get(_text(candidate_id, "candidate_id"))
            if candidate is None:
                raise KeyError(candidate_id)
            if candidate["status"] != "validated_supported":
                raise ValueError(f"candidate is not validated as supported: {candidate_id}")
            if candidate["base_revision_id"] != self._current_revision_id:
                raise TransitionConformanceError(f"stale candidate: {candidate_id}")
            selected.append(candidate)

        cells = [(item["probe_id"], item["current_state"]) for item in selected]
        if len(set(cells)) != len(cells):
            raise ValueError("activation cannot include multiple proposals for the same probe/state cell")

        updated = _copy_json(self._current_model, "current model")
        for candidate in selected:
            _, transition = _find_transition(
                updated, candidate["probe_id"], candidate["current_state"]
            )
            transition["outcome"] = _copy_json(candidate["proposed_outcome"], "proposed outcome")
            transition["next_state"] = candidate["proposed_next_state"]
            # Preserve the existing abstract intervention cost. No timing span
            # or unrelated measurement is promoted into this model quantity.

        model = updated["model"]
        limits = updated["solver_limits"]
        rebuilt = build_intervention_attention_frontier(
            world_states=model["world_states"],
            hypotheses=model["hypotheses"],
            probes=model["probes"],
            max_depth=updated["max_depth"],
            max_hypotheses=limits["max_hypotheses"],
            max_frontier=limits["max_frontier"],
            max_combinations=limits["max_combinations"],
        )
        new_revision = self._make_revision(
            revision_id, self._current_revision_id, rebuilt,
            [item["candidate_id"] for item in selected], actor,
        )
        self._revisions.append(new_revision)
        self._current_model = rebuilt
        self._current_revision_id = revision_id
        for candidate in selected:
            updated_candidate = dict(self._candidates[candidate["candidate_id"]])
            updated_candidate["status"] = "activated"
            updated_candidate["activated_revision_id"] = revision_id
            self._candidates[candidate["candidate_id"]] = updated_candidate
        self._append_event("revision_activated", actor, {
            "revision_id": revision_id,
            "parent_revision_id": new_revision["parent_revision_id"],
            "model_digest": rebuilt["model_digest"],
            "activated_candidate_ids": [item["candidate_id"] for item in selected],
            "intervention_cost_policy": "preserved_from_parent",
        })
        return _copy_json(new_revision, "revision")

    def to_dict(self) -> dict[str, Any]:
        core = {
            "format": _LEDGER_FORMAT,
            "schema": _LEDGER_SCHEMA,
            "current_revision_id": self._current_revision_id,
            "revisions": list(self.revisions),
            "candidates": list(self.candidates),
            "events": list(self.events),
            "interpretation_limits": [
                "Conformance records retain references and digests; referenced artifacts are not fetched or authenticated by this ledger.",
                "Candidate validation is an explicit caller-supplied decision and is not independently authenticated here.",
                "Only validated_supported candidates can be activated; rejected and inconclusive proposals remain in history.",
                "Activation creates a new immutable planner model revision and preserves the parent's intervention_cost for the updated transition.",
                "Observed operation duration is not a calibration of intervention cost and never changes that field.",
                "State-space vocabulary expansion, stochastic transitions, and autonomous dynamics require separate versioned operations.",
            ],
        }
        return {**core, "ledger_digest": _digest(core)}
