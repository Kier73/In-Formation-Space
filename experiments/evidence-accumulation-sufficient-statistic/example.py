"""RIV-004: repeated noisy observations compressed into a sufficient statistic."""
import json
from evidence_accumulation import build_report

report = build_report(
    observation_count=5,
    prior_hypothesis_a="1/2",
    p_signal_a_given_hypothesis_a="3/4",
    p_signal_a_given_hypothesis_b="1/4",
)
print(json.dumps(report, indent=2, sort_keys=True))
