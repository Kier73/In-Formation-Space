"""Bind an explicitly selected GPT-2 MLP to revalidated HFR payload evidence."""
from __future__ import annotations

import hashlib
import numpy as np

from .formation import Block, FormationError, check_budget, MAX_ELEMENTS


def tensor_names(layer: int = 0) -> list[str]:
    if type(layer) is not int or layer < 0:
        raise FormationError("layer must be a nonnegative integer")
    return [f"h.{layer}.mlp.{suffix}" for suffix in
            ("c_fc.weight", "c_fc.bias", "c_proj.weight", "c_proj.bias")]


def observed_block(graph: dict, payloads: dict[str, bytes], evidence: list[dict], *, layer: int = 0) -> Block:
    """Validate selected payload hashes and their exact graph/header bindings."""
    names = tensor_names(layer)
    if set(payloads) != set(names) or len(evidence) != 4:
        raise FormationError("expected exactly four selected MLP tensors")
    records = {e["name"]: e for e in evidence}
    if set(records) != set(names):
        raise FormationError("evidence allowlist mismatch")
    catalog = {t["name"]: t for t in graph["tensors"]}
    shapes = [catalog[n]["shape"] for n in names]
    if any(catalog[n]["dtype"] != "F32" for n in names):
        raise FormationError("observed block requires F32 source tensors")
    if len(shapes[0]) != 2 or len(shapes[2]) != 2:
        raise FormationError("invalid source matrix ranks")
    inputs, hidden = shapes[0]
    hidden2, outputs = shapes[2]
    check_budget(inputs, hidden, outputs, MAX_ELEMENTS)
    if hidden != hidden2 or shapes[1] != [hidden] or shapes[3] != [outputs]:
        raise FormationError("invalid source affine shapes")
    # Bind tensor roles to actual edges of the selected supported chain.
    edges = graph["edges"]
    operations = {o["id"]: o for o in graph["operations"]}
    consumers = {}
    for name in names:
        matches = [e["target"] for e in edges if e["source"] == {"kind": "tensor", "name": name}]
        if len(matches) != 1:
            raise FormationError("selected tensor must have exactly one consumer")
        consumers[name] = matches[0]
    up, down = consumers[names[0]]["operation"], consumers[names[2]]["operation"]
    for pair, op_id in ((names[:2], up), (names[2:], down)):
        if any(consumers[n]["operation"] != op_id for n in pair):
            raise FormationError("affine weight/bias bound to different operations")
        if [consumers[n]["port"] for n in pair] != ["weight", "bias"]:
            raise FormationError("affine tensor port binding mismatch")
        op = operations[op_id]
        if op["operator"] != "linear.affine" or op["attributes"]["weight_layout"] != "input_by_output":
            raise FormationError("unsupported source affine layout")
    links = [(e["source"]["operation"], e["target"]["operation"]) for e in edges
             if e["source"]["kind"] == "operation_output" and e["target"]["kind"] == "operation_input"]
    activations = [op for op in operations.values() if op["operator"] == "activation.gelu_tanh"
                   and (up, op["id"]) in links and (op["id"], down) in links]
    if len(activations) != 1:
        raise FormationError("source must contain a direct affine/GELU-tanh/affine chain")
    arrays = []
    for name, shape in zip(names, shapes):
        tensor, record, payload = catalog[name], records[name], payloads[name]
        expected_size = int(np.prod(shape)) * 4
        source = tensor["source"]
        if (record["dtype"] != "F32" or record["shape"] != shape or
                record["size_bytes"] != expected_size or len(payload) != expected_size or
                record["shard"] != source["file"] or
                record["shard_header_sha256"] != source["header_sha256"] or
                record["payload_sha256_scope"] != "complete-selected-tensor-payload" or
                hashlib.sha256(payload).hexdigest() != record["payload_sha256"]):
            raise FormationError("selected payload evidence mismatch")
        arrays.append(np.frombuffer(payload, dtype="<f4").reshape(shape).astype(np.float32, copy=True))
    result = Block(*arrays)
    result.validate()
    return result
