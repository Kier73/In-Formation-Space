"""Prepare, but do not dispatch, the next RIV-016 robust policy observation."""
import json
import sys
from pathlib import Path

_EXPERIMENT = Path(__file__).resolve().parent
if str(_EXPERIMENT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT))

from robust_likelihood_acquisition import build_joint_belief_document
from robust_sequential_acquisition import build_report
from robust_policy_execution import new_robust_policy_observation_path


def likelihoods(rows):
    return [
        {
            "outcome": outcome,
            "likelihoods": [
                {"hypothesis": "A", "context_state": "fixed", "probability": pa},
                {"hypothesis": "B", "context_state": "fixed", "probability": pb},
            ],
        }
        for outcome, pa, pb in rows
    ]


def main():
    belief = build_joint_belief_document(
        joint_posterior=(
            {"hypothesis": "A", "context_state": "fixed", "probability": "1/2"},
            {"hypothesis": "B", "context_state": "fixed", "probability": "1/2"},
        ),
        source_ref="artifact://RIV-017/planned-path-demo",
        source_report_digest="e" * 64,
    )
    candidates = (
        {"sensor_id": "screen", "dimension": "target-hypothesis", "cost": "1/10", "outcomes": ["yes", "no"]},
        {"sensor_id": "reader-a", "dimension": "target-hypothesis", "cost": "1/10", "outcomes": ["yes", "no"]},
        {"sensor_id": "reader-b", "dimension": "target-hypothesis", "cost": "1/10", "outcomes": ["yes", "no"]},
    )
    scenarios = ({
        "scenario_id": "declared-response-model",
        "candidate_models": [
            {"sensor_id": "screen", "outcome_likelihoods": likelihoods((
                ("yes", "4/5", "1/5"), ("no", "1/5", "4/5"),
            ))},
            {"sensor_id": "reader-a", "outcome_likelihoods": likelihoods((
                ("yes", "9/10", "2/5"), ("no", "1/10", "3/5"),
            ))},
            {"sensor_id": "reader-b", "outcome_likelihoods": likelihoods((
                ("yes", "3/5", "1/10"), ("no", "2/5", "9/10"),
            ))},
        ],
    },)
    policy = build_report(
        joint_belief=belief,
        candidate_sensors=candidates,
        model_scenarios=scenarios,
        path_cost_budget="1/5",
        max_measurements=2,
    )
    planned = new_robust_policy_observation_path(
        policy_report=policy,
        attempt_id="planned-attempt-001",
    )
    print(json.dumps({
        "policy_report_digest": policy["report_digest"],
        "selected_sensor": policy["selected_policy"]["policy_tree"]["sensor_id"],
        "observation_path": planned.to_dict(),
        "status": planned.status,
        "terminal": planned.terminal,
        "statement": "planned only; no dispatch, return, authorization, or measurement is claimed",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
