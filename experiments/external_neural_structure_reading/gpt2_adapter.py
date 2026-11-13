"""Shape-checked GPT-2 operation-graph interpretation for HFR-001.

The adapter reads only an NSD v0.1 observation. It never reads or executes
model source code and never accesses tensor payload values.
"""

from __future__ import annotations

from typing import Any

GRAPH_SCHEMA = "in-formation-space.gpt2-operation-graph.v0.1"
TRANSFORMERS_REFERENCE = "https://huggingface.co/docs/transformers/main/model_doc/gpt2"
TRANSFORMERS_REFERENCE_CHECKED = "2026-11-13"


class GPT2InterpretationError(ValueError):
    """Raised when the NSD does not satisfy this adapter's declared GPT-2 contract."""


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise GPT2InterpretationError(f"{label} must be a positive integer")
    return value


def _probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GPT2InterpretationError(f"{label} must be a number in [0, 1)")
    value = float(value)
    if not 0.0 <= value < 1.0:
        raise GPT2InterpretationError(f"{label} must be in [0, 1)")
    return value


def interpret_gpt2(nsd: dict[str, Any]) -> dict[str, Any]:
    """Build a typed inferred operation graph after exhaustive tensor-shape checks.

    Supported family in this first adapter:
      - config.model_type == 'gpt2'
      - config.architectures contains 'GPT2LMHeadModel'
      - activation_function == 'gelu_new'
      - standard self-attention without cross-attention, inverse-layer scaling,
        or reordered/upcast attention.

    The architecture graph is an interpretation based on the declared
    Transformers GPT-2 family contract plus the observed config/tensor manifest.
    It is not a forward implementation or a functional-equivalence claim.
    """
    if not isinstance(nsd, dict) or nsd.get("schema") != "in-formation-space.neural-structure-description.v0.1":
        raise GPT2InterpretationError("input must be a Neural Structure Description v0.1")
    source = nsd.get("source")
    observed = nsd.get("observed")
    if not isinstance(source, dict) or not isinstance(observed, dict):
        raise GPT2InterpretationError("NSD source and observed sections are required")

    config = observed.get("configuration")
    manifest = observed.get("tensor_manifest")
    if not isinstance(config, dict) or not isinstance(manifest, list):
        raise GPT2InterpretationError("NSD configuration and tensor_manifest are required")
    if config.get("model_type") != "gpt2":
        raise GPT2InterpretationError("model_type must be 'gpt2'")
    architectures = config.get("architectures")
    if not isinstance(architectures, list) or "GPT2LMHeadModel" not in architectures:
        raise GPT2InterpretationError("architectures must declare GPT2LMHeadModel")

    hidden = _positive_int(config.get("n_embd"), "n_embd")
    layer_count = _positive_int(config.get("n_layer"), "n_layer")
    head_count = _positive_int(config.get("n_head"), "n_head")
    context = _positive_int(config.get("n_positions"), "n_positions")
    vocabulary = _positive_int(config.get("vocab_size"), "vocab_size")
    if hidden % head_count:
        raise GPT2InterpretationError("n_embd must be divisible by n_head")
    head_dim = hidden // head_count

    activation = config.get("activation_function", "gelu_new")
    if activation != "gelu_new":
        raise GPT2InterpretationError(
            "this adapter version supports only the observed/default gelu_new activation"
        )
    if config.get("add_cross_attention", False) is not False:
        raise GPT2InterpretationError("cross-attention is outside this adapter contract")
    if config.get("scale_attn_by_inverse_layer_idx", False) is not False:
        raise GPT2InterpretationError("inverse-layer attention scaling is unsupported")
    if config.get("reorder_and_upcast_attn", False) is not False:
        raise GPT2InterpretationError("reordered/upcast attention is unsupported")

    tie_value = config.get("tie_word_embeddings", True)
    if type(tie_value) is not bool:
        raise GPT2InterpretationError("tie_word_embeddings must be boolean when present")
    scale_value = config.get("scale_attn_weights", True)
    if type(scale_value) is not bool:
        raise GPT2InterpretationError("scale_attn_weights must be boolean when present")
    if scale_value is not True:
        raise GPT2InterpretationError("this adapter version requires standard scaled dot-product attention")

    epsilon = config.get("layer_norm_epsilon", 1e-5)
    if isinstance(epsilon, bool) or not isinstance(epsilon, (int, float)) or epsilon <= 0:
        raise GPT2InterpretationError("layer_norm_epsilon must be positive")
    embedding_dropout = _probability(config.get("embd_pdrop", 0.1), "embd_pdrop")
    attention_dropout = _probability(config.get("attn_pdrop", 0.1), "attn_pdrop")
    residual_dropout = _probability(config.get("resid_pdrop", 0.1), "resid_pdrop")

    tensors: dict[str, dict[str, Any]] = {}
    for tensor in manifest:
        if not isinstance(tensor, dict):
            raise GPT2InterpretationError("every tensor manifest entry must be an object")
        name = tensor.get("name")
        if not isinstance(name, str) or not name:
            raise GPT2InterpretationError("every tensor manifest entry needs a non-empty name")
        if name in tensors:
            raise GPT2InterpretationError(f"duplicate tensor manifest entry: {name}")
        shape = tensor.get("shape")
        if not isinstance(shape, list) or any(type(dim) is not int or dim < 0 for dim in shape):
            raise GPT2InterpretationError(f"tensor {name} has an invalid shape")
        if not isinstance(tensor.get("dtype"), str) or not tensor["dtype"]:
            raise GPT2InterpretationError(f"tensor {name} has an invalid dtype")
        tensors[name] = tensor

    def require_tensor(name: str, expected_shape: list[int]) -> dict[str, Any]:
        tensor = tensors.get(name)
        if tensor is None:
            raise GPT2InterpretationError(f"required tensor is missing: {name}")
        if tensor["shape"] != expected_shape:
            raise GPT2InterpretationError(
                f"tensor {name} shape {tensor['shape']} does not match {expected_shape}"
            )
        return tensor

    global_shapes = {
        "wte.weight": [vocabulary, hidden],
        "wpe.weight": [context, hidden],
        "ln_f.weight": [hidden],
        "ln_f.bias": [hidden],
    }
    for name, shape in global_shapes.items():
        require_tensor(name, shape)

    if tie_value:
        if "lm_head.weight" in tensors:
            raise GPT2InterpretationError(
                "tied GPT-2 head should not expose a separate lm_head.weight in this NSD"
            )
    else:
        require_tensor("lm_head.weight", [vocabulary, hidden])

    blocks: list[dict[str, Any]] = []
    required_names = set(global_shapes)
    if not tie_value:
        required_names.add("lm_head.weight")
    intermediate_width: int | None = None
    for index in range(layer_count):
        prefix = f"h.{index}."
        fc_weight_name = prefix + "mlp.c_fc.weight"
        fc_weight = tensors.get(fc_weight_name)
        if fc_weight is None:
            raise GPT2InterpretationError(f"required tensor is missing: {fc_weight_name}")
        fc_shape = fc_weight["shape"]
        if len(fc_shape) != 2 or fc_shape[0] != hidden:
            raise GPT2InterpretationError(
                f"{fc_weight_name} must have shape [n_embd, n_inner]"
            )
        layer_intermediate = _positive_int(fc_shape[1], f"{fc_weight_name} inner width")
        if intermediate_width is None:
            intermediate_width = layer_intermediate
        elif layer_intermediate != intermediate_width:
            raise GPT2InterpretationError("MLP intermediate width changes between transformer blocks")

        expected = {
            "attn.bias": [1, 1, context, context],
            "attn.c_attn.weight": [hidden, 3 * hidden],
            "attn.c_attn.bias": [3 * hidden],
            "attn.c_proj.weight": [hidden, hidden],
            "attn.c_proj.bias": [hidden],
            "ln_1.weight": [hidden],
            "ln_1.bias": [hidden],
            "ln_2.weight": [hidden],
            "ln_2.bias": [hidden],
            "mlp.c_fc.weight": [hidden, intermediate_width],
            "mlp.c_fc.bias": [intermediate_width],
            "mlp.c_proj.weight": [intermediate_width, hidden],
            "mlp.c_proj.bias": [hidden],
        }
        for suffix, shape in expected.items():
            require_tensor(prefix + suffix, shape)
            required_names.add(prefix + suffix)

        blocks.append(
            {
                "index": index,
                "prefix": prefix,
                "intermediate_width": intermediate_width,
                "tensor_names": sorted(prefix + suffix for suffix in expected),
            }
        )

    if config.get("n_inner") is not None:
        configured_inner = _positive_int(config["n_inner"], "n_inner")
        if configured_inner != intermediate_width:
            raise GPT2InterpretationError(
                "config.n_inner does not match the observed MLP projection shapes"
            )

    unexpected = sorted(set(tensors) - required_names)
    missing = sorted(required_names - set(tensors))
    if missing or unexpected:
        raise GPT2InterpretationError(
            f"manifest tensor set differs from the supported GPT-2 template "
            f"(missing={missing[:5]}, unexpected={unexpected[:5]})"
        )

    def tensor_binding(name: str, role: str, basis: str = "safetensors-header") -> dict[str, Any]:
        tensor = tensors[name]
        return {
            "name": name,
            "role": role,
            "shape": tensor["shape"],
            "dtype": tensor["dtype"],
            "evidence_basis": basis,
        }

    nodes: list[dict[str, Any]] = []

    def add_node(
        node_id: str,
        operator: str,
        inputs: list[str],
        outputs: list[str],
        *,
        attributes: dict[str, Any] | None = None,
        bindings: list[dict[str, Any]] | None = None,
    ) -> None:
        nodes.append(
            {
                "id": node_id,
                "operator": operator,
                "inputs": inputs,
                "outputs": outputs,
                "attributes": attributes or {},
                "tensor_bindings": bindings or [],
            }
        )

    add_node(
        "embedding.token_lookup",
        "embedding.lookup",
        ["input.token_ids"],
        ["state.token_embeddings"],
        attributes={"vocabulary_size": vocabulary, "embedding_width": hidden},
        bindings=[tensor_binding("wte.weight", "token_embedding_table")],
    )
    add_node(
        "embedding.position_lookup",
        "embedding.lookup",
        ["input.position_ids"],
        ["state.position_embeddings"],
        attributes={"maximum_positions": context, "embedding_width": hidden},
        bindings=[tensor_binding("wpe.weight", "absolute_position_embedding_table")],
    )
    add_node(
        "embedding.add",
        "tensor.add",
        ["state.token_embeddings", "state.position_embeddings"],
        ["state.hidden.0"],
        attributes={"width": hidden, "dropout_probability": embedding_dropout},
    )

    current_hidden = "state.hidden.0"
    for index in range(layer_count):
        prefix = f"h.{index}."
        p = f"block.{index}"
        normalized_1 = f"{p}.normalized_attention_input"
        qkv = f"{p}.fused_qkv"
        attended = f"{p}.attention_context"
        projected_attention = f"{p}.attention_projection"
        after_attention = f"{p}.hidden_after_attention"
        normalized_2 = f"{p}.normalized_mlp_input"
        mlp_pre_activation = f"{p}.mlp_pre_activation"
        mlp_activated = f"{p}.mlp_activated"
        mlp_projected = f"{p}.mlp_projection"
        next_hidden = f"state.hidden.{index + 1}"

        add_node(
            f"{p}.layer_norm_1",
            "normalization.layer_norm",
            [current_hidden],
            [normalized_1],
            attributes={"width": hidden, "epsilon": float(epsilon)},
            bindings=[
                tensor_binding(prefix + "ln_1.weight", "scale"),
                tensor_binding(prefix + "ln_1.bias", "offset"),
            ],
        )
        add_node(
            f"{p}.fused_qkv_projection",
            "projection.affine",
            [normalized_1],
            [qkv],
            attributes={
                "input_width": hidden,
                "output_width": 3 * hidden,
                "checkpoint_matrix_layout": "[input_width, output_width]",
                "split_order": ["query", "key", "value"],
            },
            bindings=[
                tensor_binding(prefix + "attn.c_attn.weight", "weight"),
                tensor_binding(prefix + "attn.c_attn.bias", "bias"),
            ],
        )
        add_node(
            f"{p}.causal_multihead_attention",
            "attention.causal_scaled_dot_product",
            [qkv],
            [attended],
            attributes={
                "head_count": head_count,
                "head_width": head_dim,
                "qkv_split_order": ["query", "key", "value"],
                "causal": True,
                "scale_by_sqrt_head_width": True,
                "scale_factor": 1.0 / (head_dim ** 0.5),
                "attention_probability_dropout": attention_dropout,
                "mask_shape": [1, 1, context, context],
            },
            bindings=[
                tensor_binding(prefix + "attn.bias", "causal_mask_buffer"),
            ],
        )
        add_node(
            f"{p}.attention_output_projection",
            "projection.affine",
            [attended],
            [projected_attention],
            attributes={
                "input_width": hidden,
                "output_width": hidden,
                "checkpoint_matrix_layout": "[input_width, output_width]",
                "residual_dropout_probability": residual_dropout,
            },
            bindings=[
                tensor_binding(prefix + "attn.c_proj.weight", "weight"),
                tensor_binding(prefix + "attn.c_proj.bias", "bias"),
            ],
        )
        add_node(
            f"{p}.attention_residual_add",
            "tensor.add",
            [current_hidden, projected_attention],
            [after_attention],
            attributes={"width": hidden},
        )
        add_node(
            f"{p}.layer_norm_2",
            "normalization.layer_norm",
            [after_attention],
            [normalized_2],
            attributes={"width": hidden, "epsilon": float(epsilon)},
            bindings=[
                tensor_binding(prefix + "ln_2.weight", "scale"),
                tensor_binding(prefix + "ln_2.bias", "offset"),
            ],
        )
        add_node(
            f"{p}.mlp_input_projection",
            "projection.affine",
            [normalized_2],
            [mlp_pre_activation],
            attributes={
                "input_width": hidden,
                "output_width": intermediate_width,
                "checkpoint_matrix_layout": "[input_width, output_width]",
            },
            bindings=[
                tensor_binding(prefix + "mlp.c_fc.weight", "weight"),
                tensor_binding(prefix + "mlp.c_fc.bias", "bias"),
            ],
        )
        add_node(
            f"{p}.mlp_activation",
            "activation.gelu_new",
            [mlp_pre_activation],
            [mlp_activated],
            attributes={"activation_name": activation},
        )
        add_node(
            f"{p}.mlp_output_projection",
            "projection.affine",
            [mlp_activated],
            [mlp_projected],
            attributes={
                "input_width": intermediate_width,
                "output_width": hidden,
                "checkpoint_matrix_layout": "[input_width, output_width]",
                "residual_dropout_probability": residual_dropout,
            },
            bindings=[
                tensor_binding(prefix + "mlp.c_proj.weight", "weight"),
                tensor_binding(prefix + "mlp.c_proj.bias", "bias"),
            ],
        )
        add_node(
            f"{p}.mlp_residual_add",
            "tensor.add",
            [after_attention, mlp_projected],
            [next_hidden],
            attributes={"width": hidden},
        )
        current_hidden = next_hidden

    add_node(
        "final.layer_norm",
        "normalization.layer_norm",
        [current_hidden],
        ["state.final_hidden"],
        attributes={"width": hidden, "epsilon": float(epsilon)},
        bindings=[
            tensor_binding("ln_f.weight", "scale"),
            tensor_binding("ln_f.bias", "offset"),
        ],
    )

    if tie_value:
        head_binding = tensor_binding(
            "wte.weight",
            "shared_language_model_head_weight",
            basis="Transformers GPT2LMHeadModel family contract",
        )
        head_binding["view"] = "transpose"
        head_binding["note"] = (
            "The output projection is tied to the input token embedding table "
            "by the declared GPT2LMHeadModel family contract; this relation is "
            "not encoded as a separate lm_head.weight header entry."
        )
    else:
        head_binding = tensor_binding("lm_head.weight", "language_model_head_weight")
        head_binding["view"] = "transpose"

    add_node(
        "language_model_head",
        "projection.vocabulary_logits",
        ["state.final_hidden"],
        ["output.logits"],
        attributes={
            "input_width": hidden,
            "output_width": vocabulary,
            "checkpoint_weight_layout": "[vocabulary_size, hidden_width]",
            "binding_status": "family-contract-tied" if tie_value else "separate-observed-tensor",
        },
        bindings=[head_binding],
    )

    dtype_names = sorted({tensor["dtype"] for tensor in tensors.values()})
    checks = [
        {
            "id": "family-declaration",
            "status": "passed",
            "evidence": "observed config.model_type and config.architectures",
        },
        {
            "id": "embedding-dimensions",
            "status": "passed",
            "evidence": "wte.weight and wpe.weight shapes agree with vocabulary, context, and hidden dimensions",
        },
        {
            "id": "attention-dimensions",
            "status": "passed",
            "evidence": "every fused QKV projection, head partition, output projection, and causal mask has the expected shape",
        },
        {
            "id": "mlp-dimensions",
            "status": "passed",
            "evidence": "all blocks share the observed intermediate width and both MLP projections are dimensionally compatible",
        },
        {
            "id": "layer-count-and-parameter-inventory",
            "status": "passed",
            "evidence": "every declared block index and every expected tensor name is present exactly once",
        },
        {
            "id": "output-head-binding",
            "status": "passed",
            "evidence": "the model-family contract specifies tied input/output embeddings; the binding is explicitly tagged as family-contract evidence",
        },
    ]

    return {
        "schema": GRAPH_SCHEMA,
        "source_observation": {
            "repository": source.get("repository"),
            "revision": source.get("revision"),
            "license_id": source.get("license_id"),
        },
        "family": {
            "model_type": "gpt2",
            "architecture": "GPT2LMHeadModel",
            "adapter": "hfr-001.gpt2-adapter.v0.1",
            "interpretation_status": "inferred-family-graph",
        },
        "dimensions": {
            "vocabulary_size": vocabulary,
            "hidden_width": hidden,
            "layer_count": layer_count,
            "attention_head_count": head_count,
            "attention_head_width": head_dim,
            "context_length": context,
            "mlp_intermediate_width": intermediate_width,
            "mlp_intermediate_width_basis": (
                "observed mlp.c_fc.weight and mlp.c_proj.weight shapes"
                if config.get("n_inner") is None
                else "config.n_inner and observed tensor shapes"
            ),
            "parameter_dtypes": dtype_names,
        },
        "nodes": nodes,
        "verification": {
            "status": "passed",
            "passed_checks": len(checks),
            "failed_checks": 0,
            "checked_transformer_blocks": layer_count,
            "checks": checks,
        },
        "interpretation_reference": {
            "url": TRANSFORMERS_REFERENCE,
            "checked_on": TRANSFORMERS_REFERENCE_CHECKED,
            "used_for": [
                "GPT2LMHeadModel causal language-model family structure",
                "causal self-attention semantics",
                "GPT2Config defaults including scaled attention and tied word embeddings",
            ],
        },
        "assumptions_and_unresolved": [
            "Operation types and graph ordering are inferred from the GPT-2 family contract, not encoded directly in the Safetensors headers.",
            "The fused QKV tensor is interpreted in query/key/value split order from the GPT-2 family contract.",
            "The language-model head binding to wte.weight follows the GPT2LMHeadModel family contract; the NSD itself only observes wte.weight and the declared architecture name.",
            "No tensor values, numerical statistics, tokenizer behavior, forward execution, or functional equivalence were evaluated.",
            "Dropout values describe configured training-time operations; this graph does not choose a train/evaluation mode.",
        ],
        "evidence_boundary": (
            "A passed result verifies the selected GPT-2 family template against the observed "
            "configuration and tensor names/shapes. It does not prove that this graph reproduces "
            "the source model's numerical behavior."
        ),
    }
