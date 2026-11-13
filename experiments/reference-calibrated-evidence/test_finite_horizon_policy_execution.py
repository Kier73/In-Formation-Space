from __future__ import annotations

import copy
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

import jsonschema

from finite_horizon_policy_execution import (
    PolicyExecutionError,
    PolicyExecutionMismatch,
    PolicyExecutionStopError,
    build_reference_policy_execution_record,
    new_reference_policy_observation_path,
    validate_reference_policy_execution_record,
)
from finite_horizon_reference_policy import build_report

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "finite-horizon-policy-execution.schema.json").read_text(encoding="utf-8"))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


def channel(alpha, beta):
    return {
        "p_signal_a_given_hypothesis_a": alpha,
        "p_signal_a_given_hypothesis_b": beta,
    }


def policy_fixture():
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
    return build_report(
        prior_hypothesis_a="1/2",
        calibrations=calibrations,
        target_sensor_schedule=("sensor-0", "sensor-1", "sensor-2"),
        reference_candidates=candidates,
        max_reference_steps=3,
        cost_budget="3/2",
    )


def active_node(report, prior_paths):
    node = report["finite_horizon_policy"]["root"]
    history = []
    for raw in prior_paths:
        snapshot = raw.to_dict() if hasattr(raw, "to_dict") else raw
        returned = next(event for event in snapshot["events"] if event["stage"] == "returned")
        signal = returned["details"]["observed_outcome"]
        branch = next(row for row in node["branches"] if row["signal"] == signal)
        node = branch["child"]
        history.append(signal)
    return node, history


def make_path(report, prior_paths=(), *, attempt_id="attempt-001", signal="A", authorize=True, mutate=None):
    node, history = active_node(report, prior_paths)
    path = new_reference_policy_observation_path(
        policy_report=report,
        prior_observation_paths=prior_paths,
        attempt_id=attempt_id,
    )
    candidate_id = node["candidate_id"]
    node_digest = sha(json.dumps(
        node, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ))
    details = {
        "policy_report_digest": report["report_digest"],
        "policy_state_digest": path.intent.hypothesis_set_digest,
        "policy_node_digest": node_digest,
        "history_signal_prefix": history,
        "candidate_id": candidate_id,
        "sensor_id": node["sensor_id"],
        "dimension": "calibration-reference",
        "known_hypothesis": node["known_hypothesis"],
        "reference_standard_ref": node["reference_standard_ref"],
        "reference_standard_sha256": node["reference_standard_sha256"],
        "observed_outcome": signal,
    }
    if mutate:
        details.update(mutate)
    payload_digest = sha(f"reference payload {attempt_id} signal {signal}")
    returned = {
        **details,
        "encounter_id": f"encounter://{attempt_id}",
        "payload_digest": payload_digest,
        "canonicalization": "canonical-json-v1",
    }
    path.append(
        "dispatched", "reference-dispatcher",
        evidence_ref=f"dispatch://{attempt_id}",
        details={"request_id": attempt_id},
    )
    path.append(
        "admitted", "reference-receiver",
        evidence_ref=f"admission://{attempt_id}",
        details={"receiver_id": "reference-receiver-01"},
    )
    path.append(
        "returned", "reference-receiver",
        evidence_ref=f"encounter://{attempt_id}",
        details=returned,
    )
    if authorize:
        path.append(
            "evidence_authorized", "reference-authority",
            evidence_ref=f"authority://{attempt_id}",
            details={
                "decision_status": "AUTHORIZED",
                "policy_digest": sha("reference authority policy"),
                "decision_digest": sha(f"authority decision {attempt_id}"),
                "quorum": 2,
                "strict": True,
                "observed_sources": ["reference-source-a", "reference-source-b"],
                "dissenting_sources": [],
                "missing_sources": [],
                "representative_source": "reference-source-a",
            },
        )
        path.append(
            "interpreted", "reference-interpreter",
            evidence_ref=f"interpretation://{attempt_id}",
            details={**details, "method": "finite-horizon-reference-signal-v1"},
        )
    return path


