from __future__ import annotations

import copy
import hashlib
import json
import unittest

from mailcpu.reliability import ReliabilityPolicy
from mailcpu.transport import InMemoryTransport

from proof_action_checkpoint import (
    export_proof_action_checkpoint,
    restore_proof_action_host,
    restore_proof_action_worker,
    snapshot_proof_action_host,
    snapshot_proof_action_worker,
)
from proof_action_reliable_channel import (
    ProofActionReliableHost,
    ProofActionReliableWorker,
)
from proof_action_route_epoch import (
    InMemoryRouteEpochLedgerStore,
    ProofActionRouteEpochError,
    ProofActionRouteEpochLedger,
    bind_existing_proof_action_route_epoch,
    handoff_proof_action_route_epoch,
    open_proof_action_route_epoch,
    restore_proof_action_route_handoff,
    _uncertainty_projection,
)
from test_proof_action_execution import make_session, ground
from test_proof_action_reliable_channel import make_endpoints


class ProofActionRouteEpochTests(unittest.TestCase):
    def test_handoff_preserves_uncertain_request_and_fences_old_endpoints(self):
        _session, _trace, _pg, transport, host, worker = make_endpoints()
        ledger = ProofActionRouteEpochLedger()
        opened = open_proof_action_route_epoch(
            host, worker, ledger, epoch_id="epoch-1", owner_id="process-a"
        )
        self.assertEqual(opened["details"]["owner_generation"], 1)

        dispatched = host.dispatch_next()
        received = worker.receive_request()
        self.assertIsNotNone(received)
        self.assertEqual(received.request["attempt_id"], dispatched.attempt_id)
        # The worker ACK is queued; host has not consumed it yet.

        handoff = handoff_proof_action_route_epoch(
            host,
            worker,
            ledger,
            epoch_id="epoch-1",
            reason_code="operator_rotation",
            reason="move this proof action to a fresh worker route",
            successor_epoch_id="epoch-2",
            successor_host_id="proof-host-2",
            successor_worker_id="proof-worker-2",
            successor_request_channel="proof-action-request-epoch-2",
            successor_result_channel="proof-action-result-epoch-2",
        )

        closed = handoff.closed_epoch
        self.assertEqual(closed["details"]["reason_code"], "operator_rotation")
        self.assertEqual(
            len(closed["details"]["preclose_session_digest"]), 64
        )
        self.assertNotEqual(
            closed["details"]["preclose_session_digest"],
            closed["details"]["postclose_session_digest"],
        )
        uncertainty = closed["details"]["uncertainty"]
        self.assertEqual(uncertainty["channel_states"]["host_request_sender"]["pending"][0]["sequence"], 1)
        self.assertEqual(uncertainty["channel_states"]["worker_request_receiver"]["delivered"], [1])
        self.assertTrue(
            any(item["kind"] == "RACK" for item in uncertainty["queued_reliable_frames"])
        )
        self.assertEqual(
            uncertainty["pending_frames"][0]["frame"]["format"],
            "mailcpu-reliable-frame/1",
        )
        self.assertEqual(
            closed["details"]["pair_checkpoint_digest"],
            hashlib.sha256(
                json.dumps(
                    closed["details"]["pair_checkpoint"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest(),
        )

        self.assertEqual(host.session.attempts[0].status, "route_closed")
        self.assertEqual(handoff.host.session.attempts[0].status, "route_closed")
        self.assertEqual(ledger.active_epoch["epoch_id"], "epoch-2")
        self.assertEqual(
            handoff.opened_epoch["details"]["predecessor_close_digest"],
            closed["event_digest"],
        )

        with self.assertRaisesRegex(ProofActionRouteEpochError, "closed or superseded"):
            host.dispatch_next()
        with self.assertRaisesRegex(ProofActionRouteEpochError, "closed or superseded"):
            worker.receive_request()

        next_action = handoff.host.dispatch_next()
        self.assertIsNotNone(next_action)
        self.assertNotEqual(next_action.attempt_id, dispatched.attempt_id)
        next_request = handoff.worker.receive_request()
        self.assertIsNotNone(next_request)
        self.assertEqual(next_request.request, next_action.request)
        self.assertTrue(handoff.host.observe_request_admission())

        restored_ledger = ProofActionRouteEpochLedger.from_dict(ledger.to_dict())
        self.assertEqual(restored_ledger.active_epoch["epoch_id"], "epoch-2")
        self.assertEqual(transport.pending() > 0, True)

    def test_planned_action_moves_to_successor_without_being_reselected_or_lost(self):
        session, source_trace, _root_id = make_session()
        proof_ground = ground(source_trace)
        planned = session.begin_next()
        transport = InMemoryTransport()
        policy = ReliabilityPolicy()
        host = ProofActionReliableHost(
            session, proof_ground, transport,
            host_id="planned-host", worker_id="planned-worker",
            request_channel="planned-request", result_channel="planned-result",
            policy=policy,
        )
        worker = ProofActionReliableWorker(
            transport, worker_id="planned-worker", host_id="planned-host",
            request_channel="planned-request", result_channel="planned-result",
            policy=policy,
        )
        ledger = ProofActionRouteEpochLedger()
        open_proof_action_route_epoch(host, worker, ledger, epoch_id="planned-epoch")

        handoff = handoff_proof_action_route_epoch(
            host,
            worker,
            ledger,
            epoch_id="planned-epoch",
            reason_code="planned_migration",
            reason="move before dispatch",
            successor_epoch_id="planned-epoch-2",
            successor_host_id="planned-host-2",
            successor_worker_id="planned-worker-2",
            successor_request_channel="planned-request-2",
            successor_result_channel="planned-result-2",
        )
        self.assertEqual(handoff.host.active_attempt.attempt_id, planned.attempt_id)
        self.assertEqual(handoff.host.active_attempt.status, "planned")

        dispatch = handoff.host.dispatch_next()
        self.assertEqual(dispatch.attempt_id, planned.attempt_id)
        request = handoff.worker.receive_request()
        self.assertEqual(request.request, dispatch.request)
        self.assertTrue(handoff.host.observe_request_admission())

    def test_claiming_restored_epoch_increments_owner_and_fences_old_process(self):
        _session, _trace, proof_ground, transport, host, worker = make_endpoints()
        ledger = ProofActionRouteEpochLedger()
        open_proof_action_route_epoch(
            host, worker, ledger, epoch_id="restart-epoch", owner_id="owner-old"
        )
        host_state = snapshot_proof_action_host(host)
        worker_state = snapshot_proof_action_worker(worker)

        replacement_host = restore_proof_action_host(host_state, proof_ground, transport)
        replacement_worker = restore_proof_action_worker(worker_state, transport)
        bind_existing_proof_action_route_epoch(
            replacement_host, replacement_worker, ledger, epoch_id="restart-epoch"
        )

        active = ledger.active_epoch
        self.assertEqual(active["owner_generation"], 2)
        self.assertNotEqual(active["owner_id"], "owner-old")
        with self.assertRaisesRegex(ProofActionRouteEpochError, "closed or superseded"):
            host.dispatch_next()
        with self.assertRaisesRegex(ProofActionRouteEpochError, "closed or superseded"):
            worker.receive_request()

        dispatch = replacement_host.dispatch_next()
        received = replacement_worker.receive_request()
        self.assertEqual(received.request, dispatch.request)
        self.assertTrue(replacement_host.observe_request_admission())

        restored_ledger = ProofActionRouteEpochLedger.from_dict(ledger.to_dict())
        self.assertEqual(restored_ledger.active_epoch["owner_generation"], 2)

    def test_ledger_rejects_reused_route_identity_and_tampered_owner_chain(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        ledger = ProofActionRouteEpochLedger()
        open_proof_action_route_epoch(
            host, worker, ledger, epoch_id="integrity-epoch", owner_id="owner-1"
        )
        document = ledger.to_dict()
        self.assertEqual(
            ProofActionRouteEpochLedger.from_dict(document).active_epoch["owner_id"],
            "owner-1",
        )

        tampered = copy.deepcopy(document)
        tampered["entries"][0]["details"]["owner_generation"] = 2
        with self.assertRaisesRegex(ProofActionRouteEpochError, "ledger digest mismatch"):
            ProofActionRouteEpochLedger.from_dict(tampered)

        closed = handoff_proof_action_route_epoch(
            host,
            worker,
            ledger,
            epoch_id="integrity-epoch",
            reason_code="operator_rotation",
            reason="rotate after identity reuse test",
            successor_epoch_id="integrity-epoch-2",
            successor_host_id="integrity-host-2",
            successor_worker_id="integrity-worker-2",
            successor_request_channel="integrity-request-2",
            successor_result_channel="integrity-result-2",
        )
        closed_again = handoff_proof_action_route_epoch(
            closed.host,
            closed.worker,
            ledger,
            epoch_id="integrity-epoch-2",
            reason_code="planned_migration",
            reason="close successor before testing route reuse",
            successor_epoch_id="integrity-epoch-3",
            successor_host_id="integrity-host-3",
            successor_worker_id="integrity-worker-3",
            successor_request_channel="integrity-request-3",
            successor_result_channel="integrity-result-3",
        )
        # The old tuple is now invalid even though no epoch is currently open.
        second_close = handoff_proof_action_route_epoch(
            closed_again.host,
            closed_again.worker,
            ledger,
            epoch_id="integrity-epoch-3",
            reason_code="planned_migration",
            reason="close third epoch for route reuse assertion",
            successor_epoch_id="integrity-epoch-4",
            successor_host_id="integrity-host-4",
            successor_worker_id="integrity-worker-4",
            successor_request_channel="integrity-request-4",
            successor_result_channel="integrity-result-4",
        )
        with self.assertRaisesRegex(ProofActionRouteEpochError, "already used"):
            ledger.open_epoch(
                "epoch-reuse",
                closed.closed_epoch["route"],
                owner_id="owner-2",
                predecessor_close_digest=second_close.closed_epoch["event_digest"],
            )

    def test_authoritative_claim_fences_old_process_using_shared_store(self):
        _session, _trace, proof_ground, transport, old_host, old_worker = make_endpoints()
        store = InMemoryRouteEpochLedgerStore()
        old_ledger = ProofActionRouteEpochLedger(store=store)
        open_proof_action_route_epoch(
            old_host,
            old_worker,
            old_ledger,
            epoch_id="authority-epoch",
            owner_id="owner-process-a",
        )

        host_snapshot = snapshot_proof_action_host(old_host)
        worker_snapshot = snapshot_proof_action_worker(old_worker)
        replacement_host = restore_proof_action_host(
            host_snapshot, proof_ground, transport
        )
        replacement_worker = restore_proof_action_worker(
            worker_snapshot, transport
        )
        replacement_ledger = ProofActionRouteEpochLedger.from_dict(
            store.load(), store=store
        )
        bind_existing_proof_action_route_epoch(
            replacement_host,
            replacement_worker,
            replacement_ledger,
            epoch_id="authority-epoch",
        )

        current = replacement_ledger.active_epoch
        self.assertEqual(current["owner_generation"], 2)
        self.assertNotEqual(current["owner_id"], "owner-process-a")
        # The old process retains its generation-one local ledger, but the
        # authority check reads generation two on every guarded operation.
        with self.assertRaisesRegex(
            ProofActionRouteEpochError, "authoritative store"
        ):
            old_host.dispatch_next()
        with self.assertRaisesRegex(
            ProofActionRouteEpochError, "authoritative store"
        ):
            old_worker.receive_request()

        dispatch = replacement_host.dispatch_next()
        received = replacement_worker.receive_request()
        self.assertEqual(received.request, dispatch.request)
        self.assertTrue(replacement_host.observe_request_admission())

    def test_shared_store_compare_and_swap_rejects_stale_revision(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        store = InMemoryRouteEpochLedgerStore()
        ledger = ProofActionRouteEpochLedger(store=store)
        open_proof_action_route_epoch(
            host, worker, ledger, epoch_id="cas-epoch", owner_id="cas-owner-1"
        )
        stale_document = store.load()
        stale_digest = stale_document["ledger_digest"]

        ledger.claim_epoch("cas-epoch", owner_id="cas-owner-2")
        current_document = store.load()
        self.assertNotEqual(current_document["ledger_digest"], stale_digest)
        self.assertFalse(
            store.compare_and_swap(
                stale_digest, stale_document, actor_id="stale-process"
            )
        )
        self.assertEqual(
            ProofActionRouteEpochLedger.from_dict(current_document).active_epoch[
                "owner_generation"
            ],
            2,
        )

    def test_closed_epoch_authorizes_only_its_declared_successor_route(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        ledger = ProofActionRouteEpochLedger()
        open_proof_action_route_epoch(
            host, worker, ledger, epoch_id="authorized-epoch", owner_id="route-owner"
        )
        host.dispatch_next()
        checkpoint = export_proof_action_checkpoint(host, worker)
        uncertainty = _uncertainty_projection(checkpoint)
        session_digest = host.session.to_dict()["session_digest"]
        successor = {
            "host_id": "authorized-host-next",
            "worker_id": "authorized-worker-next",
            "request_channel": "authorized-request-next",
            "result_channel": "authorized-result-next",
            "policy": {
                "lease_ticks": host.policy.lease_ticks,
                "max_attempts": host.policy.max_attempts,
                "window_size": host.policy.window_size,
            },
        }
        closed = ledger.close_epoch(
            "authorized-epoch",
            ledger.active_epoch["route"],
            reason_code="planned_migration",
            reason="test successor authorization",
            owner_id=ledger.active_epoch["owner_id"],
            owner_generation=ledger.active_epoch["owner_generation"],
            pair_checkpoint=checkpoint,
            preclose_session_digest=session_digest,
            postclose_session_digest=session_digest,
            postclose_session_snapshot=host.session.to_dict(),
            uncertainty=uncertainty,
            successor_epoch_id="authorized-epoch-next",
            successor_owner_id="authorized-owner",
            successor_route=successor,
        )

        wrong_route = dict(successor)
        wrong_route["host_id"] = "unauthorized-host"
        with self.assertRaisesRegex(
            ProofActionRouteEpochError,
            "does not match the successor authorized",
        ):
            ledger.open_epoch(
                "unauthorized-epoch",
                wrong_route,
                owner_id="unauthorized-owner",
                predecessor_close_digest=closed["event_digest"],
            )
        opened = ledger.open_epoch(
            "authorized-epoch-next",
            successor,
            owner_id="authorized-owner",
            predecessor_close_digest=closed["event_digest"],
        )
        self.assertEqual(ledger.active_epoch["epoch_id"], "authorized-epoch-next")
        self.assertEqual(opened["route"], successor)

    def test_close_rejects_a_rehashed_but_incomplete_uncertainty_projection(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        ledger = ProofActionRouteEpochLedger()
        open_proof_action_route_epoch(
            host, worker, ledger, epoch_id="uncertainty-epoch"
        )
        host.dispatch_next()
        checkpoint = export_proof_action_checkpoint(host, worker)
        uncertainty = _uncertainty_projection(checkpoint)
        uncertainty["pending_frames"] = []
        uncertainty_core = {
            key: value for key, value in uncertainty.items()
            if key != "uncertainty_digest"
        }
        uncertainty["uncertainty_digest"] = hashlib.sha256(
            json.dumps(
                uncertainty_core,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        session_digest = host.session.to_dict()["session_digest"]
        successor = {
            "host_id": "uncertainty-host-next",
            "worker_id": "uncertainty-worker-next",
            "request_channel": "uncertainty-request-next",
            "result_channel": "uncertainty-result-next",
            "policy": {
                "lease_ticks": host.policy.lease_ticks,
                "max_attempts": host.policy.max_attempts,
                "window_size": host.policy.window_size,
            },
        }
        with self.assertRaisesRegex(
            ProofActionRouteEpochError,
            "does not describe the preserved pair checkpoint",
        ):
            ledger.close_epoch(
                "uncertainty-epoch",
                ledger.active_epoch["route"],
                reason_code="planned_migration",
                reason="incomplete uncertainty projection",
                owner_id=ledger.active_epoch["owner_id"],
                owner_generation=ledger.active_epoch["owner_generation"],
                pair_checkpoint=checkpoint,
                preclose_session_digest=session_digest,
                postclose_session_digest=session_digest,
                postclose_session_snapshot=host.session.to_dict(),
                uncertainty=uncertainty,
                successor_epoch_id="uncertainty-epoch-next",
                successor_owner_id="uncertainty-owner-next",
                successor_route=successor,
            )

    def test_stale_owner_cannot_commit_handoff_after_replacement_claim(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        store = InMemoryRouteEpochLedgerStore()
        old_ledger = ProofActionRouteEpochLedger(store=store)
        open_proof_action_route_epoch(
            host, worker, old_ledger,
            epoch_id="stale-close-epoch", owner_id="stale-close-owner"
        )
        host.dispatch_next()
        checkpoint = export_proof_action_checkpoint(host, worker)
        uncertainty = _uncertainty_projection(checkpoint)
        session_digest = host.session.to_dict()["session_digest"]

        replacement_ledger = ProofActionRouteEpochLedger.from_dict(
            store.load(), store=store
        )
        replacement_ledger.claim_epoch(
            "stale-close-epoch", owner_id="replacement-close-owner"
        )
        successor = {
            "host_id": "stale-close-host-next",
            "worker_id": "stale-close-worker-next",
            "request_channel": "stale-close-request-next",
            "result_channel": "stale-close-result-next",
            "policy": {
                "lease_ticks": host.policy.lease_ticks,
                "max_attempts": host.policy.max_attempts,
                "window_size": host.policy.window_size,
            },
        }
        with self.assertRaisesRegex(
            ProofActionRouteEpochError, "stale owner generation"
        ):
            old_ledger.handoff_epoch(
                "stale-close-epoch",
                old_ledger.active_epoch["route"],
                reason_code="operator_rotation",
                reason="stale process tried to close after replacement claim",
                owner_id="stale-close-owner",
                owner_generation=1,
                pair_checkpoint=checkpoint,
                preclose_session_digest=session_digest,
                postclose_session_digest=session_digest,
                postclose_session_snapshot=host.session.to_dict(),
                uncertainty=uncertainty,
                successor_epoch_id="stale-close-epoch-next",
                successor_owner_id="stale-close-successor",
                successor_route=successor,
            )
        self.assertEqual(host.active_attempt.status, "dispatched")
        self.assertEqual(
            replacement_ledger.active_epoch["owner_id"],
            "replacement-close-owner",
        )

    def test_handoff_commits_close_and_successor_open_in_one_cas_write(self):
        class CountingStore(InMemoryRouteEpochLedgerStore):
            def __init__(self):
                super().__init__()
                self.write_count = 0

            def compare_and_swap(
                self, expected_ledger_digest, replacement, *, actor_id
            ):
                self.write_count += 1
                return super().compare_and_swap(
                    expected_ledger_digest, replacement, actor_id=actor_id
                )

        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        store = CountingStore()
        ledger = ProofActionRouteEpochLedger(store=store)
        open_proof_action_route_epoch(
            host, worker, ledger, epoch_id="atomic-handoff-epoch"
        )
        self.assertEqual(store.write_count, 1)
        host.dispatch_next()

        handoff = handoff_proof_action_route_epoch(
            host,
            worker,
            ledger,
            epoch_id="atomic-handoff-epoch",
            reason_code="operator_rotation",
            reason="commit close and successor as one authority revision",
            successor_epoch_id="atomic-handoff-epoch-next",
            successor_host_id="atomic-handoff-host-next",
            successor_worker_id="atomic-handoff-worker-next",
            successor_request_channel="atomic-handoff-request-next",
            successor_result_channel="atomic-handoff-result-next",
        )
        self.assertEqual(store.write_count, 2)
        persisted = store.load()
        tail = persisted["entries"][-2:]
        self.assertEqual([event["event_type"] for event in tail], ["closed", "opened"])
        self.assertEqual(
            tail[1]["previous_event_digest"],
            tail[0]["event_digest"],
        )
        self.assertEqual(
            tail[1]["details"]["predecessor_close_digest"],
            tail[0]["event_digest"],
        )
        self.assertEqual(
            ProofActionRouteEpochLedger.from_dict(persisted).active_epoch["epoch_id"],
            handoff.opened_epoch["epoch_id"],
        )
        with self.assertRaisesRegex(ProofActionRouteEpochError, "closed or superseded"):
            host.dispatch_next()

    def test_restore_successor_after_crash_immediately_following_handoff_commit(self):
        _session, _trace, proof_ground, _old_transport, host, worker = make_endpoints()
        store = InMemoryRouteEpochLedgerStore()
        ledger = ProofActionRouteEpochLedger(store=store)
        open_proof_action_route_epoch(
            host, worker, ledger,
            epoch_id="crash-recovery-epoch",
            owner_id="crash-process-owner",
        )
        dispatched = host.dispatch_next()
        received = worker.receive_request()
        self.assertEqual(received.request_sequence, dispatched.request_sequence)

        handoff = handoff_proof_action_route_epoch(
            host,
            worker,
            ledger,
            epoch_id="crash-recovery-epoch",
            reason_code="worker_replacement",
            reason="simulate process loss after route handoff commit",
            successor_epoch_id="crash-recovery-epoch-next",
            successor_host_id="crash-recovery-host-next",
            successor_worker_id="crash-recovery-worker-next",
            successor_request_channel="crash-recovery-request-next",
            successor_result_channel="crash-recovery-result-next",
        )
        self.assertEqual(host.session.attempts[0].status, "route_closed")

        # Simulate a fresh process loading only the durable ledger and close record;
        # discard the returned endpoint objects from the original handoff call.
        recovered_ledger = ProofActionRouteEpochLedger.from_dict(
            store.load(), store=store
        )
        transport, recovered_host, recovered_worker = restore_proof_action_route_handoff(
            handoff.closed_epoch,
            recovered_ledger,
            proof_ground,
            restore_transport=InMemoryTransport.from_snapshot,
            owner_id="crash-recovery-new-process",
        )

        self.assertIsInstance(transport, InMemoryTransport)
        self.assertEqual(recovered_ledger.active_epoch["epoch_id"], "crash-recovery-epoch-next")
        self.assertEqual(recovered_ledger.active_epoch["owner_generation"], 2)
        self.assertEqual(
            recovered_host.session.to_dict()["session_digest"],
            handoff.closed_epoch["details"]["postclose_session_digest"],
        )
        self.assertEqual(recovered_host.session.attempts[0].status, "route_closed")
        self.assertIsNone(recovered_worker.receive_request())
        self.assertGreater(transport.pending(), 0)

        # The successor selects a new attempt; the route-closed action is not replayed.
        next_dispatch = recovered_host.dispatch_next()
        self.assertIsNotNone(next_dispatch)
        self.assertNotEqual(next_dispatch.attempt_id, dispatched.attempt_id)
        next_request = recovered_worker.receive_request()
        self.assertEqual(next_request.request, next_dispatch.request)
        self.assertTrue(recovered_host.observe_request_admission())

    def test_invalid_successor_is_rejected_before_closing_current_epoch(self):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        ledger = ProofActionRouteEpochLedger()
        open_proof_action_route_epoch(host, worker, ledger, epoch_id="safe-epoch")
        host.dispatch_next()

        with self.assertRaises(ProofActionRouteEpochError):
            handoff_proof_action_route_epoch(
                host,
                worker,
                ledger,
                epoch_id="safe-epoch",
                reason_code="operator_rotation",
                reason="bad successor",
                successor_epoch_id="epoch-next",
                successor_host_id=host.host_id,
                successor_worker_id=worker.worker_id,
                successor_request_channel=host.request_channel,
                successor_result_channel=host.result_channel,
            )
        self.assertEqual(ledger.active_epoch["epoch_id"], "safe-epoch")
        self.assertEqual(host.active_attempt.status, "dispatched")


if __name__ == "__main__":
    unittest.main(verbosity=2)
