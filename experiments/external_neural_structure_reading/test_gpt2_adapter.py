"""Shape and family-contract tests for the HFR-001 GPT-2 adapter."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

try:
    from .gpt2_adapter import GPT2InterpretationError, interpret_gpt2
except ImportError:
    from gpt2_adapter import GPT2InterpretationError, interpret_gpt2


def tensor(name: str, shape: list[int], dtype: str = "F32") -> dict:
    return {
        "name": name,
        "dtype": dtype,
        "shape": shape,
        "shard": "model.safetensors",
        "data_offsets": [0, 0],
        "data_bytes": 0,
    }


def make_nsd(*, layers: int = 1, tie: bool | None = None) -> dict:
    hidden = 4
    heads = 2
    context = 8
    vocab = 16
    inner = 16
    config = {
        "model_type": "gpt2",
        "architectures": ["GPT2LMHeadModel"],
        "n_embd": hidden,
        "n_layer": layers,
        "n_head": heads,
        "n_positions": context,
        "vocab_size": vocab,
        "n_inner": None,
        "activation_function": "gelu_new",
        "layer_norm_epsilon": 1e-5,
        "embd_pdrop": 0.1,
        "attn_pdrop": 0.1,
        "resid_pdrop": 0.1,
    }
    if tie is not None:
        config["tie_word_embeddings"] = tie

    tensors = [
        tensor("wte.weight", [vocab, hidden]),
        tensor("wpe.weight", [context, hidden]),
        tensor("ln_f.weight", [hidden]),
        tensor("ln_f.bias", [hidden]),
    ]
    if tie is False:
        tensors.append(tensor("lm_head.weight", [vocab, hidden]))

    for index in range(layers):
        prefix = f"h.{index}."
        tensors.extend(
            [
                tensor(prefix + "attn.bias", [1, 1, context, context]),
                tensor(prefix + "attn.c_attn.weight", [hidden, 3 * hidden]),
                tensor(prefix + "attn.c_attn.bias", [3 * hidden]),
                tensor(prefix + "attn.c_proj.weight", [hidden, hidden]),
                tensor(prefix + "attn.c_proj.bias", [hidden]),
                tensor(prefix + "ln_1.weight", [hidden]),
                tensor(prefix + "ln_1.bias", [hidden]),
                tensor(prefix + "ln_2.weight", [hidden]),
                tensor(prefix + "ln_2.bias", [hidden]),
                tensor(prefix + "mlp.c_fc.weight", [hidden, inner]),
                tensor(prefix + "mlp.c_fc.bias", [inner]),
                tensor(prefix + "mlp.c_proj.weight", [inner, hidden]),
                tensor(prefix + "mlp.c_proj.bias", [hidden]),
            ]
        )

    return {
        "schema": "in-formation-space.neural-structure-description.v0.1",
        "source": {
            "repository": "fixture/tiny-gpt2",
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "license_id": None,
        },
        "observed": {
            "configuration": config,
            "files": [],
            "weight_map": None,
            "tensor_manifest": tensors,
        },
        "inferred": {},
        "generated": {"architecture_graph": None, "parameter_rules": []},
    }


class GPT2AdapterTests(unittest.TestCase):
    def test_constructs_graph_from_exact_small_fixture_and_validates_schema(self):
        graph = interpret_gpt2(make_nsd(layers=2))
        self.assertEqual(graph["schema"], "in-formation-space.gpt2-operation-graph.v0.1")
        self.assertEqual(graph["dimensions"]["hidden_width"], 4)
        self.assertEqual(graph["dimensions"]["attention_head_width"], 2)
        self.assertEqual(graph["dimensions"]["mlp_intermediate_width"], 16)
        self.assertEqual(graph["dimensions"]["mlp_intermediate_width_basis"], "observed mlp.c_fc.weight and mlp.c_proj.weight shapes")
        self.assertEqual(graph["verification"]["checked_transformer_blocks"], 2)
        self.assertEqual(len(graph["nodes"]), 25)
        self.assertTrue(graph["verification"]["passed_checks"] > 0)
        self.assertTrue(
            any(
                binding["evidence_basis"] == "Transformers GPT2LMHeadModel family contract"
                for node in graph["nodes"]
                for binding in node["tensor_bindings"]
            )
        )
        schema_path = Path(__file__).parent / "gpt2-operation-graph.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(graph)

    def test_tied_lm_head_is_an_inferred_family_binding_not_a_header_tensor(self):
        graph = interpret_gpt2(make_nsd())
        head = next(node for node in graph["nodes"] if node["id"] == "language_model_head")
        binding = head["tensor_bindings"][0]
        self.assertEqual(binding["name"], "wte.weight")
        self.assertEqual(binding["view"], "transpose")
        self.assertEqual(binding["evidence_basis"], "Transformers GPT2LMHeadModel family contract")
        self.assertEqual(head["attributes"]["binding_status"], "family-contract-tied")

    def test_explicit_untied_head_requires_an_observed_lm_head_tensor(self):
        graph = interpret_gpt2(make_nsd(tie=False))
        head = next(node for node in graph["nodes"] if node["id"] == "language_model_head")
        self.assertEqual(head["tensor_bindings"][0]["name"], "lm_head.weight")
        self.assertEqual(head["attributes"]["binding_status"], "separate-observed-tensor")

    def test_qkv_dimension_mismatch_is_rejected(self):
        nsd = make_nsd()
        item = next(x for x in nsd["observed"]["tensor_manifest"] if x["name"] == "h.0.attn.c_attn.weight")
        item["shape"] = [4, 8]
        with self.assertRaisesRegex(GPT2InterpretationError, "c_attn.weight shape"):
            interpret_gpt2(nsd)

    def test_missing_layer_tensor_is_rejected(self):
        nsd = make_nsd()
        nsd["observed"]["tensor_manifest"] = [
            x for x in nsd["observed"]["tensor_manifest"]
            if x["name"] != "h.0.mlp.c_proj.bias"
        ]
        with self.assertRaisesRegex(GPT2InterpretationError, "required tensor is missing"):
            interpret_gpt2(nsd)

    def test_unexpected_tensor_is_not_silently_ignored(self):
        nsd = make_nsd()
        nsd["observed"]["tensor_manifest"].append(tensor("custom.extra", [4]))
        with self.assertRaisesRegex(GPT2InterpretationError, "unexpected"):
            interpret_gpt2(nsd)

    def test_inconsistent_inner_width_is_rejected(self):
        nsd = make_nsd(layers=2)
        item = next(x for x in nsd["observed"]["tensor_manifest"] if x["name"] == "h.1.mlp.c_fc.weight")
        item["shape"] = [4, 12]
        with self.assertRaisesRegex(GPT2InterpretationError, "intermediate width changes"):
            interpret_gpt2(nsd)

    def test_non_divisible_attention_heads_are_rejected(self):
        nsd = make_nsd()
        nsd["observed"]["configuration"]["n_head"] = 3
        with self.assertRaisesRegex(GPT2InterpretationError, "divisible"):
            interpret_gpt2(nsd)

    def test_non_supported_activation_and_cross_attention_are_rejected(self):
        activation_nsd = make_nsd()
        activation_nsd["observed"]["configuration"]["activation_function"] = "relu"
        with self.assertRaisesRegex(GPT2InterpretationError, "only the observed/default gelu_new"):
            interpret_gpt2(activation_nsd)

        cross_nsd = make_nsd()
        cross_nsd["observed"]["configuration"]["add_cross_attention"] = True
        with self.assertRaisesRegex(GPT2InterpretationError, "cross-attention"):
            interpret_gpt2(cross_nsd)


if __name__ == "__main__":
    unittest.main()
