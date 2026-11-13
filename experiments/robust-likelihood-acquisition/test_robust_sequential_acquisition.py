import copy
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

import jsonschema

from robust_likelihood_acquisition import build_joint_belief_document
from robust_sequential_acquisition import (
    RobustSequentialError,
    build_report,
    validate_report,
)


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


def belief():
    return build_joint_belief_document(
        joint_posterior=(
            {"hypothesis": "A", "context_state": "fixed", "probability": "1/2"},
            {"hypothesis": "B", "context_state": "fixed", "probability": "1/2"},
        ),
        source_ref="artifact://RIV-016/prior-belief",
        source_report_digest="f" * 64,
    )


def candidate(sensor_id, cost, outcomes=("yes", "no")):
    return {
        "sensor_id": sensor_id,
        "dimension": "target-hypothesis",
        "cost": cost,
        "outcomes": list(outcomes),
    }


def likelihoods(rows):
    return [
        {
            "outcome": outcome,
            "likelihoods": [
                {
                    "hypothesis": "A",
                    "context_state": "fixed",
                    "probability": probability_a,
                },
                {
                    "hypothesis": "B",
                    "context_state": "fixed",
                    "probability": probability_b,
                },
            ],
        }
        for outcome, probability_a, probability_b in rows
    ]


def scenario(name, models):
    return {
        "scenario_id": name,
        "candidate_models": [
            {"sensor_id": sensor_id, "outcome_likelihoods": model}
            for sensor_id, model in models.items()
        ],
    }


def adaptive_fixture():
    candidates = (
        candidate("screen", "1/10"),
        candidate("reader-a", "1/10"),
        candidate("reader-b", "1/10"),
    )
    models = scenario("known-model", {
        "screen": likelihoods((
            ("yes", "4/5", "1/5"),
            ("no", "1/5", "4/5"),
        )),
        "reader-a": likelihoods((
            ("yes", "9/10", "2/5"),
            ("no", "1/10", "3/5"),
        )),
        "reader-b": likelihoods((
            ("yes", "3/5", "1/10"),
            ("no", "2/5", "9/10"),
        )),
    })
    return candidates, (models,)


def ambiguity_fixture():
    candidates = (candidate("reader", "1/4"),)
    models = (
        scenario("low", {
            "reader": likelihoods((
                ("yes", "9/10", "1/10"),
                ("no", "1/10", "9/10"),
            )),
        }),
        scenario("high", {
            "reader": likelihoods((
                ("yes", "7/10", "3/10"),
                ("no", "3/10", "7/10"),
            )),
        }),
    )
    return candidates, models


