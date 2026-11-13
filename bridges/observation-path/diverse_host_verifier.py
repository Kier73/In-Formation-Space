#!/usr/bin/env python3
"""Independent, standard-library reconstruction of IHP-001 host evidence.

This module intentionally does not import the primary IHP verifier, E-CPU,
the operation-span validator, or the temporal-provenance validator. It checks
the serialized contracts independently so implementation diversity can be
tested on a separate hosted runner.

It does not authenticate GitHub/Sigstore attestations. The primary IHP verifier
retains that responsibility; this verifier checks the exact transferred bytes,
the declared record structure, and the causal handoff reconstructed from them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))
from formats.canonical_metadata_v1 import (  # noqa: E402
    CanonicalMetadataError,
    canonical_bytes as _shared_canonical_bytes,
)

REPOSITORY = "Kier73/In-Formation-Space"
WORKFLOW_PATH = ".github/workflows/independent-host-operation-path.yml"
SOURCE_REF = "refs/heads/main"
WORKFLOW_REF = f"{REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}"

RECORD_FORMAT = "in-formation.independent-host-operation-record"
RECORD_SCHEMA = "in-formation.independent-host-operation-record/0.1"
SPAN_FORMAT = "in-formation.operation-span"
SPAN_SCHEMA = "in-formation.operation-span/0.1"
PAYLOAD_SCHEMA = "in-formation.operation-path.handoff-payload/0.1"
HANDOFF_SCHEMA = "in-formation.operation-path.causal-handoff/0.1"
RELAY_CHANNEL = "github-actions-artifact-relay/v1"

REPORT_SCHEMA = "in-formation.diverse-host-operation-report/0.1"
PREDICATE_SCHEMA = "in-formation.diverse-host-operation-report-predicate/0.1"
PREDICATE_TYPE = (
    "https://kier73.github.io/in-formation-space/"
    "diverse-host-operation-report/v1"
)

MEASUREMENT_SCOPE = (
    "Elapsed monotonic time between the recorder's immediately-before and "
    "immediately-after samples around one synchronous callable invocation; "
    "includes blocking within the call and excludes later work."
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECORD_FIELDS = {
    "format", "schema", "role", "host", "operation_span", "temporal_frame",
    "handoff_payload", "source_record_sha256", "handoff_witness", "record_digest",
}
_HOST_FIELDS = {
    "role", "repository", "run_id", "run_attempt", "run_number",
    "workflow_ref", "workflow_sha", "git_ref", "git_sha", "job",
    "runner_name", "runner_os", "runner_arch", "runner_environment",
    "actor_id", "clock_segment_id",
}
_SPAN_FIELDS = {
    "format", "schema", "attempt_id", "span_id", "operation_id",
    "clock_actor_id", "clock_segment_id", "monotonic_start_ns",
    "monotonic_end_ns", "elapsed_ns", "clock_status", "outcome",
    "exception_type", "context", "measurement_scope", "span_digest",
}
_FRAME_FIELDS = {
    "actor_id", "monotonic", "wall", "causal", "scheduler",
    "event_lambda", "chronon_phase", "chemical_tau",
}
_PAYLOAD_FIELDS = {
    "schema", "path_id", "attempt_id", "predecessor_span_digest",
    "sender_actor_id", "sender_completion_frame", "payload_digest",
}
_HANDOFF_FIELDS = {
    "schema", "path_id", "attempt_id", "predecessor_span_digest",
    "successor_span_digest", "channel_id", "message_sequence",
    "received_sequence", "sender_actor_id", "receiver_actor_id",
    "payload_digest", "sender_completion_frame", "receiver_start_frame",
    "handoff_digest",
}


class DiverseVerificationError(ValueError):
    """A host record, handoff, or report failed independent reconstruction."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DiverseVerificationError(f"{label} must be non-empty text without NUL")
    return value


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DiverseVerificationError(f"{label} must be an integer >= {minimum}")
    return value


