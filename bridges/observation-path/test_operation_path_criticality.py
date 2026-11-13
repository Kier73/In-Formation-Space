from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from operation_path_criticality import (
    OperationPathError,
    build_operation_path_report,
    build_operation_path_trace,
    validate_operation_path_report,
)


def span(*, attempt="attempt-1", span_id, operation_id, start, end, actor="host-a", segment="run-1", outcome="succeeded"):
    core = {
        "format": "in-formation.operation-span",
        "schema": "in-formation.operation-span/0.1",
        "attempt_id": attempt,
        "span_id": span_id,
        "operation_id": operation_id,
        "clock_actor_id": actor,
        "clock_segment_id": segment,
        "monotonic_start_ns": start,
        "monotonic_end_ns": end,
        "elapsed_ns": end - start,
        "clock_status": "measured",
        "outcome": outcome,
        "exception_type": None if outcome == "succeeded" else "builtins.RuntimeError",
        "context": {"fixture": "operation-path-criticality"},
        "measurement_scope": (
            "Elapsed monotonic time between the recorder's immediately-before and "
            "immediately-after samples around one synchronous callable invocation; "
            "includes blocking within the call and excludes later work."
        ),
    }
    encoded = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return {**core, "span_digest": hashlib.sha256(encoded).hexdigest()}


def fixture(spans, root, nodes, edges):
    trace = build_operation_path_trace(
        path_id="path-1",
        attempt_id="attempt-1",
        root_span_digest=root["span_digest"],
        operation_span_digests=[item["span_digest"] for item in nodes],
        must_complete_before=[
            {"predecessor_span_digest": before["span_digest"], "successor_span_digest": after["span_digest"]}
            for before, after in edges
        ],
    )
    return build_operation_path_report(spans, trace=trace), trace


