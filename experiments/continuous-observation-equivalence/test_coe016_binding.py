"""Adversarial tests of COE-016 evidence joining (not mock cryptographic proof tests).

Real cryptography and mathematical verification run in independent CI jobs.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from coe016_binding import BindingError, join
from verify_certificates import EXPECTED_NETWORK_DIGESTS

NAMES = sorted(EXPECTED_NETWORK_DIGESTS)
PASS_LINE = "COE-014 {}: original network SHA-256 and pin PASS, two mutations rejected"


class BindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        files = {}
        py = {}
        go = {}
        for i, name in enumerate(NAMES):
            raw = ("fixture:" + name + "\n").encode()
            (self.folder / (name + ".json")).write_bytes(raw)
            h = sha256(raw).hexdigest()
            semantic = sha256(("sem:" + name).encode()).hexdigest()
            files[name] = {"original_file_sha256": h, "length_bytes": len(raw)}
            py[name] = {"status": "verified", "certificate_sha256": h,
                        "network_sha256": EXPECTED_NETWORK_DIGESTS[name],
                        "semantic_sha256": semantic}
            go[name] = dict(py[name])
        self.auth = {
            "schema": "ifs.coe015.source-authority-receipt/v1",
            "status": "verified-policy-scoped-signatures-and-network-bytes",
            "policy_mode": "test-only",
            "ground_admitted": False,
            "origin_authenticated": False,
            "verified_signers": ["demo-22", "demo-33"],
            "threshold": 2,
            "authority": "demo-untrusted-keys",
            "manifest_version": 3,
            "network_hashes": dict(EXPECTED_NETWORK_DIGESTS),
        }
        self.lean = {
            "schema": "in-formation-space.coe013.original-canonical-json-replay/0.1",
            "status": "kernel-checked-JSON-structure-after-unverified-raw-byte-embedding",
            "parser": "COE013Json.parseEnvelope",
            "count": len(NAMES),
            "files": files,
        }
        self.python = {"schema": "in-formation-space.coe002.independent-check-report/0.1",
                       "status": "all_verified", "claim_count": len(NAMES), "claims": py}
        self.go = {"schema": "in-formation-space.coe003.go-independent-report/0.1",
                   "status": "all_verified", "claim_count": len(NAMES), "claims": go}
        self.log = "\n".join(PASS_LINE.format(name) for name in NAMES)

    def check(self):
        return join(self.folder, self.auth, self.lean, self.python, self.go, self.log)

    def test_exact_same_bytes_and_explicit_non_admission(self):
        receipt = self.check()
        self.assertEqual(receipt["source_count"], 5)
        self.assertFalse(receipt["ground_admitted"])
        self.assertFalse(receipt["origin_authenticated"])
        self.assertEqual(receipt["signed_by"], ["demo-22", "demo-33"])

    def test_changed_original_file_rejected(self):
        name = NAMES[0]
        with (self.folder / (name + ".json")).open("ab") as out:
            out.write(b"tampered")
        with self.assertRaises(BindingError):
            self.check()

    def test_lean_file_hash_and_length_mismatch(self):
        for field, value in (
            ("original_file_sha256", "0" * 64), ("length_bytes", 10**6),
        ):
            with self.subTest(field=field):
                old = self.lean["files"][NAMES[0]][field]
                self.lean["files"][NAMES[0]][field] = value
                with self.assertRaises(BindingError):
                    self.check()
                self.lean["files"][NAMES[0]][field] = old

    def test_semantic_disagreement_rejected(self):
        self.go["claims"][NAMES[2]]["semantic_sha256"] = "f" * 64
        with self.assertRaises(BindingError):
            self.check()

    def test_missing_or_extra_source_rejected(self):
        del self.auth["network_hashes"][NAMES[0]]
        with self.assertRaises(BindingError):
            self.check()

    def test_missing_original_certificate_rejected(self):
        (self.folder / (NAMES[0] + ".json")).unlink()
        with self.assertRaises(BindingError):
            self.check()

    def test_changed_signed_network_rejected(self):
        self.auth["network_hashes"][NAMES[3]] = "a" * 64
        with self.assertRaises(BindingError):
            self.check()

    def test_missing_lean_pass_line_rejected(self):
        self.log = "\n".join(PASS_LINE.format(name) for name in NAMES[:-1])
        with self.assertRaises(BindingError):
            self.check()

    def test_duplicate_lean_pass_line_rejected(self):
        self.log += "\n" + PASS_LINE.format(NAMES[0])
        with self.assertRaises(BindingError):
            self.check()

    def test_fake_lean_pass_line_rejected(self):
        self.log += "\nCOE-014 impostor: PASS"
        with self.assertRaises(BindingError):
            self.check()

    def test_false_origin_claim_rejected(self):
        self.auth["origin_authenticated"] = True
        with self.assertRaises(BindingError):
            self.check()

    def test_false_ground_claim_rejected(self):
        self.auth["ground_admitted"] = True
        with self.assertRaises(BindingError):
            self.check()

    def test_signer_quorum_and_identity_fail_closed(self):
        for signers, threshold in (
            (["demo-22"], 2), (["demo-22", "demo-22"], 2),
            (["demo-22", "demo-33"], 3),
        ):
            with self.subTest(signers=signers, threshold=threshold):
                self.auth["verified_signers"] = signers
                self.auth["threshold"] = threshold
                with self.assertRaises(BindingError):
                    self.check()

    def test_untrusted_production_mode_rejected(self):
        self.auth["policy_mode"] = "production"
        with self.assertRaises(BindingError):
            self.check()

    def test_lean_parser_mismatch_rejected(self):
        self.lean["parser"] = "untrusted-json-parser"
        with self.assertRaises(BindingError):
            self.check()


if __name__ == "__main__":
    unittest.main()
