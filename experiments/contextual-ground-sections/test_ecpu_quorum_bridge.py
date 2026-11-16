"""CGS-009: real E-CPU quorum/CGS-008 signed checkpoint tests.

Each CLI stage is a distinct OS process; persistent E-CPU journals are
reopened. No in-memory fake quorum participates in these tests.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT / "ecpu_quorum_bridge.py"
DEMO = ROOT / "demo_authority.js"


class CGS009QuorumRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.space = tempfile.TemporaryDirectory(prefix="cgs009-")
        self.addCleanup(self.space.cleanup)
        self.root = Path(self.space.name)
        self.bundle = self.root / "public-bundle.json"
        self.workspace = self.root / "durable"
        with self.bundle.open("wb") as output:
            subprocess.run(["node", str(DEMO)], check=True, stdout=output,
                           timeout=40)

    def command(self, action: str, generation: int = 0,
                members: tuple[str, ...] = ("anchor-A", "anchor-B", "anchor-C"),
                success: bool = True):
        args = [sys.executable, str(BRIDGE), action, "--bundle", str(self.bundle),
                "--workspace", str(self.workspace), "--generation", str(generation),
                "--members", *members]
        run = subprocess.run(args, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, timeout=60)
        if success:
            self.assertEqual(run.returncode, 0, run.stderr)
            return json.loads(run.stdout)
        self.assertNotEqual(run.returncode, 0, run.stdout)
        return run.stderr

    def test_real_quorum_seal_two_generations_recover_latest_after_process_exit(self):
        first = self.command("seal", 1)
        self.assertEqual(first["decision_members"],
                         ["anchor-A", "anchor-B", "anchor-C"])
        self.assertEqual(first["generation"], 1)
        self.assertEqual(self.command("high-water")["generation"], 1)
        self.command("seal", 2)
        self.assertEqual(self.command("high-water")["generation"], 2)
        restored = self.command("recover", 2)
        self.assertEqual(restored["recovered_checkpoint_counter"], 2)
        self.assertEqual(restored["recovered_policy_version"], 2)
        self.assertTrue(restored["requires_new_challenge"])
        self.assertFalse(restored["current_execution_authorized"])

    def test_genuine_older_signed_state_is_refused_after_higher_quorum_seal(self):
        self.command("seal", 1)
        self.command("seal", 2)
        # Old signature remains valid and old state bytes remain intact.
        error = self.command("recover", 1, success=False)
        self.assertIn("stale", error.lower())

    def test_one_authority_cannot_pretend_to_have_majority_read_quorum(self):
        self.command("seal", 1)
        error = self.command("recover", 1, ("anchor-A",), success=False)
        self.assertIn("quorum", error.lower())

    def test_minority_prepare_can_be_completed_by_exact_retry(self):
        first_error = self.command("seal", 1, ("anchor-A",), success=False)
        self.assertIn("quorum", first_error.lower())
        accepted = self.command("seal", 1, ("anchor-A", "anchor-B"))
        self.assertEqual(accepted["decision_members"], ["anchor-A", "anchor-B"])
        self.assertEqual(self.command("recover", 1, ("anchor-A", "anchor-B"))
                         ["generation"], 1)

    def test_tampered_state_and_manifest_do_not_recover(self):
        self.command("seal", 1)
        state = self.workspace / "state-1.json"
        original = state.read_bytes()
        state.write_bytes(original.replace(b'"current_execution_authorized":false',
                                           b'"current_execution_authorized":true'))
        error = self.command("recover", 1, success=False)
        self.assertIn("digest", error.lower())
        state.write_bytes(original)
        self.assertEqual(self.command("recover", 1)["generation"], 1)
        manifest_path = self.workspace / "manifest-1.json"
        record = json.loads(manifest_path.read_text())
        record["state_digest"] = "f" * 64
        manifest_path.write_text(json.dumps(record))
        error = self.command("recover", 1, success=False)
        self.assertIn("digest", error.lower())

    def test_source_policy_tampering_refused_even_with_unchanged_quorum(self):
        self.command("seal", 1)
        bundle = json.loads(self.bundle.read_text())
        bundle["policies"][0]["body"]["expires"] += 1
        self.bundle.write_text(json.dumps(bundle))
        error = self.command("recover", 1, success=False)
        self.assertTrue("signature" in error.lower() or "refused" in error.lower())

    def test_same_generation_rival_and_generation_skips_refused(self):
        self.command("seal", 1)
        self.assertIn("generation", self.command("seal", 1, success=False).lower())
        # A new generation cannot be skipped and must bind its predecessor.
        empty_workspace = self.root / "another"
        saved = self.workspace
        self.workspace = empty_workspace
        try:
            self.assertIn("generation", self.command("seal", 2, success=False).lower())
        finally:
            self.workspace = saved

    def test_closed_new_generation_does_not_reauthorize_revoked_old_observer(self):
        self.command("seal", 1)
        self.command("seal", 2)
        result = self.command("recover", 2)
        self.assertEqual(result["recovered_policy_version"], 2)
        self.assertFalse(result["current_execution_authorized"])
        self.assertNotEqual(result["receipt_digest"], "0" * 64)


if __name__ == "__main__":
    unittest.main()
