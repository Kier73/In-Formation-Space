from __future__ import annotations

import unittest

from mailcpu.faults import FaultInjectingTransport, FaultProfile
from mailcpu.reliability import ReliabilityPolicy
from mailcpu.transport import InMemoryTransport

from proof_action_protocol import make_proof_action_result
from proof_action_reliable_channel import (
    ProofActionReliableChannelError,
    ProofActionReliableHost,
    ProofActionReliableWorker,
)
from test_proof_action_execution import accepted_root_receipt, add_result_payload, ground, make_session
from test_proof_action_protocol import return_evidence


HOST_ID = "proof-host"
WORKER_ID = "proof-worker"


def make_endpoints(
    transport=None,
    *,
    policy=None,
    request_channel="proof-action-request",
    result_channel="proof-action-result",
    session_override=None,
    proof_ground_override=None,
):
    if session_override is None:
        session, source_trace, _ = make_session()
    else:
        session = session_override
        source_trace = None
    proof_ground = proof_ground_override if proof_ground_override is not None else ground(source_trace)
    transport = transport or InMemoryTransport()
    host = ProofActionReliableHost(
        session,
        proof_ground,
        transport,
        host_id=HOST_ID,
        worker_id=WORKER_ID,
        request_channel=request_channel,
        result_channel=result_channel,
        policy=policy,
    )
    worker = ProofActionReliableWorker(
        transport,
        host_id=HOST_ID,
        worker_id=WORKER_ID,
        request_channel=request_channel,
        result_channel=result_channel,
        policy=policy,
    )
    return session, source_trace, proof_ground, transport, host, worker


def deliver_request_and_admit(host, worker):
    dispatched = host.dispatch_next()
    assert dispatched is not None
    received = worker.receive_request()
    assert received is not None
    assert received.request_sequence == dispatched.request_sequence
    assert received.request == dispatched.request
    assert host.observe_request_admission() is True
    return dispatched, received


def send_result(host, worker, source_trace, received, *, status="elaborated"):
    attempt = host.active_attempt
    updated_trace = add_result_payload(
        source_trace,
        attempt,
        result_status=status,
    )
    result = make_proof_action_result(
        received.request,
        return_evidence=return_evidence(attempt),
        proof_trace=updated_trace,
    )
    return worker.send_result(result)


