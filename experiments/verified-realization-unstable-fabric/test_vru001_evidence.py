"""Standalone verification suite for VRU-001 (Verified Realization Across an Unstable Computational Fabric)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
REPO_IFS = HERE.parents[1]
VERIFIER_PY = REPO_IFS / "bridges" / "vld-independent-verifier" / "vld_standalone_verifier.py"
VERIFIER_MJS = REPO_IFS / "bridges" / "vld-independent-verifier" / "vld_standalone_verifier.mjs"
BUNDLE_PATH = HERE / "evidence" / "vru001_bundle.json"

SPEC = importlib.util.spec_from_file_location("vld_standalone_verifier", VERIFIER_PY)
assert SPEC is not None and SPEC.loader is not None
VER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VER)


class TestVRU001Evidence(unittest.TestCase):
    def test_vru001_bundle_public_key_verification_and_zero_secret_disclosure(self) -> None:
        raw_text = BUNDLE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("quorum_member_secrets", raw_text)
        self.assertNotIn("signature_hmac", raw_text)
        self.assertIn("signature_ed25519", raw_text)

        doc = json.loads(raw_text)
        self.assertEqual(doc["experiment_id"], "VRU-001")
        self.assertFalse(doc["independent_audits"]["private_keys_included_in_bundle"])

        # Numerical equivalence & crash-recovery invariants
        num = doc["numerical_equivalence"]
        self.assertTrue(num["top5_exact_agreement_with_pytorch"])
        self.assertTrue(num["local_vs_resumed_top5_exact_match"])
        self.assertLess(num["max_abs_logit_diff_vs_pytorch_fp32"], 5e-5)
        self.assertLess(num["distributed_flash_stream_max_err"], 1e-6)
        self.assertGreater(num["premature_norm_negative_control_error"], 0.1)

        topo = doc["topology_disruptions"]
        self.assertEqual(topo["alpha_exit_code"], 73)
        self.assertEqual(topo["beta_stages_recovered_without_replay"], 2)
        self.assertGreaterEqual(topo["mtls_link_drops_recovered"], 1)

        # Standalone zero-import Python verification using ONLY Ed25519 public keys
        py_res = VER.verify_continuity_chain(
            doc["receipts"],
            pipeline_id=doc["pipeline_id"],
            initial_input=doc["initial_input"],
            quorum_member_ids=doc["quorum_member_ids"],
            quorum_member_public_keys=doc["quorum_member_public_keys"],
            require_verified_tag=True,
        )
        self.assertEqual(py_res["status"], "VERIFIED")

        prec_res = VER.verify_precision_decision_bundle(doc["precision_decision_bundle"])
        self.assertEqual(prec_res["status"], "VERIFIED")
        self.assertTrue(prec_res["certified_invariant"])

        # Standalone Node.js OpenSSL Ed25519 verification
        node_bin = shutil.which("node")
        if node_bin is not None:
            node_out = json.loads(subprocess.check_output([node_bin, str(VERIFIER_MJS), str(BUNDLE_PATH)], text=True))
            self.assertEqual(node_out["status"], "VERIFIED_NODEJS")
            self.assertEqual(node_out["signature_scheme"], "ed25519-rfc8032")
            self.assertEqual(node_out["final_continuity_digest"], py_res["final_continuity_digest"])


if __name__ == "__main__":
    unittest.main()
