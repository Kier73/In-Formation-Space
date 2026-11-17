"""CGS-007 focused independent time/phase tests. No private source phase used."""
from __future__ import annotations

import copy
import datetime as dt
import sys
import unittest
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

sys.path.insert(0, str(Path(__file__).resolve().parent))
import historical_bridge as bridge


class HistoricalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.now(dt.timezone.utc)

    @staticmethod
    def metadata():
        return {
            "id": bridge.SOURCE_RUN, "head_sha": bridge.SOURCE_SHA,
            "event": "push", "head_branch": "main",
            "path": bridge.SOURCE_WORKFLOW,
            "status": "completed", "conclusion": "success",
            "run_started_at": "2026-11-14T16:38:12Z",
            "updated_at": "2026-11-14T16:54:29Z",
        }

    def test_metadata_is_pinned_to_exact_original_run_and_commit(self):
        m = self.metadata()
        t = bridge.anchored_time(m)
        self.assertEqual(t.isoformat(), "2026-11-14T16:54:29+00:00")
        for field, value in (
            ("id", 1), ("head_sha", "f"*40),
            ("event", "pull_request"), ("head_branch", "experimental"),
            ("path", "other.yml"), ("status", "queued"),
            ("conclusion", "failure"),
            ("run_started_at", "2026-11-16T00:00:00Z"),
            ("updated_at", "2026-11-16T00:00:00Z"),
        ):
            changed = copy.deepcopy(m)
            changed[field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    bridge.anchored_time(changed)

    def test_reject_malformed_or_unanchored_times(self):
        for text in ("2026-11-14T16:54:29", "2026-11-14", "bad", None,
                     "2026-11-14T16:54:29+00:00"):
            with self.subTest(value=text), self.assertRaises(ValueError):
                bridge.parse_utc(text)
        m = self.metadata()
        m["updated_at"] = "2026-11-16T16:54:29Z"
        with self.assertRaises(ValueError):
            bridge.anchored_time(m)

    @staticmethod
    def fixture_certs(before, after):
        key = ec.generate_private_key(ec.SECP256R1())
        rootname = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CGS synthetic test root")])
        ca = (x509.CertificateBuilder().subject_name(rootname)
              .issuer_name(rootname).public_key(key.public_key())
              .serial_number(x509.random_serial_number())
              .not_valid_before(before).not_valid_after(after)
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .sign(key, hashes.SHA256()))
        dns = "observer-a.cgs.example"
        leafkey = ec.generate_private_key(ec.SECP256R1())
        leafname = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns)])
        leaf = (x509.CertificateBuilder().subject_name(leafname)
                .issuer_name(rootname).public_key(leafkey.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(before).not_valid_after(after)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]), critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                               critical=False)
                .sign(key, hashes.SHA256()))
        return (leaf.public_bytes(serialization.Encoding.PEM).decode(),
                ca.public_bytes(serialization.Encoding.PEM).decode(), dns)

    def test_historical_certificate_passes_at_event_time_but_fails_now(self):
        # Expired *today*, correctly valid at source time.
        before = self.now - dt.timedelta(days=3)
        after = self.now - dt.timedelta(days=1)
        cert, ca, dns = self.fixture_certs(before, after)
        checked = bridge.c.check_cert(cert, ca, dns,
                  validation_time=self.now - dt.timedelta(days=2))
        self.assertEqual(checked.subject.rfc4514_string(), f"CN={dns}")
        with self.assertRaises(ValueError):
            bridge.c.check_cert(cert, ca, dns)
        with self.assertRaises(ValueError):
            bridge.c.check_cert(cert, ca, dns,
                       validation_time=self.now - dt.timedelta(days=4))
        with self.assertRaises(ValueError):
            bridge.c.check_cert(cert, ca, dns,
                       validation_time=self.now.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            bridge.c.check_cert(cert, ca, "forged.cgs.example",
                       validation_time=self.now - dt.timedelta(days=2))

    def test_phase_blind_honest_receipts_preserve_two_states_and_one_intention(self):
        for threshold in (0, 1):
            for parity in (0, 1):
                public = {"observer": {"value": threshold}}
                verified = {"rounds": [
                    {"verdict": "ADMITTED_AGREEMENT",
                     "peer_readings": [parity, parity]},
                    {"verdict": "REFUSED_DISAGREEMENT",
                     "peer_readings": [parity, 1-parity]},
                ]}
                rows = bridge.project_rounds(public, verified)
                self.assertEqual(rows[0]["prior_phase_count"], 4)
                self.assertEqual(len(rows[0]["admissible_phase_candidates"]), 2)
                self.assertEqual(rows[0]["allowed_intention_values"], [parity])
                self.assertTrue(rows[0]["mathematically_determined"])
                self.assertEqual(rows[1]["prior_phase_count"], 4)
                self.assertEqual(len(rows[1]["admissible_phase_candidates"]), 4)
                self.assertFalse(rows[1]["measurement_used"])
                self.assertFalse(rows[0]["current_execution_authorized"])
                self.assertFalse(rows[1]["current_execution_authorized"])

    def test_signed_disagreement_never_selects_one_observer(self):
        verified = {"rounds": [
            {"verdict": "ADMITTED_AGREEMENT", "peer_readings": [0,0]},
            {"verdict": "REFUSED_DISAGREEMENT", "peer_readings": [0,1]},
        ]}
        public = {"observer": {"value": 0}}
        changed = copy.deepcopy(verified)
        changed["rounds"][1]["verdict"] = "ADMITTED_AGREEMENT"
        with self.assertRaises(ValueError):
            bridge.project_rounds(public, changed)
        changed = copy.deepcopy(verified)
        changed["rounds"][0]["peer_readings"] = [0,1]
        with self.assertRaises(ValueError):
            bridge.project_rounds(public, changed)
        changed = copy.deepcopy(verified)
        changed["rounds"][0]["peer_readings"] = [True,True]
        with self.assertRaises(ValueError):
            bridge.project_rounds(public, changed)
        changed = copy.deepcopy(verified)
        changed["rounds"][0]["peer_readings"] = [1,1.0]
        with self.assertRaises(ValueError):
            bridge.project_rounds(public, changed)


if __name__ == "__main__":
    unittest.main()
