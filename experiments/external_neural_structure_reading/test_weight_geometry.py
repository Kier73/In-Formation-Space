"""Deterministic descriptive-statistics tests for selected GPT-2 weight payloads."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

try:
    from .weight_geometry import (
        WeightGeometryError,
        analyze_selected_weight_geometry,
    )
except ImportError:
    from weight_geometry import (
        WeightGeometryError,
        analyze_selected_weight_geometry,
    )


def make_record(name: str, matrix: np.ndarray) -> tuple[bytes, dict]:
    raw = np.asarray(matrix, dtype="<f4").tobytes(order="C")
    record = {
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
    return raw, record


def make_inputs() -> tuple[dict, dict[str, bytes], list[dict]]:
    matrix_a = np.arange(24, dtype=np.float32).reshape(2, 12) / 10.0
    matrix_b = (np.arange(24, dtype=np.float32).reshape(2, 12) + 1.0) / 7.0
    payload_a, record_a = make_record("h.0.attn.c_attn.weight", matrix_a)
    payload_b, record_b = make_record("h.11.attn.c_attn.weight", matrix_b)
    nsd = {
        "schema": "in-formation-space.neural-structure-description.v0.1",
        "source": {
            "repository": "example-org/tiny-gpt2",
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "license_id": "mit",
        },
    }
    return (
        nsd,
        {
            record_a["name"]: payload_a,
            record_b["name"]: payload_b,
        },
        [record_a, record_b],
    )


class SelectedWeightGeometryTests(unittest.TestCase):
    def test_emits_schema_valid_geometry_summaries_without_raw_payload_values(self):
        nsd, payloads, evidence = make_inputs()
        result = analyze_selected_weight_geometry(nsd, payloads, evidence)

        self.assertEqual(result["schema"], "in-formation-space.selected-weight-geometry.v0.1")
        self.assertEqual(result["dimensions"]["input_width"], 2)
        self.assertEqual(result["dimensions"]["fused_output_width"], 12)
        self.assertEqual(result["dimensions"]["hidden_width_per_qkv_slice"], 4)
        self.assertEqual(len(result["tensor_summaries"]), 2)
        self.assertEqual(set(result["cross_layer_comparisons"]), {"fused_qkv", "q", "k", "v"})
        self.assertNotIn("payloads", result)
        self.assertNotIn("values", result)

        for summary in result["tensor_summaries"].values():
            self.assertEqual(set(summary["slices"]), {"query", "key", "value"})
            self.assertEqual(summary["fused_qkv"]["element_count"], 24)
            self.assertEqual(summary["fused_qkv"]["spectral_norm_iterations"], 16)

        schema = json.loads(
            (Path(__file__).parent / "weight-geometry.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(result)

    def test_same_payload_produces_deterministic_spectral_estimate(self):
        nsd, payloads, evidence = make_inputs()
        first = analyze_selected_weight_geometry(nsd, payloads, evidence)
        second = analyze_selected_weight_geometry(nsd, payloads, evidence)
        for name in first["tensor_summaries"]:
            self.assertEqual(
                first["tensor_summaries"][name]["fused_qkv"]["approximate_spectral_norm"],
                second["tensor_summaries"][name]["fused_qkv"]["approximate_spectral_norm"],
            )

    def test_payload_digest_mismatch_is_rejected(self):
        nsd, payloads, evidence = make_inputs()
        damaged = dict(payloads)
        first_name = evidence[0]["name"]
        damaged[first_name] = damaged[first_name][:-1] + bytes([damaged[first_name][-1] ^ 1])
        with self.assertRaisesRegex(WeightGeometryError, "SHA-256 does not match"):
            analyze_selected_weight_geometry(nsd, damaged, evidence)

    def test_non_finite_weight_values_are_rejected(self):
        nsd, payloads, evidence = make_inputs()
        name = evidence[0]["name"]
        matrix = np.frombuffer(payloads[name], dtype="<f4").copy()
        matrix[0] = np.nan
        raw = matrix.tobytes()
        payloads[name] = raw
        evidence[0]["payload_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(WeightGeometryError, "NaN or infinity"):
            analyze_selected_weight_geometry(nsd, payloads, evidence)

    def test_non_matrix_or_non_f32_evidence_is_rejected(self):
        nsd, payloads, evidence = make_inputs()
        evidence[0]["dtype"] = "BF16"
        with self.assertRaisesRegex(WeightGeometryError, "only F32"):
            analyze_selected_weight_geometry(nsd, payloads, evidence)

    def test_requires_two_comparable_selected_matrices(self):
        nsd, payloads, evidence = make_inputs()
        with self.assertRaisesRegex(WeightGeometryError, "exactly two"):
            analyze_selected_weight_geometry(nsd, {evidence[0]["name"]: payloads[evidence[0]["name"]]}, evidence[:1])


if __name__ == "__main__":
    unittest.main()
