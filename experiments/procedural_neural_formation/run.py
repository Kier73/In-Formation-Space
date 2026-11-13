"""PNF-001: procedural or bounded live-Hub construction, scheduled through E-CPU."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import platform

import numpy as np

from mailcpu.computation_dag import ComputationNode, NavigableComputationDAG

from .formation import FormationError, digest, evaluate, procedural_block, widen
from .verification import scalar_oracle, verify_conservation

REPOSITORY = "openai-community/gpt2"
REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
MAX_PAYLOAD_BYTES = 20 * 1024 * 1024


def compare(a: np.ndarray, b: np.ndarray) -> dict:
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise FormationError("invalid differential outputs")
    passed = bool(np.allclose(a, b, rtol=1e-10, atol=1e-10))
    result = {"status": "passed" if passed else "failed", "comparisons": int(a.size),
              "max_absolute_error": float(np.max(np.abs(a - b))), "rtol": 1e-10, "atol": 1e-10}
    if not passed:
        raise FormationError(f"numerical comparison failed: {result}")
    return result


def run_case(source, target_width: int, provenance: dict) -> dict:
    """Use real DAG readiness/commits for realization, two executions and comparison."""
    context = {"source": source.descriptor(), "target_width": target_width, "provenance": provenance}
    context_digest = digest(context)
    specs = [("construct", ()), ("source_forward", ()),
             ("generated_forward", ("construct",)),
             ("verify", ("construct", "source_forward", "generated_forward"))]
    dag = NavigableComputationDAG(ComputationNode(name, 1, "pnf." + name, "local.numpy",
        context_digest, deps, {"context_digest": context_digest}) for name, deps in specs)
    inputs, hidden, outputs = source.validate()
    probes = np.asarray([[((i * 7 + k * 3) % 19 - 9) / 16 for i in range(inputs)]
                         for k in range(2)], dtype=np.float64)
    selected = sorted({0, outputs // 2, outputs - 1})
    values = {}
    chronology = []
    while not dag.is_complete:
        ready = dag.ready_nodes()
        if not ready:
            raise FormationError("unexpected stalled construction DAG")
        for node in ready:
            name = node.node_id
            if name == "construct":
                child, cert = widen(source, target_width)
                values.update(child=child, certificate=cert)
                receipt = {"generated": child.descriptor(), "certificate": cert}
            elif name == "source_forward":
                values["source_output"] = evaluate(source, probes)
                receipt = compare(values["source_output"][:, selected], scalar_oracle(source, probes, selected))
            elif name == "generated_forward":
                values["generated_output"] = evaluate(values["child"], probes)
                receipt = compare(values["generated_output"][:, selected], scalar_oracle(values["child"], probes, selected))
            else:
                law = verify_conservation(source, values["child"], values["certificate"])
                comparison = compare(values["source_output"], values["generated_output"])
                # Rebind the changed identity: rejection must depend on the law,
                # not merely on a stale hash or an unobserved numerical probe.
                altered = values["child"].down_weight.copy()
                altered[0, 0] += np.float32(0.25)
                bad = replace(values["child"], down_weight=altered)
                bad_certificate = {**values["certificate"], "generated_digest": bad.descriptor()["digest"]}
                try:
                    verify_conservation(source, bad, bad_certificate)
                except FormationError:
                    rejected = True
                else:
                    raise FormationError("negative control unexpectedly accepted")
                receipt = {"coefficient_law": law, "numerical_comparison": comparison,
                           "rehashed_coefficient_tamper_rejected": rejected}
            dag.commit(name, receipt)
            chronology.append(name)
    snapshot = dag.snapshot()
    restored = NavigableComputationDAG.from_snapshot(snapshot)
    if restored.snapshot() != snapshot:
        raise FormationError("DAG checkpoint restoration differs")
    return {"context": context, "generated": values["child"].descriptor(),
            "certificate": values["certificate"], "verification": dag.result("verify"),
            "source_scalar_oracle": dag.result("source_forward"),
            "generated_scalar_oracle": dag.result("generated_forward"),
            "execution_order": chronology, "dag": snapshot, "restoration_equal": True,
            "probe_inputs": probes.tolist(), "oracle_output_indices": selected,
            "raw_parameters_retained": False, "training_performed": False,
            "execution_host_scope": "one local process; E-CPU dependency and commit semantics"}


def live_case() -> dict:
    from experiments.external_neural_structure_reading.hub import inspect_huggingface_model, fetch_selected_tensor_payloads
    from experiments.external_neural_structure_reading.neural_graph_ir import compile_gpt2_topology
    from mailcpu.neural_graph_bridge import compile_neural_graph_dag
    from vgi.neural_topology import build_neural_topology_proof_ground
    from .source import observed_block, tensor_names

    nsd = inspect_huggingface_model(REPOSITORY, REVISION, license_id="mit")
    graph = compile_gpt2_topology(nsd)
    projection = compile_neural_graph_dag(graph)
    proof = build_neural_topology_proof_ground(graph)
    payloads, records = fetch_selected_tensor_payloads(nsd, tensor_names(),
        max_total_bytes=MAX_PAYLOAD_BYTES, max_tensor_bytes=10 * 1024 * 1024)
    source = observed_block(graph, payloads, records)
    if source.validate() != (768, 3072, 768):
        raise FormationError("pinned GPT-2 block dimensions changed")
    count = sum(r["size_bytes"] for r in records)
    if count != 18_889_728:
        raise FormationError("pinned selected payload size changed")
    provenance = {"kind": "observed-selected-huggingface-payloads", "repository": REPOSITORY,
                  "revision": REVISION, "license_id": "mit", "tensor_evidence": records,
                  "selected_payload_bytes": count, "max_payload_bytes": MAX_PAYLOAD_BYTES,
                  "source_graph_digest": projection.graph_digest}
    result = run_case(source, 4096, provenance)
    result["source_graph_projection"] = projection.manifest()
    result["source_graph_vgi"] = {"graph_digest": proof.graph_digest,
        "obligation_count": len(proof.ground.obligations),
        "unverified_count": len(proof.ground.unresolved_obligations()), "kernel_accepted": 0,
        "generated_model_admission_claimed": False}
    if result["source_graph_vgi"]["unverified_count"] != len(proof.ground.obligations):
        raise FormationError("unexpected source proof status")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="read exactly four GPT-2 MLP tensors under 20 MiB")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [run_case(procedural_block(4, 16, 4, activation=activation), width,
             {"kind": "procedural", "seed": 31, "rule": "PCG64-dyadic-coefficients",
              "source_payload_bytes": 0}) for activation in ("relu", "gelu_tanh") for width in (24, 32)]
    if args.live:
        cases.append(live_case())
    report = {"schema": "ifs.procedural-neural-formation.v1", "cases": cases,
              "environment": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
              "scope": "standalone affine/activation/affine blocks, evaluation semantics; no full-model quality claim"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(cases), "status": "passed", "output": str(args.output),
                      "live_huggingface_read": args.live}))


if __name__ == "__main__":
    main()
