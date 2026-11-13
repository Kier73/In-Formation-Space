"""RIV-007: maintain joint uncertainty over a hidden state and shared calibration."""
import json
from calibration_aware_evidence import build_report

report = build_report(
    prior_hypothesis_a="1/2",
    sensor_schedule=("sensor-1", "sensor-2", "sensor-3"),
    calibrations=(
        {
            "calibration_id": "profile-1",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-1": {"p_signal_a_given_hypothesis_a": "9/10", "p_signal_a_given_hypothesis_b": "1/10"},
                "sensor-2": {"p_signal_a_given_hypothesis_a": "7/10", "p_signal_a_given_hypothesis_b": "3/10"},
                "sensor-3": {"p_signal_a_given_hypothesis_a": "9/10", "p_signal_a_given_hypothesis_b": "1/10"},
            },
        },
        {
            "calibration_id": "profile-2",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-1": {"p_signal_a_given_hypothesis_a": "3/5", "p_signal_a_given_hypothesis_b": "2/5"},
                "sensor-2": {"p_signal_a_given_hypothesis_a": "4/5", "p_signal_a_given_hypothesis_b": "1/5"},
                "sensor-3": {"p_signal_a_given_hypothesis_a": "1/10", "p_signal_a_given_hypothesis_b": "3/5"},
            },
        },
    ),
)
print(json.dumps(report, indent=2, sort_keys=True))
