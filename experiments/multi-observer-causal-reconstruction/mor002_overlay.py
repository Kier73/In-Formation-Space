#!/usr/bin/env python3
"""MOR-002: independent reconstruction of the IHP-006 E-CPU Tailscale handoff.

The A1 semantic payload is sent only through E-CPU SocketTransport/ReliableChannel
over mTLS on the ephemeral tailnet. GitHub artifacts carry bootstrap and evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
OBSERVATION = ROOT / "bridges" / "observation-path"
ECPU = ROOT / "external" / "E-CPU"
for item in (str(OBSERVATION), str(ECPU)):
    if item not in sys.path:
        sys.path.insert(0, item)

import direct_mtls_operation_path as direct
from mailcpu.temporal import ClockDomain, TemporalContext, TemporalProfile
from operation_spans import OperationSpanRecorder, validate_operation_span
from temporal_provenance import validate_temporal_frame

REPOSITORY = direct.REPOSITORY
WORKFLOW_PATH = direct.MOR002_WORKFLOW_PATH
SOURCE_REF = direct.SOURCE_REF
EVENT_SCHEMA = "in-formation.mor002-event-record/0.1"
FOLLOWUP_SCHEMA = "in-formation.mor002-source-followup/0.1"
EVENT_PREDICATE_SCHEMA = "in-formation.mor002-event-predicate/0.1"
FOLLOWUP_PREDICATE_SCHEMA = "in-formation.mor002-followup-predicate/0.1"
REPORT_SCHEMA = "in-formation.mor002-overlay-causal-report/0.1"
REPORT_PREDICATE_SCHEMA = "in-formation.mor002-overlay-report-predicate/0.1"
EVENT_PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/mor002-event-record/v1"
FOLLOWUP_PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/mor002-source-followup/v1"
REPORT_PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/mor002-overlay-causal-report/v1"


class MOR002Error(ValueError):
    """A MOR-002 identity, evidence, signature, or causal reconstruction is invalid."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MOR002Error(f"cannot read JSON evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise MOR002Error(f"evidence {path} must be a JSON object")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    direct.write_json(path, dict(value), durable=True)


