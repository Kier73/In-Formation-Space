"""Tests for the five-point GPT-2 depth spectral profile."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

try:
    from .layer_spectral_profile import (
        EXPECTED_LAYERS,
        LayerSpectralProfileError,
        analyze_gpt2_layer_spectral_profile,
    )
except ImportError:
    from layer_spectral_profile import (
        EXPECTED_LAYERS,
        LayerSpectralProfileError,
        analyze_gpt2_layer_spectral_profile,
    )


def orthogonal_permutation() -> np.ndarray:
    return np.array(
        [[0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 0, 1], [0, 0, -1, 0]],
        dtype=np.float32,
    )


def make_inputs(*, orthogonal: bool = False):
    rng = np.random.default_rng(20261113)
    base_roles = [
        rng.normal(size=(4, 4)).astype(np.float32)
        for _ in range(3)
    ]
    left = orthogonal_permutation()
    right = np.array(
        [[0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, -1], [0, 1, 0, 0]],
        dtype=np.float32,
    )

    payloads: dict[str, bytes] = {}
    evidence: list[dict] = []
    for position, layer in enumerate(EXPECTED_LAYERS):
        if orthogonal:
            # All sampled layers have the same singular spectra but different coordinates.
            slices = [left @ role @ right for role in base_roles]
        else:
            slices = [
                (role + (position * 0.13)).astype(np.float32)
                for role in base_roles
            ]
        matrix = np.concatenate(slices, axis=1).astype("<f4")
        name = f"h.{layer}.attn.c_attn.weight"
        raw = matrix.tobytes(order="C")
        record = {
            "name": name,
            "shard": "model.safetensors",
            "dtype": "F32",
            "shape": list(matrix.shape),
            "size_bytes": len(raw),
            "absolute_byte_range": [100 + position * len(raw), 99 + (position + 1) * len(raw)],
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "payload_sha256_scope": "complete-selected-tensor-payload",
            "shard_header_sha256": "a" * 64,
            "shard_size_bytes": 1_000_000,
        }
        payloads[name] = raw
        evidence.append(record)

    nsd = {
        "schema": "in-formation-space.neural-structure-description.v0.1",
        "source": {
            "repository": "example-org/tiny-gpt2",
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "license_id": "mit",
        },
    }
    return nsd, payloads, evidence


class LayerSpectralProfileTests(unittest.TestCase):
    def test_profile_has_all_five_layers_and_all_pairwise_comparisons(self):
        nsd, payloads, evidence = make_inputs()
        result = analyze_gpt2_layer_spectral_profile(nsd, payloads, evidence)

        self.assertEqual(result["schema"], "in-formation-space.gpt2-layer-spectral-profile.v0.1")
        self.assertEqual([item["layer_index"] for item in result["layer_profile"]], list(EXPECTED_LAYERS))
        self.assertEqual(result["dimensions"]["sampled_layer_count"], 5)
        for role in ("query", "key", "value"):
            self.assertEqual(len(result["pairwise_spectral_comparisons"][role]), 10)
            self.assertEqual(len(result["adjacent_sample_transitions"][role]), 4)
        self.assertEqual(len(result["layer_profile"][0]["qkv_spectra"]["query"]["singular_values"]), 4)
        self.assertNotIn("payloads", result)
        self.assertNotIn("raw_weights", result)

        schema = json.loads(
            (Path(__file__).parent / "gpt2-layer-spectral-profile.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(result)

    def test_orthogonal_transforms_preserve_each_sampled_spectrum(self):
        nsd, payloads, evidence = make_inputs(orthogonal=True)
        result = analyze_gpt2_layer_spectral_profile(nsd, payloads, evidence)
        for role in ("query", "key", "value"):
            for comparison in result["pairwise_spectral_comparisons"][role]:
                self.assertLess(
                    comparison["mean_absolute_normalized_spectrum_distance"],
                    1e-6,
                )
                self.assertLess(
                    comparison["squared_energy_jensen_shannon_divergence_bits"],
                    1e-6,
                )

    def test_missing_depth_sample_is_rejected(self):
        nsd, payloads, evidence = make_inputs()
        with self.assertRaisesRegex(LayerSpectralProfileError, "exactly 5 selected"):
            analyze_gpt2_layer_spectral_profile(nsd, payloads, evidence[:-1])

    def test_wrong_layer_indices_are_rejected(self):
        nsd, payloads, evidence = make_inputs()
        evidence[1]["name"] = "h.2.attn.c_attn.weight"
        payloads["h.2.attn.c_attn.weight"] = payloads.pop("h.3.attn.c_attn.weight")
        with self.assertRaisesRegex(LayerSpectralProfileError, "must be"):
            analyze_gpt2_layer_spectral_profile(nsd, payloads, evidence)

    def test_payload_hash_mismatch_is_rejected(self):
        nsd, payloads, evidence = make_inputs()
        name = evidence[0]["name"]
        payloads[name] = payloads[name][:-1] + bytes([payloads[name][-1] ^ 1])
        with self.assertRaisesRegex(LayerSpectralProfileError, "SHA-256 mismatch"):
            analyze_gpt2_layer_spectral_profile(nsd, payloads, evidence)

    def test_selected_tensor_shape_must_be_common_across_sample(self):
        nsd, payloads, evidence = make_inputs()
        evidence[0]["shape"] = [2, 24]
        evidence[0]["size_bytes"] = 2 * 24 * 4
        with self.assertRaisesRegex(LayerSpectralProfileError, "same shape"):
            analyze_gpt2_layer_spectral_profile(nsd, payloads, evidence)


if __name__ == "__main__":
    unittest.main()
