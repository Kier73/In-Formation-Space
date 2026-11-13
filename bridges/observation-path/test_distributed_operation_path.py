from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
TEMPORAL = HERE.parent / "temporal-provenance"
if str(TEMPORAL) not in sys.path:
    sys.path.insert(0, str(TEMPORAL))

from operation_spans import OperationSpanRecorder
from distributed_operation_path import (
    DistributedOperationPathError,
    build_causal_handoff_witness,
    build_distributed_operation_path_report,
    build_distributed_operation_path_trace,
    build_handoff_payload,
    clock_domain_id,
    validate_distributed_operation_path_report,
)
from clock_calibration import build_affine_calibration
from mailcpu.reliability import ReliabilityPolicy, ReliableChannel
from mailcpu.temporal import ClockDomain, CausalStamp, TemporalContext, TemporalProfile
from mailcpu.transport import InMemoryTransport


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


class FakeClock:
    def __init__(self, values):
        self.values = deque(values)

    def __call__(self):
        if not self.values:
            raise RuntimeError("fake clock exhausted")
        return self.values.popleft()


def operation_span(actor, segment, span_id, operation_id, start, end):
    recorder = OperationSpanRecorder(
        clock_actor_id=actor,
        clock_segment_id=str(segment),
        clock_ns=FakeClock([start, end]),
    )
    recorder.measure(
        attempt_id="attempt-1",
        span_id=span_id,
        operation_id=operation_id,
        operation=lambda: None,
    )
    return recorder.spans[0]


def frame(actor, segment, elapsed, lamport, vector):
    return {
        "actor_id": actor,
        "monotonic": {"actor_id": actor, "segment": segment, "elapsed_ns": elapsed},
        "wall": None,
        "causal": {"actor_id": actor, "lamport": lamport, "vector": vector},
        "scheduler": None,
        "event_lambda": None,
        "chronon_phase": None,
        "chemical_tau": None,
    }


def calibration(source_actor, source_segment, target_actor, target_segment, *, scale_low=1.0, scale_high=1.0):
    source_id = clock_domain_id(source_actor, str(source_segment))
    target_id = clock_domain_id(target_actor, str(target_segment))
    # Synthetic anchors exercise the numerical feasible-set adapter. The
    # calibration implementation does not fetch or authenticate these witnesses.
    anchors = [
        {
            "anchor_id": "anchor-0",
            "source_coordinate": 0,
            "target_lower": 0.0,
            "target_upper": 0.0,
            "correlation_basis": "shared_trigger",
            "witness_ref": f"synthetic:{source_actor}:{target_actor}:0",
            "witness_sha256": digest({"anchor": 0, "source": source_actor, "target": target_actor}),
        },
        {
            "anchor_id": "anchor-1",
            "source_coordinate": 1000,
            "target_lower": 1000.0 * scale_low,
            "target_upper": 1000.0 * scale_high,
            "correlation_basis": "shared_trigger",
            "witness_ref": f"synthetic:{source_actor}:{target_actor}:1",
            "witness_sha256": digest({"anchor": 1, "source": source_actor, "target": target_actor}),
        },
    ]
    return build_affine_calibration(
        calibration_id=f"{source_actor}-to-{target_actor}",
        source_clock_id=source_id,
        target_clock_id=target_id,
        source_unit="ns",
        target_unit="ns",
        anchors=anchors,
        validity_source_min=0,
        validity_source_max=1000,
    )


def make_handoff(path, predecessor, successor, channel, seq, sender_frame, receiver_frame):
    payload = build_handoff_payload(
        path_id=path,
        attempt_id="attempt-1",
        predecessor_span_digest=predecessor["span_digest"],
        sender_completion_frame=sender_frame,
    )
    return build_causal_handoff_witness(
        payload=payload,
        successor_span_digest=successor["span_digest"],
        channel_id=channel,
        message_sequence=seq,
        received_sequence=seq,
        receiver_start_frame=receiver_frame,
    )


def build_trace(spans, reference_actor, reference_segment, local=(), handoffs=(), calibrations=()):
    return build_distributed_operation_path_trace(
        path_id="path-1",
        attempt_id="attempt-1",
        span_documents=spans,
        reference_clock_actor_id=reference_actor,
        reference_clock_segment_id=str(reference_segment),
        local_dependencies=[
            {"predecessor_span_digest": a["span_digest"], "successor_span_digest": b["span_digest"]}
            for a, b in local
        ],
        causal_handoffs=list(handoffs),
        clock_calibrations=list(calibrations),
    )


