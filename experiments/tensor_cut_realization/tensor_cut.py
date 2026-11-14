"""TCR-001: bounded tensor-cut MLP execution with independently checkable jobs.

Preparation fetches/constructs a source block; individual workers receive only
one hidden-neuron partition and a common typed input. E-CPU owns the aggregation
DAG and commits received receipts. GitHub artifact handoff is *not* E-CPU Transit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "ifs.tensor-cut-realization.v1"
RECEIPT_SCHEMA = "ifs.tensor-cut-partial-receipt.v1"
REPOSITORY = "openai-community/gpt2"
REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
MAX_PARTITIONS = 16
MAX_ELEMENTS = 20_000_000
MAX_PAYLOAD_BYTES = 20 * 1024 * 1024
ATOL = 1e-9
RTOL = 1e-10


class TensorCutError(ValueError):
    """Malformed input, unverifiable binding, or numerically invalid cut."""


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _typed_digest(array: np.ndarray) -> str:
    """Hash dtype, shape, and canonical little-endian dense array bytes."""
    a = np.asarray(array)
    if a.dtype == np.float32:
        a = np.ascontiguousarray(a.astype("<f4", copy=False))
        dtype = "F32"
    elif a.dtype == np.float64:
        a = np.ascontiguousarray(a.astype("<f8", copy=False))
        dtype = "F64"
    else:
        raise TensorCutError("only float32 parameters and float64 observations are admitted")
    if not np.isfinite(a).all():
        raise TensorCutError("nonfinite tensor")
    return hashlib.sha256(_bytes({"dtype": dtype, "shape": list(a.shape)}) +
                          b"\x00" + a.tobytes(order="C")).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True,
                               ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TensorCutError("expected a JSON object")
    return value


def _validated_manifest(value: dict) -> dict:
    if value.get("schema") != SCHEMA or value.get("strategy") != "contiguous-hidden-neuron-cut":
        raise TensorCutError("unknown tensor-cut schema or strategy")
    saved = value.get("digest")
    if not isinstance(saved, str) or saved != _hash({k: v for k, v in value.items() if k != "digest"}):
        raise TensorCutError("manifest digest mismatch")
    sizes = (value.get("input_dim"), value.get("hidden_dim"), value.get("output_dim"))
    if any(type(d) is not int or d <= 0 for d in sizes):
        raise TensorCutError("invalid manifest dimensions")
    parts = value.get("partitions")
    if not isinstance(parts, list) or not 1 <= len(parts) <= min(sizes[1], MAX_PARTITIONS):
        raise TensorCutError("invalid partition count")
    cursor = 0
    for i, part in enumerate(parts):
        if (not isinstance(part, dict) or part.get("id") != i or
                type(part.get("start")) is not int or type(part.get("stop")) is not int or
                part["start"] != cursor or not cursor < part["stop"] <= sizes[1] or
                set(part.get("tensor_digests", {})) != {"up_weight", "up_bias", "down_weight"}):
            raise TensorCutError("gapped, overlapping, or malformed partition")
        cursor = part["stop"]
    if cursor != sizes[1]:
        raise TensorCutError("incomplete hidden dimension coverage")
    for digest in (value.get("source_digest"), value.get("input_digest"), value.get("output_bias_digest")):
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise TensorCutError("invalid source/input/bias digest")
    if (value.get("activation") not in ("relu", "gelu_tanh") or
            value.get("arithmetic") != "float64-eval-of-float32-parameters" or
            type(value.get("probe_count")) is not int or not 1 <= value["probe_count"] <= 8 or
            not isinstance(value.get("source_provenance"), dict)):
        raise TensorCutError("invalid model or observation metadata")
    for part in parts:
        for digest in part["tensor_digests"].values():
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise TensorCutError("invalid partition tensor digest")
    return value


def _activation(z: np.ndarray, family: str) -> np.ndarray:
    if family == "relu":
        return np.maximum(z, 0)
    if family == "gelu_tanh":
        return 0.5 * z * (1.0 + np.tanh(math.sqrt(2.0 / math.pi) *
                                      (z + 0.044715 * z**3)))
    raise TensorCutError("unsupported activation")


def _probe_inputs(width: int) -> np.ndarray:
    return np.asarray([[((i * 7 + k * 3) % 19 - 9) / 16
                        for i in range(width)] for k in range(2)], dtype=np.float64)


def _reference(block: Any, x: np.ndarray) -> np.ndarray:
    return (_activation(x @ block.up_weight.astype(np.float64) + block.up_bias,
                        block.activation) @ block.down_weight.astype(np.float64) + block.down_bias)


def _scalar_oracle(block: Any, x: np.ndarray, selected: list[int]) -> np.ndarray:
    """Independent Python-loop/math.fsum oracle, no NumPy matmul or vector activation."""
    up = block.up_weight
    ub = block.up_bias
    down = block.down_weight
    db = block.down_bias
    answers = []
    for vector in x:
        hidden = []
        for j in range(up.shape[1]):
            z = math.fsum(float(vector[i]) * float(up[i, j]) for i in range(up.shape[0])) + float(ub[j])
            if block.activation == "relu":
                h = max(z, 0.0)
            elif block.activation == "gelu_tanh":
                h = 0.5 * z * (1.0 + math.tanh(math.sqrt(2.0 / math.pi) *
                                               (z + 0.044715 * z**3)))
            else:
                raise TensorCutError("unsupported activation")
            hidden.append(h)
        answers.append([math.fsum(hidden[j] * float(down[j, out]) for j in range(len(hidden))) +
                        float(db[out]) for out in selected])
    return np.asarray(answers, dtype=np.float64)


def prepare(block: Any, provenance: dict, directory: Path, partitions: int = 4) -> dict:
    """Materialize separate workers' parameters without sharing the whole block."""
    inputs, hidden, outputs = block.validate()
    if (type(partitions) is not int or partitions < 1 or
            partitions > min(hidden, MAX_PARTITIONS)):
        raise TensorCutError("invalid partition count")
    x = _probe_inputs(inputs)
    if x.size + len(x) * (4 * hidden + outputs) > MAX_ELEMENTS:
        raise TensorCutError("execution element budget exceeded")
    source = block.descriptor()
    if source["digest"] != _hash({k: v for k, v in source.items() if k != "digest"}):
        raise TensorCutError("invalid source descriptor")
    if block.activation not in ("relu", "gelu_tanh"):
        raise TensorCutError("unsupported activation")
    widths = [hidden // partitions + int(i < hidden % partitions) for i in range(partitions)]
    splits, cursor = [], 0
    for index, width in enumerate(widths):
        start, stop = cursor, cursor + width
        cursor = stop
        up_weight = np.ascontiguousarray(block.up_weight[:, start:stop])
        up_bias = np.ascontiguousarray(block.up_bias[start:stop])
        down_weight = np.ascontiguousarray(block.down_weight[start:stop, :])
        splits.append({"id": index, "start": start, "stop": stop,
                       "tensor_digests": {"up_weight": _typed_digest(up_weight),
                                          "up_bias": _typed_digest(up_bias),
                                          "down_weight": _typed_digest(down_weight)}})
        packet = directory / f"shard-{index}"
        packet.mkdir(parents=True, exist_ok=True)
        np.savez(packet / "shard.npz", up_weight=up_weight, up_bias=up_bias,
                 down_weight=down_weight, inputs=x)
    manifest = {"schema": SCHEMA, "strategy": "contiguous-hidden-neuron-cut",
                "source_digest": source["digest"], "source_provenance": provenance,
                "input_dim": inputs, "hidden_dim": hidden, "output_dim": outputs,
                "activation": block.activation, "input_digest": _typed_digest(x),
                "output_bias_digest": _typed_digest(block.down_bias),
                "partitions": splits, "probe_count": len(x), "arithmetic": "float64-eval-of-float32-parameters"}
    manifest["digest"] = _hash(manifest)
    _validated_manifest(manifest)
    _write_json(directory / "manifest.json", manifest)
    for index in range(partitions):
        _write_json(directory / f"shard-{index}" / "manifest.json", manifest)
        _write_json(directory / f"shard-{index}" / "assignment.json",
                    {"partition_id": index, "manifest_digest": manifest["digest"]})
    y = _reference(block, x)
    chosen = sorted({0, outputs // 2, outputs - 1})
    oracle = _scalar_oracle(block, x, chosen)
    _compare(y[:, chosen], oracle, "source dense vs independent scalar oracle")
    np.savez(directory / "reference.npz", inputs=x, reference_y=y,
             down_bias=block.down_bias, oracle_selected=oracle,
             oracle_indices=np.asarray(chosen, dtype=np.int64))
    return manifest


def _compare(actual: np.ndarray, expected: np.ndarray, label: str) -> float:
    if (actual.shape != expected.shape or not np.isfinite(actual).all() or
            not np.isfinite(expected).all()):
        raise TensorCutError(f"{label}: shape or finite-value mismatch")
    err = float(np.max(np.abs(actual - expected)))
    if not np.allclose(actual, expected, rtol=RTOL, atol=ATOL):
        raise TensorCutError(f"{label}: numerical mismatch (max abs {err})")
    return err


def worker(packet: Path, destination: Path) -> dict:
    """A standalone worker sees one shard, input and a shared manifest, not the full model."""
    manifest = _validated_manifest(_read_json(packet / "manifest.json"))
    with np.load(packet / "shard.npz", allow_pickle=False) as loaded:
        if set(loaded.files) != {"up_weight", "up_bias", "down_weight", "inputs"}:
            raise TensorCutError("unexpected shard archive members")
        arrays = {name: loaded[name] for name in loaded.files}
    up, ub, down, x = (arrays[name] for name in ("up_weight", "up_bias", "down_weight", "inputs"))
    if (up.dtype != np.float32 or ub.dtype != np.float32 or down.dtype != np.float32 or
            x.dtype != np.float64 or x.ndim != 2 or up.ndim != 2 or down.ndim != 2):
        raise TensorCutError("invalid shard types or ranks")
    assignment = _read_json(packet / "assignment.json")
    index = assignment.get("partition_id")
    if (type(index) is not int or not 0 <= index < len(manifest["partitions"]) or
            assignment != {"partition_id": index, "manifest_digest": manifest["digest"]}):
        raise TensorCutError("worker assignment does not bind to manifest")
    part = manifest["partitions"][index]
    if any(_typed_digest(arrays[name]) != part["tensor_digests"][name]
           for name in ("up_weight", "up_bias", "down_weight")):
        raise TensorCutError("worker parameters do not match assigned tensor digests")
    if (up.shape != (manifest["input_dim"], part["stop"]-part["start"]) or
            ub.shape != (up.shape[1],) or down.shape != (up.shape[1], manifest["output_dim"]) or
            x.shape != (manifest["probe_count"], manifest["input_dim"]) or
            _typed_digest(x) != manifest["input_digest"]):
        raise TensorCutError("shard/input shape or identity mismatch")
    partial = _activation(x @ up.astype(np.float64) + ub,
                          manifest["activation"]) @ down.astype(np.float64)
    if not np.isfinite(partial).all():
        raise TensorCutError("nonfinite partial output")
    receipt = {"schema": RECEIPT_SCHEMA, "manifest_digest": manifest["digest"],
               "source_digest": manifest["source_digest"], "input_digest": manifest["input_digest"],
               "partition_id": part["id"], "partition_tensor_digests": part["tensor_digests"],
               "output_digest": _typed_digest(partial), "output_shape": list(partial.shape),
               "arithmetic": manifest["arithmetic"], "status": "complete",
               "worker_trust": "unsigned artifact; no hardware or transport attestation"}
    destination.mkdir(parents=True, exist_ok=True)
    _write_json(destination / f"receipt-{part['id']}.json", receipt)
    np.save(destination / f"partial-{part['id']}.npy", partial, allow_pickle=False)
    return receipt


def _accept(manifest: dict, results: Path, index: int) -> tuple[np.ndarray, dict]:
    receipt = _read_json(results / f"receipt-{index}.json")
    part = manifest["partitions"][index]
    expected = {"schema": RECEIPT_SCHEMA, "manifest_digest": manifest["digest"],
                "source_digest": manifest["source_digest"], "input_digest": manifest["input_digest"],
                "partition_id": index, "partition_tensor_digests": part["tensor_digests"],
                "output_shape": [manifest["probe_count"], manifest["output_dim"]],
                "arithmetic": manifest["arithmetic"], "status": "complete",
                "worker_trust": "unsigned artifact; no hardware or transport attestation"}
    if set(receipt) != set(expected) | {"output_digest"} or any(receipt.get(k) != v for k, v in expected.items()):
        raise TensorCutError("malformed or unrelated worker receipt")
    value = np.load(results / f"partial-{index}.npy", allow_pickle=False)
    if value.dtype != np.float64 or list(value.shape) != receipt["output_shape"] or _typed_digest(value) != receipt["output_digest"]:
        raise TensorCutError("worker payload digest mismatch")
    return value, receipt


def aggregate(prepared: Path, results: Path, output: Path) -> dict:
    """Commit verified worker evidence in E-CPU's dependency DAG; no Transit claim."""
    from mailcpu.computation_dag import ComputationNode, NavigableComputationDAG

    manifest = _validated_manifest(_read_json(prepared / "manifest.json"))
    with np.load(prepared / "reference.npz", allow_pickle=False) as loaded:
        if set(loaded.files) != {"inputs", "reference_y", "down_bias", "oracle_selected", "oracle_indices"}:
            raise TensorCutError("unexpected reference archive members")
        x, reference, bias, oracle, selected = (loaded[name] for name in
                                                  ("inputs", "reference_y", "down_bias", "oracle_selected", "oracle_indices"))
    if (x.dtype != np.float64 or reference.dtype != np.float64 or bias.dtype != np.float32 or
            oracle.dtype != np.float64 or selected.dtype != np.int64 or
            x.shape != (manifest["probe_count"], manifest["input_dim"]) or
            reference.shape != (manifest["probe_count"], manifest["output_dim"]) or
            bias.shape != (manifest["output_dim"],) or
            _typed_digest(x) != manifest["input_digest"] or
            _typed_digest(bias) != manifest["output_bias_digest"]):
        raise TensorCutError("reference/input/output bias identity mismatch")
    indexes = sorted({0, manifest["output_dim"] // 2, manifest["output_dim"] - 1})
    if selected.tolist() != indexes or oracle.shape != (manifest["probe_count"], len(indexes)):
        raise TensorCutError("invalid independent-oracle selection")
    scalar_error = _compare(reference[:, indexes], oracle, "prepared independent oracle")
    n = len(manifest["partitions"])
    nodes = [ComputationNode(f"part.{i}", 1, "tcr.execute_partition", "external.worker",
                             manifest["digest"], (), {"partition": manifest["partitions"][i],
                                                     "source_digest": manifest["source_digest"]})
             for i in range(n)]
    nodes += [ComputationNode("reduce", 1, "tcr.deterministic_reduce", "local.numpy",
                              manifest["digest"], tuple(f"part.{i}" for i in range(n)),
                              {"bias_digest": manifest["output_bias_digest"]}),
              ComputationNode("verify", 1, "tcr.compare_observation", "local.numpy",
                              manifest["digest"], ("reduce",),
                              {"source_digest": manifest["source_digest"]})]
    dag = NavigableComputationDAG(nodes)
    partials = {}
    completed = []
    while not dag.is_complete:
        ready = dag.ready_nodes()
        if not ready:
            raise TensorCutError("E-CPU DAG stalled")
        for node in ready:
            key = node.node_id
            if key.startswith("part."):
                index = int(key.partition(".")[2])
                value, receipt = _accept(manifest, results, index)
                partials[index] = value
                evidence = receipt
            elif key == "reduce":
                total = np.zeros_like(reference)
                for index in range(n):
                    total += partials[index]
                total += bias.astype(np.float64)
                evidence = {"output_digest": _typed_digest(total), "ordered_partition_ids": list(range(n))}
            elif key == "verify":
                all_error = _compare(total, reference, "decomposed vs dense")
                selected_error = _compare(total[:, indexes], oracle, "decomposed vs independent oracle")
                evidence = {"status": "passed", "max_abs_dense_error": all_error,
                            "max_abs_scalar_error": selected_error,
                            "source_scalar_error": scalar_error, "atol": ATOL, "rtol": RTOL}
            else:
                raise TensorCutError("unknown DAG operation")
            dag.commit(key, evidence)
            completed.append(key)
    snapshot = dag.snapshot()
    if NavigableComputationDAG.from_snapshot(snapshot).snapshot() != snapshot:
        raise TensorCutError("DAG checkpoint did not reconstruct")
    # These are *logical numeric bytes*, not real network or artifact measurements.
    num_samples = manifest["probe_count"]
    logical_bytes = n * (num_samples * manifest["input_dim"] * 8 +
                         num_samples * manifest["output_dim"] * 8)
    report = {"schema": "ifs.tensor-cut-report.v1", "manifest": manifest,
              "verification": dag.result("verify"), "result_digest": _typed_digest(total),
              "source_reference_digest": _typed_digest(reference), "operation_order": completed,
              "dag_snapshot": snapshot, "dag_restoration_equal": True,
              "counts": {"partition_workers": n, "independent_oracle_coordinates": len(indexes),
                         "output_coordinates_checked": int(reference.size),
                         "logical_activation_and_partial_bytes": logical_bytes},
              "scope": {"worker_execution": "separate jobs possible through artifact handoff",
                        "coordinator": "E-CPU DAG commits worker receipts at aggregation job",
                        "transport": "GitHub Actions artifacts, not E-CPU Transit/mTLS",
                        "numeric": "float64 evaluation of real or constructed F32 coefficients",
                        "equivalence": "bounded numeric probes, not bitwise FP32 or whole-model equivalence",
                        "authentication": "no signed worker or source-publisher attestation",
                        "raw_weight_arrays_retained_in_report": False}}
    _write_json(output, report)
    return report


def _source(live: bool) -> tuple[Any, dict]:
    if not live:
        from experiments.procedural_neural_formation.formation import procedural_block
        return procedural_block(4, 16, 4, activation="gelu_tanh", seed=31), {
            "kind": "procedural", "rule": "PCG64-dyadic", "seed": 31}
    from experiments.external_neural_structure_reading.hub import inspect_huggingface_model, fetch_selected_tensor_payloads
    from experiments.external_neural_structure_reading.neural_graph_ir import compile_gpt2_topology
    from experiments.procedural_neural_formation.source import observed_block, tensor_names
    nsd = inspect_huggingface_model(REPOSITORY, REVISION, license_id="mit")
    graph = compile_gpt2_topology(nsd)
    payloads, records = fetch_selected_tensor_payloads(nsd, tensor_names(),
        max_total_bytes=MAX_PAYLOAD_BYTES, max_tensor_bytes=10 * 1024 * 1024)
    block = observed_block(graph, payloads, records)
    if block.validate() != (768, 3072, 768) or sum(r["size_bytes"] for r in records) != 18_889_728:
        raise TensorCutError("unexpected selected source dimensions or payload size")
    return block, {"kind": "observed-selected-hub-payloads", "repository": REPOSITORY,
                   "revision": REVISION, "license_id": "mit", "tensor_evidence": records,
                   "selected_payload_bytes": sum(r["size_bytes"] for r in records)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    p = actions.add_parser("prepare")
    p.add_argument("--live", action="store_true")
    p.add_argument("--partitions", type=int, default=4)
    p.add_argument("--out", required=True, type=Path)
    w = actions.add_parser("worker")
    w.add_argument("--packet", required=True, type=Path)
    w.add_argument("--out", required=True, type=Path)
    a = actions.add_parser("aggregate")
    a.add_argument("--prepared", required=True, type=Path)
    a.add_argument("--results", required=True, type=Path)
    a.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        block, provenance = _source(args.live)
        result = prepare(block, provenance, args.out, args.partitions)
        print(json.dumps({"action": "prepare", "source_kind": provenance["kind"],
                          "manifest_digest": result["digest"], "partitions": len(result["partitions"]) }))
    elif args.action == "worker":
        result = worker(args.packet, args.out)
        print(json.dumps({"action": "worker", "partition": result["partition_id"],
                          "output_digest": result["output_digest"]}))
    else:
        result = aggregate(args.prepared, args.results, args.out)
        print(json.dumps({"action": "aggregate", "verification": result["verification"],
                          "partitions": result["counts"]["partition_workers"]}))


if __name__ == "__main__":
    main()
