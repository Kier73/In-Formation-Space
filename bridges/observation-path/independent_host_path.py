#!/usr/bin/env python3
"""Create and independently reconstruct an operation path across separate hosted VMs.

The cross-host edge is validated with the existing DOP-001 temporal-frame and
causal-handoff contracts. GitHub artifact attestations authenticate the
producing workflow identity and bind each transferred record's bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

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
WORKFLOW_PATH = ".github/workflows/independent-host-operation-path.yml"
SIGNER_WORKFLOW = f"{REPOSITORY}/{WORKFLOW_PATH}"
SOURCE_REF = "refs/heads/main"
PREDICATE_TYPE = (
    "https://kier73.github.io/in-formation-space/"
    "independent-host-operation-path/v1"
)
RECORD_FORMAT = "in-formation.independent-host-operation-record"
RECORD_SCHEMA = "in-formation.independent-host-operation-record/0.1"
PREDICATE_SCHEMA = "in-formation.independent-host-operation-predicate/0.1"
REPORT_SCHEMA = "in-formation.independent-host-operation-report/0.1"
RELAY_CHANNEL = "github-actions-artifact-relay/v1"
GH_MIN_VERSION = (2, 103, 3)


class EvidenceError(ValueError):
    """A transferred host record or independent-attestation proof is invalid."""


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EvidenceError(f"value is not canonical finite JSON: {error}") from error


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
        raise EvidenceError(f"cannot read JSON evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"evidence {path} must be one JSON object")
    return value


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"required GitHub runner environment field {name} is missing")
    return value.strip()


def host_metadata(role: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Capture the job context used by the protected, main-only workflow."""
    selected = os.environ if env is None else env
    if role not in {"source_host", "receiver_host", "verifier_host"}:
        raise EvidenceError("host role is not supported")

    repository = _required_env(selected, "GITHUB_REPOSITORY")
    job = _required_env(selected, "GITHUB_JOB")
    workflow_ref = _required_env(selected, "GITHUB_WORKFLOW_REF")
    ref = _required_env(selected, "GITHUB_REF")
    runner_environment = _required_env(selected, "RUNNER_ENVIRONMENT")

    expected_workflow_ref = (
        f"{REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}"
    )
    if repository != REPOSITORY:
        raise EvidenceError("runner repository is not the expected public repository")
    if job != role:
        raise EvidenceError(f"job id must be {role}, received {job}")
    if workflow_ref != expected_workflow_ref or ref != SOURCE_REF:
        raise EvidenceError("host evidence must be produced by this workflow on main")
    if runner_environment != "github-hosted":
        raise EvidenceError("host evidence must be produced on a GitHub-hosted runner")

    runner_name = _required_env(selected, "RUNNER_NAME")
    run_id = _required_env(selected, "GITHUB_RUN_ID")
    attempt = _required_env(selected, "GITHUB_RUN_ATTEMPT")
    actor_id = (
        f"{repository}#run-{run_id}.attempt-{attempt}."
        f"{role}.{runner_name}"
    )

    return {
        "role": role,
        "repository": repository,
        "run_id": run_id,
        "run_attempt": attempt,
        "run_number": _required_env(selected, "GITHUB_RUN_NUMBER"),
        "workflow_ref": workflow_ref,
        "workflow_sha": _required_env(selected, "GITHUB_WORKFLOW_SHA"),
        "git_ref": ref,
        "git_sha": _required_env(selected, "GITHUB_SHA"),
        "job": job,
        "runner_name": runner_name,
        "runner_os": _required_env(selected, "RUNNER_OS"),
        "runner_arch": _required_env(selected, "RUNNER_ARCH"),
        "runner_environment": runner_environment,
        "actor_id": actor_id,
        "clock_segment_id": "0",
    }


def _context_for_host(host: Mapping[str, Any]) -> TemporalContext:
    return TemporalContext(
        str(host["actor_id"]),
        TemporalProfile(
            frozenset({ClockDomain.MONOTONIC, ClockDomain.CAUSAL})
        ),
        segment=0,
    )


