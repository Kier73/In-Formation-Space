"""RIV-008: compare exact expected decision value of context readers."""
import json
import sys
from fractions import Fraction
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FILTER_PATH = _REPO_ROOT / "experiments" / "context-switching-evidence-accumulator"
if str(_FILTER_PATH) not in sys.path:
    sys.path.insert(0, str(_FILTER_PATH))

from context_switching_evidence import build_report as build_context_filter_report
from decision_value_acquisition import (
    build_joint_belief_document,
    build_report,
    validate_report,
)


def context_sensor(sensor_id, good_given_good, good_given_degraded, cost):
    outcomes = []
    for outcome, probability_good, probability_degraded in (
        ("good", good_given_good, good_given_degraded),
        ("degraded", 1 - Fraction(good_given_good), 1 - Fraction(good_given_degraded)),
    ):
        outcomes.append({
            "outcome": outcome,
            "likelihoods": [
                {"hypothesis": "A", "context_state": "good", "probability": probability_good},
                {"hypothesis": "A", "context_state": "degraded", "probability": probability_degraded},
                {"hypothesis": "B", "context_state": "good", "probability": probability_good},
                {"hypothesis": "B", "context_state": "degraded", "probability": probability_degraded},
            ],
        })
    return {
        "sensor_id": sensor_id,
        "dimension": "operating-regime",
        "cost": cost,
        "outcomes": outcomes,
    }


def main():
    def filter_sensor(name):
        return {
            "sensor_id": name,
            "p_signal_a_given_hypothesis_a_good": "9/10",
            "p_signal_a_given_hypothesis_b_good": "1/10",
            "p_signal_a_given_hypothesis_a_degraded": "1/2",
            "p_signal_a_given_hypothesis_b_degraded": "1/2",
        }

    filter_report = build_context_filter_report(
        prior_hypothesis_a="1/2",
        prior_context_good="1/2",
        context_transition={
            "p_good_next_given_good": "9/10",
            "p_good_next_given_degraded": "1/10",
        },
        sensors=tuple(filter_sensor(f"sensor-{i}") for i in range(1, 5)),
    )
    layer = filter_report["joint_posterior_accumulator"]["layers"][2]
    state = next(
        item for item in layer["joint_posterior_states"]
        if item["posterior_hypothesis_a"] == {"numerator": 1, "denominator": 2}
        and item["posterior_regime_good"] == {"numerator": 301, "denominator": 890}
    )
    normalized_joint_posterior = [
        {
            "hypothesis": row["hypothesis"],
            "context_state": row["regime"],
            "probability": row["probability"],
        }
        for row in state["joint_posterior"]
    ]
    belief = build_joint_belief_document(
        joint_posterior=normalized_joint_posterior,
        source_ref="artifact://RIV-006/context-filter",
        source_report_digest=filter_report["content_digest"],
    )
    candidates = (
        context_sensor(
            "high-fidelity-context", Fraction(9, 10), Fraction(1, 10), Fraction(1)
        ),
        context_sensor(
            "budget-proxy", Fraction(2, 3), Fraction(1, 3), Fraction(1, 2)
        ),
        context_sensor(
            "perfect-context-audit", Fraction(1), Fraction(0), Fraction(2)
        ),
        context_sensor(
            "blind-context", Fraction(1, 2), Fraction(1, 2), Fraction(1, 4)
        ),
    )
    report = build_report(
        joint_belief=belief,
        candidate_sensors=candidates,
    )
    validate_report(report)
    print(json.dumps({
        "format": report["format"],
        "baseline_decision": report["baseline_decision"],
        "candidate_evaluations": report["candidate_evaluations"],
        "pareto_frontier_sensor_ids": report["pareto_frontier_sensor_ids"],
        "selection": report["selection"],
        "report_digest": report["report_digest"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
