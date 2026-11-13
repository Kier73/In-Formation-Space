"""Reproduce the RIV-011 finite-horizon versus greedy policy comparison."""
from __future__ import annotations

import hashlib

from finite_horizon_reference_policy import build_report, validate_report


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
            "sensor-0": channel("9/10", "1/10"),
            "sensor-1": channel("3/5", "4/5"),
            "sensor-2": channel("4/5", "3/5"),
        },
    },
    {
        "calibration_id": "profile-2",
        "prior_probability": "1/2",
        "sensor_models": {
            "sensor-0": channel("3/5", "3/10"),
            "sensor-1": channel("4/5", "3/10"),
            "sensor-2": channel("3/5", "1/5"),
        },
    },
)

specifications = (
    ("sensor-0-standard-A", "sensor-0", "A", "1/2"),
    ("sensor-0-standard-B", "sensor-0", "B", "1"),
    ("sensor-1-standard-A", "sensor-1", "A", "1/2"),
    ("sensor-1-standard-B", "sensor-1", "B", "1/4"),
    ("sensor-2-standard-A", "sensor-2", "A", "5/4"),
    ("sensor-2-standard-B", "sensor-2", "B", "5/4"),
)
reference_candidates = tuple({
    "candidate_id": candidate_id,
    "sensor_id": sensor_id,
    "known_hypothesis": standard,
    "reference_standard_ref": f"fixture://standard/{candidate_id}",
    "reference_standard_sha256": sha(f"known standard: {candidate_id}"),
    "cost": cost,
} for candidate_id, sensor_id, standard, cost in specifications)

report = build_report(
    prior_hypothesis_a="1/2",
    calibrations=calibrations,
    target_sensor_schedule=("sensor-0", "sensor-1", "sensor-2"),
    reference_candidates=reference_candidates,
    max_reference_steps=3,
    cost_budget="3/2",
)
validate_report(report)

print("RIV-011 finite-horizon reference acquisition")
print("Baseline target MAP accuracy:", report["baseline_target_map_accuracy"])
print("Pathwise reference budget:", report["model"]["cost_budget"])
for label, section in (
    ("Finite-horizon DP", report["finite_horizon_policy"]),
    ("Repeated RIV-010 greedy", report["greedy_reselection_policy"]),
):
    print(
        label,
        "accuracy", section["expected_target_map_accuracy"],
        "expected cost", section["expected_reference_cost"],
        "expected reads", section["expected_reference_count"],
        "first action", section["root"]["candidate_id"],
    )

print("Finite-horizon first action:", report["finite_horizon_policy"]["root"]["candidate_id"])
for branch in report["finite_horizon_policy"]["root"]["branches"]:
    child = branch["child"]
    print("  first signal", branch["signal"], "-> next action", child["candidate_id"])
print("Accuracy advantage over greedy:", report["comparison"]["finite_horizon_accuracy_gain_over_greedy"])
print("Policy state count:", report["finite_horizon_policy"]["policy_state_count"])
print("Report digest:", report["report_digest"])
