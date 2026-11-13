"""Signed completion receipts for stable E-CPU proof-runner tickets.

This is an isolated reference experiment. It verifies that a runner key signed
an exact, request-correlated proof-action result after a particular route
authority event granted an execution ticket. It does not verify that a tactic
was honestly executed or that a proof was accepted by a kernel.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


RECEIPT_FORMAT = "in-formation.proof-runner-completion-receipt/0.1"
REQUEST_FORMAT = "in-formation.proof-action-request/0.1"
RESULT_FORMAT = "in-formation.proof-action-result/0.1"
SIGNATURE_ALGORITHM = "Ed25519"


class CompletionReceiptError(ValueError):
    """Invalid authority event, request, result, receipt, or runner identity."""


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
        raise CompletionReceiptError(
            "receipt material must be finite canonical JSON"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CompletionReceiptError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompletionReceiptError(f"{label} must be non-empty text")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise CompletionReceiptError(f"{label} must be a positive integer")
    return value


def _copy_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CompletionReceiptError(f"{label} must be an object")
    try:
        return json.loads(_canonical(dict(value)))
    except (TypeError, ValueError) as exc:
        raise CompletionReceiptError(f"{label} must be finite JSON data") from exc


def derive_execution_id(
    route_epoch_id: str,
    attempt_id: str,
    request_digest: str,
) -> str:
    """Reproduce the exact deterministic ticket formula in proof_action_route_epoch.py."""
    epoch = _text(route_epoch_id, "route_epoch_id")
    attempt = _text(attempt_id, "attempt_id")
    digest = _sha256(request_digest, "request_digest")
    return "urn:sha256:" + _digest({
        "epoch_id": epoch,
        "attempt_id": attempt,
        "request_digest": digest,
    })


def validate_execution_authorization_event(
    event_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the self-digest and ticket binding of one route-ledger event.

    This checks the event hash and its internal consistency. The caller must
    separately validate the containing route-ledger chain and authority trust.
    """
    event = _copy_mapping(event_document, "execution_authorization_event")
    required = {
        "sequence", "event_type", "epoch_id", "epoch_number", "route",
        "route_digest", "details", "previous_event_digest", "event_digest",
    }
    if set(event) != required:
        raise CompletionReceiptError("execution authorization event fields are invalid")
    if event["event_type"] != "execution_authorized":
        raise CompletionReceiptError("route event is not execution_authorized")
    _positive_int(event["sequence"], "event.sequence")
    _positive_int(event["epoch_number"], "event.epoch_number")
    _text(event["epoch_id"], "event.epoch_id")
    if not isinstance(event["route"], Mapping):
        raise CompletionReceiptError("event.route must be an object")
    if _sha256(event["route_digest"], "event.route_digest") != _digest(event["route"]):
        raise CompletionReceiptError("execution authorization route digest mismatch")
    _sha256(event["previous_event_digest"], "event.previous_event_digest")

    details = event["details"]
    if not isinstance(details, Mapping) or set(details) != {
        "owner_id", "owner_generation", "attempt_id", "request_digest",
        "request_sequence", "admission_event_digest", "execution_id", "runner_id",
    }:
        raise CompletionReceiptError("execution authorization details are invalid")
    _text(details["owner_id"], "event.details.owner_id")
    _positive_int(details["owner_generation"], "event.details.owner_generation")
    attempt_id = _text(details["attempt_id"], "event.details.attempt_id")
    request_digest = _sha256(details["request_digest"], "event.details.request_digest")
    _positive_int(details["request_sequence"], "event.details.request_sequence")
    _sha256(details["admission_event_digest"], "event.details.admission_event_digest")
    execution_id = _text(details["execution_id"], "event.details.execution_id")
    runner_id = _text(details["runner_id"], "event.details.runner_id")

    expected_execution_id = derive_execution_id(
        event["epoch_id"], attempt_id, request_digest
    )
    if execution_id != expected_execution_id:
        raise CompletionReceiptError("execution ID does not match the route ticket formula")

    core = {key: value for key, value in event.items() if key != "event_digest"}
    event_digest = _sha256(event["event_digest"], "event.event_digest")
    if event_digest != _digest(core):
        raise CompletionReceiptError("execution authorization event digest mismatch")
    return event


