"""Distributed operation-path reconstruction with causal handoffs and bounded clock-rate calibration.

Causal order and elapsed duration are deliberately separate inputs:
- local edges are checked against one actor/segment's monotonic intervals;
- cross-clock edges require a message-linked vector-clock handoff witness;
- operation durations are normalized only through explicit affine clock calibrations.

The result is a conservative critical-path duration interval. It is not a
single global wall-clock latency measurement.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from operation_spans import validate_operation_span

_TEMPORAL_DIR = Path(__file__).resolve().parents[1] / "temporal-provenance"
if str(_TEMPORAL_DIR) not in sys.path:
    sys.path.insert(0, str(_TEMPORAL_DIR))

from clock_calibration import validate_calibration
from temporal_provenance import validate_temporal_frame

TRACE_FORMAT = "in-formation.distributed-operation-path"
TRACE_SCHEMA = "in-formation.distributed-operation-path/0.1"
HANDOFF_SCHEMA = "in-formation.operation-path.causal-handoff/0.1"
PAYLOAD_SCHEMA = "in-formation.operation-path.handoff-payload/0.1"
REPORT_SCHEMA = "in-formation.distributed-operation-path-report/0.1"

TRACE_SCOPE = (
    "A DAG of measured operation spans joined by same-clock monotonic completion "
    "dependencies or message-linked vector-clock handoff witnesses. Every clock "
    "domain is normalized to one declared reference clock only through a supplied "
    "bounded positive-affine calibration."
)
LIMITS = [
    "A vector-clock relation is only as trustworthy as the code and actor identity that generated and merged its stamps. This analyzer checks consistency, not source authentication or transport signatures.",
    "A message sequence and payload digest bind the supplied handoff record internally; they do not prove that a physical network peer sent or received that message.",
    "Clock calibration anchors and witness references are caller-supplied. Calibration digests permit reconstruction but do not authenticate the physical anchors.",
    "Affine scale bounds are numeric feasible-set envelopes, not probability distributions or calibrated confidence intervals.",
    "The critical-path duration interval is conservative. Its lower-bound and upper-bound maximizing chains can differ; path identity may remain unresolved under calibration uncertainty.",
    "There is no common root interval in this format. It does not report global wall latency, root slack, transport overhead, CPU time, or CPU utilization.",
    "Operation spans measure supplied synchronous call boundaries. Nested or overlapping instrumentation can count work more than once; omitted dependency edges can understate the actual critical path.",
]
TRACE_FIELDS = {
    "format", "schema", "path_id", "attempt_id", "reference_clock_actor_id",
    "reference_clock_segment_id", "span_digests", "local_dependencies",
    "causal_handoffs", "calibration_bindings", "measurement_scope", "trace_digest",
}
HANDOFF_FIELDS = {
    "schema", "path_id", "attempt_id", "predecessor_span_digest",
    "successor_span_digest", "channel_id", "message_sequence",
    "received_sequence", "sender_actor_id", "receiver_actor_id",
    "payload_digest", "sender_completion_frame", "receiver_start_frame",
    "handoff_digest",
}
REPORT_FIELDS = {
    "schema", "path_id", "attempt_id", "reference_clock_id",
    "reference_clock_actor_id", "reference_clock_segment_id",
    "operation_count", "local_dependency_count", "causal_handoff_count",
    "aggregate_duration_lower_ns", "aggregate_duration_upper_ns",
    "critical_path_lower_ns", "critical_path_upper_ns",
    "critical_path_lower_span_digests", "critical_path_upper_span_digests",
    "critical_path_selection_status", "clock_domain_profiles",
    "calibration_digests", "span_digests", "trace_digest",
    "causal_evidence_status", "interpretation_limits", "report_digest",
}


class DistributedOperationPathError(ValueError):
    """A distributed operation path, handoff, calibration, or report is invalid."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DistributedOperationPathError(
            f"value is not canonical finite JSON: {exc}"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DistributedOperationPathError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DistributedOperationPathError(f"{label} must be an integer >= {minimum}")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DistributedOperationPathError(f"{label} must be a lowercase SHA-256 digest")
    return value