class OperationPathCriticalityTests(unittest.TestCase):
    def test_serial_path_separates_measured_work_from_root_slack(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=31)
        a = span(span_id="encode", operation_id="encode", start=2, end=7)
        b = span(span_id="send", operation_id="send", start=7, end=17)
        c = span(span_id="commit", operation_id="commit", start=19, end=31)
        telemetry = span(span_id="telemetry", operation_id="telemetry", start=10, end=12)
        report, trace = fixture([root, a, b, c, telemetry], root, [a, b, c, telemetry], [(a, b), (b, c)])
        self.assertEqual(report["aggregate_operation_ns"], 29)
        self.assertEqual(report["known_dependency_path_ns"], 27)
        self.assertEqual(report["known_dependency_path_span_ids"], ["encode", "send", "commit"])
        self.assertEqual(report["root_elapsed_ns"], 31)
        self.assertEqual(report["root_slack_ns"], 4)
        self.assertEqual(report["noncritical_aggregate_ns"], 2)
        self.assertEqual(validate_operation_path_report(report, [root, a, b, c, telemetry], trace=trace), report)

    def test_parallel_fork_join_allows_aggregate_work_to_exceed_wall_envelope(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=20)
        a = span(span_id="worker-a", operation_id="worker.compute", start=0, end=10)
        b = span(span_id="worker-b", operation_id="worker.compute", start=0, end=10)
        join = span(span_id="join", operation_id="receiver.join", start=10, end=20)
        report, _ = fixture([root, a, b, join], root, [a, b, join], [(a, join), (b, join)])
        self.assertEqual(report["aggregate_operation_ns"], 30)
        self.assertEqual(report["known_dependency_path_ns"], 20)
        self.assertEqual(report["root_slack_ns"], 0)
        self.assertEqual(report["noncritical_aggregate_ns"], 10)
        self.assertEqual(report["known_dependency_path_span_ids"], ["worker-a", "join"])

    def test_independent_operations_do_not_become_causal_just_because_time_is_ordered(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=30)
        first = span(span_id="first", operation_id="sensor.read", start=1, end=5)
        second = span(span_id="second", operation_id="sensor.write", start=18, end=28)
        report, _ = fixture([root, first, second], root, [first, second], [])
        self.assertEqual(report["known_dependency_path_ns"], 10)
        self.assertEqual(report["dependency_count"], 0)
        self.assertIn("timestamp order alone never creates a causal edge", " ".join(report["interpretation_limits"]))

    def test_declared_dependency_must_be_consistent_with_local_intervals(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=30)
        first = span(span_id="first", operation_id="first", start=1, end=12)
        second = span(span_id="second", operation_id="second", start=8, end=20)
        with self.assertRaisesRegex(OperationPathError, "not supported"):
            fixture([root, first, second], root, [first, second], [(first, second)])

    def test_cross_actor_or_segment_aggregation_is_refused(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=30)
        remote = span(span_id="remote", operation_id="remote.call", start=1, end=10, actor="host-b")
        with self.assertRaisesRegex(OperationPathError, "cross-clock aggregation"):
            fixture([root, remote], root, [remote], [])
        other_segment = span(span_id="restart", operation_id="restart.call", start=1, end=10, segment="run-2")
        with self.assertRaisesRegex(OperationPathError, "cross-clock aggregation"):
            fixture([root, other_segment], root, [other_segment], [])

    def test_root_must_enclose_every_operation(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=10)
        outside = span(span_id="outside", operation_id="outside", start=8, end=12)
        with self.assertRaisesRegex(OperationPathError, "enclose"):
            fixture([root, outside], root, [outside], [])

    def test_unmeasured_operation_cannot_enter_duration_analysis(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=20)
        unmeasured = span(span_id="bad", operation_id="operation", start=2, end=10)
        unmeasured["clock_status"] = "regressed"
        unmeasured["monotonic_start_ns"] = 10
        unmeasured["monotonic_end_ns"] = 2
        unmeasured["elapsed_ns"] = None
        core = {k: v for k, v in unmeasured.items() if k != "span_digest"}
        encoded = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        unmeasured["span_digest"] = hashlib.sha256(encoded).hexdigest()
        with self.assertRaisesRegex(OperationPathError, "measured monotonic duration"):
            fixture([root, unmeasured], root, [unmeasured], [])

    def test_cycle_is_rejected(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=20)
        a = span(span_id="a", operation_id="a", start=1, end=5)
        b = span(span_id="b", operation_id="b", start=5, end=9)
        with self.assertRaises(OperationPathError):
            fixture([root, a, b], root, [a, b], [(a, b), (b, a)])

    def test_unknown_or_extra_source_spans_are_rejected(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=20)
        a = span(span_id="a", operation_id="a", start=1, end=5)
        trace = build_operation_path_trace(
            path_id="path-1", attempt_id="attempt-1",
            root_span_digest=root["span_digest"],
            operation_span_digests=[a["span_digest"]],
            must_complete_before=[],
        )
        extra = span(span_id="extra", operation_id="extra", start=6, end=9)
        with self.assertRaisesRegex(OperationPathError, "exactly"):
            build_operation_path_report([root, a, extra], trace=trace)

    def test_reconstruction_rejects_rehashed_report_forgery(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=20)
        a = span(span_id="a", operation_id="a", start=1, end=9)
        report, trace = fixture([root, a], root, [a], [])
        forged = copy.deepcopy(report)
        forged["root_slack_ns"] += 1
        core = {k: v for k, v in forged.items() if k != "report_digest"}
        encoded = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        forged["report_digest"] = hashlib.sha256(encoded).hexdigest()
        with self.assertRaisesRegex(OperationPathError, "independent source-span reconstruction"):
            validate_operation_path_report(forged, [root, a], trace=trace)

    def test_trace_tampering_is_rejected(self):
        root = span(span_id="root", operation_id="path.root", start=0, end=20)
        a = span(span_id="a", operation_id="a", start=1, end=9)
        trace = build_operation_path_trace(
            path_id="path-1", attempt_id="attempt-1",
            root_span_digest=root["span_digest"],
            operation_span_digests=[a["span_digest"]],
            must_complete_before=[],
        )
        trace["path_id"] = "altered"
        with self.assertRaisesRegex(OperationPathError, "canonical or its digest"):
            build_operation_path_report([root, a], trace=trace)


if __name__ == "__main__":
    unittest.main()