def _finite_number(value: object, label: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiverseVerificationError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise DiverseVerificationError(f"{label} must be finite and >= {minimum}")
    return number


def canonical_bytes(value: object) -> bytes:
    try:
        return _shared_canonical_bytes(value)
    except CanonicalMetadataError as error:
        raise DiverseVerificationError(str(error)) from error


def object_digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DiverseVerificationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _exact_fields(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise DiverseVerificationError(f"{label} must contain exactly {sorted(expected)}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def read_canonical_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise DiverseVerificationError(f"{path} must use canonical JSON followed by one LF")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DiverseVerificationError(f"{path} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise DiverseVerificationError(f"{path} must contain one JSON object")
    if canonical_bytes(value) + b"\n" != raw:
        raise DiverseVerificationError(f"{path} is not in the canonical JSON byte representation")
    return value, raw


def host_metadata(
    role: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Capture and constrain the fresh verifier job's GitHub workflow context."""
    selected = os.environ if env is None else env
    if role != "diverse_verifier_host":
        raise DiverseVerificationError("unsupported verifier role")

    def required(name: str) -> str:
        return _text(selected.get(name), f"runner environment {name}")

    repository = required("GITHUB_REPOSITORY")
    job = required("GITHUB_JOB")
    workflow_ref = required("GITHUB_WORKFLOW_REF")
    git_ref = required("GITHUB_REF")
    runner_environment = required("RUNNER_ENVIRONMENT")
    if repository != REPOSITORY:
        raise DiverseVerificationError("verifier repository is not the expected repository")
    if job != role:
        raise DiverseVerificationError(f"verifier job must be {role}, received {job}")
    if workflow_ref != WORKFLOW_REF or git_ref != SOURCE_REF:
        raise DiverseVerificationError("diverse verification must run in this workflow on main")
    if runner_environment != "github-hosted":
        raise DiverseVerificationError("diverse verifier must use a GitHub-hosted runner")

    runner_name = required("RUNNER_NAME")
    run_id = required("GITHUB_RUN_ID")
    attempt = required("GITHUB_RUN_ATTEMPT")
    actor_id = (
        f"{repository}#run-{run_id}.attempt-{attempt}."
        f"{role}.{runner_name}"
    )
    return {
        "role": role,
        "repository": repository,
        "run_id": run_id,
        "run_attempt": attempt,
        "run_number": required("GITHUB_RUN_NUMBER"),
        "workflow_ref": workflow_ref,
        "workflow_sha": required("GITHUB_WORKFLOW_SHA"),
        "git_ref": git_ref,
        "git_sha": required("GITHUB_SHA"),
        "job": job,
        "runner_name": runner_name,
        "runner_os": required("RUNNER_OS"),
        "runner_arch": required("RUNNER_ARCH"),
        "runner_environment": runner_environment,
        "actor_id": actor_id,
        "clock_segment_id": "0",
    }


def _validate_frame(frame: object, label: str) -> dict[str, Any]:
    raw = _exact_fields(frame, _FRAME_FIELDS, label)
    actor = _text(raw["actor_id"], f"{label}.actor_id")
    normalized: dict[str, Any] = {"actor_id": actor}

    monotonic = raw["monotonic"]
    if monotonic is None:
        normalized["monotonic"] = None
    else:
        monotonic = _exact_fields(
            monotonic, {"actor_id", "segment", "elapsed_ns"}, f"{label}.monotonic"
        )
        if _text(monotonic["actor_id"], f"{label}.monotonic.actor_id") != actor:
            raise DiverseVerificationError(f"{label} monotonic actor mismatch")
        normalized["monotonic"] = {
            "actor_id": actor,
            "segment": _integer(monotonic["segment"], f"{label}.monotonic.segment"),
            "elapsed_ns": _integer(monotonic["elapsed_ns"], f"{label}.monotonic.elapsed_ns"),
        }

    wall = raw["wall"]
    if wall is None:
        normalized["wall"] = None
    else:
        wall = _exact_fields(wall, {"actor_id", "utc_ns", "sample_index"}, f"{label}.wall")
        if _text(wall["actor_id"], f"{label}.wall.actor_id") != actor:
            raise DiverseVerificationError(f"{label} wall actor mismatch")
        if isinstance(wall["utc_ns"], bool) or not isinstance(wall["utc_ns"], int):
            raise DiverseVerificationError(f"{label}.wall.utc_ns must be an integer")
        normalized["wall"] = {
            "actor_id": actor,
            "utc_ns": wall["utc_ns"],
            "sample_index": _integer(wall["sample_index"], f"{label}.wall.sample_index"),
        }

    causal = raw["causal"]
    if causal is None:
        normalized["causal"] = None
    else:
        causal = _exact_fields(causal, {"actor_id", "lamport", "vector"}, f"{label}.causal")
        if _text(causal["actor_id"], f"{label}.causal.actor_id") != actor:
            raise DiverseVerificationError(f"{label} causal actor mismatch")
        lamport = _integer(causal["lamport"], f"{label}.causal.lamport")
        vector = causal["vector"]
        if not isinstance(vector, Mapping) or not vector:
            raise DiverseVerificationError(f"{label}.causal.vector must be a non-empty object")
        normalized_vector: dict[str, int] = {}
        for key, count in vector.items():
            actor_key = _text(key, f"{label}.causal.vector actor")
            normalized_vector[actor_key] = _integer(count, f"{label}.causal.vector[{actor_key}]")
            if normalized_vector[actor_key] > lamport:
                raise DiverseVerificationError(f"{label}.causal.vector exceeds Lamport value")
        if actor not in normalized_vector:
            raise DiverseVerificationError(f"{label}.causal.vector omits its own actor")
        normalized["causal"] = {
            "actor_id": actor,
            "lamport": lamport,
            "vector": dict(sorted(normalized_vector.items())),
        }

    scheduler = raw["scheduler"]
    if scheduler is None:
        normalized["scheduler"] = None
    else:
        scheduler = _exact_fields(
            scheduler, {"scheduler_id", "tick"}, f"{label}.scheduler"
        )
        normalized["scheduler"] = {
            "scheduler_id": _text(scheduler["scheduler_id"], f"{label}.scheduler.scheduler_id"),
            "tick": _integer(scheduler["tick"], f"{label}.scheduler.tick"),
        }

    event_lambda = raw["event_lambda"]
    normalized["event_lambda"] = (
        None if event_lambda is None else _integer(event_lambda, f"{label}.event_lambda")
    )

    phase = raw["chronon_phase"]
    if phase is None:
        normalized["chronon_phase"] = None
    else:
        if not isinstance(phase, (list, tuple)) or len(phase) != 2:
            raise DiverseVerificationError(f"{label}.chronon_phase must be a pair")
        real = _finite_number(phase[0], f"{label}.chronon_phase[0]")
        imaginary = _finite_number(phase[1], f"{label}.chronon_phase[1]")
        if not math.isclose(math.hypot(real, imaginary), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise DiverseVerificationError(f"{label}.chronon_phase must lie on the unit circle")
        normalized["chronon_phase"] = [real, imaginary]

    chemical_tau = raw["chemical_tau"]
    normalized["chemical_tau"] = (
        None if chemical_tau is None
        else _finite_number(chemical_tau, f"{label}.chemical_tau", minimum=0.0)
    )
    return normalized


def _validate_span(span: object, label: str) -> dict[str, Any]:
    raw = _exact_fields(span, _SPAN_FIELDS, label)
    if raw["format"] != SPAN_FORMAT or raw["schema"] != SPAN_SCHEMA:
        raise DiverseVerificationError(f"{label} format or schema is unsupported")
    for key in (
        "attempt_id", "span_id", "operation_id", "clock_actor_id", "clock_segment_id"
    ):
        _text(raw[key], f"{label}.{key}")
    start = _integer(raw["monotonic_start_ns"], f"{label}.monotonic_start_ns")
    end = _integer(raw["monotonic_end_ns"], f"{label}.monotonic_end_ns")
    elapsed = _integer(raw["elapsed_ns"], f"{label}.elapsed_ns")
    if raw["clock_status"] != "measured" or end < start or elapsed != end - start:
        raise DiverseVerificationError(f"{label} must contain one exact measured monotonic interval")
    if raw["outcome"] != "succeeded" or raw["exception_type"] is not None:
        raise DiverseVerificationError(f"{label} must describe a successful callable")
    if raw["measurement_scope"] != MEASUREMENT_SCOPE:
        raise DiverseVerificationError(f"{label} measurement scope is not recognized")
    if not isinstance(raw["context"], Mapping):
        raise DiverseVerificationError(f"{label}.context must be a JSON object")
    canonical_bytes(dict(raw["context"]))
    core = {key: raw[key] for key in _SPAN_FIELDS if key != "span_digest"}
    if _require_digest(raw["span_digest"], f"{label}.span_digest") != object_digest(core):
        raise DiverseVerificationError(f"{label} digest does not match its contents")
    return dict(raw)


def _validate_host(host: object, role: str) -> dict[str, Any]:
    raw = _exact_fields(host, _HOST_FIELDS, f"{role}.host")
    for key in _HOST_FIELDS:
        _text(raw[key], f"{role}.host.{key}")
    if raw["role"] != role or raw["job"] != role:
        raise DiverseVerificationError(f"{role} host role and job do not match")
    if raw["repository"] != REPOSITORY:
        raise DiverseVerificationError(f"{role} host repository mismatch")
    if raw["workflow_ref"] != WORKFLOW_REF or raw["git_ref"] != SOURCE_REF:
        raise DiverseVerificationError(f"{role} host is not bound to the protected main workflow")
    if raw["runner_environment"] != "github-hosted":
        raise DiverseVerificationError(f"{role} host is not marked GitHub-hosted")
    return dict(raw)


def _validate_record(document: object, role: str) -> dict[str, Any]:
    raw = _exact_fields(document, _RECORD_FIELDS, f"{role} record")
    if raw["format"] != RECORD_FORMAT or raw["schema"] != RECORD_SCHEMA:
        raise DiverseVerificationError(f"{role} record format or schema is unsupported")
    if raw["role"] != role:
        raise DiverseVerificationError(f"expected {role}, received {raw['role']!r}")
    core = {key: raw[key] for key in _RECORD_FIELDS if key != "record_digest"}
    if _require_digest(raw["record_digest"], f"{role}.record_digest") != object_digest(core):
        raise DiverseVerificationError(f"{role} record digest does not match its contents")

    host = _validate_host(raw["host"], role)
    span = _validate_span(raw["operation_span"], f"{role}.operation_span")
    frame = _validate_frame(raw["temporal_frame"], f"{role}.temporal_frame")
    if span["clock_actor_id"] != host["actor_id"] or frame["actor_id"] != host["actor_id"]:
        raise DiverseVerificationError(f"{role} actor identity does not bind span and frame")
    if span["clock_segment_id"] != host["clock_segment_id"]:
        raise DiverseVerificationError(f"{role} span segment does not bind host metadata")
    if frame["monotonic"] is None or frame["causal"] is None:
        raise DiverseVerificationError(f"{role} frame requires monotonic and causal coordinates")
    if str(frame["monotonic"]["segment"]) != host["clock_segment_id"]:
        raise DiverseVerificationError(f"{role} frame segment does not bind host metadata")

    if role == "source_host":
        if raw["source_record_sha256"] is not None or raw["handoff_witness"] is not None:
            raise DiverseVerificationError("source record cannot claim a predecessor or receiver witness")
        payload = _exact_fields(raw["handoff_payload"], _PAYLOAD_FIELDS, "source handoff payload")
        if payload["schema"] != PAYLOAD_SCHEMA:
            raise DiverseVerificationError("source handoff payload schema is unsupported")
        payload_core = {key: payload[key] for key in _PAYLOAD_FIELDS if key != "payload_digest"}
        if _require_digest(payload["payload_digest"], "source payload_digest") != object_digest(payload_core):
            raise DiverseVerificationError("source handoff payload digest is invalid")
        if payload["sender_actor_id"] != host["actor_id"]:
            raise DiverseVerificationError("source payload sender does not match source host")
        if payload["attempt_id"] != span["attempt_id"]:
            raise DiverseVerificationError("source payload attempt does not match source span")
        if payload["predecessor_span_digest"] != span["span_digest"]:
            raise DiverseVerificationError("source payload does not bind source operation span")
        if payload["sender_completion_frame"] != frame:
            raise DiverseVerificationError("source payload frame differs from source temporal frame")
        if frame["monotonic"]["elapsed_ns"] < span["monotonic_end_ns"]:
            raise DiverseVerificationError("source completion frame predates source operation completion")
        _text(payload["path_id"], "source payload.path_id")
    else:
        _require_digest(raw["source_record_sha256"], "receiver.source_record_sha256")
        if raw["handoff_payload"] is not None or not isinstance(raw["handoff_witness"], Mapping):
            raise DiverseVerificationError("receiver must retain only its received handoff witness")
        witness = raw["handoff_witness"]
        if witness.get("attempt_id") != span["attempt_id"]:
            raise DiverseVerificationError("receiver witness attempt does not match receiver span")
        if witness.get("successor_span_digest") != span["span_digest"]:
            raise DiverseVerificationError("receiver witness does not bind receiver operation span")
    return dict(raw)


def _vector_relation(left: Mapping[str, int], right: Mapping[str, int]) -> str:
    """Return the partial order over vector clocks; missing actors count as zero."""
    actors = set(left) | set(right)
    less = any(left.get(actor, 0) < right.get(actor, 0) for actor in actors)
    greater = any(left.get(actor, 0) > right.get(actor, 0) for actor in actors)
    if less and greater:
        return "concurrent"
    if less:
        return "before"
    if greater:
        return "after"
    return "equal"


def _validate_pair_context(
    source_host: Mapping[str, Any],
    receiver_host: Mapping[str, Any],
    verifier_host: Mapping[str, Any],
) -> None:
    shared = (
        "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha",
    )
    for field in shared:
        if source_host[field] != receiver_host[field]:
            raise DiverseVerificationError(f"source and receiver differ in {field}")
        if source_host[field] != verifier_host[field]:
            raise DiverseVerificationError(f"verifier differs from host records in {field}")
    jobs = {source_host["job"], receiver_host["job"], verifier_host["job"]}
    actors = {source_host["actor_id"], receiver_host["actor_id"], verifier_host["actor_id"]}
    if len(jobs) != 3 or len(actors) != 3:
        raise DiverseVerificationError("source, receiver, and diverse verifier must be distinct jobs and actors")
    if source_host["job"] != "source_host" or receiver_host["job"] != "receiver_host":
        raise DiverseVerificationError("source and receiver job roles are not exact")
    if verifier_host["role"] != "diverse_verifier_host" or verifier_host["job"] != "diverse_verifier_host":
        raise DiverseVerificationError("independent verifier is not the distinct fourth job")
    if any(host["runner_environment"] != "github-hosted"
           for host in (source_host, receiver_host, verifier_host)):
        raise DiverseVerificationError("all three records must declare GitHub-hosted runners")


def reconstruct(
    source_document: Mapping[str, Any],
    source_bytes: bytes,
    receiver_document: Mapping[str, Any],
    receiver_bytes: bytes,
    verifier_host: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently reconstruct one IHP-001 causal edge from exact artifact bytes."""
    if canonical_bytes(source_document) + b"\n" != source_bytes:
        raise DiverseVerificationError("source record bytes are not canonical JSON plus LF")
    if canonical_bytes(receiver_document) + b"\n" != receiver_bytes:
        raise DiverseVerificationError("receiver record bytes are not canonical JSON plus LF")
    source = _validate_record(source_document, "source_host")
    receiver = _validate_record(receiver_document, "receiver_host")
    verifier = _validate_host(verifier_host, "diverse_verifier_host")
    source_host, receiver_host = source["host"], receiver["host"]
    _validate_pair_context(source_host, receiver_host, verifier)

    source_artifact_sha256 = bytes_digest(source_bytes)
    receiver_artifact_sha256 = bytes_digest(receiver_bytes)
    if receiver["source_record_sha256"] != source_artifact_sha256:
        raise DiverseVerificationError("receiver does not bind the exact source artifact bytes")

    predecessor = source["operation_span"]
    successor = receiver["operation_span"]
    payload = source["handoff_payload"]
    witness = _exact_fields(receiver["handoff_witness"], _HANDOFF_FIELDS, "receiver handoff witness")
    witness_core = {key: witness[key] for key in _HANDOFF_FIELDS if key != "handoff_digest"}
    if witness["schema"] != HANDOFF_SCHEMA:
        raise DiverseVerificationError("receiver handoff witness schema is unsupported")
    if _require_digest(witness["handoff_digest"], "handoff_digest") != object_digest(witness_core):
        raise DiverseVerificationError("receiver handoff witness digest is invalid")

    source_frame = _validate_frame(source["temporal_frame"], "source.temporal_frame")
    sender_frame = _validate_frame(witness["sender_completion_frame"], "witness.sender_completion_frame")
    receiver_frame = _validate_frame(witness["receiver_start_frame"], "witness.receiver_start_frame")
    if sender_frame != source_frame or payload["sender_completion_frame"] != source_frame:
        raise DiverseVerificationError("handoff witness does not preserve the exact sender completion frame")
    if receiver_frame != receiver["temporal_frame"]:
        raise DiverseVerificationError("receiver record does not preserve the exact receiver start frame")

    path_id = _text(payload["path_id"], "source payload.path_id")
    attempt_id = _text(payload["attempt_id"], "source payload.attempt_id")
    if witness["path_id"] != path_id or witness["attempt_id"] != attempt_id:
        raise DiverseVerificationError("handoff witness belongs to another path or attempt")
    if predecessor["attempt_id"] != attempt_id or successor["attempt_id"] != attempt_id:
        raise DiverseVerificationError("operation spans do not belong to the same attempt")
    if witness["predecessor_span_digest"] != predecessor["span_digest"]:
        raise DiverseVerificationError("handoff predecessor digest does not match source span")
    if witness["successor_span_digest"] != successor["span_digest"]:
        raise DiverseVerificationError("handoff successor digest does not match receiver span")
    if witness["payload_digest"] != payload["payload_digest"]:
        raise DiverseVerificationError("handoff witness does not bind the exact source payload digest")

    sender_id = source_host["actor_id"]
    receiver_id = receiver_host["actor_id"]
    if witness["sender_actor_id"] != sender_id or witness["receiver_actor_id"] != receiver_id:
        raise DiverseVerificationError("handoff actor identities do not match the host records")
    if sender_id == receiver_id or sender_frame["actor_id"] != sender_id or receiver_frame["actor_id"] != receiver_id:
        raise DiverseVerificationError("handoff requires distinct, correctly bound temporal actors")

    sender_mono = sender_frame["monotonic"]
    receiver_mono = receiver_frame["monotonic"]
    if str(sender_mono["segment"]) != predecessor["clock_segment_id"]:
        raise DiverseVerificationError("sender frame and source operation use different clock segments")
    if str(receiver_mono["segment"]) != successor["clock_segment_id"]:
        raise DiverseVerificationError("receiver frame and successor operation use different clock segments")
    if sender_mono["elapsed_ns"] < predecessor["monotonic_end_ns"]:
        raise DiverseVerificationError("sender completion frame predates the source operation end")
    if receiver_mono["elapsed_ns"] > successor["monotonic_start_ns"]:
        raise DiverseVerificationError("receiver start frame follows the receiver operation start")

    if witness["channel_id"] != RELAY_CHANNEL:
        raise DiverseVerificationError("handoff relay channel is not the declared artifact relay")
    sent = _integer(witness["message_sequence"], "handoff.message_sequence", 1)
    received = _integer(witness["received_sequence"], "handoff.received_sequence", 1)
    if sent != received:
        raise DiverseVerificationError("sender and receiver artifact-relay sequence values differ")

    sender_causal = sender_frame["causal"]
    receiver_causal = receiver_frame["causal"]
    relation = _vector_relation(sender_causal["vector"], receiver_causal["vector"])
    if relation != "before" or sender_causal["lamport"] >= receiver_causal["lamport"]:
        raise DiverseVerificationError("receiver vector clock does not strictly follow sender completion")

    report_core = {
        "schema": REPORT_SCHEMA,
        "path_id": path_id,
        "attempt_id": attempt_id,
        "repository": source_host["repository"],
        "run_id": source_host["run_id"],
        "run_attempt": source_host["run_attempt"],
        "workflow_ref": source_host["workflow_ref"],
        "workflow_sha": source_host["workflow_sha"],
        "source": {
            "job": source_host["job"],
            "actor_id": sender_id,
            "runner_name": source_host["runner_name"],
            "runner_os": source_host["runner_os"],
            "runner_arch": source_host["runner_arch"],
            "local_elapsed_ns": predecessor["elapsed_ns"],
            "span_digest": predecessor["span_digest"],
            "record_digest": source["record_digest"],
            "artifact_sha256": source_artifact_sha256,
        },
        "receiver": {
            "job": receiver_host["job"],
            "actor_id": receiver_id,
            "runner_name": receiver_host["runner_name"],
            "runner_os": receiver_host["runner_os"],
            "runner_arch": receiver_host["runner_arch"],
            "local_elapsed_ns": successor["elapsed_ns"],
            "span_digest": successor["span_digest"],
            "record_digest": receiver["record_digest"],
            "artifact_sha256": receiver_artifact_sha256,
            "source_artifact_sha256": receiver["source_record_sha256"],
        },
        "diverse_verifier": {
            "role": verifier["role"],
            "job": verifier["job"],
            "actor_id": verifier["actor_id"],
            "runner_name": verifier["runner_name"],
            "runner_os": verifier["runner_os"],
            "runner_arch": verifier["runner_arch"],
            "runner_environment": verifier["runner_environment"],
        },
        "checks": {
            "canonical_source_bytes": True,
            "canonical_receiver_bytes": True,
            "source_record_digest": True,
            "receiver_record_digest": True,
            "source_artifact_bytes_bound_by_receiver": True,
            "both_operation_span_digests": True,
            "host_actor_and_clock_segment_bindings": True,
            "sender_payload_digest_reconstructed": True,
            "receiver_handoff_digest_reconstructed": True,
            "handoff_endpoint_digests_and_attempt": True,
            "sender_and_receiver_frame_bindings": True,
            "local_monotonic_endpoint_constraints": True,
            "strict_vector_clock_happens_before": True,
            "artifact_relay_sequence_matches": True,
        },
        "causal_reconstruction": {
            "status": "reconstructed_from_independent_implementation",
            "edge_count": 1,
            "edge_basis": "message-linked vector-clock handoff and local monotonic endpoint checks",
            "relay_channel_id": witness["channel_id"],
            "message_sequence": sent,
            "received_sequence": received,
            "vector_relation": relation,
            "sender_vector": sender_causal["vector"],
            "receiver_vector": receiver_causal["vector"],
            "sender_lamport": sender_causal["lamport"],
            "receiver_lamport": receiver_causal["lamport"],
            "predecessor_span_digest": predecessor["span_digest"],
            "successor_span_digest": successor["span_digest"],
            "payload_digest": payload["payload_digest"],
            "handoff_digest": witness["handoff_digest"],
            "topological_order": [predecessor["span_digest"], successor["span_digest"]],
        },
        "duration": {
            "source_local_elapsed_ns": predecessor["elapsed_ns"],
            "receiver_local_elapsed_ns": successor["elapsed_ns"],
            "combined_cross_host_elapsed_ns": None,
            "status": "not_computed_independent_unaligned_clock_domains",
        },
        "scope": [
            "This is an independently implemented consistency reconstruction, not a cryptographic attestation verifier.",
            "This job does not run gh attestation verify and does not authenticate the Sigstore signatures on the source or receiver artifacts.",
            "The primary IHP verifier remains responsible for verifying artifact attestations against exact bytes and the pinned signer workflow policy.",
            "Host, runner, operating-system, architecture, actor, and job fields are validated as record claims; this verifier does not independently attest hardware identity or physical fault-domain separation.",
            "The causal edge is reconstructed from the participants' declared vector-clock frames, local monotonic endpoint constraints, and message-linked digests. A participant process can still misrepresent the operation it performed.",
            "The channel sequence belongs to the GitHub Actions artifact relay contract; it is not an E-CPU ReliableChannel sequence or evidence of direct TCP/mTLS transport.",
            "The source and receiver durations are local synchronous-call measurements. They are not CPU time, network latency, or a combined cross-host elapsed duration.",
        ],
    }
    return {**report_core, "report_digest": object_digest(report_core)}


def verify_to_report(source_path: Path, receiver_path: Path, output_path: Path) -> dict[str, Any]:
    source, source_bytes = read_canonical_json(source_path)
    receiver, receiver_bytes = read_canonical_json(receiver_path)
    verifier = host_metadata("diverse_verifier_host")
    report = reconstruct(source, source_bytes, receiver, receiver_bytes, verifier)
    write_json(output_path, report)
    return report


def write_report_predicate(
    report_path: Path,
    predicate_path: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Bind the diverse verifier job identity and exact report bytes to its predicate."""
    report, report_bytes = read_canonical_json(report_path)
    if report.get("schema") != REPORT_SCHEMA:
        raise DiverseVerificationError("unsupported diverse reconstruction report")
    core = {key: value for key, value in report.items() if key != "report_digest"}
    if _require_digest(report.get("report_digest"), "report_digest") != object_digest(core):
        raise DiverseVerificationError("diverse reconstruction report digest is invalid")
    verifier = host_metadata("diverse_verifier_host", env)
    expected_identity = {
        "role": verifier["role"],
        "job": verifier["job"],
        "actor_id": verifier["actor_id"],
        "runner_name": verifier["runner_name"],
        "runner_os": verifier["runner_os"],
        "runner_arch": verifier["runner_arch"],
        "runner_environment": verifier["runner_environment"],
    }
    if report.get("diverse_verifier") != expected_identity:
        raise DiverseVerificationError("report does not identify the current diverse verifier job")
    predicate = {
        "schema": PREDICATE_SCHEMA,
        "repository": verifier["repository"],
        "run_id": verifier["run_id"],
        "run_attempt": verifier["run_attempt"],
        "workflow_ref": verifier["workflow_ref"],
        "workflow_sha": verifier["workflow_sha"],
        "git_ref": verifier["git_ref"],
        "git_sha": verifier["git_sha"],
        "job": verifier["job"],
        "runner_name": verifier["runner_name"],
        "runner_os": verifier["runner_os"],
        "runner_arch": verifier["runner_arch"],
        "runner_environment": verifier["runner_environment"],
        "actor_id": verifier["actor_id"],
        "report_sha256": bytes_digest(report_bytes),
        "report_digest": report["report_digest"],
        "source_record_sha256": report["source"]["artifact_sha256"],
        "receiver_record_sha256": report["receiver"]["artifact_sha256"],
        "path_id": report["path_id"],
        "causal_handoff_digest": report["causal_reconstruction"]["handoff_digest"],
    }
    write_json(predicate_path, predicate)
    return predicate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--source", type=Path, required=True)
    verify_parser.add_argument("--receiver", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    predicate_parser = commands.add_parser("write-report-predicate")
    predicate_parser.add_argument("--report", type=Path, required=True)
    predicate_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            verify_to_report(args.source, args.receiver, args.output)
        else:
            write_report_predicate(args.report, args.output)
    except (DiverseVerificationError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"diverse-host-verifier: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