def clock_domain_id(actor_id: str, segment_id: str) -> str:
    """Return an unambiguous content-derived ID for one actor/monotonic segment."""
    return _digest({
        "schema": "in-formation.monotonic-clock-domain/0.1",
        "actor_id": _text(actor_id, "actor_id"),
        "segment_id": _text(segment_id, "segment_id"),
    })


def _span_index(span_documents: list[Mapping[str, Any]], attempt_id: str) -> dict[str, dict[str, Any]]:
    if not isinstance(span_documents, list) or not span_documents:
        raise DistributedOperationPathError("span_documents must be a non-empty list")
    spans: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str]] = set()
    for raw in span_documents:
        span = validate_operation_span(raw)
        if span["attempt_id"] != attempt_id:
            raise DistributedOperationPathError("all operation spans must use the trace attempt_id")
        identity = (span["attempt_id"], span["span_id"])
        if identity in identities:
            raise DistributedOperationPathError("duplicate operation-span identity")
        identities.add(identity)
        if span["span_digest"] in spans:
            raise DistributedOperationPathError("duplicate operation-span digest")
        if span["clock_status"] != "measured" or span["elapsed_ns"] is None:
            raise DistributedOperationPathError("every operation span must have a measured monotonic duration")
        spans[span["span_digest"]] = span
    return spans


