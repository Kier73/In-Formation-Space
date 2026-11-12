import copy
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

import json
import jsonschema

from test_transition_context import assignment, make_model, make_record
from transition_context import build_transition_context_analysis
from context_attention import (
    ContextAttentionError,
    ContextProbeMethod,
    build_context_attention_plan,
    validate_context_attention_plan,
)
import vgi


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


class ContextAttentionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.model = make_model()
        self.records = [
            make_record(self.model, attempt_id="a", outcome="ready", next_state="s1"),
            make_record(self.model, attempt_id="b", outcome="other", next_state="s2"),
            make_record(self.model, attempt_id="c", outcome="ready", next_state="s1"),
            make_record(self.model, attempt_id="d", outcome="ready", full=False),
        ]
        self.assignments = [
            assignment(self.records[0], {
                "region": {"status": "observed", "value": "east"},
                "runtime": {"status": "unknown", "reason": "probe was not collected"},
            }),
            assignment(self.records[1], {
                "region": {"status": "observed", "value": "east"},
                "runtime": {"status": "unknown", "reason": "probe was not collected"},
            }),
            assignment(self.records[2], {
                "region": {"status": "observed", "value": "west"},
            }),
        ]
        self.analysis = build_transition_context_analysis(
            model_document=self.model,
            conformance_records=self.records,
            context_assignments=self.assignments,
        )
        self.region = ContextProbeMethod(
            "capture-region",
            "region",
            ("north", "west"),
            cost=Fraction(1),
        )
        self.runtime = ContextProbeMethod(
            "capture-runtime",
            "runtime",
            ("r1", "r2", "r3"),
            cost=Fraction(10),
        )

    def build(self, methods, **kwargs):
        return build_context_attention_plan(
            context_analysis=self.analysis,
            model_document=self.model,
            probe_id="inspect",
            current_state="s0",
            methods=methods,
            vgi_api=__import__("vgi"),
            **kwargs,
        )

    def test_minimax_policy_targets_missing_context_without_rebuilding_ranker(self):
        report = self.build((self.region,), max_probes=2)
        self.assertEqual(report["vgi_revision"], "ac13c1bbd92dfd09f17de51adef7adb2d2088bf6")
        self.assertIn("not_cryptographically_attested", report["vgi_revision_semantics"])
        self.assertEqual(report["candidate_probe_count"], 1)
        self.assertEqual(report["plan_config"]["horizon"], 1)
        self.assertEqual(report["policy"]["objective"],
                         "minimize_worst_case_unresolved_then_exact_worst_case_cost")
        self.assertEqual(report["policy"]["scenario_semantics"],
                         "declared_counterfactual_branches_not_probability_or_exhaustiveness_claim")
        self.assertEqual(report["next_measurement"]["attempt_id"], "d")
        self.assertEqual(report["next_measurement"]["method_id"], "capture-region")
        self.assertEqual(report["next_measurement"]["declared_scenario_values"],
                         ["east", "north", "west"])
        self.assertEqual(report["execution_status"], "proposal_only_not_dispatched")
        self.assertEqual(report["ground_effect"], "none")
        self.assertEqual(report["model_effect"], "none")
        self.assertEqual(report["attention_policy_effect"], "none")

    def test_baseline_reports_residual_disagreement_inside_context_equivalence(self):
        report = self.build((self.region,), max_probes=0)
        relations = report["initial_context_pair_relations"]
        self.assertEqual(relations["attempt_pair_status_counts"], {
            "equivalent": 1,
            "distinguishable": 2,
            "unresolved": 3,
        })
        self.assertEqual(relations["full_transition_pair_count"], 3)
        self.assertEqual(relations["full_transition_disagreement_pair_count"], 2)
        equivalent = relations["full_transition_pair_relations"]["equivalent"]
        self.assertEqual(equivalent["pair_count"], 1)
        self.assertEqual(equivalent["transition_disagreement_count"], 1)
        self.assertEqual(
            relations["transition_comparison_semantics"],
            "exact_observed_outcome_and_next_state_pair",
        )

    def test_unknown_not_supplied_and_unassigned_remain_distinct(self):
        report = self.build((self.runtime,), max_probes=1)
        metadata = report["synthetic_ground"]["document"]["metadata"]
        statuses = metadata["context_status_by_method_and_attempt"]
        self.assertEqual(statuses["capture-runtime"]["a"]["status"], "unknown")
        self.assertEqual(statuses["capture-runtime"]["b"]["status"], "unknown")
        self.assertEqual(statuses["capture-runtime"]["c"]["status"], "not_supplied")
        self.assertEqual(statuses["capture-runtime"]["d"]["status"], "unassigned")
        self.assertIn("region", report["unselected_context_dimensions"])

    def test_outcome_only_attempt_is_a_context_state_but_not_a_transition_pair(self):
        report = self.build((self.region,), max_probes=0)
        self.assertIn("d", report["selected_transition_cell"]["attempt_ids"])
        relations = report["initial_context_pair_relations"]
        self.assertEqual(relations["outcome_only_attempt_count"], 1)
        self.assertEqual(relations["full_transition_pair_count"], 3)
        self.assertEqual(relations["full_transition_disagreement_pair_count"], 2)

    def test_context_value_encoding_is_injective_beyond_one_base8_digit(self):
        values = tuple(f"value-{index:02d}" for index in range(10))
        method = ContextProbeMethod(
            "capture-bucket", "bucket", values, cost=Fraction(1, 3)
        )
        report = self.build((method,), max_probes=1)
        encoding = report["methods"][0]["value_encoding"]
        codes = [tuple(item["output"]) for item in encoding]
        self.assertEqual(len(encoding), 10)
        self.assertEqual(len(set(codes)), 10)
        self.assertTrue(all(len(code) == 2 for code in codes))
        self.assertEqual(report["synthetic_ground"]["document"]["channels"],
                         ["context_digit_0", "context_digit_1"])

    def test_exact_costs_and_single_method_per_dimension_are_enforced(self):
        with self.assertRaises(ContextAttentionError):
            ContextProbeMethod("float", "float-cost", ("x", "y"), cost=0.1)
        with self.assertRaises(ContextAttentionError):
            ContextProbeMethod("bool", "bool-cost", ("x", "y"), cost=True)
        with self.assertRaises(ContextAttentionError):
            ContextProbeMethod("bad-value", "bad-value", ("x", 1.5))
        duplicate_dimension = ContextProbeMethod(
            "alternate-region", "region", ("east", "west"), cost=Fraction(2)
        )
        with self.assertRaises(ContextAttentionError):
            self.build((self.region, duplicate_dimension))

    def test_policy_search_fails_closed_at_state_cap(self):
        with self.assertRaises(ContextAttentionError):
            self.build((self.region,), max_probes=2, max_states=1)

    def test_report_reconstructs_and_tampering_is_rejected(self):
        report = self.build((self.region, self.runtime), max_probes=2)
        self.assertEqual(
            validate_context_attention_plan(
                report,
                context_analysis=self.analysis,
                model_document=self.model,
                vgi_api=__import__("vgi"),
            ),
            report,
        )
        changed = copy.deepcopy(report)
        changed["candidate_probe_count"] += 1
        core = {key: value for key, value in changed.items() if key != "report_digest"}
        changed["report_digest"] = canonical_digest(core)
        with self.assertRaises(ContextAttentionError):
            validate_context_attention_plan(
                changed,
                context_analysis=self.analysis,
                model_document=self.model,
                vgi_api=__import__("vgi"),
            )

    def test_published_schema_accepts_reconstructed_policy_artifact(self):
        report = self.build((self.region, self.runtime), max_probes=2)
        schema_path = Path(__file__).with_name("context-attention-policy.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(report, schema)

    def test_result_is_invariant_to_method_and_source_order(self):
        forward = self.build((self.region, self.runtime), max_probes=2)
        reverse_analysis = build_transition_context_analysis(
            model_document=self.model,
            conformance_records=list(reversed(self.records)),
            context_assignments=list(reversed(self.assignments)),
        )
        reverse = build_context_attention_plan(
            context_analysis=reverse_analysis,
            model_document=self.model,
            probe_id="inspect",
            current_state="s0",
            methods=(self.runtime, self.region),
            vgi_api=__import__("vgi"),
            max_probes=2,
        )
        self.assertEqual(forward, reverse)

    def test_empty_candidate_budget_returns_explicit_unresolved_policy(self):
        report = self.build((self.region,), budget=0, max_probes=2)
        self.assertIsNone(report["next_measurement"])
        self.assertEqual(report["policy"]["worst_case_cost"],
                         {"numerator": 0, "denominator": 1})
        self.assertGreater(report["policy"]["worst_case_unresolved_pairs"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
