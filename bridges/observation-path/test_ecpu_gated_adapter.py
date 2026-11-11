import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from ecpu_gated_adapter import ECPUGatedObservationAdapter
from observation_path import ObservationIntent, ObservationPath


@dataclass(frozen=True)
class FakeDecision:
    kind: str = "phase"
    logical_time: int = 7
    status: str = "AUTHORIZED"
    quorum: int = 2
    observed_sources: tuple = ("A", "B")
    dissenting_sources: tuple = ()
    missing_sources: tuple = ()
    canonical_payload: tuple = ("phase", 7, 1)
    strict: bool = True


class FakeObservation:
    kind = "phase"
    logical_time = 7
    source = "A"

    def register_values(self, prefix="substrate"):
        return {f"{prefix}_quadrant": 1}


class FakeBackend:
    def __init__(self, registers=None):
        self.registers = dict(registers or {})

    def read_register(self, name):
        if name not in self.registers:
            raise KeyError(name)
        return self.registers[name]


class FakeSenderChannel:
    def __init__(self, source, channel, pending):
        self.source = source
        self.channel = channel
        self._pending = set(pending)

    def pending_sequences(self):
        return tuple(sorted(self._pending))


class FakeCoordinator:
    def __init__(self, *, decision=None, snapshot=None, registers=None, checkpoint_digest=None, ack_results=None):
        self.decision = decision or FakeDecision()
        self.state = snapshot or coordinator_snapshot()
        self.vm = SimpleNamespace(
            scheduler=SimpleNamespace(
                tasks={42: SimpleNamespace(backend=FakeBackend(registers or {"phase_quadrant": 1}))}
            ),
            snapshot=lambda: vm_snapshot(),
        )
        self.commit_calls = 0
        self.checkpoint_digest = checkpoint_digest or ("b" * 64)
        self.ack_results = ack_results or {"A": (3, 8), "B": (5,)}
        self.ack_calls = 0

    def process_acks(self, sender_channels):
        self.ack_calls += 1
        removed = {}
        for source, channel in sender_channels.items():
            sequences = tuple(self.ack_results.get(source, ()))
            channel._pending.difference_update(sequences)
            removed[source] = sequences
        return removed

    def finalize_event(self, kind, logical_time):
        return self.decision

    def commit_event(self, kind, logical_time, checkpoint_path):
        self.commit_calls += 1
        return self.decision

    def snapshot(self):
        return self.state

    def save_checkpoint(self, checkpoint_path):
        return self.checkpoint_digest


def links():
    return [
        {
            "source": "A", "channel": "phase-A", "sequence": 3,
            "payload": ["phase", "A", 7, 1],
        },
        {
            "source": "B", "channel": "phase-B", "sequence": 5,
            "payload": ["phase", "B", 7, 1],
        },
    ]


def coordinator_snapshot(status="AUTHORIZED"):
    representative = links()[0]
    return {
        "target_pid": 42,
        "register_prefix": "phase",
        "policy_consensus": {
            "policy": {
                "kind": "phase",
                "allowed_sources": ["A", "B"],
                "quorum": 2,
                "strict": True,
            },
            "finalized": [{"kind": "phase", "logical_time": 7, "status": status}],
        },
        "links": [{"kind": "phase", "logical_time": 7, "sources": links()}],
        "representatives": (
            [{"kind": "phase", "logical_time": 7, "link": representative}]
            if status == "AUTHORIZED" else []
        ),
        "applied": (
            [{"kind": "phase", "logical_time": 7, "link": representative}]
            if status == "AUTHORIZED" else []
        ),
        "consumed": (
            [{"kind": "phase", "logical_time": 7, "sources": ["A", "B"]}]
            if status == "AUTHORIZED" else []
        ),
        # E-CPU retains an empty per-event consume-intent bucket after commit.
        "consume_intents": [{"kind": "phase", "logical_time": 7, "links": []}],
        "apply_intents": [],
    }


def vm_snapshot():
    return {
        "resolver_observation_receipts": [
            {
                "pid": 42,
                "source": "A",
                "sequence": 3,
                "payload": ["phase", "A", 7, 1],
            }
        ]
    }


def decode_observation(payload):
    if list(payload) != ["phase", "A", 7, 1]:
        raise ValueError("unexpected typed observation payload")
    return FakeObservation()


