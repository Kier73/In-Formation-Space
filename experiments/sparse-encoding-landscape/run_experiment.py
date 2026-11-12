"""Exact encoding landscape for sparse finite Boolean transition models."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import platform
import statistics
import struct
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[2]
RCN = ROOT / "experiments" / "realization-cost-navigation"
if str(RCN) not in sys.path:
    sys.path.insert(0, str(RCN))
rcn = importlib.import_module("run_experiment")

from mailcpu.semantic_translation import (
    EffectClass, ObservationContract, ReplayClass, RepresentationRef,
    ResourceBound, TranslationContract, canonical_value_digest,
    compare_projected_observations,
)
from mailcpu.transition_space import SparseTransitionReLUNetwork

COMPILERS = {
    "minterm": "mailcpu.transition_space.compile_transition_table",
    "direct_dag": "mailcpu.transition_space.compile_compositional_transition_program",
    "live_dag": "mailcpu.transition_space.compile_live_compositional_transition_program",
}
ENCODINGS = ("coo_json", "csr_json", "rowmask_json", "csr_binary", "rowmask_binary", "hybrid_binary")
REPEATS = 5


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def meta(model: SparseTransitionReLUNetwork) -> dict[str, Any]:
    return {
        "source_kind": model.source_kind,
        "source_digest": model.source_digest,
        "source_model_digest": model.source_model_digest,
        "input_names": list(model.input_names),
        "output_names": list(model.output_names),
        "architecture": list(model.architecture),
    }


def make_sparse(info: dict[str, Any], rows: Sequence[Sequence[Sequence[int | float]]], biases: Sequence[Sequence[Sequence[int | float]]]) -> SparseTransitionReLUNetwork:
    return SparseTransitionReLUNetwork(
        rows, biases,
        source_kind=info["source_kind"],
        source_digest=info["source_digest"],
        source_model_digest=info["source_model_digest"],
        input_names=info["input_names"],
        output_names=info["output_names"],
        architecture=info["architecture"],
    )


def seal_json(payload: dict[str, Any]) -> bytes:
    return canonical({**payload, "payload_digest": sha(payload)})


def open_json(payload: bytes) -> dict[str, Any]:
    data = json.loads(payload)
    supplied = data.pop("payload_digest", None)
    if supplied != sha(data):
        raise ValueError("JSON payload digest mismatch")
    return data


def encode_coo(model: SparseTransitionReLUNetwork) -> bytes:
    return canonical(model.snapshot())


def decode_coo(payload: bytes) -> SparseTransitionReLUNetwork:
    return SparseTransitionReLUNetwork.from_snapshot(json.loads(payload))


def encode_csr_json(model: SparseTransitionReLUNetwork) -> bytes:
    layers = []
    for rows, biases in zip(model.sparse_weights, model.sparse_biases):
        offsets, indices, values = [0], [], []
        for row in rows:
            for index, value in row:
                indices.append(index)
                values.append(value)
            offsets.append(len(indices))
        layers.append({
            "row_offsets": offsets, "input_indices": indices, "weight_values": values,
            "bias_indices": [index for index, _ in biases],
            "bias_values": [value for _, value in biases],
        })
    return seal_json({
        "schema": "sre002.csr-json.v1", "encoding": "csr_json",
        **meta(model), "layers": layers,
        "stored_parameter_count": model.stored_parameter_count,
    })


def decode_csr_json(payload: bytes) -> SparseTransitionReLUNetwork:
    data = open_json(payload)
    if data.get("schema") != "sre002.csr-json.v1":
        raise ValueError("unsupported CSR JSON schema")
    rows_all, biases_all = [], []
    for layer_index, layer in enumerate(data["layers"]):
        width = data["architecture"][layer_index + 1]
        offsets, indices, values = layer["row_offsets"], layer["input_indices"], layer["weight_values"]
        if len(offsets) != width + 1 or offsets[0] != 0 or offsets[-1] != len(indices) or len(indices) != len(values):
            raise ValueError("CSR JSON row pointers or arrays are malformed")
        if any(a > b for a, b in zip(offsets, offsets[1:])):
            raise ValueError("CSR JSON row pointers are not monotonic")
        rows_all.append([
            [(indices[k], values[k]) for k in range(offsets[row], offsets[row + 1])]
            for row in range(width)
        ])
        if len(layer["bias_indices"]) != len(layer["bias_values"]):
            raise ValueError("CSR JSON bias arrays differ")
        biases_all.append(list(zip(layer["bias_indices"], layer["bias_values"])))
    result = make_sparse(data, rows_all, biases_all)
    if result.stored_parameter_count != data["stored_parameter_count"]:
        raise ValueError("CSR JSON parameter count mismatch")
    return result


def encode_rowmask_json(model: SparseTransitionReLUNetwork) -> bytes:
    layers = []
    for rows, biases, output_width in zip(model.sparse_weights, model.sparse_biases, model.architecture[1:]):
        masks, values = [], []
        for row in rows:
            mask = 0
            for index, value in row:
                mask |= 1 << index
                values.append(value)
            masks.append(mask)
        bias_mask, bias_values = 0, []
        for index, value in biases:
            bias_mask |= 1 << index
            bias_values.append(value)
        layers.append({
            "weight_masks": masks, "weight_values": values,
            "bias_mask": bias_mask, "bias_values": bias_values,
            "output_width": output_width,
        })
    return seal_json({
        "schema": "sre002.rowmask-json.v1", "encoding": "rowmask_json",
        **meta(model), "layers": layers,
        "stored_parameter_count": model.stored_parameter_count,
    })


def decode_rowmask_json(payload: bytes) -> SparseTransitionReLUNetwork:
    data = open_json(payload)
    if data.get("schema") != "sre002.rowmask-json.v1":
        raise ValueError("unsupported row-mask JSON schema")
    rows_all, biases_all = [], []
    for layer_index, layer in enumerate(data["layers"]):
        iw, ow = data["architecture"][layer_index:layer_index + 2]
        if len(layer["weight_masks"]) != ow or layer["output_width"] != ow:
            raise ValueError("row-mask JSON output width mismatch")
        cursor, rows = 0, []
        for mask in layer["weight_masks"]:
            if type(mask) is not int or mask < 0 or mask >> iw:
                raise ValueError("row-mask JSON mask out of range")
            indices = [i for i in range(iw) if mask & (1 << i)]
            count = len(indices)
            vals = layer["weight_values"][cursor:cursor + count]
            if len(vals) != count:
                raise ValueError("row-mask JSON values truncated")
            rows.append(list(zip(indices, vals)))
            cursor += count
        if cursor != len(layer["weight_values"]):
            raise ValueError("row-mask JSON has trailing values")
        bm = layer["bias_mask"]
        if type(bm) is not int or bm < 0 or bm >> ow:
            raise ValueError("row-mask JSON bias mask out of range")
        bi = [i for i in range(ow) if bm & (1 << i)]
        if len(bi) != len(layer["bias_values"]):
            raise ValueError("row-mask JSON bias count mismatch")
        rows_all.append(rows)
        biases_all.append(list(zip(bi, layer["bias_values"])))
    result = make_sparse(data, rows_all, biases_all)
    if result.stored_parameter_count != data["stored_parameter_count"]:
        raise ValueError("row-mask JSON parameter count mismatch")
    return result


def scalar_dtype(values: Sequence[float]) -> str:
    return "i8" if all(math.isfinite(float(v)) and float(v).is_integer() and -128 <= int(v) <= 127 for v in values) else "f64"


UWIDTH = {"u8": 1, "u16": 2, "u32": 4}
SWIDTH = {"i8": 1, "f64": 8}


def index_dtype(maximum: int) -> str:
    return "u8" if maximum <= 255 else "u16" if maximum <= 65535 else "u32"


def pack_u(values: Sequence[int], kind: str) -> bytes:
    size, out = UWIDTH[kind], bytearray()
    for value in values:
        if type(value) is not int or value < 0 or value >= 1 << (8 * size):
            raise ValueError("packed unsigned integer out of range")
        out.extend(value.to_bytes(size, "little"))
    return bytes(out)


def unpack_u(data: bytes, offset: int, count: int, kind: str) -> tuple[list[int], int]:
    size, end = UWIDTH[kind], offset + count * UWIDTH[kind]
    if end > len(data):
        raise ValueError("packed integer array truncated")
    return [
        int.from_bytes(data[offset + i * size:offset + (i + 1) * size], "little")
        for i in range(count)
    ], end


def pack_values(values: Sequence[float], kind: str) -> bytes:
    if kind == "i8":
        return b"".join(int(v).to_bytes(1, "little", signed=True) for v in values)
    return b"".join(struct.pack("<d", float(v)) for v in values)


def unpack_values(data: bytes, offset: int, count: int, kind: str) -> tuple[list[float], int]:
    size, end = SWIDTH[kind], offset + count * SWIDTH[kind]
    if end > len(data):
        raise ValueError("packed scalar array truncated")
    if kind == "i8":
        result = [float(int.from_bytes(data[offset + i:offset + i + 1], "little", signed=True)) for i in range(count)]
    else:
        result = [struct.unpack_from("<d", data, offset + i * 8)[0] for i in range(count)]
    return result, end


def pack_mask(mask: int, width: int) -> bytes:
    if type(mask) is not int or mask < 0 or mask >> width:
        raise ValueError("bit mask out of range")
    return mask.to_bytes((width + 7) // 8, "little")


def unpack_mask(data: bytes, offset: int, width: int) -> tuple[int, int]:
    size, end = (width + 7) // 8, offset + (width + 7) // 8
    if end > len(data):
        raise ValueError("packed bitmask truncated")
    return int.from_bytes(data[offset:end], "little"), end


def pack_envelope(header: dict[str, Any], body: bytes) -> bytes:
    header_bytes = canonical({**header, "body_sha256": sha_bytes(body)})
    return struct.pack("<I", len(header_bytes)) + header_bytes + body


def unpack_envelope(payload: bytes) -> tuple[dict[str, Any], bytes]:
    if len(payload) < 4:
        raise ValueError("binary payload lacks header length")
    size = struct.unpack_from("<I", payload, 0)[0]
    split = 4 + size
    if split > len(payload):
        raise ValueError("binary header truncated")
    header, body = json.loads(payload[4:split]), payload[split:]
    if header.get("body_sha256") != sha_bytes(body):
        raise ValueError("binary body digest mismatch")
    return header, body


def encode_csr_binary(model: SparseTransitionReLUNetwork) -> bytes:
    heads, body = [], bytearray()
    for layer_index, (rows, biases) in enumerate(zip(model.sparse_weights, model.sparse_biases)):
        iw, ow = model.architecture[layer_index:layer_index + 2]
        ptr, indices, values = [0], [], []
        for row in rows:
            for index, value in row:
                indices.append(index)
                values.append(value)
            ptr.append(len(indices))
        bi, bv = [i for i, _ in biases], [v for _, v in biases]
        wt, bt = scalar_dtype(values), scalar_dtype(bv)
        it, bit = index_dtype(iw - 1), index_dtype(ow - 1)
        rt = "u16" if len(indices) <= 65535 else "u32"
        heads.append({"input_width": iw, "output_width": ow, "nnz": len(indices), "bias_nnz": len(bi), "weight_dtype": wt, "bias_dtype": bt, "index_dtype": it, "bias_index_dtype": bit, "rowptr_dtype": rt})
        body.extend(pack_u(ptr, rt))
        body.extend(pack_u(indices, it))
        body.extend(pack_values(values, wt))
        body.extend(pack_u(bi, bit))
        body.extend(pack_values(bv, bt))
    return pack_envelope({"schema": "sre002.csr-binary.v1", "encoding": "csr_binary", **meta(model), "layers": heads, "stored_parameter_count": model.stored_parameter_count}, bytes(body))


def decode_csr_binary(payload: bytes) -> SparseTransitionReLUNetwork:
    header, body = unpack_envelope(payload)
    if header.get("schema") != "sre002.csr-binary.v1":
        raise ValueError("unsupported CSR binary schema")
    offset, rows_all, biases_all = 0, [], []
    for layer in header["layers"]:
        ow, nnz, bnnz = layer["output_width"], layer["nnz"], layer["bias_nnz"]
        ptr, offset = unpack_u(body, offset, ow + 1, layer["rowptr_dtype"])
        inds, offset = unpack_u(body, offset, nnz, layer["index_dtype"])
        vals, offset = unpack_values(body, offset, nnz, layer["weight_dtype"])
        bi, offset = unpack_u(body, offset, bnnz, layer["bias_index_dtype"])
        bv, offset = unpack_values(body, offset, bnnz, layer["bias_dtype"])
        if not ptr or ptr[0] != 0 or ptr[-1] != nnz or any(a > b for a, b in zip(ptr, ptr[1:])):
            raise ValueError("CSR binary pointers invalid")
        rows_all.append([[(inds[k], vals[k]) for k in range(ptr[r], ptr[r + 1])] for r in range(ow)])
        biases_all.append(list(zip(bi, bv)))
    if offset != len(body):
        raise ValueError("CSR binary trailing bytes")
    result = make_sparse(header, rows_all, biases_all)
    if result.stored_parameter_count != header["stored_parameter_count"]:
        raise ValueError("CSR binary count mismatch")
    return result


def encode_rowmask_binary(model: SparseTransitionReLUNetwork) -> bytes:
    heads, body = [], bytearray()
    for li, (rows, biases) in enumerate(zip(model.sparse_weights, model.sparse_biases)):
        iw, ow = model.architecture[li:li + 2]
        masks, vals = [], []
        for row in rows:
            mask = 0
            for index, value in row:
                mask |= 1 << index
                vals.append(value)
            masks.append(mask)
        bm, bv = 0, []
        for index, value in biases:
            bm |= 1 << index
            bv.append(value)
        wt, bt = scalar_dtype(vals), scalar_dtype(bv)
        for mask in masks:
            body.extend(pack_mask(mask, iw))
        body.extend(pack_values(vals, wt))
        body.extend(pack_mask(bm, ow))
        body.extend(pack_values(bv, bt))
        heads.append({"input_width": iw, "output_width": ow, "nnz": len(vals), "bias_nnz": len(bv), "weight_dtype": wt, "bias_dtype": bt})
    return pack_envelope({"schema": "sre002.rowmask-binary.v1", "encoding": "rowmask_binary", **meta(model), "layers": heads, "stored_parameter_count": model.stored_parameter_count}, bytes(body))


def decode_rowmask_binary(payload: bytes) -> SparseTransitionReLUNetwork:
    header, body = unpack_envelope(payload)
    if header.get("schema") != "sre002.rowmask-binary.v1":
        raise ValueError("unsupported row-mask binary schema")
    offset, rows_all, biases_all = 0, [], []
    for layer in header["layers"]:
        iw, ow = layer["input_width"], layer["output_width"]
        masks = []
        for _ in range(ow):
            mask, offset = unpack_mask(body, offset, iw)
            masks.append(mask)
        vals, offset = unpack_values(body, offset, layer["nnz"], layer["weight_dtype"])
        cursor, rows = 0, []
        for mask in masks:
            indices = [i for i in range(iw) if mask & (1 << i)]
            count = len(indices)
            rows.append(list(zip(indices, vals[cursor:cursor + count])))
            cursor += count
        if cursor != layer["nnz"]:
            raise ValueError("row-mask binary weight count mismatch")
        bm, offset = unpack_mask(body, offset, ow)
        bv, offset = unpack_values(body, offset, layer["bias_nnz"], layer["bias_dtype"])
        bi = [i for i in range(ow) if bm & (1 << i)]
        if len(bi) != layer["bias_nnz"]:
            raise ValueError("row-mask binary bias count mismatch")
        rows_all.append(rows)
        biases_all.append(list(zip(bi, bv)))
    if offset != len(body):
        raise ValueError("row-mask binary trailing bytes")
    result = make_sparse(header, rows_all, biases_all)
    if result.stored_parameter_count != header["stored_parameter_count"]:
        raise ValueError("row-mask binary count mismatch")
    return result


def encode_hybrid_binary(model: SparseTransitionReLUNetwork) -> bytes:
    heads, body = [], bytearray()
    for li, (rows, biases) in enumerate(zip(model.sparse_weights, model.sparse_biases)):
        iw, ow = model.architecture[li:li + 2]
        all_w, all_b = [v for row in rows for _, v in row], [v for _, v in biases]
        wt, bt = scalar_dtype(all_w), scalar_dtype(all_b)
        vsize, msize, dense_cost = SWIDTH[wt], (iw + 7) // 8, iw * SWIDTH[wt]
        mode_bytes = (ow + 7) // 8
        sparse_rows = [msize + len(row) * vsize < dense_cost for row in rows]
        savings = sum(dense_cost - (msize + len(row) * vsize) for row, flag in zip(rows, sparse_rows) if flag)
        if savings <= mode_bytes:
            sparse_rows = [False] * ow
        mode = sum((1 << i) for i, flag in enumerate(sparse_rows) if flag)
        body.extend(pack_mask(mode, ow))
        for row, flag in zip(rows, sparse_rows):
            if flag:
                mask, vals = 0, []
                for index, value in row:
                    mask |= 1 << index
                    vals.append(value)
                body.extend(pack_mask(mask, iw))
                body.extend(pack_values(vals, wt))
            else:
                dense = [0.0] * iw
                for index, value in row:
                    dense[index] = value
                body.extend(pack_values(dense, wt))
        bm = sum((1 << i) for i, _ in biases)
        sparse_bias = ((ow + 7) // 8 + len(biases) * SWIDTH[bt]) < ow * SWIDTH[bt]
        if sparse_bias:
            body.extend(pack_mask(bm, ow))
            body.extend(pack_values(all_b, bt))
        else:
            dense_b = [0.0] * ow
            for index, value in biases:
                dense_b[index] = value
            body.extend(pack_values(dense_b, bt))
        heads.append({"input_width": iw, "output_width": ow, "weight_dtype": wt, "bias_dtype": bt, "sparse_row_count": sum(sparse_rows), "sparse_bias": sparse_bias})
    return pack_envelope({"schema": "sre002.hybrid-binary.v1", "encoding": "hybrid_binary", **meta(model), "layers": heads, "stored_parameter_count": model.stored_parameter_count}, bytes(body))


def decode_hybrid_binary(payload: bytes) -> SparseTransitionReLUNetwork:
    header, body = unpack_envelope(payload)
    if header.get("schema") != "sre002.hybrid-binary.v1":
        raise ValueError("unsupported hybrid binary schema")
    offset, rows_all, biases_all = 0, [], []
    for layer in header["layers"]:
        iw, ow = layer["input_width"], layer["output_width"]
        mode, offset = unpack_mask(body, offset, ow)
        rows = []
        for row_index in range(ow):
            if mode & (1 << row_index):
                mask, offset = unpack_mask(body, offset, iw)
                vals, offset = unpack_values(body, offset, mask.bit_count(), layer["weight_dtype"])
                ids = [i for i in range(iw) if mask & (1 << i)]
                rows.append(list(zip(ids, vals)))
            else:
                vals, offset = unpack_values(body, offset, iw, layer["weight_dtype"])
                rows.append([(i, v) for i, v in enumerate(vals) if v != 0.0])
        if mode.bit_count() != layer["sparse_row_count"]:
            raise ValueError("hybrid sparse row count mismatch")
        if layer["sparse_bias"]:
            bm, offset = unpack_mask(body, offset, ow)
            bv, offset = unpack_values(body, offset, bm.bit_count(), layer["bias_dtype"])
            bi = [i for i in range(ow) if bm & (1 << i)]
            biases = list(zip(bi, bv))
        else:
            bv, offset = unpack_values(body, offset, ow, layer["bias_dtype"])
            biases = [(i, v) for i, v in enumerate(bv) if v != 0.0]
        rows_all.append(rows)
        biases_all.append(biases)
    if offset != len(body):
        raise ValueError("hybrid binary trailing bytes")
    result = make_sparse(header, rows_all, biases_all)
    if result.stored_parameter_count != header["stored_parameter_count"]:
        raise ValueError("hybrid binary count mismatch")
    return result


def encode_dense_binary(dense: Any, sparse: SparseTransitionReLUNetwork) -> bytes:
    weights = [v for layer in dense.weights for row in layer for v in row]
    biases = [v for layer in dense.biases for v in layer]
    wt, bt = scalar_dtype(weights), scalar_dtype(biases)
    body, heads = bytearray(), []
    for matrix, bias, iw, ow in zip(dense.weights, dense.biases, dense.architecture[:-1], dense.architecture[1:]):
        for row in matrix:
            body.extend(pack_values(row, wt))
        body.extend(pack_values(bias, bt))
        heads.append({"input_width": iw, "output_width": ow})
    return pack_envelope({
        "schema": "sre002.dense-binary.v1", "encoding": "dense_binary",
        **meta(sparse), "layers": heads, "weight_dtype": wt, "bias_dtype": bt,
        "dense_parameter_count": dense.parameter_count, "dense_model_digest": dense.digest,
    }, bytes(body))


def decode_dense_binary(payload: bytes):
    header, body = unpack_envelope(payload)
    if header.get("schema") != "sre002.dense-binary.v1":
        raise ValueError("unsupported dense binary schema")
    offset, matrices, biases = 0, [], []
    for layer in header["layers"]:
        iw, ow = layer["input_width"], layer["output_width"]
        matrix = []
        for _ in range(ow):
            row, offset = unpack_values(body, offset, iw, header["weight_dtype"])
            matrix.append(tuple(row))
        bias, offset = unpack_values(body, offset, ow, header["bias_dtype"])
        matrices.append(tuple(matrix))
        biases.append(tuple(bias))
    if offset != len(body):
        raise ValueError("dense binary trailing bytes")
    return header, tuple(matrices), tuple(biases)


def forward_dense(weights, biases, inputs):
    values = [float(v) for v in inputs]
    for layer_index, (matrix, bias) in enumerate(zip(weights, biases)):
        outputs = [sum(w * v for w, v in zip(row, values)) + bias[i] for i, row in enumerate(matrix)]
        values = [max(0.0, v) for v in outputs] if layer_index < len(weights) - 1 else outputs
    return tuple(values)


def contract_for(workload, table, compiler, encoding, dense, sparse, payload):
    source = RepresentationRef.from_payload("mailcpu.dense-finite-transition-relu", 1, dense.snapshot())
    target = RepresentationRef.from_payload("mailcpu.sparse-transition-encoded", 1, {
        "encoding": encoding, "payload_sha256": sha_bytes(payload),
        "decoded_sparse_digest": sparse.digest, "snapshot": sparse.snapshot(),
    })
    mapping = RepresentationRef.from_payload("mailcpu.sparse-encoding-decoder", 1, {
        "compiler": COMPILERS[compiler], "workload": workload.name,
        "encoding": encoding, "payload_sha256": sha_bytes(payload),
        "decoded_sparse_digest": sparse.digest,
    })
    observation = ObservationContract.from_definition("mailcpu.finite-state-next-value", 1, {
        "output_fields": list(table.output_names), "value_domain": [0, 1],
        "comparison": "canonical-json-exact", "input_domain": f"{{0,1}}^{len(table.input_names)}",
    })
    return TranslationContract(
        contract_id=f"sre002-{workload.name}-{compiler}-{encoding}", revision=1,
        source=source, target=target, mapping=mapping, observation=observation,
        context_digest=canonical_value_digest({
            "program_digest": workload.program.digest, "table_digest": table.digest,
            "compiler": compiler, "encoding": encoding,
        }),
        precondition_digests=(canonical_value_digest({"input_domain": f"{{0,1}}^{len(table.input_names)}"}),),
        invariant_digests=(canonical_value_digest({"output_domain": f"{{0,1}}^{len(table.output_names)}"}),),
        resource_bounds=(
            ResourceBound("dense_parameters", dense.parameter_count, "scalar-parameter-slots"),
            ResourceBound("sparse_parameters", sparse.stored_parameter_count, "stored-nonzero-parameters"),
            ResourceBound("encoded_bytes", len(payload), "serialized-bytes"),
        ),
        effect_class=EffectClass.PURE, replay_class=ReplayClass.DETERMINISTIC,
    )


def measure(function, repeats=REPEATS):
    first = function()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        value = function()
        samples.append(time.perf_counter_ns() - start)
        if isinstance(first, bytes):
            if value != first:
                raise AssertionError("encoder output is not deterministic")
        elif hasattr(first, "digest"):
            if value.digest != first.digest:
                raise AssertionError("decoder output is not deterministic")
        elif value != first:
            raise AssertionError("codec result is not deterministic")
    return {"sample_count": len(samples), "samples_ns": samples, "median_ns": int(statistics.median(samples)), "minimum_ns": min(samples), "maximum_ns": max(samples)}


def codec_table(model):
    return {
        "coo_json": (encode_coo(model), decode_coo, lambda: encode_coo(model)),
        "csr_json": (encode_csr_json(model), decode_csr_json, lambda: encode_csr_json(model)),
        "rowmask_json": (encode_rowmask_json(model), decode_rowmask_json, lambda: encode_rowmask_json(model)),
        "csr_binary": (encode_csr_binary(model), decode_csr_binary, lambda: encode_csr_binary(model)),
        "rowmask_binary": (encode_rowmask_binary(model), decode_rowmask_binary, lambda: encode_rowmask_binary(model)),
        "hybrid_binary": (encode_hybrid_binary(model), decode_hybrid_binary, lambda: encode_hybrid_binary(model)),
    }


def compile_models(program, table):
    return {
        "minterm": rcn.compile_transition_table(table),
        "direct_dag": rcn.compile_compositional_transition_program(program),
        "live_dag": rcn.compile_live_compositional_transition_program(program),
    }


def verify_workload(workload):
    program, table = workload.program, workload.program.to_table()
    inputs_all = [tuple(row.inputs) for row in table.rows]
    expected_all = []
    for values in inputs_all:
        expected = workload.reference(values)
        if program.evaluate(values) != expected or table.row_for(values).outputs != expected:
            raise AssertionError(f"source descriptions disagree: {workload.name}/{values}")
        expected_all.append(expected)
    route_results = []
    for compiler, dense in compile_models(program, table).items():
        sparse = SparseTransitionReLUNetwork.from_dense(dense)
        dense_json_bytes = len(canonical(dense.snapshot()))
        dense_binary = encode_dense_binary(dense, sparse)
        dense_header, dense_weights, dense_biases = decode_dense_binary(dense_binary)
        if dense_weights != dense.weights or dense_biases != dense.biases:
            raise AssertionError("dense binary tensor reconstruction mismatch")
        dense_rows = []
        for values, expected in zip(inputs_all, expected_all):
            decoded = tuple(int(round(v)) for v in forward_dense(dense_weights, dense_biases, values))
            if decoded != expected or dense.predict(values) != expected:
                raise AssertionError("dense binary forward output mismatch")
            dense_rows.append({"inputs": list(values), "outputs": list(decoded)})
        enc_results = []
        for encoding, (payload, decoder, encoder) in codec_table(sparse).items():
            decoded_sparse = decoder(payload)
            if decoded_sparse.digest != sparse.digest:
                raise AssertionError(f"{encoding} failed sparse model round trip")
            encode_time = measure(encoder)
            decode_time = measure(lambda dec=decoder, raw=payload: dec(raw))
            contract = contract_for(workload, table, compiler, encoding, dense, decoded_sparse, payload)
            case_records, contract_digests = [], []
            for row_index, (values, expected) in enumerate(zip(inputs_all, expected_all)):
                dense_out, sparse_out = dense.predict(values), decoded_sparse.predict(values)
                if dense_out != expected or sparse_out != expected:
                    raise AssertionError(f"decoded {encoding} output mismatch: {workload.name}/{compiler}/{row_index}")
                comparison = compare_projected_observations(
                    contract,
                    case_payload={
                        "program_digest": program.digest,
                        "table_digest": table.digest,
                        "input_registers": dict(zip(table.input_names, values)),
                    },
                    source_observation=dict(zip(table.output_names, dense_out)),
                    target_observation=dict(zip(table.output_names, sparse_out)),
                )
                if not comparison.equivalent:
                    raise AssertionError(f"{encoding} translation mismatch: {workload.name}/{compiler}/{row_index}")
                contract_digests.append(comparison.contract_digest)
                case_records.append({
                    "row_index": row_index, "inputs": list(values),
                    "outputs": list(expected),
                    "translation_contract_digest": comparison.contract_digest,
                })
            enc_results.append({
                "encoding": encoding, "encoded_bytes": len(payload),
                "encoded_sha256": sha_bytes(payload),
                "decoded_sparse_digest": decoded_sparse.digest,
                "stored_parameter_count": decoded_sparse.stored_parameter_count,
                "reduction_vs_dense_json": 1.0 - len(payload) / dense_json_bytes if dense_json_bytes else 0.0,
                "reduction_vs_dense_binary": 1.0 - len(payload) / len(dense_binary) if dense_binary else 0.0,
                "round_trip_exact": True, "translation_comparison_count": len(case_records),
                "translation_contract_digest": sha(contract_digests),
                "case_evidence_digest": sha(case_records),
                "encode_timing": encode_time, "decode_timing": decode_time,
            })
        route_results.append({
            "compiler": compiler, "compiler_id": COMPILERS[compiler],
            "architecture": list(dense.architecture),
            "program_digest": program.digest, "table_digest": table.digest,
            "dense_model_digest": dense.digest, "sparse_model_digest": sparse.digest,
            "dense_parameter_count": dense.parameter_count,
            "dense_active_parameter_count": dense.active_parameter_count,
            "sparse_stored_parameter_count": sparse.stored_parameter_count,
            "dense_json_bytes": dense_json_bytes,
            "dense_binary_bytes": len(dense_binary),
            "dense_binary_dtype": {"weights": dense_header["weight_dtype"], "biases": dense_header["bias_dtype"]},
            "dense_binary_sha256": sha_bytes(dense_binary),
            "dense_binary_forward_digest": sha(dense_rows),
            "encodings": enc_results,
        })
    return {
        "name": workload.name, "family": workload.family,
        "description": workload.description,
        "input_width": len(program.input_names), "output_width": len(program.output_names),
        "complete_domain_rows": len(inputs_all),
        "program_digest": program.digest, "table_digest": table.digest,
        "routes": route_results,
        "translation_comparison_count": len(inputs_all) * len(route_results) * len(ENCODINGS),
        "all_encodings_round_trip_exactly": True,
    }


def run_experiment():
    results = [verify_workload(workload) for workload in rcn.build_workloads()]
    records = [
        {
            **encoding, "workload": workload["name"],
            "compiler": route["compiler"],
            "dense_json_bytes": route["dense_json_bytes"],
            "dense_binary_bytes": route["dense_binary_bytes"],
        }
        for workload in results for route in workload["routes"] for encoding in route["encodings"]
    ]
    summaries = {}
    for encoding in ENCODINGS:
        selected = [item for item in records if item["encoding"] == encoding]
        total = sum(item["encoded_bytes"] for item in selected)
        dense_json = sum(item["dense_json_bytes"] for item in selected)
        dense_binary = sum(item["dense_binary_bytes"] for item in selected)
        summaries[encoding] = {
            "model_artifact_count": len(selected), "encoded_bytes_sum": total,
            "dense_json_bytes_sum": dense_json, "dense_binary_bytes_sum": dense_binary,
            "reduction_vs_dense_json": 1.0 - total / dense_json if dense_json else 0.0,
            "reduction_vs_dense_binary": 1.0 - total / dense_binary if dense_binary else 0.0,
            "median_encode_time_ns": int(statistics.median(item["encode_timing"]["median_ns"] for item in selected)),
            "median_decode_time_ns": int(statistics.median(item["decode_timing"]["median_ns"] for item in selected)),
            "exact_round_trip_count": sum(item["round_trip_exact"] for item in selected),
        }
    payload = {
        "schema": "in-formation-space.sparse-encoding-landscape.sre002.v1",
        "experiment_id": "SRE-002", "status": "verified-within-complete-finite-domains",
        "source_revisions": {
            "ifs": os.environ.get("IFS_REVISION", "unspecified-local-checkout"),
            "ecpu": os.environ.get("ECPU_REVISION", "unspecified-local-checkout"),
            "vgi": os.environ.get("VGI_REVISION", "unspecified-local-checkout"),
        },
        "environment": {
            "python": platform.python_version(), "platform": platform.platform(),
            "processor": platform.processor(),
            "clock": {
                "implementation": time.get_clock_info("perf_counter").implementation,
                "monotonic": time.get_clock_info("perf_counter").monotonic,
                "resolution": time.get_clock_info("perf_counter").resolution,
            },
            "timing_repeats": REPEATS,
        },
        "workload_count": len(results),
        "complete_input_rows_verified": sum(item["complete_domain_rows"] for item in results),
        "compiler_model_pair_count": sum(len(item["routes"]) for item in results),
        "encoding_count": len(ENCODINGS),
        "dense_to_encoding_translation_comparisons": sum(item["translation_comparison_count"] for item in results),
        "all_encodings_round_trip_exactly": True,
        "encoding_summaries": summaries, "encoding_evidence_digest": sha(records),
        "limitations": [
            "Only the 16 selected RCN-001 workloads and their complete Boolean domains are covered.",
            "Canonical JSON and binary byte counts measure serialized payload, not resident memory or transport throughput.",
            "Int8 is selected only for exact integer coefficients in [-128, 127]; otherwise float64 preserves values exactly.",
            "The binary formats are prototypes and are not integrated into E-CPU runtime or communication transport.",
            "Encode/decode times are local Python host observations, not hardware or production benchmarks.",
            "No lossy quantization, compression library, GPU kernel, or distributed execution is introduced.",
        ],
        "workloads": results,
    }
    payload["result_digest"] = sha(payload)
    return payload


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_experiment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "experiment_id": result["experiment_id"], "status": result["status"],
        "workloads": result["workload_count"],
        "input_rows": result["complete_input_rows_verified"],
        "model_pairs": result["compiler_model_pair_count"],
        "encodings": result["encoding_count"],
        "comparisons": result["dense_to_encoding_translation_comparisons"],
        "result_digest": result["result_digest"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
