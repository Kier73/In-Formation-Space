import copy
import hashlib
import json
import unittest
from fractions import Fraction

from vgi import (
    GroundTransitionSystem,
    ObserverContext,
    TransitionObservation,
    TransitionOutcome,
)
from vgi.partial_attention import (
    ProbeScenario,
    TransitionProbe,
    counterfactual_probe_ground,
    score_partial_probe,
)
from vgi.partial_policy import plan_partial_probe_policy

from minimax_policy_execution import (
    MinimaxPartialProbeExecution,
    MinimaxPolicyExecutionError,
    build_decision_receipt,
    validate_decision_receipt,
)


VGI_REVISION = "ac13c1bbd92dfd09f17de51adef7adb2d2088bf6"


def make_execution():
    system = GroundTransitionSystem(
        states=("a", "b"),
        actions=("X", "Y"),
        initial_state="a",
        channels=("out",),
        observations=(
            TransitionObservation(
                "a", "X", (TransitionOutcome("a", (0,)),),
                evidence=("seed-evidence-a",),
            ),
            TransitionObservation(
                "b", "X", (TransitionOutcome("b", (0,)),),
                evidence=("seed-evidence-b",),
            ),
        ),
    )
    observer = ObserverContext.full(system)
    probes = (
        TransitionProbe(
            "a", "Y",
            (
                ProbeScenario(TransitionOutcome("a", (0,))),
                ProbeScenario(TransitionOutcome("b", (1,))),
            ),
            cost=Fraction(1),
            label="observe-a-Y",
        ),
        TransitionProbe(
            "b", "Y",
            (
                ProbeScenario(TransitionOutcome("b", (0,))),
                ProbeScenario(TransitionOutcome("a", (1,))),
            ),
            cost=Fraction(1),
            label="observe-b-Y",
        ),
    )
    policy = plan_partial_probe_policy(system, observer, probes, 1)
    execution = MinimaxPartialProbeExecution(
        system,
        observer,
        policy,
        score_probe=score_partial_probe,
        counterfactual_ground=counterfactual_probe_ground,
        attempt_id_prefix="minimax-test",
        query_label="resolve the two-state transition distinction",
        vgi_revision=VGI_REVISION,
    )
    return system, observer, policy, execution


def return_and_authorize(attempt, suffix):
    attempt.mark_dispatched("sender", f"dispatch:{suffix}")
    attempt.mark_admitted("receiver", f"admission:{suffix}")
    payload_digest = hashlib.sha256(f"payload:{suffix}".encode()).hexdigest()
    attempt.record_return(
        "receiver",
        evidence_ref=f"encounter:{suffix}",
        encounter_id=f"encounter-id:{suffix}",
        payload_digest=payload_digest,
        canonicalization="canonical-json-v1",
    )
    attempt.path.append(
        "evidence_authorized",
        "authority",
        evidence_ref=f"authority:{suffix}",
        details={
            "decision_status": "AUTHORIZED",
            "policy_digest": "test-authority-policy",
            "decision_digest": f"authority-decision:{suffix}",
            "quorum": 2,
            "strict": True,
            "observed_sources": ["sensor-a", "sensor-b"],
            "dissenting_sources": [],
            "missing_sources": [],
            "representative_source": "sensor-a",
        },
    )


