"""USM-007: two actual claimant processes race existing durable route authority."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from independent_verify import canonical_digest
from model_route_fencing import (
    EPOCH, ModelPublicationRefused, open_authority,
    prepared_source, run_race,
)
from proof_action_route_epoch import ProofActionRouteEpochError, ProofActionRouteEpochLedger
from sqlite_route_epoch_store import SQLiteRouteEpochLedgerStore
from test_recovery_independent import recovery_fixture


class ModelResultFencingTests(unittest.TestCase):
    def test_two_real_processes_one_durable_owner_and_one_ticket(self):
        """Two distinct Python processes cannot both claim the same owner gen."""
        with tempfile.TemporaryDirectory(prefix="ifs-model-fence-") as d:
            report = run_race(recovery_fixture(), Path(d))
        self.assertEqual(report["schema"], "in-formation-space.usm007.model-result-fencing.v1")
        self.assertTrue(report["prior_model_recovery_verified"])
        self.assertTrue(report["one_owner_claim"])
        self.assertTrue(report["one_execution_authorization"])
        self.assertTrue(report["stale_receiver_refused"])
        self.assertTrue(report["single_host_authority"])
        self.assertFalse(report["remote_quorum_fencing_verified"])
        self.assertEqual(len(report["contenders"]), 2)
        self.assertEqual(
            sorted(item["outcome"] for item in report["contenders"]),
            ["authorized", "superseded"],
        )
        self.assertEqual(
            len(set(item["contender_process"] for item in report["contenders"])), 2
        )
        winner = next(x for x in report["contenders"] if x["outcome"] == "authorized")
        self.assertEqual(winner["owner_id"], report["winning_owner"])
        self.assertEqual(winner["publication"]["execution_id"], report["winning_ticket"])
        self.assertEqual(winner["publication"]["read_receipt_id"], report["read_receipt_id"])
        self.assertEqual(winner["publication"]["value"], report["recovered_value"])
        self.assertGreaterEqual(report["route_authority_revision_count"], 4)
        self.assertEqual(
            report["report_digest"],
            canonical_digest({k: v for k, v in report.items() if k != "report_digest"}),
        )

    def test_independent_evidence_must_pass_before_route_authority_is_created(self):
        """A forged Ground result cannot create a route, even with a new hash."""
        bad = recovery_fixture()
        bad["result"]["value"] += 1
        bad["report_digest"] = canonical_digest(
            {k: v for k, v in bad.items() if k != "report_digest"}
        )
        with tempfile.TemporaryDirectory(prefix="ifs-model-bad-") as d:
            folder = Path(d)
            with self.assertRaises(Exception):
                run_race(bad, folder)
            self.assertFalse((folder / "route-authority.sqlite").exists())

    def test_existing_authority_rejects_a_stale_owner_after_new_claim(self):
        """Use the native ledger's CAS semantics rather than a new lock."""
        original = recovery_fixture()
        verified = prepared_source(original)
        with tempfile.TemporaryDirectory(prefix="ifs-model-authority-") as d:
            database = Path(d) / "authority.sqlite"
            prepared = open_authority(database, verified)
            a = ProofActionRouteEpochLedger(SQLiteRouteEpochLedgerStore(database))
            b = ProofActionRouteEpochLedger(SQLiteRouteEpochLedgerStore(database))
            a.claim_epoch(
                EPOCH, owner_id="replacement-a",
                expected_owner_id=prepared["owner"],
                expected_owner_generation=1,
            )
            with self.assertRaises(ProofActionRouteEpochError):
                b.claim_epoch(
                    EPOCH, owner_id="replacement-b",
                    expected_owner_id=prepared["owner"],
                    expected_owner_generation=1,
                )
            b.refresh()
            self.assertEqual(b.active_epoch["owner_id"], "replacement-a")
            self.assertIsNone(b.record_execution_authorization(
                EPOCH, prepared["route_digest"],
                owner_id=prepared["owner"], owner_generation=1,
                attempt_id=verified["attempt_id"],
                request_digest=verified["request_digest"],
                runner_id="model-ground-result-publisher",
            ))

    def test_same_attempt_cannot_change_its_admitted_model_request(self):
        """Native route admission detects conflicting hashes for one attempt."""
        original = recovery_fixture()
        verified = prepared_source(original)
        with tempfile.TemporaryDirectory(prefix="ifs-model-request-") as d:
            database = Path(d) / "authority.sqlite"
            config = open_authority(database, verified)
            fresh = ProofActionRouteEpochLedger(SQLiteRouteEpochLedgerStore(database))
            self.assertTrue(fresh.record_request_admission(
                EPOCH, config["route_digest"],
                owner_id=config["owner"], owner_generation=1,
                request_sequence=4,
                attempt_id=verified["attempt_id"],
                request_digest=verified["request_digest"],
            ))
            with self.assertRaises(ProofActionRouteEpochError):
                fresh.record_request_admission(
                    EPOCH, config["route_digest"],
                    owner_id=config["owner"], owner_generation=1,
                    request_sequence=5,
                    attempt_id=verified["attempt_id"],
                    request_digest="0" * 64,
                )


if __name__ == "__main__":
    unittest.main()
