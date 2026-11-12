from __future__ import annotations

import copy
import hashlib
import unittest

from proof_action_execution import (
    ProofActionExecutionError,
    ProofAttentionSession,
)
from vgi.proof import ProofGroundAdapter, VerifiedKernelReceipt


ENV = {
    "assistant": "Lean",
    "assistant_version": "4.15.0",
    "environment_fingerprint": "env-sha256",
    "imports_fingerprint": "imports-sha256",
    "options_fingerprint": "options-sha256",
}


def trace(*, environment=None, transitions=None, extra_obligations=()):
    return {
        "format": "VGI-LeanProofTrace-1",
        "environment": environment or ENV,
        "obligations": [
            {"key": "root", "goal": {"kind": "root", "type": "Nat"}},
            {"key": "child", "goal": {"kind": "child", "type": "Nat"}},
            *list(extra_obligations),
        ],
        "transitions": transitions if transitions is not None else [
            {
                "source": "root",
                "tactic": "induction",
                "subgoals": ["child"],
                "attempt_status": "candidate",
                "evidence_ref": "candidate:induction",
            },
            {
                "source": "root",
                "tactic": "simp",
                "subgoals": [],
                "attempt_status": "candidate",
                "evidence_ref": "candidate:simp",
            },
        ],
    }


def ground(payload, receipts=()):
    return ProofGroundAdapter.from_lean_trace(payload, verified_receipts=receipts)


def accepted_root_receipt(proof_ground):
    root_id = next(
        item.fingerprint
        for item in proof_ground.obligations
        if item.goal.get("kind") == "root"
    )
    return VerifiedKernelReceipt(
        root_id,
        "proof-term-sha256",
        ENV["environment_fingerprint"],
        "Lean.kernel",
        "4.15.0",
        "accepted",
        "kernel-receipt:root",
    )


def make_session(*, transitions=None, receipts=()):
    payload = trace(transitions=transitions)
    proof_ground = ground(payload, receipts)
    root_id = next(
        item.fingerprint
        for item in proof_ground.obligations
        if item.goal.get("kind") == "root"
    )
    session = ProofAttentionSession(
        proof_ground,
        (root_id,),
        attempt_id_prefix="proof-run",
        query_label="establish the root theorem",
    )
    return session, payload, root_id


def add_result(payload, attempt, *, result_status="elaborated", evidence_ref=None, include_receipt=False):
    updated = copy.deepcopy(payload)
    updated["transitions"].append({
        "source": "root",
        "tactic": attempt.action["tactic"],
        "subgoals": ["child"] if result_status == "elaborated" else [],
        "attempt_status": result_status,
        "evidence_ref": evidence_ref or attempt.attempt_id,
    })
    provisional = ground(updated)
    receipts = (accepted_root_receipt(provisional),) if include_receipt else ()
    return ground(updated, receipts)


def execute_to_return(attempt, *, actor_prefix="worker"):
    attempt.mark_dispatched(f"{actor_prefix}-sender", f"dispatch://{attempt.attempt_id}")
    attempt.mark_admitted(f"{actor_prefix}-receiver", f"admission://{attempt.attempt_id}")
    attempt.record_return(
        f"{actor_prefix}-receiver",
        evidence_ref=f"encounter://{attempt.attempt_id}",
        encounter_id=f"encounter-{attempt.attempt_id}",
        payload_digest=hashlib.sha256(attempt.attempt_id.encode()).hexdigest(),
        canonicalization="canonical-json-v1",
    )


