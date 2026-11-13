"""RIV-005: accumulate evidence from sensors with different reliabilities."""
import json
from heterogeneous_evidence import build_report

report = build_report(
    prior_hypothesis_a="1/2",
    sensors=(
        {"sensor_id": "strong-1", "p_signal_a_given_hypothesis_a": "9/10", "p_signal_a_given_hypothesis_b": "1/10"},
        {"sensor_id": "strong-2", "p_signal_a_given_hypothesis_a": "9/10", "p_signal_a_given_hypothesis_b": "1/10"},
        {"sensor_id": "weak-1", "p_signal_a_given_hypothesis_a": "3/5", "p_signal_a_given_hypothesis_b": "2/5"},
        {"sensor_id": "weak-2", "p_signal_a_given_hypothesis_a": "3/5", "p_signal_a_given_hypothesis_b": "2/5"},
    ),
)
print(json.dumps(report, indent=2, sort_keys=True))
