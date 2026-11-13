"""Reconstruct a measured operation path from same-clock spans and explicit dependencies.

The analyzer deliberately refuses to combine spans from different clock actors
or clock segments. It validates caller-declared completion dependencies against
local monotonic coordinates, then computes the longest measured chain in that
DAG. It never infers causality from timestamp order alone.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from operation_spans import load_operation_span_artifact, validate_operation_span

TRACE_FORMAT = "in-formation.operation-path"
TRACE_SCHEMA = "in-formation.operation-path/0.1"
REPORT_SCHEMA = "in-formation.operation-path-criticality/0.1"
TRACE_SCOPE = (
    "A caller-declared operation dependency DAG over one measured root span and "
    "same-clock atomic operation spans; dependency edges mean predecessor "
    "completion is required before successor invocation."
)
LIMITS = [
    "The root span is an observed synchronous envelope from one clock actor and segment; all included operation spans must use that same actor and segment.",
    "A must-complete-before edge is supplied by the caller and checked against local monotonic coordinates; timestamp order alone never creates a causal edge.",
    "The known dependency path includes only declared edges. Omitted prerequisites can make the computed chain shorter than the actual dependency critical path.",
    "Aggregate operation duration sums invocation durations and can exceed root elapsed time under concurrency; it is not CPU time or CPU utilization.",
    "Root slack is root elapsed time minus the longest declared dependency chain. It is not attributed transport, scheduling, admission, or verification time.",
    "Each source span measures its supplied synchronous callable boundary, including blocking inside that call; nested instrumentation can count overlapping work more than once.",
]
TRACE_FIELDS = {
    "format", "schema", "path_id", "attempt_id", "root_span_digest",
    "operation_span_digests", "must_complete_before", "measurement_scope", "trace_digest",
}
REPORT_FIELDS = {
    "schema", "path_id", "attempt_id", "clock_actor_id", "clock_segment_id",
    "root_span_digest", "root_span_id", "root_elapsed_ns", "operation_count",
    "dependency_count", "aggregate_operation_ns", "known_dependency_path_ns",
    "known_dependency_path_span_digests", "known_dependency_path_span_ids",
    "noncritical_aggregate_ns", "root_slack_ns", "operation_totals",
    "source_span_digests", "trace_digest", "interpretation_limits", "report_digest",
}


class OperationPathError(ValueError):
    """An operation-path trace is malformed, incomplete, or inconsistent."""


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OperationPathError(f"value is not canonical finite JSON: {exc}") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise OperationPathError(f"{label} must be non-empty text without NUL")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise OperationPathError(f"{label} must be a lowercase SHA-256 digest")
    return value


def build_operation_path_trace(
    *,
    path_id: str,
    attempt_id: str,
    root_span_digest: str,
    operation_span_digests: Sequence[str],
    must_complete_before: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Create a canonical, digest-bound declaration of the operation DAG."""
    path_id = _text(path_id, "path_id")
    attempt_id = _text(attempt_id, "attempt_id")
    root_digest = _sha256(root_span_digest, "root_span_digest")
    if not isinstance(operation_span_digests, (list, tuple)) or not operation_span_digests:
        raise OperationPathError("at least one operation span is required")
    operation_digests = sorted(_sha256(item, "operation_span_digest") for item in operation_span_digests)
    if len(set(operation_digests)) != len(operation_digests):
        raise OperationPathError("operation span digests must be unique")
    if root_digest in operation_digests:
        raise OperationPathError("root span cannot also be an operation node")

    if not isinstance(must_complete_before, (list, tuple)):
        raise OperationPathError("must_complete_before must be a list")
    edges: list[dict[str, str]] = []
    for index, edge in enumerate(must_complete_before):
        if not isinstance(edge, Mapping) or set(edge) != {"predecessor_span_digest", "successor_span_digest"}:
            raise OperationPathError(f"must_complete_before[{index}] must contain exactly predecessor and successor digests")
        predecessor = _sha256(edge["predecessor_span_digest"], f"must_complete_before[{index}].predecessor_span_digest")
        successor = _sha256(edge["successor_span_digest"], f"must_complete_before[{index}].successor_span_digest")
        if predecessor == successor:
            raise OperationPathError("an operation cannot be its own predecessor")
        if predecessor not in operation_digests or successor not in operation_digests:
            raise OperationPathError("dependency edge references a span outside operation_span_digests")
        edges.append({"predecessor_span_digest": predecessor, "successor_span_digest": successor})
    edge_keys = [(e["predecessor_span_digest"], e["successor_span_digest"]) for e in edges]
    if len(set(edge_keys)) != len(edge_keys):
        raise OperationPathError("duplicate dependency edges are not allowed")
    edges.sort(key=lambda e: (e["predecessor_span_digest"], e["successor_span_digest"]))

    core = {
        "format": TRACE_FORMAT,
        "schema": TRACE_SCHEMA,
        "path_id": path_id,
        "attempt_id": attempt_id,
        "root_span_digest": root_digest,
        "operation_span_digests": operation_digests,
        "must_complete_before": edges,
        "measurement_scope": TRACE_SCOPE,
    }
    return {**core, "trace_digest": _digest(core)}


