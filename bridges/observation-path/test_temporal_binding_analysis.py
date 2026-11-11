import hashlib
import json
import unittest
from pathlib import Path

import jsonschema

from analyze_temporal_binding import analyze_temporal_binding, validate_temporal_analysis


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def binding_with_deltas(deltas, actors=None):
    actors = actors or ["clock-a"] * (len(deltas) + 1)
    stages = ["planned", "dispatched", "admitted", "returned"][:len(deltas) + 1]
    events = [
        {
            "index": index,
            "stage": stage,
            "observation_event_digest": f"{index + 1:064x}",
            "temporal_frame_actor_id": actors[index],
            "temporal_frame_digest": f"{index + 101:064x}",
        }
        for index, stage in enumerate(stages)
    ]
    intervals = []
    for index, delta in enumerate(deltas):
        intervals.append({
            "from_stage": stages[index],
            "to_stage": stages[index + 1],
            "delta": {
                "start_actor_id": actors[index],
                "end_actor_id": actors[index + 1],
                "monotonic_elapsed_ns": None,
                "monotonic_regressed": False,
                "wall_elapsed_ns": None,
                "causal_relation": None,
                "scheduler_ticks": None,
                "event_steps": None,
                "chemical_tau_delta": None,
                "chronon_phase_from": None,
                "chronon_phase_to": None,
                **delta,
            },
        })
    core = {
        "schema": "in-formation.observation-temporal-binding/0.1",
        "attempt_id": "attempt-temporal-analysis",
        "observation_path_digest": "a" * 64,
        "temporal_trace_ref": "temporal/attempt.json",
        "temporal_trace_digest": "b" * 64,
        "event_bindings": events,
        "intervals": intervals,
    }
    return {**core, "binding_digest": digest(core)}


class TemporalBindingAnalysisTests(unittest.TestCase):
    def test_total_uses_only_complete_adjacent_monotonic_intervals(self):
        binding = binding_with_deltas([
            {
                "monotonic_elapsed_ns": 12,
                "wall_elapsed_ns": 100,
                "causal_relation": "before",
            },
            {
                "monotonic_elapsed_ns": 25,
                "wall_elapsed_ns": -5,
                "causal_relation": "before",
            },
            {
                "monotonic_elapsed_ns": 8,
                "wall_elapsed_ns": 10,
                "causal_relation": "before",
            },
        ])
        report = analyze_temporal_binding(binding)
        self.assertEqual(report["monotonic_total_status"], "complete")
        self.assertEqual(report["monotonic_total_elapsed_ns"], 45)
        self.assertEqual(report["intervals"][1]["wall_elapsed_ns"], -5)
        self.assertEqual(report["intervals"][1]["monotonic_elapsed_ns"], 25)
        self.assertEqual(report["intervals"][0]["monotonic_status"], "measured")
        self.assertIn("not an isolated measurement", report["measurement_scope"])

    def test_missing_or_incomparable_interval_prevents_a_total(self):
        binding = binding_with_deltas([
            {"monotonic_elapsed_ns": 12},
            {"monotonic_elapsed_ns": None},
        ], actors=["clock-a", "clock-a", "clock-b"])
        report = analyze_temporal_binding(binding)
        self.assertEqual(report["monotonic_total_status"], "incomplete_or_incomparable")
        self.assertIsNone(report["monotonic_total_elapsed_ns"])
        self.assertEqual(
            report["intervals"][1]["monotonic_status"],
            "not_comparable_or_unobserved",
        )

    def test_monotonic_regression_is_preserved_and_never_summed(self):
        binding = binding_with_deltas([
            {"monotonic_elapsed_ns": 12},
            {"monotonic_elapsed_ns": None, "monotonic_regressed": True},
        ])
        report = analyze_temporal_binding(binding)
        self.assertEqual(report["intervals"][1]["monotonic_status"], "regressed")
        self.assertIsNone(report["monotonic_total_elapsed_ns"])

    def test_wall_clock_regression_does_not_negate_monotonic_elapsed(self):
        binding = binding_with_deltas([
            {
                "monotonic_elapsed_ns": 12,
                "wall_elapsed_ns": -100,
                "causal_relation": "before",
            },
        ])
        report = analyze_temporal_binding(binding)
        self.assertEqual(report["monotonic_total_elapsed_ns"], 12)
        self.assertEqual(report["intervals"][0]["wall_elapsed_ns"], -100)

    def test_interval_actor_ids_must_match_the_bound_frames(self):
        binding = binding_with_deltas([
            {"monotonic_elapsed_ns": 12},
        ])
        binding["intervals"][0]["delta"]["start_actor_id"] = "unrelated-clock"
        core = {key: value for key, value in binding.items() if key != "binding_digest"}
        binding["binding_digest"] = digest(core)
        with self.assertRaises(ValueError):
            analyze_temporal_binding(binding)

    def test_binding_digest_tampering_is_rejected(self):
        binding = binding_with_deltas([{"monotonic_elapsed_ns": 12}])
        binding["intervals"][0]["delta"]["monotonic_elapsed_ns"] = 999
        with self.assertRaises(ValueError):
            analyze_temporal_binding(binding)

    def test_one_event_has_no_measurable_interval(self):
        binding = binding_with_deltas([])
        report = analyze_temporal_binding(binding)
        self.assertEqual(report["monotonic_total_status"], "no_intervals")
        self.assertIsNone(report["monotonic_total_elapsed_ns"])
        self.assertEqual(report["interval_count"], 0)

    def test_analysis_digest_and_portable_schema_validate(self):
        report = analyze_temporal_binding(binding_with_deltas([
            {"monotonic_elapsed_ns": 12, "causal_relation": "before"},
        ]))
        binding = binding_with_deltas([
            {"monotonic_elapsed_ns": 12, "causal_relation": "before"},
        ])
        self.assertEqual(validate_temporal_analysis(report, binding), report)
        altered = dict(report)
        altered["monotonic_total_elapsed_ns"] = 999
        with self.assertRaises(ValueError):
            validate_temporal_analysis(altered, binding)

        # A freshly recomputed digest must not legitimize an incorrect derivation.
        altered["analysis_digest"] = digest({
            key: value for key, value in altered.items() if key != "analysis_digest"
        })
        with self.assertRaises(ValueError):
            validate_temporal_analysis(altered, binding)

        schema = json.loads(
            (Path(__file__).with_name("temporal-path-analysis.schema.json"))
            .read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(report, schema)


if __name__ == "__main__":
    unittest.main(verbosity=2)
