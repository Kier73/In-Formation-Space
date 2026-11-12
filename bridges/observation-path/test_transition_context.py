import hashlib
import json
import unittest
from pathlib import Path

from transition_conformance import build_transition_conformance_record
from transition_context import (
    TransitionContextError,
    build_transition_context_analysis,
    build_transition_context_assignment,
    validate_transition_context_analysis,
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
    full=True,
    probe_id="inspect",
    current_state="s0",
    model_ref="artifact://trial08/model-001",
):
    path = make_path(outcome, attempt_id, candidate_name=probe_id)
    kwargs = {
        "conformance_id": f"conformance-{attempt_id}",
        "model_document": model,
        "model_ref": model_ref,
        "observation_path": path.to_dict(),
        "probe_id": probe_id,
        "current_state": current_state,
        "observed_outcome": outcome,
    }
    if full:
        kwargs.update({
            "before_state_ref": f"state://before-{attempt_id}",
            "before_state_digest": sha(f"before-{attempt_id}"),
            "observed_next_state": next_state,
            "after_state_ref": f"state://after-{attempt_id}",
            "after_state_digest": sha(f"after-{attempt_id}"),
        })
    else:
        kwargs.update({
            "before_state_ref": f"state://before-{attempt_id}",
            "before_state_digest": sha(f"before-{attempt_id}"),
        })
    return build_transition_conformance_record(**kwargs)


def assignment(record, dimensions, source_ref=None):
    return build_transition_context_assignment(
        attempt_id=record["attempt_id"],
        conformance_record=record,
        dimensions=dimensions,
        source_ref=source_ref,
    )


class TransitionContextAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.model = make_model()

    def test_context_partition_separates_observed_transition_variants(self):
        records = [
            make_record(self.model, attempt_id="a", outcome="ready", next_state="s1"),
            make_record(self.model, attempt_id="b", outcome="ready", next_state="s1"),
            make_record(self.model, attempt_id="c", outcome="other", next_state="s2"),
            make_record(self.model, attempt_id="d", outcome="other", next_state="s2"),
        ]
        assignments = [
            assignment(record, {"firmware": {"status": "observed", "value": version}})
            for record, version in zip(records, ("v1", "v1", "v2", "v2"))
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model,
            conformance_records=records,
            context_assignments=assignments,
        )
        cell = analysis["cells"][0]
        dimension = cell["dimensions"][0]
        comparison = dimension["pairwise_comparison"]
        self.assertEqual(dimension["dimension"], "firmware")
        self.assertEqual(dimension["distinct_observed_value_count"], 2)
        self.assertEqual(comparison["pooled_pair_count"], 6)
        self.assertEqual(comparison["pooled_disagreement_pair_count"], 4)
        self.assertEqual(comparison["within_stratum_pair_count"], 2)
        self.assertEqual(comparison["within_stratum_disagreement_pair_count"], 0)
        self.assertEqual(comparison["between_stratum_pair_count"], 4)
        self.assertEqual(comparison["between_stratum_disagreement_pair_count"], 4)
        self.assertEqual(
            comparison["separation_status"],
            "observed_partition_separates_supplied_sample",
        )
        self.assertEqual(
            analysis["frequency_semantics"],
            "descriptive_empirical_sample_fraction_not_transition_probability",
        )
        self.assertEqual(analysis["policy_effect"], "none")
        self.assertEqual(analysis["model_effect"], "none")

    def test_partition_can_reduce_but_not_eliminate_within_stratum_disagreement(self):
        records = [
            make_record(self.model, attempt_id="a", outcome="ready", next_state="s1"),
            make_record(self.model, attempt_id="b", outcome="other", next_state="s2"),
            make_record(self.model, attempt_id="c", outcome="ready", next_state="s1"),
            make_record(self.model, attempt_id="d", outcome="other", next_state="s2"),
        ]
        assignments = [
            assignment(records[0], {"mode": {"status": "observed", "value": "A"}}),
            assignment(records[1], {"mode": {"status": "observed", "value": "A"}}),
            assignment(records[2], {"mode": {"status": "observed", "value": "B"}}),
            assignment(records[3], {"mode": {"status": "observed", "value": "B"}}),
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=records,
            context_assignments=assignments,
        )
        comparison = analysis["cells"][0]["dimensions"][0]["pairwise_comparison"]
        self.assertEqual(comparison["pooled_disagreement_pair_count"], 4)
        self.assertEqual(comparison["within_stratum_disagreement_pair_count"], 2)
        self.assertEqual(comparison["between_stratum_disagreement_pair_count"], 2)
        self.assertEqual(
            comparison["separation_status"],
            "observed_partition_reduces_within_stratum_disagreement",
        )

    def test_unknown_not_supplied_and_unassigned_context_remain_distinct(self):
        records = [
            make_record(self.model, attempt_id="observed"),
            make_record(self.model, attempt_id="unknown"),
            make_record(self.model, attempt_id="not-supplied"),
            make_record(self.model, attempt_id="unassigned"),
        ]
        assignments = [
            assignment(records[0], {
                "mode": {"status": "observed", "value": "safe"},
                "region": {"status": "observed", "value": "east"},
            }),
            assignment(records[1], {
                "mode": {"status": "unknown", "reason": "sensor did not report mode"},
                "region": {"status": "observed", "value": "east"},
            }),
            assignment(records[2], {
                "region": {"status": "observed", "value": "west"},
            }),
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=records,
            context_assignments=assignments,
        )
        cell = analysis["cells"][0]
        mode = next(item for item in cell["dimensions"] if item["dimension"] == "mode")
        self.assertEqual(mode["unknown_attempt_ids"], ["unknown"])
        self.assertEqual(mode["not_supplied_attempt_ids"], ["not-supplied"])
        self.assertEqual(mode["unassigned_attempt_ids"], ["unassigned"])
        self.assertEqual(mode["observed_attempt_count"], 1)
        self.assertEqual(cell["unassigned_attempt_ids"], ["unassigned"])
        self.assertEqual(
            cell["joint_context"]["incomplete_context_attempt_ids"],
            ["not-supplied", "unassigned", "unknown"],
        )

    def test_joint_partition_requires_complete_observed_dimensions(self):
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b"),
            make_record(self.model, attempt_id="c"),
        ]
        assignments = [
            assignment(records[0], {
                "mode": {"status": "observed", "value": "A"},
                "host": {"status": "observed", "value": "X"},
            }),
            assignment(records[1], {
                "mode": {"status": "observed", "value": "A"},
                "host": {"status": "observed", "value": "Y"},
            }),
            assignment(records[2], {
                "mode": {"status": "observed", "value": "B"},
            }),
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=records,
            context_assignments=assignments,
        )
        joint = analysis["cells"][0]["joint_context"]
        self.assertEqual(joint["dimension_names"], ["host", "mode"])
        self.assertEqual(joint["complete_context_attempt_ids"], ["a", "b"])
        self.assertEqual(joint["incomplete_context_attempt_ids"], ["c"])
        self.assertEqual(joint["distinct_joint_context_count"], 2)

    def test_outcome_only_samples_never_enter_pairwise_transition_denominators(self):
        records = [
            make_record(self.model, attempt_id="full"),
            make_record(self.model, attempt_id="outcome-only", full=False),
        ]
        assignments = [
            assignment(record, {"mode": {"status": "observed", "value": "A"}})
            for record in records
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=records,
            context_assignments=assignments,
        )
        dimension = analysis["cells"][0]["dimensions"][0]
        comparison = dimension["pairwise_comparison"]
        group = dimension["groups"][0]
        self.assertEqual(group["sample_count"], 2)
        self.assertEqual(group["full_transition_sample_count"], 1)
        self.assertEqual(group["outcome_only_sample_count"], 1)
        self.assertEqual(comparison["full_transition_sample_count"], 1)
        self.assertEqual(comparison["pooled_pair_count"], 0)
        self.assertIsNone(comparison["pooled_disagreement_fraction"])

    def test_outcome_only_context_groups_do_not_count_as_full_transition_strata(self):
        records = [
            make_record(self.model, attempt_id="full-a"),
            make_record(self.model, attempt_id="full-b", outcome="other", next_state="s2"),
            make_record(self.model, attempt_id="outcome-a", full=False),
        ]
        assignments = [
            assignment(records[0], {"mode": {"status": "observed", "value": "A"}}),
            assignment(records[1], {"mode": {"status": "observed", "value": "A"}}),
            assignment(records[2], {"mode": {"status": "observed", "value": "B"}}),
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=records,
            context_assignments=assignments,
        )
        comparison = analysis["cells"][0]["dimensions"][0]["pairwise_comparison"]
        self.assertEqual(
            comparison["separation_status"],
            "insufficient_distinct_observed_context_values",
        )

    def test_context_assignments_are_bound_to_exact_attempts_and_conformance_digests(self):
        record = make_record(self.model, attempt_id="a")
        wrong_binding = assignment(record, {"mode": {"status": "observed", "value": "A"}})
        wrong_binding["conformance_digest"] = sha("other conformance")
        core = {key: value for key, value in wrong_binding.items() if key != "assignment_digest"}
        wrong_binding["assignment_digest"] = sha(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ))
        with self.assertRaises(TransitionContextError):
            build_transition_context_analysis(
                model_document=self.model, conformance_records=[record],
                context_assignments=[wrong_binding],
            )
        with self.assertRaises(TransitionContextError):
            build_transition_context_analysis(
                model_document=self.model, conformance_records=[record],
                context_assignments=[
                    assignment(record, {"mode": {"status": "observed", "value": "A"}}),
                    assignment(record, {"mode": {"status": "observed", "value": "B"}}),
                ],
            )

    def test_assignment_digest_and_context_types_are_validated(self):
        record = make_record(self.model, attempt_id="a")
        item = assignment(record, {"mode": {"status": "observed", "value": "A"}})
        item["dimensions"]["mode"]["value"] = "B"
        with self.assertRaises(TransitionContextError):
            build_transition_context_analysis(
                model_document=self.model, conformance_records=[record],
                context_assignments=[item],
            )
        with self.assertRaises(TransitionContextError):
            build_transition_context_assignment(
                attempt_id="a", conformance_record=record,
                dimensions={"mode": {"status": "observed", "value": 1.5}},
            )
        with self.assertRaises(TransitionContextError):
            build_transition_context_assignment(
                attempt_id="a", conformance_record=record,
                dimensions={"mode": {"status": "unknown", "reason": "  "}},
            )

    def test_conformance_source_is_reconstructed_before_context_analysis(self):
        import copy
        record = make_record(self.model, attempt_id="a")
        changed = copy.deepcopy(record)
        changed["conformance_status"] = "transition_mismatch"
        core = {key: value for key, value in changed.items() if key != "conformance_digest"}
        changed["conformance_digest"] = sha(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ))
        with self.assertRaises(TransitionContextError):
            build_transition_context_analysis(
                model_document=self.model, conformance_records=[changed],
                context_assignments=[],
            )

    def test_analysis_is_self_contained_and_independently_reconstructed(self):
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b", outcome="different", next_state="s2"),
        ]
        assignments = [
            assignment(record, {"revision": {"status": "observed", "value": value}})
            for record, value in zip(records, ("r1", "r2"))
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=records,
            context_assignments=assignments,
        )
        self.assertEqual(
            validate_transition_context_analysis(analysis, model_document=self.model),
            analysis,
        )
        tampered = dict(analysis)
        tampered["cells"] = [dict(analysis["cells"][0])]
        tampered["cells"][0]["sample_count"] = 100
        core = {key: value for key, value in tampered.items() if key != "analysis_digest"}
        tampered["analysis_digest"] = sha(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ))
        with self.assertRaises(TransitionContextError):
            validate_transition_context_analysis(tampered, model_document=self.model)

    def test_empty_context_assignments_preserve_all_attempts_as_unassigned(self):
        record = make_record(self.model, attempt_id="a")
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=[record],
            context_assignments=[],
        )
        cell = analysis["cells"][0]
        self.assertEqual(cell["unassigned_attempt_ids"], ["a"])
        self.assertEqual(cell["dimensions"], [])
        self.assertIsNone(cell["joint_context"])

    def test_analysis_matches_published_json_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is installed by the focused CI workflow")
        records = [
            make_record(self.model, attempt_id="a"),
            make_record(self.model, attempt_id="b", outcome="different", next_state="s2"),
        ]
        assignments = [
            assignment(record, {"revision": {"status": "observed", "value": value}})
            for record, value in zip(records, ("r1", "r2"))
        ]
        analysis = build_transition_context_analysis(
            model_document=self.model, conformance_records=records,
            context_assignments=assignments,
        )
        schema = json.loads(
            Path(__file__).with_name("transition-context-analysis.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(analysis, schema)


if __name__ == "__main__":
    unittest.main()
