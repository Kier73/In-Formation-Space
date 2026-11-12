import copy
import json
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional development dependency
    jsonschema = None

from temporal_provenance import (
    FORMAT,
    TemporalProvenanceError,
    analyze_observations,
    attach_to_encounter_envelope,
    compare_observations,
    extract_from_encounter_envelope,
    validate_observation,
    validate_temporal_frame,
)


def frame(
    actor,
    *,
    monotonic=None,
    wall=None,
    causal=None,
    scheduler=None,
    event_lambda=None,
    chronon_phase=None,
    chemical_tau=None,
):
    return {
        "actor_id": actor,
        "monotonic": monotonic,
        "wall": wall,
        "causal": causal,
        "scheduler": scheduler,
        "event_lambda": event_lambda,
        "chronon_phase": chronon_phase,
        "chemical_tau": chemical_tau,
    }


def observation(
    event_id,
    *,
    clock_id=None,
    coordinate=None,
    unit="tick",
    temporal_frame=None,
):
    local = None
    if clock_id is not None:
        local = {
            "clock_id": clock_id,
            "coordinate": coordinate,
            "unit": unit,
        }
    return {
        "format": FORMAT,
        "event_id": event_id,
        "local_counter": local,
        "temporal_frame": temporal_frame,
    }


def causal(actor, vector, lamport=None):
    return {
        "actor_id": actor,
        "lamport": max(vector.values()) if lamport is None else lamport,
        "vector": dict(vector),
    }


class TemporalFrameContractTests(unittest.TestCase):
    def test_accepts_e_cpu_temporal_frame_shape(self):
        data = frame(
            "worker-a",
            monotonic={"actor_id": "worker-a", "segment": 2, "elapsed_ns": 400},
            wall={"actor_id": "worker-a", "utc_ns": -50, "sample_index": 7},
            causal=causal("worker-a", {"worker-a": 4, "worker-b": 2}),
            scheduler={"scheduler_id": "sched-a", "tick": 12},
            event_lambda=12,
            chronon_phase=[0.0, -1.0],
            chemical_tau=0.5,
        )
        self.assertEqual(validate_temporal_frame(data), data)

    def test_rejects_frame_clock_actor_mismatch(self):
        data = frame(
            "worker-a",
            monotonic={"actor_id": "worker-b", "segment": 0, "elapsed_ns": 1},
        )
        with self.assertRaises(TemporalProvenanceError):
            validate_temporal_frame(data)

    def test_rejects_causal_vector_without_own_actor(self):
        data = frame("worker-a", causal=causal("worker-a", {"worker-b": 1}, lamport=1))
        with self.assertRaises(TemporalProvenanceError):
            validate_temporal_frame(data)

    def test_rejects_causal_counter_above_lamport_scalar(self):
        data = frame(
            "worker-a",
            causal=causal("worker-a", {"worker-a": 2}, lamport=1),
        )
        with self.assertRaises(TemporalProvenanceError):
            validate_temporal_frame(data)

    def test_rejects_non_unit_chronon_coordinate(self):
        data = frame("worker-a", chronon_phase=[2.0, 0.0])
        with self.assertRaises(TemporalProvenanceError):
            validate_temporal_frame(data)

    def test_event_must_have_at_least_one_clock_witness(self):
        with self.assertRaises(TemporalProvenanceError):
            validate_observation(observation("event-with-no-clock"))


