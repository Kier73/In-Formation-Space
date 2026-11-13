"""Run RIV-015's exact scenario-robust context reader comparison."""
import json
from fractions import Fraction

from robust_likelihood_acquisition import (
    build_joint_belief_document,
    build_report,
    validate_report,
)


def likelihoods(p_yes_a, p_yes_b):
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


def scenario(scenario_id, rows):
    return {
        "scenario_id": scenario_id,
        "candidate_models": [
            {"sensor_id": sensor_id, "outcome_likelihoods": model}
            for sensor_id, model in rows.items()
        ],
    }


def main():
    belief = build_joint_belief_document(
        joint_posterior=(
            {"hypothesis": "A", "context_state": "fixed", "probability": "1/2"},
            {"hypothesis": "B", "context_state": "fixed", "probability": "1/2"},
        ),
        source_ref="artifact://RIV-015/example-joint-belief",
        source_report_digest="a" * 64,
    )
    candidates = (
        {"sensor_id": "robust-reader", "dimension": "target-hypothesis",
         "cost": "1", "outcomes": ["yes", "no"]},
        {"sensor_id": "cheap-reader", "dimension": "target-hypothesis",
         "cost": "1/4", "outcomes": ["yes", "no"]},
        {"sensor_id": "perfect-audit", "dimension": "target-hypothesis",
         "cost": "2", "outcomes": ["yes", "no"]},
        {"sensor_id": "sign-flip-reader", "dimension": "target-hypothesis",
         "cost": "1/10", "outcomes": ["yes", "no"]},
    )
    models = (
        scenario("calibration-low", {
            "robust-reader": likelihoods("9/10", "1/10"),
            "cheap-reader": likelihoods("13/20", "7/20"),
            "perfect-audit": likelihoods(1, 0),
            "sign-flip-reader": likelihoods("99/100", "1/100"),
        }),
        scenario("calibration-high", {
            "robust-reader": likelihoods("7/10", "3/10"),
            "cheap-reader": likelihoods("13/20", "7/20"),
            "perfect-audit": likelihoods(1, 0),
            "sign-flip-reader": likelihoods("1/100", "99/100"),
        }),
    )
    report = build_report(
        joint_belief=belief,
        candidate_sensors=candidates,
        model_scenarios=models,
    )
    validate_report(report)
    print(json.dumps({
        "format": report["format"],
        "ambiguity_set": report["ambiguity_set"],
        "baseline_decision": report["baseline_decision"],
        "candidate_evaluations": [
            {
                "sensor_id": row["sensor_id"],
                "selected_robust_policy": row["selected_robust_policy"]["outcome_to_action"],
                "worst_case_expected_decision_loss": row["worst_case_expected_decision_loss"],
                "robust_expected_loss_reduction": row["robust_expected_loss_reduction"],
                "robust_value_per_cost": row["robust_value_per_cost"],
                "worst_case_regret_to_scenario_oracle": row["worst_case_regret_to_scenario_oracle"],
            }
            for row in report["candidate_evaluations"]
        ],
        "pareto_frontier_sensor_ids": report["pareto_frontier_sensor_ids"],
        "selection": report["selection"],
        "report_digest": report["report_digest"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
