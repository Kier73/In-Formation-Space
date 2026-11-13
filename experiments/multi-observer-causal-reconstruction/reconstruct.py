#!/usr/bin/env python3
"""Reconstruct a multi-observer causal event graph from E-CPU TemporalFrames.

A1 is sent from source A to receiver B. A2 is later on A but is deliberately
not sent. B1 merges only A1. C1 is produced by an independent observer whose
temporal profile omits the causal domain. A fourth host reconstructs the
pairwise relation matrix from attested records.

Wall clocks are deliberately offset per host and are never used for causal
ordering. Each operation duration remains in its own monotonic clock domain.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for candidate in (
    ROOT / "external" / "E-CPU",
    ROOT / "bridges" / "observation-path",
    ROOT / "bridges" / "temporal-provenance",
):
    # Resolve the E-CPU checkout from the workspace, not from the script's
    # directory. PYTHONPATH entries are not reliably relative in script mode.
    resolved = str(candidate.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

from operation_spans import OperationSpanRecorder, validate_operation_span
from distributed_operation_path import (
    build_causal_handoff_witness,
    build_handoff_payload,
    validate_causal_handoff_witness,
)
from temporal_provenance import validate_temporal_frame
from mailcpu.temporal import (
    CausalStamp,
    ClockDomain,
    TemporalContext,
    TemporalProfile,
)

REPOSITORY = "Kier73/In-Formation-Space"
WORKFLOW_PATH = ".github/workflows/multi-observer-causal-reconstruction.yml"
SIGNER_WORKFLOW = f"{REPOSITORY}/{WORKFLOW_PATH}"
SOURCE_REF = "refs/heads/main"
RECORD_FORMAT = "in-formation.multi-observer-causal-record"
RECORD_SCHEMA = "in-formation.multi-observer-causal-record/0.1"
REPORT_SCHEMA = "in-formation.multi-observer-causal-report/0.1"
RECORD_PREDICATE_TYPE = (
    "https://kier73.github.io/in-formation-space/multi-observer-causal-record/v1"
)
REPORT_PREDICATE_TYPE = (
    "https://kier73.github.io/in-formation-space/multi-observer-causal-report/v1"
)
RECORD_PREDICATE_SCHEMA = "in-formation.multi-observer-causal-record-predicate/0.1"
REPORT_PREDICATE_SCHEMA = "in-formation.multi-observer-causal-report-predicate/0.1"
RELAY_CHANNEL = "github-actions-artifact-relay/v1"
GH_MIN_VERSION = (2, 103, 3)
CAUSAL_ROLES = ("source_host", "receiver_host")
PRODUCER_ROLES = ("source_host", "receiver_host", "observer_host")
EVENT_IDS = {
    "source_host": ("A1", "A2"),
    "receiver_host": ("B1",),
    "observer_host": ("C1",),
}
WALL_OFFSETS_NS = {
    "source_host": 12 * 60 * 60 * 1_000_000_000,
    "receiver_host": -12 * 60 * 60 * 1_000_000_000,
    "observer_host": 3 * 60 * 60 * 1_000_000_000,
}
SHARED_RUN_FIELDS = (
    "repository", "run_id", "run_attempt", "run_number",
    "workflow_ref", "workflow_sha", "git_ref", "git_sha",
)


class ReconstructionError(ValueError):
    """A record, attestation, temporal frame, or reconstructed relation is invalid."""


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ReconstructionError(f"value is not canonical finite JSON: {error}") from error


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_object(value: object) -> str:
    return digest_bytes(canonical(value))


def sha256_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReconstructionError(f"cannot read evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise ReconstructionError("evidence file must contain one JSON object")
    return value


def _required_env(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReconstructionError(f"required GitHub environment field {key} is missing")
    return value.strip()


def actor_id_for(role: str, run_id: str, attempt: str) -> str:
    allowed = (*PRODUCER_ROLES, "verifier_host")
    if role not in allowed:
        raise ReconstructionError(f"unsupported host role {role!r}")
    return f"{REPOSITORY}#run-{run_id}.attempt-{attempt}.{role}"


def host_metadata(role: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    selected = os.environ if env is None else env
    if role not in (*PRODUCER_ROLES, "verifier_host"):
        raise ReconstructionError(f"unsupported host role {role!r}")
    repository = _required_env(selected, "GITHUB_REPOSITORY")
    job = _required_env(selected, "GITHUB_JOB")
    workflow_ref = _required_env(selected, "GITHUB_WORKFLOW_REF")
    git_ref = _required_env(selected, "GITHUB_REF")
    runner_environment = _required_env(selected, "RUNNER_ENVIRONMENT")
    expected_workflow_ref = f"{SIGNER_WORKFLOW}@{SOURCE_REF}"
    if repository != REPOSITORY or job != role:
        raise ReconstructionError("repository or job identity does not match the expected role")
    if workflow_ref != expected_workflow_ref or git_ref != SOURCE_REF:
        raise ReconstructionError("records must be produced by this workflow on main")
    if runner_environment != "github-hosted":
        raise ReconstructionError("records must be produced on GitHub-hosted runners")
    run_id = _required_env(selected, "GITHUB_RUN_ID")
    attempt = _required_env(selected, "GITHUB_RUN_ATTEMPT")
    return {
        "role": role,
        "repository": repository,
        "run_id": run_id,
        "run_attempt": attempt,
        "run_number": _required_env(selected, "GITHUB_RUN_NUMBER"),
        "workflow_ref": workflow_ref,
        "workflow_sha": _required_env(selected, "GITHUB_WORKFLOW_SHA"),
        "git_ref": git_ref,
        "git_sha": _required_env(selected, "GITHUB_SHA"),
        "job": job,
        "runner_name": _required_env(selected, "RUNNER_NAME"),
        "runner_os": _required_env(selected, "RUNNER_OS"),
        "runner_arch": _required_env(selected, "RUNNER_ARCH"),
        "runner_environment": runner_environment,
        "actor_id": actor_id_for(role, run_id, attempt),
        "clock_segment_id": "0",
    }


def _causal_roster(host: Mapping[str, Any]) -> dict[str, int]:
    return {
        actor_id_for(role, str(host["run_id"]), str(host["run_attempt"])): 0
        for role in CAUSAL_ROLES
    }


def _temporal_context(
    host: Mapping[str, Any],
    *,
    include_causal: bool,
) -> TemporalContext:
    domains = {ClockDomain.MONOTONIC, ClockDomain.WALL}
    vector = None
    if include_causal:
        domains.add(ClockDomain.CAUSAL)
        vector = _causal_roster(host)
    # The offset is injected only into the calendar source. E-CPU retains
    # independent monotonic and causal coordinates; no conversion is defined.
    wall_offset = WALL_OFFSETS_NS[str(host["role"])]
    return TemporalContext(
        str(host["actor_id"]),
        TemporalProfile(frozenset(domains)),
        wall_time_ns=lambda: time.time_ns() + wall_offset,
        segment=0,
        vector=vector,
    )


def _recorder(host: Mapping[str, Any], context: TemporalContext) -> OperationSpanRecorder:
    return OperationSpanRecorder(
        clock_actor_id=str(host["actor_id"]),
        clock_segment_id=str(host["clock_segment_id"]),
        clock_ns=lambda: context.monotonic_reading().elapsed_ns,
    )


def _bounded_work(label: str) -> str:
    value = label.encode("utf-8")
    for counter in range(384):
        value = hashlib.sha256(value + counter.to_bytes(4, "big")).digest()
    return value.hex()


def _event(event_id: str, frame: Mapping[str, Any], span: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "temporal_frame": dict(frame),
        "operation_span": dict(span),
    }


def _seal_record(core: dict[str, Any]) -> dict[str, Any]:
    return {**core, "record_digest": digest_object(core)}


def _validate_host(host: object, expected_role: str) -> dict[str, Any]:
    fields = {
        "role", "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha", "job",
        "runner_name", "runner_os", "runner_arch", "runner_environment",
        "actor_id", "clock_segment_id",
    }
    if not isinstance(host, Mapping) or set(host) != fields:
        raise ReconstructionError("host identity fields are incomplete or unexpected")
    if any(not isinstance(host[key], str) or not host[key] for key in fields):
        raise ReconstructionError("host identity fields must be non-empty strings")
    if host["role"] != expected_role or host["job"] != expected_role:
        raise ReconstructionError("host role and GitHub job do not agree")
    if host["repository"] != REPOSITORY:
        raise ReconstructionError("host record belongs to another repository")
    if host["workflow_ref"] != f"{SIGNER_WORKFLOW}@{SOURCE_REF}" or host["git_ref"] != SOURCE_REF:
        raise ReconstructionError("host record was not produced by this protected main workflow")
    if host["runner_environment"] != "github-hosted":
        raise ReconstructionError("host record is not from a GitHub-hosted runner")
    if host["actor_id"] != actor_id_for(expected_role, host["run_id"], host["run_attempt"]):
        raise ReconstructionError("actor ID is not bound to its workflow role and run")
    if host["clock_segment_id"] != "0":
        raise ReconstructionError("unexpected monotonic clock segment")
    return dict(host)


def _validate_event(
    raw: object,
    *,
    host: Mapping[str, Any],
    expected_event_id: str,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != {
        "event_id", "temporal_frame", "operation_span"
    }:
        raise ReconstructionError("event record fields are incomplete or unexpected")
    if raw["event_id"] != expected_event_id:
        raise ReconstructionError(f"expected event {expected_event_id}")
    try:
        frame = validate_temporal_frame(raw["temporal_frame"])
        span = validate_operation_span(raw["operation_span"])
    except (TypeError, ValueError, KeyError) as error:
        raise ReconstructionError(f"event {expected_event_id} has invalid temporal evidence: {error}") from error
    if frame["actor_id"] != host["actor_id"]:
        raise ReconstructionError(f"event {expected_event_id} actor differs from its host")
    if frame["monotonic"] is None or frame["wall"] is None:
        raise ReconstructionError(f"event {expected_event_id} must retain monotonic and wall readings")
    if frame["monotonic"]["actor_id"] != host["actor_id"]:
        raise ReconstructionError(f"event {expected_event_id} monotonic actor differs from host")
    if str(frame["monotonic"]["segment"]) != host["clock_segment_id"]:
        raise ReconstructionError(f"event {expected_event_id} monotonic segment differs from host")
    if frame["wall"]["actor_id"] != host["actor_id"]:
        raise ReconstructionError(f"event {expected_event_id} wall actor differs from host")
    if span["clock_actor_id"] != host["actor_id"] or span["clock_segment_id"] != host["clock_segment_id"]:
        raise ReconstructionError(f"event {expected_event_id} operation span differs from host clock")
    if span["clock_status"] != "measured" or span["elapsed_ns"] is None:
        raise ReconstructionError(f"event {expected_event_id} has no measured local duration")
    if span["attempt_id"] != f"run-{host['run_id']}-attempt-{host['run_attempt']}":
        raise ReconstructionError(f"event {expected_event_id} belongs to another attempt")
    frame_elapsed = frame["monotonic"]["elapsed_ns"]
    if expected_event_id == "B1":
        # B1's witnessed frame is intentionally captured at receiver start,
        # before its measured operation span begins.
        if frame_elapsed > span["monotonic_start_ns"]:
            raise ReconstructionError("B1 receiver-start frame follows its operation start")
    elif frame_elapsed < span["monotonic_end_ns"]:
        raise ReconstructionError(f"event {expected_event_id} frame predates operation completion")
    return {
        "event_id": expected_event_id,
        "temporal_frame": frame,
        "operation_span": span,
    }


def _validate_vector(event: Mapping[str, Any], roster: set[str], *, required: bool) -> None:
    frame = event["temporal_frame"]
    causal = frame["causal"]
    if causal is None:
        if required:
            raise ReconstructionError(f"event {event['event_id']} requires a causal stamp")
        return
    if set(causal["vector"]) != roster:
        raise ReconstructionError(
            f"event {event['event_id']} vector does not contain the complete declared roster"
        )
    if causal["actor_id"] != frame["actor_id"]:
        raise ReconstructionError(f"event {event['event_id']} causal actor differs from its frame")


def validate_record(document: Mapping[str, Any], expected_role: str) -> dict[str, Any]:
    fields = {
        "format", "schema", "role", "host", "wall_offset_ns", "events",
        "handoff_payload", "handoff_witness", "source_record_sha256", "record_digest",
    }
    if not isinstance(document, Mapping) or set(document) != fields:
        raise ReconstructionError("record fields are incomplete or unexpected")
    if document["format"] != RECORD_FORMAT or document["schema"] != RECORD_SCHEMA:
        raise ReconstructionError("unsupported multi-observer record format")
    if document["role"] != expected_role:
        raise ReconstructionError("record has the wrong host role")
    core = {key: document[key] for key in fields if key != "record_digest"}
    if document["record_digest"] != digest_object(core):
        raise ReconstructionError("record digest does not match its contents")
    host = _validate_host(document["host"], expected_role)
    if document["wall_offset_ns"] != WALL_OFFSETS_NS[expected_role]:
        raise ReconstructionError("wall-clock offset differs from the declared experiment profile")
    raw_events = document["events"]
    expected_ids = EVENT_IDS[expected_role]
    if not isinstance(raw_events, list) or len(raw_events) != len(expected_ids):
        raise ReconstructionError("record contains the wrong number of events")
    events = [
        _validate_event(raw, host=host, expected_event_id=expected_id)
        for raw, expected_id in zip(raw_events, expected_ids, strict=True)
    ]
    roster = set(_causal_roster(host))

    if expected_role == "source_host":
        if document["handoff_witness"] is not None or document["source_record_sha256"] is not None:
            raise ReconstructionError("source cannot contain a receiver witness or prior source digest")
        payload = document["handoff_payload"]
        if not isinstance(payload, Mapping):
            raise ReconstructionError("source is missing its handoff payload")
        _validate_vector(events[0], roster, required=True)
        _validate_vector(events[1], roster, required=True)
        rebuilt = build_handoff_payload(
            path_id=str(payload.get("path_id", "")),
            attempt_id=events[0]["operation_span"]["attempt_id"],
            predecessor_span_digest=events[0]["operation_span"]["span_digest"],
            sender_completion_frame=events[0]["temporal_frame"],
        )
        if dict(payload) != rebuilt:
            raise ReconstructionError("source A1 payload cannot be independently rebuilt")
        # Only A1 is present in the handoff. A2 must not be smuggled into it.
        if payload["predecessor_span_digest"] != events[0]["operation_span"]["span_digest"]:
            raise ReconstructionError("handoff predecessor is not A1")
        if payload["sender_completion_frame"] != events[0]["temporal_frame"]:
            raise ReconstructionError("handoff frame is not A1's exact completion frame")
    elif expected_role == "receiver_host":
        if document["handoff_payload"] is not None:
            raise ReconstructionError("receiver must retain the transferred payload only through its witness")
        if not isinstance(document["source_record_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", document["source_record_sha256"]):
            raise ReconstructionError("receiver does not bind exact source record bytes")
        if not isinstance(document["handoff_witness"], Mapping):
            raise ReconstructionError("receiver is missing its causal handoff witness")
        _validate_vector(events[0], roster, required=True)
    else:
        if document["handoff_payload"] is not None or document["handoff_witness"] is not None or document["source_record_sha256"] is not None:
            raise ReconstructionError("independent observer cannot claim a message handoff")
        _validate_vector(events[0], roster, required=False)
        if events[0]["temporal_frame"]["causal"] is not None:
            raise ReconstructionError("C1 must intentionally omit the causal domain")

    return {
        "format": RECORD_FORMAT,
        "schema": RECORD_SCHEMA,
        "role": expected_role,
        "host": host,
        "wall_offset_ns": document["wall_offset_ns"],
        "events": events,
        "handoff_payload": None if document["handoff_payload"] is None else dict(document["handoff_payload"]),
        "handoff_witness": None if document["handoff_witness"] is None else dict(document["handoff_witness"]),
        "source_record_sha256": document["source_record_sha256"],
        "record_digest": document["record_digest"],
    }


def produce_source(output_path: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    host = host_metadata("source_host", env)
    context = _temporal_context(host, include_causal=True)
    recorder = _recorder(host, context)
    attempt = f"run-{host['run_id']}-attempt-{host['run_attempt']}"

    recorder.measure(
        attempt_id=attempt, span_id="A1-span", operation_id="source.A1",
        operation=lambda: _bounded_work("source-event-A1"),
        context={"event_id": "A1", "role": "source_host"},
    )
    span_a1 = recorder.spans[-1]
    context.emit_causal_stamp()
    frame_a1 = context.observe().to_dict()

    # A2 is later in A's stream but intentionally not sent to B.
    recorder.measure(
        attempt_id=attempt, span_id="A2-span", operation_id="source.A2",
        operation=lambda: _bounded_work("source-event-A2"),
        context={"event_id": "A2", "role": "source_host"},
    )
    span_a2 = recorder.spans[-1]
    context.emit_causal_stamp()
    frame_a2 = context.observe().to_dict()

    path_id = f"run-{host['run_id']}-multi-observer"
    payload = build_handoff_payload(
        path_id=path_id,
        attempt_id=attempt,
        predecessor_span_digest=span_a1["span_digest"],
        sender_completion_frame=frame_a1,
    )
    record = _seal_record({
        "format": RECORD_FORMAT,
        "schema": RECORD_SCHEMA,
        "role": "source_host",
        "host": host,
        "wall_offset_ns": WALL_OFFSETS_NS["source_host"],
        "events": [
            _event("A1", frame_a1, span_a1),
            _event("A2", frame_a2, span_a2),
        ],
        "handoff_payload": payload,
        "handoff_witness": None,
        "source_record_sha256": None,
    })
    validate_record(record, "source_host")
    write_json(output_path, record)
    return record


def produce_receiver(
    source_path: Path,
    output_path: Path,
    env: Mapping[str, str] | None = None,
    *,
    attestation_verifier: Callable[..., Mapping[str, Any]] | None = None,
    gh: str = "gh",
) -> dict[str, Any]:
    source_bytes = source_path.read_bytes()
    source = validate_record(read_json(source_path), "source_host")
    verifier = verify_artifact_attestation if attestation_verifier is None else attestation_verifier
    source_attestation = verifier(source_path, source, "source_host", gh=gh)
    _validate_attestation_summary(source_attestation, digest_bytes(source_bytes))

    host = host_metadata("receiver_host", env)
    _validate_shared_run(source["host"], host)
    frame_a1 = source["events"][0]["temporal_frame"]
    context = _temporal_context(host, include_causal=True)
    context.receive_causal_stamp(CausalStamp.from_dict(frame_a1["causal"]))
    receiver_start_frame = context.observe().to_dict()

    recorder = _recorder(host, context)
    attempt = source["events"][0]["operation_span"]["attempt_id"]
    recorder.measure(
        attempt_id=attempt, span_id="B1-span", operation_id="receiver.B1",
        operation=lambda: _bounded_work("receiver-event-B1"),
        context={"event_id": "B1", "role": "receiver_host"},
    )
    span_b1 = recorder.spans[-1]
    witness = build_causal_handoff_witness(
        payload=source["handoff_payload"],
        successor_span_digest=span_b1["span_digest"],
        channel_id=RELAY_CHANNEL,
        message_sequence=1,
        received_sequence=1,
        receiver_start_frame=receiver_start_frame,
    )
    record = _seal_record({
        "format": RECORD_FORMAT,
        "schema": RECORD_SCHEMA,
        "role": "receiver_host",
        "host": host,
        "wall_offset_ns": WALL_OFFSETS_NS["receiver_host"],
        "events": [_event("B1", receiver_start_frame, span_b1)],
        "handoff_payload": None,
        "handoff_witness": witness,
        "source_record_sha256": digest_bytes(source_bytes),
    })
    validate_record(record, "receiver_host")
    write_json(output_path, record)
    return record


def produce_observer(output_path: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    host = host_metadata("observer_host", env)
    context = _temporal_context(host, include_causal=False)
    recorder = _recorder(host, context)
    attempt = f"run-{host['run_id']}-attempt-{host['run_attempt']}"
    recorder.measure(
        attempt_id=attempt, span_id="C1-span", operation_id="observer.C1",
        operation=lambda: _bounded_work("observer-event-C1"),
        context={"event_id": "C1", "role": "observer_host"},
    )
    span_c1 = recorder.spans[-1]
    frame_c1 = context.observe().to_dict()
    record = _seal_record({
        "format": RECORD_FORMAT,
        "schema": RECORD_SCHEMA,
        "role": "observer_host",
        "host": host,
        "wall_offset_ns": WALL_OFFSETS_NS["observer_host"],
        "events": [_event("C1", frame_c1, span_c1)],
        "handoff_payload": None,
        "handoff_witness": None,
        "source_record_sha256": None,
    })
    validate_record(record, "observer_host")
    write_json(output_path, record)
    return record


def _validate_shared_run(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    for field in SHARED_RUN_FIELDS:
        if left[field] != right[field]:
            raise ReconstructionError(f"host records differ in shared run field {field}")
    if left["job"] == right["job"] or left["actor_id"] == right["actor_id"]:
        raise ReconstructionError("host records must use distinct jobs and temporal actors")


def _vector_relation(left: Mapping[str, int], right: Mapping[str, int]) -> str:
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


def _ordered(left: int, right: int) -> str:
    return "before" if left < right else "after" if left > right else "equal"


def _attestation_predicate(record: Mapping[str, Any]) -> dict[str, Any]:
    host = record["host"]
    return {
        "schema": RECORD_PREDICATE_SCHEMA,
        "role": record["role"],
        "repository": host["repository"],
        "run_id": host["run_id"],
        "run_attempt": host["run_attempt"],
        "run_number": host["run_number"],
        "workflow_ref": host["workflow_ref"],
        "workflow_sha": host["workflow_sha"],
        "git_ref": host["git_ref"],
        "git_sha": host["git_sha"],
        "job": host["job"],
        "runner_name": host["runner_name"],
        "runner_os": host["runner_os"],
        "runner_arch": host["runner_arch"],
        "runner_environment": host["runner_environment"],
        "actor_id": host["actor_id"],
        "record_digest": record["record_digest"],
        "event_ids": [event["event_id"] for event in record["events"]],
        "wall_offset_ns": record["wall_offset_ns"],
        "source_record_sha256": record["source_record_sha256"],
        "payload_digest": None if record["handoff_payload"] is None else record["handoff_payload"]["payload_digest"],
        "handoff_digest": None if record["handoff_witness"] is None else record["handoff_witness"]["handoff_digest"],
    }


def write_record_predicate(record_path: Path, output_path: Path, role: str) -> dict[str, Any]:
    record = validate_record(read_json(record_path), role)
    predicate = _attestation_predicate(record)
    write_json(output_path, predicate)
    return predicate


def _gh_version(gh: str) -> tuple[int, int, int]:
    completed = subprocess.run([gh, "--version"], check=True, capture_output=True, text=True)
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", completed.stdout)
    if not match:
        raise ReconstructionError("cannot parse GitHub CLI version")
    return tuple(int(part) for part in match.groups())


def _attestation_command(path: Path, gh: str) -> list[str]:
    return [
        gh, "attestation", "verify", str(path),
        "--repo", REPOSITORY,
        "--predicate-type", RECORD_PREDICATE_TYPE,
        "--signer-workflow", SIGNER_WORKFLOW,
        "--source-ref", SOURCE_REF,
        "--deny-self-hosted-runners",
        "--format", "json",
    ]


def _matching_statement(results: Any, artifact_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(results, list):
        raise ReconstructionError("GitHub CLI attestation output must be a JSON array")
    matches = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        verification = item.get("verificationResult")
        if not isinstance(verification, Mapping):
            continue
        statement = verification.get("statement")
        if not isinstance(statement, Mapping):
            continue
        subjects = statement.get("subject", [])
        if any(
            isinstance(subject, Mapping)
            and isinstance(subject.get("digest"), Mapping)
            and subject["digest"].get("sha256") == artifact_sha256
            for subject in subjects
        ):
            matches.append((dict(statement), dict(verification)))
    if not matches:
        raise ReconstructionError("no verified attestation subject matches exact record bytes")
    if any(statement.get("predicateType") != RECORD_PREDICATE_TYPE for statement, _ in matches):
        raise ReconstructionError("attestation statement has an unexpected predicate type")
    return matches[0]


def verify_artifact_attestation(
    record_path: Path,
    record: Mapping[str, Any],
    expected_role: str,
    *,
    gh: str = "gh",
) -> dict[str, Any]:
    if _gh_version(gh) < GH_MIN_VERSION:
        raise ReconstructionError("GitHub CLI 2.103.3 or newer is required")
    artifact_sha = sha256_file(record_path)
    try:
        completed = subprocess.run(
            _attestation_command(record_path, gh),
            check=True, capture_output=True, text=True, env=os.environ.copy(),
        )
        results = json.loads(completed.stdout)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() if error.stderr else str(error)
        raise ReconstructionError(f"artifact attestation verification failed: {detail}") from error
    except json.JSONDecodeError as error:
        raise ReconstructionError("GitHub CLI did not return valid attestation JSON") from error
    statement, verification = _matching_statement(results, artifact_sha)
    if statement.get("predicate") != _attestation_predicate(record):
        raise ReconstructionError("signed record predicate differs from downloaded host record")
    if record["role"] != expected_role:
        raise ReconstructionError("record role differs from requested attestation role")
    signature = verification.get("signature")
    certificate_present = (
        isinstance(signature, Mapping)
        and isinstance(signature.get("certificate"), Mapping)
    )
    timestamps = verification.get("verifiedTimestamps", [])
    if not certificate_present:
        raise ReconstructionError("verified attestation has no signing certificate")
    return {
        "verified": True,
        "subject_sha256": artifact_sha,
        "predicate_type": RECORD_PREDICATE_TYPE,
        "signer_workflow": SIGNER_WORKFLOW,
        "source_ref": SOURCE_REF,
        "self_hosted_runners_denied": True,
        "verified_signature_certificate_present": True,
        "verified_timestamp_count": len(timestamps) if isinstance(timestamps, list) else 0,
    }


def _validate_attestation_summary(summary: Mapping[str, Any], expected_sha: str) -> dict[str, Any]:
    fields = {
        "verified", "subject_sha256", "predicate_type", "signer_workflow",
        "source_ref", "self_hosted_runners_denied",
        "verified_signature_certificate_present", "verified_timestamp_count",
    }
    if not isinstance(summary, Mapping) or set(summary) != fields:
        raise ReconstructionError("attestation summary fields are incomplete")
    if summary["verified"] is not True or summary["subject_sha256"] != expected_sha:
        raise ReconstructionError("attestation summary does not bind exact expected bytes")
    if summary["predicate_type"] != RECORD_PREDICATE_TYPE:
        raise ReconstructionError("attestation summary predicate type is unexpected")
    if summary["signer_workflow"] != SIGNER_WORKFLOW or summary["source_ref"] != SOURCE_REF:
        raise ReconstructionError("attestation summary does not pin protected main workflow")
    if summary["self_hosted_runners_denied"] is not True or summary["verified_signature_certificate_present"] is not True:
        raise ReconstructionError("attestation summary is missing signature or runner-policy evidence")
    count = summary["verified_timestamp_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ReconstructionError("attestation verified timestamp count is invalid")
    return dict(summary)


def build_report(
    source: Mapping[str, Any],
    receiver: Mapping[str, Any],
    observer: Mapping[str, Any],
    *,
    attestations: Mapping[str, Mapping[str, Any]],
    artifact_sha256: Mapping[str, str],
    verifier_host: Mapping[str, Any],
) -> dict[str, Any]:
    source = validate_record(source, "source_host")
    receiver = validate_record(receiver, "receiver_host")
    observer = validate_record(observer, "observer_host")
    _validate_shared_run(source["host"], receiver["host"])
    _validate_shared_run(source["host"], observer["host"])
    verifier = _validate_host(verifier_host, "verifier_host")
    _validate_shared_run(source["host"], verifier)
    hosts = (source["host"], receiver["host"], observer["host"], verifier)
    if len({host["job"] for host in hosts}) != 4 or len({host["actor_id"] for host in hosts}) != 4:
        raise ReconstructionError("three producers and verifier must be four distinct job actors")

    if set(attestations) != set(PRODUCER_ROLES) or set(artifact_sha256) != set(PRODUCER_ROLES):
        raise ReconstructionError("attestations and exact artifact digests must cover all producers")
    verified_attestations = {
        role: _validate_attestation_summary(attestations[role], artifact_sha256[role])
        for role in PRODUCER_ROLES
    }
    if receiver["source_record_sha256"] != artifact_sha256["source_host"]:
        raise ReconstructionError("receiver does not bind exact source artifact bytes")

    source_a1, source_a2 = source["events"]
    receiver_b1 = receiver["events"][0]
    observer_c1 = observer["events"][0]
    events = {
        event["event_id"]: event
        for event in (source_a1, source_a2, receiver_b1, observer_c1)
    }
    if set(events) != {"A1", "A2", "B1", "C1"}:
        raise ReconstructionError("event set differs from declared experiment")
    roster = set(_causal_roster(source["host"]))
    for event in events.values():
        _validate_vector(event, roster, required=event["event_id"] != "C1")

    witness = receiver["handoff_witness"]
    verified_witness = validate_causal_handoff_witness(
        witness,
        predecessor_span=source_a1["operation_span"],
        successor_span=receiver_b1["operation_span"],
    )
    if (
        verified_witness["sender_completion_frame"] != source_a1["temporal_frame"]
        or verified_witness["receiver_start_frame"] != receiver_b1["temporal_frame"]
        or witness["payload_digest"] != source["handoff_payload"]["payload_digest"]
        or witness["channel_id"] != RELAY_CHANNEL
    ):
        raise ReconstructionError("receiver witness does not bind exact A1 message and B1 frame")

    ordered_events = [events[key] for key in sorted(events)]
    pairwise = []
    counts = {status: 0 for status in ("before", "after", "equal", "concurrent", "unobserved")}
    for left, right in itertools.combinations(ordered_events, 2):
        left_frame, right_frame = left["temporal_frame"], right["temporal_frame"]
        left_causal, right_causal = left_frame["causal"], right_frame["causal"]
        causal_status = (
            "unobserved" if left_causal is None or right_causal is None
            else _vector_relation(left_causal["vector"], right_causal["vector"])
        )
        counts[causal_status] += 1
        left_mono, right_mono = left_frame["monotonic"], right_frame["monotonic"]
        local_status = (
            _ordered(left_mono["elapsed_ns"], right_mono["elapsed_ns"])
            if (left_mono["actor_id"], left_mono["segment"]) == (right_mono["actor_id"], right_mono["segment"])
            else "incomparable"
        )
        pairwise.append({
            "left_event_id": left["event_id"],
            "right_event_id": right["event_id"],
            "causal_status": causal_status,
            "causal_basis": (
                "complete E-CPU vector stamps compared componentwise"
                if causal_status != "unobserved"
                else "one or both events lack a causal stamp"
            ),
            "local_monotonic_status": local_status,
            "wall_status": "not_used",
        })

    expected = {
        ("A1", "A2"): "before",
        ("A1", "B1"): "before",
        ("A1", "C1"): "unobserved",
        ("A2", "B1"): "concurrent",
        ("A2", "C1"): "unobserved",
        ("B1", "C1"): "unobserved",
    }
    observed = {
        (item["left_event_id"], item["right_event_id"]): item["causal_status"]
        for item in pairwise
    }
    if observed != expected:
        raise ReconstructionError(f"pairwise causal matrix differs from experiment contract: {observed}")

    event_summaries = []
    local_durations = []
    wall_samples = []
    for event in ordered_events:
        frame, span = event["temporal_frame"], event["operation_span"]
        host = next(host for host in hosts[:3] if host["actor_id"] == frame["actor_id"])
        event_summaries.append({
            "event_id": event["event_id"],
            "role": host["role"],
            "actor_id": frame["actor_id"],
            "clock_segment_id": str(frame["monotonic"]["segment"]),
            "causal": frame["causal"],
            "monotonic_elapsed_ns": frame["monotonic"]["elapsed_ns"],
            "wall_utc_ns": frame["wall"]["utc_ns"],
            "configured_wall_offset_ns": WALL_OFFSETS_NS[host["role"]],
            "operation_span_digest": span["span_digest"],
            "local_elapsed_ns": span["elapsed_ns"],
        })
        local_durations.append({
            "event_id": event["event_id"],
            "actor_id": span["clock_actor_id"],
            "clock_segment_id": span["clock_segment_id"],
            "elapsed_ns": span["elapsed_ns"],
            "measurement_scope": "synchronous-callable-local-monotonic-interval",
        })
        wall_samples.append({
            "event_id": event["event_id"],
            "actor_id": frame["wall"]["actor_id"],
            "utc_ns": frame["wall"]["utc_ns"],
            "configured_offset_ns": WALL_OFFSETS_NS[host["role"]],
            "used_for_causal_order": False,
        })

    strict_before = [
        {"before": left, "after": right}
        for (left, right), status in observed.items() if status == "before"
    ]
    concurrent = [
        {"left": left, "right": right}
        for (left, right), status in observed.items() if status == "concurrent"
    ]
    unobserved = [
        {"left": left, "right": right}
        for (left, right), status in observed.items() if status == "unobserved"
    ]
    report_core = {
        "schema": REPORT_SCHEMA,
        "path_id": source["handoff_payload"]["path_id"],
        "attempt_id": source_a1["operation_span"]["attempt_id"],
        "repository": REPOSITORY,
        "run_id": source["host"]["run_id"],
        "run_attempt": source["host"]["run_attempt"],
        "workflow_ref": source["host"]["workflow_ref"],
        "workflow_sha": source["host"]["workflow_sha"],
        "hosts": [
            {
                "role": role,
                "job": record["host"]["job"],
                "actor_id": record["host"]["actor_id"],
                "runner_name": record["host"]["runner_name"],
                "runner_os": record["host"]["runner_os"],
                "runner_arch": record["host"]["runner_arch"],
                "runner_environment": record["host"]["runner_environment"],
                "record_digest": record["record_digest"],
                "record_sha256": artifact_sha256[role],
                "attestation": dict(verified_attestations[role]),
            }
            for role, record in (
                ("source_host", source), ("receiver_host", receiver), ("observer_host", observer)
            )
        ],
        "verifier": {
            "role": verifier["role"],
            "job": verifier["job"],
            "actor_id": verifier["actor_id"],
            "runner_name": verifier["runner_name"],
            "runner_os": verifier["runner_os"],
            "runner_arch": verifier["runner_arch"],
            "runner_environment": verifier["runner_environment"],
        },
        "host_separation": {
            "distinct_jobs": True,
            "distinct_temporal_actors": True,
            "all_github_hosted": True,
            "producer_host_count": 3,
            "verifier_is_fourth_job": True,
            "artifact_relay": "GitHub Actions artifact storage",
            "message_channel_id": RELAY_CHANNEL,
        },
        "event_summaries": event_summaries,
        "pairwise_relations": pairwise,
        "causal_summary": {
            "strict_before_pairs": strict_before,
            "concurrent_pairs": concurrent,
            "unobserved_pairs": unobserved,
            "pair_status_counts": counts,
            "global_total_order": None,
            "interpretation": (
                "Missing causal stamps are unobserved, not concurrent. "
                "Concurrent means two complete vector stamps are componentwise incomparable."
            ),
        },
        "duration": {
            "local_operation_durations": local_durations,
            "combined_cross_host_elapsed_ns": None,
            "combined_duration_status": "not_computed_independent_unaligned_clock_domains",
            "cpu_time_claimed": False,
        },
        "wall_clock": {
            "configured_offsets_ns": dict(WALL_OFFSETS_NS),
            "samples": wall_samples,
            "used_for_causal_order": False,
            "interpretation": (
                "Per-host wall readings use deliberately offset clock sources. "
                "They are retained but never compared to infer causal order or elapsed time."
            ),
        },
        "handoff": {
            "status": "verified_from_independently_attested_host_records",
            "predecessor_event_id": "A1",
            "successor_event_id": "B1",
            "message_sequence": witness["message_sequence"],
            "received_sequence": witness["received_sequence"],
            "handoff_digest": witness["handoff_digest"],
            "payload_digest": source["handoff_payload"]["payload_digest"],
            "predecessor_span_digest": source_a1["operation_span"]["span_digest"],
            "successor_span_digest": receiver_b1["operation_span"]["span_digest"],
        },
        "limitations": [
            "A1 to B1 is relayed through GitHub Actions artifact storage, not E-CPU SocketTransport or direct mTLS.",
            "The frames are produced by actual E-CPU TemporalContext instances. The wall source is deliberately offset and is not an unmodified OS wall-clock reading.",
            "A2 is not included in the A1 handoff. Its concurrency with B1 follows from the two complete vector stamps, not a claim of physical simultaneity.",
            "C1 omits the causal clock domain; its relation to every other event is unobserved, not concurrent.",
            "Artifact attestations authenticate exact record bytes under a workflow/ref policy, not the truth of the participant's claimed operation or physical machine identity.",
            "Distinct GitHub-hosted jobs do not prove distinct physical servers, failure domains, or administrators.",
            "Spans measure synchronous callable duration within each actor's own monotonic domain. Local durations must not be summed across hosts.",
            "No affine calibration, global wall latency, combined cross-host elapsed duration, CPU time, or network latency is inferred.",
        ],
    }
    return {**report_core, "report_digest": digest_object(report_core)}


def write_report_predicate(
    report_path: Path,
    predicate_path: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    raw_bytes = report_path.read_bytes()
    report = read_json(report_path)
    if report.get("schema") != REPORT_SCHEMA:
        raise ReconstructionError("unsupported multi-observer report schema")
    core = {key: value for key, value in report.items() if key != "report_digest"}
    if report.get("report_digest") != digest_object(core):
        raise ReconstructionError("multi-observer report digest mismatch")
    verifier = host_metadata("verifier_host", env)
    if report.get("verifier", {}).get("actor_id") != verifier["actor_id"]:
        raise ReconstructionError("report was not produced by the current verifier actor")
    predicate = {
        "schema": REPORT_PREDICATE_SCHEMA,
        "repository": verifier["repository"],
        "run_id": verifier["run_id"],
        "run_attempt": verifier["run_attempt"],
        "workflow_ref": verifier["workflow_ref"],
        "workflow_sha": verifier["workflow_sha"],
        "git_ref": verifier["git_ref"],
        "git_sha": verifier["git_sha"],
        "job": verifier["job"],
        "actor_id": verifier["actor_id"],
        "report_sha256": digest_bytes(raw_bytes),
        "report_digest": report["report_digest"],
        "producer_record_sha256": {
            host["role"]: host["record_sha256"] for host in report["hosts"]
        },
        "path_id": report["path_id"],
        "handoff_digest": report["handoff"]["handoff_digest"],
    }
    write_json(predicate_path, predicate)
    return predicate


def verify_to_report(
    source_path: Path,
    receiver_path: Path,
    observer_path: Path,
    output_path: Path,
    *,
    gh: str = "gh",
) -> dict[str, Any]:
    source = validate_record(read_json(source_path), "source_host")
    receiver = validate_record(read_json(receiver_path), "receiver_host")
    observer = validate_record(read_json(observer_path), "observer_host")
    attestations = {
        role: verify_artifact_attestation(path, record, role, gh=gh)
        for role, path, record in (
            ("source_host", source_path, source),
            ("receiver_host", receiver_path, receiver),
            ("observer_host", observer_path, observer),
        )
    }
    artifact_sha256 = {
        "source_host": sha256_file(source_path),
        "receiver_host": sha256_file(receiver_path),
        "observer_host": sha256_file(observer_path),
    }
    report = build_report(
        source, receiver, observer,
        attestations=attestations,
        artifact_sha256=artifact_sha256,
        verifier_host=host_metadata("verifier_host"),
    )
    write_json(output_path, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    source = commands.add_parser("produce-source")
    source.add_argument("--output", type=Path, required=True)

    receiver = commands.add_parser("produce-receiver")
    receiver.add_argument("--source", type=Path, required=True)
    receiver.add_argument("--output", type=Path, required=True)
    receiver.add_argument("--gh", default="gh")

    observer = commands.add_parser("produce-observer")
    observer.add_argument("--output", type=Path, required=True)

    predicate = commands.add_parser("write-record-predicate")
    predicate.add_argument("--record", type=Path, required=True)
    predicate.add_argument("--role", choices=PRODUCER_ROLES, required=True)
    predicate.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--source", type=Path, required=True)
    verify.add_argument("--receiver", type=Path, required=True)
    verify.add_argument("--observer", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument("--gh", default="gh")

    report_predicate = commands.add_parser("write-report-predicate")
    report_predicate.add_argument("--report", type=Path, required=True)
    report_predicate.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "produce-source":
            produce_source(args.output)
        elif args.command == "produce-receiver":
            produce_receiver(args.source, args.output, gh=args.gh)
        elif args.command == "produce-observer":
            produce_observer(args.output)
        elif args.command == "write-record-predicate":
            record = validate_record(read_json(args.record), args.role)
            write_json(args.output, _attestation_predicate(record))
        elif args.command == "verify":
            verify_to_report(
                args.source, args.receiver, args.observer, args.output, gh=args.gh
            )
        elif args.command == "write-report-predicate":
            write_report_predicate(args.report, args.output)
    except (ReconstructionError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"multi-observer-reconstruction: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