def _recorder(host: Mapping[str, Any], context: TemporalContext) -> OperationSpanRecorder:
    return OperationSpanRecorder(
        clock_actor_id=str(host["actor_id"]),
        clock_segment_id="0",
        clock_ns=lambda: context.monotonic_reading().elapsed_ns,
    )


def _bounded_local_work(label: str) -> str:
    """A deterministic, observable workload; no cross-host timing is implied."""
    value = label.encode("utf-8")
    for counter in range(512):
        value = hashlib.sha256(value + counter.to_bytes(4, "big")).digest()
    return value.hex()


def _seal_record(core: dict[str, Any]) -> dict[str, Any]:
    return {**core, "record_digest": digest_object(core)}


def _validate_record(document: Mapping[str, Any], expected_role: str) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise EvidenceError("host operation record must be an object")
    expected_fields = {
        "format", "schema", "role", "host", "operation_span",
        "temporal_frame", "handoff_payload", "source_record_sha256",
        "handoff_witness", "record_digest",
    }
    if set(document) != expected_fields:
        raise EvidenceError("host operation record fields are incomplete or unexpected")
    if document["format"] != RECORD_FORMAT or document["schema"] != RECORD_SCHEMA:
        raise EvidenceError("unsupported host operation record schema")
    if document["role"] != expected_role:
        raise EvidenceError(f"expected a {expected_role} record")

    core = {key: document[key] for key in expected_fields if key != "record_digest"}
    if document["record_digest"] != digest_object(core):
        raise EvidenceError("host operation record digest does not match its contents")

    host = document["host"]
    host_fields = {
        "role", "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha", "job",
        "runner_name", "runner_os", "runner_arch", "runner_environment",
        "actor_id", "clock_segment_id",
    }
    if not isinstance(host, Mapping) or set(host) != host_fields:
        raise EvidenceError("host metadata fields are incomplete or unexpected")
    if host["role"] != expected_role or host["job"] != expected_role:
        raise EvidenceError("host role and workflow job id do not agree")
    if host["repository"] != REPOSITORY:
        raise EvidenceError("host repository identity does not match")
    if host["workflow_ref"] != f"{REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}":
        raise EvidenceError("host workflow identity does not match")
    if host["git_ref"] != SOURCE_REF:
        raise EvidenceError("host source ref is not main")
    if host["runner_environment"] != "github-hosted":
        raise EvidenceError("host record does not name a GitHub-hosted runner")
    if not all(isinstance(host[key], str) and host[key] for key in host_fields):
        raise EvidenceError("host metadata must contain non-empty text fields")

    span = validate_operation_span(document["operation_span"])
    if span["clock_actor_id"] != host["actor_id"]:
        raise EvidenceError("operation span actor does not match the host actor")
    if span["clock_segment_id"] != host["clock_segment_id"]:
        raise EvidenceError("operation span segment does not match the host segment")

    frame = validate_temporal_frame(document["temporal_frame"])
    if frame["actor_id"] != host["actor_id"]:
        raise EvidenceError("temporal frame actor does not match the host actor")
    if frame["monotonic"] is None or frame["causal"] is None:
        raise EvidenceError("host temporal frame needs monotonic and causal coordinates")
    if str(frame["monotonic"]["segment"]) != host["clock_segment_id"]:
        raise EvidenceError("temporal frame clock segment does not match the host")

    if expected_role == "source_host":
        if document["source_record_sha256"] is not None or document["handoff_witness"] is not None:
            raise EvidenceError("source record must not claim a prior host artifact or receiver witness")
        payload = document["handoff_payload"]
        if not isinstance(payload, Mapping):
            raise EvidenceError("source record is missing its handoff payload")
        rebuilt = build_handoff_payload(
            path_id=str(payload.get("path_id", "")),
            attempt_id=str(payload.get("attempt_id", "")),
            predecessor_span_digest=span["span_digest"],
            sender_completion_frame=frame,
        )
        if dict(payload) != rebuilt:
            raise EvidenceError("source handoff payload cannot be independently rebuilt")
        if payload["attempt_id"] != span["attempt_id"]:
            raise EvidenceError("source handoff attempt does not match the operation span")
        if frame["monotonic"]["elapsed_ns"] < span["monotonic_end_ns"]:
            raise EvidenceError("source frame predates its measured operation completion")
    else:
        if not isinstance(document["source_record_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", document["source_record_sha256"]):
            raise EvidenceError("receiver record must bind the exact source artifact bytes")
        if document["handoff_payload"] is not None:
            raise EvidenceError("receiver stores the received payload only inside its witness")
        if not isinstance(document["handoff_witness"], Mapping):
            raise EvidenceError("receiver record is missing its causal handoff witness")
        witness = document["handoff_witness"]
        if witness.get("attempt_id") != span["attempt_id"]:
            raise EvidenceError("receiver handoff attempt does not match the operation span")
        if witness.get("successor_span_digest") != span["span_digest"]:
            raise EvidenceError("receiver handoff successor does not match the operation span")

    return dict(document)


def produce_source(output_path: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    host = host_metadata("source_host", env)
    context = _context_for_host(host)
    recorder = _recorder(host, context)
    recorder.measure(
        attempt_id=f"run-{host['run_id']}-attempt-{host['run_attempt']}",
        span_id="source-prepare",
        operation_id="host-a.prepare",
        operation=lambda: _bounded_local_work("source-host-operation"),
        context={"role": "source_host", "runner_os": host["runner_os"]},
    )
    span = recorder.spans[-1]
    context.emit_causal_stamp()
    frame = context.observe().to_dict()
    attempt_id = span["attempt_id"]
    payload = build_handoff_payload(
        path_id=f"run-{host['run_id']}-distributed-path",
        attempt_id=attempt_id,
        predecessor_span_digest=span["span_digest"],
        sender_completion_frame=frame,
    )
    record = _seal_record({
        "format": RECORD_FORMAT,
        "schema": RECORD_SCHEMA,
        "role": "source_host",
        "host": host,
        "operation_span": span,
        "temporal_frame": frame,
        "handoff_payload": payload,
        "source_record_sha256": None,
        "handoff_witness": None,
    })
    _validate_record(record, "source_host")
    write_json(output_path, record)
    return record


def produce_receiver(
    source_path: Path,
    output_path: Path,
    env: Mapping[str, str] | None = None,
    gh: str = "gh",
) -> dict[str, Any]:
    """Verify the source artifact first, then merge its causal stamp and continue."""
    source_bytes = source_path.read_bytes()
    source = read_json(source_path)
    verify_artifact_attestation(
        source_path, source, "source_host", gh=gh
    )
    source = _validate_record(source, "source_host")

    host = host_metadata("receiver_host", env)
    _validate_pair_context(source["host"], host)
    sender_frame = source["temporal_frame"]
    source_stamp = CausalStamp.from_dict(sender_frame["causal"])
    context = _context_for_host(host)
    context.receive_causal_stamp(source_stamp)
    receiver_start_frame = context.observe().to_dict()

    recorder = _recorder(host, context)
    attempt_id = source["operation_span"]["attempt_id"]
    recorder.measure(
        attempt_id=attempt_id,
        span_id="receiver-continue",
        operation_id="host-b.continue",
        operation=lambda: _bounded_local_work("receiver-host-operation"),
        context={"role": "receiver_host", "runner_os": host["runner_os"]},
    )
    successor_span = recorder.spans[-1]
    payload = source["handoff_payload"]
    witness = build_causal_handoff_witness(
        payload=payload,
        successor_span_digest=successor_span["span_digest"],
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
        "operation_span": successor_span,
        "temporal_frame": receiver_start_frame,
        "handoff_payload": None,
        "source_record_sha256": digest_bytes(source_bytes),
        "handoff_witness": witness,
    })
    _validate_record(record, "receiver_host")
    write_json(output_path, record)
    return record


def _validate_pair_context(source_host: Mapping[str, Any], receiver_host: Mapping[str, Any]) -> None:
    if source_host["role"] != "source_host" or receiver_host["role"] != "receiver_host":
        raise EvidenceError("host pair roles are invalid")
    shared_fields = (
        "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha",
    )
    for field in shared_fields:
        if source_host[field] != receiver_host[field]:
            raise EvidenceError(f"source and receiver differ in shared run field {field}")
    if source_host["job"] == receiver_host["job"]:
        raise EvidenceError("causal handoff jobs must be distinct")
    if source_host["actor_id"] == receiver_host["actor_id"]:
        raise EvidenceError("causal handoff actors must be distinct")
    if source_host["runner_environment"] != "github-hosted" or receiver_host["runner_environment"] != "github-hosted":
        raise EvidenceError("both operation records must come from GitHub-hosted runners")


def _validate_verifier_context(
    source_host: Mapping[str, Any],
    receiver_host: Mapping[str, Any],
    verifier_host: Mapping[str, Any],
) -> None:
    _validate_pair_context(source_host, receiver_host)
    host_fields = {
        "role", "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha", "job",
        "runner_name", "runner_os", "runner_arch", "runner_environment",
        "actor_id", "clock_segment_id",
    }
    if not isinstance(verifier_host, Mapping) or set(verifier_host) != host_fields:
        raise EvidenceError("independent verifier host metadata is incomplete or unexpected")
    if not all(isinstance(verifier_host[key], str) and verifier_host[key] for key in host_fields):
        raise EvidenceError("independent verifier host metadata must be non-empty text")
    if verifier_host.get("role") != "verifier_host" or verifier_host.get("job") != "verifier_host":
        raise EvidenceError("independent verifier must run in the verifier_host job")
    shared_fields = (
        "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha",
    )
    for field in shared_fields:
        if source_host[field] != verifier_host[field]:
            raise EvidenceError(f"verifier differs from host records in shared run field {field}")
    actors = {
        source_host["actor_id"],
        receiver_host["actor_id"],
        verifier_host["actor_id"],
    }
    jobs = {
        source_host["job"],
        receiver_host["job"],
        verifier_host["job"],
    }
    if len(actors) != 3 or len(jobs) != 3:
        raise EvidenceError("source, receiver, and verifier must be three distinct job actors")
    if any(host.get("runner_environment") != "github-hosted" for host in (source_host, receiver_host, verifier_host)):
        raise EvidenceError("all three roles must use GitHub-hosted runners")


def _gh_version(gh: str) -> tuple[int, int, int]:
    result = subprocess.run([gh, "--version"], check=True, capture_output=True, text=True)
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match:
        raise EvidenceError("cannot parse GitHub CLI version")
    return tuple(int(part) for part in match.groups())


def _attestation_command(path: Path, gh: str) -> list[str]:
    return [
        gh, "attestation", "verify", str(path),
        "--repo", REPOSITORY,
        "--predicate-type", PREDICATE_TYPE,
        "--signer-workflow", SIGNER_WORKFLOW,
        "--source-ref", SOURCE_REF,
        "--deny-self-hosted-runners",
        "--format", "json",
    ]


def _predicate_for(record: Mapping[str, Any]) -> dict[str, Any]:
    host = record["host"]
    return {
        "schema": PREDICATE_SCHEMA,
        "role": record["role"],
        "repository": host["repository"],
        "run_id": host["run_id"],
        "run_attempt": host["run_attempt"],
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
        "source_record_sha256": record["source_record_sha256"],
        "path_id": (
            record["handoff_witness"]["path_id"]
            if record["role"] == "receiver_host"
            else record["handoff_payload"]["path_id"]
        ),
    }


def write_predicate(record_path: Path, output_path: Path, role: str) -> dict[str, Any]:
    record = _validate_record(read_json(record_path), role)
    predicate = _predicate_for(record)
    write_json(output_path, predicate)
    return predicate


def _extract_statement(results: Any, artifact_digest: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(results, list):
        raise EvidenceError("GitHub CLI attestation output must be a JSON array")
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        verified = item.get("verificationResult")
        if not isinstance(verified, Mapping):
            continue
        statement = verified.get("statement")
        if not isinstance(statement, Mapping):
            continue
        subject_match = False
        for subject in statement.get("subject", []):
            if not isinstance(subject, Mapping):
                continue
            digests = subject.get("digest")
            if isinstance(digests, Mapping) and digests.get("sha256") == artifact_digest:
                subject_match = True
        if subject_match:
            matches.append((dict(statement), dict(verified)))
    if not matches:
        raise EvidenceError("no verified attestation subject matches the exact artifact bytes")
    # Several valid attestations may exist for the same digest; every matching
    # statement must have the required pinned type and protected-run metadata.
    for statement, _verified in matches:
        if statement.get("predicateType") != PREDICATE_TYPE:
            raise EvidenceError("verified statement has an unexpected predicate type")
    return matches[0]


def verify_artifact_attestation(
    artifact_path: Path,
    record: Mapping[str, Any],
    expected_role: str,
    *,
    gh: str = "gh",
) -> dict[str, Any]:
    """Require a fresh, cryptographically verified Sigstore attestation for the bytes."""
    if _gh_version(gh) < GH_MIN_VERSION:
        raise EvidenceError(
            "GitHub CLI 2.103.3 or newer is required for exact signer-policy verification"
        )
    artifact_digest = sha256_file(artifact_path)
    try:
        completed = subprocess.run(
            _attestation_command(artifact_path, gh),
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        results = json.loads(completed.stdout)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() if error.stderr else str(error)
        raise EvidenceError(f"GitHub artifact attestation verification failed: {detail}") from error
    except json.JSONDecodeError as error:
        raise EvidenceError("GitHub CLI did not return valid attestation JSON") from error

    statement, verified = _extract_statement(results, artifact_digest)
    predicate = statement.get("predicate")
    expected_predicate = _predicate_for(record)
    if not isinstance(predicate, Mapping) or dict(predicate) != expected_predicate:
        raise EvidenceError("signed attestation predicate does not match this host record")
    if record["role"] != expected_role:
        raise EvidenceError("record role does not match requested attestation role")

    verification_signature = verified.get("signature")
    certificate_present = (
        isinstance(verification_signature, Mapping)
        and isinstance(verification_signature.get("certificate"), Mapping)
    )
    timestamps = verified.get("verifiedTimestamps", [])
    if not certificate_present:
        raise EvidenceError("verified artifact attestation is missing its signing certificate")
    return {
        "verified": True,
        "subject_sha256": artifact_digest,
        "predicate_type": PREDICATE_TYPE,
        "signer_workflow": SIGNER_WORKFLOW,
        "source_ref": SOURCE_REF,
        "self_hosted_runners_denied": True,
        "verified_signature_certificate_present": certificate_present,
        "verified_timestamp_count": len(timestamps) if isinstance(timestamps, list) else 0,
    }


def _validate_attestation_summary(summary: Mapping[str, Any], expected_digest: str) -> dict[str, Any]:
    required = {
        "verified", "subject_sha256", "predicate_type", "signer_workflow",
        "source_ref", "self_hosted_runners_denied",
        "verified_signature_certificate_present", "verified_timestamp_count",
    }
    if not isinstance(summary, Mapping) or set(summary) != required:
        raise EvidenceError("attestation verification summary fields are incomplete or unexpected")
    if summary["verified"] is not True or summary["subject_sha256"] != expected_digest:
        raise EvidenceError("attestation summary does not verify the expected artifact digest")
    if summary["predicate_type"] != PREDICATE_TYPE:
        raise EvidenceError("attestation summary uses an unexpected predicate type")
    if summary["signer_workflow"] != SIGNER_WORKFLOW or summary["source_ref"] != SOURCE_REF:
        raise EvidenceError("attestation summary does not pin the protected main workflow")
    if summary["self_hosted_runners_denied"] is not True:
        raise EvidenceError("attestation summary did not deny self-hosted runners")
    if summary["verified_signature_certificate_present"] is not True:
        raise EvidenceError("attestation summary has no verified signing certificate")
    if isinstance(summary["verified_timestamp_count"], bool) or not isinstance(summary["verified_timestamp_count"], int) or summary["verified_timestamp_count"] < 0:
        raise EvidenceError("attestation timestamp count is invalid")
    return dict(summary)


def build_report(
    source: Mapping[str, Any],
    receiver: Mapping[str, Any],
    *,
    source_attestation: Mapping[str, Any],
    receiver_attestation: Mapping[str, Any],
    receiver_artifact_sha256: str,
    verifier_host: Mapping[str, Any],
) -> dict[str, Any]:
    source = _validate_record(source, "source_host")
    receiver = _validate_record(receiver, "receiver_host")
    _validate_verifier_context(source["host"], receiver["host"], verifier_host)
    source_attestation = _validate_attestation_summary(
        source_attestation, str(receiver["source_record_sha256"])
    )
    receiver_attestation = _validate_attestation_summary(
        receiver_attestation, receiver_artifact_sha256
    )

    if receiver["source_record_sha256"] != source_attestation["subject_sha256"]:
        raise EvidenceError("receiver did not bind the exact attested source artifact")
    payload = source["handoff_payload"]
    witness = receiver["handoff_witness"]
    successor = receiver["operation_span"]
    predecessor = source["operation_span"]
    if receiver["temporal_frame"] != witness["receiver_start_frame"]:
        raise EvidenceError("receiver start frame differs from the witnessed frame")
    if witness["path_id"] != payload["path_id"] or witness["attempt_id"] != payload["attempt_id"]:
        raise EvidenceError("causal handoff belongs to another path or attempt")

    verified_witness = validate_causal_handoff_witness(
        witness,
        predecessor_span=predecessor,
        successor_span=successor,
    )
    if (
        verified_witness["payload_digest"] != payload["payload_digest"]
        or verified_witness["sender_completion_frame"] != source["temporal_frame"]
    ):
        raise EvidenceError("causal handoff witness does not bind the exact source payload")

    source_elapsed = predecessor["elapsed_ns"]
    receiver_elapsed = successor["elapsed_ns"]
    report_core = {
        "schema": REPORT_SCHEMA,
        "path_id": payload["path_id"],
        "attempt_id": payload["attempt_id"],
        "repository": source["host"]["repository"],
        "run_id": source["host"]["run_id"],
        "run_attempt": source["host"]["run_attempt"],
        "workflow_ref": source["host"]["workflow_ref"],
        "workflow_sha": source["host"]["workflow_sha"],
        "source": {
            "job": source["host"]["job"],
            "actor_id": source["host"]["actor_id"],
            "runner_name": source["host"]["runner_name"],
            "runner_os": source["host"]["runner_os"],
            "runner_arch": source["host"]["runner_arch"],
            "local_elapsed_ns": source_elapsed,
            "span_digest": predecessor["span_digest"],
            "record_digest": source["record_digest"],
            "attestation": dict(source_attestation),
        },
        "receiver": {
            "job": receiver["host"]["job"],
            "actor_id": receiver["host"]["actor_id"],
            "runner_name": receiver["host"]["runner_name"],
            "runner_os": receiver["host"]["runner_os"],
            "runner_arch": receiver["host"]["runner_arch"],
            "local_elapsed_ns": receiver_elapsed,
            "span_digest": successor["span_digest"],
            "record_digest": receiver["record_digest"],
            "source_artifact_sha256": receiver["source_record_sha256"],
            "attestation": dict(receiver_attestation),
        },
        "verifier": {
            "role": verifier_host["role"],
            "job": verifier_host["job"],
            "actor_id": verifier_host["actor_id"],
            "runner_name": verifier_host["runner_name"],
            "runner_os": verifier_host["runner_os"],
            "runner_arch": verifier_host["runner_arch"],
            "runner_environment": verifier_host["runner_environment"],
        },
        "host_separation": {
            "distinct_jobs": len({source["host"]["job"], receiver["host"]["job"], verifier_host["job"]}) == 3,
            "distinct_temporal_actors": len({source["host"]["actor_id"], receiver["host"]["actor_id"], verifier_host["actor_id"]}) == 3,
            "both_github_hosted": all(host["runner_environment"] == "github-hosted" for host in (source["host"], receiver["host"], verifier_host)),
            "verification_host_is_third_job": verifier_host["job"] not in {source["host"]["job"], receiver["host"]["job"]},
            "cross_os": source["host"]["runner_os"] != receiver["host"]["runner_os"],
            "artifact_relay": "GitHub Actions artifact storage",
            "relay_channel_id": RELAY_CHANNEL,
        },
        "causal_reconstruction": {
            "status": "verified_from_independent_attested_host_records",
            "edge_count": 1,
            "edge_basis": "E-CPU vector-clock handoff plus local monotonic endpoint checks",
            "sender_vector": witness["sender_completion_frame"]["causal"]["vector"],
            "receiver_vector": witness["receiver_start_frame"]["causal"]["vector"],
            "sender_lamport": witness["sender_completion_frame"]["causal"]["lamport"],
            "receiver_lamport": witness["receiver_start_frame"]["causal"]["lamport"],
            "predecessor_span_digest": predecessor["span_digest"],
            "successor_span_digest": successor["span_digest"],
            "handoff_digest": witness["handoff_digest"],
            "topological_order": [predecessor["span_digest"], successor["span_digest"]],
        },
        "duration": {
            "source_local_elapsed_ns": source_elapsed,
            "receiver_local_elapsed_ns": receiver_elapsed,
            "combined_cross_host_elapsed_ns": None,
            "status": "not_computed_independent_unaligned_clock_domains",
        },
        "limitations": [
            "The artifact relay is GitHub Actions storage; this run does not exercise E-CPU SocketTransport or a direct worker-to-worker TCP session.",
            "The attestation authenticates the repository, protected main workflow identity, and artifact digest. Runner name, operating-system, architecture, and actor labels are workflow predicate data, not hardware attestations.",
            "Separate standard GitHub-hosted jobs run in separate hosted runner VMs, but this does not prove distinct physical servers, regions, power supplies, or administrative fault domains.",
            "Causal order is reconstructed from the supplied E-CPU vector clocks and endpoint constraints. A malicious host can still lie about the local operation it claims to have performed.",
            "The trust base includes GitHub's runner isolation, OIDC/Sigstore attestation service, the protected main branch workflow, and the GitHub artifact relay.",
            "Each span is a synchronous local callable duration, not CPU time. No global elapsed time or cross-host latency is inferred.",
        ],
    }
    return {**report_core, "report_digest": digest_object(report_core)}


def verify_to_report(
    source_path: Path,
    receiver_path: Path,
    output_path: Path,
    gh: str = "gh",
) -> dict[str, Any]:
    source = read_json(source_path)
    receiver = read_json(receiver_path)
    source = _validate_record(source, "source_host")
    receiver = _validate_record(receiver, "receiver_host")
    source_attestation = verify_artifact_attestation(
        source_path, source, "source_host", gh=gh
    )
    receiver_attestation = verify_artifact_attestation(
        receiver_path, receiver, "receiver_host", gh=gh
    )
    verifier_host = host_metadata("verifier_host")
    report = build_report(
        source,
        receiver,
        source_attestation=source_attestation,
        receiver_attestation=receiver_attestation,
        receiver_artifact_sha256=sha256_file(receiver_path),
        verifier_host=verifier_host,
    )
    write_json(output_path, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    source_parser = commands.add_parser("produce-source")
    source_parser.add_argument("--output", type=Path, required=True)

    receiver_parser = commands.add_parser("produce-receiver")
    receiver_parser.add_argument("--source", type=Path, required=True)
    receiver_parser.add_argument("--output", type=Path, required=True)
    receiver_parser.add_argument("--gh", default="gh")

    predicate_parser = commands.add_parser("write-predicate")
    predicate_parser.add_argument("--record", type=Path, required=True)
    predicate_parser.add_argument("--role", choices=("source_host", "receiver_host"), required=True)
    predicate_parser.add_argument("--output", type=Path, required=True)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--source", type=Path, required=True)
    verify_parser.add_argument("--receiver", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--gh", default="gh")

    args = parser.parse_args(argv)
    try:
        if args.command == "produce-source":
            produce_source(args.output)
        elif args.command == "produce-receiver":
            produce_receiver(args.source, args.output, gh=args.gh)
        elif args.command == "write-predicate":
            write_predicate(args.record, args.output, args.role)
        elif args.command == "verify":
            verify_to_report(args.source, args.receiver, args.output, gh=args.gh)
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"independent-host-path: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