class MinimaxPolicyExecutionTests(unittest.TestCase):
    def test_follows_exact_vgi_branches_and_builds_reconstructable_receipt(self):
        initial, _, policy, execution = make_execution()
        self.assertEqual(execution.status, "ready")
        self.assertEqual(policy.system_fingerprint, initial.fingerprint)

        first_attempt = execution.begin_next()
        self.assertIsNotNone(first_attempt)
        first_probe = first_attempt.score.probe
        first_outcome = first_probe.scenarios[0].outcome
        return_and_authorize(first_attempt, "first")
        first_result = execution.complete_active(
            first_outcome,
            actor="interpreter",
            interpretation_ref="interpretation:first",
        )
        self.assertEqual(first_result.status, "ground_revised")
        self.assertTrue(first_result.scenario_match)
        self.assertEqual(execution.status, "ready")
        self.assertNotEqual(execution.system.fingerprint, initial.fingerprint)
        self.assertEqual(execution.system.status(*first_probe.state_action) if hasattr(first_probe, "state_action") else execution.system.status(first_probe.state, first_probe.action), "known")

        second_attempt = execution.begin_next()
        self.assertIsNotNone(second_attempt)
        second_probe = second_attempt.score.probe
        self.assertNotEqual(
            (first_probe.state, first_probe.action),
            (second_probe.state, second_probe.action),
        )
        second_outcome = second_probe.scenarios[0].outcome
        return_and_authorize(second_attempt, "second")
        second_result = execution.complete_active(
            second_outcome,
            actor="interpreter",
            interpretation_ref="interpretation:second",
        )
        self.assertEqual(second_result.status, "policy_terminal")
        self.assertEqual(execution.status, "complete")

        receipt = build_decision_receipt(execution.to_dict(), policy.to_dict())
        rebuilt = validate_decision_receipt(receipt)
        self.assertEqual(rebuilt, receipt)
        self.assertEqual(len(receipt["decisions"]), 2)
        first_decision = receipt["decisions"][0]
        self.assertIn("seed-evidence-a", first_decision["available_ground_evidence_refs"])
        self.assertIn("admission:first", first_decision["controller_declared_used_evidence_refs"])
        self.assertIn("encounter:first", first_decision["controller_declared_used_evidence_refs"])
        self.assertEqual(first_decision["decision_kind"], "branch_selected")
        self.assertEqual(receipt["clock_policy"]["global_total_order"], None)

    def test_authorization_is_required_before_interpretation_or_ground_revision(self):
        initial, _, _, execution = make_execution()
        attempt = execution.begin_next()
        attempt.mark_dispatched("sender", "dispatch:unauthorized")
        attempt.mark_admitted("receiver", "admission:unauthorized")
        attempt.record_return(
            "receiver",
            evidence_ref="encounter:unauthorized",
            encounter_id="encounter-id:unauthorized",
            payload_digest="a" * 64,
            canonicalization="canonical-json-v1",
        )
        with self.assertRaisesRegex(MinimaxPolicyExecutionError, "required evidence gate"):
            execution.complete_active(
                attempt.score.probe.scenarios[0].outcome,
                actor="interpreter",
                interpretation_ref="interpretation:too-early",
            )
        self.assertEqual(execution.system.fingerprint, initial.fingerprint)
        self.assertEqual(execution.status, "active")

    def test_unmodeled_outcome_is_retained_without_branch_selection_or_ground_change(self):
        initial, _, policy, execution = make_execution()
        attempt = execution.begin_next()
        return_and_authorize(attempt, "mismatch")
        result = execution.complete_active(
            TransitionOutcome("b", (7,)),
            actor="interpreter",
            interpretation_ref="interpretation:mismatch",
        )
        self.assertEqual(result.status, "model_mismatch")
        self.assertFalse(result.scenario_match)
        self.assertEqual(execution.status, "model_mismatch")
        self.assertEqual(execution.system.fingerprint, initial.fingerprint)
        self.assertEqual(execution.history[0]["decision"]["decision_kind"], "model_mismatch")

        receipt = build_decision_receipt(execution.to_dict(), policy.to_dict())
        validate_decision_receipt(receipt)
        self.assertEqual(receipt["decisions"][0]["decision_kind"], "model_mismatch")

    def test_receipt_rejects_event_tampering_even_with_recomputed_outer_digest(self):
        _, _, policy, execution = make_execution()
        attempt = execution.begin_next()
        return_and_authorize(attempt, "tamper")
        execution.complete_active(
            attempt.score.probe.scenarios[0].outcome,
            actor="interpreter",
            interpretation_ref="interpretation:tamper",
        )
        receipt = build_decision_receipt(execution.to_dict(), policy.to_dict())
        corrupted = copy.deepcopy(receipt)
        corrupted["event_log"][1]["event"]["actor"] = "substituted-actor"
        core = {key: value for key, value in corrupted.items() if key != "report_digest"}
        corrupted["report_digest"] = hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode()
        ).hexdigest()
        with self.assertRaises(MinimaxPolicyExecutionError):
            validate_decision_receipt(corrupted)

    def test_policy_digest_tampering_is_rejected(self):
        _, _, policy, execution = make_execution()
        record = policy.to_dict()
        record["root"]["worst_case_cost"] = {"numerator": 99, "denominator": 1}
        with self.assertRaises(MinimaxPolicyExecutionError):
            build_decision_receipt(execution.to_dict(), record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
