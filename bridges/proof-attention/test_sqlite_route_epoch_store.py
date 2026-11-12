from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from proof_action_route_epoch import (
    ProofActionRouteEpochError,
    ProofActionRouteEpochLedger,
    open_proof_action_route_epoch,
    handoff_proof_action_route_epoch,
)
from sqlite_route_epoch_store import (
    SQLiteRouteEpochLedgerStore,
    SQLiteRouteEpochStoreError,
)
from test_proof_action_reliable_channel import make_endpoints


class SQLiteRouteEpochLedgerStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "route-authority.sqlite3"

    def tearDown(self):
        self.temporary.cleanup()

    def make_open_ledger(self, store, *, epoch_id="sqlite-epoch", owner_id="owner-initial"):
        _session, _trace, _pg, _transport, host, worker = make_endpoints()
        ledger = ProofActionRouteEpochLedger(store=store)
        open_proof_action_route_epoch(
            host,
            worker,
            ledger,
            epoch_id=epoch_id,
            owner_id=owner_id,
        )
        return host, worker, ledger

    def test_reopens_durable_owner_generation_and_revision_history(self):
        first_store = SQLiteRouteEpochLedgerStore(self.database_path)
        host, worker, first_ledger = self.make_open_ledger(first_store)
        before = first_store.load()
        self.assertEqual(before["entries"][0]["event_type"], "opened")

        active = first_ledger.active_epoch
        first_ledger.claim_epoch(
            active["epoch_id"],
            owner_id="owner-after-restart",
            expected_owner_id=active["owner_id"],
            expected_owner_generation=active["owner_generation"],
        )

        # Create a fresh store object as a new process would after restart.
        second_store = SQLiteRouteEpochLedgerStore(self.database_path)
        restored_document = second_store.load()
        restored_ledger = ProofActionRouteEpochLedger.from_dict(
            restored_document,
            store=second_store,
        )

        self.assertEqual(restored_ledger.active_epoch["epoch_id"], "sqlite-epoch")
        self.assertEqual(restored_ledger.active_epoch["owner_id"], "owner-after-restart")
        self.assertEqual(restored_ledger.active_epoch["owner_generation"], 2)
        history = second_store.revision_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["previous_ledger_digest"], None)
        self.assertEqual(
            history[1]["previous_ledger_digest"],
            history[0]["ledger_digest"],
        )
        self.assertEqual(history[0]["actor_id"], "owner-initial")
        self.assertEqual(history[1]["actor_id"], "owner-after-restart")
        self.assertEqual(len(history[0]["appended_event_digests"]), 1)
        self.assertEqual(len(history[1]["appended_event_digests"]), 1)

    def test_worker_admission_is_durable_across_sqlite_store_reopen(self):
        first_store = SQLiteRouteEpochLedgerStore(self.database_path)
        _host, _worker, ledger = self.make_open_ledger(
            first_store,
            epoch_id="sqlite-admission-epoch",
            owner_id="sqlite-admission-owner",
        )
        # Endpoint pair comes from the helper for the exact route/transport pair.
        # Build another helper call with the same route identities on that
        # transport so the worker and host share the same admitted message path.
        transport = _host.transport
        session = _host.session
        proof_ground = _host.proof_ground
        from proof_action_reliable_channel import (
            ProofActionReliableHost, ProofActionReliableWorker
        )
        host = ProofActionReliableHost(
            session, proof_ground, transport,
            host_id=_host.host_id, worker_id=_host.worker_id,
            request_channel=_host.request_channel, result_channel=_host.result_channel,
            policy=_host.policy,
        )
        worker = ProofActionReliableWorker(
            transport,
            host_id=_host.host_id, worker_id=_host.worker_id,
            request_channel=_host.request_channel, result_channel=_host.result_channel,
            policy=_host.policy,
        )
        from proof_action_route_epoch import bind_existing_proof_action_route_epoch
        bind_existing_proof_action_route_epoch(
            host, worker, ledger, epoch_id="sqlite-admission-epoch",
            owner_id="sqlite-admission-replacement-owner",
        )
        dispatch = host.dispatch_next()
        received = worker.receive_request()
        self.assertIsNotNone(received)
        self.assertEqual(received.request_sequence, dispatch.request_sequence)

        # Reload using a completely new SQLite adapter as a fresh process would.
        second_store = SQLiteRouteEpochLedgerStore(self.database_path)
        restored = ProofActionRouteEpochLedger.from_dict(
            second_store.load(), store=second_store
        )
        admission = [
            event for event in restored.entries
            if event["event_type"] == "admitted"
        ]
        self.assertEqual(len(admission), 1)
        self.assertEqual(admission[0]["details"]["attempt_id"], dispatch.attempt_id)
        self.assertEqual(
            admission[0]["details"]["request_digest"],
            dispatch.request_digest,
        )
        history = second_store.revision_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(len(history[-1]["appended_event_digests"]), 1)
        self.assertEqual(
            history[-1]["appended_event_digests"][0],
            admission[0]["event_digest"],
        )

    def test_atomic_route_handoff_is_one_durable_revision_with_two_events(self):
        store = SQLiteRouteEpochLedgerStore(self.database_path)
        _host, _worker, ledger = self.make_open_ledger(store)
        self.assertEqual(len(store.revision_history()), 1)

        handoff = handoff_proof_action_route_epoch(
            _host,
            _worker,
            ledger,
            epoch_id="sqlite-epoch",
            reason_code="operator_rotation",
            reason="move the route using a single durable CAS",
            successor_epoch_id="sqlite-epoch-next",
            successor_host_id="sqlite-host-next",
            successor_worker_id="sqlite-worker-next",
            successor_request_channel="sqlite-request-next",
            successor_result_channel="sqlite-result-next",
        )

        history = store.revision_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(len(history[1]["appended_event_digests"]), 2)
        current = store.load()
        tail = current["entries"][-2:]
        self.assertEqual([event["event_type"] for event in tail], ["closed", "opened"])
        self.assertEqual(tail[1]["previous_event_digest"], tail[0]["event_digest"])
        self.assertEqual(
            tail[1]["details"]["predecessor_close_digest"],
            tail[0]["event_digest"],
        )
        self.assertEqual(
            ProofActionRouteEpochLedger.from_dict(current).active_epoch["epoch_id"],
            handoff.opened_epoch["epoch_id"],
        )

    def test_two_independent_connections_cannot_publish_the_same_stale_revision(self):
        store_a = SQLiteRouteEpochLedgerStore(self.database_path)
        _host, _worker, ledger = self.make_open_ledger(store_a)
        initial_document = store_a.load()
        initial_digest = initial_document["ledger_digest"]

        # Prepare two valid but competing successor ledger documents from the
        # same starting revision, as two processes might do before CAS.
        candidate_a = ProofActionRouteEpochLedger.from_dict(initial_document)
        candidate_b = ProofActionRouteEpochLedger.from_dict(initial_document)
        active_a = candidate_a.active_epoch
        active_b = candidate_b.active_epoch
        candidate_a.claim_epoch(
            active_a["epoch_id"],
            owner_id="concurrent-owner-a",
            expected_owner_id=active_a["owner_id"],
            expected_owner_generation=active_a["owner_generation"],
        )
        candidate_b.claim_epoch(
            active_b["epoch_id"],
            owner_id="concurrent-owner-b",
            expected_owner_id=active_b["owner_id"],
            expected_owner_generation=active_b["owner_generation"],
        )

        store_b = SQLiteRouteEpochLedgerStore(self.database_path)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(
                store_a.compare_and_swap,
                initial_digest,
                candidate_a.to_dict(),
                actor_id="concurrent-owner-a",
            )
            future_b = executor.submit(
                store_b.compare_and_swap,
                initial_digest,
                candidate_b.to_dict(),
                actor_id="concurrent-owner-b",
            )
            outcomes = [future_a.result(), future_b.result()]

        self.assertEqual(sorted(outcomes), [False, True])
        persisted = ProofActionRouteEpochLedger.from_dict(store_a.load())
        self.assertIn(
            persisted.active_epoch["owner_id"],
            {"concurrent-owner-a", "concurrent-owner-b"},
        )
        self.assertEqual(persisted.active_epoch["owner_generation"], 2)
        self.assertEqual(len(store_a.revision_history()), 2)

    def test_store_rejects_a_valid_but_non_append_only_replacement(self):
        store = SQLiteRouteEpochLedgerStore(self.database_path)
        _host, _worker, ledger = self.make_open_ledger(store)
        current = store.load()

        alternate = ProofActionRouteEpochLedger()
        alternate.open_epoch(
            "different-history",
            current["entries"][0]["route"],
            owner_id="other-owner",
        )
        with self.assertRaisesRegex(
            SQLiteRouteEpochStoreError,
            "not an append-only extension",
        ):
            store.compare_and_swap(
                current["ledger_digest"],
                alternate.to_dict(),
                actor_id="other-owner",
            )
        self.assertEqual(store.load(), current)
        self.assertEqual(len(store.revision_history()), 1)

    def test_audit_event_index_detects_database_tampering(self):
        store = SQLiteRouteEpochLedgerStore(self.database_path)
        _host, _worker, ledger = self.make_open_ledger(store)
        active = ledger.active_epoch
        ledger.claim_epoch(
            active["epoch_id"],
            owner_id="owner-second",
            expected_owner_id=active["owner_id"],
            expected_owner_generation=active["owner_generation"],
        )

        connection = sqlite3.connect(str(self.database_path))
        try:
            connection.execute(
                """
                UPDATE route_epoch_revisions
                SET appended_event_digests_json = ?
                WHERE revision = 2
                """,
                (json.dumps(["0" * 64]),),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(
            SQLiteRouteEpochStoreError,
            "audit event index",
        ):
            store.load()

    def test_execution_authorization_ticket_survives_sqlite_restart(self):
        store = SQLiteRouteEpochLedgerStore(self.database_path)
        host, worker, ledger = self.make_open_ledger(
            store,
            epoch_id="sqlite-execution-epoch",
            owner_id="sqlite-execution-owner",
        )
        host.dispatch_next()
        received = worker.receive_request()
        self.assertIsNotNone(received)

        dispatch = worker.execute_request(
            received,
            runner_id="sqlite-restartable-runner",
            runner=lambda execution_id, request: {
                "execution_id": execution_id,
                "attempt_id": request["attempt_id"],
            },
        )
        self.assertIsNotNone(dispatch)

        # Reopen both the durable adapter and ledger as a separate process.
        reopened_store = SQLiteRouteEpochLedgerStore(self.database_path)
        reopened_ledger = ProofActionRouteEpochLedger.from_dict(
            reopened_store.load(),
            store=reopened_store,
        )
        execution_events = [
            event for event in reopened_ledger.entries
            if event["event_type"] == "execution_authorized"
        ]
        self.assertEqual(len(execution_events), 1)
        self.assertEqual(
            execution_events[0]["details"]["execution_id"],
            dispatch.execution_id,
        )
        self.assertEqual(
            execution_events[0]["details"]["runner_id"],
            "sqlite-restartable-runner",
        )
        history = reopened_store.revision_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(
            history[-1]["appended_event_digests"],
            [execution_events[0]["event_digest"]],
        )

    def test_invalid_paths_and_timeout_values_are_rejected(self):
        with self.assertRaisesRegex(SQLiteRouteEpochStoreError, "filesystem database path"):
            SQLiteRouteEpochLedgerStore(":memory:")
        with self.assertRaisesRegex(SQLiteRouteEpochStoreError, "timeout_seconds"):
            SQLiteRouteEpochLedgerStore(self.database_path, timeout_seconds=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