class ProofActionReliableChannelTests(unittest.TestCase):
    def test_host_worker_roundtrip_imports_result_only_after_transport_ack(self):
        session, source_trace, _pg, _transport, host, worker = make_endpoints()
        dispatched, received = deliver_request_and_admit(host, worker)

        self.assertEqual(host.active_attempt.status, "admitted")
        self.assertEqual(host.active_attempt.attempt_id, dispatched.attempt_id)
        self.assertEqual(received.request["request_digest"], dispatched.request_digest)

        response_sequence = send_result(host, worker, source_trace, received)
        self.assertEqual(response_sequence, 1)
        imported = host.receive_result()

        self.assertIsNotNone(imported)
        self.assertEqual(imported.attempt_id, dispatched.attempt_id)
        self.assertEqual(imported.interpretation["attempt_status"], "elaborated")
        self.assertEqual(host.active_attempt, None)
        self.assertEqual(session.attempts[0].status, "interpreted")
        self.assertEqual(worker.process_result_acknowledgements(), (1,))
        self.assertEqual(worker.pending_result_sequences, ())

        next_dispatched = host.dispatch_next()
        self.assertIsNotNone(next_dispatched)
        self.assertEqual(next_dispatched.request["candidate_transition"]["tactic"], "simp")
        self.assertEqual(session.attempts[0].status, "continued")

    def test_dropped_request_retries_same_attempt_and_then_admits(self):
        transport = FaultInjectingTransport(
            FaultProfile(drop_indices=frozenset({1}))
        )
        _session, _trace, _pg, _transport, host, worker = make_endpoints(
            transport,
            policy=ReliabilityPolicy(lease_ticks=1, max_attempts=3),
        )
        dispatched = host.dispatch_next()
        self.assertEqual(host.active_attempt.status, "dispatched")
        self.assertIsNone(worker.receive_request())
        self.assertFalse(host.observe_request_admission())

        self.assertEqual(host.advance_request_retry_tick(), ())
        received = worker.receive_request()
        self.assertIsNotNone(received)
        self.assertEqual(received.request_sequence, dispatched.request_sequence)
        self.assertEqual(received.request["request_digest"], dispatched.request_digest)
        self.assertTrue(host.observe_request_admission())
        self.assertEqual(host.active_attempt.status, "admitted")

    def test_lost_request_ack_is_recovered_by_duplicate_request_without_redelivery(self):
        # Send order: request=1, first worker ACK=2 (dropped), retry request=3,
        # duplicate worker ACK=4.
        transport = FaultInjectingTransport(
            FaultProfile(drop_indices=frozenset({2}))
        )
        _session, _trace, _pg, _transport, host, worker = make_endpoints(
            transport,
            policy=ReliabilityPolicy(lease_ticks=1, max_attempts=3),
        )
        dispatched = host.dispatch_next()
        first_delivery = worker.receive_request()
        self.assertIsNotNone(first_delivery)
        self.assertEqual(first_delivery.request_sequence, dispatched.request_sequence)
        self.assertFalse(host.observe_request_admission())

        host.advance_request_retry_tick()
        duplicate_delivery = worker.receive_request()
        self.assertIsNone(duplicate_delivery)
        self.assertTrue(host.observe_request_admission())
        self.assertEqual(host.active_attempt.status, "admitted")
        self.assertEqual(host.request_pending_sequences, ())

    def test_retry_exhaustion_is_delivery_unconfirmed_not_execution_rejection(self):
        transport = FaultInjectingTransport(
            FaultProfile(drop_indices=frozenset({1, 2}))
        )
        session, _trace, _pg, _transport, host, worker = make_endpoints(
            transport,
            policy=ReliabilityPolicy(lease_ticks=1, max_attempts=2),
        )
        host.dispatch_next()
        self.assertIsNone(worker.receive_request())
        self.assertEqual(host.advance_request_retry_tick(), ())
        self.assertIsNone(worker.receive_request())
        self.assertEqual(host.advance_request_retry_tick(), (1,))

        failed = session.attempts[0]
        self.assertEqual(failed.status, "delivery_unconfirmed")
        self.assertNotIn("execution_rejected", [event["stage"] for event in failed.events])
        self.assertIsNone(host.active_attempt)
        with self.assertRaisesRegex(ProofActionReliableChannelError, "request channel is fenced"):
            host.dispatch_next()

        # A new pair of endpoints uses a fresh channel epoch; the prior
        # in-order sequence is never reused on the uncertain route.
        _new_session, _new_trace, _new_pg, _same_transport, new_host, new_worker = make_endpoints(
            transport,
            policy=ReliabilityPolicy(lease_ticks=1, max_attempts=2),
            request_channel="proof-action-request-epoch-2",
            result_channel="proof-action-result-epoch-2",
            session_override=session,
            proof_ground_override=host.proof_ground,
        )
        next_dispatch = new_host.dispatch_next()
        self.assertEqual(next_dispatch.request["candidate_transition"]["tactic"], "simp")
        self.assertEqual(new_worker.receive_request().request, next_dispatch.request)
        self.assertTrue(new_host.observe_request_admission())

    def test_result_retry_exhaustion_fences_worker_result_channel(self):
        transport = FaultInjectingTransport(
            FaultProfile(drop_indices=frozenset({3, 4}))
        )
        _session, source_trace, _pg, _transport, host, worker = make_endpoints(
            transport,
            policy=ReliabilityPolicy(lease_ticks=1, max_attempts=2),
        )
        _dispatched, received = deliver_request_and_admit(host, worker)
        result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(host.active_attempt),
            proof_trace=add_result_payload(source_trace, host.active_attempt),
        )
        self.assertEqual(worker.send_result(result), 1)
        self.assertEqual(worker.advance_result_retry_tick(), ())
        self.assertEqual(worker.advance_result_retry_tick(), (1,))
        self.assertEqual(worker.pending_result_sequences, ())

        host.mark_no_result("the worker result sequence exhausted retries")
        self.assertTrue(worker.result_channel_failed)
        self.assertTrue(worker.request_channel_failed)
        self.assertTrue(worker.fenced)
        with self.assertRaisesRegex(ProofActionReliableChannelError, "fenced"):
            worker.receive_request()
        with self.assertRaisesRegex(ProofActionReliableChannelError, "fenced"):
            worker.send_result(result)

        # A new host/worker pair gets fresh reliable sequence spaces and can
        # resume the next unattempted proof candidate.
        _new_session, _new_trace, _new_pg, _same_transport, new_host, new_worker = make_endpoints(
            transport,
            policy=ReliabilityPolicy(lease_ticks=1, max_attempts=2),
            request_channel="proof-action-request-epoch-2",
            result_channel="proof-action-result-epoch-2",
            session_override=_session,
            proof_ground_override=host.proof_ground,
        )
        next_dispatch = new_host.dispatch_next()
        self.assertEqual(next_dispatch.request["candidate_transition"]["tactic"], "simp")
        next_request = new_worker.receive_request()
        self.assertIsNotNone(next_request)
        self.assertTrue(new_host.observe_request_admission())

    def test_dropped_result_retries_and_imports_once(self):
        # Send order: request=1, request ACK=2, first result=3 (dropped),
        # result retry=4, host ACK=5.
        transport = FaultInjectingTransport(
            FaultProfile(drop_indices=frozenset({3}))
        )
        _session, source_trace, _pg, _transport, host, worker = make_endpoints(
            transport,
            policy=ReliabilityPolicy(lease_ticks=1, max_attempts=3),
        )
        _dispatched, received = deliver_request_and_admit(host, worker)
        worker.send_result(make_proof_action_result(
            received.request,
            return_evidence=return_evidence(host.active_attempt),
            proof_trace=add_result_payload(source_trace, host.active_attempt),
        ))
        self.assertIsNone(host.receive_result())
        self.assertEqual(worker.advance_result_retry_tick(), ())
        imported = host.receive_result()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.interpretation["attempt_status"], "elaborated")
        self.assertEqual(worker.process_result_acknowledgements(), (1,))
        self.assertEqual(worker.pending_result_sequences, ())

    def test_duplicate_request_and_result_frames_do_not_repeat_interpretation(self):
        # Request is duplicated by send 1; ACKs are sends 2/3; result is
        # duplicated by send 4; host response ACKs are sends 5/6.
        transport = FaultInjectingTransport(
            FaultProfile(duplicate_indices=frozenset({1, 4}))
        )
        session, source_trace, _pg, _transport, host, worker = make_endpoints(transport)
        dispatched = host.dispatch_next()
        first_request = worker.receive_request()
        self.assertIsNotNone(first_request)
        self.assertEqual(first_request.request_sequence, dispatched.request_sequence)
        self.assertIsNone(worker.receive_request())
        self.assertTrue(host.observe_request_admission())

        send_result(host, worker, source_trace, first_request)
        imported = host.receive_result()
        self.assertIsNotNone(imported)
        self.assertEqual(session.attempts[0].events[-1]["stage"], "interpreted")
        self.assertIsNone(host.receive_result())  # Duplicate old sequence is only ACKed.
        self.assertEqual(worker.process_result_acknowledgements(), (1,))
        self.assertEqual(worker.pending_result_sequences, ())
        self.assertEqual(
            [event["stage"] for event in session.attempts[0].events].count("interpreted"),
            1,
        )

    def test_no_result_requires_admitted_request_and_is_not_a_negative_tactic_reading(self):
        session, _trace, _pg, _transport, host, worker = make_endpoints()
        host.dispatch_next()
        with self.assertRaisesRegex(ProofActionReliableChannelError, "requires an admitted"):
            host.mark_no_result("deadline exceeded before worker ACK")
        worker.receive_request()
        self.assertTrue(host.observe_request_admission())
        host.mark_no_result("worker did not return a result before the deadline")

        attempt = session.attempts[0]
        self.assertEqual(attempt.status, "no_result")
        self.assertNotIn("interpreted", [event["stage"] for event in attempt.events])
        next_action = host.dispatch_next()
        self.assertIsNotNone(next_action)
        self.assertEqual(next_action.request["candidate_transition"]["tactic"], "simp")

    def test_malformed_result_is_retained_as_raw_return_then_interpretation_failed(self):
        session, _trace, _pg, _transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)
        worker.send_result({
            "attempt_id": received.request["attempt_id"],
            "request_digest": received.request["request_digest"],
            "malformed": "no return_evidence or proof trace",
        })
        with self.assertRaisesRegex(ProofActionReliableChannelError, "return_evidence"):
            host.receive_result()

        attempt = session.attempts[0]
        self.assertEqual(attempt.status, "interpretation_failed")
        self.assertEqual(
            [event["stage"] for event in attempt.events][-2:],
            ["returned", "interpretation_failed"],
        )
        self.assertEqual(worker.process_result_acknowledgements(), (1,))

    def test_late_result_after_no_result_is_acknowledged_and_quarantined(self):
        session, source_trace, _pg, _transport, host, worker = make_endpoints()
        _dispatch, received = deliver_request_and_admit(host, worker)
        late_attempt = host.active_attempt
        host.mark_no_result("host deadline elapsed")

        late_result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(late_attempt),
            proof_trace=add_result_payload(source_trace, late_attempt, result_status="timeout"),
        )
        worker.send_result(late_result)
        self.assertIsNone(host.receive_result())
        self.assertEqual(late_attempt.status, "no_result")
        self.assertEqual(len(host.quarantined_results), 1)
        self.assertEqual(host.quarantined_results[0]["attempt_id"], late_attempt.attempt_id)
        self.assertEqual(host.quarantined_results[0]["payload"], late_result)
        self.assertEqual(host.quarantined_results[0]["canonicalization"], "canonical-json-v1")
        self.assertIn("closed", host.quarantined_results[0]["reason"])
        self.assertEqual(worker.process_result_acknowledgements(), (1,))

        next_dispatch = host.dispatch_next()
        self.assertIsNotNone(next_dispatch)
        self.assertEqual(next_dispatch.request["candidate_transition"]["tactic"], "simp")

    def test_late_result_for_prior_action_cannot_poison_a_new_active_attempt(self):
        session, source_trace, _pg, _transport, host, worker = make_endpoints()
        first_dispatch, first_request = deliver_request_and_admit(host, worker)
        first_attempt = host.active_attempt
        host.mark_no_result("first worker action exceeded the deadline")

        second_dispatch = host.dispatch_next()
        second_request = worker.receive_request()
        self.assertIsNotNone(second_request)
        self.assertEqual(second_request.request_sequence, second_dispatch.request_sequence)
        self.assertTrue(host.observe_request_admission())
        second_attempt = host.active_attempt
        self.assertEqual(second_attempt.status, "admitted")

        # The worker's delayed first response arrives while attempt two is active.
        first_late_result = make_proof_action_result(
            first_request.request,
            return_evidence=return_evidence(first_attempt),
            proof_trace=add_result_payload(source_trace, first_attempt, result_status="timeout"),
        )
        worker.send_result(first_late_result)
        self.assertIsNone(host.receive_result())
        self.assertEqual(second_attempt.status, "admitted")
        self.assertEqual(first_attempt.status, "no_result")
        self.assertEqual(len(host.quarantined_results), 1)
        self.assertEqual(host.quarantined_results[0]["attempt_id"], first_dispatch.attempt_id)
        self.assertEqual(host.quarantined_results[0]["payload"], first_late_result)
        self.assertEqual(worker.process_result_acknowledgements(), (1,))

        worker.send_result(make_proof_action_result(
            second_request.request,
            return_evidence=return_evidence(second_attempt),
            proof_trace=add_result_payload(source_trace, second_attempt, result_status="elaborated"),
        ))
        imported = host.receive_result()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.attempt_id, second_dispatch.attempt_id)
        self.assertEqual(second_attempt.status, "interpreted")
        self.assertEqual(worker.process_result_acknowledgements(), (2,))

    def test_worker_does_not_acknowledge_an_invalid_request_before_validation(self):
        # Construct a raw ReliableChannel sender to bypass the host request builder.
        from mailcpu.reliability import ReliableChannel

        transport = InMemoryTransport()
        worker = ProofActionReliableWorker(
            transport,
            host_id=HOST_ID,
            worker_id=WORKER_ID,
        )
        sender = ReliableChannel(
            transport,
            source=HOST_ID,
            destination=WORKER_ID,
            channel="proof-action-request",
        )
        sender.send({"format": "not-a-proof-request"})
        with self.assertRaisesRegex(ProofActionReliableChannelError, "request is invalid"):
            worker.receive_request()
        self.assertEqual(sender.pending_sequences(), (1,))
        self.assertTrue(worker.request_channel_failed)
        with self.assertRaisesRegex(ProofActionReliableChannelError, "worker endpoint is fenced"):
            worker.receive_request()

    def test_worker_acknowledges_same_attempt_replayed_on_a_new_reliable_sequence_once(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)

        # Simulate a host replay bug using a fresh reliable sequence but the
        # exact same application-level request and attempt ID.
        replay_sequence = host._request_sender.send(received.request)
        self.assertEqual(replay_sequence, 2)
        self.assertIsNone(worker.receive_request())
        self.assertEqual(host._request_sender.process_ack(), (2,))
        self.assertEqual(
            worker._admitted_requests[received.request["attempt_id"]],
            received.request["request_digest"],
        )

    def test_worker_rejects_conflicting_request_digest_for_an_already_admitted_attempt(self):
        import copy
        import hashlib
        import json

        from mailcpu.reliability import ReliableChannel
        from proof_action_protocol import build_proof_action_request

        session, source_trace, _ = make_session()
        proof_ground = ground(source_trace)
        attempt = session.begin_next()
        request = build_proof_action_request(session, proof_ground)
        transport = InMemoryTransport()
        worker = ProofActionReliableWorker(
            transport,
            host_id=HOST_ID,
            worker_id=WORKER_ID,
        )
        sender = ReliableChannel(
            transport,
            source=HOST_ID,
            destination=WORKER_ID,
            channel="proof-action-request",
        )
        sender.send(request)
        self.assertIsNotNone(worker.receive_request())
        self.assertEqual(sender.process_ack(), (1,))

        conflicting = copy.deepcopy(request)
        conflicting["candidate_transition"]["tactic"] = "forged-tactic"
        core = {key: value for key, value in conflicting.items() if key != "request_digest"}
        conflicting["request_digest"] = hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        sender.send(conflicting)
        with self.assertRaisesRegex(
            ProofActionReliableChannelError, "conflicting request digests"
        ):
            worker.receive_request()
        self.assertEqual(sender.pending_sequences(), (2,))
        self.assertEqual(attempt.status, "planned")
        self.assertTrue(worker.request_channel_failed)
        with self.assertRaisesRegex(ProofActionReliableChannelError, "worker endpoint is fenced"):
            worker.receive_request()

    def test_transport_result_can_supply_verified_kernel_receipt_for_root_completion(self):
        session, source_trace, _pg, _transport, host, worker = make_endpoints()
        dispatched, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        updated_trace = add_result_payload(source_trace, attempt)
        updated_ground = ground(updated_trace)
        kernel_receipt = accepted_root_receipt(updated_ground)

        result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=updated_trace,
        )
        worker.send_result(result)
        imported = host.receive_result(verified_receipts=(kernel_receipt,))

        self.assertIsNotNone(imported)
        self.assertEqual(imported.attempt_id, dispatched.attempt_id)
        self.assertEqual(
            imported.proof_ground.kernel_status(attempt.action["source_obligation_id"]),
            "kernel_accepted",
        )
        self.assertEqual(attempt.status, "interpreted")
        self.assertIsNone(host.dispatch_next())
        self.assertEqual(session.status, "complete")
        self.assertEqual(attempt.status, "query_determined")
        self.assertEqual(
            [event["stage"] for event in attempt.events][-2:],
            ["interpreted", "query_determined"],
        )
        self.assertEqual(worker.process_result_acknowledgements(), (1,))

    def test_failed_result_import_closes_attempt_without_promoting_wrong_proof_state(self):
        session, source_trace, _pg, _transport, host, worker = make_endpoints()
        dispatched, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        original_ground_digest = session.plan["proof_ground_digest"]
        bad_trace = add_result_payload(
            source_trace,
            attempt,
            evidence_ref="some-other-attempt",
        )
        result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=bad_trace,
        )
        worker.send_result(result)
        with self.assertRaisesRegex(ProofActionReliableChannelError, "does not match the active action"):
            host.receive_result()
        self.assertEqual(session.attempts[0].status, "interpretation_failed")
        self.assertEqual(session.plan["proof_ground_digest"], original_ground_digest)

    def test_unidentifiable_response_is_quarantined_without_closing_active_attempt(self):
        session, _source_trace, _pg, _transport, host, worker = make_endpoints()
        _dispatch, _received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        # Exercise a malformed raw frame below the worker's public result-envelope API.
        worker._result_sender.send(["not", "a", "JSON proof-action result"])

        self.assertIsNone(host.receive_result())
        self.assertEqual(attempt.status, "admitted")
        self.assertEqual(len(host.quarantined_results), 1)
        self.assertIsNone(host.quarantined_results[0]["attempt_id"])
        self.assertIn("not a correlated", host.quarantined_results[0]["reason"])
        self.assertEqual(worker.process_result_acknowledgements(), (1,))

if __name__ == "__main__":
    unittest.main(verbosity=2)
