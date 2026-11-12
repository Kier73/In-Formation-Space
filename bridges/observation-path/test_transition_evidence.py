import hashlib
import unittest

from transition_conformance import build_transition_conformance_record
from transition_evidence import (
    TransitionEvidenceError,
    build_transition_evidence_summary,
    validate_transition_evidence_summary,
)
from intervention_attention import build_intervention_attention_frontier
from observation_path import ObservationIntent, ObservationPath


def sha(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_model():
    return build_intervention_attention_frontier(
        world_states=("s0", "s1", "s2"),
        hypotheses=(
            {"hypothesis_id": "initial-yes", "initial_state": "s0",
             "query_value": True, "prior": "1/2"},
            {"hypothesis_id": "initial-no", "initial_state": "s1",
             "query_value": False, "prior": "1/2"},
        ),
        probes=(
            {
                "probe_id": "inspect",
                "observation_cost": 1,
                "transitions": {
                    "s0": {"outcome": "ready", "next_state": "s1", "intervention_cost": 2},
                    "s1": {"outcome": "no", "next_state": "s1", "intervention_cost": 0},
                    "s2": {"outcome": "unknown", "next_state": "s2", "intervention_cost": 1},
                },
            },
            {
                "probe_id": "read",
                "observation_cost": 2,
                "transitions": {
                    "s0": {"outcome": "zero", "next_state": "s0", "intervention_cost": 0},
                    "s1": {"outcome": "one", "next_state": "s2", "intervention_cost": 1},
                    "s2": {"outcome": "two", "next_state": "s2", "intervention_cost": 1},
                },
            },
        ),
        max_depth=2,
    )


def make_path(observed_outcome, attempt_id, candidate_name="inspect"):
    path = ObservationPath(ObservationIntent(
        attempt_id=attempt_id,
        candidate_name=candidate_name,
        query="what transition did the probe produce?",
        hypothesis_set_digest=sha("hypothesis-set"),
        estimated_cost=1.0,
        plan_ref="artifact://trial08/plan-001",
    ))
    path.append("dispatched", "host", evidence_ref=f"dispatch://{attempt_id}")
    path.append("admitted", "receiver", evidence_ref=f"admission://{attempt_id}")
    path.append(
        "returned",
        "sensor",
        evidence_ref=f"encounter://{attempt_id}",
        details={
            "encounter_id": f"encounter-{attempt_id}",
            "payload_digest": sha(f"payload-{attempt_id}"),
            "canonicalization": "canonical-json-v1",
        },
    )
    path.append(
        "interpreted",
        "interpreter",
        evidence_ref=f"interpretation://{attempt_id}",
        details={"method": "exact-test-interpreter", "interpreted_value": observed_outcome},
    )
    return path


def make_record(
    model,
    *,
    attempt_id,
    outcome="ready",
    next_state="s1",
    probe_id="inspect",
    current_state="s0",
    model_ref="artifact://trial08/model-001",
):
    path = make_path(outcome, attempt_id, candidate_name=probe_id)
    return build_transition_conformance_record(
        conformance_id=f"conformance-{attempt_id}",
        model_document=model,
        model_ref=model_ref,
        observation_path=path.to_dict(),
        probe_id=probe_id,
        current_state=current_state,
        observed_outcome=outcome,
        before_state_ref=f"state://before-{attempt_id}",
        before_state_digest=sha(f"before-{attempt_id}"),
        observed_next_state=next_state,
        after_state_ref=f"state://after-{attempt_id}",
        after_state_digest=sha(f"after-{attempt_id}"),
    )


class TransitionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.model = make_model()

    def test_repeated_equal_transitions_are_counted_not_declared_deterministic(self):
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b"),
            make_record(self.model, attempt_id="c"),
        ]
        summary = build_transition_evidence_summary(
            model_document=self.model,
            conformance_records=records,
        )
        cell = summary["cells"][0]
        self.assertEqual(cell["full_transition_sample_count"], 3)
        self.assertEqual(cell["outcome_only_sample_count"], 0)
        self.assertEqual(cell["transition_diversity"], "one_distinct_full_transition_observed")
        self.assertEqual(cell["prediction_status"], "all_full_samples_match_prediction")
        self.assertEqual(len(cell["full_transition_histogram"]), 1)
        self.assertEqual(cell["full_transition_histogram"][0]["count"], 3)
        self.assertEqual(
            cell["full_transition_histogram"][0]["empirical_frequency"],
            {"numerator": 1, "denominator": 1},
        )
        self.assertIn("does not establish a deterministic transition", cell["interpretation"])

    def test_multiple_distinct_transitions_are_preserved_as_observed_diversity(self):
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b", outcome="different"),
            make_record(self.model, attempt_id="c", outcome="different", next_state="s2"),
            make_record(self.model, attempt_id="d", next_state="s2"),
        ]
        summary = build_transition_evidence_summary(
            model_document=self.model, conformance_records=records
        )
        cell = summary["cells"][0]
        self.assertEqual(cell["transition_diversity"], "multiple_distinct_full_transitions_observed")
        self.assertEqual(cell["full_transition_sample_count"], 4)
        self.assertEqual(len(cell["full_transition_histogram"]), 4)
        self.assertEqual(cell["prediction_status"], "at_least_one_full_sample_mismatches_prediction")
        self.assertEqual(cell["conformance_status_counts"]["matched"], 1)
        self.assertEqual(cell["conformance_status_counts"]["outcome_mismatch"], 1)
        self.assertEqual(cell["conformance_status_counts"]["next_state_mismatch"], 1)
        self.assertEqual(cell["conformance_status_counts"]["transition_mismatch"], 1)

    def test_outcome_only_returns_are_separate_from_full_transition_denominator(self):
        path = make_path("ready", "outcome-only")
        record = build_transition_conformance_record(
            conformance_id="conformance-outcome-only",
            model_document=self.model,
            model_ref="artifact://trial08/model-001",
            observation_path=path.to_dict(),
            probe_id="inspect",
            current_state="s0",
            observed_outcome="ready",
            before_state_ref="state://before",
            before_state_digest=sha("before"),
        )
        summary = build_transition_evidence_summary(
            model_document=self.model, conformance_records=[record]
        )
        cell = summary["cells"][0]
        self.assertEqual(cell["transition_diversity"], "no_full_transition_witnesses")
        self.assertEqual(cell["full_transition_sample_count"], 0)
        self.assertEqual(cell["outcome_only_sample_count"], 1)
        self.assertEqual(cell["full_transition_histogram"], [])
        self.assertEqual(cell["outcome_only_histogram"][0]["count"], 1)
        self.assertEqual(
            cell["prediction_status"],
            "outcome_only_evidence_not_sufficient_for_transition_comparison",
        )

    def test_mixed_cells_are_partitioned_without_conflating_transition_tables(self):
        records = [
            make_record(self.model, attempt_id="inspect-s0"),
            make_record(
                self.model, attempt_id="read-s1", probe_id="read",
                current_state="s1", outcome="one", next_state="s2",
            ),
        ]
        summary = build_transition_evidence_summary(
            model_document=self.model, conformance_records=records
        )
        self.assertEqual(len(summary["cells"]), 2)
        keys = {(cell["probe_id"], cell["current_state"]) for cell in summary["cells"]}
        self.assertEqual(keys, {("inspect", "s0"), ("read", "s1")})

    def test_duplicate_attempts_and_duplicate_conformance_digests_are_rejected(self):
        a = make_record(self.model, attempt_id="same")
        b = make_record(self.model, attempt_id="same", outcome="different")
        with self.assertRaises(TransitionEvidenceError):
            build_transition_evidence_summary(
                model_document=self.model, conformance_records=[a, b]
            )
        with self.assertRaises(TransitionEvidenceError):
            build_transition_evidence_summary(
                model_document=self.model, conformance_records=[a, a]
            )

    def test_records_must_share_one_model_reference(self):
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b", model_ref="artifact://another-name"),
        ]
        with self.assertRaises(TransitionEvidenceError):
            build_transition_evidence_summary(
                model_document=self.model, conformance_records=records
            )

    def test_source_record_tampering_fails_before_aggregation(self):
        import json
        record = make_record(self.model, attempt_id="a")
        changed = dict(record)
        changed["conformance_status"] = "transition_mismatch"
        # Recompute the outer digest to test semantic reconstruction, not only
        # the inexpensive content-integrity check.
        core = {key: value for key, value in changed.items() if key != "conformance_digest"}
        changed["conformance_digest"] = hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        with self.assertRaises(TransitionEvidenceError):
            build_transition_evidence_summary(
                model_document=self.model, conformance_records=[changed]
            )

    def test_summary_is_self_contained_and_independently_reconstructed(self):
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b", outcome="different"),
        ]
        summary = build_transition_evidence_summary(
            model_document=self.model, conformance_records=records
        )
        self.assertEqual(len(summary["source_conformance_records"]), 2)
        self.assertEqual(
            validate_transition_evidence_summary(summary, model_document=self.model),
            summary,
        )

    def test_tampered_summary_is_rejected(self):
        record = make_record(self.model, attempt_id="a")
        summary = build_transition_evidence_summary(
            model_document=self.model, conformance_records=[record]
        )
        tampered = dict(summary)
        tampered["cells"] = [dict(summary["cells"][0])]
        tampered["cells"][0]["full_transition_sample_count"] = 99
        with self.assertRaises(TransitionEvidenceError):
            validate_transition_evidence_summary(tampered, model_document=self.model)

    def test_missing_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            build_transition_evidence_summary(model_document=self.model, conformance_records=[])
        with self.assertRaises(TypeError):
            build_transition_evidence_summary(model_document=self.model, conformance_records=[None])


    def test_summary_matches_published_json_schema(self):
        import json
        from pathlib import Path
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is installed by the focused CI workflow")
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b", outcome="different"),
        ]
        summary = build_transition_evidence_summary(
            model_document=self.model, conformance_records=records
        )
        schema = json.loads(
            Path(__file__).with_name("transition-evidence-summary.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(summary, schema)


if __name__ == "__main__":
    unittest.main()
