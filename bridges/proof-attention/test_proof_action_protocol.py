from __future__ import annotations

import copy
import hashlib
import json
import unittest

from proof_action_protocol import (
    ProofActionProtocolError,
    build_proof_action_request,
    import_proof_action_result,
    make_proof_action_result,
    validate_proof_action_request,
)
from test_proof_action_execution import (
    ENV,
    accepted_root_receipt,
    add_result_payload,
    execute_to_return,
    ground,
    make_session,
    trace,
)


def return_evidence(attempt):
    return {
        "evidence_ref": f"encounter://{attempt.attempt_id}",
        "encounter_id": f"encounter-{attempt.attempt_id}",
        "payload_digest": hashlib.sha256(attempt.attempt_id.encode()).hexdigest(),
        "canonicalization": "canonical-json-v1",
    }


def result_for(request, attempt, *, result_status="elaborated", evidence=None, evidence_ref=None, environment=None):
    payload = add_result_payload(
        trace(environment=environment),
        attempt,
        result_status=result_status,
        evidence_ref=evidence_ref,
    )
    return make_proof_action_result(
        request,
        return_evidence=evidence or return_evidence(attempt),
        proof_trace=payload,
    )


class ProofActionProtocolTests(unittest.TestCase):
    def test_request_contains_full_scoped_obligation_and_selected_and_or_action(self):
        session, payload, root_id = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        validated = validate_proof_action_request(request)

        obligation = proof_ground.obligation(root_id)
        self.assertEqual(request["attempt_id"], attempt.attempt_id)
        self.assertEqual(request["source_obligation"], obligation.to_dict())
        self.assertEqual(request["candidate_transition"]["source_id"], root_id)
        self.assertEqual(request["candidate_transition"]["tactic"], attempt.action["tactic"])
        self.assertEqual(
            request["candidate_transition"]["proposed_subgoal_ids"],
            [item["obligation_id"] for item in attempt.action["and_bundle"]],
        )
        self.assertEqual(request["execution_contract"]["result_evidence_ref"], attempt.attempt_id)
        self.assertEqual(validated, request)
        self.assertEqual(session.active_attempt.status, "planned")

    def test_request_is_bound_to_the_exact_plan_and_proof_ground(self):
        session, payload, _ = make_session()
        session.begin_next()
        request = build_proof_action_request(session, ground(payload))
        changed_payload = copy.deepcopy(payload)
        changed_payload["transitions"].append({
            "source": "root", "tactic": "rfl", "subgoals": [],
            "attempt_status": "candidate", "evidence_ref": "candidate:rfl",
        })
        with self.assertRaisesRegex(ProofActionProtocolError, "differs from the active plan"):
            build_proof_action_request(session, ground(changed_payload))

        corrupted = dict(request)
        corrupted["tactic"] = "forged"
        with self.assertRaisesRegex(ProofActionProtocolError, "fields are invalid|digest mismatch"):
            validate_proof_action_request(corrupted)

    def test_result_import_correlates_request_return_and_kernel_receipt(self):
        session, payload, _ = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        execute_to_return(attempt)
        updated_payload = add_result_payload(payload, attempt, result_status="elaborated")
        provisional_ground = ground(updated_payload)
        receipt = accepted_root_receipt(provisional_ground)
        result = make_proof_action_result(
            request,
            return_evidence=return_evidence(attempt),
            proof_trace=updated_payload,
        )

        imported = import_proof_action_result(
            session,
            proof_ground,
            request,
            result,
            actor="lean-trace-adapter",
            interpretation_ref=f"interpretation://{attempt.attempt_id}",
            verified_receipts=(receipt,),
        )
        self.assertEqual(imported.attempt_id, attempt.attempt_id)
        self.assertEqual(imported.request_digest, request["request_digest"])
        self.assertEqual(imported.interpretation["attempt_status"], "elaborated")
        self.assertEqual(imported.proof_ground.kernel_status(
            next(item.fingerprint for item in imported.proof_ground.obligations if item.goal.get("kind") == "root")
        ), "kernel_accepted")
        self.assertEqual(attempt.status, "interpreted")
        self.assertIsNone(session.begin_next())
        self.assertEqual(session.status, "complete")
        self.assertEqual(attempt.status, "query_determined")

    def test_request_digest_mismatch_is_rejected_even_with_rehashed_result(self):
        session, payload, _ = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        execute_to_return(attempt)
        result = result_for(request, attempt)
        result["request_digest"] = "a" * 64
        core = {key: value for key, value in result.items() if key != "result_digest"}
        result["result_digest"] = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()

        with self.assertRaisesRegex(ProofActionProtocolError, "request_digest does not match"):
            import_proof_action_result(
                session, proof_ground, request, result,
                actor="adapter", interpretation_ref="interpretation://bad-request",
            )
        self.assertEqual(attempt.status, "returned")

    def test_return_encounter_reference_must_match_the_recorded_admitted_return(self):
        session, payload, _ = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        execute_to_return(attempt)
        evidence = return_evidence(attempt)
        evidence["payload_digest"] = "b" * 64
        result = result_for(request, attempt, evidence=evidence)

        with self.assertRaisesRegex(ProofActionProtocolError, "does not match the active attempt"):
            import_proof_action_result(
                session, proof_ground, request, result,
                actor="adapter", interpretation_ref="interpretation://bad-return",
            )
        self.assertEqual(attempt.status, "returned")

    def test_trace_result_must_bind_to_exact_attempt_id(self):
        session, payload, _ = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        execute_to_return(attempt)
        result = result_for(
            request,
            attempt,
            evidence_ref="attempt-from-another-worker",
        )

        with self.assertRaisesRegex(ProofActionProtocolError, "does not match the active action"):
            import_proof_action_result(
                session, proof_ground, request, result,
                actor="adapter", interpretation_ref="interpretation://wrong-edge",
            )
        self.assertEqual(attempt.status, "returned")

    def test_trace_environment_must_match_the_request_environment(self):
        session, payload, _ = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        execute_to_return(attempt)
        changed_environment = dict(ENV)
        changed_environment["imports_fingerprint"] = "different-import-set"
        result = result_for(
            request,
            attempt,
            environment=changed_environment,
        )

        with self.assertRaisesRegex(ProofActionProtocolError, "does not match the active action"):
            import_proof_action_result(
                session, proof_ground, request, result,
                actor="adapter", interpretation_ref="interpretation://changed-environment",
            )
        self.assertEqual(attempt.status, "returned")

    def test_timeout_result_is_imported_as_an_observation_not_a_success(self):
        session, payload, _ = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        execute_to_return(attempt)
        result = result_for(request, attempt, result_status="timeout")

        imported = import_proof_action_result(
            session,
            proof_ground,
            request,
            result,
            actor="lean-trace-adapter",
            interpretation_ref=f"interpretation://{attempt.attempt_id}",
        )
        self.assertEqual(imported.interpretation["attempt_status"], "timeout")
        self.assertEqual(attempt.status, "interpreted")
        self.assertEqual(session.status, "active")

    def test_request_requires_an_active_attempt(self):
        session, payload, _ = make_session()
        with self.assertRaisesRegex(ProofActionProtocolError, "no active"):
            build_proof_action_request(session, ground(payload))

    def test_result_digest_tampering_is_rejected_before_trace_import(self):
        session, payload, _ = make_session()
        proof_ground = ground(payload)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        execute_to_return(attempt)
        result = result_for(request, attempt)
        result["proof_trace"]["kernel_claims"] = ["root"]
        with self.assertRaisesRegex(ProofActionProtocolError, "result digest mismatch"):
            import_proof_action_result(
                session, proof_ground, request, result,
                actor="adapter", interpretation_ref="interpretation://tampered",
            )
        self.assertEqual(attempt.status, "returned")


if __name__ == "__main__":
    unittest.main(verbosity=2)
