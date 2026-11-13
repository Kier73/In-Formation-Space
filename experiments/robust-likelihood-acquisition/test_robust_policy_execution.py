import copy
import hashlib
import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

from robust_likelihood_acquisition import build_joint_belief_document
from robust_sequential_acquisition import build_report as build_policy_report
from robust_policy_execution import (
    INTERPRETATION_METHOD,
    RobustPolicyExecutionError,
    RobustPolicyExecutionMismatch,
    RobustPolicyExecutionStopError,
    build_robust_policy_execution_record,
    new_robust_policy_observation_path,
    validate_robust_policy_execution_record,
)
from observation_path import ObservationIntent, ObservationPath


def digest(value):
    return hashlib.sha256(json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


def belief():
    return build_joint_belief_document(
        joint_posterior=(
            {"hypothesis": "A", "context_state": "fixed", "probability": "1/2"},
            {"hypothesis": "B", "context_state": "fixed", "probability": "1/2"},
        ),
        source_ref="artifact://RIV-017/execution-prior",
        source_report_digest="e" * 64,
    )


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


def adaptive_policy():
    candidates = (
        {"sensor_id": "screen", "dimension": "target", "cost": "1/10", "outcomes": ["yes", "no"]},
        {"sensor_id": "reader-a", "dimension": "target", "cost": "1/10", "outcomes": ["yes", "no"]},
        {"sensor_id": "reader-b", "dimension": "target", "cost": "1/10", "outcomes": ["yes", "no"]},
    )
    scenarios = ({
        "scenario_id": "model-one",
        "candidate_models": [
            {"sensor_id": "screen", "outcome_likelihoods": likelihoods((
                ("yes", "4/5", "1/5"),
                ("no", "1/5", "4/5"),
            ))},
            {"sensor_id": "reader-a", "outcome_likelihoods": likelihoods((
                ("yes", "9/10", "2/5"),
                ("no", "1/10", "3/5"),
            ))},
            {"sensor_id": "reader-b", "outcome_likelihoods": likelihoods((
                ("yes", "3/5", "1/10"),
                ("no", "2/5", "9/10"),
            ))},
        ],
    },)
    return build_policy_report(
        joint_belief=belief(),
        candidate_sensors=candidates,
        model_scenarios=scenarios,
        path_cost_budget="1/5",
        max_measurements=2,
    )


def impossible_outcome_policy():
    candidate = {
        "sensor_id": "meter",
        "dimension": "target",
        "cost": "1/10",
        "outcomes": ["yes", "no", "impossible"],
    }
    scenario = {
        "scenario_id": "only-model",
        "candidate_models": [{
            "sensor_id": "meter",
            "outcome_likelihoods": likelihoods((
                ("yes", "9/10", "1/10"),
                ("no", "1/10", "9/10"),
                ("impossible", 0, 0),
            )),
        }],
    }
    return build_policy_report(
        joint_belief=belief(),
        candidate_sensors=(candidate,),
        model_scenarios=(scenario,),
        path_cost_budget="1/10",
        max_measurements=1,
    )


def locate_node(report, history):
    node = report["selected_policy"]["policy_tree"]
    for prior in history:
        branch = next(
            row for row in node["branches"]
            if row["outcome"] == prior["outcome"]
        )
        node = branch["next"]
    return node


def complete_path(report, prior_paths, attempt_id, outcome, candidate_name_override=None):
    prefix_history = []
    for raw_path in prior_paths:
        snapshot = raw_path.to_dict() if isinstance(raw_path, ObservationPath) else raw_path
        event = next(row for row in snapshot["events"] if row["stage"] == "returned")
        details = event["details"]
        prefix_history.append({
            "sensor_id": details["sensor_id"],
            "outcome": details["observed_outcome"],
        })
    node = locate_node(report, prefix_history)
    planned = new_robust_policy_observation_path(
        policy_report=report,
        prior_observation_paths=prior_paths,
        attempt_id=attempt_id,
    )
    intent = planned.intent
    if candidate_name_override is not None:
        planned = ObservationPath(ObservationIntent(
            attempt_id=intent.attempt_id,
            candidate_name=candidate_name_override,
            query=intent.query,
            hypothesis_set_digest=intent.hypothesis_set_digest,
            estimated_cost=intent.estimated_cost,
            plan_ref=intent.plan_ref,
            authority_required=True,
            application_required=False,
            sender_ack_required=False,
        ))
        intent = planned.intent
    state_digest = intent.hypothesis_set_digest
    node_digest = digest(node)
    candidate = next(
        row for row in report["candidate_sensors"]
        if row["sensor_id"] == node["sensor_id"]
    )
    bindings = {
        "policy_report_digest": report["report_digest"],
        "policy_state_digest": state_digest,
        "policy_node_digest": node_digest,
        "outcome_history_prefix": prefix_history,
        "sensor_id": node["sensor_id"],
        "dimension": candidate["dimension"],
        "measurement_cost": node["measurement_cost"],
        "observed_outcome": outcome,
    }
    planned.append(
        "dispatched", "transport",
        evidence_ref=f"dispatch://{attempt_id}",
        details={"sensor_id": node["sensor_id"], "policy_state_digest": state_digest},
    )
    planned.append(
        "admitted", "receiver",
        evidence_ref=f"admission://{attempt_id}",
        details={"receiver": "sensor-gateway"},
    )
    planned.append(
        "returned", "sensor",
        evidence_ref=f"encounter://{attempt_id}",
        details={
            **bindings,
            "encounter_id": f"encounter-{attempt_id}",
            "payload_digest": digest({"attempt_id": attempt_id, "outcome": outcome}),
            "canonicalization": "canonical-json-v1",
        },
    )
    planned.append(
        "evidence_authorized", "authority",
        evidence_ref=f"consensus://{attempt_id}",
        details={
            "decision_status": "AUTHORIZED",
            "policy_digest": "c" * 64,
            "decision_digest": digest({"attempt_id": attempt_id, "approved": True}),
            "quorum": 2,
            "strict": True,
            "observed_sources": ["source-a", "source-b"],
            "dissenting_sources": [],
            "missing_sources": [],
            "representative_source": "source-a",
        },
    )
    planned.append(
        "interpreted", "interpreter",
        evidence_ref=f"interpretation://{attempt_id}",
        details={
            "method": INTERPRETATION_METHOD,
            **bindings,
        },
    )
    return planned


class RobustPolicyExecutionTests(unittest.TestCase):
    def setUp(self):
        self.report = adaptive_policy()

    def test_authorized_prefix_advances_only_the_selected_policy_branch(self):
        first = complete_path(self.report, (), "attempt-1", "yes")
        next_path = new_robust_policy_observation_path(
            policy_report=self.report,
            prior_observation_paths=(first,),
            attempt_id="attempt-2",
        )
        self.assertEqual(
            next_path.intent.candidate_name,
            "robust-sequential-sensor:reader-a",
        )
        second = complete_path(self.report, (first,), "attempt-2", "yes")
        record = build_robust_policy_execution_record(
            policy_report=self.report,
            observation_paths=(first, second),
        )
        self.assertEqual(record["execution_status"], "authorized_interpreted_policy_terminal")
        self.assertEqual(record["outcome_history"], [
            {"sensor_id": "screen", "outcome": "yes"},
            {"sensor_id": "reader-a", "outcome": "yes"},
        ])
        self.assertEqual(
            record["current_policy_state"]["terminal_decision"],
            "A",
        )
        self.assertEqual(
            ratio(record["current_policy_state"]["total_path_cost"]),
            Fraction(1, 5),
        )
        self.assertEqual(
            ratio(record["current_policy_state"]["remaining_path_cost_budget"]),
            Fraction(0),
        )
        self.assertIsNone(
            record["current_policy_state"]["scenario_identity_posterior"]
        )
        self.assertEqual(validate_robust_policy_execution_record(record), record)

    def test_other_observed_branch_selects_different_second_reader(self):
        first = complete_path(self.report, (), "attempt-1", "no")
        second = new_robust_policy_observation_path(
            policy_report=self.report,
            prior_observation_paths=(first,),
            attempt_id="attempt-2",
        )
        self.assertEqual(
            second.intent.candidate_name,
            "robust-sequential-sensor:reader-b",
        )

    def test_state_binding_rejects_wrong_candidate_node(self):
        wrong = complete_path(
            self.report,
            (),
            "attempt-wrong-node",
            "yes",
            candidate_name_override="robust-sequential-sensor:reader-a",
        )
        with self.assertRaises(RobustPolicyExecutionMismatch):
            build_robust_policy_execution_record(
                policy_report=self.report,
                observation_paths=(wrong,),
            )

    def test_observation_path_requires_authority_before_interpretation(self):
        planned = new_robust_policy_observation_path(
            policy_report=self.report,
            attempt_id="attempt-no-authority",
        )
        planned.append("dispatched", "transport", evidence_ref="dispatch://noauth")
        planned.append("admitted", "receiver", evidence_ref="admission://noauth")
        planned.append(
            "returned", "sensor",
            evidence_ref="encounter://noauth",
            details={
                "encounter_id": "encounter-noauth",
                "payload_digest": "d" * 64,
                "canonicalization": "canonical-json-v1",
            },
        )
        with self.assertRaises(ValueError):
            planned.append(
                "interpreted", "interpreter",
                evidence_ref="interpretation://noauth",
                details={"method": INTERPRETATION_METHOD},
            )

    def test_returned_and_interpreted_outcomes_must_match_exactly(self):
        path = complete_path(self.report, (), "attempt-tamper", "yes")
        snapshot = path.to_dict()
        snapshot["events"][-1]["details"]["observed_outcome"] = "no"
        with self.assertRaises(RobustPolicyExecutionMismatch):
            build_robust_policy_execution_record(
                policy_report=self.report,
                observation_paths=(snapshot,),
            )

    def test_outcome_outside_declared_branch_is_rejected_not_coerced(self):
        path = complete_path(self.report, (), "attempt-unlisted", "maybe")
        with self.assertRaises(RobustPolicyExecutionMismatch):
            build_robust_policy_execution_record(
                policy_report=self.report,
                observation_paths=(path,),
            )

    def test_declared_outcome_impossible_under_every_scenario_stops_for_review(self):
        report = impossible_outcome_policy()
        path = complete_path(report, (), "attempt-model-mismatch", "impossible")
        record = build_robust_policy_execution_record(
            policy_report=report,
            observation_paths=(path,),
        )
        self.assertEqual(
            record["execution_status"],
            "authorized_interpreted_model_mismatch",
        )
        self.assertEqual(
            record["current_policy_state"]["stop_disposition"],
            "stop_and_review",
        )
        self.assertIsNone(record["current_policy_state"]["next_sensor_id"])
        with self.assertRaises(RobustPolicyExecutionStopError):
            new_robust_policy_observation_path(
                policy_report=report,
                prior_observation_paths=(path,),
                attempt_id="attempt-after-mismatch",
            )

    def test_cannot_execute_beyond_a_terminal_policy_node(self):
        first = complete_path(self.report, (), "attempt-1", "yes")
        second = complete_path(self.report, (first,), "attempt-2", "yes")
        with self.assertRaises(RobustPolicyExecutionStopError):
            new_robust_policy_observation_path(
                policy_report=self.report,
                prior_observation_paths=(first, second),
                attempt_id="attempt-after-stop",
            )

    def test_execution_record_rejects_rehashed_state_tampering(self):
        path = complete_path(self.report, (), "attempt-tamper-record", "yes")
        record = build_robust_policy_execution_record(
            policy_report=self.report,
            observation_paths=(path,),
        )
        changed = copy.deepcopy(record)
        changed["current_policy_state"]["scenario_unnormalized_joint_masses"] = {}
        core = {
            key: value for key, value in changed.items()
            if key != "record_digest"
        }
        changed["record_digest"] = digest(core)
        with self.assertRaises(RobustPolicyExecutionError):
            validate_robust_policy_execution_record(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
