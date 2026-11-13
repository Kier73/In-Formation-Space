"""HFR-002 BERT canonical topology and negative-contract tests."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

try:
    from .bert_graph_ir import BertTopologyError, _expected_tensors, compile_bert_topology
    from .neural_graph_ir import verify_typed_graph
except ImportError:
    from bert_graph_ir import BertTopologyError, _expected_tensors, compile_bert_topology
    from neural_graph_ir import verify_typed_graph


def synthetic_bert_nsd(layers: int = 2) -> dict:
    """Make small complete header-only BERT + MLM/NSP fixture."""
    config = {
        "model_type": "bert",
        "architectures": ["BertForMaskedLM"],
        "hidden_size": 4,
        "max_position_embeddings": 8,
        "vocab_size": 16,
        "type_vocab_size": 2,
        "num_hidden_layers": layers,
        "intermediate_size": 12,
        "num_attention_heads": 2,
        "hidden_act": "gelu",
        "layer_norm_eps": 1e-12,
        "attention_probs_dropout_prob": 0.1,
        "hidden_dropout_prob": 0.1,
        "position_embedding_type": "absolute",
        "tie_word_embeddings": True,
    }
    manifest = [
        {
            "name": name,
            "dtype": "F32",
            "shape": shape,
            "shard": "model.safetensors",
            "data_offsets": [0, 0],
            "data_bytes": 0,
        }
        for name, (shape, _) in sorted(_expected_tensors(config).items())
    ]
    return {
        "schema": "in-formation-space.neural-structure-description.v0.1",
        "source": {
            "repository": "fixture/tiny-bert",
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "license_id": "apache-2.0",
        },
        "observed": {
            "configuration": config,
            "files": [
                {
                    "path": "config.json",
                    "role": "configuration",
                    "sha256": "b" * 64,
                    "sha256_scope": "entire-file",
                    "size_bytes": 100,
                },
                {
                    "path": "model.safetensors",
                    "role": "safetensors-shard",
                    "sha256": "a" * 64,
                    "sha256_scope": "8-byte-prefix-and-header-only",
                    "size_bytes": 400,
                },
            ],
            "weight_map": None,
            "tensor_manifest": manifest,
        },
        "inferred": {"tensor_count": len(manifest)},
        "generated": {"architecture_graph": None, "parameter_rules": []},
    }


class BertGraphTests(unittest.TestCase):
    """Check the interpretation without copying tensor values or running model code."""

    def test_complete_two_layer_fixture_compiles_into_existing_canonical_schema(self):
        nsd = synthetic_bert_nsd(layers=2)
        graph = compile_bert_topology(nsd)
        self.assertEqual(graph["schema"], "in-formation-space.neural-computation-graph.v0.1")
        self.assertEqual(graph["source_observation"]["revision"], nsd["source"]["revision"])
        self.assertEqual(graph["completeness"]["status"], "complete-for-supported-family-template")
        self.assertEqual(graph["completeness"]["observed_tensor_count"], 46)
        self.assertEqual(graph["completeness"]["classified_tensor_count"], 46)
        self.assertEqual(graph["completeness"]["bound_tensor_count"], 46)
        self.assertEqual(graph["verification"]["status"], "passed")
        self.assertEqual(graph["verification"]["failed_check_count"], 0)
        self.assertEqual(graph["verification"]["operation_count"], 44)
        self.assertEqual(graph["verification"]["edge_count"], 105)
        self.assertEqual(graph["verification"]["input_port_count"], 103)
        self.assertEqual(graph["verification"]["output_port_count"], 44)
        self.assertEqual(len(graph["outputs"]), 2)

        schema = json.loads(
            (Path(__file__).parent / "neural-computation-graph.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(graph)

    def test_checkpoint_has_two_heads_despite_config_masked_lm_label(self):
        graph = compile_bert_topology(synthetic_bert_nsd())
        self.assertEqual(
            graph["model_family_adapter"]["family"],
            "BertForPreTraining-compatible checkpoint tensor inventory",
        )
        self.assertEqual(
            {item["name"] for item in graph["outputs"]},
            {"masked_language_logits", "next_sentence_logits"},
        )
        self.assertTrue(any("config declares" in item for item in graph["assumptions_and_unresolved"]))
        self.assertTrue(any("not necessarily runtime-active" in item for item in graph["assumptions_and_unresolved"]))
        self.assertTrue(any("erf GELU" in item for item in graph["assumptions_and_unresolved"]))
        self.assertEqual(
            sum(
                edge["source"] == {
                    "kind": "tensor",
                    "name": "bert.embeddings.word_embeddings.weight",
                }
                for edge in graph["edges"]
            ),
            2,
        )

    def test_bert_operators_are_distinct_from_causal_gpt2_ones(self):
        graph = compile_bert_topology(synthetic_bert_nsd(layers=1))
        names = {op["operator"] for op in graph["operations"]}
        self.assertIn("attention.bidirectional_scaled_dot_product", names)
        self.assertIn("attention.padding_mask_prepare", names)
        self.assertIn("activation.gelu_erf", names)
        self.assertIn("sequence.select_first_token", names)
        self.assertIn("activation.tanh", names)
        self.assertNotIn("attention.causal_scaled_dot_product", names)
        self.assertNotIn("activation.gelu_tanh", names)
        self.assertEqual(
            {
                operation["provenance"]["operator_semantics"]["reference"]
                for operation in graph["operations"]
            },
            {"https://huggingface.co/docs/transformers/model_doc/bert"},
        )

    def test_every_observed_tensor_is_used_with_explicit_source_provenance(self):
        nsd = synthetic_bert_nsd(layers=2)
        graph = compile_bert_topology(nsd)
        observed = {item["name"] for item in nsd["observed"]["tensor_manifest"]}
        classified = {item["name"] for item in graph["tensors"]}
        bound = {
            edge["source"]["name"]
            for edge in graph["edges"]
            if edge["source"]["kind"] == "tensor"
        }
        self.assertEqual(observed, classified)
        self.assertEqual(observed, bound)
        for item in graph["tensors"]:
            self.assertEqual(item["classification"]["status"], "family-interpreted")
            self.assertEqual(item["source"]["header_hash_scope"], "8-byte-prefix-and-header-only")
        self.assertEqual(graph["evidence_policy"]["numerical_parameter_values"], "not-observed")

    def test_missing_extra_or_misshapen_tensor_fails_closed(self):
        nsd = synthetic_bert_nsd()
        nsd["observed"]["tensor_manifest"] = [
            item for item in nsd["observed"]["tensor_manifest"]
            if item["name"] != "bert.pooler.dense.bias"
        ]
        with self.assertRaisesRegex(BertTopologyError, "missing="):
            compile_bert_topology(nsd)

        nsd = synthetic_bert_nsd()
        nsd["observed"]["tensor_manifest"].append({
            "name": "unknown.parameter",
            "dtype": "F32", "shape": [1],
            "shard": "model.safetensors",
            "data_offsets": [0, 0], "data_bytes": 0,
        })
        with self.assertRaisesRegex(BertTopologyError, "unexpected="):
            compile_bert_topology(nsd)

        nsd = synthetic_bert_nsd()
        target = next(item for item in nsd["observed"]["tensor_manifest"] if item["name"].endswith("layer.1.intermediate.dense.weight"))
        target["shape"] = [11, 4]
        with self.assertRaisesRegex(BertTopologyError, "incompatible shape/dtype"):
            compile_bert_topology(nsd)

    def test_unsupported_gelu_attention_mode_and_config_fail_closed(self):
        for changes, message in (
            ({"hidden_act": "gelu_new"}, "erf GELU"),
            ({"is_decoder": True}, "decoder"),
            ({"add_cross_attention": True}, "cross-attention"),
            ({"position_embedding_type": "relative_key"}, "absolute"),
            ({"tie_word_embeddings": False}, "tied MLM"),
            ({"num_attention_heads": 3}, "divisible"),
        ):
            with self.subTest(changes=changes):
                nsd = synthetic_bert_nsd()
                nsd["observed"]["configuration"].update(changes)
                with self.assertRaisesRegex(BertTopologyError, message):
                    compile_bert_topology(nsd)

    def test_verifier_rejects_mutated_attention_mask_semantics(self):
        nsd = synthetic_bert_nsd()
        graph = compile_bert_topology(nsd)
        corrupted = copy.deepcopy(graph)
        attention = next(
            op for op in corrupted["operations"]
            if op["operator"] == "attention.bidirectional_scaled_dot_product"
        )
        attention["attributes"]["causal"] = True
        result = verify_typed_graph(corrupted, nsd)
        self.assertEqual(result["verification"]["status"], "failed")
        self.assertEqual(
            next(c["status"] for c in result["verification"]["checks"]
                 if c["id"] == "operator-dimensional-contracts"),
            "failed",
        )

    def test_verifier_rejects_wrong_projection_dimensions(self):
        nsd = synthetic_bert_nsd()
        graph = compile_bert_topology(nsd)
        corrupted = copy.deepcopy(graph)
        query = next(op for op in corrupted["operations"] if op["id"] == "encoder.0.query")
        query["inputs"][1]["shape"] = [3, 4]
        result = verify_typed_graph(corrupted, nsd)
        self.assertEqual(result["verification"]["status"], "failed")

    def test_stable_serialization_and_provenance_without_parameter_payload(self):
        graph = compile_bert_topology(synthetic_bert_nsd(layers=1))
        second = compile_bert_topology(synthetic_bert_nsd(layers=1))
        self.assertEqual(
            json.dumps(graph, sort_keys=True, allow_nan=False),
            json.dumps(second, sort_keys=True, allow_nan=False),
        )
        rendered = json.dumps(graph)
        self.assertNotIn('"payload_values"', rendered)
        self.assertNotIn('"tensor_values"', rendered)
        self.assertFalse(any(key in rendered for key in ('"raw_weights"', '"numerical_payload"')))


if __name__ == "__main__":
    unittest.main()
