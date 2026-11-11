import hashlib
import json
import unittest
from dataclasses import dataclass

from ecpu_temporal_binding import (
    append_missing_temporal_events,
    create_temporal_binding,
    validate_temporal_binding,
)
from observation_path import ObservationIntent, ObservationPath


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FakeFrame:
    actor_id: str
    monotonic: dict
    wall: dict
    causal: dict

    def to_dict(self):
        return {
            "actor_id": self.actor_id,
            "monotonic": dict(self.monotonic),
            "wall": dict(self.wall),
            "causal": dict(self.causal),
            "scheduler": None,
            "event_lambda": None,
            "chronon_phase": None,
            "chemical_tau": None,
        }


@dataclass(frozen=True)
class FakeTemporalEvent:
    stage: str
    frame: FakeFrame
    evidence_digest: str


class FakeTemporalTrace:
    def __init__(self, path_id, events=()):
        self.path_id = path_id
        self.events = tuple(events)

    def append(self, stage, frame, evidence_digest):
        return FakeTemporalTrace(
            self.path_id,
            self.events + (FakeTemporalEvent(stage, frame, evidence_digest),),
        )

    @property
    def intervals(self):
        results = []
        for index in range(len(self.events) - 1):
            left = self.events[index]
            right = self.events[index + 1]
            results.append({
                "from_stage": left.stage,
                "to_stage": right.stage,
                "delta": {
                    "monotonic_elapsed_ns": 10 * (index + 1),
                    "wall_elapsed_ns": 100 * (index + 1),
                    "causal_relation": "before",
                    "scheduler_ticks": None,
                },
            })
        return tuple(results)

    @property
    def digest(self):
        return digest(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest=True):
        payload = {
            "schema": "mailcpu.temporal-path-trace.v1",
            "path_id": self.path_id,
            "events": [
                {
                    "stage": event.stage,
                    "frame": event.frame.to_dict(),
                    "evidence_digest": event.evidence_digest,
                }
                for event in self.events
            ],
            "intervals": [dict(item) for item in self.intervals],
        }
        if include_digest:
            payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, document):
        if document.get("schema") != "mailcpu.temporal-path-trace.v1":
            raise ValueError("bad temporal schema")
        events = []
        for item in document["events"]:
            frame = item["frame"]
            events.append(FakeTemporalEvent(
                item["stage"],
                FakeFrame(
                    frame["actor_id"],
                    frame["monotonic"],
                    frame["wall"],
                    frame["causal"],
                ),
                item["evidence_digest"],
            ))
        restored = cls(document["path_id"], events)
        expected = restored.to_dict()
        if expected != document:
            raise ValueError("trace digest or intervals mismatch")
        return restored


def make_path():
    path = ObservationPath(ObservationIntent(
        attempt_id="temporal-attempt:01",
        candidate_name="sensor.phase",
        query="What phase was authorized?",
        hypothesis_set_digest="sha256:prior",
        estimated_cost=1.0,
    ))
    path.append("dispatched", "remote-sender", evidence_ref="transport/send.json")
    path.append("admitted", "remote-receiver", evidence_ref="receiver/intake.json")
    path.append(
        "returned",
        "remote-sensor",
        evidence_ref="encounters/phase.json",
        details={
            "encounter_id": "phase-01",
            "payload_digest": "sha256:payload",
            "canonicalization": "utf8-raw-v1",
        },
    )
    return path


def make_frame(path_event):
    # The frame is sampled by the adapter, not attributed to the remote stage actor.
    index = len(path_event.details_json)  # deterministic variation for the fixture
    return FakeFrame(
        actor_id="ifs-temporal-observer",
        monotonic={"actor_id": "ifs-temporal-observer", "segment": 0, "elapsed_ns": index},
        wall={"actor_id": "ifs-temporal-observer", "utc_ns": 1_700_000_000_000 + index, "sample_index": 1},
        causal={"actor_id": "ifs-temporal-observer", "lamport": index + 1, "vector": {"ifs-temporal-observer": index + 1}},
    )


