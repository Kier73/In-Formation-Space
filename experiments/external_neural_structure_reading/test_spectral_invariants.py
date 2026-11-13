"""Tests for basis-invariant Q/K/V singular-spectrum observations."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

try:
    from .spectral_invariants import (
        SpectralInvariantError,
        analyze_qkv_spectral_invariants,
    )
except ImportError:
    from spectral_invariants import (
        SpectralInvariantError,
        analyze_qkv_spectral_invariants,
    )


def evidence_for(name: str, matrix: np.ndarray) -> tuple[bytes, dict]:
    raw = np.asarray(matrix, dtype="<f4").tobytes(order="C")
    return raw, {
        "name": name,
        "shard": "model.safetensors",
        "dtype": "F32",
        "shape": list(matrix.shape),
        "size_bytes": len(raw),
        "absolute_byte_range": [100, 100 + len(raw) - 1],
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
        "payload_sha256_scope": "complete-selected-tensor-payload",
        "shard_header_sha256": "a" * 64,
        "shard_size_bytes": 1_000_000,
    }


def make_inputs(orthogonal_transform: bool = False):
    rng = np.random.default_rng(20261113)
    base_slices = [rng.normal(size=(4, 4)).astype(np.float32) for _ in range(3)]
    first = np.concatenate(base_slices, axis=1)

    if orthogonal_transform:
        left = np.array(
            [[0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 0, 1], [0, 0, -1, 0]],
            dtype=np.float32,
        )
        right = np.array(
            [[0, 1, 0, 0], [1, 0, 0, 0], [0, 0, -1, 0], [0, 0, 0, -1]],
            dtype=np.float32,
        )
        last = np.concatenate([left @ part @ right for part in base_slices], axis=1)
    else:
        last = rng.normal(size=(4, 12)).astype(np.float32)

    payload_0, record_0 = evidence_for("h.0.attn.c_attn.weight", first)
    payload_11, record_11 = evidence_for("h.11.attn.c_attn.weight", last)
    nsd = {
        "schema": "in-formation-space.neural-structure-description.v0.1",
        "source": {
            "repository": "example-org/tiny-gpt2",
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "license_id": "mit",
        },
    }
    return nsd, {
        record_0["name"]: payload_0,
        record_11["name"]: payload_11,
    }, [record_0, record_11]


class SpectralInvariantTests(unittest.TestCase):
    def test_emits_schema_valid_full_singular_spectra(self):
        nsd, payloads, evidence = make_inputs()
        result = analyze_qkv_spectral_invariants(nsd, payloads, evidence)

        self.assertEqual(result["schema"], "in-formation-space.qkv-spectral-invariants.v0.1")
        self.assertEqual(result["dimensions"]["singular_values_per_projection"], 4)
        self.assertEqual(len(result["spectra"]), 2)
        for tensor in result["spectra"].values():
            self.assertEqual(set(tensor["qkv"]), {"query", "key", "value"})
            for projection in tensor["qkv"].values():
                self.assertEqual(projection["singular_value_count"], 4)
                self.assertEqual(len(projection["singular_values"]), 4)
                self.assertEqual(len(projection["frobenius_normalized_singular_values"]), 4)
                self.assertGreaterEqual(projection["stable_rank"], 1.0 - 1e-8)
        self.assertNotIn("payloads", result)
        self.assertNotIn("raw_weights", result)

        schema = json.loads(
            (Path(__file__).parent / "qkv-spectral-invariants.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(result)

    def test_singular_spectra_are_invariant_to_orthogonal_left_and_right_changes(self):
        nsd, payloads, evidence = make_inputs(orthogonal_transform=True)
        result = analyze_qkv_spectral_invariants(nsd, payloads, evidence)
        for role, comparison in result["cross_layer_spectral_comparisons"].items():
            self.assertLess(
                comparison["mean_absolute_frobenius_normalized_singular_value_distance"],
                1e-6,
                role,
            )
            self.assertLess(
                comparison["squared_energy_jensen_shannon_divergence_bits"],
                1e-6,
                role,
            )

    def test_payload_sha_mismatch_is_rejected(self):
        nsd, payloads, evidence = make_inputs()
        damaged = dict(payloads)
        name = evidence[0]["name"]
        damaged[name] = damaged[name][:-1] + bytes([damaged[name][-1] ^ 1])
        with self.assertRaisesRegex(SpectralInvariantError, "SHA-256 mismatch"):
            analyze_qkv_spectral_invariants(nsd, damaged, evidence)

    def test_payload_nan_is_rejected(self):
        nsd, payloads, evidence = make_inputs()
        name = evidence[0]["name"]
        matrix = np.frombuffer(payloads[name], dtype="<f4").copy()
        matrix[0] = np.nan
        payloads[name] = matrix.tobytes()
        evidence[0]["payload_sha256"] = hashlib.sha256(payloads[name]).hexdigest()
        with self.assertRaisesRegex(SpectralInvariantError, "NaN or infinity"):
            analyze_qkv_spectral_invariants(nsd, payloads, evidence)

    def test_non_divisible_qkv_width_is_rejected(self):
        nsd, payloads, evidence = make_inputs()
        record = evidence[0]
        raw = np.arange(20, dtype="<f4").tobytes()
        record["shape"] = [4, 5]
        record["size_bytes"] = len(raw)
        record["payload_sha256"] = hashlib.sha256(raw).hexdigest()
        payloads[record["name"]] = raw
        with self.assertRaisesRegex(SpectralInvariantError, "divide into three"):
            analyze_qkv_spectral_invariants(nsd, payloads, evidence)


if __name__ == "__main__":
    unittest.main()
