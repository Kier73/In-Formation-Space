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
        self.authority_key = _read(self.root / "authority" / "authority-public-key.json")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_fixture_is_complete_and_authority_binding_reconstructs(self) -> None:
        event = _verify_authority_material(
            self.ledger, self.request, self.attestation, self.authority_key
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
                self.ledger, self.request, altered, self.authority_key
            )

    def test_ledger_substitution_is_rejected_by_signed_checkpoint(self) -> None:
        altered = copy.deepcopy(self.ledger)
        altered["entries"][1]["details"]["request_sequence"] = 99
        with self.assertRaisesRegex(EvidenceError, "ledger digest mismatch"):
            _verify_authority_material(
                altered, self.request, self.attestation, self.authority_key
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