def _seal(core: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(core)
    return {**payload, "record_digest": direct.digest_object(payload)}


def _check_run(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    direct._require_run_match(left, right)
    if left["job"] == right["job"] or left["actor_id"] == right["actor_id"]:
        raise MOR002Error("MOR-002 participants must use distinct workflow jobs and actors")


def _validate_event_record(record: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"schema", "role", "event_id", "host", "temporal_frame", "operation_span", "record_digest"}
    if not isinstance(record, Mapping) or set(record) != fields:
        raise MOR002Error("observer event record fields are incomplete or unexpected")
    if record["schema"] != EVENT_SCHEMA or record["role"] != "observer_host" or record["event_id"] != "C1":
        raise MOR002Error("observer record must describe the declared C1 event")
    core = {key: value for key, value in record.items() if key != "record_digest"}
    if record["record_digest"] != direct.digest_object(core):
        raise MOR002Error("observer record digest does not match its exact fields")
    host = direct._validate_host_metadata(record["host"], "observer_host")
    frame = validate_temporal_frame(record["temporal_frame"])
    span = validate_operation_span(record["operation_span"])
    if frame["actor_id"] != host["actor_id"] or frame["causal"] is not None:
        raise MOR002Error("C1 must belong to its observer and omit the causal clock")
    if frame["monotonic"] is None or frame["monotonic"]["actor_id"] != host["actor_id"]:
        raise MOR002Error("C1 must retain its observer-local monotonic coordinate")
    if span["clock_actor_id"] != host["actor_id"]:
        raise MOR002Error("C1 operation span belongs to another actor")
    return dict(record)


def produce_observer(output: Path) -> dict[str, Any]:
    host = direct.host_metadata("observer_host")
    context = TemporalContext(
        host["actor_id"],
        TemporalProfile(frozenset({ClockDomain.MONOTONIC})),
        segment=0,
    )
    recorder = OperationSpanRecorder(
        clock_actor_id=host["actor_id"],
        clock_segment_id="0",
        clock_ns=lambda: context.monotonic_reading().elapsed_ns,
    )
    attempt = f"run-{host['run_id']}-attempt-{host['run_attempt']}"
    recorder.measure(
        attempt_id=attempt,
        span_id="mor002-observer-C1",
        operation_id="mor002.observer.C1",
        operation=lambda: hashlib.sha256(b"mor002-independent-observation").hexdigest(),
        context={"event_id": "C1", "role": "observer_host", "causal_clock_enabled": False},
    )
    record = _seal({
        "schema": EVENT_SCHEMA,
        "role": "observer_host",
        "event_id": "C1",
        "host": host,
        "temporal_frame": context.observe().to_dict(),
        "operation_span": recorder.spans[-1],
    })
    _validate_event_record(record)
    _write(output, record)
    return record


def write_observer_predicate(record_path: Path, predicate_path: Path) -> dict[str, Any]:
    record = _validate_event_record(_read(record_path))
    host = record["host"]
    if host != direct.host_metadata("observer_host"):
        raise MOR002Error("observer record identity differs from the current observer runner")
    predicate = {
        "schema": EVENT_PREDICATE_SCHEMA,
        "role": "observer_host",
        "event_id": "C1",
        "repository": host["repository"],
        "run_id": host["run_id"],
        "run_attempt": host["run_attempt"],
        "workflow_ref": host["workflow_ref"],
        "workflow_sha": host["workflow_sha"],
        "git_ref": host["git_ref"],
        "git_sha": host["git_sha"],
        "job": host["job"],
        "actor_id": host["actor_id"],
        "record_sha256": direct.file_digest(record_path),
        "record_digest": record["record_digest"],
        "causal_stamp_present": False,
    }
    _write(predicate_path, predicate)
    return predicate


def write_followup_predicate(record_path: Path, predicate_path: Path) -> dict[str, Any]:
    signed = _read(record_path)
    core = signed.get("core")
    if not isinstance(core, Mapping) or set(signed) != {"core", "signature", "signed_digest"}:
        raise MOR002Error("source follow-up must be a signed document")
    if signed["signed_digest"] != direct.digest_object(core):
        raise MOR002Error("source follow-up signed digest mismatch")
    host = direct._validate_host_metadata(core.get("host"), "client_host")
    if host != direct.host_metadata("client_host"):
        raise MOR002Error("source follow-up host identity differs from the current client runner")
    expected = {
        "schema", "event_id", "predecessor_event_id", "path_id", "attempt_id",
        "host", "predecessor_span_digest", "predecessor_frame",
        "handoff_envelope_digest", "operation_span", "temporal_frame",
        "transferred_in_handoff",
    }
    if set(core) != expected or core["schema"] != FOLLOWUP_SCHEMA:
        raise MOR002Error("source follow-up core fields are invalid")
    if core["event_id"] != "A2" or core["predecessor_event_id"] != "A1" or core["transferred_in_handoff"] is not False:
        raise MOR002Error("source follow-up must be A2 and remain outside the A1 handoff")
    predicate = {
        "schema": FOLLOWUP_PREDICATE_SCHEMA,
        "role": "client_host",
        "event_id": "A2",
        "repository": host["repository"],
        "run_id": host["run_id"],
        "run_attempt": host["run_attempt"],
        "workflow_ref": host["workflow_ref"],
        "workflow_sha": host["workflow_sha"],
        "git_ref": host["git_ref"],
        "git_sha": host["git_sha"],
        "job": host["job"],
        "actor_id": host["actor_id"],
        "record_sha256": direct.file_digest(record_path),
        "signed_digest": signed["signed_digest"],
        "handoff_envelope_digest": core["handoff_envelope_digest"],
        "transferred_in_handoff": False,
    }
    _write(predicate_path, predicate)
    return predicate


def _validate_predicate(summary: Mapping[str, Any], *, expected_sha: str, expected_type: str) -> dict[str, Any]:
    if (
        summary.get("verified") is not True
        or summary.get("subject_sha256") != expected_sha
        or summary.get("predicate_type") != expected_type
        or summary.get("signer_workflow") != f"{REPOSITORY}/{WORKFLOW_PATH}"
        or summary.get("source_ref") != SOURCE_REF
        or summary.get("self_hosted_runners_denied") is not True
    ):
        raise MOR002Error("verified artifact attestation does not bind the expected MOR-002 bytes and workflow")
    return dict(summary)


def _vector(frame: Mapping[str, Any], actor_ids: set[str], event_id: str) -> dict[str, int]:
    causal = frame.get("causal")
    if not isinstance(causal, Mapping):
        raise MOR002Error(f"{event_id} must carry a complete causal stamp")
    stamp = direct.CausalStamp.from_dict(causal)
    vector = stamp.vector_map()
    if not set(vector).issubset(actor_ids) or stamp.actor_id != frame["actor_id"]:
        raise MOR002Error(f"{event_id} vector contains an unknown actor or mismatched stamp identity")
    # E-CPU uses sparse vector clocks: an actor not yet observed is represented by zero.
    return vector


def _relation(left: Mapping[str, int], right: Mapping[str, int]) -> str:
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


def _event(event_id: str, role: str, host: Mapping[str, Any], frame: Mapping[str, Any], span: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "role": role,
        "actor_id": host["actor_id"],
        "temporal_frame": dict(frame),
        "operation_span": dict(span),
    }


def build_report(
    *,
    direct_report: Mapping[str, Any],
    client_record: Mapping[str, Any],
    server_record: Mapping[str, Any],
    client_cert_path: Path,
    followup_signed: Mapping[str, Any],
    followup_attestation: Mapping[str, Any],
    observer_record: Mapping[str, Any],
    observer_attestation: Mapping[str, Any],
    followup_sha256: str,
    observer_sha256: str,
    verifier_host: Mapping[str, Any],
) -> dict[str, Any]:
    client = direct._validate_record(client_record, "client_host")
    server = direct._validate_record(server_record, "server_host")
    observer = _validate_event_record(observer_record)
    verifier = direct._validate_host_metadata(verifier_host, "verifier_host")
    for host in (server["host"], observer["host"], verifier):
        _check_run(client["host"], host)
    if len({client["host"]["actor_id"], server["host"]["actor_id"], observer["host"]["actor_id"], verifier["actor_id"]}) != 4:
        raise MOR002Error("three event producers and independent verifier must be four distinct actors")

    followup_core = direct._verify_signed_document(followup_signed, client_cert_path)
    expected_followup = {
        "schema", "event_id", "predecessor_event_id", "path_id", "attempt_id",
        "host", "predecessor_span_digest", "predecessor_frame",
        "handoff_envelope_digest", "operation_span", "temporal_frame",
        "transferred_in_handoff",
    }
    if set(followup_core) != expected_followup or followup_core["schema"] != FOLLOWUP_SCHEMA:
        raise MOR002Error("signed A2 source follow-up fields or schema are invalid")
    followup_host = direct._validate_host_metadata(followup_core["host"], "client_host")
    if followup_host != client["host"]:
        raise MOR002Error("A2 sidecar is not bound to the actual client host identity")
    _check_run(client["host"], observer["host"])
    if followup_core["event_id"] != "A2" or followup_core["predecessor_event_id"] != "A1":
        raise MOR002Error("source-local follow-up event identity is invalid")
    if followup_core["transferred_in_handoff"] is not False:
        raise MOR002Error("A2 must not be transferred in the semantic A1 envelope")
    if direct_report.get("status") != "direct_mtls_verified":
        unavailable_core = {
            "schema": REPORT_SCHEMA,
            "status": "direct_transport_unavailable",
            "path_id": direct_report.get("path_id"),
            "run_id": client["host"]["run_id"],
            "run_attempt": client["host"]["run_attempt"],
            "direct_transport_report_digest": direct_report.get("report_digest"),
            "direct_transport_status": direct_report.get("status"),
            "event_observations": {
                "A1": client.get("temporal_frame"),
                "A2": followup_core["temporal_frame"],
                "B1": server.get("temporal_frame"),
                "C1": observer["temporal_frame"],
            },
            "causal_reconstruction": None,
            "duration": {
                "combined_cross_host_elapsed_ns": None,
                "status": "not_computed_independent_unaligned_clock_domains",
            },
            "limitations": [
                "The direct Tailscale mTLS ReliableChannel exchange did not complete; no A1-to-B1 causal handoff is claimed.",
                "A1, A2, B1, and C1 are only compared when both endpoints have complete causal stamps and a verified transport receipt.",
                "GitHub-hosted runner identity does not prove distinct physical servers or independent failure domains.",
            ],
        }
        return {**unavailable_core, "report_digest": direct.digest_object(unavailable_core)}

    if not isinstance(client.get("handoff_envelope"), Mapping):
        raise MOR002Error("verified client record is missing the signed A1 envelope")
    envelope = client["handoff_envelope"]
    envelope_core = direct._verify_handoff_envelope(envelope, client_cert_path, expected_sequence=1)
    if server.get("received_envelope") != envelope:
        raise MOR002Error("server did not receive the exact client A1 envelope")
    if followup_core["path_id"] != direct_report["path_id"] or followup_core["attempt_id"] != envelope_core["attempt_id"]:
        raise MOR002Error("A2 sidecar path or attempt differs from the direct handoff")
    if followup_core["predecessor_span_digest"] != envelope_core["operation_span"]["span_digest"]:
        raise MOR002Error("A2 does not identify the exact A1 predecessor span")
    if followup_core["predecessor_frame"] != envelope_core["sender_completion_frame"]:
        raise MOR002Error("A2 predecessor frame differs from the exact signed A1 frame")
    if followup_core["handoff_envelope_digest"] != envelope["signed_digest"]:
        raise MOR002Error("A2 sidecar is not bound to the actual signed A1 envelope")
    a2_span = validate_operation_span(followup_core["operation_span"])
    a2_frame = validate_temporal_frame(followup_core["temporal_frame"])
    a1_span = validate_operation_span(envelope_core["operation_span"])
    a1_frame = validate_temporal_frame(envelope_core["sender_completion_frame"])
    b1_span = validate_operation_span(server["operation_span"])
    b1_frame = validate_temporal_frame(server["temporal_frame"])
    c1_span = validate_operation_span(observer["operation_span"])
    c1_frame = validate_temporal_frame(observer["temporal_frame"])
    if (
        a2_span["clock_actor_id"] != client["host"]["actor_id"]
        or a2_frame["actor_id"] != client["host"]["actor_id"]
        or a2_span["attempt_id"] != a1_span["attempt_id"]
        or a2_frame["monotonic"]["elapsed_ns"] < a2_span["monotonic_end_ns"]
        or a2_span["monotonic_start_ns"] < a1_frame["monotonic"]["elapsed_ns"]
    ):
        raise MOR002Error("A2 is not a later source-local event in the same monotonic segment")
    if c1_frame["causal"] is not None:
        raise MOR002Error("C1 observer unexpectedly has a causal stamp")

    actors = {client["host"]["actor_id"], server["host"]["actor_id"]}
    vectors = {
        "A1": _vector(a1_frame, actors, "A1"),
        "A2": _vector(a2_frame, actors, "A2"),
        "B1": _vector(b1_frame, actors, "B1"),
    }
    expected = {
        ("A1", "A2"): "before",
        ("A1", "B1"): "before",
        ("A1", "C1"): "unobserved",
        ("A2", "B1"): "concurrent",
        ("A2", "C1"): "unobserved",
        ("B1", "C1"): "unobserved",
    }
    events = {
        "A1": _event("A1", "client_host", client["host"], a1_frame, a1_span),
        "A2": _event("A2", "client_host", client["host"], a2_frame, a2_span),
        "B1": _event("B1", "server_host", server["host"], b1_frame, b1_span),
        "C1": _event("C1", "observer_host", observer["host"], c1_frame, c1_span),
    }
    pairwise = []
    for left_id, right_id in itertools.combinations(("A1", "A2", "B1", "C1"), 2):
        status = "unobserved" if "C1" in {left_id, right_id} else _relation(vectors[left_id], vectors[right_id])
        pairwise.append({
            "left_event_id": left_id,
            "right_event_id": right_id,
            "causal_status": status,
            "causal_basis": "componentwise comparison of complete E-CPU vector stamps" if status != "unobserved" else "C1 omits the causal clock domain",
        })
    observed = {(item["left_event_id"], item["right_event_id"]): item["causal_status"] for item in pairwise}
    if observed != expected:
        raise MOR002Error(f"MOR-002 event graph differs from the MOR-001 invariant: {observed}")

    route_pair = direct_report.get("direct_transport", {}).get("peer_route_observations")
    if not isinstance(route_pair, Mapping):
        raise MOR002Error("successful Tailscale handoff report is missing reciprocal peer-route observations")
    if (
        route_pair.get("client", {}).get("peer_overlay_ipv4") != route_pair.get("server", {}).get("local_overlay_ipv4")
        or route_pair.get("server", {}).get("peer_overlay_ipv4") != route_pair.get("client", {}).get("local_overlay_ipv4")
    ):
        raise MOR002Error("route observations do not identify reciprocal socket endpoints")
    followup_verified = _validate_predicate(
        followup_attestation, expected_sha=followup_sha256, expected_type=FOLLOWUP_PREDICATE_TYPE
    )
    observer_verified = _validate_predicate(
        observer_attestation, expected_sha=observer_sha256, expected_type=EVENT_PREDICATE_TYPE
    )

    counts = {status: sum(1 for pair in pairwise if pair["causal_status"] == status)
              for status in ("before", "after", "equal", "concurrent", "unobserved")}
    before = [{"before": left, "after": right} for (left, right), status in observed.items() if status == "before"]
    concurrent = [{"left": left, "right": right} for (left, right), status in observed.items() if status == "concurrent"]
    unobserved = [{"left": left, "right": right} for (left, right), status in observed.items() if status == "unobserved"]
    summaries = []
    durations = []
    for event_id in ("A1", "A2", "B1", "C1"):
        event = events[event_id]
        frame, span = event["temporal_frame"], event["operation_span"]
        summaries.append({
            "event_id": event_id,
            "role": event["role"],
            "actor_id": event["actor_id"],
            "causal": frame["causal"],
            "monotonic_elapsed_ns": frame["monotonic"]["elapsed_ns"],
            "operation_span_digest": span["span_digest"],
            "local_elapsed_ns": span["elapsed_ns"],
        })
        durations.append({
            "event_id": event_id,
            "actor_id": span["clock_actor_id"],
            "clock_segment_id": span["clock_segment_id"],
            "elapsed_ns": span["elapsed_ns"],
            "measurement_scope": "synchronous-callable-local-monotonic-interval",
        })

    report_core = {
        "schema": REPORT_SCHEMA,
        "status": "direct_mtls_verified",
        "path_id": direct_report["path_id"],
        "run_id": client["host"]["run_id"],
        "run_attempt": client["host"]["run_attempt"],
        "workflow_ref": client["host"]["workflow_ref"],
        "direct_transport_report_digest": direct_report["report_digest"],
        "hosts": {
            "client": {
                "actor_id": client["host"]["actor_id"],
                "runner_name": client["host"]["runner_name"],
                "record_digest": client["record_digest"],
                "tls_peer_certificate_sha256": client["peer_certificate_sha256"],
                "attestation": direct_report["client"]["record_attestation"],
            },
            "server": {
                "actor_id": server["host"]["actor_id"],
                "runner_name": server["host"]["runner_name"],
                "record_digest": server["record_digest"],
                "tls_peer_certificate_sha256": server["peer_certificate_sha256"],
                "attestation": direct_report["server"]["record_attestation"],
            },
            "observer": {
                "actor_id": observer["host"]["actor_id"],
                "runner_name": observer["host"]["runner_name"],
                "record_digest": observer["record_digest"],
                "record_sha256": observer_sha256,
                "attestation": observer_verified,
            },
            "verifier": {
                "actor_id": verifier["actor_id"],
                "runner_name": verifier["runner_name"],
            },
        },
        "transport": {
            "substrate": "E-CPU SocketTransport over Tailscale and mutually authenticated TLS",
            "data_channel": direct.DATA_CHANNEL,
            "receipt_channel": direct.RECEIPT_CHANNEL,
            "message_sequence": 1,
            "receipt_sequence": 1,
            "semantic_payload_relayed_by_artifact_store": False,
            "artifact_store_scope": "public certificates, signed endpoint bootstrap, and attested evidence only",
            "peer_route_observations": route_pair,
        },
        "events": summaries,
        "pairwise_relations": pairwise,
        "causal_summary": {
            "strict_before_pairs": before,
            "concurrent_pairs": concurrent,
            "unobserved_pairs": unobserved,
            "pair_status_counts": counts,
            "global_total_order": None,
            "interpretation": "A2 and B1 are concurrent in vector-clock knowledge, not a claim that their physical execution intervals overlapped. Missing C1 causal stamp means unobserved, not concurrent.",
        },
        "handoff": {
            "status": "verified_from_signed_direct_peer_receipt",
            "predecessor_event_id": "A1",
            "successor_event_id": "B1",
            "message_sequence": 1,
            "received_sequence": 1,
            "a1_envelope_digest": envelope["signed_digest"],
            "receiver_receipt_digest": client["receiver_receipt"]["signed_digest"],
            "a2_followup_digest": followup_signed["signed_digest"],
            "a2_followup_attestation": followup_verified,
            "a2_transferred_in_handoff": False,
        },
        "duration": {
            "local_operation_durations": durations,
            "combined_cross_host_elapsed_ns": None,
            "status": "not_computed_independent_unaligned_clock_domains",
            "cpu_time_claimed": False,
        },
        "wall_clock": {
            "used_for_causal_order": False,
            "cross_host_wall_comparison": "not_performed",
            "interpretation": "MOR-002 does not sample wall time for its causal reconstruction; only actor-scoped monotonic and causal coordinates are used.",
        },
        "limitations": [
            "The semantic A1 envelope, ReliableChannel ACK, and signed receiver receipt travel over the Tailscale-protected E-CPU mTLS socket; GitHub artifacts carry bootstrap and evidence, not the semantic payload.",
            "GitHub-hosted job identities and runner names do not prove distinct physical machines, cloud providers, administrators, or failure domains.",
            "Artifact attestations authenticate exact bytes under the protected workflow policy; they do not prove that a participant's claimed computation is honest.",
            "Ed25519 signatures and mTLS establish key possession and peer identity, not non-malicious execution.",
            "Tailscale route status is a local point-in-time observation adjacent to the application session, not a packet-level trace of every segment.",
            "A2 is deliberately recorded after A1 but omitted from the signed A1 message; vector-clock concurrency with B1 does not imply physical simultaneity.",
            "C1 intentionally has no causal stamp; all C1 causal relations remain unobserved.",
            "Operation spans measure synchronous callable elapsed intervals, not CPU time.",
            "No combined cross-host elapsed duration, calibrated one-way latency, or global wall-clock order is inferred.",
        ],
    }
    return {**report_core, "report_digest": direct.digest_object(report_core)}


def verify_to_report(directory: Path, output_path: Path, *, gh: str = "gh") -> dict[str, Any]:
    base_report_path = directory / "direct-mtls-report.json"
    base_report = direct.verify_to_report(directory, base_report_path, gh=gh)
    client_record_path = directory / "client-result" / "client_host-record.json"
    server_record_path = directory / "server-result" / "server_host-record.json"
    followup_path = directory / "source-followup" / "mor002-source-followup.json"
    observer_path = directory / "observer" / "observer.json"
    followup_predicate = _read(directory / "source-followup" / "mor002-source-followup.predicate.json")
    observer_predicate = _read(directory / "observer" / "observer.predicate.json")
    followup = _read(followup_path)
    observer = _validate_event_record(_read(observer_path))
    followup_attestation = direct.verify_artifact_attestation(
        followup_path, FOLLOWUP_PREDICATE_TYPE,
        expected_predicate=followup_predicate, gh=gh,
    )
    observer_attestation = direct.verify_artifact_attestation(
        observer_path, EVENT_PREDICATE_TYPE,
        expected_predicate=observer_predicate, gh=gh,
    )
    client_record = _read(client_record_path)
    server_record = _read(server_record_path)
    result = build_report(
        direct_report=base_report,
        client_record=client_record,
        server_record=server_record,
        client_cert_path=directory / "client-bootstrap" / "client-cert.pem",
        followup_signed=followup,
        followup_attestation=followup_attestation,
        observer_record=observer,
        observer_attestation=observer_attestation,
        followup_sha256=direct.file_digest(followup_path),
        observer_sha256=direct.file_digest(observer_path),
        verifier_host=direct.host_metadata("verifier_host"),
    )
    _write(output_path, result)
    return result


def write_report_predicate(report_path: Path, predicate_path: Path) -> dict[str, Any]:
    report = _read(report_path)
    if report.get("schema") != REPORT_SCHEMA:
        raise MOR002Error("unsupported MOR-002 report schema")
    core = {key: value for key, value in report.items() if key != "report_digest"}
    if report.get("report_digest") != direct.digest_object(core):
        raise MOR002Error("MOR-002 report digest mismatch")
    verifier = direct.host_metadata("verifier_host")
    if (
        report.get("run_id") != verifier["run_id"]
        or report.get("run_attempt") != verifier["run_attempt"]
        or report.get("workflow_ref") != verifier["workflow_ref"]
    ):
        raise MOR002Error("report belongs to another verifier run or workflow")
    if report.get("status") == "direct_mtls_verified":
        recorded_verifier = report.get("hosts", {}).get("verifier", {})
        if recorded_verifier.get("actor_id") != verifier["actor_id"]:
            raise MOR002Error("successful report is not bound to the current verifier actor")
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
        "report_sha256": direct.file_digest(report_path),
        "report_digest": report["report_digest"],
        "path_id": report.get("path_id"),
        "direct_transport_report_digest": report.get("direct_transport_report_digest"),
    }
    _write(predicate_path, predicate)
    return predicate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    observer = sub.add_parser("produce-observer")
    observer.add_argument("--output", type=Path, required=True)
    followup = sub.add_parser("write-followup-predicate")
    followup.add_argument("--record", type=Path, required=True)
    followup.add_argument("--output", type=Path, required=True)
    observer_predicate = sub.add_parser("write-observer-predicate")
    observer_predicate.add_argument("--record", type=Path, required=True)
    observer_predicate.add_argument("--output", type=Path, required=True)
    report = sub.add_parser("verify")
    report.add_argument("--directory", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    predicate = sub.add_parser("write-report-predicate")
    predicate.add_argument("--report", type=Path, required=True)
    predicate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "produce-observer":
            produce_observer(args.output)
        elif args.command == "write-followup-predicate":
            write_followup_predicate(args.record, args.output)
        elif args.command == "write-observer-predicate":
            write_observer_predicate(args.record, args.output)
        elif args.command == "verify":
            result = verify_to_report(args.directory, args.output)
            print(json.dumps({"status": result.get("status"), "report_digest": result.get("report_digest")}, sort_keys=True))
        elif args.command == "write-report-predicate":
            write_report_predicate(args.report, args.output)
        return 0
    except Exception as error:
        print(f"MOR-002 verification failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
