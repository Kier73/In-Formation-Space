from __future__ import annotations

import copy
import unittest

from mailcpu.transport import InMemoryTransport

from proof_action_protocol import make_proof_action_result
from proof_action_checkpoint import (
    ProofActionCheckpointError,
    export_proof_action_checkpoint,
    restore_proof_action_checkpoint,
)
from proof_action_reliable_channel import ProofActionReliableChannelError
from test_proof_action_execution import add_result_payload, make_session
from test_proof_action_protocol import return_evidence
from test_proof_action_reliable_channel import deliver_request_and_admit, make_endpoints


def restore_pair(checkpoint, proof_ground):
    return restore_proof_action_checkpoint(
        checkpoint,
        proof_ground,
        restore_transport=InMemoryTransport.from_snapshot,
    )


class ProofActionCheckpointTests(unittest.TestCase):
    def test_restore_dispatched_request_and_continue_delivery(self):
        session, _trace, proof_ground, _transport, host, worker = make_endpoints()
        dispatched = host.dispatch_next()

        checkpoint = export_proof_action_checkpoint(host, worker)
        transport2, host2, worker2 = restore_pair(checkpoint, proof_ground)

        self.assertIsInstance(transport2, InMemoryTransport)
        received = worker2.receive_request()
        self.assertIsNotNone(received)
        self.assertEqual(received.request_sequence, dispatched.request_sequence)
        self.assertEqual(received.request, dispatched.request)
        self.assertTrue(host2.observe_request_admission())
        self.assertEqual(host2.active_attempt.status, "admitted")
        self.assertEqual(session.to_dict(), host2.session.to_dict())

    def test_restore_after_worker_admission_before_host_ack_is_idempotent(self):
        _session, _trace, proof_ground, _transport, host, worker = make_endpoints()
        dispatched = host.dispatch_next()
        first = worker.receive_request()
        self.assertIsNotNone(first)
        self.assertEqual(first.request_sequence, dispatched.request_sequence)

        # Worker admission and ACK are committed; the host has not consumed ACK.
        self.assertFalse(host.observe_request_admission())
        checkpoint = export_proof_action_checkpoint(host, worker)
        _transport2, host2, worker2 = restore_pair(checkpoint, proof_ground)

        self.assertIsNone(worker2.receive_request())
        self.assertEqual(
            worker2._admitted_requests[dispatched.attempt_id],
            dispatched.request_digest,
        )
        self.assertTrue(host2.observe_request_admission())
        self.assertEqual(host2.active_attempt.status, "admitted")

    def test_restore_inflight_result_then_interpret_once_and_ack(self):
        _session, source_trace, proof_ground, _transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=add_result_payload(source_trace, attempt),
        )
        worker.send_result(result)

        checkpoint = export_proof_action_checkpoint(host, worker)
        _transport2, host2, worker2 = restore_pair(checkpoint, proof_ground)
        imported = host2.receive_result()

        self.assertIsNotNone(imported)
        self.assertEqual(imported.attempt_id, attempt.attempt_id)
        self.assertEqual(host2.session.attempts[0].status, "interpreted")
        self.assertEqual(worker2.process_result_acknowledgements(), (1,))
        self.assertEqual(worker2.pending_result_sequences, ())
        self.assertIsNone(host2.receive_result())
        self.assertEqual(
            [event["stage"] for event in host2.session.attempts[0].events].count("interpreted"),
            1,
        )

    def test_restore_after_interpretation_preserves_unconsumed_result_ack(self):
        _session, source_trace, proof_ground, _transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        worker.send_result(make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=add_result_payload(source_trace, attempt),
        ))
        self.assertIsNotNone(host.receive_result())
        self.assertEqual(worker.pending_result_sequences, (1,))

        # The result has been interpreted; the ACK is in the transport mailbox,
        # while the worker's sender still retains its pending sequence.
        checkpoint = export_proof_action_checkpoint(host, worker)
        _transport2, host2, worker2 = restore_pair(checkpoint, host.proof_ground)
        self.assertEqual(worker2.process_result_acknowledgements(), (1,))
        self.assertEqual(worker2.pending_result_sequences, ())

        next_action = host2.dispatch_next()
        self.assertIsNotNone(next_action)
        self.assertEqual(next_action.request["candidate_transition"]["tactic"], "simp")
        next_request = worker2.receive_request()
        self.assertIsNotNone(next_request)
        self.assertEqual(next_request.request, next_action.request)
        self.assertTrue(host2.observe_request_admission())

    def test_quarantine_payload_and_chain_survive_pair_restore(self):
        _session, source_trace, proof_ground, _transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)
        closed_attempt = host.active_attempt
        host.mark_no_result("host deadline elapsed")

        late_result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(closed_attempt),
            proof_trace=add_result_payload(
                source_trace, closed_attempt, result_status="timeout"
            ),
        )
        worker.send_result(late_result)
        self.assertIsNone(host.receive_result())
        self.assertEqual(host.quarantined_results[0]["payload"], late_result)

        checkpoint = export_proof_action_checkpoint(host, worker)
        _transport2, host2, worker2 = restore_pair(checkpoint, proof_ground)
        self.assertEqual(host2.quarantined_results, host.quarantined_results)
        self.assertEqual(host2.quarantined_results[0]["payload"], late_result)
        self.assertEqual(worker2._result_sent_attempt_ids, worker._result_sent_attempt_ids)

    def test_checkpoint_digest_rejects_mutated_transport_or_endpoint_state(self):
        _session, _trace, proof_ground, _transport, host, worker = make_endpoints()
        host.dispatch_next()
        checkpoint = export_proof_action_checkpoint(host, worker)

        mutated = copy.deepcopy(checkpoint)
        mutated["worker"]["worker_id"] = "other-worker"
        with self.assertRaisesRegex(ProofActionCheckpointError, "digest mismatch"):
            restore_pair(mutated, proof_ground)

        mutated_transport = copy.deepcopy(checkpoint)
        mutated_transport["transport"]["next_id"] += 1
        with self.assertRaisesRegex(ProofActionCheckpointError, "digest mismatch"):
            restore_pair(mutated_transport, proof_ground)

    def test_checkpoint_requires_both_endpoints_to_share_transport(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        other_worker_session, _trace2, _pg2, _transport2, _host2, worker2 = make_endpoints()
        with self.assertRaisesRegex(ProofActionCheckpointError, "same transport instance"):
            export_proof_action_checkpoint(host, worker2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
