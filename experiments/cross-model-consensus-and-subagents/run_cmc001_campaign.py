r"""CMC-001 — Live Pretrained Cross-Model Relational Consensus (`IDEA-005`), Hosted Subagent Co-Evolution & Live GitHub Graph Ground (`IDEA-010`).

Executes authentic Virtual-Layer-hosted pretrained models + live Internet infrastructure:
  1. **Subagent 1 (`Qwen/Qwen3-0.6B`, 28 layers, $d=1024$):** Local Safetensors + M1 `PagedKVCacheGround`.
  2. **Subagent 2 (`HuggingFaceTB/SmolLM2-135M-Instruct`, 30 layers, $d=576$):** Streamed live over
     HTTPS `206` Range from Hugging Face Hub into M1 pages.
  3. **Model 3 (`deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B`, Layer 0..1, $d=1536$):** Streamed live over
     HTTPS `206` Range for 3-architecture cross-dimension relational CKA comparison.
  4. **Boundary-Anchored Relational Consensus (`IDEA-005`):** Evaluates cumulative hidden states across 8
     shared semantic clause boundaries (eliminating BPE length mismatch across distinct vocabularies),
     comparing matched trajectories vs unrelated-topic & permutation-null negative controls.
  5. **Closed-Loop Hosted Subagent Development (`DirectedSubagentDevelopmentLoop`):** Directs `Qwen3-0.6B`
     and live `SmolLM2-135M-Instruct` across 2 rounds to assist in:
     - `IntentionToRealizationCompiler` $10^{12}+7$ orbit compilation vs 3-sample decoy refusal,
     - Qualifying **live GitHub Smart HTTP v2** (`https://github.com/Kier73/Virtual-Layer-Dynamics.git`)
       Merkle-DAG set-difference vs `ignore_have` negative control,
     - Isolating a faulty 3-edge observer holonomy loop via `CellularSheaf` (`IDEA-006`).
"""

from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Sequence

REPO_VLD = Path(__file__).resolve().parents[3]
if str(REPO_VLD / "src") not in sys.path:
    sys.path.insert(0, str(REPO_VLD / "src"))

from vld.agents import (
    ContinuousLayerBuilderAgent,
    DirectedSubagentDevelopmentLoop,
    HostedModelSubagent,
    ReceiverHypervisor,
    SubagentEngineeringTask,
    SubagentProposalOption,
    create_subagent_grant,
)
from vld.compiler import (
    AuthorityPolicy,
    IntentExpr,
    IntentionSpec,
    IntentionToRealizationCompiler,
    ObservationContract,
)
from vld.memory import InMemoryPageBacking, PagedObjectStore
from vld.models import (
    CenteredGramRelationalSketch,
    HuggingFaceBPETokenizerGround,
    LazySafetensorsWeightGround,
    TransformerArchitectureSpec,
    TransformerLayerRealizer,
    compare_relational_sketches,
)
from vld.navigation import CellularSheaf
from vld.substrates import (
    GitPackGraphGround,
    GitSmartHTTPFixtureServer,
)

QWEN3_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"


def _boundary_hidden_trajectory(
    clauses: Sequence[str],
    tok: HuggingFaceBPETokenizerGround,
    realizer: TransformerLayerRealizer,
    *,
    num_layers: int,
) -> list[list[float]]:
    """Extract hidden state at the terminal subword of each cumulative semantic clause $c_1 \\dots c_k$."""
    full_ids: list[int] = []
    end_indices: list[int] = []
    for idx, cl in enumerate(clauses):
        piece = cl if idx == 0 else (" " + cl)
        sub_ids = list(tok.encode(piece))
        if not sub_ids:
            continue
        full_ids.extend(sub_ids)
        end_indices.append(len(full_ids) - 1)

    h = realizer.embed_tokens(full_ids)
    for li in range(num_layers):
        h = realizer.forward_layer(li, h).hidden_states
    return [list(h[pos]) for pos in end_indices]