class ProofActionExecutionTests(unittest.TestCase):
    def test_one_action_runs_through_gates_and_root_receipt_completes_session(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.status, "planned")
        with self.assertRaisesRegex(ProofActionExecutionError, "already active"):
            session.begin_next()

        execute_to_return(attempt)
        updated = add_result(payload, attempt, include_receipt=True)
        result = session.interpret_result(
            updated,
            actor="proof-trace-adapter",
            interpretation_ref=f"interpretation://{attempt.attempt_id}",
        )
        self.assertEqual(result["attempt_status"], "elaborated")
        self.assertEqual(attempt.status, "interpreted")

        self.assertIsNone(session.begin_next())
        self.assertEqual(session.status, "complete")
        self.assertEqual(attempt.status, "query_determined")
        self.assertEqual(
            [event["stage"] for event in attempt.events],
            ["planned", "dispatched", "admitted", "returned", "interpreted", "query_determined"],
        )

    def test_refreshed_ground_expands_elaborated_bundle_then_links_next_candidate(self):
        session, payload, _ = make_session()
        first = session.begin_next()
        self.assertEqual(first.action["tactic"], "induction")
        execute_to_return(first)
        updated = add_result(payload, first, result_status="elaborated")
        session.interpret_result(
            updated,
            actor="proof-trace-adapter",
            interpretation_ref=f"interpretation://{first.attempt_id}",
        )

        second = session.begin_next()
        self.assertEqual(second.action["tactic"], "simp")
        self.assertEqual(first.status, "continued")
        self.assertEqual(first.events[-1]["details"]["next_attempt_id"], second.attempt_id)
        self.assertEqual(second.action["source_obligation_id"], first.action["source_obligation_id"])

    def test_timeout_is_an_observed_result_not_a_tactic_failure_inferred_from_no_result(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        updated = add_result(payload, attempt, result_status="timeout")
        result = session.interpret_result(
            updated,
            actor="proof-trace-adapter",
            interpretation_ref=f"interpretation://{attempt.attempt_id}",
        )
        self.assertEqual(result["attempt_status"], "timeout")
        self.assertEqual(attempt.status, "interpreted")
        next_attempt = session.begin_next()
        self.assertEqual(next_attempt.action["tactic"], "simp")
        self.assertEqual(attempt.status, "continued")

    def test_rejected_attempt_is_recorded_and_does_not_close_root_as_unprovable(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        updated = add_result(payload, attempt, result_status="rejected")
        session.interpret_result(
            updated,
            actor="proof-trace-adapter",
            interpretation_ref=f"interpretation://{attempt.attempt_id}",
        )
        next_attempt = session.begin_next()
        self.assertEqual(next_attempt.action["tactic"], "simp")
        self.assertEqual(attempt.status, "continued")
        self.assertNotEqual(session.status, "complete")

    def test_unadmitted_return_is_terminal_and_never_interpreted(self):
        session, _, _ = make_session()
        attempt = session.begin_next()
        attempt.mark_dispatched("sender", "dispatch://1")
        attempt.record_unadmitted_return(
            "receiver",
            evidence_ref="encounter://unadmitted",
            encounter_id="encounter-unadmitted",
            payload_digest="a" * 64,
            canonicalization="canonical-json-v1",
        )
        self.assertEqual(attempt.status, "returned_unadmitted")
        with self.assertRaisesRegex(ProofActionExecutionError, "after return"):
            session.interpret_result(
                ground(trace()),
                actor="adapter",
                interpretation_ref="interpretation://invalid",
            )
        next_attempt = session.begin_next()
        self.assertEqual(next_attempt.action["tactic"], "simp")

    def test_dispatch_failure_skips_that_candidate_without_fabricating_a_result(self):
        session, _, _ = make_session()
        attempt = session.begin_next()
        attempt.mark_failure("dispatch_failed", "sender", "worker route unavailable")
        self.assertEqual(attempt.status, "dispatch_failed")
        next_attempt = session.begin_next()
        self.assertEqual(next_attempt.action["tactic"], "simp")
        self.assertNotIn("interpreted", [event["stage"] for event in attempt.events])

    def test_execution_cannot_skip_dispatch_admission_or_return_gates(self):
        session, _, _ = make_session()
        attempt = session.begin_next()
        with self.assertRaisesRegex(ProofActionExecutionError, "planned"):
            attempt.mark_admitted("receiver", "admission://early")
        attempt.mark_dispatched("sender", "dispatch://ok")
        with self.assertRaisesRegex(ProofActionExecutionError, "dispatched"):
            attempt.record_return(
                "receiver",
                evidence_ref="encounter://early",
                encounter_id="early",
                payload_digest="b" * 64,
                canonicalization="canonical-json-v1",
            )

    def test_refreshed_ground_must_correlate_exact_attempt_id(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        updated = add_result(payload, attempt, evidence_ref="attempt-from-another-session")
        with self.assertRaisesRegex(ProofActionExecutionError, "exactly one result edge"):
            session.interpret_result(
                updated,
                actor="adapter",
                interpretation_ref="interpretation://bad-correlation",
            )
        self.assertEqual(attempt.status, "returned")

    def test_duplicate_correlated_result_edges_are_rejected(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        updated = add_result(payload, attempt)
        duplicate = copy.deepcopy(updated["transitions"][-1])
        updated["transitions"].append(duplicate)
        with self.assertRaisesRegex(ProofActionExecutionError, "exactly one result edge"):
            session.interpret_result(
                ground(updated),
                actor="adapter",
                interpretation_ref="interpretation://duplicate",
            )

    def test_refreshed_ground_must_preserve_environment_and_prior_obligations(self):
        session, payload, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        changed_environment = copy.deepcopy(payload)
        changed_environment["environment"]["imports_fingerprint"] = "other-imports"
        changed_environment["transitions"].append({
            "source": "root", "tactic": attempt.action["tactic"], "subgoals": [],
            "attempt_status": "elaborated", "evidence_ref": attempt.attempt_id,
        })
        with self.assertRaisesRegex(ProofActionExecutionError, "environment fingerprint"):
            session.interpret_result(
                ground(changed_environment),
                actor="adapter",
                interpretation_ref="interpretation://changed-environment",
            )

        missing_prior = {
            "format": "VGI-LeanProofTrace-1",
            "environment": ENV,
            "obligations": [{"key": "root", "goal": {"kind": "root", "type": "Nat"}}],
            "transitions": [{
                "source": "root", "tactic": attempt.action["tactic"], "subgoals": [],
                "attempt_status": "elaborated", "evidence_ref": attempt.attempt_id,
            }],
        }
        with self.assertRaisesRegex(ProofActionExecutionError, "discarded prior"):
            session.interpret_result(
                ground(missing_prior),
                actor="adapter",
                interpretation_ref="interpretation://dropped-obligation",
            )

    def test_interpretation_failure_is_terminal_and_next_action_remains_available(self):
        session, _, _ = make_session()
        attempt = session.begin_next()
        execute_to_return(attempt)
        attempt.mark_failure(
            "interpretation_failed",
            "trace-adapter",
            "proof trace could not be decoded",
            evidence_ref="interpretation-error://1",
        )
        next_attempt = session.begin_next()
        self.assertEqual(next_attempt.action["tactic"], "simp")
        self.assertEqual(attempt.status, "interpretation_failed")

    def test_frontier_exhaustion_is_unresolved_not_a_proof_of_impossibility(self):
        one = [{
            "source": "root", "tactic": "induction", "subgoals": ["child"],
            "attempt_status": "candidate", "evidence_ref": "candidate:only",
        }]
        session, payload, _ = make_session(transitions=one)
        attempt = session.begin_next()
        execute_to_return(attempt)
        updated = add_result(payload, attempt, result_status="timeout")
        session.interpret_result(
            updated,
            actor="adapter",
            interpretation_ref="interpretation://timeout",
        )
        self.assertIsNone(session.begin_next())
        self.assertEqual(session.status, "exhausted")
        self.assertEqual(attempt.status, "unresolved")
        self.assertIn("no unattempted candidate", attempt.events[-1]["details"]["reason"])
        self.assertIsNone(session.plan["interpretation"]["success_probability"])

    def test_all_roots_must_have_verified_receipts_to_complete(self):
        session, payload, _ = make_session()
        # Add a second root intention, which has no candidate action.
        payload["obligations"].append({
            "key": "second-root", "goal": {"kind": "second-root", "type": "Nat"}
        })
        payload["transitions"].append({
            "source": "second-root", "tactic": "rfl", "subgoals": [],
            "attempt_status": "candidate", "evidence_ref": "candidate:second",
        })
        pg = ground(payload)
        root_ids = {item.goal.get("kind"): item.fingerprint for item in pg.obligations}
        session = ProofAttentionSession(
            pg,
            (root_ids["root"], root_ids["second-root"]),
            attempt_id_prefix="multi-root",
            query_label="establish both theorems",
        )
        self.assertIsNotNone(session.begin_next())
        self.assertNotEqual(session.status, "complete")

    def test_empty_candidate_frontier_is_not_complete_without_root_receipts(self):
        transitions = [{
            "source": "root", "tactic": "simp", "subgoals": [],
            "attempt_status": "timeout", "evidence_ref": "timeout:prior",
        }]
        session, _, _ = make_session(transitions=transitions)
        self.assertIsNone(session.begin_next())
        self.assertEqual(session.status, "exhausted")

    def test_session_and_attempt_digests_are_deterministic(self):
        session, _, _ = make_session()
        attempt = session.begin_next()
        first = session.to_dict()
        second = session.to_dict()
        self.assertEqual(first, second)
        self.assertEqual(len(first["session_digest"]), 64)
        self.assertEqual(len(attempt.to_dict()["attempt_digest"]), 64)
        self.assertEqual(attempt.events[0]["previous_event_digest"], "0" * 64)
        for prior, following in zip(attempt.events, attempt.events[1:]):
            self.assertEqual(following["previous_event_digest"], prior["event_digest"])

    def test_json_roundtrip_contains_no_runtime_objects(self):
        session, _, _ = make_session()
        attempt = session.begin_next()
        encoded = session.to_json()
        self.assertIn(attempt.attempt_id, encoded)
        self.assertIn("candidate_actions", encoded)
        self.assertNotIn("ProofGroundAdapter", encoded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
