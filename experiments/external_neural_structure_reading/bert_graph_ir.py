"""HFR-002 BERT encoder and checkpoint-head adapter for the canonical typed graph IR.

The pinned google-bert/bert-base-uncased config declares BertForMaskedLM,
but its Safetensors inventory also contains a pooler and NSP classifier.
This adapter preserves BOTH checkpoint-present heads as separately named graph
outputs; it does not mistake the configuration label for complete checkpoint
inventory evidence. No numerical payloads are loaded.
"""
from __future__ import annotations

import math
from typing import Any

try:
    from .neural_graph_ir import (
        GRAPH_SCHEMA, _edge, _endpoint, _operation, _port, verify_typed_graph,
    )
except ImportError:
    from neural_graph_ir import (
        GRAPH_SCHEMA, _edge, _endpoint, _operation, _port, verify_typed_graph,
    )

BERT_REFERENCE = "https://huggingface.co/docs/transformers/model_doc/bert"
BERT_ADAPTER = "hfr-002.bert-encoder-pretraining-heads"
NSD_SCHEMA = "in-formation-space.neural-structure-description.v0.1"


class BertTopologyError(ValueError):
    """The observed tensor manifest is incompatible with this BERT variant."""


def _positive(value: Any, name: str) -> int:
    """Require a strictly positive, non-boolean configuration integer."""
    if type(value) is not int or value <= 0:
        raise BertTopologyError(f"{name} must be a positive integer")
    return value


