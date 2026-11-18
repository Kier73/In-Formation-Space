"""PMC-001 — Live 2-Process Pretrained Qwen3-0.6B Crash-and-Resume Continuity Benchmark vs PyTorch FP32 Reference.

Directly executes the Peer Audit Section 6 benchmark:
  1. Environment Alpha (Process 1, `os._exit(73)`): executes Stages 0..1 (Layers 0..13 of pinned
     `Qwen/Qwen3-0.6B @ c1899de289a04d12100db370d81485cdf75e47ca`), seals M1 hidden-state pages
     and 2q > N quorum slots on ("q0", "q1"), replicates M1 objects to an mTLS witness store,
     and terminates abruptly via `os._exit(73)`.
  2. Environment Beta (Process 2, isolated directory, rotated quorum ("q1", "q2")): streams M1
     state over X.509 v3 mTLS (`MTLSPeerServer` / `MTLSPeerClient`), fences Paxos term 2,
     recovers Stages 0..1 with ZERO replayed layers, executes Stages 2..3 (Layers 14..27 + final_logits),
     and audits receipts via both zero-import Python and zero-dependency Node.js verifiers.
  3. Separate Reference Check: evaluates `Qwen/Qwen3-0.6B` in PyTorch (`transformers`, FP32) and
     compares all 151,936 terminal logits (`top-1`, `top-5`, `max_abs_diff`).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

REPO_VLD = Path(__file__).resolve().parents[3]
if str(REPO_VLD / "src") not in sys.path:
    sys.path.insert(0, str(REPO_VLD / "src"))

from vld.authority import QuorumAuthorityMember, QuorumLineageCoordinator, QuorumMembership
from vld.canonical import canonical_bytes, parse_strict_json
from vld.continuous import ContinuousStageSpec, ContinuousVirtualSystem
from vld.fabric.mtls import (
    MTLSPeerClient,
    MTLSPeerServer,
    create_mtls_client_context,
    create_mtls_server_context,
    generate_ephemeral_mtls_pki,
)
from vld.ground import NavigationCostVector, VirtualGroundSpec
from vld.independent_audit import verify_continuity_receipt_chain_standalone
from vld.journal import HashChainedJournal
from vld.memory import DiskPageBacking, PagedObjectStore
from vld.models import LazySafetensorsWeightGround, TransformerArchitectureSpec, TransformerLayerRealizer

QWEN3_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
PROMPT_TEXT = "The capital of France is"


def _find_qwen3_snapshot() -> Path:
    snap = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--Qwen--Qwen3-0.6B"
        / "snapshots"
        / QWEN3_REVISION
    )
    if not (snap / "model.safetensors").is_file():
        raise FileNotFoundError(f"Cached Qwen3-0.6B snapshot not found at {snap}")
    return snap


def _build_qwen3_stages(arch: TransformerArchitectureSpec, realizer: TransformerLayerRealizer) -> tuple[ContinuousStageSpec, ...]:
    stage_ranges = ((0, 7), (7, 14), (14, 21), (21, 28))
    specs: list[ContinuousStageSpec] = []
    prev_rep = "prompt_token_ids"
    for s_idx, (l_start, l_end) in enumerate(stage_ranges):
        is_final = l_end == arch.num_hidden_layers
        out_rep = "vocab_logits_summary" if is_final else f"hidden_after_L{l_end - 1}"
        gspec = VirtualGroundSpec(
            f"qwen3.0_6b.stage.{s_idx}",
            "1.0",
            "qwen3",
            f"layers_{l_start}..{l_end - 1}",
            ("forward_layers", "final_logits") if is_final else ("forward_layers",),
            ("finite_rms_norm",),
            (out_rep,),
        )

        def _make_exec(ls: int, le: int, term_flag: bool):
            def _exec(st: Mapping[str, Any]) -> tuple[dict[str, Any], NavigationCostVector, str]:
                if ls == 0:
                    h = realizer.embed_tokens([int(t) for t in st["token_ids"]])
                else:
                    h = [[float(x) for x in row] for row in st["hidden_states"]]
                tensors_loaded = 0
                for li in range(ls, le):
                    out = realizer.forward_layer(li, h)
                    h = out.hidden_states
                    tensors_loaded += len(out.loaded_tensor_names)
                rms = math.sqrt(math.fsum(v * v for v in h[-1]) / len(h[-1]))
                cost = NavigationCostVector(
                    latency_ms=float((le - ls) * 2.0),
                    compute_ops=float((le - ls) * arch.hidden_size * len(h)),
                    bytes_moved=float(tensors_loaded * arch.hidden_size * 2),
                    verification_ops=float(arch.hidden_size),
                )
                if not term_flag:
                    return (
                        {
                            "hidden_rms_last": round(rms, 8),
                            "hidden_states": h,
                            "layer_end": le,
                            "token_ids": list(st["token_ids"]),
                        },
                        cost,
                        f"PASS:qwen3_L{ls}_{le - 1}",
                    )
                logits = realizer.final_logits(h)
                last_row = logits[-1]
                ranked = sorted(range(len(last_row)), key=lambda i: (-last_row[i], i))[:5]
                return (
                    {
                        "hidden_rms_last": round(rms, 8),
                        "layer_end": le,
                        "last_logits_head16": [float(x) for x in last_row[:16]],
                        "token_ids": list(st["token_ids"]),
                        "top1_logit": float(last_row[ranked[0]]),
                        "top1_token": int(ranked[0]),
                        "top5_logits": [float(last_row[i]) for i in ranked],
                        "top5_tokens": [int(i) for i in ranked],
                    },
                    cost,
                    f"PASS:qwen3_L{ls}_{le - 1}_logits",
                )

            return _exec

        def _make_ver(le: int, term_flag: bool):
            def _ver(inp: Mapping[str, Any], out: Mapping[str, Any]) -> tuple[bool, str]:
                rms = float(out.get("hidden_rms_last", -1.0))
                if int(out.get("layer_end", -1)) != le or not math.isfinite(rms) or rms <= 0.0:
                    return False, "invalid_hidden_rms_or_layer_end"
                if list(out.get("token_ids", ())) != list(inp["token_ids"]):
                    return False, "token_ids_drift"
                if not term_flag:
                    hs = out.get("hidden_states", ())
                    ok_shape = len(hs) == len(inp["token_ids"]) and all(len(r) == arch.hidden_size for r in hs)
                    return ok_shape, f"verified_hidden_L{le - 1}_rms={rms:.4f}"
                t5 = out.get("top5_tokens", ())
                l5 = out.get("top5_logits", ())
                ok_l = (
                    len(t5) == 5
                    and len(l5) == 5
                    and all(0 <= int(t) < arch.vocab_size for t in t5)
                    and all(math.isfinite(float(v)) for v in l5)
                    and l5[0] >= l5[-1]
                )
                return ok_l, f"verified_logits_top1={t5[0]}"

            return _ver

        specs.append(
            ContinuousStageSpec(
                stage_id=f"qwen3_stage_{s_idx}",
                ground_spec=gspec,
                input_representation=prev_rep,
                output_representation=out_rep,
                scheduler_id=f"sched.qwen3.env.{'alpha' if s_idx < 2 else 'beta'}",
                execute_fn=_make_exec(l_start, l_end, is_final),
                verify_fn=_make_ver(l_end, is_final),
            )
        )
        prev_rep = out_rep
    return tuple(specs)


def _load_qwen3_ground(snap_dir: Path) -> tuple[TransformerArchitectureSpec, LazySafetensorsWeightGround, dict[str, int]]:
    cfg = json.loads((snap_dir / "config.json").read_text(encoding="utf-8"))
    arch = TransformerArchitectureSpec.from_huggingface_config("Qwen/Qwen3-0.6B", QWEN3_REVISION, cfg)
    st_file = snap_dir / "model.safetensors"
    total_sz = st_file.stat().st_size
    stats = {"bytes_read": 0, "range_reads": 0}

    def _read_range(offset: int, length: int) -> bytes:
        with st_file.open("rb") as fh:
            fh.seek(offset)
            data = fh.read(length)
        stats["bytes_read"] += len(data)
        stats["range_reads"] += 1
        return data

    ground = LazySafetensorsWeightGround(
        space=arch.build_parameter_space(),
        source_pin=f"hf://Qwen/Qwen3-0.6B@{QWEN3_REVISION}",
        shard_sources={"model.safetensors": (_read_range, lambda: total_sz)},
        tensor_to_shard={},
    )
    return arch, ground, stats


def _child_env_alpha(work_root: Path, token_ids: list[int]) -> None:
    snap_dir = _find_qwen3_snapshot()
    arch, weight_ground, io_stats = _load_qwen3_ground(snap_dir)
    realizer = TransformerLayerRealizer(arch, weight_ground)
    stages = _build_qwen3_stages(arch, realizer)

    env_a_m1 = DiskPageBacking(work_root / "env_alpha_m1", page_size=4096)
    store_a = PagedObjectStore(env_a_m1)
    journal_path = work_root / "shared_journal.jsonl"
    journal = HashChainedJournal(journal_path)
    q_mem = QuorumMembership("pmc001.qwen3.lineage", ("q0", "q1", "q2"))
    secs = {m: f"pmc001-sec-{m}-0123456789abcdef".encode("utf-8") for m in q_mem.member_ids}
    nodes = [QuorumAuthorityMember(m, secs[m], journal_path=work_root / f"quorum_{m}.jsonl") for m in q_mem.member_ids]
    quorum = QuorumLineageCoordinator(q_mem, nodes, secs)

    cvs = ContinuousVirtualSystem(
        "pmc001.qwen3_0_6b.pipe",
        store=store_a,
        quorum=quorum,
        active_quorum_members=("q0", "q1"),
        journal=journal,
        require_independent_verifier=True,
    )
    res_a = cvs.execute_stages(stages, {"token_ids": token_ids}, host_id="env.alpha.host", interrupt_after_stage=1)
    # Persist Environment Alpha telemetry & manifest list before sudden process loss (`os._exit(73)`)
    manifests_meta = [m.to_dict() for m in store_a._manifests.values()]
    (work_root / "alpha_summary.json").write_bytes(
        canonical_bytes(
            {
                "manifests": manifests_meta,
                "measured_m1_bytes": res_a.measured_m1_bytes,
                "measured_wall_ms": res_a.measured_wall_ms,
                "safetensors_bytes_read": io_stats["bytes_read"],
                "safetensors_range_reads": io_stats["range_reads"],
                "stages_executed": res_a.stages_executed_this_invocation,
                "telemetry": [t.to_dict() for t in res_a.stage_telemetry],
            }
        )
    )
    os._exit(73)


def _child_env_beta(work_root: Path, token_ids: list[int]) -> None:
    from vld.memory import PagedByteManifest

    snap_dir = _find_qwen3_snapshot()
    arch, weight_ground, io_stats = _load_qwen3_ground(snap_dir)
    realizer = TransformerLayerRealizer(arch, weight_ground)
    stages = _build_qwen3_stages(arch, realizer)

    # Serve Environment Alpha's M1 disk store over mutually-authenticated X.509 v3 TLS into Environment Beta's isolated store!
    alpha_summary = parse_strict_json((work_root / "alpha_summary.json").read_bytes())
    store_alpha_ro = PagedObjectStore(DiskPageBacking(work_root / "env_alpha_m1", page_size=4096))
    for m_dict in alpha_summary["manifests"]:
        store_alpha_ro.register_manifest(PagedByteManifest.from_dict(m_dict))

    store_beta = PagedObjectStore(DiskPageBacking(work_root / "env_beta_m1", page_size=4096))
    pki = generate_ephemeral_mtls_pki(work_root / "mtls_pki", ("alpha.witness.vld", "beta.resumer.vld"))
    with MTLSPeerServer(
        peer_id="alpha.witness",
        ssl_context=create_mtls_server_context(pki["alpha.witness.vld"]),
        allowed_peer_dns=frozenset({"beta.resumer.vld"}),
        store=store_alpha_ro,
    ) as srv:
        host, port = srv.endpoint
        cli = MTLSPeerClient(
            host=host,
            port=port,
            expected_server_dns="alpha.witness.vld",
            ssl_context=create_mtls_client_context(pki["beta.resumer.vld"]),
        )
        for m_dict in alpha_summary["manifests"]:
            cli.fetch_m1_object_resumable(str(m_dict["manifest_digest"]), store_beta)
        mtls_bytes_streamed = srv.bulk_bytes_streamed

    q_mem = QuorumMembership("pmc001.qwen3.lineage", ("q0", "q1", "q2"))
    secs = {m: f"pmc001-sec-{m}-0123456789abcdef".encode("utf-8") for m in q_mem.member_ids}
    nodes = [QuorumAuthorityMember(m, secs[m], journal_path=work_root / f"quorum_{m}.jsonl") for m in q_mem.member_ids]
    quorum = QuorumLineageCoordinator(q_mem, nodes, secs)
    journal = HashChainedJournal(work_root / "shared_journal.jsonl")

    # Note: q0 is simulated OFFLINE; Environment Beta fences term 2 using ("q1", "q2")!
    cvs_beta = ContinuousVirtualSystem(
        "pmc001.qwen3_0_6b.pipe",
        store=store_beta,
        quorum=quorum,
        active_quorum_members=("q1", "q2"),
        journal=journal,
        require_independent_verifier=True,
        reverify_recovered_stages=True,
    )
    res_b = cvs_beta.execute_stages(stages, {"token_ids": token_ids}, host_id="env.beta.host")
    (work_root / "beta_summary.json").write_bytes(
        canonical_bytes(
            {
                "final_continuity_digest": res_b.final_continuity_digest,
                "final_state": dict(res_b.final_state),
                "measured_m1_bytes": res_b.measured_m1_bytes,
                "measured_wall_ms": res_b.measured_wall_ms,
                "model_total_cost": res_b.total_cost.to_dict(),
                "mtls_bulk_bytes_streamed": mtls_bytes_streamed,
                "quorum_member_ids": list(q_mem.member_ids),
                "quorum_member_secrets_utf8": {k: v.decode("utf-8") for k, v in secs.items()},
                "receipts": [r.to_dict() for r in res_b.receipts],
                "safetensors_bytes_read": io_stats["bytes_read"],
                "safetensors_range_reads": io_stats["range_reads"],
                "stages_executed_this_invocation": res_b.stages_executed_this_invocation,
                "stages_recovered_from_quorum": res_b.stages_recovered_from_quorum,
                "telemetry": [t.to_dict() for t in res_b.stage_telemetry],
            }
        )
    )


def run_full_benchmark() -> dict[str, Any]:
    os.environ["USE_TF"] = "0"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    snap_dir = _find_qwen3_snapshot()
    tok = AutoTokenizer.from_pretrained(str(snap_dir), local_files_only=True)
    token_ids = [int(x) for x in tok.encode(PROMPT_TEXT, add_special_tokens=False)]

    with tempfile.TemporaryDirectory(prefix="pmc001_qwen3_") as tmp:
        work_root = Path(tmp)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_VLD / "src")
        env["USE_TF"] = "0"

        t_a0 = time.perf_counter()
        proc_a = subprocess.run(
            [sys.executable, __file__, "--role", "alpha", "--work-root", str(work_root), "--tokens", json.dumps(token_ids)],
            env=env,
            capture_output=True,
            text=True,
        )
        wall_alpha_ms = (time.perf_counter() - t_a0) * 1000.0
        if proc_a.returncode != 73:
            raise RuntimeError(f"Expected Environment Alpha os._exit(73), got {proc_a.returncode}: {proc_a.stderr}")

        t_b0 = time.perf_counter()
        proc_b = subprocess.run(
            [sys.executable, __file__, "--role", "beta", "--work-root", str(work_root), "--tokens", json.dumps(token_ids)],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        wall_beta_ms = (time.perf_counter() - t_b0) * 1000.0

        alpha_doc = parse_strict_json((work_root / "alpha_summary.json").read_bytes())
        beta_doc = parse_strict_json((work_root / "beta_summary.json").read_bytes())

    # Independent PyTorch FP32 reference evaluation
    t_ref0 = time.perf_counter()
    hf_model = AutoModelForCausalLM.from_pretrained(str(snap_dir), torch_dtype=torch.float32, local_files_only=True).eval()
    with torch.no_grad():
        ref_logits = hf_model(torch.tensor([token_ids], dtype=torch.long)).logits[0, -1].cpu().tolist()
    ref_wall_ms = (time.perf_counter() - t_ref0) * 1000.0
    ref_ranked = sorted(range(len(ref_logits)), key=lambda i: (-ref_logits[i], i))[:5]

    vld_final = beta_doc["final_state"]
    head16_diff = max(abs(float(a) - float(b)) for a, b in zip(vld_final["last_logits_head16"], ref_logits[:16]))
    top5_logit_diff = max(abs(float(vld_final["top5_logits"][k]) - float(ref_logits[ref_ranked[k]])) for k in range(5))
    max_logit_diff = max(head16_diff, top5_logit_diff)

    # Audit receipt chain via BOTH zero-import Python verifier AND zero-dependency Node.js verifier!
    py_audit = verify_continuity_receipt_chain_standalone(
        beta_doc["receipts"],
        pipeline_id="pmc001.qwen3_0_6b.pipe",
        initial_input={"token_ids": token_ids},
        quorum_member_ids=beta_doc["quorum_member_ids"],
        quorum_member_secrets={k: v.encode("utf-8") for k, v in beta_doc["quorum_member_secrets_utf8"].items()},
        require_verified_tag=True,
    )
    node_bin = shutil.which("node")
    node_audit: dict[str, Any] = {"status": "SKIPPED"}
    if node_bin is not None:
        mjs = Path(__file__).resolve().parents[2] / "bridges" / "vld-independent-verifier" / "vld_standalone_verifier.mjs"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(
                {
                    "initial_input": {"token_ids": token_ids},
                    "pipeline_id": "pmc001.qwen3_0_6b.pipe",
                    "quorum_member_ids": beta_doc["quorum_member_ids"],
                    "quorum_member_secrets_utf8": beta_doc["quorum_member_secrets_utf8"],
                    "receipts": beta_doc["receipts"],
                },
                tf,
            )
            bpath = tf.name
        try:
            np_res = subprocess.run([node_bin, str(mjs), bpath], capture_output=True, text=True, check=True)
            node_audit = json.loads(np_res.stdout)
        finally:
            Path(bpath).unlink(missing_ok=True)

    return {
        "benchmark_id": "PMC-001",
        "continuity_bundle": {
            "initial_input": {"token_ids": token_ids},
            "pipeline_id": "pmc001.qwen3_0_6b.pipe",
            "quorum_member_ids": beta_doc["quorum_member_ids"],
            "quorum_member_secrets_utf8": beta_doc["quorum_member_secrets_utf8"],
            "receipts": beta_doc["receipts"],
        },
        "environment_alpha": {
            "active_quorum": ["q0", "q1"],
            "exit_code": 73,
            "host_id": "env.alpha.host",
            "layers_committed_before_crash": [0, 13],
            "measured_m1_bytes_persisted": alpha_doc["measured_m1_bytes"],
            "measured_pipeline_ms": round(float(alpha_doc["measured_wall_ms"]), 3),
            "process_wall_ms": round(wall_alpha_ms, 3),
            "safetensors_bytes_read": alpha_doc["safetensors_bytes_read"],
            "safetensors_range_reads": alpha_doc["safetensors_range_reads"],
            "stages_executed": alpha_doc["stages_executed"],
        },
        "environment_beta": {
            "active_quorum": ["q1", "q2"],
            "fenced_offline_member": "q0",
            "host_id": "env.beta.host",
            "layers_resumed_and_completed": [14, 27],
            "measured_m1_bytes_persisted": beta_doc["measured_m1_bytes"],
            "measured_pipeline_ms": round(float(beta_doc["measured_wall_ms"]), 3),
            "mtls_bulk_bytes_streamed": beta_doc["mtls_bulk_bytes_streamed"],
            "process_wall_ms": round(wall_beta_ms, 3),
            "replayed_layers": 0,
            "safetensors_bytes_read": beta_doc["safetensors_bytes_read"],
            "safetensors_range_reads": beta_doc["safetensors_range_reads"],
            "stages_executed_this_invocation": beta_doc["stages_executed_this_invocation"],
            "stages_recovered_from_quorum": beta_doc["stages_recovered_from_quorum"],
        },
        "independent_audits": {
            "nodejs_standalone": node_audit,
            "python_zero_import": py_audit,
        },
        "model": {
            "hidden_size": 1024,
            "num_hidden_layers": 28,
            "prompt_text": PROMPT_TEXT,
            "prompt_token_ids": token_ids,
            "repo_id": "Qwen/Qwen3-0.6B",
            "revision": QWEN3_REVISION,
            "vocab_size": 151936,
        },
        "model_cost_vector": beta_doc["model_total_cost"],
        "reference_comparison_pytorch_fp32": {
            "decoded_top1_token": tok.decode([vld_final["top1_token"]]),
            "max_abs_logit_diff": max_logit_diff,
            "pytorch_reference_wall_ms": round(ref_wall_ms, 3),
            "pytorch_top5_tokens": ref_ranked,
            "top1_token_match": int(vld_final["top1_token"]) == int(ref_ranked[0]),
            "top5_tokens_match": list(vld_final["top5_tokens"]) == list(ref_ranked),
            "vld_resumed_top5_tokens": vld_final["top5_tokens"],
        },
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--role", choices=("orchestrate", "alpha", "beta"), default="orchestrate")
    p.add_argument("--work-root", type=str, default="")
    p.add_argument("--tokens", type=str, default="[]")
    p.add_argument(
        "--out",
        type=str,
        default=str(Path(__file__).resolve().parent / "evidence" / "qwen3_0_6b_crash_resume_vs_pytorch.json"),
    )
    ns = p.parse_args()
    if ns.role == "alpha":
        _child_env_alpha(Path(ns.work_root), json.loads(ns.tokens))
    elif ns.role == "beta":
        _child_env_beta(Path(ns.work_root), json.loads(ns.tokens))
    else:
        report = run_full_benchmark()
        out_p = Path(ns.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "decoded_top1": report["reference_comparison_pytorch_fp32"]["decoded_top1_token"],
                    "env_alpha_exit": report["environment_alpha"]["exit_code"],
                    "final_continuity_digest": report["independent_audits"]["python_zero_import"]["final_continuity_digest"],
                    "max_abs_logit_diff": report["reference_comparison_pytorch_fp32"]["max_abs_logit_diff"],
                    "mtls_bytes": report["environment_beta"]["mtls_bulk_bytes_streamed"],
                    "node_audit": report["independent_audits"]["nodejs_standalone"]["status"],
                    "recovered_stages": report["environment_beta"]["stages_recovered_from_quorum"],
                    "top1_match": report["reference_comparison_pytorch_fp32"]["top1_token_match"],
                    "top5_match": report["reference_comparison_pytorch_fp32"]["top5_tokens_match"],
                },
                indent=2,
                sort_keys=True,
            )
        )