class ECPUTemporalBindingTests(unittest.TestCase):
    def test_binds_each_observation_event_to_one_typed_temporal_frame(self):
        path = make_path()
        trace = append_missing_temporal_events(
            path,
            FakeTemporalTrace(path.intent.attempt_id),
            make_frame,
        )
        binding = create_temporal_binding(
            path,
            trace,
            temporal_trace_ref="temporal/attempt-01.json",
            restore_trace=FakeTemporalTrace.from_dict,
        )
        document = binding.to_dict()

        self.assertEqual(document["attempt_id"], path.intent.attempt_id)
        self.assertEqual(len(document["event_bindings"]), len(path.events))
        self.assertEqual(
            [item["stage"] for item in document["event_bindings"]],
            [event.stage for event in path.events],
        )
        self.assertTrue(all(
            item["temporal_frame_actor_id"] == "ifs-temporal-observer"
            for item in document["event_bindings"]
        ))
        self.assertNotEqual(path.events[2].actor, document["event_bindings"][2]["temporal_frame_actor_id"])
        self.assertEqual(
            document["event_bindings"][2]["observation_event_digest"],
            digest(path.to_dict()["events"][2]),
        )
        self.assertEqual(document["intervals"], trace.to_dict()["intervals"])
        self.assertEqual(len(document["intervals"]), len(path.events) - 1)

    def test_pending_event_append_is_idempotent(self):
        path = make_path()
        trace = append_missing_temporal_events(path, FakeTemporalTrace(path.intent.attempt_id), make_frame)
        same = append_missing_temporal_events(path, trace, make_frame)
        self.assertEqual(same.to_dict(), trace.to_dict())

    def test_trace_must_match_attempt_identity_and_stage_order(self):
        path = make_path()
        with self.assertRaises(ValueError):
            create_temporal_binding(
                path,
                FakeTemporalTrace("another-attempt"),
                temporal_trace_ref="temporal/other.json",
                restore_trace=FakeTemporalTrace.from_dict,
            )

        trace = append_missing_temporal_events(path, FakeTemporalTrace(path.intent.attempt_id), make_frame)
        first = trace.events[0]
        reordered = FakeTemporalTrace(path.intent.attempt_id, (trace.events[1], first) + trace.events[2:])
        with self.assertRaises(ValueError):
            create_temporal_binding(
                path,
                reordered,
                temporal_trace_ref="temporal/reordered.json",
                restore_trace=FakeTemporalTrace.from_dict,
            )

    def test_trace_evidence_digest_must_bind_exact_path_event(self):
        path = make_path()
        trace = append_missing_temporal_events(path, FakeTemporalTrace(path.intent.attempt_id), make_frame)
        corrupted_first = FakeTemporalEvent(
            trace.events[0].stage,
            trace.events[0].frame,
            "0" * 64,
        )
        corrupted = FakeTemporalTrace(
            path.intent.attempt_id,
            (corrupted_first,) + trace.events[1:],
        )
        with self.assertRaises(ValueError):
            create_temporal_binding(
                path,
                corrupted,
                temporal_trace_ref="temporal/corrupt.json",
                restore_trace=FakeTemporalTrace.from_dict,
            )

    def test_reconstruction_rejects_binding_tampering_and_path_change(self):
        path = make_path()
        trace = append_missing_temporal_events(path, FakeTemporalTrace(path.intent.attempt_id), make_frame)
        binding = create_temporal_binding(
            path,
            trace,
            temporal_trace_ref="temporal/attempt.json",
            restore_trace=FakeTemporalTrace.from_dict,
        )
        altered = binding.to_dict()
        altered["intervals"][0]["delta"]["monotonic_elapsed_ns"] = 999
        with self.assertRaises(ValueError):
            validate_temporal_binding(
                altered,
                path,
                trace,
                restore_trace=FakeTemporalTrace.from_dict,
            )

        path.append("interpreted", "interpreter", evidence_ref="interpretation.json", details={"method": "v1"})
        with self.assertRaises(ValueError):
            validate_temporal_binding(
                binding.to_dict(),
                path,
                trace,
                restore_trace=FakeTemporalTrace.from_dict,
            )

    def test_temporal_trace_restore_verifier_is_mandatory(self):
        path = make_path()
        trace = append_missing_temporal_events(path, FakeTemporalTrace(path.intent.attempt_id), make_frame)
        document = trace.to_dict()
        document["digest"] = "0" * 64
        bad = FakeTemporalTrace.from_dict
        with self.assertRaises(ValueError):
            create_temporal_binding(
                path,
                FakeTemporalTrace.from_dict(document),
                temporal_trace_ref="temporal/bad.json",
                restore_trace=bad,
            )


if __name__ == "__main__":
    unittest.main()
