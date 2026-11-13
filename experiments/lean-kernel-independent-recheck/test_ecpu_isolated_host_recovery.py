"""PR-safe host-provisioning and crash-prefix controls (not live Sigstore).

The authoritative multi-container, separate-process, certificate and replay
exercise happens only on a trusted main-branch GitHub Actions run.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

import ecpu_isolated_host_recovery as isolation
import ecpu_proof_transit as transport
import proof_receipt_receiver as receiver
import term_receipt as term


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL required for test-only certificate provisioner")
class VirtualHostProvisioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.source = self.root / "untrusted-subjects"
        self.source.mkdir(mode=0o700)
        self.subjects = {}
        for index, kind in enumerate(receiver.SUBJECTS):
            file = self.source / f"{kind}.source"
            file.write_bytes(bytes([index + 31]) * 101)
            self.subjects[kind] = file
        self.intent = self.root / "trusted-policy.json"
        self.intent_doc = {
            "format": receiver.POLICY_FORMAT,
            "recipient_scope": "ecpu-virtual-host-B",
            "expected_obligation_id": "b" * 64,
            "expected_source_sha": "c" * 40,
            "expected_run_id": "1234",
            "expected_run_attempt": "1",
            "not_before_unix": 10,
            "not_after_unix": 100,
            "revoked_receipt_refs": [],
            "revoked_source_shas": [],
        }
        term._write(self.intent, self.intent_doc)

    def test_credentials_intent_and_artifacts_are_provisioned_to_disjoint_hosts(self):
        folders = isolation._provision(self.root, self.subjects, self.intent)
        sender = folders["sender-credentials"]
        recipient = folders["recipient-credentials"]
        admin = folders["ca-provisioner"]
        self.assertEqual(
            set(path.name for path in sender.iterdir()),
            {"identity.key", "identity.pem", "ca.pem"},
        )
        self.assertEqual(
            set(path.name for path in recipient.iterdir()),
            {"identity.key", "identity.pem", "ca.pem"},
        )
        self.assertNotEqual(
            (sender / "identity.key").read_bytes(),
            (recipient / "identity.key").read_bytes(),
        )
        self.assertEqual(
            (sender / "ca.pem").read_bytes(),
            (recipient / "ca.pem").read_bytes(),
        )
        self.assertIn("demo-ca.key", {file.name for file in admin.iterdir()})
        self.assertFalse((sender / "demo-ca.key").exists())
        self.assertFalse((recipient / "demo-ca.key").exists())
        self.assertFalse((folders["sender-data"] / "trusted-intent.json").exists())
        self.assertFalse((folders["recipient-state"] / "runner.bin").exists())
        self.assertEqual(
            set(path.name for path in folders["sender-data"].iterdir()),
            {f"{kind}.bin" for kind in receiver.SUBJECTS},
        )
        self.assertEqual(
            (folders["recipient-state"] / "trusted-intent.json").read_bytes(),
            self.intent.read_bytes(),
        )
        for folder in (sender, recipient):
            self.assertEqual((folder / "identity.key").stat().st_mode & 0o777, 0o600)

    def test_recipient_intent_is_locally_pinned_and_not_rewritten_from_sender(self):
        self.intent_doc["recipient_scope"] = "attacker-controlled-scope"
        term._write(self.intent, self.intent_doc)
        with self.assertRaisesRegex(isolation.IsolatedHostFailure, "audience"):
            isolation._provision(self.root, self.subjects, self.intent)

    def test_missing_subject_or_symlinked_input_rejected_before_network(self):
        self.subjects.pop("signed")
        with self.assertRaisesRegex(isolation.IsolatedHostFailure, "six"):
            isolation._provision(self.root, self.subjects, self.intent)
        self.subjects["signed"] = self.source / "signed.source"
        alias = self.root / "alias"
        alias.symlink_to(self.subjects["signed"])
        self.subjects["signed"] = alias
        second_workspace = self.root / "second-provisioner"
        second_workspace.mkdir()
        with self.assertRaisesRegex(isolation.IsolatedHostFailure, "regular file"):
            isolation._provision(second_workspace, self.subjects, self.intent)

    def test_bounded_test_fault_prefix_requires_incomplete_manifest(self):
        for invalid in (-1, 0, False, 10_000):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                transport.ProofTransitError, "test fault prefix"
            ):
                transport.send_frames(
                    "127.0.0.1", 1, self.subjects,
                    ca=self.root / "not-needed",
                    cert=self.root / "not-needed",
                    key=self.root / "not-needed",
                    test_fault_after_frames=invalid,
                )

    def test_two_sender_prefix_frames_are_not_proof_admission(self):
        frames = transport.make_frames(self.subjects)
        decoder = transport.ProofStreamDecoder()
        for frame in frames[:2]:
            decoder.ingest(frame)
        self.assertFalse(decoder.finished)
        # The first subject may be fully buffered, but the six-subject
        # transfer is incomplete and cannot be promoted to VGI admission.
        self.assertEqual(set(decoder.raw), {"runner"})
        self.assertNotEqual(set(decoder.raw), set(transport.SUBJECTS))
        with self.assertRaisesRegex(transport.ProofTransitError, "incomplete"):
            decoder.materialize(self.root)


if __name__ == "__main__":
    unittest.main()
