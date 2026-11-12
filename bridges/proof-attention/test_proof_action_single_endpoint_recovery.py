from __future__ import annotations

import unittest

from proof_action_checkpoint import (
    restore_proof_action_host,
    restore_proof_action_worker,
    snapshot_proof_action_host,
    snapshot_proof_action_worker,
)
from proof_action_protocol import make_proof_action_result
from test_proof_action_execution import add_result_payload
from test_proof_action_protocol import return_evidence
from test_proof_action_reliable_channel import (
    deliver_request_and_admit,
    make_endpoints,
)


class ProofActionSingleEndpointRecoveryTests(unittest.TestCase):
    def test_host_restart_preserves_pending_request_while_worker_stays_live(self):
        _session, _trace, proof_ground, transport, host, worker = make_endpoints()
        dispatched = host.dispatch_next()
        checkpoint = snapshot_proof_action_host(host)

        restored_host = restore_proof_action_host(
            checkpoint, proof_ground, transport
        )

        received = worker.receive_request()
        self.assertIsNotNone(received)
        self.assertEqual(received.request_sequence, dispatched.request_sequence)
        self.assertEqual(received.request, dispatched.request)
        self.assertTrue(restored_host.observe_request_admission())
        self.assertEqual(restored_host.active_attempt.status, "admitted")
        self.assertIsNone(worker.receive_request())

    def test_worker_restart_preserves_admission_and_can_return_result(self):
        _session, source_trace, _proof_ground, transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)
        checkpoint = snapshot_proof_action_worker(worker)

        restored_worker = restore_proof_action_worker(checkpoint, transport)
        attempt = host.active_attempt
        result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=add_result_payload(source_trace, attempt),
        )

        self.assertEqual(restored_worker.send_result(result), 1)
        imported = host.receive_result()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.attempt_id, attempt.attempt_id)
        self.assertEqual(attempt.status, "interpreted")
        self.assertEqual(restored_worker.process_result_acknowledgements(), (1,))
        self.assertEqual(restored_worker.pending_result_sequences, ())

    def test_worker_restart_with_result_in_flight_preserves_pending_sender(self):
        _session, source_trace, _proof_ground, transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        result = make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=add_result_payload(source_trace, attempt),
        )
        self.assertEqual(worker.send_result(result), 1)

        checkpoint = snapshot_proof_action_worker(worker)
        restored_worker = restore_proof_action_worker(checkpoint, transport)
        imported = host.receive_result()

        self.assertIsNotNone(imported)
        self.assertEqual(imported.attempt_id, attempt.attempt_id)
        self.assertEqual(attempt.status, "interpreted")
        self.assertEqual(restored_worker.process_result_acknowledgements(), (1,))
        self.assertEqual(restored_worker.pending_result_sequences, ())

    def test_host_restart_with_result_waiting_in_mailbox_interprets_once(self):
        _session, source_trace, proof_ground, transport, host, worker = make_endpoints()
        _dispatched, received = deliver_request_and_admit(host, worker)
        attempt = host.active_attempt
        worker.send_result(make_proof_action_result(
            received.request,
            return_evidence=return_evidence(attempt),
            proof_trace=add_result_payload(source_trace, attempt),
        ))

        checkpoint = snapshot_proof_action_host(host)
        restored_host = restore_proof_action_host(
            checkpoint, proof_ground, transport
        )
        imported = restored_host.receive_result()

        self.assertIsNotNone(imported)
        self.assertEqual(imported.attempt_id, attempt.attempt_id)
        self.assertEqual(restored_host.session.attempts[0].status, "interpreted")
        self.assertEqual(worker.process_result_acknowledgements(), (1,))
        self.assertIsNone(restored_host.receive_result())
        self.assertEqual(
            [event["stage"] for event in restored_host.session.attempts[0].events].count(
                "interpreted"
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