def validate_request_document(request_document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the current portable proof-action request envelope digest."""
    request = _copy_mapping(request_document, "proof-action request")
    if request.get("format") != REQUEST_FORMAT:
        raise CompletionReceiptError("unsupported proof-action request format")
    _text(request.get("attempt_id"), "request.attempt_id")
    request_digest = _sha256(request.get("request_digest"), "request.request_digest")
    core = {key: value for key, value in request.items() if key != "request_digest"}
    if request_digest != _digest(core):
        raise CompletionReceiptError("proof-action request digest mismatch")
    return request


def validate_result_document(
    result_document: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the existing result envelope and its exact request correlation."""
    result = _copy_mapping(result_document, "proof-action result")
    if set(result) != {
        "format", "attempt_id", "request_digest", "return_evidence",
        "proof_trace", "result_digest",
    } or result.get("format") != RESULT_FORMAT:
        raise CompletionReceiptError("proof-action result fields or format are invalid")
    _text(result["attempt_id"], "result.attempt_id")
    result_request_digest = _sha256(result["request_digest"], "result.request_digest")
    if result["attempt_id"] != request["attempt_id"]:
        raise CompletionReceiptError("result attempt ID does not match the request")
    if result_request_digest != request["request_digest"]:
        raise CompletionReceiptError("result request digest does not match the request")

    evidence = result["return_evidence"]
    if not isinstance(evidence, Mapping) or set(evidence) != {
        "evidence_ref", "encounter_id", "payload_digest", "canonicalization",
    }:
        raise CompletionReceiptError("result return_evidence fields are invalid")
    _text(evidence["evidence_ref"], "result.return_evidence.evidence_ref")
    _text(evidence["encounter_id"], "result.return_evidence.encounter_id")
    _sha256(evidence["payload_digest"], "result.return_evidence.payload_digest")
    _text(evidence["canonicalization"], "result.return_evidence.canonicalization")
    if not isinstance(result["proof_trace"], Mapping):
        raise CompletionReceiptError("result.proof_trace must be an object")

    core = {key: value for key, value in result.items() if key != "result_digest"}
    if _sha256(result["result_digest"], "result.result_digest") != _digest(core):
        raise CompletionReceiptError("proof-action result digest mismatch")
    return result


def runner_key_id(public_key: Ed25519PublicKey) -> str:
    if not isinstance(public_key, Ed25519PublicKey):
        raise CompletionReceiptError("public_key must be an Ed25519PublicKey")
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _receipt_core(
    authorization_event: Mapping[str, Any],
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    public_key: Ed25519PublicKey,
) -> dict[str, Any]:
    event = validate_execution_authorization_event(authorization_event)
    validated_request = validate_request_document(request)
    validated_result = validate_result_document(result, request=validated_request)
    details = event["details"]

    if details["attempt_id"] != validated_request["attempt_id"]:
        raise CompletionReceiptError("route authorization attempt does not match the request")
    if details["request_digest"] != validated_request["request_digest"]:
        raise CompletionReceiptError("route authorization request digest does not match the request")
    if details["execution_id"] != derive_execution_id(
        event["epoch_id"], validated_request["attempt_id"], validated_request["request_digest"]
    ):
        raise CompletionReceiptError("route authorization execution ticket is inconsistent")

    return {
        "format": RECEIPT_FORMAT,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "authorization_event_digest": event["event_digest"],
        "route_epoch_id": event["epoch_id"],
        "execution_id": details["execution_id"],
        "attempt_id": validated_request["attempt_id"],
        "request_digest": validated_request["request_digest"],
        "runner_id": details["runner_id"],
        "runner_key_id": runner_key_id(public_key),
        "completion_status": "result_produced",
        "result_format": validated_result["format"],
        "result_digest": validated_result["result_digest"],
        "return_evidence_digest": _digest(validated_result["return_evidence"]),
        "proof_trace_digest": _digest(validated_result["proof_trace"]),
    }


@dataclass(frozen=True)
class VerifiedRunnerCompletion:
    """A signature-verified runner claim bound to an authority event and result."""

    route_epoch_id: str
    execution_id: str
    attempt_id: str
    request_digest: str
    runner_id: str
    runner_key_id: str
    authorization_event_digest: str
    result_digest: str
    return_evidence_digest: str
    proof_trace_digest: str
    receipt_digest: str


def create_completion_receipt(
    authorization_event: Mapping[str, Any],
    request_document: Mapping[str, Any],
    result_document: Mapping[str, Any],
    *,
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    """Sign an exact correlated result after its runner-side durable commit."""
    if not isinstance(private_key, Ed25519PrivateKey):
        raise CompletionReceiptError("private_key must be an Ed25519PrivateKey")
    public_key = private_key.public_key()
    core = _receipt_core(
        authorization_event, request_document, result_document,
        public_key=public_key,
    )
    receipt_digest = _digest(core)
    signed_payload = {**core, "receipt_digest": receipt_digest}
    signature = private_key.sign(_canonical(signed_payload).encode("utf-8")).hex()
    return {**signed_payload, "signature": signature}


def verify_completion_receipt(
    receipt_document: Mapping[str, Any],
    authorization_event: Mapping[str, Any],
    request_document: Mapping[str, Any],
    result_document: Mapping[str, Any],
    *,
    trusted_runner_id: str,
    trusted_public_key: Ed25519PublicKey,
) -> VerifiedRunnerCompletion:
    """Verify signature, runner-key binding, authority ticket and exact result.

    The trusted runner identity/key mapping is an external trust input. The
    caller must also validate the entire route ledger before trusting its event.
    """
    if not isinstance(trusted_public_key, Ed25519PublicKey):
        raise CompletionReceiptError("trusted_public_key must be an Ed25519PublicKey")
    runner_id = _text(trusted_runner_id, "trusted_runner_id")
    expected_core = _receipt_core(
        authorization_event, request_document, result_document,
        public_key=trusted_public_key,
    )
    if expected_core["runner_id"] != runner_id:
        raise CompletionReceiptError("route authorization names a different runner identity")

    receipt = _copy_mapping(receipt_document, "completion receipt")
    required = set(expected_core) | {"receipt_digest", "signature"}
    if set(receipt) != required:
        raise CompletionReceiptError("completion receipt fields are invalid")
    for key, expected_value in expected_core.items():
        if receipt.get(key) != expected_value:
            raise CompletionReceiptError(f"completion receipt {key} mismatch")

    receipt_digest = _sha256(receipt["receipt_digest"], "receipt.receipt_digest")
    if receipt_digest != _digest(expected_core):
        raise CompletionReceiptError("completion receipt digest mismatch")
    signature = receipt["signature"]
    if (
        not isinstance(signature, str)
        or len(signature) != 128
        or any(character not in "0123456789abcdef" for character in signature)
    ):
        raise CompletionReceiptError("receipt signature must be 64-byte lowercase hex")

    signed_payload = {**expected_core, "receipt_digest": receipt_digest}
    try:
        trusted_public_key.verify(
            bytes.fromhex(signature),
            _canonical(signed_payload).encode("utf-8"),
        )
    except (InvalidSignature, ValueError) as exc:
        raise CompletionReceiptError("completion receipt signature verification failed") from exc

    return VerifiedRunnerCompletion(
        route_epoch_id=expected_core["route_epoch_id"],
        execution_id=expected_core["execution_id"],
        attempt_id=expected_core["attempt_id"],
        request_digest=expected_core["request_digest"],
        runner_id=expected_core["runner_id"],
        runner_key_id=expected_core["runner_key_id"],
        authorization_event_digest=expected_core["authorization_event_digest"],
        result_digest=expected_core["result_digest"],
        return_evidence_digest=expected_core["return_evidence_digest"],
        proof_trace_digest=expected_core["proof_trace_digest"],
        receipt_digest=receipt_digest,
    )


__all__ = [
    "RECEIPT_FORMAT",
    "CompletionReceiptError",
    "VerifiedRunnerCompletion",
    "derive_execution_id",
    "validate_execution_authorization_event",
    "validate_request_document",
    "validate_result_document",
    "runner_key_id",
    "create_completion_receipt",
    "verify_completion_receipt",
]
