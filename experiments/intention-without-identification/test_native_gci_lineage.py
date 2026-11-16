"""IWI-006 native integration tests, consuming actual GCI-005 live mTLS artifacts.

The required IWI006_EVIDENCE_DIRECTORY is the phase-BLIND output of the
existing hosted GCI-005 authenticated-disagreement workflow. This suite is
not a fake transport fixture and deliberately does not import the hidden phase.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import native_gci_lineage as b
from mailcpu.federated_ground_continuity import AtomicGroundEvidenceStore
from mailcpu.recovery_lineage import (
    RecoveryLineageCoordinator, RecoveryLineageError, RecoveryStateManifest,
)


class ActualSignedReceiptToVGITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        directory = os.environ.get("IWI006_EVIDENCE_DIRECTORY")
        pins = os.environ.get("IWI006_PINS")
        if not directory or not pins:
            raise RuntimeError(
                "IWI006 requires the existing phase-blind GCI-005 live artifacts "
                "and a separately supplied pinned source identity"
            )
        cls.directory = Path(directory)
        cls.pins_file = Path(pins)
        if (cls.directory / "gci003-private.json").exists():
            raise RuntimeError("GCI-005 private phase leaked into IWI-006 verifier")
        cls.pins = b.VerifiedSourcePins.from_dict(
            json.loads(cls.pins_file.read_text(encoding="utf-8"))
        )
        cls.binding, cls.public, cls.plan = b.h.get_binding(cls.directory)
        cls.report = json.loads((cls.directory / "gci005-quorum.json").read_text())
        cls.network = json.loads((cls.directory / "gci004-network.json").read_text())
        cls.artifact = b.reconstruct(
            cls.report, cls.binding, cls.public, cls.plan,
            cls.network, pins=cls.pins,
        )

    def test_actual_source_signatures_to_vgi_authorized_and_conflict(self) -> None:
        report = b.verify_artifact(self.artifact, pins=self.pins)
        self.assertEqual(report["decisions"], ["AUTHORIZED", "CONFLICT"])
        observations = self.artifact["vgi_observation_events"]
        self.assertEqual([x["vgi_status_before_finalization"] for x in observations],
                         ["QUORUM", "CONFLICT"])
        self.assertEqual(len(observations[0]["native_vgi_ground"]["observations"]), 1)
        self.assertEqual(len(observations[1]["native_vgi_ground"]["observations"]), 0)
        for row in observations:
            self.assertFalse(row["ground_complete"])
            self.assertFalse(row["original_tls_frame_reconstructed"])
            self.assertFalse(row["persistent_phase_law_proven"])
            self.assertEqual(len(row["native_vgi_ledger"]["evidence"]), 2)

    def test_source_report_cannot_be_replaced_after_attested_pin(self) -> None:
        changed = copy.deepcopy(self.artifact)
        changed["gci005_report"]["rounds"][0]["receipts"][0]["payload"]["value"] ^= 1
        with self.assertRaises(Exception):
            b.verify_artifact(changed, pins=self.pins)
        changed = copy.deepcopy(self.artifact)
        changed["gci005_report"]["rounds"][0]["discovery"][0]["certificate_pem"] = (
            changed["gci005_report"]["rounds"][0]["discovery"][1]["certificate_pem"]
        )
        with self.assertRaises(Exception):
            b.verify_artifact(changed, pins=self.pins)
        changed = copy.deepcopy(self.artifact)
        changed["gci004_network"]["report_digest"] = "0" * 64
        with self.assertRaises(Exception):
            b.verify_artifact(changed, pins=self.pins)

    def test_resealed_outer_report_cannot_rescue_bad_ecdsa_source_signature(self) -> None:
        # Changing both source JSON and the outer report digest defeats a
        # digest-only consistency checker. The original GCI-005 source
        # verifier must *still* inspect the original ECDSA receipt bytes.
        raw = copy.deepcopy(self.report)
        raw["rounds"][0]["receipts"][0]["signature_b64"] = (
            raw["rounds"][0]["receipts"][1]["signature_b64"]
        )
        raw.pop("report_digest")
        forged = b.h.c.sealed(raw)
        forged_pins = dataclasses.replace(
            self.pins, gci005_digest=forged["report_digest"]
        )
        with self.assertRaises(Exception):
            b.reconstruct(
                forged, self.binding, self.public, self.plan,
                self.network, pins=forged_pins,
            )

    def test_native_vgi_finalization_cannot_be_forged_in_artifact(self) -> None:
        changed = copy.deepcopy(self.artifact)
        changed["vgi_observation_events"][1]["vgi_finalization"] = "AUTHORIZED"
        with self.assertRaises(b.NativeReuseRefused):
            b.verify_artifact(changed, pins=self.pins)
        changed = copy.deepcopy(self.artifact)
        changed["vgi_observation_events"][0]["native_vgi_ground"]["observations"] = []
        with self.assertRaises(b.NativeReuseRefused):
            b.verify_artifact(changed, pins=self.pins)
        changed = copy.deepcopy(self.artifact)
        changed["external_source_law_proven"] = True
        with self.assertRaises(b.NativeReuseRefused):
            b.verify_artifact(changed, pins=self.pins)

    def test_pins_are_external_and_wrong_trust_root_is_rejected(self) -> None:
        changed = dataclasses.replace(self.pins, ca_digest_honest="a" * 64)
        with self.assertRaises(b.NativeReuseRefused):
            b.verify_artifact(self.artifact, pins=changed)
        changed = dataclasses.replace(self.pins, ground_fingerprint="b" * 64)
        with self.assertRaises(b.NativeReuseRefused):
            b.verify_artifact(self.artifact, pins=changed)
        changed = dataclasses.replace(self.pins, gci004_digest="c" * 64)
        with self.assertRaises(b.NativeReuseRefused):
            b.verify_artifact(self.artifact, pins=changed)

    def test_atomic_store_and_three_journal_majority_recovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iwi006-quorum-test-") as td:
            root = Path(td)
            storage = AtomicGroundEvidenceStore(root / "store")
            authority = b.native_coordinator(root / "journals")
            m, proof = b.seal_artifact(
                self.artifact, pins=self.pins, coordinator=authority,
                storage=storage, generation=1,
                predecessor_digest=authority.membership.genesis_state_digest,
            )
            self.assertGreaterEqual(len(proof.decisions), authority.membership.quorum)
            # New process-style object reconstruction from durable journals.
            again = b.native_coordinator(root / "journals")
            recovered = b.recover_artifact(
                pins=self.pins, coordinator=again, storage=storage,
                manifest=RecoveryStateManifest.from_snapshot(m.snapshot()),
                proof=proof,
            )
            self.assertEqual(recovered["status"], "RECOVERED_SIGNED_OBSERVATIONS")
            self.assertEqual(recovered["decisions"], ["AUTHORIZED", "CONFLICT"])
            self.assertFalse(recovered["reexecuted_receivers"])
            self.assertFalse(recovered["source_phase_stationarity_proven"])
            self.assertFalse(recovered["independent_machine_quorum_proven"])

    def test_majority_failure_does_not_admit_prepared_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iwi006-minority-") as td:
            root = Path(td)
            storage = AtomicGroundEvidenceStore(root / "store")
            full = b.native_coordinator(root / "journals")
            one = RecoveryLineageCoordinator(
                full.membership, {"anchor-a": full.authorities["anchor-a"]}
            )
            with self.assertRaises(RecoveryLineageError):
                b.seal_artifact(
                    self.artifact, pins=self.pins, coordinator=one,
                    storage=storage, generation=1,
                    predecessor_digest=full.membership.genesis_state_digest,
                )
            # Content may be durably prepared, but this is NOT a committed proof.
            self.assertEqual(list((root / "store").glob("*.json")) != [], True)
            self.assertEqual(full.latest_proof(), None)

    def test_new_quorum_generation_fences_older_successful_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iwi006-stale-") as td:
            root = Path(td)
            storage = AtomicGroundEvidenceStore(root / "store")
            first_authority = b.native_coordinator(root / "journals")
            one, proof_one = b.seal_artifact(
                self.artifact, pins=self.pins, coordinator=first_authority,
                storage=storage, generation=1,
                predecessor_digest=first_authority.membership.genesis_state_digest,
            )
            two, proof_two = b.seal_artifact(
                self.artifact, pins=self.pins, coordinator=first_authority,
                storage=storage, generation=2, predecessor_digest=one.digest,
            )
            again = b.native_coordinator(root / "journals")
            with self.assertRaises(RecoveryLineageError):
                b.recover_artifact(
                    pins=self.pins, coordinator=again, storage=storage,
                    manifest=one, proof=proof_one,
                )
            self.assertEqual(b.recover_artifact(
                pins=self.pins, coordinator=again, storage=storage,
                manifest=two, proof=proof_two,
            )["state_digest"], two.state_digest)

    def test_corrupt_store_refused_after_valid_majority_seal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iwi006-corruption-") as td:
            root = Path(td)
            storage = AtomicGroundEvidenceStore(root / "store")
            coordinator = b.native_coordinator(root / "journals")
            m, proof = b.seal_artifact(
                self.artifact, pins=self.pins, coordinator=coordinator,
                storage=storage, generation=1,
                predecessor_digest=coordinator.membership.genesis_state_digest,
            )
            blob_path = storage.directory / (m.state_digest + ".json")
            original = blob_path.read_bytes()
            blob_path.write_bytes(original + b"tampered")
            with self.assertRaises(Exception):
                b.recover_artifact(
                    pins=self.pins, coordinator=coordinator, storage=storage,
                    manifest=m, proof=proof,
                )
            blob_path.write_bytes(original)
            self.assertEqual(b.recover_artifact(
                pins=self.pins, coordinator=coordinator, storage=storage,
                manifest=m, proof=proof,
            )["decisions"], ["AUTHORIZED", "CONFLICT"])

    def test_seal_and_recover_in_distinct_real_OS_processes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iwi006-processes-") as td:
            args = [
                sys.executable, str(Path(b.__file__).resolve()),
                "--durable", td, "--pins", str(self.pins_file.resolve()),
            ]
            env = os.environ.copy()
            seal = subprocess.run(
                args[:2] + ["seal"] + args[2:] + [
                    "--directory", str(self.directory.resolve())
                ],
                capture_output=True, text=True, timeout=30, env=env,
            )
            self.assertEqual(seal.returncode, 0, seal.stderr)
            sealed = json.loads(seal.stdout)
            self.assertEqual(sealed["status"], "SEALED_SIGNED_VGI_OBSERVATIONS")
            recovered = subprocess.run(
                args[:2] + ["recover"] + args[2:],
                capture_output=True, text=True, timeout=30, env=env,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            got = json.loads(recovered.stdout)
            self.assertEqual(got["status"], "RECOVERED_SIGNED_OBSERVATIONS")
            self.assertEqual(got["decisions"], ["AUTHORIZED", "CONFLICT"])
            self.assertEqual(got["state_digest"], sealed["state_digest"])
            self.assertFalse(got["reexecuted_receivers"])


if __name__ == "__main__":
    unittest.main()
