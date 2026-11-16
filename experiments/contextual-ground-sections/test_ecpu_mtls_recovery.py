"""CGS-010: hard-killed owner/receiver, remote E-CPU mTLS authority services.

Reuses E-CPU's own pinned test *service launcher and certificate fixtures*.
The actual coordinator, TLS, journals, durability and quorum live inside the
installed E-CPU package. Each test uses real subprocesses and TCP sockets.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WORKER = HERE / "ecpu_mtls_recovery.py"
NODE_DEMO = HERE / "demo_authority.js"
ECPU_TEST = ROOT / "external" / "E-CPU" / "tests" / "test_recovery_lineage_service.py"

sys.path.insert(0, str(HERE))
import ecpu_mtls_recovery as bridge


def import_service_fixture():
    spec = importlib.util.spec_from_file_location(
        "_cgs010_pinned_ecpu_service_fixture", ECPU_TEST)
    if spec is None or spec.loader is None:
        raise RuntimeError("pinned original E-CPU service test helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(ECPU_TEST.exists() and shutil.which("openssl") and
                     shutil.which("node"),
                     "requires pinned E-CPU checkout, OpenSSL and Node")
class RealECPUHardkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cgs010-mtls-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.fixture = import_service_fixture()
        self.bundle = self.base / "source.json"
        with self.bundle.open("wb") as output:
            subprocess.run(["node", str(NODE_DEMO)],
                           stdout=output, stderr=subprocess.PIPE,
                           check=True, timeout=30)
        source = bridge.existing.load_bundle(self.bundle)
        self.trust = self.base / "provisioned-trust.json"
        self.trust.write_bytes(bridge.existing.canonical(source["trust"]))
        self.membership = bridge.membership_for(source["trust"])
        self.certificates = self.fixture._make_certificates(self.base)
        self.archive = self.base / "external-content-archive"
        self.owner_journal = self.base / "owner-authority" / "A.jsonl"
        self.endpoints_path = self.base / "authenticated-endpoints.json"
        self.services = {}
        self.endpoints = {}
        self._start_service("B")
        self._start_service("C")
        self._write_endpoints()

    def _start_service(self, member):
        proc, ready = self.fixture._start_member(
            self.base, self.membership, self.certificates, member)
        self.services[member] = proc
        self.endpoints[member] = {
            "host": "127.0.0.1", "port": ready["port"],
            "dns": bridge.DNS[member],
        }
        self.addCleanup(self.fixture._stop, proc)

    def _write_endpoints(self):
        self.endpoints_path.write_bytes(
            bridge.existing.canonical(self.endpoints))

    def _args(self, command):
        return [
            sys.executable, str(WORKER), command,
            "--archive", str(self.archive),
            "--trust", str(self.trust),
            "--owner-journal", str(self.owner_journal),
            "--tls-dir", str(self.base),
            "--endpoints", str(self.endpoints_path),
        ]

    def _run(self, command, *, ok=True, extra=()):
        cmd = self._args(command) + list(extra)
        if command == "seal-two":
            cmd += ["--bundle", str(self.bundle)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=55)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stderr

    def _seal_and_hard_kill(self):
        ready = self.base / "temporary-owner-readiness.json"
        command = self._args("seal-two") + [
            "--bundle", str(self.bundle), "--ready-file", str(ready),
            "--hard-kill-ready"]
        original = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.fixture._stop, original)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and not ready.exists():
            if original.poll() is not None:
                out, err = original.communicate(timeout=2)
                self.fail("owner died before publishing quorum proof: "
                          + err + out)
            time.sleep(.04)
        self.assertTrue(ready.exists(), "quorum-sealed readiness never appeared")
        self.assertIsNone(original.poll())
        reports = json.loads(ready.read_text())
        self.assertEqual(len(reports["sealed"]), 2)
        self.assertEqual(reports["sealed"][1]["generation"], 2)
        self.assertEqual(
            reports["sealed"][1]["decision_members"], ["A", "B", "C"])
        original.kill()  # hard OS process kill, not graceful close or exception
        original.communicate(timeout=6)
        self.assertNotEqual(original.returncode, 0)
        ready.unlink()
        self.assertFalse(ready.exists())
        return reports

    def test_replacement_discovers_highwater_without_original_local_checkpoint(self):
        sealed = self._seal_and_hard_kill()
        result = self._run("recover")  # NO --bundle and NO --generation
        self.assertEqual(result["generation"], 2)
        self.assertEqual(
            result["manifest_root"], sealed["sealed"][1]["manifest_root"])
        self.assertEqual(result["receiver_counter"], 2)
        self.assertEqual(result["policy_version"], 2)
        self.assertTrue(result["state_selected_from_quorum_not_local_checkpoint"])
        self.assertTrue(result["source_ed25519_verified"])
        self.assertTrue(result["requires_fresh_challenge"])
        self.assertFalse(result["current_execution_authorized"])

    def test_fully_authentic_older_manifest_cannot_override_quorum_root(self):
        sealed = self._seal_and_hard_kill()
        old = sealed["sealed"][0]["manifest_root"]
        self.assertTrue(bridge.stored_path(
            self.archive, "manifests", old).is_file())
        failure = self._run("recover", ok=False,
                            extra=("--candidate-hint", old))
        self.assertIn("superseded", failure.lower())
        self.assertEqual(self._run("recover")["generation"], 2)

    def test_authentic_quorum_cannot_recover_missing_archived_state_bytes(self):
        sealed = self._seal_and_hard_kill()
        address = sealed["sealed"][1]["state_digest"]
        state_path = bridge.stored_path(self.archive, "objects", address)
        state_path.unlink()
        failure = self._run("recover", ok=False)
        self.assertIn("no such file", failure.lower())

    def test_mutated_state_and_resealed_archive_are_refused(self):
        sealed = self._seal_and_hard_kill()
        address = sealed["sealed"][1]["state_digest"]
        state_path = bridge.stored_path(self.archive, "objects", address)
        raw = state_path.read_bytes()
        self.assertIn(b'"current_execution_authorized":false', raw)
        state_path.write_bytes(
            raw.replace(b'"current_execution_authorized":false',
                        b'"current_execution_authorized":true'))
        failure = self._run("recover", ok=False)
        self.assertIn("digest", failure.lower())
        state_path.write_bytes(raw)
        self.assertEqual(self._run("recover")["generation"], 2)

    def test_separately_hosted_authority_process_restarts_own_journal(self):
        sealed = self._seal_and_hard_kill()
        self.fixture._stop(self.services["B"])
        self._start_service("B")
        self._write_endpoints()
        outcome = self._run("recover")
        self.assertEqual(outcome["generation"], 2)
        self.assertEqual(
            outcome["manifest_root"], sealed["sealed"][1]["manifest_root"])

    def test_quorum_access_fails_closed_when_services_are_offline(self):
        self._seal_and_hard_kill()
        self.fixture._stop(self.services["B"])
        self.fixture._stop(self.services["C"])
        failure = self._run("recover", ok=False)
        self.assertTrue("authority" in failure.lower() or
                        "connect" in failure.lower())

    def test_wrong_authority_dns_identity_refused_by_real_mtls(self):
        self._seal_and_hard_kill()
        self.endpoints["B"]["port"] = self.endpoints["C"]["port"]
        self._write_endpoints()
        failure = self._run("recover", ok=False)
        self.assertTrue("certificate" in failure.lower() or
                        "tls" in failure.lower() or "authority" in failure.lower())

    def test_receiver_trust_bootstrap_substitution_refused(self):
        self._seal_and_hard_kill()
        trusted = json.loads(self.trust.read_text())
        trusted["realm"] = "different-owner-realm"
        self.trust.write_bytes(bridge.existing.canonical(trusted))
        failure = self._run("recover", ok=False)
        self.assertTrue("membership" in failure.lower() or
                        "authority" in failure.lower() or
                        "digest" in failure.lower())

    def test_old_observer_remains_revoked_despite_recovery(self):
        self._seal_and_hard_kill()
        outcome = self._run("recover")
        self.assertEqual(outcome["generation"], 2)
        src_dir = self.archive / "sources"
        names = list(src_dir.glob("*.json"))
        self.assertEqual(len(names), 1)
        bundle = json.loads(names[0].read_bytes())
        policy2 = bundle["policies"][1]["body"]
        self.assertIn("bob", policy2["revoked"])
        self.assertNotIn("bob", {g["observer"] for g in policy2["grants"]})
        self.assertFalse(outcome["current_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
