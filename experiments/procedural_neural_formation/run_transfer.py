"""PNF-002 portable parameter export and separate receiver verification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform

import numpy as np

from .capsule import pack_pair
from .formation import FormationError, procedural_block, widen
from .run import REPOSITORY, REVISION, MAX_PAYLOAD_BYTES
from .transfer import transfer_pair


def observe_source():
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
    if source.validate() != (768, 3072, 768) or sum(r["size_bytes"] for r in records) != 18_889_728:
        raise FormationError("pinned source block changed")
    if len(proof.ground.obligations) != 654 or len(proof.ground.unresolved_obligations()) != 654:
        raise FormationError("unexpected source proof status")
    provenance = {"kind": "observed-selected-huggingface-payloads", "repository": REPOSITORY,
        "revision": REVISION, "license_id": "mit", "tensor_evidence": records,
        "source_graph_digest": projection.graph_digest,
        "source_graph_operation_count": len(projection.dag.nodes),
        "source_vgi_unverified_obligations": 654, "source_vgi_kernel_accepted": 0}
    return source, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capsule-output", type=Path,
                        help="retain the final model-pair capsule and external policy sidecar")
    args = parser.parse_args()
    cases = []
    origins = [(procedural_block(8, 1024, 8, activation=activation), 2048,
                {"kind": "procedural", "seed": 31, "rule": "PCG64-dyadic-coefficients"})
               for activation in ("relu", "gelu_tanh")]
    if args.live:
        source, provenance = observe_source()
        origins.append((source, 4096, provenance))
    for source, width, provenance in origins:
        generated, certificate = widen(source, width)
        inputs = source.validate()[0]
        probes = [[((i * 7 + k * 3) % 19 - 9) / 16 for i in range(inputs)] for k in range(2)]
        raw, policy = pack_pair(source, generated, certificate, provenance, probes)
        result = transfer_pair(raw, policy)
        if result["receiver"]["report"]["status"] != "verified":
            raise FormationError("separate receiver rejected the generated realization")
        cases.append({"provenance": provenance, "transfer": result})
        summary = {"source_kind": provenance["kind"], "activation": source.activation,
            "source_dimensions": list(source.validate()), "generated_dimensions": list(generated.validate()),
            "capsule_bytes": len(raw), "capsule_sha256": policy["capsule_sha256"],
            "chunks": result["chunk_count"], "status": result["receiver"]["report"]["status"],
            "receiver_max_absolute_error": result["receiver"]["report"]["max_absolute_error"]}
        print(json.dumps(summary), flush=True)
    if args.capsule_output:
        args.capsule_output.parent.mkdir(parents=True, exist_ok=True)
        args.capsule_output.write_bytes(raw)
        args.capsule_output.with_suffix(".policy.json").write_bytes(json.dumps(policy, indent=2, sort_keys=True).encode() + b"\n")
    report = {"schema": "ifs.portable-neural-transfer-experiment.v1", "cases": cases,
              "environment": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
              "scope": "separate processes over actual loopback mTLS sockets; one physical host",
              "persisted_final_capsule": args.capsule_output is not None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
