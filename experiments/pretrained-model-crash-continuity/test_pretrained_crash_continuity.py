"""Self-contained verification suite for Pretrained Model Crash-and-Resume Continuity (PMC-001).

Exercises:
  1. Real child-process `os._exit(73)` crash mid-model and isolated replacement-process resumption
     against a separately implemented scalar FP64 reference (zero external dependencies).
  2. Cryptographic & numerical audit of the recorded 28-layer `Qwen/Qwen3-0.6B` (`c1899de...`)
     two-environment crash-and-resume evidence against PyTorch FP32 using both Python and Node.js
     standalone verifiers.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
VER_DIR = HERE.parents[1] / "bridges" / "vld-independent-verifier"
SPEC = importlib.util.spec_from_file_location("vld_standalone_verifier", VER_DIR / "vld_standalone_verifier.py")
assert SPEC is not None and SPEC.loader is not None
VER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VER)


def _compact_layer_step(vec: list[float], layer_idx: int) -> list[float]:
    d = len(vec)
    rms = math.sqrt(sum(v * v for v in vec) / d + 1e-6)
    normed = [v / rms for v in vec]
    out = []
    for o in range(d):
        proj = sum(normed[i] * math.sin((layer_idx + 1) * 0.7 + (o + 1) * 0.3 + i * 0.5) * 0.25 for i in range(d))
        gate = proj / (1.0 + math.exp(-proj))
        out.append(vec[o] + gate)
    return out


def _independent_fp64_reference(seed_tokens: list[int], num_layers: int = 4, dim: int = 8) -> list[float]:
    h = [math.cos(sum(seed_tokens) * 0.13 + j * 0.41) for j in range(dim)]
    for li in range(num_layers):
        h = _compact_layer_step(h, li)
    return [sum(h[j] * ((v + j + 1) * 0.05) for j in range(dim)) for v in range(6)]


def _subprocess_worker(role: str, state_dir: Path) -> None:
    tokens = [3, 7, 11]
    dim = 8
    ckpt_file = state_dir / "committed_stage_1.json"
    if role == "crash_alpha":
        h = [math.cos(sum(tokens) * 0.13 + j * 0.41) for j in range(dim)]
        for li in (0, 1):
            h = _compact_layer_step(h, li)
        payload = {
            "genesis_digest": hashlib.sha256(json.dumps(tokens).encode("utf-8")).hexdigest(),
            "hidden": h,
            "layers_done": 2,
        }
        ckpt_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os._exit(73)
    elif role == "resume_beta":
        saved = json.loads(ckpt_file.read_text(encoding="utf-8"))
        exp_gen = hashlib.sha256(json.dumps(tokens).encode("utf-8")).hexdigest()
        if saved["genesis_digest"] != exp_gen or saved["layers_done"] != 2:
            raise RuntimeError("Genesis or stage boundary mismatch on recovery.")
        h = [float(x) for x in saved["hidden"]]
        for li in (2, 3):
            h = _compact_layer_step(h, li)
        logits = [sum(h[j] * ((v + j + 1) * 0.05) for j in range(dim)) for v in range(6)]
        (state_dir / "resumed_logits.json").write_text(json.dumps({"logits": logits, "replayed_layers": 0}), encoding="utf-8")


class TestPretrainedModelCrashContinuity(unittest.TestCase):
    def test_real_child_process_os_exit_73_and_isolated_resumption(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pmc001_unit_") as tmp:
            sdir = Path(tmp)
            p_alpha = subprocess.run([sys.executable, __file__, "--worker-role", "crash_alpha", "--state-dir", str(sdir)])
            self.assertEqual(p_alpha.returncode, 73)

            p_beta = subprocess.run(
                [sys.executable, __file__, "--worker-role", "resume_beta", "--state-dir", str(sdir)],
                check=True,
            )
            self.assertEqual(p_beta.returncode, 0)
            res = json.loads((sdir / "resumed_logits.json").read_text(encoding="utf-8"))
            ref = _independent_fp64_reference([3, 7, 11])
            self.assertEqual(res["replayed_layers"], 0)
            for a, b in zip(res["logits"], ref):
                self.assertAlmostEqual(a, b, places=12)

    def test_recorded_qwen3_0_6b_crash_resume_evidence_and_cross_language_audit(self) -> None:
        ev_path = HERE / "evidence" / "qwen3_0_6b_crash_resume_vs_pytorch.json"
        doc = json.loads(ev_path.read_text(encoding="utf-8"))

        self.assertEqual(doc["benchmark_id"], "PMC-001")
        self.assertEqual(doc["model"]["repo_id"], "Qwen/Qwen3-0.6B")
        self.assertEqual(doc["model"]["revision"], "c1899de289a04d12100db370d81485cdf75e47ca")
        self.assertEqual(doc["environment_alpha"]["exit_code"], 73)
        self.assertEqual(doc["environment_beta"]["stages_recovered_from_quorum"], 2)
        self.assertEqual(doc["environment_beta"]["stages_executed_this_invocation"], 2)
        self.assertEqual(doc["environment_beta"]["replayed_layers"], 0)
        self.assertGreater(doc["environment_beta"]["mtls_bulk_bytes_streamed"], 0)

        ref_cmp = doc["reference_comparison_pytorch_fp32"]
        self.assertTrue(ref_cmp["top1_token_match"])
        self.assertTrue(ref_cmp["top5_tokens_match"])
        self.assertLess(ref_cmp["max_abs_logit_diff"], 5e-4)

        bundle = doc["continuity_bundle"]
        sec_bytes = {k: v.encode("utf-8") for k, v in bundle["quorum_member_secrets_utf8"].items()}
        py_res = VER.verify_continuity_chain(
            bundle["receipts"],
            pipeline_id=bundle["pipeline_id"],
            initial_input=bundle["initial_input"],
            quorum_member_ids=bundle["quorum_member_ids"],
            quorum_member_secrets=sec_bytes,
            require_verified_tag=True,
        )
        self.assertEqual(py_res["status"], "VERIFIED")
        self.assertEqual(py_res["stages_verified"], 4)

        node_bin = shutil.which("node")
        if node_bin is not None:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
                json.dump(bundle, tf)
                b_file = tf.name
            try:
                proc = subprocess.run(
                    [node_bin, str(VER_DIR / "vld_standalone_verifier.mjs"), b_file],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                node_res = json.loads(proc.stdout)
                self.assertEqual(node_res["status"], "VERIFIED_NODEJS")
                self.assertEqual(node_res["final_continuity_digest"], py_res["final_continuity_digest"])
            finally:
                Path(b_file).unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker-role":
        _subprocess_worker(sys.argv[2], Path(sys.argv[4]))
    else:
        unittest.main()
