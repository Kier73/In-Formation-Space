"""Basis-invariant Q/K/V singular-spectrum comparison for selected GPT-2 layers.

This module calculates full singular-value spectra from the same explicit,
bounded payload allowlist used by HFR-001. It emits only derived spectra and
summary evidence, never tensor arrays.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

SPECTRAL_SCHEMA = "in-formation-space.qkv-spectral-invariants.v0.1"
ROLES = ("query", "key", "value")
TOP_ENERGY_COUNTS = (1, 8, 32, 64, 128)
SINGULAR_QUANTILES = (0, 5, 25, 50, 75, 95, 100)


class SpectralInvariantError(ValueError):
    """Raised when source evidence or a spectral comparison is invalid."""


def _prepare_matrices(
    nsd: dict[str, Any],
    payloads: dict[str, bytes],
    evidence: list[dict[str, Any]],
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]]]:
    if not isinstance(nsd, dict) or nsd.get("schema") != "in-formation-space.neural-structure-description.v0.1":
        raise SpectralInvariantError("input must be a Neural Structure Description v0.1")
    source = nsd.get("source")
    if not isinstance(source, dict):
        raise SpectralInvariantError("NSD source provenance is missing")
    if not isinstance(evidence, list) or len(evidence) != 2:
        raise SpectralInvariantError("exactly two selected tensor evidence records are required")
    if not isinstance(payloads, dict):
        raise SpectralInvariantError("selected tensor payloads must be a dictionary")

    matrices: dict[str, np.ndarray] = {}
    records: dict[str, dict[str, Any]] = {}
    for record in evidence:
        if not isinstance(record, dict):
            raise SpectralInvariantError("every tensor evidence record must be an object")
        name = record.get("name")
        shape = record.get("shape")
        if not isinstance(name, str) or not name:
            raise SpectralInvariantError("tensor evidence needs a non-empty name")
        if name in records:
            raise SpectralInvariantError(f"duplicate selected tensor evidence: {name}")
        if not isinstance(shape, list) or len(shape) != 2 or any(
            type(dimension) is not int or dimension <= 0 for dimension in shape
        ):
            raise SpectralInvariantError(f"{name}: expected a positive two-dimensional shape")
        if record.get("dtype") != "F32":
            raise SpectralInvariantError(f"{name}: v0.1 supports only F32 selected tensors")
        expected_bytes = shape[0] * shape[1] * 4
        if record.get("size_bytes") != expected_bytes:
            raise SpectralInvariantError(f"{name}: evidence size does not match its F32 shape")
        digest = record.get("payload_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpectralInvariantError(f"{name}: payload hash is missing or malformed")
        raw = payloads.get(name)
        if not isinstance(raw, bytes) or len(raw) != expected_bytes:
            raise SpectralInvariantError(f"{name}: payload bytes are missing or have the wrong size")
        if hashlib.sha256(raw).hexdigest() != digest:
            raise SpectralInvariantError(f"{name}: payload SHA-256 mismatch")
        matrix = np.frombuffer(raw, dtype="<f4").reshape(shape)
        if not np.isfinite(matrix).all():
            raise SpectralInvariantError(f"{name}: payload contains NaN or infinity")
        if shape[1] % 3:
            raise SpectralInvariantError(f"{name}: fused QKV width must divide into three equal slices")
        matrices[name] = matrix
        records[name] = record

    names = sorted(matrices)
    if matrices[names[0]].shape != matrices[names[1]].shape:
        raise SpectralInvariantError("selected matrices must have matching shapes")
    return matrices, records


def _spectrum_summary(matrix: np.ndarray) -> dict[str, Any]:
    """Calculate exact singular values and basis-invariant distribution summaries."""
    # Use float64 LAPACK for numerical stability while input storage remains F32.
    singular_values = np.linalg.svd(
        matrix.astype(np.float64, copy=False),
        compute_uv=False,
        full_matrices=False,
    )
    if not np.isfinite(singular_values).all():
        raise SpectralInvariantError("SVD returned a non-finite singular value")
    energy = singular_values * singular_values
    total_energy = float(np.sum(energy))
    frobenius = float(np.sqrt(total_energy))
    largest = float(singular_values[0]) if singular_values.size else 0.0

    if total_energy > 0.0:
        probabilities = energy / total_energy
        positive = probabilities[probabilities > 0.0]
        entropy = float(-np.sum(positive * np.log(positive)))
        effective_rank = float(np.exp(entropy))
        participation_ratio = float(1.0 / np.sum(probabilities * probabilities))
        normalized = singular_values / frobenius
    else:
        probabilities = np.zeros_like(energy)
        effective_rank = None
        participation_ratio = None
        normalized = np.zeros_like(singular_values)

    quantiles = np.percentile(singular_values, SINGULAR_QUANTILES)
    top_energy = {
        str(count): (
            min(1.0, float(np.sum(energy[: min(count, energy.size)]) / total_energy))
            if total_energy > 0.0
            else None
        )
        for count in TOP_ENERGY_COUNTS
    }
    return {
        "shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        "rank_bound": int(min(matrix.shape)),
        "singular_values": [float(value) for value in singular_values],
        "frobenius_normalized_singular_values": [float(value) for value in normalized],
        "singular_value_quantiles": {
            str(percentile): float(value)
            for percentile, value in zip(SINGULAR_QUANTILES, quantiles)
        },
        "frobenius_norm": frobenius,
        "spectral_norm": largest,
        "stable_rank": float(total_energy / (largest * largest)) if largest > 0.0 else None,
        "entropy_effective_rank": effective_rank,
        "participation_ratio": participation_ratio,
        "top_singular_energy_fraction": top_energy,
        "singular_value_count": int(singular_values.size),
    }


def _spectrum_distance(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    a = np.asarray(left["frobenius_normalized_singular_values"], dtype=np.float64)
    b = np.asarray(right["frobenius_normalized_singular_values"], dtype=np.float64)
    if a.shape != b.shape:
        raise SpectralInvariantError("normalized spectra must have equal lengths")
    p = a * a
    q = b * b
    p_total = float(p.sum())
    q_total = float(q.sum())
    if p_total > 0.0:
        p = p / p_total
    if q_total > 0.0:
        q = q / q_total
    midpoint = (p + q) * 0.5

    def kl_divergence(first: np.ndarray, second: np.ndarray) -> float:
        mask = first > 0.0
        return float(np.sum(first[mask] * np.log2(first[mask] / second[mask])))

    js = (
        min(1.0, 0.5 * kl_divergence(p, midpoint) + 0.5 * kl_divergence(q, midpoint))
        if p_total > 0.0 and q_total > 0.0
        else None
    )
    return {
        "mean_absolute_frobenius_normalized_singular_value_distance": float(np.mean(np.abs(a - b))),
        "root_mean_square_frobenius_normalized_singular_value_distance": float(np.sqrt(np.mean((a - b) ** 2))),
        "squared_energy_jensen_shannon_divergence_bits": js,
        "interpretation": (
            "distance between singular-value distributions; invariant under orthogonal "
            "left/right basis changes, but not a proof of equal input-output functions"
        ),
    }


def analyze_qkv_spectral_invariants(
    nsd: dict[str, Any],
    payloads: dict[str, bytes],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare exact Q/K/V singular spectra for two matching selected layers."""
    matrices, records = _prepare_matrices(nsd, payloads, evidence)
    names = sorted(matrices)
    spectra: dict[str, dict[str, Any]] = {}
    slices: dict[str, dict[str, np.ndarray]] = {}

    for name in names:
        matrix = matrices[name]
        width = matrix.shape[1] // 3
        slices[name] = {}
        spectra[name] = {
            "tensor_evidence": {
                "payload_sha256": records[name]["payload_sha256"],
                "payload_sha256_scope": records[name]["payload_sha256_scope"],
                "shard_header_sha256": records[name]["shard_header_sha256"],
                "size_bytes": records[name]["size_bytes"],
                "absolute_byte_range": records[name]["absolute_byte_range"],
            },
            "qkv": {},
        }
        for index, role in enumerate(ROLES):
            part = matrix[:, index * width : (index + 1) * width]
            slices[name][role] = part
            spectra[name]["qkv"][role] = _spectrum_summary(part)

    first, last = names
    comparisons = {
        role: _spectrum_distance(
            spectra[first]["qkv"][role],
            spectra[last]["qkv"][role],
        )
        for role in ROLES
    }
    return {
        "schema": SPECTRAL_SCHEMA,
        "source_observation": {
            "repository": nsd["source"].get("repository"),
            "revision": nsd["source"].get("revision"),
            "license_id": nsd["source"].get("license_id"),
        },
        "method": {
            "selected_tensor_names": names,
            "projection_partition": ["query", "key", "value"],
            "svd_method": "numpy.linalg.svd(compute_uv=False) in float64",
            "normalization": "divide singular values by the matrix Frobenius norm",
            "basis_invariance": (
                "singular values are unchanged under orthogonal multiplication "
                "on the left or right"
            ),
            "comparison_metrics": [
                "mean absolute distance between Frobenius-normalized singular spectra",
                "root-mean-square distance between Frobenius-normalized singular spectra",
                "Jensen-Shannon divergence between normalized squared-singular-value energy distributions",
            ],
            "raw_payload_policy": "selected tensor bytes are analyzed in memory and are not included in this output",
        },
        "dimensions": {
            "matrix_input_width": int(matrices[first].shape[0]),
            "fused_qkv_output_width": int(matrices[first].shape[1]),
            "per_projection_output_width": int(matrices[first].shape[1] // 3),
            "singular_values_per_projection": int(min(matrices[first].shape[0], matrices[first].shape[1] // 3)),
        },
        "spectra": spectra,
        "cross_layer_spectral_comparisons": comparisons,
        "interpretation": {
            "status": "basis-invariant-linear-parameter-structure",
            "claims": [
                "The singular-value spectra describe each selected linear projection's scale distribution and effective dimensional concentration.",
                "Frobenius-normalized spectra compare spectral shape after removing overall matrix scale.",
                "Singular values are invariant under independent orthogonal changes of row and column coordinates for each matrix.",
            ],
            "not_established": [
                "equivalence of the first and last layer functions",
                "equivalence under arbitrary non-orthogonal basis changes",
                "causal or semantic importance of a projection",
                "existence or quality of a procedural replacement parameterization",
            ],
        },
    }
