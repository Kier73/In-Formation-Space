"""Five-point depth profile of GPT-2 Q/K/V singular spectra."""

from __future__ import annotations

import hashlib
import re
from itertools import combinations
from typing import Any

import numpy as np

from .spectral_invariants import (
    _spectrum_distance,
    _spectrum_summary,
)

PROFILE_SCHEMA = "in-formation-space.gpt2-layer-spectral-profile.v0.1"
EXPECTED_LAYERS = (0, 3, 6, 9, 11)
ROLES = ("query", "key", "value")
_LAYER_NAME = re.compile(r"^h\.(\d+)\.attn\.c_attn\.weight$")


class LayerSpectralProfileError(ValueError):
    """Raised when the selected GPT-2 layer profile is incomplete or inconsistent."""


def _layer_index(name: str) -> int:
    match = _LAYER_NAME.fullmatch(name)
    if match is None:
        raise LayerSpectralProfileError(
            f"expected a GPT-2 fused attention projection name, got {name!r}"
        )
    return int(match.group(1))


def analyze_gpt2_layer_spectral_profile(
    nsd: dict[str, Any],
    payloads: dict[str, bytes],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare Q/K/V spectral distributions at a fixed five-point depth sample."""
    if not isinstance(nsd, dict) or nsd.get("schema") != "in-formation-space.neural-structure-description.v0.1":
        raise LayerSpectralProfileError("input must be an NSD v0.1 observation")
    source = nsd.get("source")
    if not isinstance(source, dict):
        raise LayerSpectralProfileError("NSD source provenance is missing")
    if not isinstance(evidence, list) or len(evidence) != len(EXPECTED_LAYERS):
        raise LayerSpectralProfileError(
            f"exactly {len(EXPECTED_LAYERS)} selected layer records are required"
        )

    selected: dict[int, tuple[dict[str, Any], np.ndarray]] = {}
    for record in evidence:
        if not isinstance(record, dict):
            raise LayerSpectralProfileError("each selected tensor evidence record must be an object")
        name = record.get("name")
        if not isinstance(name, str):
            raise LayerSpectralProfileError("selected tensor evidence has no name")
        index = _layer_index(name)
        if index in selected:
            raise LayerSpectralProfileError(f"duplicate selected layer index: {index}")
        shape = record.get("shape")
        if (
            record.get("dtype") != "F32"
            or not isinstance(shape, list)
            or len(shape) != 2
            or any(type(dimension) is not int or dimension <= 0 for dimension in shape)
            or shape[1] % 3
        ):
            raise LayerSpectralProfileError(
                f"{name}: expected an F32 two-dimensional fused-QKV matrix, got "
                f"{record.get('dtype')} {shape}"
            )
        expected_size = shape[0] * shape[1] * 4
        if record.get("size_bytes") != expected_size:
            raise LayerSpectralProfileError(f"{name}: selected tensor byte count is inconsistent")
        digest = record.get("payload_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise LayerSpectralProfileError(f"{name}: payload SHA-256 is malformed")
        raw = payloads.get(name)
        if not isinstance(raw, bytes) or len(raw) != expected_size:
            raise LayerSpectralProfileError(f"{name}: payload is absent or has the wrong size")
        if hashlib.sha256(raw).hexdigest() != digest:
            raise LayerSpectralProfileError(f"{name}: payload SHA-256 mismatch")
        matrix = np.frombuffer(raw, dtype="<f4").reshape(shape)
        if not np.isfinite(matrix).all():
            raise LayerSpectralProfileError(f"{name}: payload contains NaN or infinity")
        selected[index] = (record, matrix)

    if tuple(sorted(selected)) != EXPECTED_LAYERS:
        raise LayerSpectralProfileError(
            f"selected layer indices must be {EXPECTED_LAYERS}, got {tuple(sorted(selected))}"
        )
    selected_shapes = {tuple(matrix.shape) for _, matrix in selected.values()}
    if len(selected_shapes) != 1:
        raise LayerSpectralProfileError("all selected projection matrices must have the same shape")
    input_width, fused_width = next(iter(selected_shapes))
    if input_width <= 0 or fused_width <= 0 or fused_width % 3:
        raise LayerSpectralProfileError("selected fused QKV matrix dimensions are invalid")
    projection_width = fused_width // 3

    profile: list[dict[str, Any]] = []
    layer_spectra: dict[int, dict[str, dict[str, Any]]] = {}
    for index in EXPECTED_LAYERS:
        record, matrix = selected[index]
        width = projection_width
        role_spectra: dict[str, dict[str, Any]] = {}
        for offset, role in enumerate(ROLES):
            projection = matrix[:, offset * width : (offset + 1) * width]
            role_spectra[role] = _spectrum_summary(projection)
        layer_spectra[index] = role_spectra
        profile.append(
            {
                "layer_index": index,
                "tensor_name": record["name"],
                "tensor_evidence": {
                    "payload_sha256": record["payload_sha256"],
                    "payload_sha256_scope": record["payload_sha256_scope"],
                    "shard_header_sha256": record["shard_header_sha256"],
                    "size_bytes": record["size_bytes"],
                    "absolute_byte_range": record["absolute_byte_range"],
                },
                "qkv_spectra": role_spectra,
            }
        )

    pairwise: dict[str, list[dict[str, Any]]] = {role: [] for role in ROLES}
    for role in ROLES:
        for first, second in combinations(EXPECTED_LAYERS, 2):
            distance = _spectrum_distance(
                layer_spectra[first][role],
                layer_spectra[second][role],
            )
            pairwise[role].append(
                {
                    "first_layer": first,
                    "second_layer": second,
                    "mean_absolute_normalized_spectrum_distance": distance[
                        "mean_absolute_frobenius_normalized_singular_value_distance"
                    ],
                    "root_mean_square_normalized_spectrum_distance": distance[
                        "root_mean_square_frobenius_normalized_singular_value_distance"
                    ],
                    "squared_energy_jensen_shannon_divergence_bits": distance[
                        "squared_energy_jensen_shannon_divergence_bits"
                    ],
                }
            )

    adjacent: dict[str, list[dict[str, Any]]] = {role: [] for role in ROLES}
    for role in ROLES:
        for first, second in zip(EXPECTED_LAYERS[:-1], EXPECTED_LAYERS[1:]):
            distance = _spectrum_distance(
                layer_spectra[first][role],
                layer_spectra[second][role],
            )
            adjacent[role].append(
                {
                    "from_layer": first,
                    "to_layer": second,
                    "mean_absolute_normalized_spectrum_distance": distance[
                        "mean_absolute_frobenius_normalized_singular_value_distance"
                    ],
                    "squared_energy_jensen_shannon_divergence_bits": distance[
                        "squared_energy_jensen_shannon_divergence_bits"
                    ],
                    "stable_rank_change": (
                        layer_spectra[second][role]["stable_rank"]
                        - layer_spectra[first][role]["stable_rank"]
                    ),
                    "entropy_effective_rank_change": (
                        layer_spectra[second][role]["entropy_effective_rank"]
                        - layer_spectra[first][role]["entropy_effective_rank"]
                    ),
                }
            )

    return {
        "schema": PROFILE_SCHEMA,
        "source_observation": {
            "repository": source.get("repository"),
            "revision": source.get("revision"),
            "license_id": source.get("license_id"),
        },
        "method": {
            "selected_layers": list(EXPECTED_LAYERS),
            "selection_rule": "fixed five-point sample across 12 GPT-2 transformer blocks: 0, 3, 6, 9, 11",
            "tensor_role": "fused QKV projection weight",
            "expected_tensor_shape": [input_width, fused_width],
            "selected_matrix_count": len(EXPECTED_LAYERS),
            "projection_partition": ["query", "key", "value"],
            "svd_method": "numpy.linalg.svd(compute_uv=False) in float64",
            "normalization": "divide singular values by each projection's Frobenius norm",
            "raw_payload_policy": "selected tensor bytes are analyzed in memory and are not included in this output",
        },
        "dimensions": {
            "model_layer_count": 12,
            "sampled_layer_count": len(EXPECTED_LAYERS),
            "hidden_width": input_width,
            "projection_width": projection_width,
            "singular_values_per_projection": min(input_width, projection_width),
        },
        "layer_profile": profile,
        "pairwise_spectral_comparisons": pairwise,
        "adjacent_sample_transitions": adjacent,
        "interpretation": {
            "status": "sampled-depth-spectral-profile",
            "claims": [
                "The sampled singular spectra describe selected Q/K/V projection scale distributions at five transformer depths.",
                "Stable rank and entropy effective rank summarize concentration of each projection's singular-value energy.",
                "Pairwise spectrum distances are invariant under orthogonal left/right transformations applied independently to each sampled matrix.",
            ],
            "not_established": [
                "the unsampled blocks follow the same pattern",
                "functional equivalence between any pair of layers",
                "alignment of latent coordinate systems",
                "semantic or causal importance of projections",
                "replacement parameters with preserved model behavior",
            ],
        },
    }
