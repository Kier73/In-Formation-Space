from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from durable_authority import (
    build_sqlite_authority_bundle,
    validate_revision_history,
    verify_sqlite_authority_bundle,
)


class DurableAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = build_sqlite_authority_bundle(
            self.root / "authority",
            run_id="sqlite-process-test",
            runner_id="runner-sqlite-test",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_authority_reopens_across_three_processes_and_rejects_old_generation(self):
        phases = self.bundle["process_evidence"]["phases"]
        self.assertEqual(
            [item["phase"] for item in phases],
            [
                "initial_open",
                "restart_claim_admit_authorize",
                "stale_generation_replay",
            ],
        )
        self.assertEqual(len({item["process_instance_id"] for item in phases}), 3)
        self.assertEqual(self.bundle["store_revision_count"], 4)
        self.assertEqual(
            [event["event_type"] for event in self.bundle["ledger"]["entries"]],
            ["opened", "claimed", "admitted", "execution_authorized"],
        )
        stale = self.bundle["stale_owner_attempt"]
        self.assertFalse(stale["accepted"])
        self.assertEqual(stale["observed_owner_generation"], 2)
        self.assertTrue(self.bundle["process_evidence"]["stale_owner_attempt_rejected"])
        self.assertFalse(
            any(
                event["event_type"] == "admitted"
                and event["details"]["attempt_id"] == stale["stale_attempt_id"]
                for event in self.bundle["ledger"]["entries"]
            )
        )

    def test_revision_history_reconstructs_every_intermediate_ledger_digest(self):
        validate_revision_history(self.bundle["ledger"], self.bundle["history"])
        self.assertEqual(len(self.bundle["history"]), 4)
        previous = None
        for index, row in enumerate(self.bundle["history"], 1):
            self.assertEqual(row["revision"], index)
            self.assertEqual(row["previous_ledger_digest"], previous)
            self.assertEqual(len(row["appended_event_digests"]), 1)
            previous = row["ledger_digest"]
        self.assertEqual(previous, self.bundle["ledger"]["ledger_digest"])

    def test_independent_host_can_reopen_actual_database_and_match_exported_evidence(self):
        result = verify_sqlite_authority_bundle(
            self.bundle["database_path"],
            expected_ledger=self.bundle["ledger"],
            expected_history=self.bundle["history"],
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["revision_count"], 4)
        self.assertEqual(result["active_owner_generation"], 2)
        self.assertEqual(
            result["active_epoch_id"],
            self.bundle["active_epoch"]["epoch_id"],
        )

    def test_modified_intermediate_revision_is_rejected_even_when_chain_links_are_rewritten(self):
        altered = [dict(item) for item in self.bundle["history"]]
        altered[1] = dict(altered[1])
        altered[1]["ledger_digest"] = "0" * 64
        altered[2] = dict(altered[2])
        altered[2]["previous_ledger_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "intermediate ledger digest mismatch"):
            validate_revision_history(self.bundle["ledger"], altered)

    def test_sqlite_audit_event_index_detects_database_tampering(self):
        tampered_path = self.root / "tampered.sqlite3"
        tampered_path.write_bytes(self.bundle["database_path"].read_bytes())
        connection = sqlite3.connect(str(tampered_path))
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

        with self.assertRaisesRegex(Exception, "audit event index"):
            verify_sqlite_authority_bundle(
                tampered_path,
                expected_ledger=self.bundle["ledger"],
                expected_history=self.bundle["history"],
            )

    def test_two_os_processes_racing_one_sqlite_revision_have_exactly_one_winner(self):
        # Build a second database with only its initial route event so both
        # child processes can prepare different valid claims from the same head.
        database = self.root / "race.sqlite3"
        database.parent.mkdir(parents=True, exist_ok=True)
        # Prepare two independent candidates from one one-event authority head.
        from durable_authority import _load_types, _route
        Ledger, Store = _load_types()
        store = Store(database)
        ledger = Ledger(store=store)
        ledger.open_epoch(
            "sqlite-race-epoch",
            _route("sqlite-race"),
            owner_id="sqlite-race-owner-initial",
        )
        initial = store.load()
        initial_digest = initial["ledger_digest"]

        candidate_documents = []
        for owner in ("sqlite-race-owner-a", "sqlite-race-owner-b"):
            candidate = Ledger.from_dict(initial)
            active = candidate.active_epoch
            candidate.claim_epoch(
                active["epoch_id"],
                owner_id=owner,
                expected_owner_id=active["owner_id"],
                expected_owner_generation=active["owner_generation"],
            )
            path = self.root / f"{owner}.json"
            path.write_bytes(
                __import__("formats.canonical_metadata_v1", fromlist=["canonical_bytes"])
                .canonical_bytes(candidate.to_dict())
                + b"\n"
            )
            candidate_documents.append((owner, path))

        gate = self.root / "start-cas-race"
        children = []
        result_paths = []
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [
                str(Path(__file__).resolve().parents[2] / "bridges" / "proof-attention"),
                str(Path(__file__).resolve().parents[2] / "external" / "E-CPU"),
                str(Path(__file__).resolve().parents[2]),
                env.get("PYTHONPATH", ""),
            ]
        )
        script = Path(__file__).with_name("durable_authority.py")
        try:
            for actor, candidate_path in candidate_documents:
                result_path = self.root / f"{actor}.result.json"
                result_paths.append(result_path)
                child = subprocess.Popen(
                    [
                        sys.executable,
                        str(script),
                        "cas",
                        "--database", str(database),
                        "--candidate", str(candidate_path),
                        "--expected-digest", initial_digest,
                        "--actor-id", actor,
                        "--start-gate", str(gate),
                        "--result", str(result_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                children.append(child)
            gate.write_text("go", encoding="utf-8")
            for child in children:
                stdout, stderr = child.communicate(timeout=30)
                self.assertEqual(
                    child.returncode,
                    0,
                    f"CAS child failed: stdout={stdout!r} stderr={stderr!r}",
                )
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)

        outcomes = [
            json.loads(path.read_text(encoding="utf-8"))["accepted"]
            for path in result_paths
        ]
        self.assertEqual(sorted(outcomes), [False, True])
        reopened = Ledger.from_dict(Store(database).load())
        self.assertEqual(reopened.active_epoch["owner_generation"], 2)
        self.assertIn(
            reopened.active_epoch["owner_id"],
            {"sqlite-race-owner-a", "sqlite-race-owner-b"},
        )
        self.assertEqual(len(Store(database).revision_history()), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
