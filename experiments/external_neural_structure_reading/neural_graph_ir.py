"""HFR-002: architecture-independent typed neural computation graph.

The GPT-2 family adapter is deliberately kept at the input boundary. Its output
is normalized into a small graph vocabulary (typed values, tensors, operations,
ports, and directed edges) that is not tied to GPT-2 tensor names or a specific
execution framework.

This module uses only NSD metadata and Safetensors headers. It never reads
tensor payloads and never executes source model code.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from .gpt2_adapter import GPT2InterpretationError, interpret_gpt2

GRAPH_SCHEMA = "in-formation-space.neural-computation-graph.v0.1"
GRAPH_IR_VERSION = "0.1.0"
TRANSFORMERS_REFERENCE = "https://huggingface.co/docs/transformers/main/model_doc/gpt2"
_LAYER_PREFIX = re.compile(r"^h\.(\d+)\.(.+)$")


class TopologyError(ValueError):
    """Raised when the NSD cannot be normalized into a complete, typed graph."""


def _port(name: str, dtype: str, shape: list[int | str]) -> dict[str, Any]:
    return {"name": name, "dtype": dtype, "shape": shape}


def _endpoint(kind: str, **values: str) -> dict[str, str]:
    return {"kind": kind, **values}


def _classify_tensor(name: str, config: dict[str, Any]) -> tuple[str, list[str]]:
    """Classify every supported GPT-2 tensor without relying on payload values."""
    global_roles = {
        "wte.weight": (
            "embedding.token_table",
            ["observed tensor name and shape", "GPT2LMHeadModel family contract"],
        ),
        "wpe.weight": (
            "embedding.position_table",
            ["observed tensor name and shape", "GPT2Model family contract"],
        ),
        "ln_f.weight": (
            "normalization.final.scale",
            ["observed tensor name and shape", "GPT2Model family contract"],
        ),
        "ln_f.bias": (
            "normalization.final.offset",
            ["observed tensor name and shape", "GPT2Model family contract"],
        ),
        "lm_head.weight": (
            "language_model_head.weight",
            ["observed tensor name and shape", "GPT2LMHeadModel family contract"],
        ),
    }
    if name in global_roles:
        return global_roles[name]

    match = _LAYER_PREFIX.fullmatch(name)
    if match is None:
        raise TopologyError(f"tensor name is outside the supported GPT-2 template: {name!r}")
    suffix = match.group(2)
    roles = {
        "attn.bias": "attention.causal_mask",
        "attn.c_attn.weight": "attention.fused_qkv.weight",
        "attn.c_attn.bias": "attention.fused_qkv.bias",
        "attn.c_proj.weight": "attention.output_projection.weight",
        "attn.c_proj.bias": "attention.output_projection.bias",
        "ln_1.weight": "normalization.attention.scale",
        "ln_1.bias": "normalization.attention.offset",
        "ln_2.weight": "normalization.mlp.scale",
        "ln_2.bias": "normalization.mlp.offset",
        "mlp.c_fc.weight": "mlp.expansion.weight",
        "mlp.c_fc.bias": "mlp.expansion.bias",
        "mlp.c_proj.weight": "mlp.contraction.weight",
        "mlp.c_proj.bias": "mlp.contraction.bias",
    }
    role = roles.get(suffix)
    if role is None:
        raise TopologyError(f"unsupported tensor role at {name!r}")
    return (
        f"transformer_block.{role}",
        [
            "observed tensor name and shape",
            "GPT2Block family contract",
            "dimensional compatibility with the surrounding operations",
        ],
    )


def _build_tensor_catalog(nsd: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    observed = nsd["observed"]
    shard_records = {
        item["path"]: item
        for item in observed["files"]
        if isinstance(item, dict) and item.get("role") == "safetensors-shard"
    }
    result: list[dict[str, Any]] = []
    for tensor in observed["tensor_manifest"]:
        name = tensor["name"]
        role, evidence = _classify_tensor(name, config)
        shard = tensor["shard"]
        source_file = shard_records.get(shard)
        if source_file is None:
            raise TopologyError(f"tensor {name!r} references a shard absent from the NSD file inventory")
        result.append(
            {
                "name": name,
                "dtype": tensor["dtype"],
                "shape": tensor["shape"],
                "source": {
                    "file": shard,
                    "data_offsets": tensor["data_offsets"],
                    "data_bytes": tensor["data_bytes"],
                    "header_sha256": source_file["sha256"],
                    "header_hash_scope": source_file["sha256_scope"],
                },
                "classification": {
                    "role": role,
                    "status": "family-interpreted",
                    "evidence": evidence,
                },
            }
        )
    result.sort(key=lambda item: item["name"])
    return result


def _operation(
    identifier: str,
    operator: str,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    attributes: dict[str, Any],
    *,
    semantic_basis: str = "GPT2LMHeadModel family contract",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "operator": operator,
        "inputs": inputs,
        "outputs": outputs,
        "attributes": attributes,
        "provenance": {
            "operator_semantics": {
                "status": "family-interpreted",
                "basis": semantic_basis,
                "reference": TRANSFORMERS_REFERENCE,
            },
            "port_shapes": {
                "status": "dimensionally-derived",
                "basis": "NSD configuration and tensor header shapes",
            },
        },
    }


def _edge(source: dict[str, str], target: dict[str, str], basis: str) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "provenance": {
            "status": "inferred-connection",
            "basis": basis,
        },
    }


def compile_gpt2_topology(nsd: dict[str, Any]) -> dict[str, Any]:
    """Normalize a supported GPT-2 NSD into the framework-independent graph IR."""
    if not isinstance(nsd, dict):
        raise TopologyError("NSD must be a JSON object")
    try:
        family_graph = interpret_gpt2(nsd)
    except GPT2InterpretationError as exc:
        raise TopologyError(f"GPT-2 family interpretation failed: {exc}") from exc

    source = nsd["source"]
    observed = nsd["observed"]
    config = observed["configuration"]
    dimensions = family_graph["dimensions"]
    hidden = dimensions["hidden_width"]
    vocabulary = dimensions["vocabulary_size"]
    context = dimensions["context_length"]
    layers = dimensions["layer_count"]
    heads = dimensions["attention_head_count"]
    head_width = dimensions["attention_head_width"]
    inner = dimensions["mlp_intermediate_width"]
    epsilon = float(config.get("layer_norm_epsilon", 1e-5))
    embd_pdrop = float(config.get("embd_pdrop", 0.1))
    attn_pdrop = float(config.get("attn_pdrop", 0.1))
    resid_pdrop = float(config.get("resid_pdrop", 0.1))
    activation = config.get("activation_function", "gelu_new")
    tied_head = config.get("tie_word_embeddings", True)

    batch = "batch"
    sequence = "sequence"
    hidden_shape = [batch, sequence, hidden]
    token_shape = [batch, sequence]

    tensor_catalog = _build_tensor_catalog(nsd, config)
    tensor_by_name = {item["name"]: item for item in tensor_catalog}
    operations: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    consumed_tensors: dict[str, list[str]] = defaultdict(list)

    def add(
        identifier: str,
        operator: str,
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        attributes: dict[str, Any],
    ) -> None:
        if any(node["id"] == identifier for node in operations):
            raise TopologyError(f"duplicate operation identifier: {identifier}")
        operations.append(_operation(identifier, operator, inputs, outputs, attributes))

    def input_edge(graph_input: str, operation: str, port: str) -> None:
        edges.append(
            _edge(
                _endpoint("graph_input", name=graph_input),
                _endpoint("operation_input", operation=operation, port=port),
                "named model input and GPT-2 forward contract",
            )
        )

    def tensor_edge(tensor_name: str, operation: str, port: str, basis: str | None = None) -> None:
        if tensor_name not in tensor_by_name:
            raise TopologyError(f"operation {operation!r} binds missing tensor {tensor_name!r}")
        edges.append(
            _edge(
                _endpoint("tensor", name=tensor_name),
                _endpoint("operation_input", operation=operation, port=port),
                basis or "tensor role and GPT-2 family operation contract",
            )
        )
        consumed_tensors[tensor_name].append(f"{operation}.{port}")

    def operation_edge(
        source_operation: str,
        source_port: str,
        target_operation: str,
        target_port: str,
        basis: str = "GPT-2 block ordering and typed dimensional compatibility",
    ) -> None:
        edges.append(
            _edge(
                _endpoint("operation_output", operation=source_operation, port=source_port),
                _endpoint("operation_input", operation=target_operation, port=target_port),
                basis,
            )
        )

    def output_edge(operation: str, port: str, graph_output: str) -> None:
        edges.append(
            _edge(
                _endpoint("operation_output", operation=operation, port=port),
                _endpoint("graph_output", name=graph_output),
                "declared GPT2LMHeadModel output contract",
            )
        )

    # Embedding path.
    add(
        "embedding.token_lookup",
        "embedding.lookup",
        [
            _port("indices", "I64", token_shape),
            _port("table", "F32", [vocabulary, hidden]),
        ],
        [_port("embeddings", "F32", hidden_shape)],
        {
            "vocabulary_size": vocabulary,
            "embedding_width": hidden,
            "padding_index": config.get("pad_token_id"),
        },
    )
    input_edge("token_ids", "embedding.token_lookup", "indices")
    tensor_edge("wte.weight", "embedding.token_lookup", "table")

    add(
        "embedding.position_lookup",
        "embedding.lookup",
        [
            _port("indices", "I64", token_shape),
            _port("table", "F32", [context, hidden]),
        ],
        [_port("embeddings", "F32", hidden_shape)],
        {
            "vocabulary_size": context,
            "embedding_width": hidden,
            "position_encoding": "learned_absolute",
        },
    )
    input_edge("position_ids", "embedding.position_lookup", "indices")
    tensor_edge("wpe.weight", "embedding.position_lookup", "table")

    add(
        "embedding.add",
        "tensor.add",
        [
            _port("token_embeddings", "F32", hidden_shape),
            _port("position_embeddings", "F32", hidden_shape),
        ],
        [_port("summed_embeddings", "F32", hidden_shape)],
        {"broadcasting": "none"},
    )
    operation_edge("embedding.token_lookup", "embeddings", "embedding.add", "token_embeddings")
    operation_edge("embedding.position_lookup", "embeddings", "embedding.add", "position_embeddings")

    add(
        "embedding.dropout",
        "regularization.dropout",
        [_port("value", "F32", hidden_shape)],
        [_port("output", "F32", hidden_shape)],
        {
            "probability": embd_pdrop,
            "runtime_mode": "active-during-training; identity-during-evaluation",
        },
    )
    operation_edge("embedding.add", "summed_embeddings", "embedding.dropout", "value")

    previous_operation = "embedding.dropout"
    previous_port = "output"

    # Repeated transformer blocks. Each block is expanded into primitive,
    # framework-independent operation types with explicit parameter edges.
    for index in range(layers):
        prefix = f"h.{index}."
        block = f"block.{index}"
        residual_shape = hidden_shape
        expanded_shape = [batch, sequence, inner]
        qkv_shape = [batch, sequence, 3 * hidden]

        ln1 = f"{block}.attention_norm"
        qkv = f"{block}.qkv_projection"
        attention = f"{block}.causal_attention"
        attention_projection = f"{block}.attention_output_projection"
        attention_dropout = f"{block}.attention_output_dropout"
        attention_add = f"{block}.attention_residual_add"
        ln2 = f"{block}.mlp_norm"
        mlp_expand = f"{block}.mlp_expansion"
        mlp_activation = f"{block}.mlp_activation"
        mlp_contract = f"{block}.mlp_contraction"
        mlp_dropout = f"{block}.mlp_output_dropout"
        mlp_add = f"{block}.mlp_residual_add"

        add(
            ln1,
            "normalization.layer_norm",
            [
                _port("value", "F32", residual_shape),
                _port("scale", "F32", [hidden]),
                _port("offset", "F32", [hidden]),
            ],
            [_port("normalized", "F32", residual_shape)],
            {"width": hidden, "epsilon": epsilon, "normalization_axes": [-1]},
        )
        operation_edge(previous_operation, previous_port, ln1, "value")
        tensor_edge(prefix + "ln_1.weight", ln1, "scale")
        tensor_edge(prefix + "ln_1.bias", ln1, "offset")

        add(
            qkv,
            "linear.affine",
            [
                _port("data", "F32", residual_shape),
                _port("weight", "F32", [hidden, 3 * hidden]),
                _port("bias", "F32", [3 * hidden]),
            ],
            [_port("projected", "F32", qkv_shape)],
            {
                "input_width": hidden,
                "output_width": 3 * hidden,
                "weight_layout": "input_by_output",
                "checkpoint_parameter_convention": "GPT-2 Conv1D",
            },
        )
        operation_edge(ln1, "normalized", qkv, "data")
        tensor_edge(prefix + "attn.c_attn.weight", qkv, "weight")
        tensor_edge(prefix + "attn.c_attn.bias", qkv, "bias")

        add(
            attention,
            "attention.causal_scaled_dot_product",
            [
                _port("fused_query_key_value", "F32", qkv_shape),
                _port("causal_mask", tensor_by_name[prefix + "attn.bias"]["dtype"], [1, 1, context, context]),
            ],
            [_port("context", "F32", residual_shape)],
            {
                "head_count": heads,
                "head_width": head_width,
                "qkv_partition_order": ["query", "key", "value"],
                "causal": True,
                "scale_by_sqrt_head_width": True,
                "attention_probability_dropout": attn_pdrop,
                "maximum_sequence_length": context,
                "mask_semantics": "causal_lower_triangle",
            },
        )
        operation_edge(qkv, "projected", attention, "fused_query_key_value")
        tensor_edge(
            prefix + "attn.bias",
            attention,
            "causal_mask",
            "mask role is inferred from GPT2Attention family contract; mask payload values are unobserved",
        )

        add(
            attention_projection,
            "linear.affine",
            [
                _port("data", "F32", residual_shape),
                _port("weight", "F32", [hidden, hidden]),
                _port("bias", "F32", [hidden]),
            ],
            [_port("projected", "F32", residual_shape)],
            {
                "input_width": hidden,
                "output_width": hidden,
                "weight_layout": "input_by_output",
                "checkpoint_parameter_convention": "GPT-2 Conv1D",
            },
        )
        operation_edge(attention, "context", attention_projection, "data")
        tensor_edge(prefix + "attn.c_proj.weight", attention_projection, "weight")
        tensor_edge(prefix + "attn.c_proj.bias", attention_projection, "bias")

        add(
            attention_dropout,
            "regularization.dropout",
            [_port("value", "F32", residual_shape)],
            [_port("output", "F32", residual_shape)],
            {
                "probability": resid_pdrop,
                "runtime_mode": "active-during-training; identity-during-evaluation",
            },
        )
        operation_edge(attention_projection, "projected", attention_dropout, "value")

        add(
            attention_add,
            "tensor.add",
            [
                _port("residual", "F32", residual_shape),
                _port("update", "F32", residual_shape),
            ],
            [_port("sum", "F32", residual_shape)],
            {"broadcasting": "none"},
        )
        operation_edge(previous_operation, previous_port, attention_add, "residual")
        operation_edge(attention_dropout, "output", attention_add, "update")

        add(
            ln2,
            "normalization.layer_norm",
            [
                _port("value", "F32", residual_shape),
                _port("scale", "F32", [hidden]),
                _port("offset", "F32", [hidden]),
            ],
            [_port("normalized", "F32", residual_shape)],
            {"width": hidden, "epsilon": epsilon, "normalization_axes": [-1]},
        )
        operation_edge(attention_add, "sum", ln2, "value")
        tensor_edge(prefix + "ln_2.weight", ln2, "scale")
        tensor_edge(prefix + "ln_2.bias", ln2, "offset")

        add(
            mlp_expand,
            "linear.affine",
            [
                _port("data", "F32", residual_shape),
                _port("weight", "F32", [hidden, inner]),
                _port("bias", "F32", [inner]),
            ],
            [_port("projected", "F32", expanded_shape)],
            {
                "input_width": hidden,
                "output_width": inner,
                "weight_layout": "input_by_output",
                "checkpoint_parameter_convention": "GPT-2 Conv1D",
            },
        )
        operation_edge(ln2, "normalized", mlp_expand, "data")
        tensor_edge(prefix + "mlp.c_fc.weight", mlp_expand, "weight")
        tensor_edge(prefix + "mlp.c_fc.bias", mlp_expand, "bias")

        add(
            mlp_activation,
            "activation.gelu_tanh",
            [_port("value", "F32", expanded_shape)],
            [_port("output", "F32", expanded_shape)],
            {
                "family_activation_name": activation,
                "mathematical_form": (
                    "0.5*x*(1+tanh(sqrt(2/pi)*(x+0.044715*x^3)))"
                ),
            },
        )
        operation_edge(mlp_expand, "projected", mlp_activation, "value")

        add(
            mlp_contract,
            "linear.affine",
            [
                _port("data", "F32", expanded_shape),
                _port("weight", "F32", [inner, hidden]),
                _port("bias", "F32", [hidden]),
            ],
            [_port("projected", "F32", residual_shape)],
            {
                "input_width": inner,
                "output_width": hidden,
                "weight_layout": "input_by_output",
                "checkpoint_parameter_convention": "GPT-2 Conv1D",
            },
        )
        operation_edge(mlp_activation, "output", mlp_contract, "data")
        tensor_edge(prefix + "mlp.c_proj.weight", mlp_contract, "weight")
        tensor_edge(prefix + "mlp.c_proj.bias", mlp_contract, "bias")

        add(
            mlp_dropout,
            "regularization.dropout",
            [_port("value", "F32", residual_shape)],
            [_port("output", "F32", residual_shape)],
            {
                "probability": resid_pdrop,
                "runtime_mode": "active-during-training; identity-during-evaluation",
            },
        )
        operation_edge(mlp_contract, "projected", mlp_dropout, "value")

        add(
            mlp_add,
            "tensor.add",
            [
                _port("residual", "F32", residual_shape),
                _port("update", "F32", residual_shape),
            ],
            [_port("sum", "F32", residual_shape)],
            {"broadcasting": "none"},
        )
        operation_edge(attention_add, "sum", mlp_add, "residual")
        operation_edge(mlp_dropout, "output", mlp_add, "update")

        previous_operation = mlp_add
        previous_port = "sum"

    add(
        "final.layer_norm",
        "normalization.layer_norm",
        [
            _port("value", "F32", hidden_shape),
            _port("scale", "F32", [hidden]),
            _port("offset", "F32", [hidden]),
        ],
        [_port("normalized", "F32", hidden_shape)],
        {"width": hidden, "epsilon": epsilon, "normalization_axes": [-1]},
    )
    operation_edge(previous_operation, previous_port, "final.layer_norm", "value")
    tensor_edge("ln_f.weight", "final.layer_norm", "scale")
    tensor_edge("ln_f.bias", "final.layer_norm", "offset")

    if tied_head:
        head_tensor = "wte.weight"
        head_binding_basis = (
            "GPT2LMHeadModel tied-embedding family contract; no separate head tensor is observed"
        )
    else:
        head_tensor = "lm_head.weight"
        head_binding_basis = "separate observed language-model head tensor"

    add(
        "language_model_head",
        "linear.affine",
        [
            _port("data", "F32", hidden_shape),
            _port("weight", "F32", [vocabulary, hidden]),
        ],
        [_port("logits", "F32", [batch, sequence, vocabulary])],
        {
            "input_width": hidden,
            "output_width": vocabulary,
            "weight_layout": "output_by_input",
            "weight_view": "transpose",
            "binding_status": "family-contract-tied" if tied_head else "separate-observed-tensor",
            "weight_binding_basis": head_binding_basis,
        },
    )
    operation_edge("final.layer_norm", "normalized", "language_model_head", "data")
    tensor_edge(head_tensor, "language_model_head", "weight", head_binding_basis)
    output_edge("language_model_head", "logits", "logits")

    graph_inputs = [
        {
            "name": "token_ids",
            "dtype": "I64",
            "shape": token_shape,
            "semantic_role": "input_token_identifiers",
        },
        {
            "name": "position_ids",
            "dtype": "I64",
            "shape": token_shape,
            "semantic_role": "learned_absolute_position_indices",
        },
    ]
    graph_outputs = [
        {
            "name": "logits",
            "dtype": "F32",
            "shape": [batch, sequence, vocabulary],
            "semantic_role": "next_token_vocabulary_scores",
        }
    ]
    source_files = []
    for item in observed["files"]:
        source_files.append(
            {
                "path": item["path"],
                "role": item["role"],
                "sha256": item["sha256"],
                "sha256_scope": item["sha256_scope"],
                "size_bytes": item["size_bytes"],
            }
        )
    source_files.sort(key=lambda item: item["path"])

    graph = {
        "schema": GRAPH_SCHEMA,
        "ir_version": GRAPH_IR_VERSION,
        "source_observation": {
            "repository": source["repository"],
            "revision": source["revision"],
            "license_id": source.get("license_id"),
            "nsd_schema": nsd["schema"],
            "source_files": source_files,
        },
        "model_family_adapter": {
            "id": "hfr-002.gpt2-family-adapter",
            "version": "0.1.0",
            "family": "GPT2LMHeadModel",
            "reference": TRANSFORMERS_REFERENCE,
            "status": "family-interpreted",
        },
        "dimension_symbols": {
            "batch": {"kind": "runtime", "value": None, "minimum": 1},
            "sequence": {"kind": "runtime", "value": None, "minimum": 1, "maximum": context},
            "hidden": {"kind": "fixed", "value": hidden},
            "vocabulary": {"kind": "fixed", "value": vocabulary},
            "context": {"kind": "fixed", "value": context},
            "heads": {"kind": "fixed", "value": heads},
            "head_width": {"kind": "fixed", "value": head_width},
            "mlp_width": {"kind": "fixed", "value": inner},
        },
        "inputs": graph_inputs,
        "outputs": graph_outputs,
        "tensors": tensor_catalog,
        "operations": operations,
        "edges": edges,
        "completeness": {
            "status": "pending-verification",
            "observed_tensor_count": len(observed["tensor_manifest"]),
            "classified_tensor_count": len(tensor_catalog),
            "bound_tensor_count": len(consumed_tensors),
            "unclassified_tensors": [],
            "unused_tensors": [],
            "unsupported_components": [],
            "missing_expected_components": [],
        },
        "verification": {
            "status": "pending",
            "checks": [],
        },
        "evidence_policy": {
            "tensor_identity_dtype_shape_offsets": "observed-from-NSD",
            "tensor_roles": "interpreted-from-tensor-names-dimensions-and-GPT2-family-contract",
            "operator_types_and_semantics": "interpreted-from-GPT2-family-contract",
            "directed_connections": "inferred-from-GPT2-family-order-and-validated-by-typed-ports",
            "port_dimensions": "derived-from-observed-configuration-and-tensor-shapes",
            "numerical_parameter_values": "not-observed",
            "execution_behavior": "not-tested",
        },
        "assumptions_and_unresolved": [
            "The graph is a GPT-2 family interpretation expressed in a framework-independent IR; it is not a framework-independent discovery of the family semantics.",
            "The causal meaning of attn.bias is inferred from the GPT-2 family contract; its numerical payload was not read.",
            "The fused QKV partition order is interpreted as query, key, value from the GPT-2 family contract.",
            "The language-model head uses the token embedding tensor when tie_word_embeddings is effective; if that field is absent, the value comes from the GPT-2 family default.",
            "Position IDs are explicit graph inputs; a caller that omits them must supply the documented GPT-2 position-generation behavior outside this graph.",
            "Dropout operators are represented with configured probabilities; runtime training/evaluation mode is not selected by this graph.",
            "The graph has not been numerically executed and does not establish functional equivalence to the source model.",
        ],
    }
    verification = verify_typed_graph(graph, nsd)
    graph["completeness"].update(verification["completeness"])
    graph["verification"] = verification["verification"]
    return graph


def _shape_is_valid(shape: Any) -> bool:
    return isinstance(shape, list) and all(
        (type(item) is int and item >= 0)
        or (isinstance(item, str) and bool(item))
        for item in shape
    )


def _operation_contract(operation: dict[str, Any]) -> list[str]:
    """Check local dimensional contracts for the canonical operator vocabulary."""
    failures: list[str] = []
    operator = operation["operator"]
    inputs = {port["name"]: port for port in operation["inputs"]}
    outputs = {port["name"]: port for port in operation["outputs"]}
    attributes = operation["attributes"]

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(f"{operation['id']}: {message}")

    if operator == "embedding.lookup":
        require(set(inputs) == {"indices", "table"}, "embedding.lookup needs indices and table")
        require(set(outputs) == {"embeddings"}, "embedding.lookup needs embeddings output")
        if set(inputs) == {"indices", "table"} and set(outputs) == {"embeddings"}:
            index_shape = inputs["indices"]["shape"]
            table_shape = inputs["table"]["shape"]
            output_shape = outputs["embeddings"]["shape"]
            require(len(table_shape) == 2, "embedding table must be rank 2")
            require(len(output_shape) == len(index_shape) + 1, "embedding output rank must be index rank + 1")
            if len(table_shape) == 2 and output_shape:
                require(output_shape[:-1] == index_shape, "embedding output leading dimensions must match indices")
                require(output_shape[-1] == table_shape[-1], "embedding output width must match table width")
                require(inputs["indices"]["dtype"] == "I64", "embedding indices must be I64")
                require(inputs["table"]["dtype"] == outputs["embeddings"]["dtype"], "embedding table/output dtype mismatch")
    elif operator == "tensor.add":
        require(set(inputs) in ({"left", "right"}, {"token_embeddings", "position_embeddings"}, {"residual", "update"}), "tensor.add has an unsupported input signature")
        require(len(outputs) == 1, "tensor.add must have one output")
        if len(inputs) == 2 and len(outputs) == 1:
            first, second = list(inputs.values())
            result = next(iter(outputs.values()))
            require(first["shape"] == second["shape"] == result["shape"], "tensor.add shapes must be equal")
            require(first["dtype"] == second["dtype"] == result["dtype"], "tensor.add dtypes must be equal")
    elif operator == "regularization.dropout":
        require(set(inputs) == {"value"} and set(outputs) == {"output"}, "dropout port signature is invalid")
        if inputs and outputs:
            require(inputs["value"]["shape"] == outputs["output"]["shape"], "dropout must preserve shape")
            require(inputs["value"]["dtype"] == outputs["output"]["dtype"], "dropout must preserve dtype")
        probability = attributes.get("probability")
        require(
            isinstance(probability, (int, float)) and not isinstance(probability, bool) and 0 <= probability < 1,
            "dropout probability must be in [0, 1)",
        )
    elif operator == "normalization.layer_norm":
        require(set(inputs) == {"value", "scale", "offset"}, "layer_norm port signature is invalid")
        require(set(outputs) == {"normalized"}, "layer_norm output signature is invalid")
        if set(inputs) == {"value", "scale", "offset"} and outputs:
            value = inputs["value"]["shape"]
            scale = inputs["scale"]["shape"]
            offset = inputs["offset"]["shape"]
            normalized = outputs["normalized"]["shape"]
            require(bool(value), "layer_norm input must have rank >= 1")
            if value:
                require(scale == offset == [value[-1]], "layer_norm scale/offset must match final width")
                require(normalized == value, "layer_norm must preserve shape")
        epsilon = attributes.get("epsilon")
        require(isinstance(epsilon, (int, float)) and epsilon > 0, "layer_norm epsilon must be positive")
    elif operator == "linear.affine":
        require(set(inputs) in ({"data", "weight", "bias"}, {"data", "weight"}), "linear.affine port signature is invalid")
        require(len(outputs) == 1, "linear.affine must have one output")
        if "data" in inputs and "weight" in inputs and outputs:
            data_shape = inputs["data"]["shape"]
            weight_shape = inputs["weight"]["shape"]
            output_shape = next(iter(outputs.values()))["shape"]
            weight_layout = attributes.get("weight_layout")
            require(bool(data_shape) and len(weight_shape) == 2, "linear.affine expects data rank >= 1 and a rank-2 weight")
            if data_shape and len(weight_shape) == 2:
                input_width = data_shape[-1]
                if weight_layout == "input_by_output":
                    expected_in, expected_out = weight_shape
                elif weight_layout == "output_by_input":
                    expected_out, expected_in = weight_shape
                else:
                    expected_in, expected_out = None, None
                    require(False, "weight_layout must be input_by_output or output_by_input")
                require(expected_in == input_width, "linear.affine input width does not match weight")
                require(output_shape == data_shape[:-1] + [expected_out], "linear.affine output shape is incompatible")
                if "bias" in inputs:
                    require(inputs["bias"]["shape"] == [expected_out], "linear.affine bias width is incompatible")
                    require(inputs["bias"]["dtype"] == inputs["data"]["dtype"], "linear.affine bias dtype mismatch")
                require(inputs["weight"]["dtype"] == inputs["data"]["dtype"], "linear.affine weight dtype mismatch")
                require(next(iter(outputs.values()))["dtype"] == inputs["data"]["dtype"], "linear.affine output dtype mismatch")
    elif operator == "attention.causal_scaled_dot_product":
        require(set(inputs) == {"fused_query_key_value", "causal_mask"}, "causal attention input signature is invalid")
        require(set(outputs) == {"context"}, "causal attention output signature is invalid")
        if set(inputs) == {"fused_query_key_value", "causal_mask"} and outputs:
            qkv = inputs["fused_query_key_value"]["shape"]
            mask = inputs["causal_mask"]["shape"]
            output = outputs["context"]["shape"]
            heads = attributes.get("head_count")
            width = attributes.get("head_width")
            require(bool(qkv) and len(qkv) >= 2, "fused QKV input must include sequence and feature axes")
            if qkv:
                require(qkv[-1] == 3 * heads * width, "fused QKV width must equal 3 * heads * head_width")
                require(output == qkv[:-1] + [heads * width], "attention output shape is incompatible with QKV width")
            require(len(mask) == 4 and mask[0:2] == [1, 1], "causal mask must have shape [1, 1, context, context]")
            require(mask[2] == mask[3], "causal mask must be square")
            require(attributes.get("causal") is True, "attention must declare causal masking")
            require(attributes.get("scale_by_sqrt_head_width") is True, "attention must declare scaled dot-product")
    elif operator == "activation.gelu_tanh":
        require(set(inputs) == {"value"} and set(outputs) == {"output"}, "GELU port signature is invalid")
        if inputs and outputs:
            require(inputs["value"]["shape"] == outputs["output"]["shape"], "GELU must preserve shape")
            require(inputs["value"]["dtype"] == outputs["output"]["dtype"], "GELU must preserve dtype")
    else:
        failures.append(f"{operation['id']}: unknown canonical operator {operator!r}")
    return failures


def verify_typed_graph(graph: dict[str, Any], nsd: dict[str, Any]) -> dict[str, Any]:
    """Validate graph structure, complete tensor classification, types, shapes, and DAG topology."""
    failures: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(identifier: str, passed: bool, detail: str) -> None:
        checks.append({"id": identifier, "status": "passed" if passed else "failed", "detail": detail})
        if not passed:
            failures.append(f"{identifier}: {detail}")

    check("graph-schema", graph.get("schema") == GRAPH_SCHEMA, "canonical graph schema identifier")
    nsd_manifest = nsd.get("observed", {}).get("tensor_manifest", [])
    nsd_by_name = {
        item.get("name"): item for item in nsd_manifest
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }

    tensor_items = graph.get("tensors", [])
    tensor_by_name: dict[str, dict[str, Any]] = {}
    duplicate_tensors = False
    for item in tensor_items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            failures.append("tensor catalog contains an invalid item")
            continue
        if item["name"] in tensor_by_name:
            duplicate_tensors = True
        tensor_by_name[item["name"]] = item
    observed_names = set(nsd_by_name)
    classified_names = set(tensor_by_name)
    missing_classifications = sorted(observed_names - classified_names)
    extra_classifications = sorted(classified_names - observed_names)
    check(
        "tensor-classification-bijection",
        not duplicate_tensors and not missing_classifications and not extra_classifications,
        f"observed={len(observed_names)}, classified={len(classified_names)}, "
        f"missing={missing_classifications[:5]}, extra={extra_classifications[:5]}",
    )

    tensor_binding_mismatches: list[str] = []
    for name in sorted(observed_names & classified_names):
        observed_tensor = nsd_by_name[name]
        graph_tensor = tensor_by_name[name]
        if (
            graph_tensor.get("dtype") != observed_tensor.get("dtype")
            or graph_tensor.get("shape") != observed_tensor.get("shape")
            or graph_tensor.get("source", {}).get("file") != observed_tensor.get("shard")
            or graph_tensor.get("source", {}).get("data_offsets") != observed_tensor.get("data_offsets")
        ):
            tensor_binding_mismatches.append(name)
    check(
        "observed-tensor-fidelity",
        not tensor_binding_mismatches,
        f"tensor metadata matches NSD for {len(observed_names) - len(tensor_binding_mismatches)} entries; "
        f"mismatches={tensor_binding_mismatches[:5]}",
    )

    operations = graph.get("operations", [])
    operation_by_id: dict[str, dict[str, Any]] = {}
    duplicate_operations = False
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("id"), str):
            failures.append("operation list contains an invalid item")
            continue
        if operation["id"] in operation_by_id:
            duplicate_operations = True
        operation_by_id[operation["id"]] = operation
    check("unique-operation-identifiers", not duplicate_operations, f"{len(operation_by_id)} operation identifiers")

    graph_inputs = {item["name"]: item for item in graph.get("inputs", [])}
    graph_outputs = {item["name"]: item for item in graph.get("outputs", [])}
    input_ports: dict[tuple[str, str], dict[str, Any]] = {}
    output_ports: dict[tuple[str, str], dict[str, Any]] = {}
    invalid_ports: list[str] = []
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        for direction, port_map in (("inputs", input_ports), ("outputs", output_ports)):
            seen: set[str] = set()
            for port in operation.get(direction, []):
                if not isinstance(port, dict) or not isinstance(port.get("name"), str):
                    invalid_ports.append(f"{operation.get('id')}:{direction}")
                    continue
                name = port["name"]
                if name in seen or not isinstance(port.get("dtype"), str) or not _shape_is_valid(port.get("shape")):
                    invalid_ports.append(f"{operation.get('id')}:{direction}.{name}")
                    continue
                seen.add(name)
                port_map[(operation["id"], name)] = port
    check("typed-operation-ports", not invalid_ports, f"{len(input_ports)} input ports, {len(output_ports)} output ports; invalid={invalid_ports[:5]}")

    edge_targets: dict[tuple[str, str, str], int] = defaultdict(int)
    edge_sources: dict[tuple[str, str, str], int] = defaultdict(int)
    edge_keys: set[tuple[str, str, str, str, str, str]] = set()
    adjacency: dict[str, set[str]] = defaultdict(set)
    edge_failures: list[str] = []
    used_tensors: dict[str, int] = defaultdict(int)
    used_inputs: dict[str, int] = defaultdict(int)
    used_outputs: dict[str, int] = defaultdict(int)

    def resolve_source(endpoint: dict[str, Any]) -> dict[str, Any] | None:
        kind = endpoint.get("kind")
        if kind == "graph_input":
            return graph_inputs.get(endpoint.get("name"))
        if kind == "tensor":
            return tensor_by_name.get(endpoint.get("name"))
        if kind == "operation_output":
            return output_ports.get((endpoint.get("operation"), endpoint.get("port")))
        return None

    def resolve_target(endpoint: dict[str, Any]) -> dict[str, Any] | None:
        kind = endpoint.get("kind")
        if kind == "operation_input":
            return input_ports.get((endpoint.get("operation"), endpoint.get("port")))
        if kind == "graph_output":
            return graph_outputs.get(endpoint.get("name"))
        return None

    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            edge_failures.append("edge is not an object")
            continue
        src = edge.get("source", {})
        dst = edge.get("target", {})
        if not isinstance(src, dict) or not isinstance(dst, dict):
            edge_failures.append("edge endpoints must be objects")
            continue
        src_kind, dst_kind = src.get("kind"), dst.get("kind")
        source_port = resolve_source(src)
        target_port = resolve_target(dst)
        if source_port is None:
            edge_failures.append(f"unresolved source endpoint: {src}")
            continue
        if target_port is None:
            edge_failures.append(f"unresolved target endpoint: {dst}")
            continue
        if source_port.get("dtype") != target_port.get("dtype") or source_port.get("shape") != target_port.get("shape"):
            edge_failures.append(f"type/shape mismatch: {src} -> {dst}")
        target_key = (
            dst_kind,
            dst.get("operation", dst.get("name", "")),
            dst.get("port", ""),
        )
        source_key = (
            src_kind,
            src.get("operation", src.get("name", "")),
            src.get("port", ""),
        )
        edge_targets[target_key] += 1
        edge_sources[source_key] += 1
        key = (src_kind, source_key[1], source_key[2], dst_kind, target_key[1], target_key[2])
        if key in edge_keys:
            edge_failures.append(f"duplicate edge: {src} -> {dst}")
        edge_keys.add(key)

        if src_kind == "tensor":
            used_tensors[src.get("name", "")] += 1
        elif src_kind == "graph_input":
            used_inputs[src.get("name", "")] += 1
        elif src_kind == "operation_output" and dst_kind == "operation_input":
            adjacency[src.get("operation", "")].add(dst.get("operation", ""))
        elif src_kind == "operation_output" and dst_kind == "graph_output":
            used_outputs[dst.get("name", "")] += 1

    expected_targets = len(input_ports) + len(graph_outputs)
    incoming_once = all(value == 1 for value in edge_targets.values()) and len(edge_targets) == expected_targets
    outgoing_once = (
        all(edge_sources.get(("graph_input", name, ""), 0) == 1 for name in graph_inputs)
        and all(edge_sources.get(("operation_output", op_id, port_name), 0) == 1 for op_id, port_name in output_ports)
    )
    every_tensor_used = set(used_tensors) == set(tensor_by_name)
    edges_valid = not edge_failures
    check("edge-endpoint-and-type-integrity", edges_valid, f"{len(graph.get('edges', []))} edges; failures={edge_failures[:5]}")
    check("single-producer-input-ports", incoming_once, f"each of {expected_targets} operation/graph-output input ports has exactly one source")
    check("single-consumer-operation-outputs", outgoing_once, "every graph input and operation output has exactly one consumer")
    check("complete-tensor-usage", every_tensor_used, f"used={len(used_tensors)}, catalog={len(tensor_by_name)}, unused={sorted(set(tensor_by_name)-set(used_tensors))[:5]}")

    local_failures: list[str] = []
    for operation in operations:
        if isinstance(operation, dict):
            local_failures.extend(_operation_contract(operation))
    check("operator-dimensional-contracts", not local_failures, f"{len(operations)} operations checked; failures={local_failures[:8]}")

    # All operation vertices must form a DAG.
    indegree = {identifier: 0 for identifier in operation_by_id}
    for source_id, targets in adjacency.items():
        if source_id not in operation_by_id:
            edge_failures.append(f"adjacency references missing source operation {source_id}")
            continue
        for target_id in targets:
            if target_id not in operation_by_id:
                edge_failures.append(f"adjacency references missing target operation {target_id}")
                continue
            indegree[target_id] += 1
    queue = deque(sorted(identifier for identifier, degree in indegree.items() if degree == 0))
    visited: list[str] = []
    while queue:
        identifier = queue.popleft()
        visited.append(identifier)
        for target_id in sorted(adjacency.get(identifier, set())):
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)
    is_dag = len(visited) == len(operation_by_id) and not edge_failures
    check("acyclic-operation-topology", is_dag, f"topologically ordered {len(visited)} of {len(operation_by_id)} operations")

    input_integrity = all(used_inputs.get(name) == 1 for name in graph_inputs)
    output_integrity = all(used_outputs.get(name) == 1 for name in graph_outputs)
    check("graph-interface-connectivity", input_integrity and output_integrity, "every declared graph input and output is connected exactly once")

    expected_tensor_count = len(nsd_manifest)
    classified_count = len(classified_names & observed_names)
    bound_count = len(used_tensors)
    unused = sorted(set(tensor_by_name) - set(used_tensors))
    unclassified = sorted(observed_names - classified_names)
    completeness_status = (
        "complete-for-supported-family-template"
        if classified_count == expected_tensor_count and bound_count == expected_tensor_count and not unused and not unclassified
        else "incomplete"
    )
    completeness = {
        "status": completeness_status,
        "observed_tensor_count": expected_tensor_count,
        "classified_tensor_count": classified_count,
        "bound_tensor_count": bound_count,
        "unclassified_tensors": unclassified,
        "unused_tensors": unused,
        "unsupported_components": [],
        "missing_expected_components": [],
    }
    passed = [item for item in checks if item["status"] == "passed"]
    failed = [item for item in checks if item["status"] == "failed"]
    verification = {
        "status": "passed" if not failures else "failed",
        "passed_check_count": len(passed),
        "failed_check_count": len(failed),
        "operation_count": len(operations),
        "edge_count": len(graph.get("edges", [])),
        "input_port_count": len(input_ports),
        "output_port_count": len(output_ports),
        "checks": checks,
    }
    return {"completeness": completeness, "verification": verification}


def validate_graph_or_raise(graph: dict[str, Any], nsd: dict[str, Any]) -> None:
    result = verify_typed_graph(graph, nsd)
    if result["verification"]["status"] != "passed":
        failures = [
            item["id"] + ": " + item["detail"]
            for item in result["verification"]["checks"]
            if item["status"] != "passed"
        ]
        raise TopologyError("typed graph validation failed: " + "; ".join(failures))


if __name__ == "__main__":
    raise SystemExit("Use the live-reference runner or import compile_gpt2_topology().")