class ClockDomainComparisonTests(unittest.TestCase):
    def test_same_local_counter_proves_only_same_clock_order(self):
        left = observation("C100", clock_id="controller:C", coordinate=100)
        right = observation("C105", clock_id="controller:C", coordinate=105)
        result = compare_observations(left, right)
        self.assertEqual(result["relations"]["local_counter"]["status"], "before")
        self.assertEqual(result["relations"]["causal"]["status"], "unobserved")
        self.assertEqual(result["relations"]["wall"]["status"], "not_used")

    def test_different_local_clocks_are_incomparable(self):
        controller = observation("C100", clock_id="controller:C", coordinate=100)
        sensor = observation("S11", clock_id="sensor:S", coordinate=11)
        result = compare_observations(controller, sensor)
        self.assertEqual(result["relations"]["local_counter"]["status"], "incomparable")
        self.assertIn("clock IDs", result["relations"]["local_counter"]["witness"])

    def test_absent_causal_stamps_are_unobserved_not_concurrent(self):
        left = observation("A", clock_id="A-clock", coordinate=1)
        right = observation("B", clock_id="B-clock", coordinate=2)
        result = compare_observations(left, right)
        self.assertEqual(result["relations"]["causal"]["status"], "unobserved")
        self.assertNotEqual(result["relations"]["causal"]["status"], "concurrent")

    def test_vector_clock_reports_concurrency_only_when_observed(self):
        left = observation(
            "A",
            temporal_frame=frame("A", causal=causal("A", {"A": 1})),
        )
        right = observation(
            "B",
            temporal_frame=frame("B", causal=causal("B", {"B": 1})),
        )
        result = compare_observations(left, right)
        self.assertEqual(result["relations"]["causal"]["status"], "concurrent")

    def test_vector_clock_preserves_happens_before(self):
        left = observation(
            "A1",
            temporal_frame=frame("A", causal=causal("A", {"A": 1})),
        )
        right = observation(
            "B2",
            temporal_frame=frame("B", causal=causal("B", {"A": 1, "B": 1})),
        )
        self.assertEqual(compare_observations(left, right)["relations"]["causal"]["status"], "before")

    def test_monotonic_subtraction_requires_same_actor_and_segment(self):
        a = observation(
            "A0",
            temporal_frame=frame(
                "A", monotonic={"actor_id": "A", "segment": 0, "elapsed_ns": 10}
            ),
        )
        b = observation(
            "A1",
            temporal_frame=frame(
                "A", monotonic={"actor_id": "A", "segment": 0, "elapsed_ns": 30}
            ),
        )
        restored = observation(
            "A2",
            temporal_frame=frame(
                "A", monotonic={"actor_id": "A", "segment": 1, "elapsed_ns": 40}
            ),
        )
        self.assertEqual(compare_observations(a, b)["relations"]["monotonic"]["status"], "before")
        self.assertEqual(compare_observations(a, restored)["relations"]["monotonic"]["status"], "incomparable")

    def test_scheduler_ticks_are_scoped_to_scheduler_id(self):
        a = observation(
            "a",
            temporal_frame=frame("a", scheduler={"scheduler_id": "vm-a", "tick": 10}),
        )
        b = observation(
            "b",
            temporal_frame=frame("b", scheduler={"scheduler_id": "vm-b", "tick": 11}),
        )
        self.assertEqual(compare_observations(a, b)["relations"]["scheduler"]["status"], "incomparable")

    def test_wall_clock_offset_does_not_override_vector_concurrency(self):
        a = observation(
            "a",
            temporal_frame=frame(
                "a",
                wall={"actor_id": "a", "utc_ns": 900_000, "sample_index": 1},
                causal=causal("a", {"a": 1}),
            ),
        )
        b = observation(
            "b",
            temporal_frame=frame(
                "b",
                wall={"actor_id": "b", "utc_ns": 100_000, "sample_index": 1},
                causal=causal("b", {"b": 1}),
            ),
        )
        result = compare_observations(a, b)
        self.assertEqual(result["relations"]["causal"]["status"], "concurrent")
        self.assertEqual(result["relations"]["wall"]["status"], "not_used")

    def test_same_actor_causal_and_monotonic_disagreement_is_reported(self):
        a = observation(
            "later-monotonic",
            temporal_frame=frame(
                "A",
                monotonic={"actor_id": "A", "segment": 0, "elapsed_ns": 20},
                causal=causal("A", {"A": 1}),
            ),
        )
        b = observation(
            "earlier-monotonic",
            temporal_frame=frame(
                "A",
                monotonic={"actor_id": "A", "segment": 0, "elapsed_ns": 10},
                causal=causal("A", {"A": 2}),
            ),
        )
        result = compare_observations(a, b)
        self.assertEqual(result["relations"]["causal"]["status"], "before")
        self.assertEqual(result["relations"]["monotonic"]["status"], "after")
        self.assertEqual(result["cross_domain_consistency"], "local_causal_disagreement")


