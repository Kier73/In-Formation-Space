#!/usr/bin/env python3
"""Produce the three-host proof-runner reconstruction experiment artifacts.

Authority and runner private keys are process-local and never written to the
artifact directories. Public-key documents are attested separately by the
GitHub-hosted job that creates them. The independent Go verifier receives those
public keys only after its host verifies their GitHub artifact attestations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "proof-runner-completion-receipts"))

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from formats.canonical_metadata_v1 import canonical_bytes, canonical_digest, decode_canonical_document
from completion_receipts import (
    CompletionReceiptError,
    create_completion_receipt,
    validate_execution_authorization_event,
    validate_request_document,
)

REPOSITORY = "Kier73/In-Formation-Space"
WORKFLOW_PATH = ".github/workflows/proof-runner-three-host-reconstruction.yml"
SIGNER_WORKFLOW = f"{REPOSITORY}/{WORKFLOW_PATH}"
SOURCE_REF = "refs/heads/main"
LEDGER_FORMAT = "in-formation.proof-action-route-ledger/0.1"
AUTHORITY_ATTESTATION_FORMAT = "in-formation.proof-action-route-ledger-attestation/0.2"
KEY_FORMAT = "in-formation.proof-runner-participant-key/0.1"
BUNDLE_FORMAT = "in-formation.proof-runner-reconstruction-input/0.1"
PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/proof-runner-participant-key/v1"
KEY_PREDICATE_SCHEMA = "in-formation.proof-runner-participant-key-predicate/0.1"
GH_MIN_VERSION = (2, 103, 3)


class EvidenceError(ValueError):
    """Invalid participant artifact, authority statement, or host attestation."""


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(dict(value)) + b"\n")


def _read(path: Path) -> dict[str, Any]:
    try:
        return decode_canonical_document(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"{path} is not a canonical metadata artifact: {exc}") from exc


def _digest(value: Any) -> str:
    return canonical_digest(value)


def _raw_public_key(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _key_id(key: Ed25519PublicKey) -> str:
    return "sha256:" + hashlib.sha256(_raw_public_key(key)).hexdigest()


def _host_identity(role: str, *, fixture: bool = False) -> dict[str, str]:
    if fixture:
        runner_name = "fixture-" + role
        run_id = "fixture-run-0001"
        attempt = "1"
        run_number = "1"
        workflow_ref = f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main"
        workflow_sha = "a" * 40
        git_sha = "b" * 40
        actor = "fixture-contributor"
        return {
            "repository": REPOSITORY,
            "run_id": run_id,
            "run_attempt": attempt,
            "run_number": run_number,
            "workflow_ref": workflow_ref,
            "workflow_sha": workflow_sha,
            "git_ref": SOURCE_REF,
            "git_sha": git_sha,
            "job": role,
            "runner_name": runner_name,
            "runner_os": "Linux",
            "runner_arch": "X64",
            "runner_environment": "github-hosted",
            "actor_id": f"{REPOSITORY}#fixture.{role}.{runner_name}.{actor}",
        }

    names = {
        "repository": "GITHUB_REPOSITORY",
        "run_id": "GITHUB_RUN_ID",
        "run_attempt": "GITHUB_RUN_ATTEMPT",
        "run_number": "GITHUB_RUN_NUMBER",
        "workflow_ref": "GITHUB_WORKFLOW_REF",
        "workflow_sha": "GITHUB_WORKFLOW_SHA",
        "git_ref": "GITHUB_REF",
        "git_sha": "GITHUB_SHA",
        "job": "GITHUB_JOB",
        "runner_name": "RUNNER_NAME",
        "runner_os": "RUNNER_OS",
        "runner_arch": "RUNNER_ARCH",
        "runner_environment": "RUNNER_ENVIRONMENT",
    }
    result = {field: os.environ.get(variable, "").strip() for field, variable in names.items()}
    for field, value in result.items():
        if not value:
            raise EvidenceError(f"required GitHub host identity field {field} is missing")
    if result["repository"] != REPOSITORY:
        raise EvidenceError("host is running in an unexpected repository")
    if result["job"] != role:
        raise EvidenceError(f"expected job {role}, observed {result['job']}")
    if result["git_ref"] != SOURCE_REF:
        raise EvidenceError("live host evidence may only be produced from protected main")
    if result["runner_environment"] != "github-hosted":
        raise EvidenceError("participant jobs must use GitHub-hosted runners")
    result["actor_id"] = (
        f"{result['repository']}#run-{result['run_id']}.attempt-{result['run_attempt']}."
        f"{role}.{result['runner_name']}"
    )
    return result


def _participant_key_document(
    key: Ed25519PrivateKey,
    participant_id: str,
    role: str,
    *,
    fixture: bool = False,
) -> dict[str, Any]:
    public = key.public_key()
    return {
        "format": KEY_FORMAT,
        "participant_id": participant_id,
        "role": role,
        "key_algorithm": "Ed25519",
        "key_id": _key_id(public),
        "public_key_hex": _raw_public_key(public).hex(),
        "host": _host_identity(role, fixture=fixture),
    }


def _make_event(
    *,
    sequence: int,
    previous_event_digest: str,
    event_type: str,
    epoch_id: str,
    epoch_number: int,
    route: Mapping[str, Any],
    details: Mapping[str, Any],
) -> dict[str, Any]:
    core = {
        "sequence": sequence,
        "event_type": event_type,
        "epoch_id": epoch_id,
        "epoch_number": epoch_number,
        "route": dict(route),
        "route_digest": _digest(route),
        "details": dict(details),
        "previous_event_digest": previous_event_digest,
    }
    return {**core, "event_digest": _digest(core)}


def _derive_execution_id(epoch_id: str, attempt_id: str, request_digest: str) -> str:
    return "urn:sha256:" + _digest({
        "epoch_id": epoch_id,
        "attempt_id": attempt_id,
        "request_digest": request_digest,
    })


def _validate_store_revision_history(
    ledger: Mapping[str, Any],
    history: list[Mapping[str, Any]],
) -> None:
    """Recompute each SQLite ledger prefix from its append-only revision delta."""
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not isinstance(history, list) or not history:
        raise EvidenceError("SQLite authority history and route ledger must be non-empty")
    event_offset = 0
    previous_ledger_digest: str | None = None
    for expected_revision, row in enumerate(history, 1):
        required = {
            "revision", "previous_ledger_digest", "ledger_digest", "actor_id",
            "appended_event_digests", "committed_utc",
        }
        if not isinstance(row, Mapping) or set(row) != required:
            raise EvidenceError(f"SQLite revision {expected_revision} fields are invalid")
        if type(row["revision"]) is not int or row["revision"] != expected_revision:
            raise EvidenceError("SQLite revision sequence is not contiguous")
        if row["previous_ledger_digest"] != previous_ledger_digest:
            raise EvidenceError("SQLite revision predecessor digest mismatch")
        actor = row["actor_id"]
        if not isinstance(actor, str) or not actor.strip():
            raise EvidenceError("SQLite revision actor ID is invalid")
        if not isinstance(row["committed_utc"], str) or not row["committed_utc"]:
            raise EvidenceError("SQLite revision commit marker is invalid")
        appended = row["appended_event_digests"]
        if not isinstance(appended, list) or not appended:
            raise EvidenceError("SQLite revision must append event digests")
        end_offset = event_offset + len(appended)
        if end_offset > len(entries):
            raise EvidenceError("SQLite revision appends beyond the route ledger")
        batch = entries[event_offset:end_offset]
        if [event.get("event_digest") for event in batch] != appended:
            raise EvidenceError("SQLite revision append index differs from route ledger events")
        for event in batch:
            details = event.get("details", {})
            event_actor = details.get("owner_id") if isinstance(details, Mapping) else None
            if actor != event_actor:
                raise EvidenceError("SQLite revision actor differs from appended event owner")
        prefix = {"format": ledger["format"], "entries": entries[:end_offset]}
        computed = _digest(prefix)
        if row["ledger_digest"] != computed:
            raise EvidenceError(
                f"SQLite revision {expected_revision} intermediate ledger digest mismatch"
            )
        previous_ledger_digest = computed
        event_offset = end_offset
    if event_offset != len(entries) or previous_ledger_digest != ledger.get("ledger_digest"):
        raise EvidenceError("SQLite revision history does not reproduce the complete route ledger")


def _validate_authority_process_evidence(
    ledger: Mapping[str, Any],
    process_evidence: Mapping[str, Any],
    stale_attempt: Mapping[str, Any],
    history: list[Mapping[str, Any]],
    request: Mapping[str, Any],
) -> None:
    required = {
        "format", "authority_store_type", "authority_process_count", "phases",
        "final_store_revision", "final_ledger_digest", "stale_owner_attempt_rejected",
    }
    if not isinstance(process_evidence, Mapping) or set(process_evidence) != required:
        raise EvidenceError("authority process evidence fields are invalid")
    if process_evidence["format"] != "in-formation.proof-runner-authority-process-evidence/0.1":
        raise EvidenceError("authority process evidence format is unsupported")
    if process_evidence["authority_store_type"] != "sqlite-local-file":
        raise EvidenceError("authority store type is not the declared SQLite local-file adapter")
    if process_evidence["authority_process_count"] != 3 or process_evidence["final_store_revision"] != len(history):
        raise EvidenceError("authority process count or final revision is inconsistent")
    if process_evidence["final_ledger_digest"] != ledger.get("ledger_digest"):
        raise EvidenceError("authority process evidence names a different final ledger")
    if process_evidence["stale_owner_attempt_rejected"] is not True:
        raise EvidenceError("authority process evidence does not record stale-owner rejection")

    phases = process_evidence["phases"]
    expected_phases = [
        "initial_open",
        "restart_claim_admit_authorize",
        "stale_generation_replay",
    ]
    if not isinstance(phases, list) or len(phases) != 3:
        raise EvidenceError("authority process evidence must contain three phases")
    if [item.get("phase") for item in phases] != expected_phases:
        raise EvidenceError("authority process phases are missing or reordered")
    instance_ids: set[str] = set()
    for phase in phases:
        if not isinstance(phase, Mapping):
            raise EvidenceError("authority process phase must be an object")
        process_id = phase.get("process_id")
        instance_id = phase.get("process_instance_id")
        if type(process_id) is not int or process_id <= 0:
            raise EvidenceError("authority phase process ID is invalid")
        if not isinstance(instance_id, str) or not instance_id or instance_id in instance_ids:
            raise EvidenceError("authority process instances are not distinct")
        instance_ids.add(instance_id)
        if type(phase.get("observed_store_revision")) is not int:
            raise EvidenceError("authority phase store revision is invalid")
        if not isinstance(phase.get("event_digests"), list):
            raise EvidenceError("authority phase event digest list is invalid")
    entries = ledger["entries"]
    expected_digests = [
        [entries[0]["event_digest"]],
        [entries[1]["event_digest"], entries[2]["event_digest"], entries[3]["event_digest"]],
        [],
    ]
    if [item["event_digests"] for item in phases] != expected_digests:
        raise EvidenceError("authority process phases do not bind the expected ledger commits")
    if [item["observed_store_revision"] for item in phases] != [1, 4, 4]:
        raise EvidenceError("authority process phases do not match the SQLite revision history")
    if [item["decision"] for item in phases] != [
        "opened", "replacement_owner_authorized", "rejected"
    ]:
        raise EvidenceError("authority process phase decisions are invalid")

    stale_fields = {
        "phase", "process_id", "process_instance_id", "event_digests",
        "observed_store_revision", "decision", "stale_attempt_id", "accepted",
        "observed_owner_id", "observed_owner_generation",
    }
    if not isinstance(stale_attempt, Mapping) or set(stale_attempt) != stale_fields:
        raise EvidenceError("stale-owner attempt record fields are invalid")
    if stale_attempt != phases[2]:
        raise EvidenceError("stale-owner attempt does not match the third process record")
    if (
        stale_attempt["accepted"] is not False
        or stale_attempt["observed_owner_generation"] != 2
        or stale_attempt["observed_owner_id"] != entries[1]["details"]["owner_id"]
        or stale_attempt["stale_attempt_id"] != f"{request['attempt_id']}:stale-replay"
    ):
        raise EvidenceError("stale owner-generation attempt was not rejected as expected")


def _database_bytes(path_or_bytes: Path | bytes) -> bytes:
    if isinstance(path_or_bytes, bytes):
        return path_or_bytes
    return path_or_bytes.read_bytes()


def _authority_attestation_core(
    authority_key: Ed25519PrivateKey,
    *,
    authority_id: str,
    runner_id: str,
    ledger: Mapping[str, Any],
    request: Mapping[str, Any],
    history: list[Mapping[str, Any]],
    process_evidence: Mapping[str, Any],
    stale_attempt: Mapping[str, Any],
    database_path_or_bytes: Path | bytes,
) -> dict[str, Any]:
    _validate_store_revision_history(ledger, history)
    _validate_authority_process_evidence(
        ledger, process_evidence, stale_attempt, history, request
    )
    event = ledger["entries"][-1]
    details = event["details"]
    database_sha256 = hashlib.sha256(_database_bytes(database_path_or_bytes)).hexdigest()
    return {
        "format": AUTHORITY_ATTESTATION_FORMAT,
        "signature_algorithm": "Ed25519",
        "authority_id": authority_id,
        "authority_key_id": _key_id(authority_key.public_key()),
        "ledger_digest": ledger["ledger_digest"],
        "ledger_sequence": len(ledger["entries"]),
        "authorization_event_digest": event["event_digest"],
        "execution_id": details["execution_id"],
        "attempt_id": request["attempt_id"],
        "request_digest": request["request_digest"],
        "runner_id": runner_id,
        "store_type": "sqlite-local-file",
        "store_revision_count": len(history),
        "store_history_digest": _digest(history),
        "store_database_sha256": database_sha256,
        "process_evidence_digest": _digest(process_evidence),
        "process_phase_count": len(process_evidence["phases"]),
        "stale_owner_rejected": stale_attempt["accepted"] is False,
    }


def _sign_authority_attestation(
    authority_key: Ed25519PrivateKey,
    core: Mapping[str, Any],
) -> dict[str, Any]:
    attestation_digest = _digest(dict(core))
    signed_payload = {**dict(core), "attestation_digest": attestation_digest}
    return {
        **signed_payload,
        "signature": authority_key.sign(canonical_bytes(signed_payload)).hex(),
    }


def _build_authority_material(
    authority_key: Ed25519PrivateKey,
    *,
    fixture: bool,
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any],
    list[dict[str, Any]], bytes, dict[str, Any], dict[str, Any],
]:
    run_id = "fixture" if fixture else "live"
    attempt_id = "proof-run:fixture:000001" if fixture else "proof-run:live:000001"
    epoch_id = "proof-route-epoch-fixture" if fixture else "proof-route-epoch-live"
    runner_id = "lean-worker-fixture" if fixture else "lean-worker-live"
    initial_owner = "route-owner-fixture-process-1" if fixture else "route-owner-live-process-1"
    replacement_owner = "route-owner-fixture-process-2" if fixture else "route-owner-live-process-2"

    request_core = {
        "format": "in-formation.proof-action-request/0.1",
        "attempt_id": attempt_id,
        "query_label": "establish identity",
        "plan_digest": "1" * 64,
        "proof_ground_digest": "2" * 64,
        "candidate_transition": {
            "transition_id": "transition-identity",
            "source_id": "obligation-root",
            "tactic": "rfl",
            "proposed_subgoal_ids": [],
        },
    }
    request = {**request_core, "request_digest": _digest(request_core)}
    route = {
        "host_id": "proof-authority-host",
        "worker_id": "proof-runner-host",
        "request_channel": f"proof-request-{run_id}",
        "result_channel": f"proof-result-{run_id}",
        "policy": {"lease_ticks": 3, "max_attempts": 4, "window_size": 8},
    }
    opened = _make_event(
        sequence=1,
        previous_event_digest="0" * 64,
        event_type="opened",
        epoch_id=epoch_id,
        epoch_number=1,
        route=route,
        details={
            "predecessor_close_digest": None,
            "owner_generation": 1,
            "owner_id": initial_owner,
        },
    )
    claimed = _make_event(
        sequence=2,
        previous_event_digest=opened["event_digest"],
        event_type="claimed",
        epoch_id=epoch_id,
        epoch_number=1,
        route=route,
        details={
            "owner_generation": 2,
            "previous_owner_id": initial_owner,
            "owner_id": replacement_owner,
        },
    )
    admitted = _make_event(
        sequence=3,
        previous_event_digest=claimed["event_digest"],
        event_type="admitted",
        epoch_id=epoch_id,
        epoch_number=1,
        route=route,
        details={
            "owner_id": replacement_owner,
            "owner_generation": 2,
            "attempt_id": attempt_id,
            "request_digest": request["request_digest"],
            "request_sequence": 1,
        },
    )
    execution_id = _derive_execution_id(epoch_id, attempt_id, request["request_digest"])
    authorized = _make_event(
        sequence=4,
        previous_event_digest=admitted["event_digest"],
        event_type="execution_authorized",
        epoch_id=epoch_id,
        epoch_number=1,
        route=route,
        details={
            "owner_id": replacement_owner,
            "owner_generation": 2,
            "attempt_id": attempt_id,
            "request_digest": request["request_digest"],
            "request_sequence": 1,
            "admission_event_digest": admitted["event_digest"],
            "execution_id": execution_id,
            "runner_id": runner_id,
        },
    )
    entries = [opened, claimed, admitted, authorized]
    ledger_core = {"format": LEDGER_FORMAT, "entries": entries}
    ledger = {**ledger_core, "ledger_digest": _digest(ledger_core)}

    history = []
    previous_digest = None
    for index, event in enumerate(entries, 1):
        prefix = {"format": LEDGER_FORMAT, "entries": entries[:index]}
        current_digest = _digest(prefix)
        history.append({
            "revision": index,
            "previous_ledger_digest": previous_digest,
            "ledger_digest": current_digest,
            "actor_id": event["details"]["owner_id"],
            "appended_event_digests": [event["event_digest"]],
            "committed_utc": "2026-11-13T00:00:00.000Z",
        })
        previous_digest = current_digest

    process_evidence = {
        "format": "in-formation.proof-runner-authority-process-evidence/0.1",
        "authority_store_type": "sqlite-local-file",
        "authority_process_count": 3,
        "phases": [
            {
                "phase": "initial_open",
                "process_id": 10001,
                "process_instance_id": "fixture-process-instance-1",
                "event_digests": [opened["event_digest"]],
                "observed_store_revision": 1,
                "decision": "opened",
            },
            {
                "phase": "restart_claim_admit_authorize",
                "process_id": 10002,
                "process_instance_id": "fixture-process-instance-2",
                "event_digests": [
                    claimed["event_digest"],
                    admitted["event_digest"],
                    authorized["event_digest"],
                ],
                "observed_store_revision": 4,
                "decision": "replacement_owner_authorized",
            },
            {
                "phase": "stale_generation_replay",
                "process_id": 10003,
                "process_instance_id": "fixture-process-instance-3",
                "event_digests": [],
                "observed_store_revision": 4,
                "decision": "rejected",
                "stale_attempt_id": f"{attempt_id}:stale-replay",
                "accepted": False,
                "observed_owner_id": replacement_owner,
                "observed_owner_generation": 2,
            },
        ],
        "final_store_revision": 4,
        "final_ledger_digest": ledger["ledger_digest"],
        "stale_owner_attempt_rejected": True,
    }
    stale_attempt = process_evidence["phases"][2]
    database_bytes = b"fixture-only: deterministic stand-in; not a live SQLite database\n"
    authority_id = "route-authority-fixture" if fixture else f"route-authority-{run_id}"
    core = _authority_attestation_core(
        authority_key,
        authority_id=authority_id,
        runner_id=runner_id,
        ledger=ledger,
        request=request,
        history=history,
        process_evidence=process_evidence,
        stale_attempt=stale_attempt,
        database_path_or_bytes=database_bytes,
    )
    authority_attestation = _sign_authority_attestation(authority_key, core)
    key_doc = _participant_key_document(
        authority_key,
        authority_id,
        "authority_host",
        fixture=fixture,
    )
    return (
        ledger, request, authority_attestation, key_doc,
        history, database_bytes, process_evidence, stale_attempt,
    )


def _verify_authority_material(
    ledger: Mapping[str, Any],
    request: Mapping[str, Any],
    attestation: Mapping[str, Any],
    key_doc: Mapping[str, Any],
    *,
    history: list[Mapping[str, Any]],
    process_evidence: Mapping[str, Any],
    stale_attempt: Mapping[str, Any],
    database_path: Path,
) -> dict[str, Any]:
    if key_doc.get("format") != KEY_FORMAT or key_doc.get("role") != "authority_host":
        raise EvidenceError("authority public-key document has the wrong format or role")
    if key_doc.get("key_algorithm") != "Ed25519":
        raise EvidenceError("authority public-key algorithm is unsupported")
    try:
        public_raw = bytes.fromhex(str(key_doc.get("public_key_hex", "")))
        public_key = Ed25519PublicKey.from_public_bytes(public_raw)
    except (ValueError, TypeError) as exc:
        raise EvidenceError("authority public key is malformed") from exc
    if _key_id(public_key) != key_doc.get("key_id"):
        raise EvidenceError("authority key fingerprint mismatch")

    expected_fields = {
        "format", "signature_algorithm", "authority_id", "authority_key_id",
        "ledger_digest", "ledger_sequence", "authorization_event_digest",
        "execution_id", "attempt_id", "request_digest", "runner_id",
        "store_type", "store_revision_count", "store_history_digest",
        "store_database_sha256", "process_evidence_digest",
        "process_phase_count", "stale_owner_rejected",
        "attestation_digest", "signature",
    }
    if set(attestation) != expected_fields:
        raise EvidenceError("authority ledger attestation fields are invalid")
    if attestation["format"] != AUTHORITY_ATTESTATION_FORMAT or attestation["signature_algorithm"] != "Ed25519":
        raise EvidenceError("authority ledger attestation format is unsupported")
    core = {key: value for key, value in attestation.items() if key not in {"attestation_digest", "signature"}}
    if attestation["attestation_digest"] != _digest(core):
        raise EvidenceError("authority ledger attestation digest mismatch")
    signed_payload = {**core, "attestation_digest": attestation["attestation_digest"]}
    signature = attestation["signature"]
    if not isinstance(signature, str) or len(signature) != 128:
        raise EvidenceError("authority attestation signature must be 64-byte hex")
    try:
        public_key.verify(bytes.fromhex(signature), canonical_bytes(signed_payload))
    except (InvalidSignature, ValueError) as exc:
        raise EvidenceError("authority ledger attestation signature verification failed") from exc

    ledger_core = {key: value for key, value in ledger.items() if key != "ledger_digest"}
    if ledger.get("format") != LEDGER_FORMAT or ledger.get("ledger_digest") != _digest(ledger_core):
        raise EvidenceError("route ledger digest mismatch")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or len(entries) != 4:
        raise EvidenceError("route ledger must contain the four expected authority events")
    try:
        _validate_store_revision_history(ledger, list(history))
        _validate_authority_process_evidence(
            ledger, process_evidence, stale_attempt, list(history), request
        )
        validated_request = validate_request_document(request)
        validated_event = validate_execution_authorization_event(entries[-1])
    except (CompletionReceiptError, TypeError, ValueError, KeyError) as exc:
        raise EvidenceError(f"authority evidence failed semantic validation: {exc}") from exc
    details = validated_event["details"]
    database_sha256 = hashlib.sha256(database_path.read_bytes()).hexdigest()
    if (
        attestation["authority_id"] != key_doc["participant_id"]
        or attestation["authority_key_id"] != key_doc["key_id"]
        or attestation["ledger_digest"] != ledger["ledger_digest"]
        or attestation["ledger_sequence"] != len(entries)
        or attestation["authorization_event_digest"] != validated_event["event_digest"]
        or attestation["execution_id"] != details["execution_id"]
        or attestation["attempt_id"] != validated_request["attempt_id"]
        or attestation["request_digest"] != validated_request["request_digest"]
        or attestation["runner_id"] != details["runner_id"]
        or details["attempt_id"] != validated_request["attempt_id"]
        or details["request_digest"] != validated_request["request_digest"]
        or attestation["store_type"] != "sqlite-local-file"
        or attestation["store_revision_count"] != len(history)
        or attestation["store_history_digest"] != _digest(list(history))
        or attestation["store_database_sha256"] != database_sha256
        or attestation["process_evidence_digest"] != _digest(process_evidence)
        or attestation["process_phase_count"] != 3
        or attestation["stale_owner_rejected"] is not True
    ):
        raise EvidenceError("authority attestation does not bind the ledger, SQLite audit, processes, and request")
    return dict(validated_event)


def _build_result(request: Mapping[str, Any]) -> dict[str, Any]:
    result_core = {
        "format": "in-formation.proof-action-result/0.1",
        "attempt_id": request["attempt_id"],
        "request_digest": request["request_digest"],
        "return_evidence": {
            "evidence_ref": "encounter://proof-return/fixture",
            "encounter_id": "proof-return-fixture",
            "payload_digest": "3" * 64,
            "canonicalization": "canonical-json-v1",
        },
        "proof_trace": {
            "format": "vgi.lean-proof-trace/0.1",
            "transitions": [
                {
                    "attempt_id": request["attempt_id"],
                    "transition_id": "transition-identity",
                    "status": "elaborated",
                }
            ],
        },
    }
    return {**result_core, "result_digest": _digest(result_core)}


def _build_runner_material(
    runner_key: Ed25519PrivateKey,
    ledger: Mapping[str, Any],
    request: Mapping[str, Any],
    authority_attestation: Mapping[str, Any],
    authority_key_doc: Mapping[str, Any],
    *,
    history: list[Mapping[str, Any]],
    process_evidence: Mapping[str, Any],
    stale_attempt: Mapping[str, Any],
    database_path: Path,
    fixture: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _check_key_doc(authority_key_doc, "authority_host", "authority_host")
    event = _verify_authority_material(
        ledger,
        request,
        authority_attestation,
        authority_key_doc,
        history=history,
        process_evidence=process_evidence,
        stale_attempt=stale_attempt,
        database_path=database_path,
    )
    runner_host_identity = _host_identity("runner_host", fixture=fixture)
    authority_host_identity = authority_key_doc["host"]
    for field in ("repository", "run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_ref", "git_sha"):
        if authority_host_identity[field] != runner_host_identity[field]:
            raise EvidenceError(f"authority and runner host differ in {field}")
    result = _build_result(request)
    receipt = create_completion_receipt(
        event,
        request,
        result,
        private_key=runner_key,
    )
    run_id = runner_host_identity["run_id"]
    runner_id = "lean-worker-fixture" if fixture else f"lean-worker-{run_id}"
    if receipt["runner_id"] != runner_id:
        raise EvidenceError("runner public identity differs from route authorization")
    key_doc = _participant_key_document(
        runner_key,
        runner_id,
        "runner_host",
        fixture=fixture,
    )
    return result, receipt, key_doc


def _check_key_doc(document: Mapping[str, Any], expected_role: str, expected_job: str) -> None:
    if document.get("format") != KEY_FORMAT or document.get("role") != expected_role:
        raise EvidenceError("participant key document format or role is invalid")
    host = document.get("host")
    if not isinstance(host, Mapping):
        raise EvidenceError("participant key document is missing its host identity")
    required = {
        "repository", "run_id", "run_attempt", "run_number", "workflow_ref",
        "workflow_sha", "git_ref", "git_sha", "job", "runner_name",
        "runner_os", "runner_arch", "runner_environment", "actor_id",
    }
    if set(host) != required:
        raise EvidenceError("participant host identity fields are invalid")
    if (
        host["repository"] != REPOSITORY
        or host["job"] != expected_job
        or host["git_ref"] != SOURCE_REF
        or host["workflow_ref"] != f"{REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}"
        or host["runner_environment"] != "github-hosted"
        or not isinstance(host["runner_name"], str)
        or not host["runner_name"]
    ):
        raise EvidenceError("participant host identity does not match the protected hosted job")
    if document.get("key_algorithm") != "Ed25519":
        raise EvidenceError("participant key algorithm is unsupported")
    try:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(document["public_key_hex"])))
    except (ValueError, TypeError, KeyError) as exc:
        raise EvidenceError("participant public key is malformed") from exc
    if _key_id(public) != document.get("key_id"):
        raise EvidenceError("participant public-key fingerprint mismatch")


def _participant_key_predicate(document: Mapping[str, Any], subject_sha256: str) -> dict[str, Any]:
    """Bind the participant role and host identity to these exact public-key bytes."""
    return {
        "schema": KEY_PREDICATE_SCHEMA,
        "subject_sha256": subject_sha256,
        "participant": {
            "participant_id": document["participant_id"],
            "role": document["role"],
            "key_algorithm": document["key_algorithm"],
            "key_id": document["key_id"],
            "host": dict(document["host"]),
        },
    }


def write_key_predicate(
    key_path: Path,
    output_path: Path,
    expected_role: str,
    expected_job: str,
) -> None:
    document = _read(key_path)
    _check_key_doc(document, expected_role, expected_job)
    subject_digest = hashlib.sha256(key_path.read_bytes()).hexdigest()
    _write(output_path, _participant_key_predicate(document, subject_digest))


def _gh_version() -> tuple[int, int, int]:
    completed = subprocess.run(["gh", "--version"], check=True, capture_output=True, text=True)
    import re
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", completed.stdout)
    if not match:
        raise EvidenceError("cannot parse GitHub CLI version")
    return tuple(int(item) for item in match.groups())


def verify_key_attestation(path: Path, expected_role: str, expected_job: str) -> dict[str, Any]:
    """Verify the key file's GitHub provenance before using it as a trust anchor."""
    document = _read(path)
    _check_key_doc(document, expected_role, expected_job)
    if _gh_version() < GH_MIN_VERSION:
        raise EvidenceError("GitHub CLI 2.103.3 or newer is required")
    command = [
        "gh", "attestation", "verify", str(path),
        "--repo", REPOSITORY,
        "--signer-workflow", SIGNER_WORKFLOW,
        "--source-ref", SOURCE_REF,
        "--predicate-type", PREDICATE_TYPE,
        "--deny-self-hosted-runners",
        "--format", "json",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        verification = json.loads(completed.stdout)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if exc.stderr else str(exc)
        raise EvidenceError(f"GitHub key-document attestation failed: {detail}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError("GitHub CLI returned invalid attestation JSON") from exc

    if not isinstance(verification, list):
        raise EvidenceError("GitHub CLI attestation output must be an array")
    target_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    matches = []
    for item in verification:
        if not isinstance(item, Mapping):
            continue
        result = item.get("verificationResult")
        if not isinstance(result, Mapping):
            continue
        statement = result.get("statement")
        if not isinstance(statement, Mapping):
            continue
        subjects = statement.get("subject", [])
        if isinstance(subjects, list) and any(
            isinstance(subject, Mapping)
            and isinstance(subject.get("digest"), Mapping)
            and subject["digest"].get("sha256") == target_digest
            for subject in subjects
        ):
            matches.append((statement, result))
    if not matches:
        raise EvidenceError("no verified GitHub attestation binds the exact public-key file bytes")
    statement, result = matches[0]
    expected_predicate = _participant_key_predicate(document, target_digest)
    if statement.get("predicateType") != PREDICATE_TYPE or statement.get("predicate") != expected_predicate:
        raise EvidenceError("verified GitHub attestation predicate does not bind the participant role and host identity")
    signature = result.get("signature")
    if not isinstance(signature, Mapping) or not isinstance(signature.get("certificate"), Mapping):
        raise EvidenceError("verified key attestation is missing its signing certificate")
    return {
        "verified": True,
        "role": expected_role,
        "job": expected_job,
        "subject_sha256": target_digest,
        "signer_workflow": SIGNER_WORKFLOW,
        "source_ref": SOURCE_REF,
        "self_hosted_runners_denied": True,
    }


def build_fixture(out_dir: Path) -> None:
    """Build deterministic test artifacts; the store bytes are not a live SQLite database."""
    authority_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32))
    runner_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("22" * 32))
    (
        ledger, request, attestation, authority_key_doc,
        history, database_bytes, process_evidence, stale_attempt,
    ) = _build_authority_material(authority_key, fixture=True)
    authority_dir = out_dir / "authority"
    runner_dir = out_dir / "runner"
    _write(authority_dir / "route-ledger.json", ledger)
    _write(authority_dir / "request.json", request)
    _write(authority_dir / "authority-attestation.json", attestation)
    _write(authority_dir / "store-history.json", {"entries": history})
    _write(authority_dir / "process-evidence.json", process_evidence)
    _write(authority_dir / "stale-owner-attempt.json", stale_attempt)
    database_path = authority_dir / "authority-store-fixture.bin"
    database_path.write_bytes(database_bytes)
    _write(
        out_dir / "authority" / "sqlite-authority-verification-fixture.json",
        {
            "verified": False,
            "store_type": "sqlite-local-file",
            "ledger_digest": ledger["ledger_digest"],
            "revision_count": len(history),
            "active_epoch_id": ledger["entries"][-1]["epoch_id"],
            "active_owner_id": ledger["entries"][1]["details"]["owner_id"],
            "active_owner_generation": 2,
            "history_digest": _digest(history),
        },
    )
    authority_key_path = authority_dir / "authority-public-key.json"
    _write(authority_key_path, authority_key_doc)
    write_key_predicate(
        authority_key_path,
        authority_dir / "authority-public-key.predicate.json",
        "authority_host",
        "authority_host",
    )
    result, receipt, runner_key_doc = _build_runner_material(
        runner_key,
        ledger,
        request,
        attestation,
        authority_key_doc,
        history=history,
        process_evidence=process_evidence,
        stale_attempt=stale_attempt,
        database_path=database_path,
        fixture=True,
    )
    _write(runner_dir / "result.json", result)
    _write(runner_dir / "completion-receipt.json", receipt)
    runner_key_path = runner_dir / "runner-public-key.json"
    _write(runner_key_path, runner_key_doc)
    write_key_predicate(
        runner_key_path,
        runner_dir / "runner-public-key.predicate.json",
        "runner_host",
        "runner_host",
    )
    verifier_host = {
        "format": "in-formation.proof-runner-verifier-host/0.1",
        "host": _host_identity("independent_verifier_host", fixture=True),
    }
    _write(out_dir / "verifier-host.json", verifier_host)