def _probability(value: Any, name: str) -> float:
    """Reject invalid dropout settings instead of coercing them."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BertTopologyError(f"{name} must be a numeric dropout probability")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result < 1:
        raise BertTopologyError(f"{name} must be finite and in [0, 1)")
    return result


def _expected_tensors(config: dict[str, Any]) -> dict[str, tuple[list[int], str]]:
    """Derive exhaustive BERT/MLM/NSP tensor shapes from observed configuration."""
    hidden = _positive(config.get("hidden_size"), "hidden_size")
    context = _positive(config.get("max_position_embeddings"), "max_position_embeddings")
    vocab = _positive(config.get("vocab_size"), "vocab_size")
    types = _positive(config.get("type_vocab_size"), "type_vocab_size")
    layers = _positive(config.get("num_hidden_layers"), "num_hidden_layers")
    inner = _positive(config.get("intermediate_size"), "intermediate_size")

    expected: dict[str, tuple[list[int], str]] = {
        "bert.embeddings.word_embeddings.weight": ([vocab, hidden], "embedding.token_table"),
        "bert.embeddings.position_embeddings.weight": ([context, hidden], "embedding.position_table"),
        "bert.embeddings.token_type_embeddings.weight": ([types, hidden], "embedding.token_type_table"),
        "bert.embeddings.LayerNorm.gamma": ([hidden], "embedding.norm.scale"),
        "bert.embeddings.LayerNorm.beta": ([hidden], "embedding.norm.offset"),
        "bert.pooler.dense.weight": ([hidden, hidden], "pooler.projection.weight"),
        "bert.pooler.dense.bias": ([hidden], "pooler.projection.bias"),
        "cls.predictions.transform.dense.weight": ([hidden, hidden], "mlm.transform.weight"),
        "cls.predictions.transform.dense.bias": ([hidden], "mlm.transform.bias"),
        "cls.predictions.transform.LayerNorm.gamma": ([hidden], "mlm.norm.scale"),
        "cls.predictions.transform.LayerNorm.beta": ([hidden], "mlm.norm.offset"),
        "cls.predictions.bias": ([vocab], "mlm.output_bias"),
        "cls.seq_relationship.weight": ([2, hidden], "next_sentence.projection.weight"),
        "cls.seq_relationship.bias": ([2], "next_sentence.projection.bias"),
    }
    suffixes = {
        "attention.self.query.weight": ([hidden, hidden], "attention.query.weight"),
        "attention.self.query.bias": ([hidden], "attention.query.bias"),
        "attention.self.key.weight": ([hidden, hidden], "attention.key.weight"),
        "attention.self.key.bias": ([hidden], "attention.key.bias"),
        "attention.self.value.weight": ([hidden, hidden], "attention.value.weight"),
        "attention.self.value.bias": ([hidden], "attention.value.bias"),
        "attention.output.dense.weight": ([hidden, hidden], "attention.output.weight"),
        "attention.output.dense.bias": ([hidden], "attention.output.bias"),
        "attention.output.LayerNorm.gamma": ([hidden], "attention.norm.scale"),
        "attention.output.LayerNorm.beta": ([hidden], "attention.norm.offset"),
        "intermediate.dense.weight": ([inner, hidden], "mlp.expand.weight"),
        "intermediate.dense.bias": ([inner], "mlp.expand.bias"),
        "output.dense.weight": ([hidden, inner], "mlp.contract.weight"),
        "output.dense.bias": ([hidden], "mlp.contract.bias"),
        "output.LayerNorm.gamma": ([hidden], "mlp.norm.scale"),
        "output.LayerNorm.beta": ([hidden], "mlp.norm.offset"),
    }
    for i in range(layers):
        for suffix, (shape, role) in suffixes.items():
            expected[f"bert.encoder.layer.{i}.{suffix}"] = (
                list(shape),
                f"encoder.layer.{i}.{role}",
            )
    return expected


def compile_bert_topology(nsd: dict[str, Any]) -> dict[str, Any]:
    """Construct and independently type-check a BERT checkpoint's two-head graph.

    The supported profile requires:
    - bert encoder, absolute positions, non-decoder, non-cross attention;
    - erf-based GELU (config hidden_act='gelu');
    - separate Q/K/V projections and post-residual layer normalization;
    - checkpoint-present MLM transform/head AND pooled NSP head;
    - tied word-embedding/MLM decoder weight, with no independent decoder tensor.

    The pinned checkpoint's config may declare BertForMaskedLM while containing
    additional pooler/NSP tensors. These are preserved as checkpoint-present,
    not claimed to be active in every application of the checkpoint.
    """
    if not isinstance(nsd, dict) or nsd.get("schema") != NSD_SCHEMA:
        raise BertTopologyError("expected an HFR Neural Structure Description v0.1")
    source = nsd.get("source")
    observed = nsd.get("observed")
    if not isinstance(source, dict) or not isinstance(observed, dict):
        raise BertTopologyError("NSD source and observed sections are required")
    config = observed.get("configuration")
    manifest = observed.get("tensor_manifest")
    files = observed.get("files")
    if not isinstance(config, dict) or not isinstance(manifest, list) or not isinstance(files, list):
        raise BertTopologyError("NSD requires configuration, tensor_manifest, and files")
    if config.get("model_type") != "bert":
        raise BertTopologyError("only model_type='bert' is supported")
    architectures = config.get("architectures")
    if not isinstance(architectures, list) or not any(
        a in {"BertForMaskedLM", "BertForPreTraining"} for a in architectures
    ):
        raise BertTopologyError("checkpoint must declare a recognized BERT pretraining family")
    if config.get("hidden_act") != "gelu":
        raise BertTopologyError("only erf GELU hidden_act='gelu' is supported")
    if config.get("position_embedding_type", "absolute") != "absolute":
        raise BertTopologyError("only absolute position embeddings are supported")
    if config.get("is_decoder", False) or config.get("add_cross_attention", False):
        raise BertTopologyError("decoder and cross-attention profiles are unsupported")
    if config.get("tie_word_embeddings", True) is False:
        raise BertTopologyError("this checkpoint profile requires the tied MLM output head")
    hidden = _positive(config.get("hidden_size"), "hidden_size")
    context = _positive(config.get("max_position_embeddings"), "max_position_embeddings")
    vocab = _positive(config.get("vocab_size"), "vocab_size")
    types = _positive(config.get("type_vocab_size"), "type_vocab_size")
    layers = _positive(config.get("num_hidden_layers"), "num_hidden_layers")
    inner = _positive(config.get("intermediate_size"), "intermediate_size")
    heads = _positive(config.get("num_attention_heads"), "num_attention_heads")
    if hidden % heads:
        raise BertTopologyError("hidden_size must be divisible by num_attention_heads")
    head_width = hidden // heads
    attn_dropout = _probability(config.get("attention_probs_dropout_prob", 0.1), "attention_probs_dropout_prob")
    hidden_dropout = _probability(config.get("hidden_dropout_prob", 0.1), "hidden_dropout_prob")
    epsilon = config.get("layer_norm_eps", 1e-12)
    if isinstance(epsilon, bool) or not isinstance(epsilon, (int, float)) or not math.isfinite(float(epsilon)) or epsilon <= 0:
        raise BertTopologyError("layer_norm_eps must be finite and positive")

    expected = _expected_tensors(config)
    records: dict[str, dict[str, Any]] = {}
    for item in manifest:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise BertTopologyError("tensor manifest has an invalid entry")
        name = item["name"]
        if name in records:
            raise BertTopologyError(f"duplicate observed tensor: {name}")
        records[name] = item
    missing, unexpected = sorted(set(expected) - set(records)), sorted(set(records) - set(expected))
    if missing or unexpected:
        raise BertTopologyError(f"checkpoint tensor inventory differs from the supported BERT template: missing={missing[:5]}, unexpected={unexpected[:5]}")
    shards = {item["path"]: item for item in files if item.get("role") == "safetensors-shard" and isinstance(item.get("path"), str)}
    catalog: list[dict[str, Any]] = []
    for name in sorted(expected):
        shape, role = expected[name]
        item = records[name]
        if item.get("shape") != shape or item.get("dtype") != "F32":
            raise BertTopologyError(f"tensor {name} has incompatible shape/dtype: expected F32 {shape}, got {item.get('dtype')} {item.get('shape')}")
        shard = item.get("shard")
        file = shards.get(shard)
        if file is None:
            raise BertTopologyError(f"tensor {name} has no observed shard-header record")
        catalog.append({
            "name": name,
            "dtype": item["dtype"],
            "shape": list(shape),
            "source": {
                "file": shard,
                "data_offsets": item["data_offsets"],
                "data_bytes": item["data_bytes"],
                "header_sha256": file["sha256"],
                "header_hash_scope": file["sha256_scope"],
            },
            "classification": {
                "role": role,
                "status": "family-interpreted",
                "evidence": [
                    "observed tensor name, F32 dtype and exact shape",
                    "BERT encoder, MLM transformation and checkpoint-present NSP family contract",
                ],
            },
        })

    B, S = "batch", "sequence"
    S3 = [B, S, hidden]
    S2 = [B, S]
    M3 = [B, S, inner]
    operations: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    operation_ids: set[str] = set()
    tensor_names = set(records)

    def add(identifier: str, operator: str, inputs: list[dict[str, Any]], outputs: list[dict[str, Any]], attributes: dict[str, Any]) -> None:
        """Insert a canonical operation with BERT-specific semantic provenance."""
        if identifier in operation_ids:
            raise BertTopologyError(f"duplicate operation id: {identifier}")
        operation_ids.add(identifier)
        operations.append(_operation(identifier, operator, inputs, outputs, attributes,
            semantic_basis="BERT checkpoint family semantics, separate from observed tensor headers",
            semantic_reference=BERT_REFERENCE))

    def bind_tensor(tensor: str, dest: str, port: str, basis: str = "observed tensor role and BERT family contract") -> None:
        """Bind an observed tensor as a producer, without loading its values."""
        if tensor not in tensor_names:
            raise BertTopologyError(f"operation {dest} requires missing tensor {tensor}")
        edges.append(_edge(_endpoint("tensor", name=tensor), _endpoint("operation_input", operation=dest, port=port), basis))

    def bind_input(name: str, dest: str, port: str) -> None:
        """Connect a declared external graph input once."""
        edges.append(_edge(_endpoint("graph_input", name=name), _endpoint("operation_input", operation=dest, port=port),
                           "explicit BERT graph input and caller-supplied runtime value"))

    def link(upstream: str, out: str, downstream: str, target: str) -> None:
        """Connect two operation ports by the BERT family ordering hypothesis."""
        edges.append(_edge(
            _endpoint("operation_output", operation=upstream, port=out),
            _endpoint("operation_input", operation=downstream, port=target),
            "BERT family ordering hypothesis, checked against canonical typed ports",
        ))

    def link_output(upstream: str, out: str, name: str) -> None:
        """Produce one explicit graph output from an operation port."""
        edges.append(_edge(
            _endpoint("operation_output", operation=upstream, port=out),
            _endpoint("graph_output", name=name),
            "checkpoint-present BERT head semantics; activation depends on selected architecture",
        ))

    # Three additive, learned embedding tables, post-add normalization, dropout.
    for kind, input_name, table_name, size in (
        ("word", "token_ids", "bert.embeddings.word_embeddings.weight", vocab),
        ("position", "position_ids", "bert.embeddings.position_embeddings.weight", context),
        ("token_type", "token_type_ids", "bert.embeddings.token_type_embeddings.weight", types),
    ):
        op = f"embedding.{kind}"
        add(op, "embedding.lookup",
            [_port("indices", "I64", S2), _port("table", "F32", [size, hidden])],
            [_port("embeddings", "F32", S3)],
            {"embedding_width": hidden, "vocabulary_size": size, "table_role": kind})
        bind_input(input_name, op, "indices")
        bind_tensor(table_name, op, "table")
    add("embedding.add_word_position", "tensor.add",
        [_port("word", "F32", S3), _port("position", "F32", S3)],
        [_port("sum", "F32", S3)], {"broadcasting": "none"})
    link("embedding.word", "embeddings", "embedding.add_word_position", "word")
    link("embedding.position", "embeddings", "embedding.add_word_position", "position")
    add("embedding.add_token_type", "tensor.add",
        [_port("word_position", "F32", S3), _port("token_type", "F32", S3)],
        [_port("sum", "F32", S3)], {"broadcasting": "none"})
    link("embedding.add_word_position", "sum", "embedding.add_token_type", "word_position")
    link("embedding.token_type", "embeddings", "embedding.add_token_type", "token_type")
    add("embedding.norm", "normalization.layer_norm",
        [_port("value", "F32", S3), _port("scale", "F32", [hidden]), _port("offset", "F32", [hidden])],
        [_port("normalized", "F32", S3)], {"epsilon": epsilon, "normalization_axes": [-1]})
    link("embedding.add_token_type", "sum", "embedding.norm", "value")
    bind_tensor("bert.embeddings.LayerNorm.gamma", "embedding.norm", "scale")
    bind_tensor("bert.embeddings.LayerNorm.beta", "embedding.norm", "offset")
    add("embedding.dropout", "regularization.dropout",
        [_port("value", "F32", S3)], [_port("output", "F32", S3)],
        {"probability": hidden_dropout, "runtime_mode": "training-only; identity-during-evaluation"})
    link("embedding.norm", "normalized", "embedding.dropout", "value")

    # Introduce mask once at the public graph interface; the prepared mask can
    # then fan out to all layers without treating input fan-out as ambiguity.
    add("attention.padding_mask", "attention.padding_mask_prepare",
        [_port("mask", "I64", S2)], [_port("mask", "I64", S2)],
        {"mask_semantics": "one_attend_zero_mask", "mask_application": "additive_before_softmax"})
    bind_input("attention_mask", "attention.padding_mask", "mask")

    previous, previous_port = "embedding.dropout", "output"
    for index in range(layers):
        path = f"bert.encoder.layer.{index}."
        block = f"encoder.{index}"
        qkv_ops: dict[str, str] = {}
        for role in ("query", "key", "value"):
            op = f"{block}.{role}"
            qkv_ops[role] = op
            add(op, "linear.affine",
                [_port("data", "F32", S3), _port("weight", "F32", [hidden, hidden]), _port("bias", "F32", [hidden])],
                [_port("projected", "F32", S3)],
                {"input_width": hidden, "output_width": hidden, "weight_layout": "output_by_input"})
            link(previous, previous_port, op, "data")
            bind_tensor(path + f"attention.self.{role}.weight", op, "weight")
            bind_tensor(path + f"attention.self.{role}.bias", op, "bias")

        attn = f"{block}.bidirectional_attention"
        add(attn, "attention.bidirectional_scaled_dot_product",
            [_port("query", "F32", S3), _port("key", "F32", S3), _port("value", "F32", S3), _port("mask", "I64", S2)],
            [_port("context", "F32", S3)],
            {"head_count": heads, "head_width": head_width, "causal": False,
             "scale_by_sqrt_head_width": True, "mask_semantics": "one_attend_zero_mask",
             "attention_probability_dropout": attn_dropout, "attention_axis": "full_sequence"})
        for role in ("query", "key", "value"):
            link(qkv_ops[role], "projected", attn, role)
        link("attention.padding_mask", "mask", attn, "mask")

        proj = f"{block}.attention_output"
        add(proj, "linear.affine",
            [_port("data", "F32", S3), _port("weight", "F32", [hidden, hidden]), _port("bias", "F32", [hidden])],
            [_port("projected", "F32", S3)],
            {"input_width": hidden, "output_width": hidden, "weight_layout": "output_by_input"})
        link(attn, "context", proj, "data")
        bind_tensor(path + "attention.output.dense.weight", proj, "weight")
        bind_tensor(path + "attention.output.dense.bias", proj, "bias")

        drop = f"{block}.attention_dropout"
        add(drop, "regularization.dropout",
            [_port("value", "F32", S3)], [_port("output", "F32", S3)],
            {"probability": hidden_dropout, "runtime_mode": "training-only; identity-during-evaluation"})
        link(proj, "projected", drop, "value")

        resid = f"{block}.attention_residual"
        add(resid, "tensor.add",
            [_port("residual", "F32", S3), _port("update", "F32", S3)],
            [_port("sum", "F32", S3)], {"broadcasting": "none"})
        link(previous, previous_port, resid, "residual")
        link(drop, "output", resid, "update")

        norm = f"{block}.attention_norm"
        add(norm, "normalization.layer_norm",
            [_port("value", "F32", S3), _port("scale", "F32", [hidden]), _port("offset", "F32", [hidden])],
            [_port("normalized", "F32", S3)], {"epsilon": epsilon, "normalization_axes": [-1]})
        link(resid, "sum", norm, "value")
        bind_tensor(path + "attention.output.LayerNorm.gamma", norm, "scale")
        bind_tensor(path + "attention.output.LayerNorm.beta", norm, "offset")

        expand = f"{block}.mlp_expansion"
        add(expand, "linear.affine",
            [_port("data", "F32", S3), _port("weight", "F32", [inner, hidden]), _port("bias", "F32", [inner])],
            [_port("projected", "F32", M3)],
            {"input_width": hidden, "output_width": inner, "weight_layout": "output_by_input"})
        link(norm, "normalized", expand, "data")
        bind_tensor(path + "intermediate.dense.weight", expand, "weight")
        bind_tensor(path + "intermediate.dense.bias", expand, "bias")

        gelu = f"{block}.mlp_gelu"
        add(gelu, "activation.gelu_erf",
            [_port("value", "F32", M3)], [_port("output", "F32", M3)],
            {"form": "erf", "formula": "0.5*x*(1+erf(x/sqrt(2)))"})
        link(expand, "projected", gelu, "value")

        contract = f"{block}.mlp_contraction"
        add(contract, "linear.affine",
            [_port("data", "F32", M3), _port("weight", "F32", [hidden, inner]), _port("bias", "F32", [hidden])],
            [_port("projected", "F32", S3)],
            {"input_width": inner, "output_width": hidden, "weight_layout": "output_by_input"})
        link(gelu, "output", contract, "data")
        bind_tensor(path + "output.dense.weight", contract, "weight")
        bind_tensor(path + "output.dense.bias", contract, "bias")

        mlp_drop = f"{block}.mlp_dropout"
        add(mlp_drop, "regularization.dropout",
            [_port("value", "F32", S3)], [_port("output", "F32", S3)],
            {"probability": hidden_dropout, "runtime_mode": "training-only; identity-during-evaluation"})
        link(contract, "projected", mlp_drop, "value")

        mlp_resid = f"{block}.mlp_residual"
        add(mlp_resid, "tensor.add",
            [_port("residual", "F32", S3), _port("update", "F32", S3)],
            [_port("sum", "F32", S3)], {"broadcasting": "none"})
        link(norm, "normalized", mlp_resid, "residual")
        link(mlp_drop, "output", mlp_resid, "update")

        mlp_norm = f"{block}.mlp_norm"
        add(mlp_norm, "normalization.layer_norm",
            [_port("value", "F32", S3), _port("scale", "F32", [hidden]), _port("offset", "F32", [hidden])],
            [_port("normalized", "F32", S3)], {"epsilon": epsilon, "normalization_axes": [-1]})
        link(mlp_resid, "sum", mlp_norm, "value")
        bind_tensor(path + "output.LayerNorm.gamma", mlp_norm, "scale")
        bind_tensor(path + "output.LayerNorm.beta", mlp_norm, "offset")

        previous, previous_port = mlp_norm, "normalized"

    # Observed MLM head. Decoder weight is not present separately in this
    # checkpoint: a tied binding to word_embeddings is an explicit hypothesis.
    add("mlm.transform", "linear.affine",
        [_port("data", "F32", S3), _port("weight", "F32", [hidden, hidden]), _port("bias", "F32", [hidden])],
        [_port("projected", "F32", S3)],
        {"weight_layout": "output_by_input", "input_width": hidden, "output_width": hidden})
    link(previous, previous_port, "mlm.transform", "data")
    bind_tensor("cls.predictions.transform.dense.weight", "mlm.transform", "weight")
    bind_tensor("cls.predictions.transform.dense.bias", "mlm.transform", "bias")

    add("mlm.gelu", "activation.gelu_erf",
        [_port("value", "F32", S3)], [_port("output", "F32", S3)],
        {"form": "erf", "formula": "0.5*x*(1+erf(x/sqrt(2)))"})
    link("mlm.transform", "projected", "mlm.gelu", "value")
    add("mlm.norm", "normalization.layer_norm",
        [_port("value", "F32", S3), _port("scale", "F32", [hidden]), _port("offset", "F32", [hidden])],
        [_port("normalized", "F32", S3)], {"epsilon": epsilon, "normalization_axes": [-1]})
    link("mlm.gelu", "output", "mlm.norm", "value")
    bind_tensor("cls.predictions.transform.LayerNorm.gamma", "mlm.norm", "scale")
    bind_tensor("cls.predictions.transform.LayerNorm.beta", "mlm.norm", "offset")
    add("mlm.decoder", "linear.affine",
        [_port("data", "F32", S3), _port("weight", "F32", [vocab, hidden]), _port("bias", "F32", [vocab])],
        [_port("logits", "F32", [B, S, vocab])],
        {"weight_layout": "output_by_input", "input_width": hidden,
         "output_width": vocab, "binding_status": "family-contract-tied"})
    link("mlm.norm", "normalized", "mlm.decoder", "data")
    bind_tensor("bert.embeddings.word_embeddings.weight", "mlm.decoder", "weight",
                "tied MLM decoder inferred from BERT family contract and absence of separate observed decoder weight")
    bind_tensor("cls.predictions.bias", "mlm.decoder", "bias")
    link_output("mlm.decoder", "logits", "masked_language_logits")

    # Checkpoint-present pooler and next-sentence prediction head. The config
    # alone does not certify that an MLM-only host executes these operations.
    add("pooler.first_token", "sequence.select_first_token",
        [_port("sequence", "F32", S3)], [_port("first", "F32", [B, hidden])],
        {"token_index": 0, "role": "CLS"})
    link(previous, previous_port, "pooler.first_token", "sequence")
    add("pooler.projection", "linear.affine",
        [_port("data", "F32", [B, hidden]), _port("weight", "F32", [hidden, hidden]), _port("bias", "F32", [hidden])],
        [_port("projected", "F32", [B, hidden])],
        {"weight_layout": "output_by_input", "input_width": hidden, "output_width": hidden})
    link("pooler.first_token", "first", "pooler.projection", "data")
    bind_tensor("bert.pooler.dense.weight", "pooler.projection", "weight")
    bind_tensor("bert.pooler.dense.bias", "pooler.projection", "bias")
    add("pooler.tanh", "activation.tanh",
        [_port("value", "F32", [B, hidden])], [_port("output", "F32", [B, hidden])], {})
    link("pooler.projection", "projected", "pooler.tanh", "value")
    add("next_sentence.classifier", "linear.affine",
        [_port("data", "F32", [B, hidden]), _port("weight", "F32", [2, hidden]), _port("bias", "F32", [2])],
        [_port("logits", "F32", [B, 2])],
        {"weight_layout": "output_by_input", "input_width": hidden, "output_width": 2})
    link("pooler.tanh", "output", "next_sentence.classifier", "data")
    bind_tensor("cls.seq_relationship.weight", "next_sentence.classifier", "weight")
    bind_tensor("cls.seq_relationship.bias", "next_sentence.classifier", "bias")
    link_output("next_sentence.classifier", "logits", "next_sentence_logits")

    graph_inputs = [
        {"name": name, "dtype": "I64", "shape": S2, "semantic_role": role}
        for name, role in (
            ("token_ids", "word_embedding_indices"),
            ("position_ids", "absolute_position_indices"),
            ("token_type_ids", "segment_type_indices"),
            ("attention_mask", "one_attend_zero_mask"),
        )
    ]
    graph_outputs = [
        {"name": "masked_language_logits", "dtype": "F32", "shape": [B, S, vocab], "semantic_role": "MLM_head_checkpoint_present"},
        {"name": "next_sentence_logits", "dtype": "F32", "shape": [B, 2], "semantic_role": "NSP_head_checkpoint_present"},
    ]
    source_files = [
        {key: item[key] for key in ("path", "role", "sha256", "sha256_scope", "size_bytes")}
        for item in files
    ]
    source_files.sort(key=lambda item: item["path"])
    graph = {
        "schema": GRAPH_SCHEMA,
        "ir_version": "0.1.0",
        "source_observation": {
            "repository": source["repository"],
            "revision": source["revision"],
            "license_id": source.get("license_id"),
            "nsd_schema": nsd["schema"],
            "source_files": source_files,
        },
        "model_family_adapter": {
            "id": BERT_ADAPTER,
            "version": "0.1.0",
            "family": "BertForPreTraining-compatible checkpoint tensor inventory",
            "reference": BERT_REFERENCE,
            "status": "family-interpreted",
        },
        "dimension_symbols": {
            "batch": {"kind": "runtime", "value": None, "minimum": 1},
            "sequence": {"kind": "runtime", "value": None, "minimum": 1, "maximum": context},
            "hidden": {"kind": "fixed", "value": hidden},
            "context": {"kind": "fixed", "value": context},
            "vocabulary": {"kind": "fixed", "value": vocab},
            "token_types": {"kind": "fixed", "value": types},
            "attention_heads": {"kind": "fixed", "value": heads},
            "head_width": {"kind": "fixed", "value": head_width},
            "mlp_width": {"kind": "fixed", "value": inner},
        },
        "inputs": graph_inputs,
        "outputs": graph_outputs,
        "tensors": catalog,
        "operations": operations,
        "edges": edges,
        "completeness": {
            "status": "pending-verification",
            "observed_tensor_count": len(manifest),
            "classified_tensor_count": len(catalog),
            "bound_tensor_count": 0,
            "unclassified_tensors": [],
            "unused_tensors": [],
            "unsupported_components": [],
            "missing_expected_components": [],
        },
        "verification": {"status": "pending", "checks": []},
        "evidence_policy": {
            "tensor_identity_dtype_shape_offsets": "observed-from-NSD",
            "tensor_roles": "interpreted-from-tensor-names-dimensions-and-BERT-family-contract",
            "operator_types_and_semantics": "interpreted-from-BERT-family-contract",
            "directed_connections": "inferred-from-BERT-family-order-and-validated-by-typed-ports",
            "port_dimensions": "derived-from-observed-configuration-and-tensor-shapes",
            "numerical_parameter_values": "not-observed",
            "execution_behavior": "not-tested",
        },
        "assumptions_and_unresolved": [
            "The config declares " + str(architectures) + " but the checkpoint also contains pooler and next-sentence classifier tensors. Both heads are represented as checkpoint-present, not necessarily runtime-active.",
            "Separate query, key and value roles are inferred from tensor names and BERT family semantics.",
            "Bidirectional, padding-masked self attention and its scaling are family-interpreted; the underlying numerical behavior has not been executed.",
            "The MLM decoder weight is inferred to share the observed token-embedding table because no separate decoder tensor is in this checkpoint.",
            "The adapter models BERT's erf GELU, not GPT-2's tanh GELU approximation.",
            "Position IDs, token-type IDs, and attention mask are explicit graph inputs; optional defaults are caller responsibilities.",
            "The model has not been numerically executed, and the graph does not establish functional equivalence with a specific Transformers implementation.",
        ],
    }
    report = verify_typed_graph(graph, nsd)
    graph["completeness"].update(report["completeness"])
    graph["verification"] = report["verification"]
    return graph