class PartialOrderAnalysisTests(unittest.TestCase):
    def test_split_clock_relay_produces_two_components_not_a_global_timeline(self):
        records = [
            observation("C100", clock_id="controller:C", coordinate=100),
            observation("C101", clock_id="controller:C", coordinate=101),
            observation("C105", clock_id="controller:C", coordinate=105),
            observation("C108", clock_id="controller:C", coordinate=108),
            observation("S8", clock_id="sensor:S", coordinate=8),
            observation("S11", clock_id="sensor:S", coordinate=11),
            observation("S14", clock_id="sensor:S", coordinate=14),
        ]
        report = analyze_observations(records)
        local = report["domains"]["local_counter"]
        self.assertEqual(report["observation_count"], 7)
        self.assertEqual(local["edge_count"], 9)
        self.assertEqual(local["pair_status_counts"]["incomparable"], 12)
        self.assertEqual(local["weakly_connected_components"], [
            ["C100", "C101", "C105", "C108"],
            ["S11", "S14", "S8"],
        ])
        self.assertEqual(set(local["maximal_event_ids"]), {"C108", "S14"})
        self.assertEqual(
            report["domains"]["causal"]["pair_status_counts"]["unobserved"], 21
        )
        self.assertIsNone(report["global_total_order"])

    def test_components_do_not_linearize_independent_streams(self):
        records = [
            observation("C1", clock_id="C", coordinate=1),
            observation("C2", clock_id="C", coordinate=2),
            observation("S1", clock_id="S", coordinate=1),
            observation("S2", clock_id="S", coordinate=2),
        ]
        local = analyze_observations(records)["domains"]["local_counter"]
        self.assertEqual(local["weakly_connected_components"], [["C1", "C2"], ["S1", "S2"]])
        self.assertNotIn("topological_order", local)
        self.assertIsNone(analyze_observations(records)["global_total_order"])

    def test_input_permutation_does_not_change_analysis(self):
        records = [
            observation("b", clock_id="clock", coordinate=2),
            observation("a", clock_id="clock", coordinate=1),
            observation("c", clock_id="other", coordinate=0),
        ]
        first = analyze_observations(records)
        second = analyze_observations(list(reversed(records)))
        self.assertEqual(first, second)

    def test_duplicate_event_id_is_rejected(self):
        records = [
            observation("same", clock_id="a", coordinate=1),
            observation("same", clock_id="b", coordinate=2),
        ]
        with self.assertRaises(TemporalProvenanceError):
            analyze_observations(records)

    def test_encounter_extension_round_trip_is_copying_and_identity_bound(self):
        envelope = {
            "format": "in-formation.encounter/0.1",
            "id": "event-17",
            "source": {"kind": "test"},
            "payload": {"value": "observed"},
        }
        record = observation("event-17", clock_id="controller:C", coordinate=105)
        updated = attach_to_encounter_envelope(envelope, record)
        self.assertNotIn("extensions", envelope)
        self.assertEqual(
            extract_from_encounter_envelope(updated),
            validate_observation(record),
        )
        self.assertNotIn("extensions", envelope)

    def test_encounter_extension_rejects_event_id_mismatch_and_duplicate(self):
        envelope = {
            "format": "in-formation.encounter/0.1",
            "id": "event-17",
            "source": {"kind": "test"},
            "payload": {"value": "observed"},
        }
        with self.assertRaises(TemporalProvenanceError):
            attach_to_encounter_envelope(
                envelope,
                observation("different-event", clock_id="C", coordinate=1),
            )
        updated = attach_to_encounter_envelope(
            envelope, observation("event-17", clock_id="C", coordinate=1)
        )
        with self.assertRaises(TemporalProvenanceError):
            attach_to_encounter_envelope(
                updated, observation("event-17", clock_id="C", coordinate=2)
            )

    def test_encounter_extension_extraction_rechecks_event_identity(self):
        envelope = {
            "format": "in-formation.encounter/0.1",
            "id": "event-17",
            "source": {"kind": "test"},
            "payload": {"value": "observed"},
            "extensions": {
                FORMAT: observation("other-event", clock_id="C", coordinate=1)
            },
        }
        with self.assertRaises(TemporalProvenanceError):
            extract_from_encounter_envelope(envelope)

    def test_schema_accepts_e_cpu_compatible_temporal_frame(self):
        if jsonschema is None:
            self.skipTest("jsonschema is optional")
        schema = json.loads(
            (Path(__file__).with_name("temporal-provenance.schema.json")).read_text(
                encoding="utf-8"
            )
        )
        record = observation(
            "evt-1",
            clock_id="sensor-A",
            coordinate=12,
            temporal_frame=frame(
                "sensor-process",
                monotonic={
                    "actor_id": "sensor-process",
                    "segment": 0,
                    "elapsed_ns": 120_000,
                },
                causal=causal("sensor-process", {"sensor-process": 1}),
            ),
        )
        jsonschema.validate(instance=record, schema=schema)


if __name__ == "__main__":
    unittest.main()