def produce_authority(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    from durable_authority import build_sqlite_authority_bundle

    host = _host_identity("authority_host", fixture=False)
    run_id = host["run_id"]
    runner_id = f"lean-worker-{run_id}"
    bundle = build_sqlite_authority_bundle(
        out_dir,
        run_id=run_id,
        runner_id=runner_id,
    )
    authority_key = Ed25519PrivateKey.generate()
    authority_id = f"route-authority-{run_id}"
    core = _authority_attestation_core(
        authority_key,
        authority_id=authority_id,
        runner_id=runner_id,
        ledger=bundle["ledger"],
        request=bundle["request"],
        history=bundle["history"],
        process_evidence=bundle["process_evidence"],
        stale_attempt=bundle["stale_owner_attempt"],
        database_path_or_bytes=bundle["database_path"],
    )
    attestation = _sign_authority_attestation(authority_key, core)
    key_doc = _participant_key_document(
        authority_key,
        authority_id,
        "authority_host",
        fixture=False,
    )
    _write(out_dir / "authority-attestation.json", attestation)
    key_path = out_dir / "authority-public-key.json"
    _write(key_path, key_doc)
    write_key_predicate(
        key_path,
        out_dir / "authority-public-key.predicate.json",
        "authority_host",
        "authority_host",
    )


def produce_runner(authority_dir: Path, out_dir: Path) -> None:
    ledger = _read(authority_dir / "route-ledger.json")
    request = _read(authority_dir / "request.json")
    attestation = _read(authority_dir / "authority-attestation.json")
    authority_key_doc = _read(authority_dir / "authority-public-key.json")
    history_doc = _read(authority_dir / "store-history.json")
    history = history_doc.get("entries")
    process_evidence = _read(authority_dir / "process-evidence.json")
    stale_attempt = _read(authority_dir / "stale-owner-attempt.json")
    database_path = authority_dir / "authority-store.sqlite3"
    if not database_path.is_file():
        raise EvidenceError("runner host requires the real transferred SQLite authority database")
    runner_key = Ed25519PrivateKey.generate()
    result, receipt, runner_key_doc = _build_runner_material(
        runner_key,
        ledger,
        request,
        attestation,
        authority_key_doc,
        history=history,
        process_evidence=process_evidence,
        stale_attempt=stale_attempt,
        database_path=database_path,
        fixture=False,
    )
    _write(out_dir / "result.json", result)
    _write(out_dir / "completion-receipt.json", receipt)
    runner_key_path = out_dir / "runner-public-key.json"
    _write(runner_key_path, runner_key_doc)
    write_key_predicate(
        runner_key_path,
        out_dir / "runner-public-key.predicate.json",
        "runner_host",
        "runner_host",
    )


def verify_sqlite_authority(authority_dir: Path, output_path: Path) -> None:
    ledger = _read(authority_dir / "route-ledger.json")
    request = _read(authority_dir / "request.json")
    attestation = _read(authority_dir / "authority-attestation.json")
    key_doc = _read(authority_dir / "authority-public-key.json")
    history_doc = _read(authority_dir / "store-history.json")
    history = history_doc.get("entries")
    process_evidence = _read(authority_dir / "process-evidence.json")
    stale_attempt = _read(authority_dir / "stale-owner-attempt.json")
    database_path = authority_dir / "authority-store.sqlite3"
    if not database_path.exists():
        raise EvidenceError("independent verifier requires the transferred SQLite database")
    _verify_authority_material(
        ledger,
        request,
        attestation,
        key_doc,
        history=history,
        process_evidence=process_evidence,
        stale_attempt=stale_attempt,
        database_path=database_path,
    )
    from durable_authority import verify_sqlite_authority_bundle
    result = verify_sqlite_authority_bundle(
        database_path,
        expected_ledger=ledger,
        expected_history=history,
    )
    _write(output_path, result)


def write_verifier_host(output_path: Path, *, fixture: bool = False) -> None:
    document = {
        "format": "in-formation.proof-runner-verifier-host/0.1",
        "host": _host_identity("independent_verifier_host", fixture=fixture),
    }
    _write(output_path, document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fixture = sub.add_parser("fixture", help="write deterministic test evidence")
    fixture.add_argument("--out-dir", type=Path, required=True)

    authority = sub.add_parser("authority", help="produce a route-authority checkpoint")
    authority.add_argument("--out-dir", type=Path, required=True)

    runner = sub.add_parser("runner", help="produce the signed proof-action result")
    runner.add_argument("--authority-dir", type=Path, required=True)
    runner.add_argument("--out-dir", type=Path, required=True)

    verify = sub.add_parser("verify-key-attestation", help="verify a participant public-key attestation")
    verify.add_argument("--path", type=Path, required=True)
    verify.add_argument("--role", choices=("authority_host", "runner_host"), required=True)
    verify.add_argument("--job", choices=("authority_host", "runner_host"), required=True)

    verifier = sub.add_parser("verifier-host", help="write the independent third-host identity")
    verifier.add_argument("--output", type=Path, required=True)
    verifier.add_argument("--fixture", action="store_true", help="write deterministic test identity")

    verify_sqlite = sub.add_parser("verify-sqlite-authority", help="reopen and verify transferred SQLite authority evidence")
    verify_sqlite.add_argument("--authority-dir", type=Path, required=True)
    verify_sqlite.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "fixture":
            build_fixture(args.out_dir)
        elif args.command == "authority":
            produce_authority(args.out_dir)
        elif args.command == "runner":
            produce_runner(args.authority_dir, args.out_dir)
        elif args.command == "verify-key-attestation":
            result = verify_key_attestation(args.path, args.role, args.job)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "verifier-host":
            write_verifier_host(args.output, fixture=args.fixture)
        elif args.command == "verify-sqlite-authority":
            verify_sqlite_authority(args.authority_dir, args.output)
    except (EvidenceError, CompletionReceiptError, OSError, ValueError) as exc:
        parser.exit(1, f"proof-runner reconstruction: {exc}\n")


if __name__ == "__main__":
    main()
