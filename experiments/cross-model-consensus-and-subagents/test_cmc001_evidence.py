"""Verification tests for CMC-001 (Cross-Model Relational Consensus, Pretrained Subagents & Live GitHub Pack Ground)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
REPO_IFS = HERE.parents[1]
VERIFIER_PY = REPO_IFS / "bridges" / "vld-independent-verifier" / "vld_standalone_verifier.py"
BUNDLE_PATH = HERE / "evidence" / "cmc001_bundle.json"

SPEC = importlib.util.spec_from_file_location("vld_standalone_verifier", VERIFIER_PY)
assert SPEC is not None and SPEC.loader is not None
VER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VER)


class TestCMC001Evidence(unittest.TestCase):
    def test_cmc001_pretrained_consensus_subagent_coevolution_and_live_github_pack(self) -> None:
        doc = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(doc["experiment_id"], "CMC-001")

        # 1. Cross-model relational consensus (`IDEA-005`):
        #    (a) Intra-sequence cumulative CKA exhibits RoPE positional confounding (~0.92 vs ~0.91),
        #    (b) Position-debiased cross-statement pooled Gram cleanly separates matched (0.9367, True) vs unrelated (0.7009, False)!
        cons = doc["cross_model_relational_consensus"]
        deb_matched = cons["debiased_cross_statement_matched"]
        deb_jl = cons["debiased_cross_statement_jl128"]
        deb_unrel = cons["debiased_cross_statement_unrelated_control"]
        self.assertGreater(deb_matched["linear_cka"], 0.90)
        self.assertTrue(deb_matched["exceeds_permutation_null"])
        self.assertGreater(deb_jl["linear_cka"], 0.90)
        self.assertTrue(deb_jl["exceeds_permutation_null"])
        self.assertLess(deb_unrel["linear_cka"], 0.75)
        self.assertFalse(deb_unrel["exceeds_permutation_null"])

        # 2. Live GitHub Smart HTTP v2 pack delta reduced object count & bytes while verifying root tree
        git_rec = doc["live_vld_upgrades_and_audits"]["live_github_pack_v2_delta"]
        self.assertLess(git_rec["delta_objects"], git_rec["full_closure_objects"])
        self.assertLess(git_rec["delta_pack_bytes"], git_rec["full_closure_pack_bytes"])
        self.assertEqual(len(git_rec["root_tree_oid"]), 40)

        # 3. Sheaf 1-cocycle localized exact 3 faulty drift edges
        sheaf_rec = doc["live_vld_upgrades_and_audits"]["sheaf_1cocycle_localization"]
        self.assertEqual(sheaf_rec["conflicting_edge_ids"], ["drift.34", "drift.45", "drift.53"])

        # 4. Pretrained Qwen3-0.6B + live SmolLM2-135M subagent co-evolution reached 100% acceptance in Round 1
        sub = doc["subagent_coevolution"]
        self.assertEqual(sub["final_acceptance_rate"], 1.0)
        self.assertEqual(sub["standalone_ed25519_audit"]["status"], "VERIFIED")
        self.assertEqual(sub["standalone_ed25519_audit"]["signature_scheme"], "ed25519-rfc8032")

        # Both hosted pretrained models generated orbit-checkpointed engineering notes
        models = doc["hosted_pretrained_models"]
        self.assertEqual(len(models["qwen3_0_6b"]["generated_note"]["checkpoint_digest"]), 64)
        self.assertEqual(len(models["smollm2_135m_instruct_http206"]["generated_note"]["checkpoint_digest"]), 64)
        self.assertGreater(models["smollm2_135m_instruct_http206"]["http_206_bytes"], 100_000_000)


if __name__ == "__main__":
    unittest.main()