class FiniteHorizonPolicyExecutionTests(unittest.TestCase):
    def setUp(self):
        self.report = policy_fixture()

    def test_path_creation_binds_the_current_adaptive_policy_node(self):
        first = new_reference_policy_observation_path(
            policy_report=self.report,
            attempt_id="attempt-001",
        )
        self.assertEqual(first.status, "planned")
        self.assertTrue(first.intent.authority_required)
        self.assertFalse(first.intent.application_required)
        self.assertFalse(first.intent.sender_ack_required)
        self.assertEqual(first.intent.candidate_name, "finite-horizon-reference:sensor-0-standard-A")

    def test_authorized_first_result_advances_to_signal_specific_child(self):
        first = make_path(self.report, signal="A")
        record = build_reference_policy_execution_record(
            policy_report=self.report,
            observation_paths=(first,),
        )
        state = record["current_policy_state"]
        self.assertEqual(state["next_action"], "sensor-1-standard-A")
        posterior = {
            row["calibration_id"]: ratio(row["probability"])
            for row in state["calibration_posterior"]
        }
        self.assertEqual(
            posterior,
            {"profile-1": Fraction(5, 6), "profile-2": Fraction(1, 6)},
        )
        self.assertEqual(len(record["reference_observations"]), 1)
        self.assertEqual(
            record["updated_riv009_report"]["reference_phase"]["observation_count"],
            1,
        )
        self.assertEqual(validate_reference_policy_execution_record(record), record)

    def test_opposite_first_result_advances_to_a_different_child_action(self):
        first = make_path(self.report, signal="B")
        record = build_reference_policy_execution_record(
            policy_report=self.report,
            observation_paths=(first,),
        )
        self.assertEqual(
            record["current_policy_state"]["next_action"],
            "sensor-0-standard-A",
        )
        posterior = {
            row["calibration_id"]: ratio(row["probability"])
            for row in record["current_policy_state"]["calibration_posterior"]
        }
        self.assertEqual(
            posterior,
            {"profile-1": Fraction(1, 10), "profile-2": Fraction(9, 10)},
        )

    def test_two_step_prefix_rebuilds_cumulative_riv009_and_next_action(self):
        first = make_path(self.report, signal="A", attempt_id="attempt-001")
        second = make_path(
            self.report,
            prior_paths=(first,),
            signal="A",
            attempt_id="attempt-002",
        )
        record = build_reference_policy_execution_record(
            policy_report=self.report,
            observation_paths=(first, second),
        )
        self.assertEqual(
            [row["signal"] for row in record["reference_observations"]],
            ["A", "A"],
        )
        self.assertEqual(
            record["updated_riv009_report"]["reference_phase"]["observation_count"],
            2,
        )
        self.assertEqual(
            record["current_policy_state"]["next_action"],
            "sensor-1-standard-A",
        )
        self.assertEqual(
            record["current_policy_state"]["remaining_reference_steps"],
            1,
        )
        self.assertLessEqual(
            ratio(record["current_policy_state"]["remaining_cost_budget"]),
            Fraction(3, 2),
        )

    def test_three_step_authorized_prefix_stops_at_horizon_and_spends_at_most_budget(self):
        first = make_path(self.report, signal="A", attempt_id="attempt-001")
        second = make_path(self.report, prior_paths=(first,), signal="A", attempt_id="attempt-002")
        third = make_path(self.report, prior_paths=(first, second), signal="A", attempt_id="attempt-003")
        record = build_reference_policy_execution_record(
            policy_report=self.report,
            observation_paths=(first, second, third),
        )
        self.assertIsNone(record["current_policy_state"]["next_action"])
        self.assertEqual(record["current_policy_state"]["remaining_reference_steps"], 0)
        self.assertEqual(ratio(record["current_policy_state"]["remaining_cost_budget"]), Fraction(0))
        self.assertEqual(len(record["reference_observations"]), 3)
        self.assertEqual(validate_reference_policy_execution_record(record), record)

    def test_planning_next_step_after_policy_stop_is_rejected(self):
        first = make_path(self.report, signal="A", attempt_id="attempt-001")
        second = make_path(self.report, prior_paths=(first,), signal="A", attempt_id="attempt-002")
        third = make_path(self.report, prior_paths=(first, second), signal="A", attempt_id="attempt-003")
        with self.assertRaises(PolicyExecutionStopError):
            new_reference_policy_observation_path(
                policy_report=self.report,
                prior_observation_paths=(first, second, third),
                attempt_id="attempt-004",
            )

    def test_stale_path_from_another_policy_prefix_is_rejected(self):
        first = make_path(self.report, signal="A", attempt_id="attempt-001")
        stale = make_path(self.report, signal="A", attempt_id="attempt-002")
        with self.assertRaises(PolicyExecutionMismatch):
            build_reference_policy_execution_record(
                policy_report=self.report,
                observation_paths=(first, stale),
            )

    def test_missing_authority_cannot_advance_the_policy(self):
        path = make_path(self.report, authorize=False)
        with self.assertRaises((PolicyExecutionError, ValueError)):
            build_reference_policy_execution_record(
                policy_report=self.report,
                observation_paths=(path,),
            )

    def test_wrong_candidate_or_standard_is_rejected(self):
        bad = make_path(
            self.report,
            mutate={"candidate_id": "sensor-2-standard-B"},
        )
        with self.assertRaises(PolicyExecutionMismatch):
            build_reference_policy_execution_record(
                policy_report=self.report,
                observation_paths=(bad,),
            )
        bad = make_path(
            self.report,
            mutate={"reference_standard_sha256": sha("different standard")},
        )
        with self.assertRaises(PolicyExecutionMismatch):
            build_reference_policy_execution_record(
                policy_report=self.report,
                observation_paths=(bad,),
            )

    def test_unreachable_signal_cannot_update_calibration(self):
        # The selected first action has positive probability for both signals,
        # so replace the declared signal with an invalid label to verify fail-closed behavior.
        bad = make_path(self.report, mutate={"observed_outcome": "UNKNOWN"})
        with self.assertRaises(PolicyExecutionMismatch):
            build_reference_policy_execution_record(
                policy_report=self.report,
                observation_paths=(bad,),
            )

    def test_report_and_paths_are_reconstructed_and_schema_validated(self):
        path = make_path(self.report, signal="A")
        record = build_reference_policy_execution_record(
            policy_report=self.report,
            observation_paths=(path,),
        )
        self.assertEqual(validate_reference_policy_execution_record(record), record)
        jsonschema.Draft202012Validator.check_schema(SCHEMA)
        jsonschema.validate(record, SCHEMA)

    def test_path_tampering_is_rejected_even_with_recomputed_outer_digest(self):
        path = make_path(self.report, signal="A")
        record = build_reference_policy_execution_record(
            policy_report=self.report,
            observation_paths=(path,),
        )
        changed = copy.deepcopy(record)
        changed["observation_paths"][0]["events"][3]["details"]["observed_outcome"] = "B"
        core = {key: value for key, value in changed.items() if key != "record_digest"}
        changed["record_digest"] = sha(json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ))
        with self.assertRaises(PolicyExecutionError):
            validate_reference_policy_execution_record(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
