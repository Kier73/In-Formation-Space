"""Run RIV-016's exact adaptive robust sensor policy example."""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_EXPERIMENTS = _ROOT / "experiments" / "robust-likelihood-acquisition"
if str(_EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENTS))

from robust_likelihood_acquisition import build_joint_belief_document
from robust_sequential_acquisition import build_report, validate_report


def candidate(sensor_id, cost):
    return {
        "sensor_id": sensor_id,
        "dimension": "target-hypothesis",
        "cost": cost,
        "outcomes": ["yes", "no"],
    }


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
    prior = build_joint_belief_document(
        joint_posterior=(
            {"hypothesis": "A", "context_state": "fixed", "probability": "1/2"},
            {"hypothesis": "B", "context_state": "fixed", "probability": "1/2"},
        ),
        source_ref="artifact://RIV-016/adaptive-example-prior",
        source_report_digest="f" * 64,
    )
    sensors = (
        candidate("screen", "1/10"),
        candidate("reader-a", "1/10"),
        candidate("reader-b", "1/10"),
    )
    scenarios = ({
        "scenario_id": "declared-response-model",
        "candidate_models": [
            {
                "sensor_id": "screen",
                "outcome_likelihoods": likelihoods((
                    ("yes", "4/5", "1/5"),
                    ("no", "1/5", "4/5"),
                )),
            },
            {
                "sensor_id": "reader-a",
                "outcome_likelihoods": likelihoods((
                    ("yes", "9/10", "2/5"),
                    ("no", "1/10", "3/5"),
                )),
            },
            {
                "sensor_id": "reader-b",
                "outcome_likelihoods": likelihoods((
                    ("yes", "3/5", "1/10"),
                    ("no", "2/5", "9/10"),
                )),
            },
        ],
    },)
    report = build_report(
        joint_belief=prior,
        candidate_sensors=sensors,
        model_scenarios=scenarios,
        path_cost_budget="1/5",
        max_measurements=2,
    )
    validate_report(report)
    print(json.dumps({
        "format": report["format"],
        "ambiguity_set": report["ambiguity_set"],
        "selected_policy": report["selected_policy"],
        "root_pareto_frontier": report["root_pareto_frontier"],
        "search_metrics": report["search_metrics"],
        "report_digest": report["report_digest"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
