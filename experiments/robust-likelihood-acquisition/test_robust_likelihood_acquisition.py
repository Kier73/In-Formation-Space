import copy
import hashlib
import json
import unittest
from fractions import Fraction

from robust_likelihood_acquisition import (
    RobustAcquisitionError,
    build_joint_belief_document,
    build_report,
    validate_report,
)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


def belief_fixture():
    return build_joint_belief_document(
        joint_posterior=(
            {"hypothesis": "A", "context_state": "fixed", "probability": "1/2"},
            {"hypothesis": "B", "context_state": "fixed", "probability": "1/2"},
        ),
        source_ref="artifact://joint-belief-fixture",
        source_report_digest="a" * 64,
    )


def candidate(sensor_id, cost):
    return {
        "sensor_id": sensor_id,
        "dimension": "target-hypothesis",
        "cost": cost,
        "outcomes": ["yes", "no"],
    }


def outcome_likelihoods(p_yes_a, p_yes_b):
    p_yes_a, p_yes_b = Fraction(p_yes_a), Fraction(p_yes_b)
    return [
        {
            "outcome": "yes",
            "likelihoods": [
                {"hypothesis": "A", "context_state": "fixed", "probability": p_yes_a},
                {"hypothesis": "B", "context_state": "fixed", "probability": p_yes_b},
            ],
        },
        {
            "outcome": "no",
            "likelihoods": [
                {"hypothesis": "A", "context_state": "fixed", "probability": 1 - p_yes_a},
                {"hypothesis": "B", "context_state": "fixed", "probability": 1 - p_yes_b},
            ],
        },
    ]


def scenario(name, models):
    return {
        "scenario_id": name,
        "candidate_models": [
            {
                "sensor_id": sensor_id,
                "outcome_likelihoods": likelihoods,
            }
            for sensor_id, likelihoods in models.items()
        ],
    }


def fixtures():
    candidates = (
        candidate("robust-reader", "1"),
        candidate("cheap-reader", "1/4"),
        candidate("perfect-audit", "2"),
        candidate("sign-flip-reader", "1/10"),
    )
    model_scenarios = (
        scenario("calibration-low", {
            "robust-reader": outcome_likelihoods("9/10", "1/10"),
            "cheap-reader": outcome_likelihoods("13/20", "7/20"),
            "perfect-audit": outcome_likelihoods(1, 0),
            "sign-flip-reader": outcome_likelihoods("99/100", "1/100"),
        }),
        scenario("calibration-high", {
            "robust-reader": outcome_likelihoods("7/10", "3/10"),
            "cheap-reader": outcome_likelihoods("13/20", "7/20"),
            "perfect-audit": outcome_likelihoods(1, 0),
            "sign-flip-reader": outcome_likelihoods("1/100", "99/100"),
        }),
    )
    return candidates, model_scenarios


class RobustLikelihoodAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.belief = belief_fixture()
        self.candidates, self.scenarios = fixtures()

    def build(self, **kwargs):
        return build_report(
            joint_belief=kwargs.pop("joint_belief", self.belief),
            candidate_sensors=kwargs.pop("candidate_sensors", self.candidates),
            model_scenarios=kwargs.pop("model_scenarios", self.scenarios),
            **kwargs,
        )

    def test_joint_belief_is_exactly_normalized_and_content_bound(self):
        self.assertEqual(
            sum(ratio(row["probability"]) for row in self.belief["joint_posterior"]),
            Fraction(1),
        )
        changed = copy.deepcopy(self.belief)
        changed["joint_posterior"][0]["probability"] = {"numerator": 3, "denominator": 4}
        with self.assertRaises(RobustAcquisitionError):
            self.build(joint_belief=changed)

    def test_model_scenarios_are_an_unweighted_ambiguity_set(self):
        report = self.build()
        self.assertEqual(
            report["ambiguity_set"]["scenario_ids"],
            ["calibration-high", "calibration-low"],
        )
        self.assertIsNone(report["ambiguity_set"]["scenario_weights"])
        self.assertIn("no probability is assigned", report["ambiguity_set"]["interpretation"])

    def test_one_policy_is_used_across_all_scenarios_for_each_sensor(self):
        report = self.build()
        rows = {
            row["sensor_id"]: row
            for row in report["candidate_evaluations"]
        }
        robust = rows["robust-reader"]
        mapping = {
            row["outcome"]: row["action"]
            for row in robust["selected_robust_policy"]["outcome_to_action"]
        }
        self.assertEqual(mapping, {"no": "B", "yes": "A"})
        scenario_risks = {
            row["scenario_id"]: ratio(row["expected_decision_loss"])
            for row in robust["selected_robust_policy"]["scenario_evaluations"]
        }
        self.assertEqual(scenario_risks["calibration-low"], Fraction(1, 10))
        self.assertEqual(scenario_risks["calibration-high"], Fraction(3, 10))
        self.assertEqual(
            ratio(robust["worst_case_expected_decision_loss"]),
            Fraction(3, 10),
        )
        self.assertEqual(
            ratio(robust["robust_expected_loss_reduction"]),
            Fraction(1, 5),
        )
        self.assertEqual(
            ratio(robust["robust_value_per_cost"]),
            Fraction(1, 5),
        )

    def test_expected_nominal_gain_is_not_substituted_for_worst_case_gain(self):
        report = self.build()
        robust = next(
            row for row in report["candidate_evaluations"]
            if row["sensor_id"] == "robust-reader"
        )
        risks = [
            ratio(row["expected_decision_loss"])
            for row in robust["selected_robust_policy"]["scenario_evaluations"]
        ]
        self.assertEqual(risks, [Fraction(3, 10), Fraction(1, 10)])
        self.assertEqual(max(risks), Fraction(3, 10))
        self.assertEqual(min(risks), Fraction(1, 10))
        # There is intentionally no "average over scenarios" field.

    def test_value_per_cost_can_choose_cheap_reader_over_more_informative_audit(self):
        report = self.build()
        rows = {row["sensor_id"]: row for row in report["candidate_evaluations"]}
        self.assertEqual(
            ratio(rows["perfect-audit"]["robust_expected_loss_reduction"]),
            Fraction(1, 2),
        )
        self.assertEqual(
            ratio(rows["perfect-audit"]["robust_value_per_cost"]),
            Fraction(1, 4),
        )
        self.assertEqual(
            ratio(rows["cheap-reader"]["robust_expected_loss_reduction"]),
            Fraction(3, 20),
        )
        self.assertEqual(
            ratio(rows["cheap-reader"]["robust_value_per_cost"]),
            Fraction(3, 5),
        )
        self.assertEqual(
            report["selection"]["selected_sensor_id"],
            "cheap-reader",
        )

    def test_sign_flipping_sensor_has_no_positive_worst_case_value(self):
        report = self.build()
        row = next(
            item for item in report["candidate_evaluations"]
            if item["sensor_id"] == "sign-flip-reader"
        )
        self.assertEqual(
            ratio(row["worst_case_expected_decision_loss"]),
            Fraction(1, 2),
        )
        self.assertEqual(
            ratio(row["robust_expected_loss_reduction"]),
            Fraction(0),
        )
        self.assertEqual(
            ratio(row["worst_case_regret_to_scenario_oracle"]),
            Fraction(49, 100),
        )

    def test_constant_policy_guarantees_nonnegative_robust_value(self):
        report = self.build()
        baseline = ratio(report["baseline_decision"]["worst_case_no_measurement_risk"])
        for row in report["candidate_evaluations"]:
            self.assertLessEqual(
                ratio(row["worst_case_expected_decision_loss"]),
                baseline,
            )
            self.assertGreaterEqual(
                ratio(row["robust_expected_loss_reduction"]),
                Fraction(0),
            )

    def test_cost_budget_changes_selection_but_not_candidate_model_scores(self):
        full = self.build()
        bounded = self.build(cost_budget="1/2")
        self.assertEqual(
            bounded["selection"]["eligible_sensor_ids"],
            ["cheap-reader", "sign-flip-reader"],
        )
        self.assertEqual(
            bounded["selection"]["selected_sensor_id"],
            "cheap-reader",
        )
        self.assertEqual(
            full["candidate_evaluations"],
            bounded["candidate_evaluations"],
        )

    def test_cost_budget_can_force_stop(self):
        report = self.build(cost_budget="1/5")
        self.assertEqual(report["selection"]["eligible_sensor_ids"], ["sign-flip-reader"])
        self.assertIsNone(report["selection"]["selected_sensor_id"])
        self.assertEqual(
            report["selection"]["status"],
            "stop_no_positive_worst_case_value",
        )

    def test_custom_loss_matrix_changes_robust_outcome_policy(self):
        loss = {
            "decide_a_if_hypothesis_a": 0,
            "decide_a_if_hypothesis_b": 3,
            "decide_b_if_hypothesis_a": 1,
            "decide_b_if_hypothesis_b": 0,
        }
        report = self.build(loss_matrix=loss)
        self.assertEqual(report["baseline_decision"]["action"], "B")
        self.assertTrue(all(
            ratio(row["robust_expected_loss_reduction"]) >= 0
            for row in report["candidate_evaluations"]
        ))

    def test_each_scenario_must_define_each_candidate_exactly_once(self):
        broken = copy.deepcopy(self.scenarios)
        broken[0]["candidate_models"].pop()
        with self.assertRaises(RobustAcquisitionError):
            self.build(model_scenarios=broken)

        broken = copy.deepcopy(self.scenarios)
        broken[0]["candidate_models"][1]["sensor_id"] = broken[0]["candidate_models"][0]["sensor_id"]
        with self.assertRaises(RobustAcquisitionError):
            self.build(model_scenarios=broken)

    def test_likelihoods_must_sum_to_one_for_each_state(self):
        broken = copy.deepcopy(self.scenarios)
        broken[0]["candidate_models"][0]["outcome_likelihoods"][0]["likelihoods"][0][
            "probability"
        ] = "1/2"
        with self.assertRaises(RobustAcquisitionError):
            self.build(model_scenarios=broken)

    def test_duplicate_scenario_ids_and_inconsistent_outcome_sets_are_rejected(self):
        broken = copy.deepcopy(self.scenarios)
        broken[1]["scenario_id"] = broken[0]["scenario_id"]
        with self.assertRaises(RobustAcquisitionError):
            self.build(model_scenarios=broken)

        broken = copy.deepcopy(self.scenarios)
        broken[0]["candidate_models"][0]["outcome_likelihoods"][1]["outcome"] = "maybe"
        with self.assertRaises(RobustAcquisitionError):
            self.build(model_scenarios=broken)

    def test_float_probabilities_and_nonpositive_costs_are_rejected(self):
        for cost in (0, -1, 0.5, True):
            broken = copy.deepcopy(self.candidates)
            broken[0]["cost"] = cost
            with self.subTest(cost=cost), self.assertRaises(RobustAcquisitionError):
                self.build(candidate_sensors=broken)

        broken = copy.deepcopy(self.scenarios)
        broken[0]["candidate_models"][0]["outcome_likelihoods"][0]["likelihoods"][0][
            "probability"
        ] = 0.9
        with self.assertRaises(RobustAcquisitionError):
            self.build(model_scenarios=broken)

    def test_report_reconstruction_rejects_tampering(self):
        report = self.build()
        self.assertEqual(validate_report(report), report)
        changed = copy.deepcopy(report)
        changed["candidate_evaluations"][0][
            "robust_expected_loss_reduction"
        ] = {"numerator": 1, "denominator": 1}
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
        with self.assertRaises(RobustAcquisitionError):
            validate_report(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
