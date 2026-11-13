"""Reproduce the exact RIV-010 lookahead and authorized reference handoff."""
from __future__ import annotations

import hashlib

from reference_acquisition_lookahead import (
    build_report,
    build_reference_execution_record,
    new_reference_acquisition_observation_path,
    validate_report,
    validate_reference_execution_record,
)


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
            "sensor-2": channel("7/10", "3/10"),
            "sensor-3": channel("9/10", "1/10"),
        },
    },
    {
        "calibration_id": "profile-2",
        "prior_probability": "1/2",
        "sensor_models": {
            "sensor-1": channel("3/5", "2/5"),
            "sensor-2": channel("4/5", "1/5"),
            "sensor-3": channel("1/10", "3/5"),
        },
    },
)

candidates = (
    {
        "candidate_id": "reference-sensor-1-standard-A",
        "sensor_id": "sensor-1",
        "known_hypothesis": "A",
        "reference_standard_ref": "fixture://standard-A/sensor-1",
        "reference_standard_sha256": sha("known A standard for sensor-1"),
        "cost": "1/2",
    },
    {
        "candidate_id": "reference-sensor-2-standard-A",
        "sensor_id": "sensor-2",
        "known_hypothesis": "A",
        "reference_standard_ref": "fixture://standard-A/sensor-2",
        "reference_standard_sha256": sha("known A standard for sensor-2"),
        "cost": "1/2",
    },
    {
        "candidate_id": "reference-sensor-3-standard-A",
        "sensor_id": "sensor-3",
        "known_hypothesis": "A",
        "reference_standard_ref": "fixture://standard-A/sensor-3",
        "reference_standard_sha256": sha("known A standard for sensor-3"),
        "cost": "1/2",
    },
    {
        "candidate_id": "reference-sensor-3-standard-B",
        "sensor_id": "sensor-3",
        "known_hypothesis": "B",
        "reference_standard_ref": "fixture://standard-B/sensor-3",
        "reference_standard_sha256": sha("known B standard for sensor-3"),
        "cost": "1/2",
    },
)

report = build_report(
    prior_hypothesis_a="1/2",
    calibrations=calibrations,
    target_sensor_schedule=("sensor-1", "sensor-2", "sensor-3"),
    reference_candidates=candidates,
)
validate_report(report)

print("RIV-010 one-reference-step lookahead")
print("Baseline target MAP accuracy:", report["baseline_target_map_accuracy"])
print("Candidates (myopic RIV-008 EVSI -> downstream RIV-010 value):")
for candidate in report["candidate_evaluations"]:
    print(
        " ",
        candidate["candidate_id"],
        candidate["myopic_riv008_comparator"]["expected_bayes_risk_reduction"],
        "->",
        candidate["expected_downstream_decision_value"],
        "per cost",
        candidate["expected_downstream_decision_value_per_cost"],
    )
print("Selected reference:", report["selection"]["selected_candidate_id"])

# This is a fixture, not a claim that a physical dispatch occurred.
path = new_reference_acquisition_observation_path(
    reference_acquisition_report=report,
    attempt_id="fixture-reference-attempt-001",
)
selected = next(
    item for item in report["candidate_evaluations"]
    if item["candidate_id"] == report["selection"]["selected_candidate_id"]
)
path.append(
    "dispatched", "fixture-sensor-agent",
    evidence_ref="fixture://dispatch/001",
    details={"request_id": "fixture-reference-attempt-001"},
)
path.append(
    "admitted", "fixture-receiver",
    evidence_ref="fixture://admission/001",
    details={"receiver_id": "fixture-reference-receiver"},
)
signal = "A"
path.append(
    "returned", "fixture-receiver",
    evidence_ref="fixture://encounter/001",
    details={
        "encounter_id": "fixture-encounter-001",
        "payload_digest": sha("fixture observed signal A"),
        "canonicalization": "canonical-json-v1",
        "candidate_id": selected["candidate_id"],
        "sensor_id": selected["sensor_id"],
        "dimension": "calibration-reference",
        "known_hypothesis": selected["known_hypothesis"],
        "reference_standard_ref": selected["reference_standard_ref"],
        "reference_standard_sha256": selected["reference_standard_sha256"],
        "reference_acquisition_report_digest": report["report_digest"],
        "observed_outcome": signal,
    },
)
path.append(
    "evidence_authorized", "fixture-authority",
    evidence_ref="fixture://authority/001",
    details={
        "decision_status": "AUTHORIZED",
        "policy_digest": sha("fixture policy"),
        "decision_digest": sha("fixture authorized decision"),
        "quorum": 2,
        "strict": True,
        "observed_sources": ["reference-a", "reference-b"],
        "dissenting_sources": [],
        "missing_sources": [],
        "representative_source": "reference-a",
    },
)
path.append(
    "interpreted", "fixture-interpreter",
    evidence_ref="fixture://interpretation/001",
    details={
        "method": "exact-calibration-reference-outcome-v1",
        "candidate_id": selected["candidate_id"],
        "sensor_id": selected["sensor_id"],
        "dimension": "calibration-reference",
        "known_hypothesis": selected["known_hypothesis"],
        "reference_standard_ref": selected["reference_standard_ref"],
        "reference_standard_sha256": selected["reference_standard_sha256"],
        "reference_acquisition_report_digest": report["report_digest"],
        "observed_outcome": signal,
    },
)
record = build_reference_execution_record(
    reference_acquisition_report=report,
    observation_path=path,
)
validate_reference_execution_record(record)

print("Authorized reference:", record["reference_observation"])
print(
    "RIV-009 posterior calibration:",
    record["updated_riv009_report"]["reference_phase"]["posterior_calibration_probabilities"],
)
print("Execution record digest:", record["record_digest"])
