"""Reproduce a two-step authorized policy prefix and cumulative RIV-009 update."""
from __future__ import annotations

import hashlib
import json

from finite_horizon_reference_policy import build_report
from finite_horizon_policy_execution import (
    build_reference_policy_execution_record,
    new_reference_policy_observation_path,
    validate_reference_policy_execution_record,
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
            "sensor-0": channel("1/2", "1/2"),
            "sensor-1": channel("1/10", "4/5"),
            "sensor-2": channel("7/10", "7/10"),
        },
    },
    {
        "calibration_id": "profile-2",
        "prior_probability": "1/2",
        "sensor_models": {
            "sensor-0": channel("1/10", "9/10"),
            "sensor-1": channel("2/5", "4/5"),
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
candidates = tuple({
    "candidate_id": candidate_id,
    "sensor_id": sensor_id,
    "known_hypothesis": standard,
    "reference_standard_ref": f"fixture://standard/{candidate_id}",
    "reference_standard_sha256": sha(f"known standard: {candidate_id}"),
    "cost": cost,
} for candidate_id, sensor_id, standard, cost in specifications)

policy = build_report(
    prior_hypothesis_a="1/2",
    calibrations=calibrations,
    target_sensor_schedule=("sensor-0", "sensor-1", "sensor-2"),
    reference_candidates=candidates,
    max_reference_steps=3,
    cost_budget="3/2",
)


def active_node(prior_paths):
    node = policy["finite_horizon_policy"]["root"]
    for path in prior_paths:
        snapshot = path.to_dict()
        returned = next(event for event in snapshot["events"] if event["stage"] == "returned")
        signal = returned["details"]["observed_outcome"]
        node = next(branch["child"] for branch in node["branches"] if branch["signal"] == signal)
    return node


def authorized_fixture_path(attempt_id, prior_paths, signal):
    node = active_node(prior_paths)
    path = new_reference_policy_observation_path(
        policy_report=policy,
        prior_observation_paths=prior_paths,
        attempt_id=attempt_id,
    )
    state_digest = path.intent.hypothesis_set_digest
    node_digest = sha(json.dumps(
        node, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ))
    shared = {
        "policy_report_digest": policy["report_digest"],
        "policy_state_digest": state_digest,
        "policy_node_digest": node_digest,
        "history_signal_prefix": [
            next(e for e in p.to_dict()["events"] if e["stage"] == "returned")["details"]["observed_outcome"]
            for p in prior_paths
        ],
        "candidate_id": node["candidate_id"],
        "sensor_id": node["sensor_id"],
        "dimension": "calibration-reference",
        "known_hypothesis": node["known_hypothesis"],
        "reference_standard_ref": node["reference_standard_ref"],
        "reference_standard_sha256": node["reference_standard_sha256"],
        "observed_outcome": signal,
    }
    payload_digest = sha(f"fixture payload {attempt_id} {signal}")
    path.append(
        "dispatched", "fixture-sensor",
        evidence_ref=f"fixture://dispatch/{attempt_id}",
        details={"request_id": attempt_id},
    )
    path.append(
        "admitted", "fixture-receiver",
        evidence_ref=f"fixture://admission/{attempt_id}",
        details={"receiver_id": "fixture-receiver-01"},
    )
    path.append(
        "returned", "fixture-receiver",
        evidence_ref=f"fixture://encounter/{attempt_id}",
        details={
            **shared,
            "encounter_id": f"fixture-encounter-{attempt_id}",
            "payload_digest": payload_digest,
            "canonicalization": "canonical-json-v1",
        },
    )
    path.append(
        "evidence_authorized", "fixture-authority",
        evidence_ref=f"fixture://authority/{attempt_id}",
        details={
            "decision_status": "AUTHORIZED",
            "policy_digest": sha("fixture authority policy"),
            "decision_digest": sha(f"fixture authority decision {attempt_id}"),
            "quorum": 2,
            "strict": True,
            "observed_sources": ["fixture-source-a", "fixture-source-b"],
            "dissenting_sources": [],
            "missing_sources": [],
            "representative_source": "fixture-source-a",
        },
    )
    path.append(
        "interpreted", "fixture-interpreter",
        evidence_ref=f"fixture://interpretation/{attempt_id}",
        details={
            **shared,
            "method": "finite-horizon-reference-signal-v1",
        },
    )
    return path


# Synthetic fixture paths demonstrate the contract; no physical dispatch occurs.
first = authorized_fixture_path("fixture-reference-001", (), "A")
second = authorized_fixture_path("fixture-reference-002", (first,), "A")
record = build_reference_policy_execution_record(
    policy_report=policy,
    observation_paths=(first, second),
)
validate_reference_policy_execution_record(record)

print("RIV-012 finite-horizon policy execution")
print("Observed reference sequence:", record["signal_history"])
print("Authorized reference rows:", len(record["reference_observations"]))
print("Cumulative calibration posterior:", record["current_policy_state"]["calibration_posterior"])
print("Next policy action:", record["current_policy_state"]["next_action"])
print("Remaining path budget:", record["current_policy_state"]["remaining_cost_budget"])
print("Cumulative RIV-009 report digest:", record["updated_riv009_report"]["content_digest"])
print("Execution record digest:", record["record_digest"])
