"""HFR-002 canonical graph IR tests."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

try:
    from .neural_graph_ir import (
        GRAPH_SCHEMA,
        TopologyError,
        compile_gpt2_topology,
        verify_typed_graph,
    )
    from .test_gpt2_adapter import make_nsd
except ImportError:
    from neural_graph_ir import (
        GRAPH_SCHEMA,
        TopologyError,
        compile_gpt2_topology,
        verify_typed_graph,
    )
    from test_gpt2_adapter import make_nsd


def make_topology_nsd(*, layers: int = 1, tie: bool | None = None) -> dict:
    nsd = make_nsd(layers=layers, tie=tie)
    nsd["observed"]["files"] = [
        {
            "path": "model.safetensors",
            "role": "safetensors-shard",
            "size_bytes": 0,
            "sha256": "a" * 64,
            "sha256_scope": "8-byte-prefix-and-header-only",
            "header_bytes": 2,
            "data_bytes": 0,
            "metadata": {},
        }
    ]
    return nsd


class NeuralGraphIRTests(unittest.TestCase):
    def test_compiles_small_gpt2_into_schema_valid_architecture_independent_graph(self):
        nsd = make_topology_nsd(layers=2)
        graph = compile_gpt2_topology(nsd)

        self.assertEqual(graph["schema"], GRAPH_SCHEMA)
        self.assertEqual(graph["model_family_adapter"]["family"], "GPT2LMHeadModel")
        self.assertEqual(graph["dimension_symbols"]["sequence"]["maximum"], 8)
        self.assertEqual(graph["completeness"]["status"], "complete-for-supported-family-template")
        self.assertEqual(graph["completeness"]["observed_tensor_count"], 30)
        self.assertEqual(graph["completeness"]["classified_tensor_count"], 30)
        self.assertEqual(graph["completeness"]["bound_tensor_count"], 30)
        self.assertEqual(graph["verification"]["status"], "passed")
        self.assertEqual(graph["verification"]["failed_check_count"], 0)
        self.assertEqual(graph["verification"]["operation_count"], 29)
        self.assertEqual(graph["verification"]["input_port_count"], 66)
        self.assertEqual(graph["verification"]["output_port_count"], 29)
        self.assertEqual(graph["verification"]["edge_count"], 67)

        operator_names = {operation["operator"] for operation in graph["operations"]}
        self.assertTrue(
            {
                "embedding.lookup",
                "tensor.add",
                "regularization.dropout",
                "normalization.layer_norm",
                "linear.affine",
                "attention.causal_scaled_dot_product",
                "activation.gelu_tanh",
            }.issubset(operator_names)
        )
        self.assertFalse(any(name.startswith("gpt2.") for name in operator_names))

        schema = json.loads(
            (Path(__file__).parent / "neural-computation-graph.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(graph)

    def test_every_observed_tensor_is_classified_and_used(self):
        nsd = make_topology_nsd(layers=2)
        graph = compile_gpt2_topology(nsd)
        observed = {item["name"] for item in nsd["observed"]["tensor_manifest"]}
        classified = {item["name"] for item in graph["tensors"]}
        used = {
            edge["source"]["name"]
            for edge in graph["edges"]
            if edge["source"]["kind"] == "tensor"
        }
        self.assertEqual(observed, classified)
        self.assertEqual(observed, used)

        tied_weight_uses = [
            edge for edge in graph["edges"]
            if edge["source"] == {"kind": "tensor", "name": "wte.weight"}
        ]
        self.assertEqual(len(tied_weight_uses), 2)
        head = next(operation for operation in graph["operations"] if operation["id"] == "language_model_head")
        self.assertEqual(head["attributes"]["binding_status"], "family-contract-tied")

    def test_untied_output_head_is_classified_as_an_observed_tensor(self):
        nsd = make_topology_nsd(tie=False)
        graph = compile_gpt2_topology(nsd)
        roles = {item["name"]: item["classification"]["role"] for item in graph["tensors"]}
        self.assertEqual(roles["lm_head.weight"], "language_model_head.weight")
        head_edge = next(
            edge for edge in graph["edges"]
            if edge["target"] == {
                "kind": "operation_input",
                "operation": "language_model_head",
                "port": "weight",
            }
        )
        self.assertEqual(head_edge["source"], {"kind": "tensor", "name": "lm_head.weight"})

    def test_completeness_fails_when_a_tensor_classification_is_removed(self):
        nsd = make_topology_nsd(layers=1)
        graph = compile_gpt2_topology(nsd)
        graph["tensors"] = [
            item for item in graph["tensors"] if item["name"] != "h.0.attn.c_attn.weight"
        ]
        result = verify_typed_graph(graph, nsd)
        self.assertEqual(result["completeness"]["status"], "incomplete")
        self.assertIn("h.0.attn.c_attn.weight", result["completeness"]["unclassified_tensors"])
        self.assertEqual(result["verification"]["status"], "failed")

    def test_incompatible_edge_type_or_shape_is_rejected(self):
        nsd = make_topology_nsd(layers=1)
        graph = compile_gpt2_topology(nsd)
        damaged = copy.deepcopy(graph)
        tensor_edge = next(
            edge for edge in damaged["edges"]
            if edge["source"] == {"kind": "tensor", "name": "wte.weight"}
        )
        tensor_edge["target"] = {
            "kind": "operation_input",
            "operation": "embedding.token_lookup",
            "port": "indices",
        }
        result = verify_typed_graph(damaged, nsd)
        self.assertEqual(result["verification"]["status"], "failed")
        check = next(
            item for item in result["verification"]["checks"]
            if item["id"] == "edge-endpoint-and-type-integrity"
        )
        self.assertEqual(check["status"], "failed")

    def test_directed_cycle_and_duplicate_producer_are_rejected(self):
        nsd = make_topology_nsd(layers=1)
        graph = compile_gpt2_topology(nsd)
        damaged = copy.deepcopy(graph)
        damaged["edges"].append(
            {
                "source": {
                    "kind": "operation_output",
                    "operation": "final.layer_norm",
                    "port": "normalized",
                },
                "target": {
                    "kind": "operation_input",
                    "operation": "block.0.attention_norm",
                    "port": "value",
                },
                "provenance": {
                    "status": "inferred-connection",
                    "basis": "deliberately cyclic negative test",
                },
            }
        )
        result = verify_typed_graph(damaged, nsd)
        self.assertEqual(result["verification"]["status"], "failed")
        check = next(
            item for item in result["verification"]["checks"]
            if item["id"] == "acyclic-operation-topology"
        )
        self.assertEqual(check["status"], "failed")

    def test_unsupported_family_is_rejected_instead_of_coerced(self):
        nsd = make_topology_nsd(layers=1)
        nsd["observed"]["configuration"]["model_type"] = "unknown-family"
        with self.assertRaisesRegex(TopologyError, "family interpretation failed"):
            compile_gpt2_topology(nsd)

    def test_graph_records_observation_interpretation_and_inference_separately(self):
        nsd = make_topology_nsd(layers=1)
        graph = compile_gpt2_topology(nsd)
        self.assertEqual(
            graph["evidence_policy"]["tensor_identity_dtype_shape_offsets"],
            "observed-from-NSD",
        )
        self.assertEqual(
            graph["evidence_policy"]["tensor_roles"],
            "interpreted-from-tensor-names-dimensions-and-GPT2-family-contract",
        )
        self.assertEqual(
            graph["evidence_policy"]["directed_connections"],
            "inferred-from-GPT2-family-order-and-validated-by-typed-ports",
        )
        causal_mask = next(
            item for item in graph["tensors"]
            if item["name"] == "h.0.attn.bias"
        )
        self.assertEqual(causal_mask["classification"]["role"], "transformer_block.attention.causal_mask")
        self.assertIn("mask payload values are unobserved", next(
            edge["provenance"]["basis"]
            for edge in graph["edges"]
            if edge["source"] == {"kind": "tensor", "name": "h.0.attn.bias"}
        ))

    def test_graph_does_not_retain_or_claim_tensor_payload_values(self):
        graph = compile_gpt2_topology(make_topology_nsd(layers=1))
        rendered = json.dumps(graph)
        self.assertNotIn("payload_values", rendered)
        self.assertNotIn("raw_weights", rendered)
        self.assertNotIn("tensor_values", rendered)
        self.assertEqual(
            graph["evidence_policy"]["numerical_parameter_values"],
            "not-observed",
        )


if __name__ == "__main__":
    unittest.main()
