"""Counterfactual duration reductions on a validated, fixed operation DAG."""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import sys
from collections.abc import Mapping
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[2] / "bridges" / "observation-path"
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))
from operation_path_criticality import OperationPathError, build_operation_path_report
from operation_spans import load_operation_span_artifact

LIMITS = [
    "Counterfactual inference on the declared fixed DAG, not an observed speedup or predicted root elapsed time.",
    "Durations are nonnegative integer nanoseconds; reductions do not change edges, other durations, or introduce resource contention.",
    "Paths are distinct source-to-sink node sequences, including zero-duration nodes and isolated nodes; redundant edges can change path counts.",
    "Full-removal benefit sets one node duration to zero without deleting its dependencies. Individual benefits are not additive.",
    "All original same-clock, source-span, and caller-declared dependency limitations remain applicable.",
]


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _graph(trace):
    nodes = trace["operation_span_digests"]
    before = {n: [] for n in nodes}
    after = {n: [] for n in nodes}
    for edge in trace["must_complete_before"]:
        a, b = edge["predecessor_span_digest"], edge["successor_span_digest"]
        after[a].append(b)
        before[b].append(a)
    degree = {n: len(before[n]) for n in nodes}
    ready = [n for n in nodes if degree[n] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for child in after[n]:
            degree[child] -= 1
            if degree[child] == 0:
                heapq.heappush(ready, child)
    return order, before, after


def _longest(order, before, after, durations):
    distance, count = {}, {}
    for n in order:
        parents = before[n]
        best = max((distance[p] for p in parents), default=0)
        distance[n] = best + durations[n]
        count[n] = sum(count[p] for p in parents if distance[p] == best) if parents else 1
    sinks = [n for n in order if not after[n]]
    length = max(distance[n] for n in sinks)
    return length, sum(count[n] for n in sinks if distance[n] == length), distance, count


def build_sensitivity_report(spans, *, trace, reductions=None):
    """Reconstruct evidence first, then evaluate a separate duration hypothesis.

    reductions maps span digests to integer nanoseconds removed, at most their
    original durations. Evidence documents are never edited or rehashed.
    """
    observed = build_operation_path_report(spans, trace=trace)
    order, before, after = _graph(trace)
    by_digest = {s["span_digest"]: s for s in spans}
    durations = {n: by_digest[n]["elapsed_ns"] for n in order}
    if reductions is None:
        reductions = {}
    if not isinstance(reductions, Mapping):
        raise OperationPathError("reductions must map operation span digests to nanoseconds")
    for n, amount in reductions.items():
        if n not in durations:
            raise OperationPathError("reduction references an undeclared operation")
        if type(amount) is not int or not 0 <= amount <= durations[n]:
            raise OperationPathError("reduction must be an integer between zero and original duration")
    length, count, forward, forward_count = _longest(order, before, after, durations)
    _, _, backward, backward_count = _longest(list(reversed(order)), after, before, durations)
    nodes = []
    for n in sorted(order):
        through = forward[n] + backward[n] - durations[n]
        critical_count = forward_count[n] * backward_count[n] if through == length else 0
        removed = dict(durations)
        removed[n] = 0
        reduced_length = _longest(order, before, after, removed)[0]
        nodes.append({
            "span_digest": n, "span_id": by_digest[n]["span_id"],
            "duration_ns": durations[n], "longest_path_through_ns": through,
            "path_gap_ns": length - through, "critical_path_count_through": critical_count,
            "on_every_critical_path": critical_count == count,
            "full_removal_benefit_ns": length - reduced_length,
        })
    proposed = {n: duration - reductions.get(n, 0) for n, duration in durations.items()}
    proposed_length, proposed_count, _, _ = _longest(order, before, after, proposed)
    core = {
        "schema": "in-formation.operation-path-sensitivity/0.1",
        "observed_report_digest": observed["report_digest"], "trace_digest": trace["trace_digest"],
        "baseline_dependency_path_ns": length, "critical_path_count": count, "nodes": nodes,
        "reductions_ns": dict(sorted(reductions.items())),
        "counterfactual_dependency_path_ns": proposed_length,
        "counterfactual_critical_path_count": proposed_count,
        "counterfactual_benefit_ns": length - proposed_length,
        "interpretation_limits": list(LIMITS),
    }
    return {**core, "report_digest": _digest(core)}


def validate_sensitivity_report(report, spans, *, trace):
    if not isinstance(report, Mapping):
        raise OperationPathError("sensitivity report must be a mapping")
    rebuilt = build_sensitivity_report(spans, trace=trace, reductions=report.get("reductions_ns"))
    # Canonical bytes distinguish JSON booleans from numeric 0/1.
    if _digest(dict(report)) != _digest(rebuilt):
        raise OperationPathError("sensitivity report differs from source reconstruction")
    return rebuilt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spans", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--reductions", help="JSON object mapping span digests to ns removed")
    args = parser.parse_args()
    try:
        trace = json.loads(Path(args.trace).read_text(encoding="utf-8"))
        reductions = json.loads(Path(args.reductions).read_text(encoding="utf-8")) if args.reductions else {}
        report = build_sensitivity_report(load_operation_span_artifact(args.spans), trace=trace, reductions=reductions)
        print(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