class DistributedOperationPathTests(unittest.TestCase):
    def test_real_ecpu_reliable_channel_and_temporal_context_produce_handoff(self):
        profile = TemporalProfile(frozenset({ClockDomain.MONOTONIC, ClockDomain.CAUSAL}))
        sender_clock = FakeClock([0, 10, 20, 21])
        receiver_clock = FakeClock([0, 1, 2, 32])
        sender_context = TemporalContext("host-a", profile, monotonic_ns=sender_clock, segment=0)
        receiver_context = TemporalContext("host-b", profile, monotonic_ns=receiver_clock, segment=0)

        sender_meter = OperationSpanRecorder(
            clock_actor_id="host-a", clock_segment_id="0", clock_ns=sender_clock
        )
        sender_meter.measure(
            attempt_id="attempt-1", span_id="send-work", operation_id="compute.prepare",
            operation=lambda: "prepared",
        )
        sender_span = sender_meter.spans[0]
        sender_context.emit_causal_stamp()
        sender_frame = sender_context.observe().to_dict()

        payload = build_handoff_payload(
            path_id="path-1",
            attempt_id="attempt-1",
            predecessor_span_digest=sender_span["span_digest"],
            sender_completion_frame=sender_frame,
        )
        transport = InMemoryTransport()
        policy = ReliabilityPolicy(lease_ticks=1, max_attempts=4, window_size=2)
        sender_channel = ReliableChannel(
            transport, "host-a", "host-b", "operation-path", policy, peer="host-b"
        )
        receiver_channel = ReliableChannel(
            transport, "host-b", "host-b", "operation-path", policy, peer="host-a"
        )
        sent_sequence = sender_channel.send(payload)
        received = receiver_channel.receive()
        self.assertIsNotNone(received)
        received_sequence, received_payload = received
        self.assertEqual(received_payload, payload)
        receiver_context.receive_causal_stamp(CausalStamp.from_dict(received_payload["sender_completion_frame"]["causal"]))
        receiver_frame = receiver_context.observe().to_dict()

        receiver_meter = OperationSpanRecorder(
            clock_actor_id="host-b", clock_segment_id="0", clock_ns=receiver_clock
        )
        receiver_meter.measure(
            attempt_id="attempt-1", span_id="receive-work", operation_id="compute.finish",
            operation=lambda: "finished",
        )
        receiver_span = receiver_meter.spans[0]
        self.assertEqual(sender_channel.process_ack(), (sent_sequence,))

        handoff = build_causal_handoff_witness(
            payload=received_payload,
            successor_span_digest=receiver_span["span_digest"],
            channel_id="operation-path",
            message_sequence=sent_sequence,
            received_sequence=received_sequence,
            receiver_start_frame=receiver_frame,
        )
        clock_cal = calibration("host-a", 0, "host-b", 0)
        trace = build_trace([sender_span, receiver_span], "host-b", 0, handoffs=[handoff], calibrations=[clock_cal])
        report = build_distributed_operation_path_report(
            [sender_span, receiver_span], trace=trace, clock_calibrations=[clock_cal]
        )
        self.assertEqual(report["causal_handoff_count"], 1)
        self.assertEqual(report["critical_path_lower_ns"], 40)
        self.assertEqual(report["critical_path_upper_ns"], 40)
        self.assertEqual(report["causal_evidence_status"], "vector_clock_consistent_unverified_transport")

    def test_three_host_path_uses_partial_order_and_mixed_calibration_intervals(self):
        a = operation_span("host-a", 0, "a", "encode", 10, 20)
        b = operation_span("host-b", 0, "b", "transform", 30, 50)
        c = operation_span("host-c", 2, "c", "commit", 70, 90)
        ab = make_handoff(
            "path-1", a, b, "a-to-b", 4,
            frame("host-a", 0, 21, 1, {"host-a": 1}),
            frame("host-b", 0, 30, 2, {"host-a": 1, "host-b": 1}),
        )
        bc = make_handoff(
            "path-1", b, c, "b-to-c", 2,
            frame("host-b", 0, 51, 3, {"host-a": 1, "host-b": 2}),
            frame("host-c", 2, 70, 4, {"host-a": 1, "host-b": 2, "host-c": 1}),
        )
        cal_a = calibration("host-a", 0, "host-b", 0, scale_low=1.0, scale_high=1.0)
        cal_c = calibration("host-c", 2, "host-b", 0, scale_low=0.99, scale_high=1.01)
        trace = build_trace([a, b, c], "host-b", 0, handoffs=[ab, bc], calibrations=[cal_a, cal_c])
        report = build_distributed_operation_path_report(
            [a, b, c], trace=trace, clock_calibrations=[cal_a, cal_c]
        )
        self.assertEqual(report["critical_path_lower_span_digests"], [a["span_digest"], b["span_digest"], c["span_digest"]])
        self.assertEqual(report["critical_path_lower_ns"], 49)
        self.assertEqual(report["critical_path_upper_ns"], 51)
        self.assertEqual(report["critical_path_selection_status"], "same_extremal_chain")

    def test_calibration_uncertainty_can_leave_path_identity_unresolved(self):
        a = operation_span("host-a", 0, "a", "worker-a", 10, 20)
        b = operation_span("host-b", 0, "b", "worker-b", 10, 40)
        c = operation_span("host-c", 0, "c", "worker-c", 20, 40)
        handoff_ac = make_handoff(
            "path-1", a, c, "a-to-c", 1,
            frame("host-a", 0, 21, 1, {"host-a": 1}),
            frame("host-c", 0, 20, 2, {"host-a": 1, "host-c": 1}),
        )
        cal_a = calibration("host-a", 0, "host-b", 0, scale_low=0.5, scale_high=2.0)
        cal_c = calibration("host-c", 0, "host-b", 0)
        trace = build_trace([a, b, c], "host-b", 0, handoffs=[handoff_ac], calibrations=[cal_a, cal_c])
        report = build_distributed_operation_path_report(
            [a, b, c], trace=trace, clock_calibrations=[cal_a, cal_c]
        )
        self.assertEqual(report["critical_path_selection_status"], "chain_identity_uncertain_under_calibration")
        self.assertNotEqual(report["critical_path_lower_span_digests"], report["critical_path_upper_span_digests"])

    def test_concurrent_vector_stamps_are_not_accepted_as_a_handoff(self):
        a = operation_span("host-a", 0, "a", "a", 10, 20)
        b = operation_span("host-b", 0, "b", "b", 30, 40)
        handoff = make_handoff(
            "path-1", a, b, "channel", 1,
            frame("host-a", 0, 21, 2, {"host-a": 1, "host-c": 1}),
            frame("host-b", 0, 30, 2, {"host-a": 0, "host-b": 1}),
        )
        cal = calibration("host-a", 0, "host-b", 0)
        with self.assertRaisesRegex(DistributedOperationPathError, "strictly follows"):
            build_trace([a, b], "host-b", 0, handoffs=[handoff], calibrations=[cal])

    def test_sender_frame_must_follow_predecessor_completion(self):
        a = operation_span("host-a", 0, "a", "a", 10, 20)
        b = operation_span("host-b", 0, "b", "b", 30, 40)
        handoff = make_handoff(
            "path-1", a, b, "channel", 1,
            frame("host-a", 0, 19, 1, {"host-a": 1}),
            frame("host-b", 0, 30, 2, {"host-a": 1, "host-b": 1}),
        )
        cal = calibration("host-a", 0, "host-b", 0)
        with self.assertRaisesRegex(DistributedOperationPathError, "predates predecessor"):
            build_trace([a, b], "host-b", 0, handoffs=[handoff], calibrations=[cal])

    def test_receiver_frame_must_precede_successor_start(self):
        a = operation_span("host-a", 0, "a", "a", 10, 20)
        b = operation_span("host-b", 0, "b", "b", 30, 40)
        handoff = make_handoff(
            "path-1", a, b, "channel", 1,
            frame("host-a", 0, 21, 1, {"host-a": 1}),
            frame("host-b", 0, 31, 2, {"host-a": 1, "host-b": 1}),
        )
        cal = calibration("host-a", 0, "host-b", 0)
        with self.assertRaisesRegex(DistributedOperationPathError, "follows successor"):
            build_trace([a, b], "host-b", 0, handoffs=[handoff], calibrations=[cal])

    def test_same_clock_local_dependencies_use_intervals_without_vector_edges(self):
        a = operation_span("host-b", 0, "a", "stage-a", 10, 20)
        b = operation_span("host-b", 0, "b", "stage-b", 20, 40)
        trace = build_trace([a, b], "host-b", 0, local=[(a, b)])
        report = build_distributed_operation_path_report([a, b], trace=trace, clock_calibrations=[])
        self.assertEqual(report["critical_path_lower_ns"], 30)
        self.assertEqual(report["critical_path_upper_ns"], 30)

    def test_local_edge_cannot_cross_actors_or_segments(self):
        a = operation_span("host-a", 0, "a", "stage-a", 10, 20)
        b = operation_span("host-b", 0, "b", "stage-b", 20, 40)
        with self.assertRaisesRegex(DistributedOperationPathError, "same actor and segment"):
            build_trace([a, b], "host-b", 0, local=[(a, b)], calibrations=[calibration("host-a", 0, "host-b", 0)])

    def test_cycle_across_local_and_causal_edges_is_rejected(self):
        a = operation_span("host-a", 0, "a", "a", 10, 20)
        b = operation_span("host-b", 0, "b", "b", 30, 40)
        ab = make_handoff(
            "path-1", a, b, "ab", 1,
            frame("host-a", 0, 21, 1, {"host-a": 1}),
            frame("host-b", 0, 30, 2, {"host-a": 1, "host-b": 1}),
        )
        ba = make_handoff(
            "path-1", b, a, "ba", 1,
            frame("host-b", 0, 41, 3, {"host-a": 1, "host-b": 2}),
            frame("host-a", 0, 10, 4, {"host-a": 2, "host-b": 2}),
        )
        calibrations = [calibration("host-a", 0, "host-b", 0)]
        with self.assertRaisesRegex(DistributedOperationPathError, "cycle"):
            build_trace([a, b], "host-b", 0, handoffs=[ab, ba], calibrations=calibrations)

    def test_uncalibrated_clock_domain_is_rejected(self):
        a = operation_span("host-a", 0, "a", "a", 10, 20)
        b = operation_span("host-b", 0, "b", "b", 30, 40)
        with self.assertRaisesRegex(DistributedOperationPathError, "calibrations must cover"):
            build_trace([a, b], "host-b", 0)

    def test_handoff_payload_or_transport_sequence_tampering_is_rejected(self):
        a = operation_span("host-a", 0, "a", "a", 10, 20)
        b = operation_span("host-b", 0, "b", "b", 30, 40)
        handoff = make_handoff(
            "path-1", a, b, "channel", 1,
            frame("host-a", 0, 21, 1, {"host-a": 1}),
            frame("host-b", 0, 30, 2, {"host-a": 1, "host-b": 1}),
        )
        altered = copy.deepcopy(handoff)
        altered["received_sequence"] = 2
        core = {key: altered[key] for key in altered if key != "handoff_digest"}
        altered["handoff_digest"] = digest(core)
        cal = calibration("host-a", 0, "host-b", 0)
        with self.assertRaisesRegex(DistributedOperationPathError, "received sequence"):
            build_trace([a, b], "host-b", 0, handoffs=[altered], calibrations=[cal])

    def test_reconstruction_rejects_rehashed_report_forgery(self):
        a = operation_span("host-a", 0, "a", "a", 10, 20)
        b = operation_span("host-b", 0, "b", "b", 30, 40)
        handoff = make_handoff(
            "path-1", a, b, "channel", 1,
            frame("host-a", 0, 21, 1, {"host-a": 1}),
            frame("host-b", 0, 30, 2, {"host-a": 1, "host-b": 1}),
        )
        cal = calibration("host-a", 0, "host-b", 0)
        trace = build_trace([a, b], "host-b", 0, handoffs=[handoff], calibrations=[cal])
        report = build_distributed_operation_path_report([a, b], trace=trace, clock_calibrations=[cal])
        forged = copy.deepcopy(report)
        forged["critical_path_lower_ns"] += 1
        core = {key: forged[key] for key in forged if key != "report_digest"}
        forged["report_digest"] = digest(core)
        with self.assertRaisesRegex(DistributedOperationPathError, "independent reconstruction"):
            validate_distributed_operation_path_report(
                forged, [a, b], trace=trace, clock_calibrations=[cal]
            )


if __name__ == "__main__":
    unittest.main()
