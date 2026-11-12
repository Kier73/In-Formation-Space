"""Interop test against the pinned E-CPU TemporalFrame implementation."""
from __future__ import annotations

import unittest

from temporal_provenance import compare_observations, validate_temporal_frame


class SequenceClock:
    def __init__(self, *values: int) -> None:
        self.values = list(values)
        self.index = 0

    def __call__(self) -> int:
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


class ECPUTemporalInteropTests(unittest.TestCase):
    def test_actual_ecpu_temporal_frames_round_trip_and_keep_wall_time_separate(self):
        try:
            from mailcpu.chemical_time import SystemEpoch
            from mailcpu.temporal import ClockDomain, TemporalContext, TemporalProfile
        except ImportError:
            self.skipTest("pinned E-CPU runtime is not on PYTHONPATH")

        profile = TemporalProfile(frozenset({
            ClockDomain.MONOTONIC,
            ClockDomain.WALL,
            ClockDomain.CAUSAL,
            ClockDomain.SCHEDULER,
            ClockDomain.EVENT,
            ClockDomain.CHRONON,
            ClockDomain.CHEMICAL,
        }))
        context = TemporalContext(
            "interop-worker",
            profile,
            monotonic_ns=SequenceClock(100, 120, 130),
            wall_time_ns=SequenceClock(1_000, 900),
        )

        context.emit_causal_stamp()
        first = context.observe(
            scheduler_id="interop-scheduler",
            scheduler_tick=10,
            system_epoch=SystemEpoch(10, 1 + 0j, 0.25),
        )
        context.emit_causal_stamp()
        second = context.observe(
            scheduler_id="interop-scheduler",
            scheduler_tick=11,
            system_epoch=SystemEpoch(11, 1 + 0j, 0.5),
        )

        first_data = validate_temporal_frame(first.to_dict())
        second_data = validate_temporal_frame(second.to_dict())
        self.assertEqual(first_data["actor_id"], "interop-worker")
        self.assertEqual(first_data["monotonic"]["elapsed_ns"], 20)
        self.assertEqual(second_data["monotonic"]["elapsed_ns"], 30)
        self.assertEqual(first_data["wall"]["utc_ns"], 1_000)
        self.assertEqual(second_data["wall"]["utc_ns"], 900)
        self.assertEqual(first_data["causal"]["vector"]["interop-worker"], 1)
        self.assertEqual(second_data["causal"]["vector"]["interop-worker"], 2)

        left = {
            "format": "in-formation.temporal-provenance/0.1",
            "event_id": "first",
            "local_counter": None,
            "temporal_frame": first_data,
        }
        right = {
            "format": "in-formation.temporal-provenance/0.1",
            "event_id": "second",
            "local_counter": None,
            "temporal_frame": second_data,
        }
        comparison = compare_observations(left, right)
        self.assertEqual(comparison["relations"]["causal"]["status"], "before")
        self.assertEqual(comparison["relations"]["monotonic"]["status"], "before")
        self.assertEqual(comparison["relations"]["scheduler"]["status"], "before")
        self.assertEqual(comparison["relations"]["wall"]["status"], "not_used")
        self.assertEqual(comparison["cross_domain_consistency"], "not_assessed")


if __name__ == "__main__":
    unittest.main()