def validate_operation_path_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(trace, Mapping) or set(trace) != TRACE_FIELDS:
        raise OperationPathError("operation-path trace fields are incomplete or unexpected")
    if trace["format"] != TRACE_FORMAT or trace["schema"] != TRACE_SCHEMA:
        raise OperationPathError("unsupported operation-path trace format or schema")
    if trace["measurement_scope"] != TRACE_SCOPE:
        raise OperationPathError("operation-path trace must retain its declared measurement scope")
    rebuilt = build_operation_path_trace(
        path_id=trace["path_id"],
        attempt_id=trace["attempt_id"],
        root_span_digest=trace["root_span_digest"],
        operation_span_digests=trace["operation_span_digests"],
        must_complete_before=trace["must_complete_before"],
    )
    if rebuilt != dict(trace):
        raise OperationPathError("operation-path trace is not canonical or its digest is invalid")
    return rebuilt


def _topological_order(
    nodes: Sequence[str], successors: Mapping[str, set[str]], predecessors: Mapping[str, set[str]],
) -> list[str]:
    indegree = {node: len(predecessors[node]) for node in nodes}
    ready = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    result: list[str] = []
    while ready:
        node = heapq.heappop(ready)
        result.append(node)
        for child in sorted(successors[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(result) != len(nodes):
        raise OperationPathError("dependency graph contains a cycle")
    return result


def build_operation_path_report(
    span_documents: list[Mapping[str, Any]],
    *,
    trace: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one same-clock path and compute its known dependency-chain cost."""
    trace = validate_operation_path_trace(trace)
    if not isinstance(span_documents, list) or not span_documents:
        raise OperationPathError("span_documents must be a non-empty list")

    spans: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str]] = set()
    for raw in span_documents:
        span = validate_operation_span(raw)
        span_digest = span["span_digest"]
        if span_digest in spans:
            raise OperationPathError("duplicate source span digest")
        identity = (span["attempt_id"], span["span_id"])
        if identity in identities:
            raise OperationPathError("duplicate (attempt_id, span_id) source identity")
        identities.add(identity)
        spans[span_digest] = span

    root_digest = trace["root_span_digest"]
    node_digests = list(trace["operation_span_digests"])
    expected_digests = set(node_digests) | {root_digest}
    if set(spans) != expected_digests:
        missing = sorted(expected_digests - set(spans))
        extra = sorted(set(spans) - expected_digests)
        raise OperationPathError(f"source spans must be exactly the root and declared operation nodes (missing={missing}, extra={extra})")

    root = spans[root_digest]
    if root["attempt_id"] != trace["attempt_id"]:
        raise OperationPathError("root span attempt_id differs from trace")
    if root["clock_status"] != "measured" or root["elapsed_ns"] is None:
        raise OperationPathError("root span must have a measured monotonic duration")

    actor = root["clock_actor_id"]
    segment = root["clock_segment_id"]
    root_start = root["monotonic_start_ns"]
    root_end = root["monotonic_end_ns"]
    for digest_value in node_digests:
        span = spans[digest_value]
        if span["attempt_id"] != trace["attempt_id"]:
            raise OperationPathError("operation span attempt_id differs from trace")
        if (span["clock_actor_id"], span["clock_segment_id"]) != (actor, segment):
            raise OperationPathError("cross-clock aggregation is not supported; all spans must share the root clock actor and segment")
        if span["clock_status"] != "measured" or span["elapsed_ns"] is None:
            raise OperationPathError("every operation node must have a measured monotonic duration")
        if span["monotonic_start_ns"] < root_start or span["monotonic_end_ns"] > root_end:
            raise OperationPathError("root span must enclose every operation span")

    successors: dict[str, set[str]] = {node: set() for node in node_digests}
    predecessors: dict[str, set[str]] = {node: set() for node in node_digests}
    for edge in trace["must_complete_before"]:
        before = edge["predecessor_span_digest"]
        after = edge["successor_span_digest"]
        before_span = spans[before]
        after_span = spans[after]
        if before_span["monotonic_end_ns"] > after_span["monotonic_start_ns"]:
            raise OperationPathError("declared completion dependency is not supported by the same-clock span intervals")
        successors[before].add(after)
        predecessors[after].add(before)

    order = _topological_order(node_digests, successors, predecessors)
    best_cost: dict[str, int] = {}
    best_path: dict[str, tuple[str, ...]] = {}
    for node in order:
        duration = spans[node]["elapsed_ns"]
        assert isinstance(duration, int)
        base_cost = duration
        base_path = (node,)
        for parent in sorted(predecessors[node]):
            candidate_cost = best_cost[parent] + duration
            candidate_path = best_path[parent] + (node,)
            if candidate_cost > base_cost or (candidate_cost == base_cost and candidate_path < base_path):
                base_cost = candidate_cost
                base_path = candidate_path
        best_cost[node] = base_cost
        best_path[node] = base_path

    terminal_nodes = [node for node in node_digests if not successors[node]]
    chosen_end = min(terminal_nodes, key=lambda node: (-best_cost[node], best_path[node]))
    critical_digests = list(best_path[chosen_end])
    critical_ns = best_cost[chosen_end]
    root_elapsed = root["elapsed_ns"]
    if critical_ns > root_elapsed:
        raise OperationPathError("known dependency path exceeds the measured root envelope")

    operation_spans = [spans[digest_value] for digest_value in node_digests]
    aggregate_ns = sum(span["elapsed_ns"] for span in operation_spans)
    totals: dict[tuple[str, str], list[int]] = defaultdict(list)
    for span in operation_spans:
        totals[(span["operation_id"], span["outcome"])].append(span["elapsed_ns"])
    operation_totals = [
        {
            "operation_id": operation_id,
            "outcome": outcome,
            "span_count": len(durations),
            "aggregate_elapsed_ns": sum(durations),
        }
        for (operation_id, outcome), durations in sorted(totals.items())
    ]

    core = {
        "schema": REPORT_SCHEMA,
        "path_id": trace["path_id"],
        "attempt_id": trace["attempt_id"],
        "clock_actor_id": actor,
        "clock_segment_id": segment,
        "root_span_digest": root_digest,
        "root_span_id": root["span_id"],
        "root_elapsed_ns": root_elapsed,
        "operation_count": len(operation_spans),
        "dependency_count": len(trace["must_complete_before"]),
        "aggregate_operation_ns": aggregate_ns,
        "known_dependency_path_ns": critical_ns,
        "known_dependency_path_span_digests": critical_digests,
        "known_dependency_path_span_ids": [spans[digest_value]["span_id"] for digest_value in critical_digests],
        "noncritical_aggregate_ns": aggregate_ns - critical_ns,
        "root_slack_ns": root_elapsed - critical_ns,
        "operation_totals": operation_totals,
        "source_span_digests": sorted(spans),
        "trace_digest": trace["trace_digest"],
        "interpretation_limits": list(LIMITS),
    }
    return {**core, "report_digest": _digest(core)}


def validate_operation_path_report(
    report: Mapping[str, Any],
    span_documents: list[Mapping[str, Any]],
    *,
    trace: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(report, Mapping) or set(report) != REPORT_FIELDS:
        raise OperationPathError("operation-path report fields are incomplete or unexpected")
    supplied = dict(report)
    digest_value = supplied.pop("report_digest")
    if digest_value != _digest(supplied):
        raise OperationPathError("operation-path report digest does not match its contents")
    rebuilt = build_operation_path_report(span_documents, trace=trace)
    if rebuilt != dict(report):
        raise OperationPathError("operation-path report differs from independent source-span reconstruction")
    return rebuilt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct a declared operation dependency path from same-clock span artifacts.")
    parser.add_argument("--spans", required=True, help='JSON span array or {"spans": [...]} artifact')
    parser.add_argument("--trace", required=True, help="canonical operation-path trace JSON")
    parser.add_argument("--output", help="write report JSON to this path; default is stdout")
    args = parser.parse_args(argv)
    try:
        spans = load_operation_span_artifact(args.spans)
        trace = json.loads(Path(args.trace).read_text(encoding="utf-8"))
        report = build_operation_path_report(spans, trace=trace)
        validate_operation_path_report(report, spans, trace=trace)
        rendered = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
