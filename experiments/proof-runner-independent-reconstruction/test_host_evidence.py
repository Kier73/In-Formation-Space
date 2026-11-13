from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from host_evidence import (
    EvidenceError,
    KEY_PREDICATE_SCHEMA,
    _read,
    _verify_authority_material,
    _validate_authority_process_evidence,
    build_fixture,
)


class HostEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        build_fixture(self.root)
        self.ledger = _read(self.root / "authority" / "route-ledger.json")
        self.request = _read(self.root / "authority" / "request.json")
        self.attestation = _read(self.root / "authority" / "authority-attestation.json")
        authority_dir = self.root / "authority"
        self.authority_key = _read(authority_dir / "authority-public-key.json")
        self.history = _read(authority_dir / "store-history.json")["entries"]
        self.process_evidence = _read(authority_dir / "process-evidence.json")
        self.stale_attempt = _read(authority_dir / "stale-owner-attempt.json")
        self.database_path = authority_dir / "authority-store-fixture.bin"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_fixture_is_complete_and_authority_binding_reconstructs(self) -> None:
        event = _verify_authority_material(
            self.ledger,
            self.request,
            self.attestation,
            self.authority_key,
            history=self.history,
            process_evidence=self.process_evidence,
            stale_attempt=self.stale_attempt,
            database_path=self.database_path,
        )
        self.assertEqual(event["event_type"], "execution_authorized")
        self.assertEqual(event["details"]["attempt_id"], self.request["attempt_id"])
        self.assertEqual(event["details"]["request_digest"], self.request["request_digest"])
        self.assertTrue((self.root / "runner" / "completion-receipt.json").is_file())
        self.assertTrue((self.root / "verifier-host.json").is_file())

    def test_participant_attestation_predicate_binds_exact_key_and_host_role(self) -> None:
        key_path = self.root / "authority" / "authority-public-key.json"
        predicate = _read(self.root / "authority" / "authority-public-key.predicate.json")
        self.assertEqual(predicate["schema"], KEY_PREDICATE_SCHEMA)
        self.assertEqual(
            predicate["subject_sha256"],
            hashlib.sha256(key_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(predicate["participant"]["participant_id"], self.authority_key["participant_id"])
        self.assertEqual(predicate["participant"]["role"], "authority_host")
        self.assertEqual(predicate["participant"]["key_id"], self.authority_key["key_id"])
        self.assertEqual(predicate["participant"]["host"], self.authority_key["host"])

    def test_authority_signature_tampering_is_rejected(self) -> None:
        altered = copy.deepcopy(self.attestation)
        signature = altered["signature"]
        altered["signature"] = ("0" if signature[0] != "0" else "1") + signature[1:]
        with self.assertRaisesRegex(EvidenceError, "signature verification failed"):
            _verify_authority_material(
                self.ledger,
                self.request,
                altered,
                self.authority_key,
                history=self.history,
                process_evidence=self.process_evidence,
                stale_attempt=self.stale_attempt,
                database_path=self.database_path,
            )

    def test_ledger_substitution_is_rejected_by_signed_checkpoint(self) -> None:
        altered = copy.deepcopy(self.ledger)
        altered["entries"][1]["details"]["owner_generation"] = 9
        with self.assertRaisesRegex(EvidenceError, "route ledger digest mismatch"):
            _verify_authority_material(
                altered,
                self.request,
                self.attestation,
                self.authority_key,
                history=self.history,
                process_evidence=self.process_evidence,
                stale_attempt=self.stale_attempt,
                database_path=self.database_path,
            )

    def test_history_tampering_is_rejected_even_with_revision_link_rewrite(self) -> None:
        altered = copy.deepcopy(self.history)
        altered[1]["ledger_digest"] = "0" * 64
        altered[2]["previous_ledger_digest"] = "0" * 64
        with self.assertRaisesRegex(EvidenceError, "intermediate ledger digest mismatch"):
            _verify_authority_material(
                self.ledger,
                self.request,
                self.attestation,
                self.authority_key,
                history=altered,
                process_evidence=self.process_evidence,
                stale_attempt=self.stale_attempt,
                database_path=self.database_path,
            )

    def test_process_evidence_cannot_claim_a_different_stale_owner_outcome(self) -> None:
        altered_process = copy.deepcopy(self.process_evidence)
        altered_process["phases"][2]["accepted"] = True
        altered = altered_process["phases"][2]
        with self.assertRaisesRegex(EvidenceError, "stale owner-generation attempt"):
            _validate_authority_process_evidence(
                self.ledger,
                altered_process,
                altered,
                self.history,
                self.request,
            )

    def test_database_bytes_are_bound_by_the_authority_signature(self) -> None:
        altered_path = self.root / "authority" / "altered-store.bin"
        altered_path.write_bytes(self.database_path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(EvidenceError, "does not bind the ledger, SQLite audit"):
            _verify_authority_material(
                self.ledger,
                self.request,
                self.attestation,
                self.authority_key,
                history=self.history,
                process_evidence=self.process_evidence,
                stale_attempt=self.stale_attempt,
                database_path=altered_path,
            )

    def test_fixture_artifacts_are_reproducible(self) -> None:
        second = self.root / "second"
        build_fixture(second)
        for relative in (
            "authority/route-ledger.json",
            "authority/request.json",
            "authority/authority-attestation.json",
            "authority/authority-public-key.json",
            "authority/authority-public-key.predicate.json",
            "authority/store-history.json",
            "authority/process-evidence.json",
            "authority/stale-owner-attempt.json",
            "authority/authority-store-fixture.bin",
            "runner/result.json",
            "runner/completion-receipt.json",
            "runner/runner-public-key.json",
            "runner/runner-public-key.predicate.json",
            "verifier-host.json",
        ):
            self.assertEqual(
                (self.root / relative).read_bytes(),
                (second / relative).read_bytes(),
                relative,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
