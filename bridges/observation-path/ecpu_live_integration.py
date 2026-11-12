"""Live integration check against the pinned E-CPU GatedObservationCoordinator.

Run with E-CPU checked out at commit
800f94f83ffd6f527ed093c8d1c1e93e153c34f6 and its repository root on PYTHONPATH:

    PYTHONPATH=external/E-CPU python bridges/observation-path/ecpu_live_integration.py -v

This is intentionally a separate CI step from the fast duck-typed contract tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from mailcpu import (
    ClockDomain,
    DurableMailboxTransport,
    GatedObservationCoordinator,
    MailCPUVirtualMachine,
    ObservationAuthorityPolicy,
    Program,
    Instruction,
    Op,
    ReliableChannel,
    TemporalContext,
    TemporalPathTrace,
    TemporalProfile,
    TimingObservationProducer,
    decode_substrate_observation,
    load_gated_checkpoint,
)

from ecpu_gated_adapter import ECPUGatedObservationAdapter
from ecpu_temporal_binding import (
    append_missing_temporal_events,
    create_temporal_binding,
    validate_temporal_binding,
)
from analyze_temporal_binding import (
    analyze_temporal_binding,
    validate_temporal_analysis,
)
from operation_spans import (
    OperationSpanRecorder,
    build_operation_cost_profiles,
    validate_operation_cost_profiles,
    validate_operation_span,
)
from observation_path import ObservationIntent, ObservationPath
from validate_observation_path import validate_path_record


ECPU_REFERENCE_COMMIT = "800f94f83ffd6f527ed093c8d1c1e93e153c34f6"


def verify_ecpu_checkout() -> None:
    root = os.environ.get("ECPU_ROOT")
    if not root:
        raise RuntimeError("ECPU_ROOT must identify the pinned E-CPU checkout")
    actual = subprocess.check_output(
        ["git", "-C", root, "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if actual != ECPU_REFERENCE_COMMIT:
        raise RuntimeError(
            f"E-CPU checkout mismatch: expected {ECPU_REFERENCE_COMMIT}, got {actual}"
        )


class ECPULiveAdapterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_identity = os.environ.get("GITHUB_RUN_ID", f"local-{os.getpid()}")
        attempt_identity = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        cls.operation_span_recorder = OperationSpanRecorder(
            clock_actor_id="ecpu-live-integration-process",
            clock_segment_id=f"{run_identity}-{attempt_identity}",
        )

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.vm = MailCPUVirtualMachine()
        self.pid = self.vm.spawn_program(
            Program((Instruction(Op.HALT),)),
            "in-formation-observation-target",
        )
        self.transport = DurableMailboxTransport(self.root / "mailbox.log")
        self.sender_a = ReliableChannel(
            self.transport, "A", "R-A", "gate-A", peer="R-A"
        )
        self.sender_b = ReliableChannel(
            self.transport, "B", "R-B", "gate-B", peer="R-B"
        )
        receiver_a = ReliableChannel(
            self.transport, "R-A", "R-A", "gate-A", peer="A"
        )
        receiver_b = ReliableChannel(
            self.transport, "R-B", "R-B", "gate-B", peer="B"
        )
        self.coordinator = GatedObservationCoordinator(
            self.vm,
            ObservationAuthorityPolicy("timing", ("A", "B"), quorum=2, strict=True),
            {"A": receiver_a, "B": receiver_b},
            self.pid,
            "gated",
        )
        self.adapter = ECPUGatedObservationAdapter(
            self.coordinator,
            decode_substrate_observation,
            operation_span_recorder=self.operation_span_recorder,
        )

    def _measure_live_operation(
        self,
        path: ObservationPath,
        logical_time: int,
        span_name: str,
        operation_id: str,
        operation,
        context=None,
    ):
        return self.operation_span_recorder.measure(
            attempt_id=path.intent.attempt_id,
            span_id=f"direct:{logical_time}:{span_name}",
            operation_id=operation_id,
            operation=operation,
            context={"logical_time": logical_time, **(context or {})},
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def _start_path(self, attempt_id: str, logical_time: int) -> ObservationPath:
        path = ObservationPath(ObservationIntent(
            attempt_id=attempt_id,
            candidate_name="ecpu.timing-observation",
            query=f"Resolve the authorized timing symbol at logical time {logical_time}",
            hypothesis_set_digest=f"sha256:hypotheses-{logical_time}",
            estimated_cost=1.0,
            plan_ref=f"plans/timing-{logical_time}.json",
            authority_required=True,
            application_required=True,
            sender_ack_required=True,
        ))
        self.temporal_context = TemporalContext(
            "ifs-adapter-live",
            TemporalProfile(frozenset({
                ClockDomain.MONOTONIC,
                ClockDomain.WALL,
                ClockDomain.CAUSAL,
            })),
        )
        self.temporal_trace = TemporalPathTrace(path.intent.attempt_id)
        self._capture_temporal_events(path)
        return path

    def _capture_temporal_events(self, path: ObservationPath):
        """Timestamp newly recorded stages with the adapter's own typed clock profile."""
        def frame_factory(_path_event):
            # A fresh causal event marks the adapter's capture order. Monotonic
            # and wall coordinates remain local to this adapter process.
            self.temporal_context.emit_causal_stamp()
            return self.temporal_context.observe()

        self.temporal_trace = append_missing_temporal_events(
            path,
            self.temporal_trace,
            frame_factory,
        )
        return self.temporal_trace

    def _write_temporal_binding(self, path: ObservationPath, logical_time: int):
        trace_document = self.temporal_trace.to_dict()
        trace_ref = self.root / f"temporal-trace-{logical_time}.json"
        trace_ref.write_text(
            json.dumps(trace_document, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        binding = create_temporal_binding(
            path,
            self.temporal_trace,
            temporal_trace_ref=str(trace_ref),
            restore_trace=TemporalPathTrace.from_dict,
        )
        binding_document = binding.to_dict()
        binding_ref = self.root / f"temporal-binding-{logical_time}.json"
        binding_ref.write_text(
            json.dumps(binding_document, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        binding_schema = json.loads(
            (Path(__file__).with_name("temporal-path-binding.schema.json"))
            .read_text(encoding="utf-8")
        )
        import jsonschema
        jsonschema.validate(binding_document, binding_schema)
        restored_binding = validate_temporal_binding(
            binding_document,
            path,
            self.temporal_trace,
            restore_trace=TemporalPathTrace.from_dict,
        )
        self.assertEqual(restored_binding.binding_digest, binding.binding_digest)

        analysis_document = analyze_temporal_binding(binding_document)
        analysis_schema = json.loads(
            (Path(__file__).with_name("temporal-path-analysis.schema.json"))
            .read_text(encoding="utf-8")
        )
        jsonschema.validate(analysis_document, analysis_schema)
        restored_analysis = validate_temporal_analysis(analysis_document, binding_document)
        self.assertEqual(restored_analysis["analysis_digest"], analysis_document["analysis_digest"])
        analysis_ref = self.root / f"temporal-analysis-{logical_time}.json"
        analysis_ref.write_text(
            json.dumps(analysis_document, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return trace_ref, binding_ref, analysis_ref, binding, analysis_document

    def _send_and_record_raw(
        self,
        path: ObservationPath,
        observation_a,
        observation_b,
        logical_time: int,
    ):
        sequence_a = self._measure_live_operation(
            path,
            logical_time,
            "send-A",
            "ecpu.ReliableChannel.send",
            lambda: self.sender_a.send(observation_a.to_payload()),
            {"source": "A", "channel": "gate-A"},
        )
        sequence_b = self._measure_live_operation(
            path,
            logical_time,
            "send-B",
            "ecpu.ReliableChannel.send",
            lambda: self.sender_b.send(observation_b.to_payload()),
            {"source": "B", "channel": "gate-B"},
        )
        dispatch_ref = self.root / f"dispatch-{logical_time}.json"
        dispatch_ref.write_text(
            json.dumps(
                {"A": sequence_a, "B": sequence_b},
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        path.append(
            "dispatched",
            "ecpu-sender-adapter",
            evidence_ref=str(dispatch_ref),
        )
        self._capture_temporal_events(path)

        links = self._measure_live_operation(
            path,
            logical_time,
            "receiver-ingest",
            "ecpu.GatedObservationCoordinator.ingest_available",
            self.coordinator.ingest_available,
            {"receiver": "gated-observation-coordinator"},
        )
        matching_links = [
            link for link in links
            if link.event == ("timing", logical_time)
        ]
        self.assertEqual({link.source for link in matching_links}, {"A", "B"})
        link_snapshots = [link.to_snapshot() for link in matching_links]

        intake_ref = self.root / f"receiver-intake-{logical_time}.json"
        intake_document = {
            "event": {"kind": "timing", "logical_time": logical_time},
            "links": link_snapshots,
        }
        intake_ref.write_text(
            json.dumps(intake_document, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        path.append(
            "admitted",
            "ecpu-gated-receiver",
            evidence_ref=str(intake_ref),
            details={
                "event_kind": "timing",
                "logical_time": logical_time,
                "sources": ["A", "B"],
                "frames_consumed": False,
            },
        )
        self._capture_temporal_events(path)

        raw_payload = {
            "event": {"kind": "timing", "logical_time": logical_time},
            "links": link_snapshots,
        }
        raw_bytes = json.dumps(
            raw_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        payload_digest = hashlib.sha256(raw_bytes).hexdigest()
        encounter = {
            "format": "in-formation.encounter/0.1",
            "id": f"ecpu:timing:{logical_time}",
            "source": {
                "kind": "mailcpu.gated-observation",
                "name": "E-CPU durable receiver evidence links",
                "capture_method": "GatedObservationCoordinator.ingest_available",
            },
            "context": {
                "ecpu_reference_commit": ECPU_REFERENCE_COMMIT,
                "event_kind": "timing",
                "logical_time": logical_time,
            },
            "payload": {
                "media_type": "application/json",
                "value": raw_payload,
            },
            "integrity": {
                "algorithm": "sha256",
                "digest": payload_digest,
                "canonicalization": "json-sort-keys-utf8-v1",
            },
        }
        encounter_ref = self.root / f"encounter-{logical_time}.json"
        encounter_ref.write_text(
            json.dumps(encounter, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        path.append(
            "returned",
            "ecpu-observation-capture",
            evidence_ref=str(encounter_ref),
            details={
                "encounter_id": encounter["id"],
                "payload_digest": payload_digest,
                "canonicalization": "json-sort-keys-utf8-v1",
            },
        )
        self._capture_temporal_events(path)
        return encounter_ref

    def test_real_ecpu_quorum_commit_and_sender_ack_are_separate(self):
        logical_time = 30
        path = self._start_path("ecpu-live:30", logical_time)
        observation_a = TimingObservationProducer("A").observe_interval(logical_time, 35.0)
        observation_b = TimingObservationProducer("B").observe_interval(logical_time, 35.0)
        encounter_ref = self._send_and_record_raw(
            path, observation_a, observation_b, logical_time
        )
        self.assertTrue(encounter_ref.exists())
        self.assertEqual(self.vm.scheduler.tasks[self.pid].backend.read_register("gated_symbol"), 0)

        decision = self.adapter.record_finalized_decision(
            path,
            "timing",
            logical_time,
            decision_ref=str(self.root / "consensus-30.json"),
        )
        self.assertEqual(decision.status, "AUTHORIZED")
        self.assertEqual(path.status, "evidence_authorized")
        self._capture_temporal_events(path)
        self.assertEqual(self.vm.scheduler.tasks[self.pid].backend.read_register("gated_symbol"), 0)

        checkpoint = self.root / "gated-30.checkpoint"
        application = self.adapter.record_application_commit(
            path,
            "timing",
            logical_time,
            checkpoint,
            checkpoint_ref=str(checkpoint),
        )
        self.assertEqual(path.status, "applied")
        self._capture_temporal_events(path)
        self.assertTrue(checkpoint.exists())
        self.assertEqual(application.target_pid, self.pid)
        self.assertEqual(
            self.vm.scheduler.tasks[self.pid].backend.read_register("gated_symbol"),
            3,
        )

        schema = json.loads(
            (Path(__file__).with_name("observation-path.schema.json")).read_text(encoding="utf-8")
        )
        validate_path_record(path.to_dict(), schema)

        restored = load_gated_checkpoint(
            checkpoint,
            {"A": self.transport, "B": self.transport},
        )
        self.assertEqual(
            restored.vm.scheduler.tasks[self.pid].backend.read_register("gated_symbol"),
            3,
        )
        acknowledgement = self.adapter.record_sender_acknowledgements(
            path,
            "timing",
            logical_time,
            {"A": self.sender_a, "B": self.sender_b},
            acknowledgement_ref=str(self.root / "sender-acks-30.json"),
        )
        self.assertEqual(path.status, "sender_acknowledged")
        self.assertTrue(acknowledgement.complete)
        self.assertEqual(acknowledgement.status, "sender_acknowledged")
        self.assertEqual(acknowledgement.acknowledged_sources, ("A", "B"))
        self.assertEqual(
            set(acknowledgement.expected_event_sequences),
            {("A", "gate-A", 1), ("B", "gate-B", 1)},
        )
        self.assertEqual(self.sender_a.pending_sequences(), ())
        self.assertEqual(self.sender_b.pending_sequences(), ())
        self._capture_temporal_events(path)
        validate_path_record(path.to_dict(), schema)
        trace_ref, binding_ref, analysis_ref, binding, analysis = self._write_temporal_binding(path, logical_time)
        self.assertTrue(trace_ref.exists())
        self.assertTrue(binding_ref.exists())
        self.assertTrue(analysis_ref.exists())
        self.assertEqual(analysis["monotonic_total_status"], "complete")
        self.assertIsNotNone(analysis["monotonic_total_elapsed_ns"])
        self.assertEqual(len(binding.event_bindings), len(path.events))
        self.assertEqual(len(binding.intervals), len(path.events) - 1)
        self.assertTrue(all(
            interval["delta"]["causal_relation"] == "before"
            for interval in binding.intervals
        ))
        self.assertTrue(all(
            interval["delta"]["monotonic_elapsed_ns"] is not None
            and interval["delta"]["monotonic_elapsed_ns"] >= 0
            for interval in binding.intervals
        ))

    def test_real_ecpu_consensus_conflict_is_refusal_not_negative_measurement(self):
        logical_time = 31
        path = self._start_path("ecpu-live:31", logical_time)
        observation_a = TimingObservationProducer("A").observe_interval(logical_time, 35.0)
        observation_b = TimingObservationProducer("B").observe_interval(logical_time, 40.0)
        self._send_and_record_raw(path, observation_a, observation_b, logical_time)

        decision = self.adapter.record_finalized_decision(
            path,
            "timing",
            logical_time,
            decision_ref=str(self.root / "consensus-31-conflict.json"),
            refusal_reason="strict E-CPU source consensus detected conflicting payloads",
        )
        self.assertEqual(decision.status, "CONFLICT")
        self.assertEqual(path.status, "evidence_refused")
        self.assertTrue(path.terminal)
        self.assertEqual(
            self.vm.scheduler.tasks[self.pid].backend.read_register("gated_symbol"),
            0,
        )
        self.assertEqual(len(self.transport.list("R-A")), 1)
        self.assertEqual(len(self.transport.list("R-B")), 1)
        self._capture_temporal_events(path)
        trace_ref, binding_ref, analysis_ref, binding, analysis = self._write_temporal_binding(path, logical_time)
        self.assertTrue(trace_ref.exists())
        self.assertTrue(binding_ref.exists())
        self.assertTrue(analysis_ref.exists())
        self.assertEqual(analysis["event_count"], len(path.events))
        self.assertEqual(
            [event["stage"] for event in binding.event_bindings],
            [event.stage for event in path.events],
        )

    def test_zz_operation_span_profiles_preserve_live_call_boundaries(self):
        import jsonschema

        spans = list(self.operation_span_recorder.spans)
        self.assertEqual(len(spans), 11)
        for span in spans:
            validate_operation_span(span)
            jsonschema.validate(
                span,
                json.loads(
                    (Path(__file__).with_name("operation-span.schema.json"))
                    .read_text(encoding="utf-8")
                ),
            )

        profiles = build_operation_cost_profiles(spans, minimum_samples=3)
        profiles_schema = json.loads(
            (Path(__file__).with_name("operation-cost-profiles.schema.json"))
            .read_text(encoding="utf-8")
        )
        jsonschema.validate(profiles, profiles_schema)
        self.assertEqual(validate_operation_cost_profiles(profiles, spans), profiles)
        self.assertEqual(profiles["policy_effect"], "none")

        by_operation = {item["operation_id"]: item for item in profiles["profiles"]}
        send_profile = by_operation["ecpu.ReliableChannel.send"]
        self.assertEqual(send_profile["measured_sample_count"], 4)
        self.assertEqual(send_profile["readiness"], "descriptive_only")

        # The remaining stages are intentionally below the three-sample
        # threshold in this two-path smoke run. Their durations are retained,
        # but not represented as stable cost estimates.
        for operation_id in (
            "ecpu.GatedObservationCoordinator.ingest_available",
            "ecpu.GatedObservationCoordinator.finalize_event",
            "ecpu.GatedObservationCoordinator.commit_event",
            "ecpu.GatedObservationCoordinator.save_checkpoint",
            "ecpu.GatedObservationCoordinator.process_acks",
        ):
            self.assertEqual(
                by_operation[operation_id]["readiness"],
                "insufficient_samples",
            )

        output_dir = Path(os.environ.get(
            "OPERATION_SPAN_OUTPUT_DIR",
            str(self.root / "operation-span-artifacts"),
        ))
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "operation-spans-live-ci.json").write_text(
            json.dumps({"spans": spans}, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        (output_dir / "operation-cost-profiles-live-ci.json").write_text(
            json.dumps(profiles, sort_keys=True, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    verify_ecpu_checkout()
    unittest.main(verbosity=2)
