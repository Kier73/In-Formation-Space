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


if __name__ == "__main__":
    unittest.main()
