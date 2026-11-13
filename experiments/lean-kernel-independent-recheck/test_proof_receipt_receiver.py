"""Adversarial recipient contract tests (mock gh: NOT cryptographic evidence).

Live GitHub/Sigstore verification must independently pass in the main-only
recipient job. The tests cover durable SQLite admission and trust separation.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import term_receipt as term
import serialized_kernel_evidence as serialized
import unified_kernel_receipt as unified
import proof_receipt_receiver as receiver
from test_unified_kernel_receipt import case_record, MockGH


SHA = "b" * 40
RUN = "73492"
ATTEMPT = "1"
CTX = {"git_sha": SHA, "run_id": RUN, "run_attempt": ATTEMPT}


def host(role):
    return {
        "role": role, "job": role, "repository": unified.REPO,
        "git_sha": SHA, "run_id": RUN, "run_attempt": ATTEMPT,
    }


class ProofTransferReceiverTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.paths = {
            name: root / f"{name}.json" for name in receiver.SUBJECTS
        }
        self.paths["public_key"] = root / "checker-key.pem"
        self.ledger = root / "durable-ledger.sqlite3"
        self.intent = root / "trusted-receiver-intent.json"
        key = Ed25519PrivateKey.generate()
        exp = {
            "format": term.TERM_FORMAT, "theorem": term.THEOREM,
            "type": {"kind": "forallE", "body": {"kind": "bvar", "index": 0}},
            "proof": {"kind": "lam", "body": {"kind": "bvar", "index": 0}},
        }
        environment = term.make_environment()
        runner = term.make_observation(
            exp, case_digest="a" * 64, host=host("proof_runner"), environment=environment
        )
        checker = term.make_observation(
            exp, case_digest="f" * 64, host=host("independent_checker"), environment=environment
        )
        signed = term.recheck(runner, checker, key)
        kernel = {
            "format": serialized.FORMAT,
            "status": "serialized_term_kernel_rechecked",
            "theorem": term.THEOREM,
            "toolchain": term.TOOLCHAIN,
            "serialized_expression_profile": term.TERM_FORMAT,
            "checker_source_sha256": serialized.checker_source_sha(),
            "original_runner_observation_digest": runner["document_digest"],
            "proof_term_fingerprint": runner["proof_term_fingerprint"],
            "type_fingerprint": runner["type_fingerprint"],
            "obligation_id": runner["obligation_id"],
            "environment_fingerprint": runner["environment"]["environment_fingerprint"],
            "checker_host": {
                "repository": unified.REPO, "git_sha": SHA,
                "run_id": RUN, "run_attempt": ATTEMPT,
                "job": "serialized_kernel_checker",
            },
            "cases": [case_record(exp, x) for x in serialized.SAMPLES],
            "vgi_verified_kernel_receipt_issued": False,
            "not_established": ["test-only constructed kernel report"],
        }
        kernel["document_digest"] = term.digest(kernel)
        self.documents = {
            "runner": runner, "checker": checker,
            "signed": signed, "serialized_kernel": kernel,
        }
        for kind, doc in self.documents.items():
            term._write(self.paths[kind], doc)
        self.paths["public_key"].write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        subjects = {}
        for kind in unified.SUBJECT_NAMES:
            subjects[kind] = {
                "kind": kind,
                "sha256": hashlib.sha256(self.paths[kind].read_bytes()).hexdigest(),
                "verification_result_sha256": "0" * 64,
                "source_repository_id": unified.REPO_ID,
            }
        receipt = unified.unify(
            runner_doc=runner, checker_doc=checker, signed_doc=signed,
            kernel_doc=kernel, public_key=key.public_key(),
            attested_subjects=subjects, gh_version="2.103.3", context=CTX,
        )
        self.receipt = receipt
        term._write(self.paths["unified_receipt"], receipt)
        self.intent_doc = {
            "format": receiver.POLICY_FORMAT,
            "recipient_scope": "host-B",
            "expected_obligation_id": runner["obligation_id"],
            "expected_source_sha": SHA,
            "expected_run_id": RUN,
            "expected_run_attempt": ATTEMPT,
            "not_before_unix": 1000,
            "not_after_unix": 2000,
            "revoked_receipt_refs": [],
            "revoked_source_shas": [],
        }
        self.write_intent()
        self.fake = MockGH()

    def write_intent(self):
        term._write(self.intent, self.intent_doc)

    def accept(self, *, now=1500):
        return receiver.receive(
            paths=self.paths, intent_path=self.intent,
            ledger_path=self.ledger,
            command_runner=self.fake, now_unix=now,
        )

    def tamper(self, kind, mutation):
        doc = copy.deepcopy(self.documents[kind] if kind != "unified_receipt" else self.receipt)
        mutation(doc)
        doc["document_digest"] = term.digest({k:v for k,v in doc.items() if k!="document_digest"})
        term._write(self.paths[kind], doc)

    def test_accepts_independently_reconstructed_single_receipt(self):
        result = self.accept()
        self.assertEqual(result["status"], "accepted_once_after_independent_verification")
        self.assertEqual(result["receipt_ref"], self.receipt["verified_kernel_receipt"]["receipt_ref"])
        self.assertEqual(result["obligation_id"], self.intent_doc["expected_obligation_id"])
        self.assertEqual(len(self.fake.calls), 7)  # one patched-gh version + six attestation checks
        with sqlite3.connect(self.ledger) as conn:
            rows = conn.execute("SELECT recipient_scope, obligation_id, run_id FROM accepted_proof_transfers").fetchall()
        self.assertEqual(rows, [("host-B", self.intent_doc["expected_obligation_id"], RUN)])

    def test_replay_is_rejected_after_new_connection_and_restart(self):
        self.accept()
        with self.assertRaisesRegex(receiver.ReplayRejected, "replayed"):
            self.accept()
        with sqlite3.connect(self.ledger) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM accepted_proof_transfers").fetchone()[0], 1)

    def test_two_concurrent_transactions_accept_exactly_one(self):
        intent = receiver.ReceiverIntent.load(self.intent)
        ref = self.receipt["verified_kernel_receipt"]["receipt_ref"]
        sha = self.receipt["document_digest"]
        def add(_):
            try:
                receiver._accept_once(self.ledger, intent, ref, sha, 1500)
                return "accepted"
            except receiver.ReplayRejected:
                return "replay"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(add, range(2)))
        self.assertCountEqual(results, ["accepted", "replay"])

    def test_another_recipient_scope_has_its_own_durable_ledger_namespace(self):
        self.accept()
        self.intent_doc["recipient_scope"] = "host-C"
        self.write_intent()
        self.assertEqual(self.accept()["recipient_scope"], "host-C")

    def test_mismatched_intended_obligation_fails_before_verification(self):
        self.intent_doc["expected_obligation_id"] = "b" * 64
        self.write_intent()
        with self.assertRaisesRegex(receiver.ReceiverReject, "intent"):
            self.accept()
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.ledger.exists())

    def test_cross_run_and_wrong_commit_replay_fail_before_verification(self):
        for key, value in (
            ("expected_run_id", "123"),
            ("expected_run_attempt", "3"),
            ("expected_source_sha", "c" * 40),
        ):
            self.intent_doc[key] = value
            self.write_intent()
            with self.assertRaisesRegex(receiver.ReceiverReject, "intent"):
                self.accept()
            self.intent_doc[key] = {"expected_run_id": RUN,
                                    "expected_run_attempt": ATTEMPT,
                                    "expected_source_sha": SHA}[key]
        self.assertEqual(self.fake.calls, [])

    def test_expired_and_not_yet_active_local_policy_reject(self):
        with self.assertRaisesRegex(receiver.ReceiverReject, "approval window"):
            self.accept(now=999)
        with self.assertRaisesRegex(receiver.ReceiverReject, "approval window"):
            self.accept(now=2000)
        self.assertEqual(self.fake.calls, [])

    def test_revoked_commit_or_receipt_ref_reject(self):
        self.intent_doc["revoked_source_shas"] = [SHA]
        self.write_intent()
        with self.assertRaisesRegex(receiver.ReceiverReject, "revoked"):
            self.accept()
        self.intent_doc["revoked_source_shas"] = []
        self.intent_doc["revoked_receipt_refs"] = [self.receipt["verified_kernel_receipt"]["receipt_ref"]]
        self.write_intent()
        with self.assertRaisesRegex(receiver.ReceiverReject, "revoked"):
            self.accept()

    def test_missing_tampered_or_symlinked_subject_rejected(self):
        self.paths["serialized_kernel"].unlink()
        with self.assertRaises(receiver.ReceiverReject):
            self.accept()
        term._write(self.paths["serialized_kernel"], self.documents["serialized_kernel"])
        replacement = self.paths["unified_receipt"].with_suffix(".source")
        self.paths["unified_receipt"].rename(replacement)
        self.paths["unified_receipt"].symlink_to(replacement)
        with self.assertRaisesRegex(receiver.ReceiverReject, "symlink"):
            self.accept()

    def test_invalid_attestation_for_final_receipt_cannot_be_forged(self):
        self.fake.bad_subject = self.paths["unified_receipt"].name
        with self.assertRaises(term.TermReceiptError):
            self.accept()
        self.assertFalse(self.ledger.exists())

    def test_unpatched_cli_or_wrong_repository_rejects(self):
        self.fake.version = "gh version 2.101.0 (2026-09-11)"
        with self.assertRaisesRegex(term.TermReceiptError, "unpatched"):
            self.accept()
        self.fake = MockGH()
        self.fake.bad_repository = True
        with self.assertRaises(term.TermReceiptError):
            self.accept()

    def test_invalid_source_signature_even_with_attested_kernel_rejected(self):
        self.tamper("signed", lambda doc: doc.update(signature_base64="AAAA"))
        with self.assertRaises(term.TermReceiptError):
            self.accept()
        self.assertFalse(self.ledger.exists())

    def test_forged_unified_status_or_receipt_reference_rejected(self):
        self.tamper("unified_receipt", lambda doc: doc["verified_kernel_receipt"].update(
            receipt_ref="sha256:" + "1" * 64
        ))
        with self.assertRaises(receiver.ReceiverReject):
            self.accept()
        self.assertFalse(self.ledger.exists())

    def test_missing_serialized_negative_control_rejected(self):
        self.tamper("serialized_kernel", lambda doc: doc["cases"].pop())
        with self.assertRaises(receiver.ReceiverReject):
            self.accept()

    def test_noncanonical_json_bytes_even_with_mocked_attestation_rejected(self):
        path = self.paths["runner"]
        path.write_bytes(b" " + path.read_bytes())
        with self.assertRaisesRegex(receiver.ReceiverReject, "canonical"):
            self.accept()
        self.assertEqual(self.fake.calls, [])

    def test_malformed_recipient_intent_is_not_inferred_from_sender(self):
        self.intent_doc.pop("expected_obligation_id")
        self.write_intent()
        with self.assertRaisesRegex(term.TermReceiptError, "unexpected"):
            self.accept()
        self.assertEqual(self.fake.calls, [])


if __name__ == "__main__":
    unittest.main()
