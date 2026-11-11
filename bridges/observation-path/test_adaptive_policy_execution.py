import unittest
from dataclasses import dataclass

from adaptive_policy_execution import AdaptivePolicyExecution


@dataclass(frozen=True)
class Node:
    hypotheses: tuple
    query_result: object
    observation_name: object
    branches: tuple


@dataclass(frozen=True)
class Plan:
    complete: bool
    policy: object


@dataclass(frozen=True)
class Candidate:
    name: str
    cost: float


def digest(hypotheses):
    return "sha256:" + "|".join(str(value) for value in hypotheses)


def candidate_set():
    return (
        Candidate("left-refinement", 1.0),
        Candidate("right-refinement", 1.0),
    )


def adaptive_plan():
    true_a = Node(("A",), True, None, ())
    true_b = Node(("B",), True, None, ())
    false_c = Node(("C",), False, None, ())
    false_d = Node(("D",), False, None, ())
    right = Node(
        ("B", "D"),
        None,
        "right-refinement",
        (("yes", true_b), ("no", false_d)),
    )
    root = Node(
        ("A", "B", "C", "D"),
        None,
        "left-refinement",
        (("yes", true_a), ("no", false_c), ("same", right)),
    )
    return Plan(True, root)


class AdaptivePolicyExecutionTests(unittest.TestCase):
    def setUp(self):
        self.execution = AdaptivePolicyExecution(
            adaptive_plan(),
            candidate_set(),
            attempt_id_prefix="query-01",
            query_label="Is the hidden state in {A, B}?",
            hypothesis_digest=digest,
            plan_ref="plans/policy-01.json",
        )

    def dispatch_and_admit(self):
        self.execution.mark_dispatched(
            "host", "transport/send.json",
            clock_value="100", clock_domain="host-clock",
        )
        self.execution.mark_admitted(
            "receiver", "receiver/admission.json",
            clock_value="12", clock_domain="receiver-clock",
        )

    def return_value(self, value, name="reading"):
        self.execution.record_return(
            "sensor",
            evidence_ref=f"encounters/{name}.json",
            encounter_id=name,
            payload_digest=f"sha256:{name}",
            canonicalization="utf8-raw-v1",
            clock_value="14",
            clock_domain="sensor-clock",
        )
        return self.execution.interpret(
            value,
            actor="interpreter",
            method="sensor-value-parser-v1",
            evidence_ref=f"interpretations/{name}.json",
        )

    def test_adaptive_branch_continues_then_resolves(self):
        path = self.execution.begin_attempt()
        self.assertEqual(path.status, "planned")
        self.assertEqual(path.intent.candidate_name, "left-refinement")
        self.dispatch_and_admit()
        intermediate = self.return_value("same", "first")
        self.assertEqual(intermediate.status, "ready")
        self.assertIsNone(intermediate.query_result)
        self.assertEqual(intermediate.attempts[0]["status"], "continued")
        self.assertEqual(intermediate.attempts[0]["events"][-1]["details"]["next_candidate_name"], "right-refinement")

        second_path = self.execution.begin_attempt()
        self.assertEqual(second_path.intent.candidate_name, "right-refinement")
        self.dispatch_and_admit()
        final = self.return_value("yes", "second")
        self.assertEqual(final.status, "resolved")
        self.assertTrue(final.query_result)
        self.assertEqual(len(final.attempts), 2)
        self.assertEqual(final.attempts[1]["status"], "query_determined")

    def test_observed_outcome_outside_policy_model_stops_without_guessing(self):
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        result = self.return_value("unexpected", "unexpected")
        self.assertEqual(result.status, "unresolved_model_mismatch")
        self.assertIsNone(result.query_result)
        self.assertEqual(result.attempts[0]["status"], "unresolved")
        self.assertEqual(
            result.attempts[0]["events"][-1]["details"]["reason"],
            "interpreted observation value was not predicted by the policy",
        )

    def test_planning_does_not_imply_transport_execution(self):
        path = self.execution.begin_attempt()
        result = self.execution.result()
        self.assertEqual(result.status, "planned")
        self.assertEqual(path.status, "planned")
        self.assertEqual(len(path.events), 1)

    def test_receiver_rejection_terminates_attempt_without_sensor_value(self):
        self.execution.begin_attempt()
        self.execution.mark_dispatched("host", "transport/send.json")
        result = self.execution.stop_rejected("receiver", "not admitted")
        self.assertEqual(result.status, "rejected")
        self.assertIsNone(result.query_result)
        self.assertEqual(result.attempts[0]["status"], "rejected")

    def test_timeout_is_not_a_negative_observation(self):
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        result = self.execution.stop_no_result("sensor", "timeout")
        self.assertEqual(result.status, "no_result")
        self.assertIsNone(result.query_result)
        self.assertFalse(any(
            event["stage"] == "returned"
            for event in result.attempts[0]["events"]
        ))

    def test_incomplete_policy_is_not_executable(self):
        with self.assertRaises(ValueError):
            AdaptivePolicyExecution(
                Plan(False, None),
                candidate_set(),
                attempt_id_prefix="query-03",
                query_label="q",
                hypothesis_digest=digest,
            )

    def test_dispatch_failure_is_terminal_and_not_a_sensor_value(self):
        self.execution.begin_attempt()
        self.execution.stop_dispatch_failed("host", "connection unavailable")
        result = self.execution.result()
        self.assertEqual(result.status, "dispatch_failed")
        self.assertIsNone(result.query_result)
        self.assertEqual(result.attempts[0]["events"][-1]["details"]["reason"], "connection unavailable")

    def test_unadmitted_return_is_preserved_but_never_interpreted(self):
        self.execution.begin_attempt()
        self.execution.mark_dispatched("host", "transport/send.json")
        result = self.execution.record_unadmitted_return(
            "transport",
            evidence_ref="encounters/unadmitted.json",
            encounter_id="unadmitted-01",
            payload_digest="sha256:unadmitted",
            canonicalization="utf8-raw-v1",
        )
        self.assertEqual(result.status, "returned_unadmitted")
        self.assertEqual(result.attempts[0]["events"][-1]["stage"], "returned_unadmitted")
        with self.assertRaises(ValueError):
            self.execution.interpret("same", actor="interpreter", method="v1", evidence_ref="interpretation.json")

    def test_interpreter_failure_keeps_raw_return_reference(self):
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.execution.record_return(
            "sensor", evidence_ref="encounters/raw.json", encounter_id="raw-01",
            payload_digest="sha256:raw", canonicalization="utf8-raw-v1",
        )
        result = self.execution.stop_interpretation_failed("interpreter", "invalid encoding")
        self.assertEqual(result.status, "interpretation_failed")
        stages = [event["stage"] for event in result.attempts[0]["events"]]
        self.assertIn("returned", stages)
        self.assertEqual(stages[-1], "interpretation_failed")

    def test_policy_reference_to_missing_next_observation_stops_unresolved(self):
        terminal = Node(("A",), True, None, ())
        missing = Node(("B", "C"), None, "not-installed", (("yes", terminal),))
        root = Node(("A", "B", "C"), None, "left-refinement", (("continue", missing),))
        self.execution = AdaptivePolicyExecution(
            Plan(True, root), candidate_set(), attempt_id_prefix="query-missing",
            query_label="q", hypothesis_digest=digest,
        )
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        result = self.return_value("continue", "missing-next")
        self.assertEqual(result.status, "unresolved_missing_candidate")
        self.assertEqual(result.attempts[0]["status"], "unresolved")

    def test_pre_resolved_root_needs_no_transport_attempt(self):
        self.execution = AdaptivePolicyExecution(
            Plan(True, Node(("A", "B"), False, None, ())),
            candidate_set(), attempt_id_prefix="query-trivial",
            query_label="q", hypothesis_digest=digest,
        )
        result = self.execution.result()
        self.assertEqual(result.status, "resolved")
        self.assertFalse(result.query_result)
        self.assertEqual(result.attempts, ())
    def test_quorum_authority_gate_precedes_policy_interpretation(self):
        self.execution = AdaptivePolicyExecution(
            adaptive_plan(), candidate_set(), attempt_id_prefix="query-authority",
            query_label="q", hypothesis_digest=digest, evidence_authority_required=True,
        )
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.execution.record_return(
            "sensor", evidence_ref="encounters/first.json", encounter_id="first",
            payload_digest="sha256:first", canonicalization="utf8-raw-v1",
        )
        with self.assertRaises(ValueError):
            self.execution.interpret("same", actor="interpreter", method="v1", evidence_ref="interpretation.json")
        self.execution.mark_evidence_authorized(
            "consensus", "consensus/authorized.json",
            policy_digest="sha256:policy", decision_digest="sha256:decision",
            quorum=2, strict=True, observed_sources=("A", "B"),
            representative_source="A",
        )
        result = self.execution.interpret(
            "same", actor="interpreter", method="v1", evidence_ref="interpretations/first.json"
        )
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.attempts[0]["status"], "continued")
        stages = [event["stage"] for event in result.attempts[0]["events"]]
        self.assertLess(stages.index("evidence_authorized"), stages.index("interpreted"))

    def test_evidence_refusal_ends_without_interpreting_return(self):
        self.execution = AdaptivePolicyExecution(
            adaptive_plan(), candidate_set(), attempt_id_prefix="query-refused",
            query_label="q", hypothesis_digest=digest, evidence_authority_required=True,
        )
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.execution.record_return(
            "sensor", evidence_ref="encounters/conflict.json", encounter_id="conflict",
            payload_digest="sha256:conflict", canonicalization="utf8-raw-v1",
        )
        result = self.execution.mark_evidence_refused(
            "consensus", "consensus/conflict.json", decision_status="CONFLICT",
            policy_digest="sha256:policy", decision_digest="sha256:decision",
            quorum=2, strict=True, observed_sources=("A", "B"),
            dissenting_sources=("B",), missing_sources=(), reason="sources disagreed",
        )
        self.assertEqual(result.status, "evidence_refused")
        self.assertIsNone(result.query_result)
        self.assertFalse(any(event["stage"] == "interpreted" for event in result.attempts[0]["events"]))

    def test_receiver_application_gate_precedes_interpretation(self):
        self.execution = AdaptivePolicyExecution(
            adaptive_plan(), candidate_set(), attempt_id_prefix="query-applied",
            query_label="q", hypothesis_digest=digest, evidence_authority_required=True,
            receiver_application_required=True,
        )
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.execution.record_return(
            "sensor", evidence_ref="encounters/application.json", encounter_id="application",
            payload_digest="sha256:application", canonicalization="utf8-raw-v1",
        )
        self.execution.mark_evidence_authorized(
            "consensus", "consensus/authorized.json", policy_digest="sha256:policy",
            decision_digest="sha256:decision", quorum=2, strict=True,
            observed_sources=("A", "B"), representative_source="A",
        )
        with self.assertRaises(ValueError):
            self.execution.interpret("yes", actor="interpreter", method="v1", evidence_ref="interpretation.json")
        self.execution.mark_applied(
            "receiver-vm", "vm/application-receipt.json", application_id="event-01",
            target_id="vm-task-7", projection_digest="sha256:projection",
            register_prefix="gated",
        )
        result = self.execution.interpret(
            "yes", actor="interpreter", method="v1", evidence_ref="interpretations/application.json"
        )
        self.assertEqual(result.status, "resolved")
        self.assertTrue(result.query_result)
        stages = [event["stage"] for event in result.attempts[0]["events"]]
        self.assertLess(stages.index("evidence_authorized"), stages.index("applied"))
        self.assertLess(stages.index("applied"), stages.index("interpreted"))

    def test_receiver_application_failure_is_terminal(self):
        self.execution = AdaptivePolicyExecution(
            adaptive_plan(), candidate_set(), attempt_id_prefix="query-apply-failed",
            query_label="q", hypothesis_digest=digest, evidence_authority_required=True,
            receiver_application_required=True,
        )
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.execution.record_return(
            "sensor", evidence_ref="encounters/application.json", encounter_id="application",
            payload_digest="sha256:application", canonicalization="utf8-raw-v1",
        )
        self.execution.mark_evidence_authorized(
            "consensus", "consensus/authorized.json", policy_digest="sha256:policy",
            decision_digest="sha256:decision", quorum=2, strict=True,
            observed_sources=("A", "B"), representative_source="A",
        )
        result = self.execution.stop_application_failed("receiver-vm", "commit checkpoint unavailable")
        self.assertEqual(result.status, "application_failed")
        self.assertIsNone(result.query_result)
    def authority_execution(self, application_required=False, sender_ack_required=False):
        return AdaptivePolicyExecution(
            adaptive_plan(), candidate_set(), attempt_id_prefix="query-ecpu",
            query_label="q", hypothesis_digest=digest, evidence_authority_required=True,
            receiver_application_required=application_required,
            sender_acknowledgement_required=sender_ack_required,
        )

    def authorize_current_return(self):
        self.execution.mark_evidence_authorized(
            "consensus", "consensus/authorized.json",
            policy_digest="sha256:policy", decision_digest="sha256:decision",
            quorum=2, strict=True, observed_sources=("source-a", "source-b"),
            representative_source="source-a",
        )

    def record_current_return(self):
        self.execution.record_return(
            "sensor", evidence_ref="encounters/raw.json", encounter_id="raw-01",
            payload_digest="sha256:raw", canonicalization="utf8-raw-v1",
        )

    def test_quorum_authorization_required_before_interpretation(self):
        self.execution = self.authority_execution()
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.record_current_return()
        with self.assertRaises(ValueError):
            self.execution.interpret("same", actor="interpreter", method="v1", evidence_ref="interpretation.json")
        self.authorize_current_return()
        result = self.execution.interpret("same", actor="interpreter", method="v1", evidence_ref="interpretation.json")
        self.assertEqual(result.status, "ready")
        stages = [event["stage"] for event in result.attempts[0]["events"]]
        self.assertLess(stages.index("returned"), stages.index("evidence_authorized"))
        self.assertLess(stages.index("evidence_authorized"), stages.index("interpreted"))

    def test_evidence_refusal_is_terminal_after_raw_return(self):
        self.execution = self.authority_execution()
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.record_current_return()
        result = self.execution.mark_evidence_refused(
            "consensus", "consensus/refused.json", decision_status="CONFLICT",
            policy_digest="sha256:policy", decision_digest="sha256:decision",
            quorum=2, strict=True, observed_sources=("A", "B"),
            dissenting_sources=("B",), missing_sources=(), reason="source disagreement",
        )
        self.assertEqual(result.status, "evidence_refused")
        self.assertIsNone(result.query_result)

    def test_receiver_application_must_follow_authority_and_precede_interpretation(self):
        self.execution = self.authority_execution(application_required=True)
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.record_current_return()
        self.authorize_current_return()
        with self.assertRaises(ValueError):
            self.execution.interpret("yes", actor="interpreter", method="v1", evidence_ref="interpretation.json")
        self.execution.mark_applied(
            "receiver-vm", "vm/application-receipt.json", application_id="event-01",
            target_id="vm-task-7", projection_digest="sha256:projection", register_prefix="gated",
        )
        result = self.execution.interpret("yes", actor="interpreter", method="v1", evidence_ref="interpretation.json")
        self.assertEqual(result.status, "resolved")
        self.assertTrue(result.query_result)

    def test_application_failure_prevents_query_interpretation(self):
        self.execution = self.authority_execution(application_required=True)
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.record_current_return()
        self.authorize_current_return()
        result = self.execution.stop_application_failed("receiver-vm", "commit receipt unavailable")
        self.assertEqual(result.status, "application_failed")
        self.assertIsNone(result.query_result)


    def test_sender_acknowledgement_is_required_before_policy_interpretation(self):
        self.execution = self.authority_execution(application_required=True, sender_ack_required=True)
        self.execution.begin_attempt()
        self.dispatch_and_admit()
        self.record_current_return()
        self.authorize_current_return()
        self.execution.mark_applied(
            "receiver-vm", "vm/checkpoint.json", application_id="event-01",
            target_id="vm-task-7", projection_digest="sha256:projection", register_prefix="gated",
        )
        with self.assertRaises(ValueError):
            self.execution.interpret("yes", actor="interpreter", method="v1", evidence_ref="interpretation.json")
        self.execution.mark_sender_acknowledged(
            "sender", "acks/event-01.json", event_kind="phase", logical_time=7,
            sources=("source-a", "source-b"),
            expected_event_sequences=(
                {"source": "source-a", "channel": "phase-A", "sequence": 3},
                {"source": "source-b", "channel": "phase-B", "sequence": 5},
            ),
            acknowledged_sequences=(
                {"source": "source-a", "channel": "phase-A", "sequence": 3},
                {"source": "source-b", "channel": "phase-B", "sequence": 5},
            ),
            ack_digest="a" * 64,
        )
        result = self.execution.interpret(
            "yes", actor="interpreter", method="v1", evidence_ref="interpretation.json"
        )
        self.assertEqual(result.status, "resolved")
        stages = [event["stage"] for event in result.attempts[0]["events"]]
        self.assertLess(stages.index("applied"), stages.index("sender_acknowledged"))
        self.assertLess(stages.index("sender_acknowledged"), stages.index("interpreted"))

    def test_sender_ack_requirement_implies_receiver_application(self):
        with self.assertRaises(ValueError):
            AdaptivePolicyExecution(
                adaptive_plan(), candidate_set(), attempt_id_prefix="query-invalid-ack",
                query_label="q", hypothesis_digest=digest,
                evidence_authority_required=True,
                receiver_application_required=False,
                sender_acknowledgement_required=True,
            )

if __name__ == "__main__":
    unittest.main()
