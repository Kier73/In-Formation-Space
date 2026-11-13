"""Deterministic descriptive geometry for selected dense GPT-2 weight matrices.

This module never persists or emits tensor values. It returns numeric summaries
and provenance hashes for an explicit, bounded list of selected tensors.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

GEOMETRY_SCHEMA = "in-formation-space.selected-weight-geometry.v0.1"
ROLES = ("query", "key", "value")
POWER_ITERATIONS = 16
NEAR_ZERO_THRESHOLD = 1e-6


class WeightGeometryError(ValueError):
    """Raised when selected tensor bytes or observation records are inconsistent."""


def _validate_record(record: dict[str, Any]) -> tuple[str, tuple[int, int], str]:
    name = record.get("name")
    shape = record.get("shape")
    dtype = record.get("dtype")
    size = record.get("size_bytes")
    digest = record.get("payload_sha256")
    if not isinstance(name, str) or not name:
        raise WeightGeometryError("tensor evidence needs a non-empty name")
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(type(value) is not int or value <= 0 for value in shape)
    ):
        raise WeightGeometryError(f"{name}: selected weight must be a positive 2D matrix")
    if dtype != "F32":
        raise WeightGeometryError(f"{name}: v0.1 geometry analyzer supports only F32")
    expected_size = shape[0] * shape[1] * 4
    if size != expected_size:
        raise WeightGeometryError(f"{name}: evidence byte count does not match its F32 shape")
    if not isinstance(digest, str) or len(digest) != 64:
        raise WeightGeometryError(f"{name}: payload SHA-256 is missing or malformed")
    return name, (shape[0], shape[1]), digest


def _power_spectral_norm(matrix: np.ndarray, seed_material: str) -> float:
    """Estimate the largest singular value by deterministic power iteration."""
    seed = int.from_bytes(hashlib.sha256(seed_material.encode("utf-8")).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    vector = rng.standard_normal(matrix.shape[1]).astype(np.float32)
    vector_norm = float(np.linalg.norm(vector))
    if vector_norm == 0.0:
        raise WeightGeometryError("deterministic spectral initialization produced a zero vector")
    vector /= vector_norm

    for _ in range(POWER_ITERATIONS):
        left = matrix @ vector
        right = matrix.T @ left
        norm = float(np.linalg.norm(right))
        if norm == 0.0:
            return 0.0
        vector = right / norm

    return float(np.linalg.norm(matrix @ vector))


def _matrix_summary(matrix: np.ndarray, label: str) -> dict[str, Any]:
    matrix64 = matrix.astype(np.float64, copy=False)
    frobenius = float(np.linalg.norm(matrix64))
    spectral = _power_spectral_norm(matrix, label)
    if not np.isfinite(matrix64).all():
        raise WeightGeometryError(f"{label}: selected tensor contains non-finite values")

    row_norms = np.linalg.norm(matrix64, axis=1)
    column_norms = np.linalg.norm(matrix64, axis=0)
    total = int(matrix.size)
    zeros = int(np.count_nonzero(matrix == 0.0))
    near_zeros = int(np.count_nonzero(np.abs(matrix) <= NEAR_ZERO_THRESHOLD))
    return {
        "shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        "element_count": total,
        "mean": float(np.mean(matrix64)),
        "standard_deviation": float(np.std(matrix64)),
        "minimum": float(np.min(matrix64)),
        "maximum": float(np.max(matrix64)),
        "frobenius_norm": frobenius,
        "approximate_spectral_norm": spectral,
        "spectral_norm_method": "deterministic-power-iteration",
        "spectral_norm_iterations": POWER_ITERATIONS,
        "approximate_stable_rank": (
            float((frobenius * frobenius) / (spectral * spectral))
            if spectral > 0.0
            else None
        ),
        "exact_zero_fraction": zeros / total,
        "near_zero_fraction_at_1e-6": near_zeros / total,
        "mean_row_l2_norm": float(np.mean(row_norms)),
        "std_row_l2_norm": float(np.std(row_norms)),
        "mean_column_l2_norm": float(np.mean(column_norms)),
        "std_column_l2_norm": float(np.std(column_norms)),
    }


def _pair_comparison(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    left64 = left.astype(np.float64, copy=False).reshape(-1)
    right64 = right.astype(np.float64, copy=False).reshape(-1)
    if left64.shape != right64.shape:
        raise WeightGeometryError("cross-layer comparison requires matching tensor shapes")
    left_norm = float(np.linalg.norm(left64))
    right_norm = float(np.linalg.norm(right64))
    denominator = left_norm * right_norm
    cosine = (
        float(np.dot(left64, right64) / denominator)
        if denominator > 0.0
        else None
    )
    relative_distance = (
        float(np.linalg.norm(left64 - right64) / left_norm)
        if left_norm > 0.0
        else None
    )
    return {
        "cosine_similarity": cosine,
        "relative_frobenius_distance_to_first": relative_distance,
        "frobenius_norm_first": left_norm,
        "frobenius_norm_second": right_norm,
        "interpretation": "descriptive parameter-space comparison; not functional equivalence",
    }


def analyze_selected_weight_geometry(
    nsd: dict[str, Any],
    payloads: dict[str, bytes],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize two matching fused GPT-2 QKV matrices and compare Q/K/V slices."""
    if not isinstance(nsd, dict) or nsd.get("schema") != "in-formation-space.neural-structure-description.v0.1":
        raise WeightGeometryError("input must be an NSD v0.1 observation")
    source = nsd.get("source")
    if not isinstance(source, dict):
        raise WeightGeometryError("NSD source provenance is missing")

    if not isinstance(evidence, list) or not evidence:
        raise WeightGeometryError("selected tensor evidence is required")
    records: dict[str, dict[str, Any]] = {}
    for record in evidence:
        if not isinstance(record, dict):
            raise WeightGeometryError("every selected tensor evidence record must be an object")
        name, shape, digest = _validate_record(record)
        if name in records:
            raise WeightGeometryError(f"duplicate selected tensor evidence: {name}")
        records[name] = record
        raw = payloads.get(name)
        if not isinstance(raw, bytes):
            raise WeightGeometryError(f"{name}: selected tensor payload is missing")
        if len(raw) != record["size_bytes"]:
            raise WeightGeometryError(f"{name}: payload length does not match its evidence")
        if hashlib.sha256(raw).hexdigest() != digest:
            raise WeightGeometryError(f"{name}: payload SHA-256 does not match its evidence")

    layer_names = sorted(records)
    if len(layer_names) != 2:
        raise WeightGeometryError("v0.1 requires exactly two selected matrices for cross-layer comparison")
    arrays: dict[str, np.ndarray] = {}
    for name in layer_names:
        shape = tuple(records[name]["shape"])
        if shape[1] % 3:
            raise WeightGeometryError(f"{name}: fused QKV width must divide evenly into three")
        array = np.frombuffer(payloads[name], dtype="<f4")
        if array.size != shape[0] * shape[1]:
            raise WeightGeometryError(f"{name}: F32 element count does not match matrix shape")
        matrix = array.reshape(shape)
        if not np.isfinite(matrix).all():
            raise WeightGeometryError(f"{name}: selected matrix contains NaN or infinity")
        arrays[name] = matrix

    first, second = layer_names
    if arrays[first].shape != arrays[second].shape:
        raise WeightGeometryError("selected first/last layer matrices must have equal shapes")

    hidden_width = arrays[first].shape[1] // 3
    expected_shapes = [arrays[first].shape[0], 3 * hidden_width]
    matrix_summaries: dict[str, Any] = {}
    slices: dict[str, dict[str, np.ndarray]] = {}
    for name in layer_names:
        matrix = arrays[name]
        if matrix.shape != tuple(expected_shapes):
            raise WeightGeometryError(f"{name}: fused projection shape is inconsistent")
        matrix_summaries[name] = {
            "tensor_evidence": {
                "payload_sha256": records[name]["payload_sha256"],
                "payload_sha256_scope": records[name]["payload_sha256_scope"],
                "size_bytes": records[name]["size_bytes"],
                "shard_header_sha256": records[name]["shard_header_sha256"],
                "absolute_byte_range": records[name]["absolute_byte_range"],
            },
            "fused_qkv": _matrix_summary(matrix, name + ":fused-qkv"),
            "slices": {},
        }
        slices[name] = {}
        for index, role in enumerate(ROLES):
            part = matrix[:, index * hidden_width : (index + 1) * hidden_width]
            slices[name][role] = part
            matrix_summaries[name]["slices"][role] = _matrix_summary(part, name + ":" + role)

    comparisons = {
        "fused_qkv": _pair_comparison(arrays[first], arrays[second]),
        "q": _pair_comparison(slices[first]["query"], slices[second]["query"]),
        "k": _pair_comparison(slices[first]["key"], slices[second]["key"]),
        "v": _pair_comparison(slices[first]["value"], slices[second]["value"]),
    }
    return {
        "schema": GEOMETRY_SCHEMA,
        "source_observation": {
            "repository": source.get("repository"),
            "revision": source.get("revision"),
            "license_id": source.get("license_id"),
        },
        "method": {
            "selected_tensor_count": len(layer_names),
            "selected_tensor_names": layer_names,
            "dtype": "F32",
            "qkv_column_partition": ["query", "key", "value"],
            "matrix_layout": "Safetensors GPT-2 Conv1D checkpoint weight [input_width, 3 * hidden_width]",
            "near_zero_threshold": NEAR_ZERO_THRESHOLD,
            "spectral_norm_method": "deterministic-power-iteration",
            "spectral_norm_iterations": POWER_ITERATIONS,
            "retained_payload_policy": "raw selected tensor values are not included in this output",
        },
        "dimensions": {
            "input_width": int(arrays[first].shape[0]),
            "fused_output_width": int(arrays[first].shape[1]),
            "hidden_width_per_qkv_slice": int(hidden_width),
        },
        "tensor_summaries": matrix_summaries,
        "cross_layer_comparisons": comparisons,
        "interpretation": {
            "status": "descriptive-parameter-geometry-only",
            "claims": [
                "The summaries describe selected stored parameter arrays in their checkpoint coordinate system.",
                "Cosine similarity and relative Frobenius distance compare parameter coordinates and do not establish functional similarity.",
                "Stable rank is an estimate derived from the Frobenius norm and a deterministic power-iteration estimate of the spectral norm.",
            ],
            "not_established": [
                "learned semantic content",
                "causal contribution of any individual projection",
                "functional equivalence between layers",
                "ability to generate replacement parameters with retained behavior",
            ],
        },
    }