class RobustSequentialAcquisitionTests(unittest.TestCase):
    def test_adaptive_policy_chooses_different_second_readers_by_observed_branch(self):
        candidates, models = adaptive_fixture()
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget="1/5",
            max_measurements=2,
        )
        tree = report["selected_policy"]["policy_tree"]
        self.assertEqual(tree["node_type"], "measure")
        self.assertEqual(tree["sensor_id"], "screen")
        branches = {row["outcome"]: row["next"] for row in tree["branches"]}
        self.assertEqual(branches["yes"]["node_type"], "measure")
        self.assertEqual(branches["yes"]["sensor_id"], "reader-a")
        self.assertEqual(branches["no"]["node_type"], "measure")
        self.assertEqual(branches["no"]["sensor_id"], "reader-b")
        self.assertEqual(
            ratio(report["selected_policy"]["worst_case_expected_decision_loss"]),
            Fraction(4, 25),
        )
        self.assertEqual(
            ratio(report["selected_policy"]["robust_expected_loss_reduction"]),
            Fraction(17, 50),
        )
        self.assertEqual(
            ratio(report["selected_policy"]["worst_case_expected_measurement_cost"]),
            Fraction(1, 5),
        )
        self.assertEqual(
            ratio(report["selected_policy"]["maximum_path_cost"]),
            Fraction(1, 5),
        )
        self.assertEqual(
            report["selected_policy"]["maximum_measurements_on_path"],
            2,
        )

    def test_single_measurement_horizon_matches_riv015_for_one_candidate(self):
        candidates, models = ambiguity_fixture()
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget="1/4",
            max_measurements=1,
        )
        tree = report["selected_policy"]["policy_tree"]
        self.assertEqual(tree["node_type"], "measure")
        self.assertEqual(tree["sensor_id"], "reader")
        self.assertEqual(
            ratio(report["selected_policy"]["worst_case_expected_decision_loss"]),
            Fraction(3, 10),
        )
        self.assertEqual(
            ratio(report["selected_policy"]["scenario_expected_decision_loss"]["high"]),
            Fraction(3, 10),
        )
        self.assertEqual(
            ratio(report["selected_policy"]["scenario_expected_decision_loss"]["low"]),
            Fraction(1, 10),
        )

    def test_root_minimax_uses_distinct_fixed_scenarios_for_the_complete_tree(self):
        candidates, models = adaptive_fixture()
        # The second scenario degrades reader-a but keeps its direction and
        # reader-b's channel. The same outcome tree must be evaluated in both
        # complete data-generating worlds; no branch can switch scenario.
        second = copy.deepcopy(models[0])
        second["scenario_id"] = "reader-a-degraded"
        reader_a = next(
            item for item in second["candidate_models"]
            if item["sensor_id"] == "reader-a"
        )
        reader_a["outcome_likelihoods"] = likelihoods((
            ("yes", "4/5", "2/5"),
            ("no", "1/5", "3/5"),
        ))
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=(models[0], second),
            path_cost_budget="1/5",
            max_measurements=2,
        )
        self.assertIsNone(report["ambiguity_set"]["scenario_weights"])
        self.assertEqual(
            report["ambiguity_set"]["scenario_persistence"],
            "one fixed but unknown model scenario for the entire policy-tree execution",
        )
        scenario_risks = {
            key: ratio(value)
            for key, value in report["selected_policy"]["scenario_expected_decision_loss"].items()
        }
        self.assertEqual(set(scenario_risks), {"known-model", "reader-a-degraded"})
        self.assertNotEqual(
            report["model_scenarios"][0],
            report["model_scenarios"][1],
        )
        self.assertEqual(
            max(scenario_risks.values()),
            ratio(report["selected_policy"]["worst_case_expected_decision_loss"]),
        )
        policy_tree = report["selected_policy"]["policy_tree"]
        self.assertEqual(policy_tree["node_type"], "measure")
        self.assertEqual(len(policy_tree["branches"]), 2)
        self.assertTrue(all(
            branch["next"]["node_type"] in {"measure", "stop"}
            for branch in policy_tree["branches"]
        ))

    def test_zero_measurement_horizon_selects_no_measurement(self):
        candidates, models = adaptive_fixture()
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget=0,
            max_measurements=0,
        )
        self.assertEqual(
            report["selected_policy"]["policy_tree"],
            {"node_type": "stop", "decision": "A"},
        )
        self.assertEqual(
            ratio(report["selected_policy"]["worst_case_expected_decision_loss"]),
            Fraction(1, 2),
        )
        self.assertEqual(
            ratio(report["selected_policy"]["robust_expected_loss_reduction"]),
            Fraction(0),
        )

    def test_pathwise_budget_prevents_unreachable_two_measurement_path(self):
        candidates, models = adaptive_fixture()
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget="1/10",
            max_measurements=2,
        )
        tree = report["selected_policy"]["policy_tree"]
        self.assertEqual(tree["node_type"], "measure")
        self.assertTrue(all(
            branch["next"]["node_type"] == "stop"
            for branch in tree["branches"]
        ))
        self.assertEqual(
            ratio(report["selected_policy"]["maximum_path_cost"]),
            Fraction(1, 10),
        )
        self.assertEqual(
            report["selected_policy"]["maximum_measurements_on_path"],
            1,
        )

    def test_outcome_impossible_under_all_models_is_explicit_model_mismatch_stop(self):
        candidates = (candidate("sensor-with-impossible-branch", "1", ("yes", "no", "never")),)
        models = (scenario("m1", {
            "sensor-with-impossible-branch": likelihoods((
                ("yes", "9/10", "1/10"),
                ("no", "1/10", "9/10"),
                ("never", 0, 0),
            )),
        }),)
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget=1,
            max_measurements=1,
        )
        tree = report["selected_policy"]["policy_tree"]
        branch = next(row for row in tree["branches"] if row["outcome"] == "never")
        self.assertEqual(branch["next"]["node_type"], "model_mismatch_stop")
        self.assertEqual(branch["next"]["disposition"], "stop_and_review")

    def test_frontier_retains_non_dominated_loss_cost_policy_vectors(self):
        candidates, models = adaptive_fixture()
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget="1/5",
            max_measurements=2,
        )
        frontier = report["root_pareto_frontier"]
        self.assertTrue(len(frontier) >= 2)
        self.assertTrue(any(
            row["maximum_measurements_on_path"] == 0
            for row in frontier
        ))
        self.assertTrue(any(
            row["maximum_measurements_on_path"] == 2
            for row in frontier
        ))

    def test_report_reconstruction_rejects_tampering(self):
        candidates, models = adaptive_fixture()
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget="1/5",
            max_measurements=2,
        )
        self.assertEqual(validate_report(report), report)
        changed = copy.deepcopy(report)
        changed["selected_policy"]["robust_expected_loss_reduction"] = {
            "numerator": 1, "denominator": 1
        }
        core = {
            key: value for key, value in changed.items()
            if key != "report_digest"
        }
        changed["report_digest"] = sha(json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ))
        with self.assertRaises(RobustSequentialError):
            validate_report(changed)

    def test_schema_accepts_reconstructed_policy_tree(self):
        candidates, models = adaptive_fixture()
        report = build_report(
            joint_belief=belief(),
            candidate_sensors=candidates,
            model_scenarios=models,
            path_cost_budget="1/5",
            max_measurements=2,
        )
        schema_path = Path(__file__).with_name(
            "robust-sequential-acquisition.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(report, schema)

    def test_search_limits_fail_closed(self):
        candidates, models = adaptive_fixture()
        with self.assertRaises(RobustSequentialError):
            build_report(
                joint_belief=belief(),
                candidate_sensors=candidates,
                model_scenarios=models,
                path_cost_budget="1/5",
                max_measurements=2,
                max_dp_states=1,
            )

    def test_invalid_horizon_and_negative_budget_are_rejected(self):
        candidates, models = adaptive_fixture()
        with self.assertRaises(RobustSequentialError):
            build_report(
                joint_belief=belief(),
                candidate_sensors=candidates,
                model_scenarios=models,
                path_cost_budget="1/5",
                max_measurements=4,
            )
        with self.assertRaises(RobustSequentialError):
            build_report(
                joint_belief=belief(),
                candidate_sensors=candidates,
                model_scenarios=models,
                path_cost_budget="-1/5",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
