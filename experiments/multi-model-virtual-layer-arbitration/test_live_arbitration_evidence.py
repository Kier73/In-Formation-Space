"""Integrity & schema verification test for recorded MVA-001 7-model arbitration evidence."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class TestLiveArbitrationEvidence(unittest.TestCase):
    def test_7model_campaign_evidence_structure_and_digests(self) -> None:
        doc = json.loads((HERE / "evidence" / "live_7model_campaign.json").read_text(encoding="utf-8"))

        # 1. Recursive arbitration & standalone audit record
        arb = doc["arbitration_and_audit"]
        self.assertRegex(arb["arbitrator_capsule_digest"], HEX64)
        self.assertRegex(arb["final_continuity_digest"], HEX64)
        self.assertRegex(arb["encounter_envelope_digest"], HEX64)
        self.assertEqual(arb["standalone_audit"]["status"], "VERIFIED")
        self.assertEqual(arb["standalone_audit"]["stages_verified"], 5)
        self.assertEqual(arb["standalone_audit"]["final_continuity_digest"], arb["final_continuity_digest"])
        self.assertIn("in_layer.frontier_sub_arbitrator", arb["selected_workers"])

        # 2. Full-model autoregressive generations (SmolLM2-135M 30-layer live & Qwen3-0.6B 28-layer local)
        smol = doc["smollm2_135m_live_30layer"]
        self.assertRegex(smol["revision"], HEX40)
        self.assertRegex(smol["final_checkpoint_digest"], HEX64)
        self.assertEqual(len(smol["generated_ids"]), 12)
        self.assertTrue(smol["full_text"].startswith(smol["prompt"]))

        q3 = doc["qwen3_0_6b_local_28layer"]
        self.assertRegex(q3["revision"], HEX40)
        self.assertRegex(q3["final_checkpoint_digest"], HEX64)
        self.assertEqual(len(q3["generated_ids"]), 12)

        # 3. Live Layer-0 range realizations (DeepSeek-R1-Distill-Qwen-1.5B & GLM-Z1-9B-0414)
        dsr1 = doc["deepseek_r1_distill_qwen_1_5b_l0"]
        self.assertLess(dsr1["checkpoint_fraction_pct"], 5.0)
        self.assertEqual(len(dsr1["layer0_last_head8"]), 8)

        glmz1 = doc["glm_z1_9b_0414_l0"]
        self.assertLess(glmz1["checkpoint_fraction_pct"], 5.0)
        self.assertEqual(len(glmz1["layer0_last_head8"]), 8)

        # 4. Frontier MoE glances
        gl = doc["live_frontier_glances"]
        self.assertEqual(gl["deepseek_v41_flash"]["kv_compression_factor"], 128.0)
        self.assertAlmostEqual(gl["glm_53_bf16"]["kv_compression_factor"], 56.888889, places=4)
        self.assertEqual(gl["qwen3_30b_a3b"]["routed_experts"], 128)


if __name__ == "__main__":
    unittest.main()
