"""Live integration check against the pinned E-CPU GatedObservationCoordinator.

Run with E-CPU checked out at commit
53569e138aca51954335729cdd31b87faf73896f and its repository root on PYTHONPATH:

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
    DurableMailboxTransport,
    GatedObservationCoordinator,
    MailCPUVirtualMachine,
    ObservationAuthorityPolicy,
    Program,
    Instruction,
    Op,
    ReliableChannel,
    TimingObservationProducer,
    decode_substrate_observation,
    load_gated_checkpoint,
)

from ecpu_gated_adapter import ECPUGatedObservationAdapter
from observation_path import ObservationIntent, ObservationPath
from validate_observation_path import validate_path_record


ECPU_REFERENCE_COMMIT = "53569e138aca51954335729cdd31b87faf73896f"


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
        ))
        return path

    def _send_and_record_raw(
        self,
        path: ObservationPath,
        observation_a,
        observation_b,
        logical_time: int,
    ):
        sequence_a = self.sender_a.send(observation_a.to_payload())
        sequence_b = self.sender_b.send(observation_b.to_payload())
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

        links = self.coordinator.ingest_available()
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
        self.assertEqual(
            self.coordinator.process_acks({"A": self.sender_a, "B": self.sender_b}),
            {"A": (1,), "B": (1,)},
        )
        self.assertEqual(self.sender_a.pending_sequences(), ())
        self.assertEqual(self.sender_b.pending_sequences(), ())
        # The path stops at receiver application: sender-side ACK processing is separate.
        self.assertEqual(path.status, "applied")

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


if __name__ == "__main__":
    verify_ecpu_checkout()
    unittest.main(verbosity=2)