def _validated_frame(frame: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        normalized = validate_temporal_frame(frame)
    except (TypeError, ValueError, KeyError) as exc:
        raise DistributedOperationPathError(f"{label} is not a valid E-CPU TemporalFrame: {exc}") from exc
    if normalized["monotonic"] is None or normalized["causal"] is None:
        raise DistributedOperationPathError(f"{label} must include monotonic and causal coordinates")
    return normalized


def build_handoff_payload(
    *,
    path_id: str,
    attempt_id: str,
    predecessor_span_digest: str,
    sender_completion_frame: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the exact payload that a sender places on ReliableChannel."""
    frame = _validated_frame(sender_completion_frame, "sender_completion_frame")
    predecessor = _sha256(predecessor_span_digest, "predecessor_span_digest")
    core = {
        "schema": PAYLOAD_SCHEMA,
        "path_id": _text(path_id, "path_id"),
        "attempt_id": _text(attempt_id, "attempt_id"),
        "predecessor_span_digest": predecessor,
        "sender_actor_id": frame["actor_id"],
        "sender_completion_frame": frame,
    }
    return {**core, "payload_digest": _digest(core)}


def build_causal_handoff_witness(
    *,
    payload: Mapping[str, Any],
    successor_span_digest: str,
    channel_id: str,
    message_sequence: int,
    received_sequence: int,
    receiver_start_frame: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the received sequence and receiver-side causal merge to a sender payload."""
    if not isinstance(payload, Mapping):
        raise DistributedOperationPathError("handoff payload must be a mapping")
    expected_payload_fields = {
        "schema", "path_id", "attempt_id", "predecessor_span_digest",
        "sender_actor_id", "sender_completion_frame", "payload_digest",
    }
    if set(payload) != expected_payload_fields:
        raise DistributedOperationPathError("handoff payload fields are incomplete or unexpected")
    payload_core = {key: payload[key] for key in expected_payload_fields if key != "payload_digest"}
    if payload["schema"] != PAYLOAD_SCHEMA or payload["payload_digest"] != _digest(payload_core):
        raise DistributedOperationPathError("handoff payload digest or schema is invalid")
    sender_frame = _validated_frame(payload["sender_completion_frame"], "sender_completion_frame")
    receiver_frame = _validated_frame(receiver_start_frame, "receiver_start_frame")
    sender = _text(payload["sender_actor_id"], "sender_actor_id")
    receiver = receiver_frame["actor_id"]
    if sender != sender_frame["actor_id"]:
        raise DistributedOperationPathError("sender_actor_id differs from sender frame")
    if sender == receiver:
        raise DistributedOperationPathError("causal handoff requires distinct E-CPU actor identities")
    sequence = _integer(message_sequence, "message_sequence", 1)
    received = _integer(received_sequence, "received_sequence", 1)
    if sequence != received:
        raise DistributedOperationPathError("ReliableChannel received sequence differs from sent sequence")

    core = {
        "schema": HANDOFF_SCHEMA,
        "path_id": _text(payload["path_id"], "path_id"),
        "attempt_id": _text(payload["attempt_id"], "attempt_id"),
        "predecessor_span_digest": _sha256(payload["predecessor_span_digest"], "predecessor_span_digest"),
        "successor_span_digest": _sha256(successor_span_digest, "successor_span_digest"),
        "channel_id": _text(channel_id, "channel_id"),
        "message_sequence": sequence,
        "received_sequence": received,
        "sender_actor_id": sender,
        "receiver_actor_id": receiver,
        "payload_digest": _sha256(payload["payload_digest"], "payload_digest"),
        "sender_completion_frame": sender_frame,
        "receiver_start_frame": receiver_frame,
    }
    return {**core, "handoff_digest": _digest(core)}


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


def validate_causal_handoff_witness(
    handoff: Mapping[str, Any],
    *,
    predecessor_span: Mapping[str, Any],
    successor_span: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(handoff, Mapping) or set(handoff) != HANDOFF_FIELDS:
        raise DistributedOperationPathError("causal handoff fields are incomplete or unexpected")
    core = {key: handoff[key] for key in HANDOFF_FIELDS if key != "handoff_digest"}
    if handoff["schema"] != HANDOFF_SCHEMA or handoff["handoff_digest"] != _digest(core):
        raise DistributedOperationPathError("causal handoff digest or schema is invalid")
    sender_frame = _validated_frame(handoff["sender_completion_frame"], "sender_completion_frame")
    receiver_frame = _validated_frame(handoff["receiver_start_frame"], "receiver_start_frame")
    before = _sha256(handoff["predecessor_span_digest"], "predecessor_span_digest")
    after = _sha256(handoff["successor_span_digest"], "successor_span_digest")
    if before != predecessor_span["span_digest"] or after != successor_span["span_digest"]:
        raise DistributedOperationPathError("handoff endpoint digests do not match supplied operation spans")

    sender = _text(handoff["sender_actor_id"], "sender_actor_id")
    receiver = _text(handoff["receiver_actor_id"], "receiver_actor_id")
    if sender != predecessor_span["clock_actor_id"] or receiver != successor_span["clock_actor_id"]:
        raise DistributedOperationPathError("handoff actor IDs do not match operation-span clock actors")
    if sender == receiver:
        raise DistributedOperationPathError("same-actor dependency must use a local monotonic edge")
    if sender_frame["actor_id"] != sender or receiver_frame["actor_id"] != receiver:
        raise DistributedOperationPathError("handoff temporal-frame actors do not match message endpoints")

    sender_mono = sender_frame["monotonic"]
    receiver_mono = receiver_frame["monotonic"]
    if str(sender_mono["segment"]) != predecessor_span["clock_segment_id"]:
        raise DistributedOperationPathError("sender handoff frame belongs to another monotonic segment")
    if str(receiver_mono["segment"]) != successor_span["clock_segment_id"]:
        raise DistributedOperationPathError("receiver handoff frame belongs to another monotonic segment")
    if sender_mono["elapsed_ns"] < predecessor_span["monotonic_end_ns"]:
        raise DistributedOperationPathError("sender causal frame predates predecessor operation completion")
    if receiver_mono["elapsed_ns"] > successor_span["monotonic_start_ns"]:
        raise DistributedOperationPathError("receiver causal frame follows successor operation start")

    sender_causal = sender_frame["causal"]
    receiver_causal = receiver_frame["causal"]
    relation = _vector_relation(sender_causal["vector"], receiver_causal["vector"])
    if relation != "before" or sender_causal["lamport"] >= receiver_causal["lamport"]:
        raise DistributedOperationPathError("receiver causal frame does not strictly follow sender completion frame")

    expected_payload = {
        "schema": PAYLOAD_SCHEMA,
        "path_id": handoff["path_id"],
        "attempt_id": handoff["attempt_id"],
        "predecessor_span_digest": before,
        "sender_actor_id": sender,
        "sender_completion_frame": sender_frame,
    }
    if _digest(expected_payload) != _sha256(handoff["payload_digest"], "payload_digest"):
        raise DistributedOperationPathError("handoff payload digest does not bind the declared predecessor and sender frame")
    _integer(handoff["message_sequence"], "message_sequence", 1)
    if _integer(handoff["received_sequence"], "received_sequence", 1) != handoff["message_sequence"]:
        raise DistributedOperationPathError("received sequence differs from message sequence")
    _text(handoff["channel_id"], "channel_id")
    return dict(handoff)


def _topological_order(nodes: Sequence[str], edges: Sequence[tuple[str, str]]) -> list[str]:
    outgoing = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for before, after in edges:
        if before not in outgoing or after not in outgoing:
            raise DistributedOperationPathError("dependency references an unknown operation span")
        if after not in outgoing[before]:
            outgoing[before].add(after)
            indegree[after] += 1
    ready = [node for node in nodes if indegree[node] == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for child in sorted(outgoing[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(nodes):
        raise DistributedOperationPathError("combined dependency graph contains a cycle")
    return order


def _validate_calibrations(
    clock_calibrations: list[Mapping[str, Any]],
    spans: Mapping[str, Mapping[str, Any]],
    reference_clock_id: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    if not isinstance(clock_calibrations, list):
        raise TypeError("clock_calibrations must be a list")
    domains = {
        clock_domain_id(span["clock_actor_id"], span["clock_segment_id"])
        for span in spans.values()
    }
    if reference_clock_id not in domains:
        raise DistributedOperationPathError("reference clock domain must be present in the operation spans")
    by_source: dict[str, dict[str, Any]] = {}
    for raw in clock_calibrations:
        calibration = validate_calibration(raw)
        source = calibration["source_clock_id"]
        if source in by_source:
            raise DistributedOperationPathError("duplicate calibration for one source clock domain")
        if source == reference_clock_id or calibration["target_clock_id"] != reference_clock_id:
            raise DistributedOperationPathError("each calibration must map one non-reference clock to the declared reference clock")
        if calibration["source_unit"] != "ns" or calibration["target_unit"] != "ns":
            raise DistributedOperationPathError("operation path duration calibration units must both be ns")
        by_source[source] = calibration

    expected_sources = domains - {reference_clock_id}
    if set(by_source) != expected_sources:
        raise DistributedOperationPathError(
            f"calibrations must cover every non-reference clock domain exactly once; "
            f"missing={sorted(expected_sources-set(by_source))}, extra={sorted(set(by_source)-expected_sources)}"
        )
    bindings = [
        {"source_clock_id": source, "calibration_digest": by_source[source]["calibration_digest"]}
        for source in sorted(by_source)
    ]
    return by_source, bindings


def build_distributed_operation_path_trace(
    *,
    path_id: str,
    attempt_id: str,
    span_documents: list[Mapping[str, Any]],
    reference_clock_actor_id: str,
    reference_clock_segment_id: str,
    local_dependencies: Sequence[Mapping[str, str]],
    causal_handoffs: Sequence[Mapping[str, Any]],
    clock_calibrations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Construct a digest-bound distributed DAG without assuming a common clock epoch."""
    path = _text(path_id, "path_id")
    attempt = _text(attempt_id, "attempt_id")
    spans = _span_index(span_documents, attempt)
    reference_clock = clock_domain_id(reference_clock_actor_id, reference_clock_segment_id)
    _calibration_map, calibration_bindings = _validate_calibrations(clock_calibrations, spans, reference_clock)

    nodes = set(spans)
    local_edges: list[dict[str, str]] = []
    for index, edge in enumerate(local_dependencies):
        if not isinstance(edge, Mapping) or set(edge) != {"predecessor_span_digest", "successor_span_digest"}:
            raise DistributedOperationPathError(f"local_dependencies[{index}] must contain predecessor and successor digests")
        before = _sha256(edge["predecessor_span_digest"], f"local_dependencies[{index}].predecessor_span_digest")
        after = _sha256(edge["successor_span_digest"], f"local_dependencies[{index}].successor_span_digest")
        if before not in nodes or after not in nodes or before == after:
            raise DistributedOperationPathError("local dependency references an unknown or identical operation span")
        a, b = spans[before], spans[after]
        if (a["clock_actor_id"], a["clock_segment_id"]) != (b["clock_actor_id"], b["clock_segment_id"]):
            raise DistributedOperationPathError("local monotonic dependency must use the same actor and segment")
        if a["monotonic_end_ns"] > b["monotonic_start_ns"]:
            raise DistributedOperationPathError("local dependency is not supported by monotonic span intervals")
        local_edges.append({"predecessor_span_digest": before, "successor_span_digest": after})
    if len({(e["predecessor_span_digest"], e["successor_span_digest"]) for e in local_edges}) != len(local_edges):
        raise DistributedOperationPathError("duplicate local dependency edges are not allowed")
    local_edges.sort(key=lambda e: (e["predecessor_span_digest"], e["successor_span_digest"]))

    handoffs: list[dict[str, Any]] = []
    for handoff in causal_handoffs:
        if not isinstance(handoff, Mapping):
            raise DistributedOperationPathError("causal_handoffs entries must be mappings")
        before = handoff.get("predecessor_span_digest")
        after = handoff.get("successor_span_digest")
        if before not in spans or after not in spans:
            raise DistributedOperationPathError("causal handoff references an unknown operation span")
        handoffs.append(validate_causal_handoff_witness(
            handoff, predecessor_span=spans[before], successor_span=spans[after]
        ))
    handoffs.sort(key=lambda h: (h["predecessor_span_digest"], h["successor_span_digest"]))
    edge_pairs = [(e["predecessor_span_digest"], e["successor_span_digest"]) for e in local_edges]
    edge_pairs.extend((h["predecessor_span_digest"], h["successor_span_digest"]) for h in handoffs)
    if len(set(edge_pairs)) != len(edge_pairs):
        raise DistributedOperationPathError("duplicate dependency relation across local and causal edges")
    _topological_order(sorted(nodes), edge_pairs)

    core = {
        "format": TRACE_FORMAT,
        "schema": TRACE_SCHEMA,
        "path_id": path,
        "attempt_id": attempt,
        "reference_clock_actor_id": _text(reference_clock_actor_id, "reference_clock_actor_id"),
        "reference_clock_segment_id": _text(reference_clock_segment_id, "reference_clock_segment_id"),
        "span_digests": sorted(nodes),
        "local_dependencies": local_edges,
        "causal_handoffs": handoffs,
        "calibration_bindings": calibration_bindings,
        "measurement_scope": TRACE_SCOPE,
    }
    return {**core, "trace_digest": _digest(core)}


def validate_distributed_operation_path_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(trace, Mapping) or set(trace) != TRACE_FIELDS:
        raise DistributedOperationPathError("distributed operation-path trace fields are incomplete or unexpected")
    if trace["format"] != TRACE_FORMAT or trace["schema"] != TRACE_SCHEMA:
        raise DistributedOperationPathError("unsupported distributed operation-path format or schema")
    if trace["measurement_scope"] != TRACE_SCOPE:
        raise DistributedOperationPathError("distributed operation-path scope changed")
    core = {key: trace[key] for key in TRACE_FIELDS if key != "trace_digest"}
    if _sha256(trace["trace_digest"], "trace_digest") != _digest(core):
        raise DistributedOperationPathError("distributed operation-path trace digest mismatch")
    return dict(trace)


def _scaled_duration(elapsed_ns: int, lower_scale: float, upper_scale: float) -> tuple[int, int]:
    if lower_scale == upper_scale == 1.0:
        return elapsed_ns, elapsed_ns
    lower_value = math.nextafter(lower_scale * elapsed_ns, -math.inf)
    upper_value = math.nextafter(upper_scale * elapsed_ns, math.inf)
    return max(0, math.floor(lower_value)), max(0, math.ceil(upper_value))


def _longest_path(
    nodes: Sequence[str],
    predecessors: Mapping[str, set[str]],
    successors: Mapping[str, set[str]],
    weights: Mapping[str, int],
    order: Sequence[str],
) -> tuple[int, tuple[str, ...]]:
    best: dict[str, tuple[int, tuple[str, ...]]] = {}
    for node in order:
        duration = weights[node]
        candidates = [(duration, (node,))]
        for parent in sorted(predecessors[node]):
            previous, chain = best[parent]
            candidates.append((previous + duration, chain + (node,)))
        best[node] = min(candidates, key=lambda item: (-item[0], item[1]))
    terminals = [node for node in nodes if not successors[node]]
    return min((best[node] for node in terminals), key=lambda item: (-item[0], item[1]))


def build_distributed_operation_path_report(
    span_documents: list[Mapping[str, Any]],
    *,
    trace: Mapping[str, Any],
    clock_calibrations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    trace = validate_distributed_operation_path_trace(trace)
    # Rebuild the complete trace before using its edges; a self-consistent
    # digest alone is not evidence that the local intervals and handoffs match.
    rebuilt_trace = build_distributed_operation_path_trace(
        path_id=trace["path_id"],
        attempt_id=trace["attempt_id"],
        span_documents=span_documents,
        reference_clock_actor_id=trace["reference_clock_actor_id"],
        reference_clock_segment_id=trace["reference_clock_segment_id"],
        local_dependencies=trace["local_dependencies"],
        causal_handoffs=trace["causal_handoffs"],
        clock_calibrations=clock_calibrations,
    )
    if rebuilt_trace != dict(trace):
        raise DistributedOperationPathError("trace differs from independent reconstruction from source spans and calibrations")

    spans = _span_index(span_documents, trace["attempt_id"])
    reference_clock = clock_domain_id(
        trace["reference_clock_actor_id"], trace["reference_clock_segment_id"]
    )
    calibration_map, calibration_bindings = _validate_calibrations(
        clock_calibrations, spans, reference_clock
    )

    duration_bounds: dict[str, tuple[int, int]] = {}
    profiles: dict[str, dict[str, Any]] = {}
    for digest_value, span in spans.items():
        domain = clock_domain_id(span["clock_actor_id"], span["clock_segment_id"])
        if domain == reference_clock:
            lower, upper = span["elapsed_ns"], span["elapsed_ns"]
        else:
            calibration = calibration_map[domain]
            if not (
                calibration["validity_source_min"] <= span["monotonic_start_ns"]
                <= calibration["validity_source_max"]
                and calibration["validity_source_min"] <= span["monotonic_end_ns"]
                <= calibration["validity_source_max"]
            ):
                raise DistributedOperationPathError("operation span lies outside its clock calibration validity interval")
            scales = [vertex["scale"] for vertex in calibration["feasible_region"]]
            lower, upper = _scaled_duration(span["elapsed_ns"], min(scales), max(scales))
        duration_bounds[digest_value] = (lower, upper)
        group = profiles.setdefault(domain, {
            "clock_domain_id": domain,
            "clock_actor_id": span["clock_actor_id"],
            "clock_segment_id": span["clock_segment_id"],
            "operation_count": 0,
            "native_duration_ns": 0,
            "reference_duration_lower_ns": 0,
            "reference_duration_upper_ns": 0,
        })
        group["operation_count"] += 1
        group["native_duration_ns"] += span["elapsed_ns"]
        group["reference_duration_lower_ns"] += lower
        group["reference_duration_upper_ns"] += upper

    nodes = sorted(spans)
    edges = [
        (edge["predecessor_span_digest"], edge["successor_span_digest"])
        for edge in trace["local_dependencies"]
    ] + [
        (edge["predecessor_span_digest"], edge["successor_span_digest"])
        for edge in trace["causal_handoffs"]
    ]
    order = _topological_order(nodes, edges)
    predecessors: dict[str, set[str]] = {node: set() for node in nodes}
    successors: dict[str, set[str]] = {node: set() for node in nodes}
    for before, after in edges:
        predecessors[after].add(before)
        successors[before].add(after)

    lower_weights = {node: bounds[0] for node, bounds in duration_bounds.items()}
    upper_weights = {node: bounds[1] for node, bounds in duration_bounds.items()}
    critical_lower, lower_chain = _longest_path(nodes, predecessors, successors, lower_weights, order)
    critical_upper, upper_chain = _longest_path(nodes, predecessors, successors, upper_weights, order)
    aggregate_lower = sum(lower_weights.values())
    aggregate_upper = sum(upper_weights.values())

    core = {
        "schema": REPORT_SCHEMA,
        "path_id": trace["path_id"],
        "attempt_id": trace["attempt_id"],
        "reference_clock_id": reference_clock,
        "reference_clock_actor_id": trace["reference_clock_actor_id"],
        "reference_clock_segment_id": trace["reference_clock_segment_id"],
        "operation_count": len(nodes),
        "local_dependency_count": len(trace["local_dependencies"]),
        "causal_handoff_count": len(trace["causal_handoffs"]),
        "aggregate_duration_lower_ns": aggregate_lower,
        "aggregate_duration_upper_ns": aggregate_upper,
        "critical_path_lower_ns": critical_lower,
        "critical_path_upper_ns": critical_upper,
        "critical_path_lower_span_digests": list(lower_chain),
        "critical_path_upper_span_digests": list(upper_chain),
        "critical_path_selection_status": (
            "same_extremal_chain" if lower_chain == upper_chain
            else "chain_identity_uncertain_under_calibration"
        ),
        "clock_domain_profiles": [profiles[key] for key in sorted(profiles)],
        "calibration_digests": [item["calibration_digest"] for item in calibration_bindings],
        "span_digests": sorted(nodes),
        "trace_digest": trace["trace_digest"],
        "causal_evidence_status": "vector_clock_consistent_unverified_transport",
        "interpretation_limits": list(LIMITS),
    }
    return {**core, "report_digest": _digest(core)}


def validate_distributed_operation_path_report(
    report: Mapping[str, Any],
    span_documents: list[Mapping[str, Any]],
    *,
    trace: Mapping[str, Any],
    clock_calibrations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(report, Mapping) or set(report) != REPORT_FIELDS:
        raise DistributedOperationPathError("distributed operation-path report fields are incomplete or unexpected")
    core = {key: report[key] for key in REPORT_FIELDS if key != "report_digest"}
    if report["report_digest"] != _digest(core):
        raise DistributedOperationPathError("distributed operation-path report digest mismatch")
    rebuilt = build_distributed_operation_path_report(
        span_documents, trace=trace, clock_calibrations=clock_calibrations
    )
    if rebuilt != dict(report):
        raise DistributedOperationPathError("report differs from independent reconstruction from source spans and calibrations")
    return rebuilt
