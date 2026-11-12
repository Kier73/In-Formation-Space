"""Portable request/result protocol for evidence-gated proof-worker handoffs.

The protocol gives an external worker the exact scoped VGI obligation for one
selected tactic candidate. A returned normalized VGI trace is imported only
when its request digest and return evidence references match the active
ProofActionAttempt.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from proof_action_execution import ProofActionAttempt, ProofAttentionSession
from proof_attention import build_proof_attention_plan
from vgi.proof import ProofGroundAdapter, VerifiedKernelReceipt


REQUEST_FORMAT = "in-formation.proof-action-request/0.1"
RESULT_FORMAT = "in-formation.proof-action-result/0.1"


class ProofActionProtocolError(ValueError):
    """Invalid worker request, result envelope, or request/return correlation."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProofActionProtocolError(
            "proof-action protocol values must be finite canonical JSON"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProofActionProtocolError(f"{label} must be non-empty text")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ProofActionProtocolError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _request_core(document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise ProofActionProtocolError("proof-action request must be an object")
    copied = _copy(dict(document))
    required = {
        "format", "attempt_id", "query_label", "plan_digest",
        "proof_ground_digest", "active_root_obligation_ids",
        "source_obligation", "candidate_transition", "attention",
        "execution_contract", "request_digest",
    }
    if set(copied) != required:
        raise ProofActionProtocolError("proof-action request fields are invalid")
    if copied["format"] != REQUEST_FORMAT:
        raise ProofActionProtocolError("unsupported proof-action request format")
    supplied_digest = _sha256(copied.pop("request_digest"), "request_digest")
    if supplied_digest != _digest(copied):
        raise ProofActionProtocolError("proof-action request digest mismatch")
    return {**copied, "request_digest": supplied_digest}


def validate_proof_action_request(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a detached, digest-checked request document."""
    request = _request_core(document)
    _text(request["attempt_id"], "attempt_id")
    _text(request["query_label"], "query_label")
    _sha256(request["plan_digest"], "plan_digest")
    _sha256(request["proof_ground_digest"], "proof_ground_digest")
    roots = request["active_root_obligation_ids"]
    if not isinstance(roots, list) or not roots or any(
        not isinstance(item, str) or not item for item in roots
    ):
        raise ProofActionProtocolError("request requires explicit active root obligation IDs")
    if roots != sorted(set(roots)):
        raise ProofActionProtocolError("active root obligation IDs must be sorted and unique")
    if not isinstance(request["source_obligation"], Mapping):
        raise ProofActionProtocolError("source_obligation must be a structured object")
    if not isinstance(request["candidate_transition"], Mapping):
        raise ProofActionProtocolError("candidate_transition must be an object")
    if not isinstance(request["attention"], Mapping):
        raise ProofActionProtocolError("attention must be an object")
    contract = request["execution_contract"]
    if not isinstance(contract, Mapping):
        raise ProofActionProtocolError("execution_contract must be an object")
    if (
        contract.get("result_evidence_ref") != request["attempt_id"]
        or contract.get("candidate_is_not_observation") is not True
        or contract.get("subgoals_are_jointly_required") != "AND"
        or contract.get("alternatives_are") != "OR"
        or contract.get("kernel_acceptance_requires_verified_receipt") is not True
        or contract.get("allowed_attempt_statuses") != ["elaborated", "timeout", "rejected"]
    ):
        raise ProofActionProtocolError("request execution contract is invalid")
    transition = request["candidate_transition"]
    if transition.get("attempt_status") != "candidate":
        raise ProofActionProtocolError("request must describe a candidate transition")
    _text(transition.get("transition_id"), "candidate transition_id")
    _text(transition.get("source_id"), "candidate source_id")
    _text(transition.get("tactic"), "candidate tactic")
    subgoals = transition.get("proposed_subgoal_ids")
    if not isinstance(subgoals, list) or any(
        not isinstance(item, str) or not item for item in subgoals
    ):
        raise ProofActionProtocolError("proposed_subgoal_ids must be a string array")
    if len(set(subgoals)) != len(subgoals):
        raise ProofActionProtocolError("proposed subgoal IDs must be unique")
    return request


def build_proof_action_request(
    session: ProofAttentionSession,
    proof_ground: Any,
) -> dict[str, Any]:
    """Build the exact request for the session's one active proof action.

    The request is portable JSON. It contains the complete structured source
    obligation (goal, local context, metavariables, assumptions, environment),
    the selected tactic candidate, and the digests which bind it to the
    session's plan and ProofGround.
    """
    if not isinstance(session, ProofAttentionSession):
        raise ProofActionProtocolError("session must be a ProofAttentionSession")
    attempt = session.active_attempt
    if not isinstance(attempt, ProofActionAttempt):
        raise ProofActionProtocolError("session has no active proof-action attempt")
    if attempt.status not in ("planned", "dispatched", "admitted", "returned"):
        raise ProofActionProtocolError(
            f"cannot build a worker request for attempt stage {attempt.status!r}"
        )

    plan = session.plan
    if (
        plan.get("plan_digest") != attempt.plan_digest
        or plan.get("proof_ground_digest") != attempt.proof_ground_digest
    ):
        raise ProofActionProtocolError("active attempt no longer matches the current plan")
    roots = plan.get("active_root_obligation_ids")
    if not isinstance(roots, list) or not roots:
        raise ProofActionProtocolError("current plan has no explicit active root intentions")

    try:
        reconstructed = build_proof_attention_plan(proof_ground, tuple(roots))
    except (TypeError, ValueError) as exc:
        raise ProofActionProtocolError(f"could not inspect supplied ProofGround: {exc}") from exc
    if reconstructed["proof_ground_digest"] != plan["proof_ground_digest"]:
        raise ProofActionProtocolError("supplied ProofGround differs from the active plan")

    candidate_actions = [
        action for action in plan.get("candidate_actions", ())
        if action.get("transition_id") == attempt.action.get("transition_id")
    ]
    if len(candidate_actions) != 1 or candidate_actions[0] != attempt.action:
        raise ProofActionProtocolError("active action is not the exact candidate in the current plan")

    transition_id = _text(attempt.action.get("transition_id"), "action.transition_id")
    edges = [
        edge for edge in proof_ground.transitions
        if getattr(edge, "transition_id", None) == transition_id
    ]
    if len(edges) != 1:
        raise ProofActionProtocolError("selected transition must identify exactly one VGI hyper-transition")
    edge = edges[0]
    source_id = _text(edge.source_id, "transition.source_id")
    tactic = _text(edge.tactic, "transition.tactic")
    subgoal_ids = tuple(edge.subgoal_ids)
    if (
        edge.attempt_status != "candidate"
        or source_id != attempt.action.get("source_obligation_id")
        or tactic != attempt.action.get("tactic")
        or list(subgoal_ids) != [
            item["obligation_id"] for item in attempt.action.get("and_bundle", ())
        ]
    ):
        raise ProofActionProtocolError("selected VGI hyper-transition differs from the planned action")
    try:
        obligation = proof_ground.obligation(source_id)
        obligation_document = obligation.to_dict()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ProofActionProtocolError("selected source obligation is unavailable") from exc
    if getattr(obligation, "fingerprint", None) != source_id:
        raise ProofActionProtocolError("source obligation fingerprint does not match its VGI ID")

    core = {
        "format": REQUEST_FORMAT,
        "attempt_id": attempt.attempt_id,
        "query_label": attempt.query_label,
        "plan_digest": attempt.plan_digest,
        "proof_ground_digest": attempt.proof_ground_digest,
        "active_root_obligation_ids": sorted(roots),
        "source_obligation": _copy(obligation_document),
        "candidate_transition": {
            "transition_id": transition_id,
            "source_id": source_id,
            "tactic": tactic,
            "proposed_subgoal_ids": list(subgoal_ids),
            "candidate_evidence_ref": getattr(edge, "evidence_ref", ""),
            "attempt_status": "candidate",
        },
        "attention": {
            "intent_root_ids": list(attempt.action["intent_root_ids"]),
            "minimum_elaboration_distance": attempt.action["minimum_elaboration_distance"],
            "or_alternative_count_at_source": attempt.action["or_alternative_count_at_source"],
            "and_bundle_width": attempt.action["and_bundle_width"],
        },
        "execution_contract": {
            "result_evidence_ref": attempt.attempt_id,
            "allowed_attempt_statuses": ["elaborated", "timeout", "rejected"],
            "candidate_is_not_observation": True,
            "subgoals_are_jointly_required": "AND",
            "alternatives_are": "OR",
            "kernel_acceptance_requires_verified_receipt": True,
        },
    }
    request = {**core, "request_digest": _digest(core)}
    return validate_proof_action_request(request)


def make_proof_action_result(
    request_document: Mapping[str, Any],
    *,
    return_evidence: Mapping[str, Any],
    proof_trace: Mapping[str, Any],
) -> dict[str, Any]:
    """Package a normalized VGI trace and the exact receipt for its raw return.

    This creates a self-consistent result envelope, not an authentication
    signature. The importer also compares return_evidence with the active
    ProofActionAttempt's previously recorded admitted-return event.
    """
    request = validate_proof_action_request(request_document)
    if not isinstance(return_evidence, Mapping):
        raise ProofActionProtocolError("return_evidence must be an object")
    receipt = _copy(dict(return_evidence))
    if set(receipt) != {
        "evidence_ref", "encounter_id", "payload_digest", "canonicalization"
    }:
        raise ProofActionProtocolError("return_evidence fields are invalid")
    _text(receipt["evidence_ref"], "return_evidence.evidence_ref")
    _text(receipt["encounter_id"], "return_evidence.encounter_id")
    _sha256(receipt["payload_digest"], "return_evidence.payload_digest")
    _text(receipt["canonicalization"], "return_evidence.canonicalization")
    if not isinstance(proof_trace, Mapping):
        raise ProofActionProtocolError("proof_trace must be a normalized VGI trace object")
    trace = _copy(dict(proof_trace))
    if trace.get("format") != ProofGroundAdapter.FORMAT:
        raise ProofActionProtocolError(
            f"proof_trace must use {ProofGroundAdapter.FORMAT}"
        )
    core = {
        "format": RESULT_FORMAT,
        "attempt_id": request["attempt_id"],
        "request_digest": request["request_digest"],
        "return_evidence": receipt,
        "proof_trace": trace,
    }
    return {**core, "result_digest": _digest(core)}


@dataclass(frozen=True)
class ImportedProofActionResult:
    """Imported ProofGround and interpreted result from one correlated return."""

    proof_ground: Any
    interpretation: dict[str, Any]
    attempt_id: str
    request_digest: str
    result_digest: str


def import_proof_action_result(
    session: ProofAttentionSession,
    proof_ground: Any,
    request_document: Mapping[str, Any],
    result_document: Mapping[str, Any],
    *,
    actor: str,
    interpretation_ref: str,
    verified_receipts: Sequence[VerifiedKernelReceipt] = (),
) -> ImportedProofActionResult:
    """Import a returned VGI trace only after request and transport correlation.

    The attempt must already have a recorded dispatch, receiver admission, and
    raw return. This importer compares the result envelope's Encounter
    reference, ID, digest, and canonicalization with that exact return event.
    VGI imports the normalized trace; ProofAttentionSession then requires one
    result edge correlated to the exact attempt ID.
    """
    request = validate_proof_action_request(request_document)
    expected_request = build_proof_action_request(session, proof_ground)
    if request != expected_request:
        raise ProofActionProtocolError("worker request does not match the active session and ProofGround")

    if not isinstance(result_document, Mapping):
        raise ProofActionProtocolError("proof-action result must be an object")
    result = _copy(dict(result_document))
    required = {
        "format", "attempt_id", "request_digest", "return_evidence",
        "proof_trace", "result_digest",
    }
    if set(result) != required or result.get("format") != RESULT_FORMAT:
        raise ProofActionProtocolError("proof-action result fields or format are invalid")
    result_core = {key: value for key, value in result.items() if key != "result_digest"}
    result_digest = _sha256(result["result_digest"], "result_digest")
    if result_digest != _digest(result_core):
        raise ProofActionProtocolError("proof-action result digest mismatch")

    attempt = session.active_attempt
    if attempt is None or attempt.attempt_id != request["attempt_id"]:
        raise ProofActionProtocolError("result does not identify the active proof-action attempt")
    if attempt.status != "returned":
        raise ProofActionProtocolError(
            f"result import requires an admitted returned payload; current stage is {attempt.status!r}"
        )
    if result["attempt_id"] != attempt.attempt_id:
        raise ProofActionProtocolError("result attempt_id does not match active attempt")
    if result["request_digest"] != request["request_digest"]:
        raise ProofActionProtocolError("result request_digest does not match the issued request")

    return_events = [event for event in attempt.events if event["stage"] == "returned"]
    if len(return_events) != 1:
        raise ProofActionProtocolError("active attempt has no unique admitted-return event")
    returned = return_events[0]
    expected_receipt = {
        "evidence_ref": returned["evidence_ref"],
        "encounter_id": returned["details"].get("encounter_id"),
        "payload_digest": returned["details"].get("payload_digest"),
        "canonicalization": returned["details"].get("canonicalization"),
    }
    receipt = result["return_evidence"]
    if not isinstance(receipt, Mapping) or _copy(dict(receipt)) != expected_receipt:
        raise ProofActionProtocolError(
            "result return_evidence does not match the active attempt's admitted return"
        )
    if (
        returned["details"].get("attempt_id") != attempt.attempt_id
        or returned["details"].get("transition_id") != attempt.action["transition_id"]
    ):
        raise ProofActionProtocolError("returned payload is not bound to the selected transition")

    try:
        updated_ground = ProofGroundAdapter.from_lean_trace(
            result["proof_trace"],
            verified_receipts=tuple(verified_receipts),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProofActionProtocolError(f"returned VGI proof trace is invalid: {exc}") from exc
    try:
        interpreted = session.interpret_result(
            updated_ground,
            actor=actor,
            interpretation_ref=interpretation_ref,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProofActionProtocolError(f"returned proof trace does not match the active action: {exc}") from exc

    return ImportedProofActionResult(
        proof_ground=updated_ground,
        interpretation=interpreted,
        attempt_id=attempt.attempt_id,
        request_digest=request["request_digest"],
        result_digest=result_digest,
    )


__all__ = [
    "REQUEST_FORMAT",
    "RESULT_FORMAT",
    "ProofActionProtocolError",
    "ImportedProofActionResult",
    "validate_proof_action_request",
    "build_proof_action_request",
    "make_proof_action_result",
    "import_proof_action_result",
]
