import hashlib
import itertools
import json
import unittest
from pathlib import Path

import jsonschema

from run_experiment import (
    CONDITION_FIELDS,
    EXPERIMENT_ID,
    MINIMUM_PROFILE_SAMPLES,
    _condition_key,
    _fixture_hypotheses,
    build_cost_profile_matrix,
    matrix_conditions,
    validate_cost_profile_matrix,
)
from observation_outcomes import build_observation_outcome
from operation_spans import OperationSpanRecorder


class WorkloadMatrixTests(unittest.TestCase):
    def test_matrix_has_full_declared_factor_coverage(self):
        conditions = matrix_conditions()
        self.assertEqual(len(conditions), 24)
        self.assertEqual({item["payload_value_bytes"] for item in conditions}, {64, 1024})
        self.assertEqual({item["queue_depth_initial_per_source"] for item in conditions}, {1, 3})
        self.assertEqual(
            {(item["source_count"], item["quorum"]) for item in conditions},
            {(2, 2), (4, 2), (4, 4)},
        )
        self.assertEqual({item["receiver_load_workers"] for item in conditions}, {0, 2})
        for condition in conditions:
            self.assertEqual(tuple(condition), CONDITION_FIELDS)
            self.assertEqual(_condition_key(condition), tuple(condition.values()))

    def test_condition_key_rejects_booleans_and_inconsistent_quorum(self):
        valid = matrix_conditions()[0]
        invalid = dict(valid, source_count=True)
        with self.assertRaisesRegex(ValueError, "source_count"):
            _condition_key(invalid)
        invalid = dict(valid, quorum=5)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            _condition_key(invalid)
        invalid = dict(valid, payload_value_bytes=2)
        with self.assertRaisesRegex(ValueError, "fit"):
            _condition_key(invalid)

    def test_cost_matrix_partitions_conditions_and_target_path(self):
        condition = matrix_conditions()[0]
        ticks = itertools.count(100)
        recorder = OperationSpanRecorder(
            clock_actor_id="matrix-test-process",
            clock_segment_id="matrix-test-segment",
            clock_ns=lambda: next(ticks),
        )
        for replicate in range(MINIMUM_PROFILE_SAMPLES):
            attempt = f"test-{replicate}"
            for phase in ("queue_drain", "target"):
                recorder.measure(
                    attempt_id=attempt,
                    span_id=f"{phase}-{replicate}",
                    operation_id="ecpu.GatedObservationCoordinator.ingest_available",
                    operation=lambda: None,
                    context={
                        **condition,
                        "experiment_id": EXPERIMENT_ID,
                        "workload_id": attempt,
                        "observation_id": f"{attempt}:{phase}",
                        "phase": phase,
                        "logical_time": replicate + 1,
                    },
                )
        spans = list(recorder.spans)
        matrix = build_cost_profile_matrix(spans, minimum_samples=3)
        self.assertEqual(validate_cost_profile_matrix(matrix, spans), matrix)
        self.assertEqual(matrix["policy_effect"], "none")
        self.assertEqual(len(matrix["condition_profiles"]), 2)
        all_events = next(item for item in matrix["condition_profiles"] if item["scope"] == "all_events")
        target_events = next(item for item in matrix["condition_profiles"] if item["scope"] == "target_event")
        self.assertEqual(all_events["profile"]["profiles"][0]["measured_sample_count"], 6)
        self.assertEqual(target_events["profile"]["profiles"][0]["measured_sample_count"], 3)

    def test_cost_matrix_detects_tampered_profile_and_source_span(self):
        condition = matrix_conditions()[0]
        ticks = itertools.count(1)
        recorder = OperationSpanRecorder(
            clock_actor_id="matrix-test-process",
            clock_segment_id="matrix-test-segment",
            clock_ns=lambda: next(ticks),
        )
        spans = []
        for replicate in range(3):
            recorder.measure(
                attempt_id=f"a-{replicate}",
                span_id=f"ingest-{replicate}",
                operation_id="ecpu.GatedObservationCoordinator.ingest_available",
                operation=lambda: None,
                context={
                    **condition,
                    "experiment_id": EXPERIMENT_ID,
                    "workload_id": f"a-{replicate}",
                    "observation_id": f"a-{replicate}:o",
                    "phase": "target",
                    "logical_time": replicate,
                },
            )
        spans = list(recorder.spans)
        matrix = build_cost_profile_matrix(spans, minimum_samples=3)
        altered = {
            **matrix,
            "condition_profiles": [
                {
                    **entry,
                    "profile": {
                        **entry["profile"],
                        "profiles": [
                            {**profile, "median_ns": profile["median_ns"] + 1}
                            for profile in entry["profile"]["profiles"]
                        ],
                    },
                }
                for entry in matrix["condition_profiles"]
            ],
        }
        with self.assertRaisesRegex(ValueError, "digest|reconstruction"):
            validate_cost_profile_matrix(altered, spans)
        with self.assertRaisesRegex(ValueError, "reconstruction"):
            validate_cost_profile_matrix(matrix, spans[:-1])


    def test_run_manifest_matches_portable_schema(self):
        manifest = {
            "format": "in-formation.ecpu-observation-cost-information",
            "schema": "in-formation.ecpu-observation-cost-information/0.1",
            "experiment_id": EXPERIMENT_ID,
            "ecpu_reference_commit": "800f94f83ffd6f527ed093c8d1c1e93e153c34f6",
            "python_version": "3.11",
            "platform": "linux",
            "clock_actor_id": "matrix-process",
            "clock_segment_id": "run-1",
            "replicates": 3,
            "factor_levels": {
                "payload_value_bytes": [64, 1024],
                "queue_depth_initial_per_source": [1, 3],
                "source_quorum": [
                    {"source_count": 2, "quorum": 2},
                    {"source_count": 4, "quorum": 2},
                    {"source_count": 4, "quorum": 4},
                ],
                "receiver_load_workers": [0, 2],
            },
            "condition_count": 24,
            "attempt_count": 72,
            "span_count": 100,
            "evidence_record_count": 100,
            "information_outcome_count": 100,
            "profile_matrix_digest": "a" * 64,
            "information_outcome_digests": ["b" * 64],
            "minimum_profile_samples": 3,
            "interpretation_limits": ["pilot only"],
            "report_digest": "c" * 64,
        }
        schema = json.loads(
            Path(__file__).with_name("run-manifest.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(manifest, schema)

    def test_first_live_ci_summary_schema_and_digest(self):
        summary_path = Path(__file__).with_name("results") / "live-ci-run-271-summary.json"
        schema_path = Path(__file__).with_name("results") / "run-summary.schema.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(summary, schema)
        core = {key: value for key, value in summary.items() if key != "summary_digest"}
        calculated = hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(summary["summary_digest"], calculated)
        self.assertEqual(summary["workflow"]["run_id"], 43130567381)
        self.assertEqual(summary["matrix"]["attempt_count"], 72)
        self.assertEqual(summary["matrix"]["span_count"], 2448)
        self.assertTrue(summary["matrix"]["all_sender_acknowledgements_complete"])

    def test_fixture_information_model_reports_one_bit_expected_gain(self):
        document = build_observation_outcome(
            attempt_id="attempt-fixture",
            observation_id="observation-fixture",
            evidence_ref="evidence/fixture.json",
            evidence_digest=hashlib.sha256(b"fixture").hexdigest(),
            model_ref="fixture:resolver-hit-miss-v1",
            prior_hypotheses=_fixture_hypotheses(),
            observed_outcome="hit",
        )
        analysis = document["analysis"]
        self.assertAlmostEqual(analysis["expected_information_gain_bits"], 1.0)
        self.assertAlmostEqual(analysis["expected_query_resolution_probability"], 1.0)
        self.assertEqual(analysis["query_status"], "resolved")
        self.assertIs(analysis["query_value"], True)
        self.assertAlmostEqual(
            sum(item["probability"] for item in analysis["posterior"]), 1.0
        )


if __name__ == "__main__":
    unittest.main()
