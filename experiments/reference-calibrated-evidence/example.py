"""Reproduce the exact two-stage calibration-reference example."""
from __future__ import annotations

import hashlib

from reference_calibrated_evidence import build_report, validate_report


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def channel(alpha: str, beta: str) -> dict[str, str]:
    return {
        "p_signal_a_given_hypothesis_a": alpha,
        "p_signal_a_given_hypothesis_b": beta,
    }


calibrations = (
    {
        "calibration_id": "profile-1",
        "prior_probability": "1/2",
        "sensor_models": {
            "sensor-1": channel("9/10", "1/10"),
            "sensor-2": channel("9/10", "1/10"),
            "sensor-3": channel("8/10", "2/10"),
        },
    },
    {
        "calibration_id": "profile-2",
        "prior_probability": "1/2",
        "sensor_models": {
            "sensor-1": channel("3/5", "2/5"),
            "sensor-2": channel("2/5", "3/5"),
            "sensor-3": channel("1/5", "4/5"),
        },
    },
)

reference_observations = (
    {
        "observation_id": "reference-001",
        "sensor_id": "sensor-1",
        "known_hypothesis": "A",
        "signal": "A",
        "reference_standard_ref": "fixture://known-standard/A/run-1",
        "reference_standard_sha256": sha("known standard A, run 1"),
        "observation_ref": "fixture://sensor-observation/reference-001",
        "observation_sha256": sha("reference observation 001: sensor-1 -> A"),
        "cost": "1/2",
    },
    {
        "observation_id": "reference-002",
        "sensor_id": "sensor-1",
        "known_hypothesis": "A",
        "signal": "A",
        "reference_standard_ref": "fixture://known-standard/A/run-2",
        "reference_standard_sha256": sha("known standard A, run 2"),
        "observation_ref": "fixture://sensor-observation/reference-002",
        "observation_sha256": sha("reference observation 002: sensor-1 -> A"),
        "cost": "1/2",
    },
)

report = build_report(
    prior_hypothesis_a="1/2",
    calibrations=calibrations,
    target_sensor_schedule=("sensor-1", "sensor-2", "sensor-3"),
    reference_observations=reference_observations,
)
validate_report(report)

comparison = report["comparison_in_one_reference_conditioned_target_world"]
reference = report["reference_phase"]
print("RIV-009 exact reference-calibration example")
print("Calibration posterior:")
for item in reference["posterior_calibration_probabilities"]:
    value = item["probability"]
    print(f"  {item['calibration_id']}: {value['numerator']}/{value['denominator']}")
print("Reference evidence probability:", reference["reference_evidence_probability"])
print("Total declared reference cost:", reference["total_declared_reference_cost"])
print("Target policy accuracy in one common reference-conditioned world:")
for name, key in (
    ("uncalibrated prior policy", "uncalibrated_prior_policy_accuracy"),
    ("reference-conditioned Bayes policy", "reference_conditioned_bayes_policy_accuracy"),
    ("MAP-profile plug-in policy", "map_profile_plugin_policy_accuracy"),
):
    value = comparison[key]
    print(f"  {name}: {value['numerator']}/{value['denominator']}")
print("Gain over uncalibrated prior policy:", comparison["reference_conditioned_gain_over_uncalibrated_prior_policy"])
print("Gain over MAP-profile plug-in:", comparison["reference_conditioned_gain_over_map_profile_plugin"])
print("Content digest:", report["content_digest"])
