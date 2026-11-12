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
from test_proof_action_execution import add_result_payload, ground, make_session
from test_proof_action_protocol import return_evidence


HOST_ID = "proof-host"
WORKER_ID = "proof-worker"


def make_endpoints(transport=None, *, policy=None):
    session, source_trace, _ = make_session()
    proof_ground = ground(source_trace)
    transport = transport or InMemoryTransport()
    host = ProofActionReliableHost(
        session,
        proof_ground,
        transport,
        host_id=HOST_ID,
        worker_id=WORKER_ID,
        policy=policy,
    )
    worker = ProofActionReliableWorker(
        transport,
        host_id=HOST_ID,
        worker_id=WORKER_ID,
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
        self.assertEqual(host.dispatch_next().request["candidate_transition"]["tactic"], "simp")

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
        self.assertEqual(session.attempts[0].events[-2]["stage"], "interpreted")
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
        _dispatched, _received = deliver_request_and_admit(host, worker)
        worker.send_result({"not": "a proof-action result"})
        with self.assertRaisesRegex(ProofActionReliableChannelError, "return_evidence"):
            host.receive_result()

        attempt = session.attempts[0]
        self.assertEqual(attempt.status, "interpretation_failed")
        self.assertEqual(
            [event["stage"] for event in attempt.events][-2:],
            ["returned", "interpretation_failed"],
        )
        self.assertEqual(worker.process_result_acknowledgements(), (1,))

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

    def test_failed_result_import_closes_attempt_without_promoting_wrong_proof_state(self):
        session, source_trace, _pg, _transport, host, worker = make_endpoints()
        dispatched, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        original_ground_fingerprint = host.proof_ground.fingerprint
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
        self.assertEqual(host.proof_ground.fingerprint, original_ground_fingerprint)

if __name__ == "__main__":
    unittest.main(verbosity=2)