def make_path():
    path = ObservationPath(ObservationIntent(
        attempt_id="attempt-ecpu-01",
        candidate_name="phase-stream",
        query="What is the authorized phase quadrant?",
        hypothesis_set_digest="sha256:prior-hypotheses",
        estimated_cost=1.0,
        authority_required=True,
        application_required=True,
        sender_ack_required=True,
    ))
    path.append("dispatched", "host", evidence_ref="transport/dispatch.json")
    path.append("admitted", "ecpu-receiver", evidence_ref="receiver/intake.json")
    path.append(
        "returned",
        "ecpu-observation",
        evidence_ref="encounters/phase-7.json",
        details={
            "encounter_id": "phase-7",
            "payload_digest": "sha256:raw-phase-7",
            "canonicalization": "utf8-raw-v1",
        },
    )
    return path


class ECPUGatedObservationAdapterTests(unittest.TestCase):
    def test_authorization_then_verified_commit_records_two_distinct_stages(self):
        coordinator = FakeCoordinator()
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()

        decision_record = adapter.record_finalized_decision(
            path, "phase", 7, decision_ref="consensus/phase-7.json"
        )
        self.assertEqual(decision_record.status, "AUTHORIZED")
        self.assertEqual(decision_record.representative_source, "A")
        self.assertEqual(path.status, "evidence_authorized")

        application = adapter.record_application_commit(
            path, "phase", 7, "/tmp/checkpoints/phase-7.json",
            checkpoint_ref="checkpoints/phase-7.json",
        )
        self.assertEqual(coordinator.commit_calls, 1)
        self.assertEqual(path.status, "applied")
        self.assertEqual(application.target_pid, 42)
        self.assertEqual(application.representative_source, "A")
        self.assertEqual(application.representative_sequence, 3)
        self.assertEqual(application.checkpoint_digest, "b" * 64)
        self.assertEqual(
            path.events[-1].details["projection_digest"],
            application.projection_digest,
        )
        sender_channels = {
            "A": FakeSenderChannel("A", "phase-A", (3, 8)),
            "B": FakeSenderChannel("B", "phase-B", (5,)),
        }
        ack = adapter.record_sender_acknowledgements(
            path,
            "phase",
            7,
            sender_channels,
            acknowledgement_ref="sender-acks/phase-7.json",
        )
        self.assertEqual(coordinator.ack_calls, 1)
        self.assertEqual(path.status, "sender_acknowledged")
        self.assertEqual(ack.acknowledged_sources, ("A", "B"))
        self.assertEqual(
            set(ack.expected_event_sequences),
            {("A", "phase-A", 3), ("B", "phase-B", 5)},
        )
        self.assertIn(("A", "phase-A", 8), ack.acknowledged_sequences)
        self.assertEqual(sender_channels["A"].pending_sequences(), ())
        self.assertEqual(sender_channels["B"].pending_sequences(), ())

    def test_consensus_refusal_is_recorded_without_application(self):
        decision = FakeDecision(
            status="CONFLICT",
            dissenting_sources=("B",),
            canonical_payload=("phase", 7, 1),
        )
        coordinator = FakeCoordinator(
            decision=decision,
            snapshot=coordinator_snapshot(status="CONFLICT"),
        )
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()

        result = adapter.record_finalized_decision(
            path, "phase", 7,
            decision_ref="consensus/phase-7-conflict.json",
            refusal_reason="configured sources disagreed",
        )
        self.assertEqual(result.status, "CONFLICT")
        self.assertEqual(path.status, "evidence_refused")
        self.assertTrue(path.terminal)
        self.assertEqual(coordinator.commit_calls, 0)

    def test_unfinalized_decision_is_not_recorded_as_authorized(self):
        decision = FakeDecision(status="QUORUM")
        coordinator = FakeCoordinator(decision=decision)
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        with self.assertRaises(ValueError):
            adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/pending.json")
        self.assertEqual(path.status, "returned")

    def test_commit_requires_exact_applied_representative_marker(self):
        snapshot = coordinator_snapshot()
        snapshot["applied"] = []
        coordinator = FakeCoordinator(snapshot=snapshot)
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        with self.assertRaises(ValueError):
            adapter.record_application_commit(
                path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
            )
        self.assertEqual(path.status, "evidence_authorized")

    def test_commit_requires_all_receiver_sources_consumed(self):
        snapshot = coordinator_snapshot()
        snapshot["consumed"] = [{"kind": "phase", "logical_time": 7, "sources": ["A"]}]
        coordinator = FakeCoordinator(snapshot=snapshot)
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        with self.assertRaises(ValueError):
            adapter.record_application_commit(
                path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
            )

    def test_commit_requires_vm_idempotence_receipt(self):
        coordinator = FakeCoordinator()
        coordinator.vm.snapshot = lambda: {"resolver_observation_receipts": []}
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        with self.assertRaises(ValueError):
            adapter.record_application_commit(
                path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
            )

    def test_commit_requires_register_readback_to_match_typed_projection(self):
        coordinator = FakeCoordinator(registers={"phase_quadrant": 3})
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        with self.assertRaises(ValueError):
            adapter.record_application_commit(
                path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
            )
        self.assertEqual(path.status, "evidence_authorized")

    def test_commit_rejects_unresolved_checkpoint_intent(self):
        snapshot = coordinator_snapshot()
        snapshot["apply_intents"] = [{"kind": "phase", "logical_time": 7, "link": links()[0]}]
        coordinator = FakeCoordinator(snapshot=snapshot)
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        with self.assertRaises(ValueError):
            adapter.record_application_commit(
                path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
            )

    def test_checkpoint_digest_must_be_sha256(self):
        coordinator = FakeCoordinator(checkpoint_digest="not-a-digest")
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        with self.assertRaises(ValueError):
            adapter.record_application_commit(
                path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
            )

    def test_observed_source_set_must_match_evidence_links(self):
        decision = FakeDecision(observed_sources=("A",))
        coordinator = FakeCoordinator(decision=decision)
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        with self.assertRaises(ValueError):
            adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")


    def test_commit_must_match_the_exact_policy_decision_already_recorded(self):
        coordinator = FakeCoordinator()
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        coordinator.decision = FakeDecision(canonical_payload=("phase", 7, 2))
        with self.assertRaises(ValueError):
            adapter.record_application_commit(
                path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
            )
        self.assertEqual(path.status, "evidence_authorized")

    def test_adapter_application_path_is_portable_schema_valid(self):
        import json
        from pathlib import Path
        from validate_observation_path import validate_path_record

        coordinator = FakeCoordinator()
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        adapter.record_application_commit(
            path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
        )
        schema_path = Path(__file__).with_name("observation-path.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validate_path_record(path.to_dict(), schema)


    def test_sender_acknowledgement_requires_every_event_sequence_to_be_removed(self):
        coordinator = FakeCoordinator(ack_results={"A": (), "B": (5,)})
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        adapter.record_application_commit(
            path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
        )
        sender_channels = {
            "A": FakeSenderChannel("A", "phase-A", (3,)),
            "B": FakeSenderChannel("B", "phase-B", (5,)),
        }
        partial = adapter.record_sender_acknowledgements(
            path, "phase", 7, sender_channels,
            acknowledgement_ref="sender-acks/partial.json",
        )
        self.assertFalse(partial.complete)
        self.assertEqual(partial.status, "sender_ack_progress")
        self.assertEqual(partial.missing_event_sequences, (("A", "phase-A", 3),))
        self.assertEqual(path.status, "sender_ack_progress")
        self.assertEqual(sender_channels["A"].pending_sequences(), (3,))
        self.assertEqual(sender_channels["B"].pending_sequences(), ())

        coordinator.ack_results = {"A": (3,), "B": ()}
        complete = adapter.record_sender_acknowledgements(
            path, "phase", 7, sender_channels,
            acknowledgement_ref="sender-acks/complete.json",
        )
        self.assertTrue(complete.complete)
        self.assertEqual(complete.status, "sender_acknowledged")
        self.assertEqual(complete.missing_event_sequences, ())
        self.assertEqual(path.status, "sender_acknowledged")
        self.assertEqual(sender_channels["A"].pending_sequences(), ())
        self.assertEqual(sender_channels["B"].pending_sequences(), ())

    def test_sender_acknowledgement_requires_declared_intent(self):
        coordinator = FakeCoordinator()
        adapter = ECPUGatedObservationAdapter(coordinator, decode_observation)
        path = make_path()
        adapter.record_finalized_decision(path, "phase", 7, decision_ref="consensus/phase-7.json")
        adapter.record_application_commit(
            path, "phase", 7, "/tmp/phase-7.json", checkpoint_ref="checkpoints/phase-7.json"
        )
        path.intent = ObservationIntent(
            attempt_id="attempt-ecpu-01",
            candidate_name="phase-stream",
            query="What is the authorized phase quadrant?",
            hypothesis_set_digest="sha256:prior-hypotheses",
            estimated_cost=1.0,
            authority_required=True,
            application_required=True,
            sender_ack_required=False,
        )
        with self.assertRaises(ValueError):
            adapter.record_sender_acknowledgements(
                path, "phase", 7,
                {
                    "A": FakeSenderChannel("A", "phase-A", (3,)),
                    "B": FakeSenderChannel("B", "phase-B", (5,)),
                },
                acknowledgement_ref="sender-acks/not-required.json",
            )

if __name__ == "__main__":
    unittest.main()