def run_cmc001() -> dict[str, Any]:
    t0_total = time.perf_counter()

    # 1. Load Local 28-Layer Qwen3-0.6B
    qwen_snap = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--Qwen--Qwen3-0.6B"
        / "snapshots"
        / QWEN3_REVISION
    )
    q3_arch = TransformerArchitectureSpec.from_published_profile("qwen3-0.6b")
    q3_tok = HuggingFaceBPETokenizerGround.from_file(qwen_snap / "tokenizer.json")
    q3_store = PagedObjectStore(InMemoryPageBacking(65536))
    q3_wg = LazySafetensorsWeightGround.from_local_checkpoint(qwen_snap, arch=q3_arch, cache_store=q3_store)

    # 2. Stream Live 30-Layer SmolLM2-135M-Instruct Over HTTPS 206 Range!
    t0_smol = time.perf_counter()
    smol_arch = TransformerArchitectureSpec.from_published_profile("smollm2-135m-instruct")
    smol_tok = HuggingFaceBPETokenizerGround.from_huggingface_hub(smol_arch.source_model, revision=smol_arch.revision)
    smol_store = PagedObjectStore(InMemoryPageBacking(65536))
    smol_wg, smol_http = LazySafetensorsWeightGround.from_huggingface_hub(
        smol_arch.source_model, revision=smol_arch.revision, arch=smol_arch, cache_store=smol_store
    )
    all_smol_names = [t.name for t in smol_arch.build_parameter_space().tensors]
    smol_spans = smol_wg.prefetch_tensors_coalesced(all_smol_names, max_gap_bytes=1024 * 1024, max_span_bytes=64 * 1024 * 1024)
    smol_bytes_206 = sum(s.bytes_transferred for s in smol_http.values())
    smol_reqs_206 = sum(s.requests_made for s in smol_http.values())
    for s in smol_http.values():
        s.close()
    smol_prefetch_sec = round(time.perf_counter() - t0_smol, 3)

    # 3. Stream Live DeepSeek-R1-Distill-Qwen-1.5B Layers 0..1 Over HTTPS 206 Range ($d=1536$)!
    t0_ds = time.perf_counter()
    ds_arch = TransformerArchitectureSpec.from_published_profile("deepseek-r1-distill-qwen-1.5b")
    ds_tok = HuggingFaceBPETokenizerGround.from_huggingface_hub(ds_arch.source_model, revision=ds_arch.revision)
    ds_store = PagedObjectStore(InMemoryPageBacking(65536))
    ds_wg, ds_http = LazySafetensorsWeightGround.from_huggingface_hub(
        ds_arch.source_model, revision=ds_arch.revision, arch=ds_arch, cache_store=ds_store
    )
    ds_l01_names = [t.name for li in (0, 1) for t in ds_arch.layer_tensor_spaces(li)]
    ds_wg.prefetch_tensors_coalesced(ds_l01_names, max_gap_bytes=256 * 1024, max_span_bytes=64 * 1024 * 1024)
    ds_realizer = TransformerLayerRealizer(ds_arch, ds_wg, store=ds_store, cache_decoded_weights=True)

    # Instantiate HostedModelSubagents for Qwen3-0.6B (28 layers) and SmolLM2-135M-Instruct (30 layers)!
    hyp = ReceiverHypervisor("cmc001.pretrained.hypervisor")
    hyp.register_agent(create_subagent_grant("subagent.qwen3_0_6b", probe_budget=128, allowed_memory_prefix="cmc."))
    hyp.register_agent(create_subagent_grant("subagent.smollm2_135m", probe_budget=128, allowed_memory_prefix="cmc."))

    sa_qwen3 = HostedModelSubagent(
        "subagent.qwen3_0_6b",
        arch=q3_arch,
        weight_ground=q3_wg,
        encode_fn=q3_tok.encode,
        decode_fn=q3_tok.decode,
        hypervisor=hyp,
        store=PagedObjectStore(InMemoryPageBacking(65536)),
        llm_weight=Fraction(1, 2),
        max_continuation_tokens=4,
        cache_decoded_weights=True,
    )
    sa_smol = HostedModelSubagent(
        "subagent.smollm2_135m",
        arch=smol_arch,
        weight_ground=smol_wg,
        encode_fn=smol_tok.encode,
        decode_fn=smol_tok.decode,
        hypervisor=hyp,
        store=PagedObjectStore(InMemoryPageBacking(65536)),
        llm_weight=Fraction(1, 2),
        max_continuation_tokens=4,
        cache_decoded_weights=True,
    )

    # =========================================================================
    # Part A: Empirical Cross-Model Relational Consensus (`IDEA-005`)
    # =========================================================================
    matched_clauses = (
        "Given an initial state x0,",
        "an affine modular transition applies multiplier a,",
        "adds constant offset b modulo M,",
        "composes associatively across k steps,",
        "collapses via binary exponentiation in log k time,",
        "emits a cryptographic quorum certificate,",
        "verifies independently without private secrets,",
        "and admits the terminal observation.",
    )
    unrelated_clauses = (
        "Preheat a cast-iron oven to 450 degrees,",
        "whisk sourdough starter into warm water,",
        "fold salted bread flour into elastic dough,",
        "rest beneath a damp linen towel,",
        "score the risen boule with a sharp blade,",
        "bake until the crust caramelizes golden brown,",
        "cool on a wire rack for forty minutes,",
        "and slice into crisp artisan loaves.",
    )

    q3_traj = _boundary_hidden_trajectory(matched_clauses, q3_tok, sa_qwen3.realizer, num_layers=28)
    smol_traj = _boundary_hidden_trajectory(matched_clauses, smol_tok, sa_smol.realizer, num_layers=30)
    ds_traj = _boundary_hidden_trajectory(matched_clauses, ds_tok, ds_realizer, num_layers=2)
    smol_unrelated = _boundary_hidden_trajectory(unrelated_clauses, smol_tok, sa_smol.realizer, num_layers=30)

    ds_bytes_206 = sum(s.bytes_transferred for s in ds_http.values())
    for s in ds_http.values():
        s.close()
    ds_elapsed_sec = round(time.perf_counter() - t0_ds, 3)

    sk_q3_exact = CenteredGramRelationalSketch.from_hidden_states("Qwen3-0.6B(d=1024,L28)", q3_traj)
    sk_smol_exact = CenteredGramRelationalSketch.from_hidden_states("SmolLM2-135M(d=576,L30)", smol_traj)
    sk_ds_exact = CenteredGramRelationalSketch.from_hidden_states("DeepSeek-R1-1.5B(d=1536,L2)", ds_traj)
    sk_smol_unrel = CenteredGramRelationalSketch.from_hidden_states("SmolLM2-Unrelated(d=576,L30)", smol_unrelated)

    sk_q3_jl = CenteredGramRelationalSketch.from_hidden_states("Qwen3-JL128", q3_traj, sketch_dim=128, seed_tag="q3")
    sk_smol_jl = CenteredGramRelationalSketch.from_hidden_states("SmolLM2-JL128", smol_traj, sketch_dim=128, seed_tag="sm")

    cka_q3_smol = compare_relational_sketches(sk_q3_exact, sk_smol_exact, num_permutations=24)
    cka_q3_ds = compare_relational_sketches(sk_q3_exact, sk_ds_exact, num_permutations=24)
    cka_q3_unrel = compare_relational_sketches(sk_q3_exact, sk_smol_unrel, num_permutations=24)
    cka_jl128 = compare_relational_sketches(sk_q3_jl, sk_smol_jl, num_permutations=24)

    # =========================================================================
    # Part B: Directed Pretrained Subagents Developing & Auditing Live VLD!
    # =========================================================================
    builder = ContinuousLayerBuilderAgent("subagent.qwen3_0_6b", hyp)
    compiler = IntentionToRealizationCompiler()

    # Query current origin/main and origin/main~1 of live Virtual-Layer-Dynamics on GitHub!
    head_oid = subprocess.check_output(["git", "-C", str(REPO_VLD), "rev-parse", "origin/main"], text=True).strip()
    prev_oid = subprocess.check_output(["git", "-C", str(REPO_VLD), "rev-parse", "origin/main~1"], text=True).strip()

    live_git_record: dict[str, Any] = {}
    sheaf_record: dict[str, Any] = {}
    compiler_record: dict[str, Any] = {}

    def _run_compiler_upgrade() -> dict[str, Any]:
        ex = IntentExpr.iterate_affine(IntentExpr.var("x"), a=5, b=13, steps=10**12 + 7, modulus=256)
        plan = compiler.compile(IntentionSpec("cmc.orbit.1e12", ex, ObservationContract("int_vector"), AuthorityPolicy("cmc.lin")))
        ir = compiler.verify_interchangeable_realizations(plan, {"x": [11, 42]})
        upg = builder.probe_certify_and_install_orbit_shortcut(
            "upg.cmc.orbit",
            memory_id="cmc.orbit_29",
            probe_fn=lambda t: (7 * t + 5) % 29,
            num_probes=8,
            domain="Z_mod",
            declared_modulus=29,
            target_horizon=10**12,
        )
        compiler_record.update(
            {
                "admitted_observation": ir["admitted_observation"],
                "backends_verified": ir["backends_verified"],
                "pareto_selected": ir["pareto_selected"],
                "upgrade_digest": upg.artifact_digest,
            }
        )
        return {"admitted": True, **compiler_record}

    def _run_live_github_pack_qualification() -> dict[str, Any]:
        g_live = GitPackGraphGround("https://github.com/Kier73/Virtual-Layer-Dynamics.git")
        cert = g_live.qualify_graph_delta_operator(base_oid=prev_oid, target_oid=head_oid)
        live_git_record.update(
            {
                "base_oid": cert.base_oid,
                "byte_reduction_ratio": cert.byte_reduction_ratio,
                "certificate_digest": cert.certificate_digest,
                "delta_objects": cert.delta_objects,
                "delta_pack_bytes": cert.delta_pack_bytes,
                "full_closure_objects": cert.full_closure_objects,
                "full_closure_pack_bytes": cert.full_closure_pack_bytes,
                "root_tree_oid": cert.root_tree_oid,
                "target_oid": cert.target_oid,
            }
        )
        return {"admitted": True, **live_git_record}

    def _run_bad_git_ignore_have() -> dict[str, Any]:
        with GitSmartHTTPFixtureServer(mode="ignore_have") as bad_srv:
            g_bad = GitPackGraphGround(bad_srv.base_url)
            refs = g_bad.observe_refs()
            g_bad.qualify_graph_delta_operator(base_oid=refs["refs/tags/v0.1"], target_oid=refs["refs/heads/main"])
        return {"admitted": True}

    def _run_sheaf_audit() -> dict[str, Any]:
        sh = CellularSheaf("cmc.observer.sheaf", field="Fp", modulus=97)
        for idx in range(6):
            sh.add_observer(f"host.{idx}", 1)
        sh.add_restriction_edge("ok.01", source_observer="host.0", target_observer="host.1", source_map=[[1]], target_map=[[1]], offset=[12])
        sh.add_restriction_edge("ok.12", source_observer="host.1", target_observer="host.2", source_map=[[1]], target_map=[[1]], offset=[18])
        sh.add_restriction_edge("ok.20", source_observer="host.2", target_observer="host.0", source_map=[[1]], target_map=[[1]], offset=[67])
        sh.add_restriction_edge("drift.34", source_observer="host.3", target_observer="host.4", source_map=[[1]], target_map=[[1]], offset=[9])
        sh.add_restriction_edge("drift.45", source_observer="host.4", target_observer="host.5", source_map=[[1]], target_map=[[1]], offset=[14])
        sh.add_restriction_edge("drift.53", source_observer="host.5", target_observer="host.3", source_map=[[1]], target_map=[[1]], offset=[8])
        rep = sh.solve_global_section()
        assert rep.obstruction is not None
        sheaf_record.update(
            {
                "conflicting_edge_ids": list(rep.obstruction.conflicting_edge_ids),
                "holonomy_residual": rep.obstruction.holonomy_residual,
                "report_digest": rep.report_digest,
            }
        )
        return {"admitted": True, **sheaf_record}

    t_orbit = SubagentEngineeringTask(
        "cmc.task1.orbit_compiler",
        "intention_compiler",
        "Compile 10^12+7 affine recurrence to closed-form jump and reject 3-sample unwrapped decoy.",
        (
            SubagentProposalOption(
                "00_decoy_3sample",
                "accept_3sample_unwrapped",
                "Accept rapid 3-sample fit immediately.",
                Fraction(0),
                Fraction(0),
                Fraction(1, 10),
                Fraction(0),
                "pat.cmc.df0",
                lambda: hyp.propose_structural_law("subagent.qwen3_0_6b", memory_id="cmc.bad", samples=[3, 19, 8], domain="Z_mod"),
            ),
            SubagentProposalOption(
                "01_compile_and_certify_orbit",
                "compile_pareto_orbit",
                "Probe 8 samples with wrap witness and verify 3-backend e-graph compilation.",
                Fraction(5),
                Fraction(1),
                Fraction(99, 100),
                Fraction(1),
                "pat.cmc.orbit_ok",
                _run_compiler_upgrade,
            ),
        ),
    )

    t_git = SubagentEngineeringTask(
        "cmc.task2.live_github_pack",
        "internet_git_ground",
        "Qualify live GitHub Wire Protocol v2 want/have graph delta against full-closure bypass.",
        (
            SubagentProposalOption(
                "00_unqualified_ignore_have",
                "admit_ignore_have_endpoint",
                "Trust endpoint without checking have set-difference reduction.",
                Fraction(0),
                Fraction(0),
                Fraction(0),
                Fraction(0),
                "pat.cmc.ignore_have",
                _run_bad_git_ignore_have,
            ),
            SubagentProposalOption(
                "01_qualify_live_github_delta",
                "qualify_github_smart_http_v2",
                "Verify PACK SHA-1, Merkle root tree, and strict want/have byte reduction on GitHub.",
                Fraction(3),
                Fraction(1),
                Fraction(97, 100),
                Fraction(1),
                "pat.cmc.github_ok",
                _run_live_github_pack_qualification,
            ),
        ),
    )

    t_sheaf = SubagentEngineeringTask(
        "cmc.task3.sheaf_holonomy",
        "observer_consistency",
        "Audit 6-observer cyclic F_97 network via exact 0-coboundary RREF and 1-cocycle witness.",
        (
            SubagentProposalOption(
                "01_extract_minimal_1cocycle",
                "solve_sheaf_1cocycle",
                "Compute Fredholm dual cocycle y in ker(delta0^T) localizing the faulty 3-edge loop.",
                Fraction(3),
                Fraction(1),
                Fraction(9, 10),
                Fraction(1),
                "pat.cmc.sheaf_ok",
                _run_sheaf_audit,
            ),
            SubagentProposalOption(
                "00_trust_root_clock_blindly",
                "ignore_cycle_holonomy",
                "Overwrite cycle discrepancy from host.0 without checking holonomy.",
                Fraction(0),
                Fraction(0),
                Fraction(0),
                Fraction(0),
                "pat.cmc.blind_clock",
                lambda: (_ for _ in ()).throw(ValueError("refused_unverified_clock_overwrite")),
            ),
        ),
    )

    # Measure raw pre-calibration LLM log-probs on Task 1 before running the 2-round loop!
    pre_q3_scores = {r.proposal_id: r.mean_token_logprob for r in sa_qwen3.score_task_options(t_orbit)}
    pre_smol_scores = {r.proposal_id: r.mean_token_logprob for r in sa_smol.score_task_options(t_orbit)}

    loop = DirectedSubagentDevelopmentLoop("cmc001.pretrained.coevolution", [sa_qwen3, sa_smol])
    ev_rep = loop.run_development_rounds(
        [
            [t_orbit],                   # Round 0: calibrate against decoy/identifiability gate
            [t_orbit, t_git, t_sheaf],   # Round 1: execute all 3 live VLD upgrades & audits!
        ]
    )

    post_q3_scores = {r.proposal_id: r.mean_token_logprob for r in sa_qwen3.score_task_options(t_orbit)}
    post_smol_scores = {r.proposal_id: r.mean_token_logprob for r in sa_smol.score_task_options(t_orbit)}

    # Generate authentic autoregressive engineering summaries from BOTH pretrained models inside VLD!
    q3_note = sa_qwen3.generate_engineering_note(
        "In Virtual Layer Dynamics, verifying mathematical laws before execution ensures", max_new_tokens=10
    )
    smol_note = sa_smol.generate_engineering_note(
        "In Virtual Layer Dynamics, verifying mathematical laws before execution ensures", max_new_tokens=10
    )

    bundle = {
        "cross_model_relational_consensus": {
            "method": "Boundary-anchored cumulative clause hidden states + double-centered Token-Gram CKA",
            "qwen3_L28_vs_deepseek_r1_L2_matched": cka_q3_ds.to_dict(),
            "qwen3_L28_vs_smollm2_L30_jl128_sketch": cka_jl128.to_dict(),
            "qwen3_L28_vs_smollm2_L30_matched": cka_q3_smol.to_dict(),
            "qwen3_L28_vs_smollm2_L30_unrelated_control": cka_q3_unrel.to_dict(),
        },
        "experiment_id": "CMC-001",
        "hosted_pretrained_models": {
            "deepseek_r1_distill_1_5b": {
                "elapsed_sec": ds_elapsed_sec,
                "hidden_size": ds_arch.hidden_size,
                "http_206_bytes": ds_bytes_206,
                "repo": ds_arch.source_model,
                "revision": ds_arch.revision,
            },
            "qwen3_0_6b": {
                "generated_note": q3_note,
                "hidden_size": q3_arch.hidden_size,
                "layers": q3_arch.num_hidden_layers,
                "repo": q3_arch.source_model,
                "revision": q3_arch.revision,
            },
            "smollm2_135m_instruct_http206": {
                "coalesced_spans": smol_spans,
                "generated_note": smol_note,
                "hidden_size": smol_arch.hidden_size,
                "http_206_bytes": smol_bytes_206,
                "http_206_requests": smol_reqs_206,
                "layers": smol_arch.num_hidden_layers,
                "prefetch_sec": smol_prefetch_sec,
                "repo": smol_arch.source_model,
                "revision": smol_arch.revision,
            },
        },
        "live_vld_upgrades_and_audits": {
            "intention_compiler_1e12": compiler_record,
            "live_github_pack_v2_delta": live_git_record,
            "sheaf_1cocycle_localization": sheaf_record,
        },
        "subagent_coevolution": {
            "continuity_certificate_digest": ev_rep.continuity_digest,
            "final_acceptance_rate": ev_rep.final_acceptance_rate,
            "initial_acceptance_rate": ev_rep.initial_acceptance_rate,
            "post_directive_llm_logprobs": {"qwen3": post_q3_scores, "smollm2": post_smol_scores},
            "pre_directive_llm_logprobs": {"qwen3": pre_q3_scores, "smollm2": pre_smol_scores},
            "quorum_public_keys": dict(ev_rep.quorum_public_keys),
            "round_outcomes": [
                {
                    "action_kind": o.selected_action_kind,
                    "admitted": o.admitted,
                    "cross_model_cka": o.cross_model_cka,
                    "proposal_id": o.selected_proposal_id,
                    "round_index": o.round_index,
                    "task_id": o.task_id,
                }
                for o in ev_rep.round_outcomes
            ],
            "standalone_ed25519_audit": dict(ev_rep.standalone_audit),
        },
        "total_elapsed_sec": round(time.perf_counter() - t0_total, 3),
    }

    ev_path = Path(__file__).resolve().parent / "evidence" / "cmc001_bundle.json"
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    ev_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


if __name__ == "__main__":
    out = run_cmc001()
    print(json.dumps(out, indent=2, sort_keys=True))
