// Independent, standard-library-only verifier for HFR-002 graph artifacts.
//
// This program consumes an NSD JSON observation and a Neural Computation
// Graph JSON artifact. It does not import, invoke, or reimplement the Python
// graph compiler or GPT-2 adapter. It independently derives the expected
// GPT-2 tensor inventory, operation/port signatures, edge set, and topology
// from the NSD configuration and Safetensors header manifest.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"
	"strings"
)

type object = map[string]any

type check struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Detail string `json:"detail"`
}

type report struct {
	Schema                 string  `json:"schema"`
	Implementation          string  `json:"implementation"`
	Status                  string  `json:"status"`
	PassedCheckCount        int     `json:"passed_check_count"`
	FailedCheckCount        int     `json:"failed_check_count"`
	ObservedTensorCount     int     `json:"observed_tensor_count"`
	OperationCount          int     `json:"operation_count"`
	ExpectedEdgeCount       int     `json:"expected_edge_count"`
	ActualEdgeCount         int     `json:"actual_edge_count"`
	WeightPayloadBytesRead  int     `json:"weight_payload_bytes_read"`
	Checks                  []check `json:"checks"`
}

type verifier struct {
	checks []check
	failed int
}

func (v *verifier) add(id string, ok bool, detail string) {
	status := "passed"
	if !ok {
		status = "failed"
		v.failed++
	}
	v.checks = append(v.checks, check{ID: id, Status: status, Detail: detail})
}

func asObject(value any) object {
	if result, ok := value.(map[string]any); ok {
		return result
	}
	return nil
}

func asArray(value any) []any {
	if result, ok := value.([]any); ok {
		return result
	}
	return nil
}

func asString(value any) string {
	result, _ := value.(string)
	return result
}

func asInt(value any) (int, bool) {
	number, ok := value.(float64)
	if !ok || number != float64(int(number)) {
		return 0, false
	}
	return int(number), true
}

func positiveInt(config object, name string) (int, bool) {
	value, ok := asInt(config[name])
	return value, ok && value > 0
}

func jsonEqual(left, right any) bool {
	a, errA := json.Marshal(left)
	b, errB := json.Marshal(right)
	return errA == nil && errB == nil && string(a) == string(b)
}

func shape(values ...any) []any {
	return values
}

func ints(values ...int) []any {
	result := make([]any, len(values))
	for i, value := range values {
		result[i] = float64(value)
	}
	return result
}

func readJSON(path string) (object, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var result object
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	if result == nil {
		return nil, fmt.Errorf("%s must contain a JSON object", path)
	}
	return result, nil
}

type tensorSpec struct {
	shape []any
	role  string
}

func expectedTensorSpecs(layers, hidden, context, inner, vocab int, tied bool) map[string]tensorSpec {
	result := map[string]tensorSpec{
		"wte.weight": {shape: ints(vocab, hidden), role: "embedding.token_table"},
		"wpe.weight": {shape: ints(context, hidden), role: "embedding.position_table"},
		"ln_f.weight": {shape: ints(hidden), role: "normalization.final.scale"},
		"ln_f.bias":   {shape: ints(hidden), role: "normalization.final.offset"},
	}
	if !tied {
		result["lm_head.weight"] = tensorSpec{
			shape: ints(vocab, hidden), role: "language_model_head.weight",
		}
	}
	layerRoles := map[string]string{
		"attn.bias":             "transformer_block.attention.causal_mask",
		"attn.c_attn.weight":    "transformer_block.attention.fused_qkv.weight",
		"attn.c_attn.bias":      "transformer_block.attention.fused_qkv.bias",
		"attn.c_proj.weight":    "transformer_block.attention.output_projection.weight",
		"attn.c_proj.bias":      "transformer_block.attention.output_projection.bias",
		"ln_1.weight":           "transformer_block.normalization.attention.scale",
		"ln_1.bias":             "transformer_block.normalization.attention.offset",
		"ln_2.weight":           "transformer_block.normalization.mlp.scale",
		"ln_2.bias":             "transformer_block.normalization.mlp.offset",
		"mlp.c_fc.weight":       "transformer_block.mlp.expansion.weight",
		"mlp.c_fc.bias":         "transformer_block.mlp.expansion.bias",
		"mlp.c_proj.weight":     "transformer_block.mlp.contraction.weight",
		"mlp.c_proj.bias":       "transformer_block.mlp.contraction.bias",
	}
	layerShapes := map[string][]any{
		"attn.bias":          ints(1, 1, context, context),
		"attn.c_attn.weight": ints(hidden, 3*hidden),
		"attn.c_attn.bias":   ints(3 * hidden),
		"attn.c_proj.weight": ints(hidden, hidden),
		"attn.c_proj.bias":   ints(hidden),
		"ln_1.weight":        ints(hidden),
		"ln_1.bias":          ints(hidden),
		"ln_2.weight":        ints(hidden),
		"ln_2.bias":          ints(hidden),
		"mlp.c_fc.weight":    ints(hidden, inner),
		"mlp.c_fc.bias":      ints(inner),
		"mlp.c_proj.weight":  ints(inner, hidden),
		"mlp.c_proj.bias":    ints(hidden),
	}
	for layer := 0; layer < layers; layer++ {
		prefix := fmt.Sprintf("h.%d.", layer)
		for suffix, role := range layerRoles {
			result[prefix+suffix] = tensorSpec{shape: layerShapes[suffix], role: role}
		}
	}
	return result
}

type portSpec struct {
	name  string
	dtype string
	shape []any
}

type operationSpec struct {
	id       string
	operator string
	inputs   []portSpec
	outputs  []portSpec
}

func p(name, dtype string, dimensions ...any) portSpec {
	return portSpec{name: name, dtype: dtype, shape: dimensions}
}

func operationSpecs(layers, hidden, context, inner, vocab, heads int, maskTypes map[string]string) []operationSpec {
	bh := shape("batch", "sequence", float64(hidden))
	bqkv := shape("batch", "sequence", float64(3*hidden))
	binner := shape("batch", "sequence", float64(inner))
	token := shape("batch", "sequence")
	ops := []operationSpec{
		{
			id: "embedding.token_lookup", operator: "embedding.lookup",
			inputs: []portSpec{p("indices", "I64", token...), p("table", "F32", float64(vocab), float64(hidden))},
			outputs: []portSpec{p("embeddings", "F32", bh...)},
		},
		{
			id: "embedding.position_lookup", operator: "embedding.lookup",
			inputs: []portSpec{p("indices", "I64", token...), p("table", "F32", float64(context), float64(hidden))},
			outputs: []portSpec{p("embeddings", "F32", bh...)},
		},
		{
			id: "embedding.add", operator: "tensor.add",
			inputs: []portSpec{p("token_embeddings", "F32", bh...), p("position_embeddings", "F32", bh...)},
			outputs: []portSpec{p("summed_embeddings", "F32", bh...)},
		},
		{
			id: "embedding.dropout", operator: "regularization.dropout",
			inputs: []portSpec{p("value", "F32", bh...)},
			outputs: []portSpec{p("output", "F32", bh...)},
		},
	}
	for layer := 0; layer < layers; layer++ {
		block := fmt.Sprintf("block.%d", layer)
		maskType := maskTypes[fmt.Sprintf("h.%d.attn.bias", layer)]
		ops = append(ops,
			operationSpec{
				id: block + ".attention_norm", operator: "normalization.layer_norm",
				inputs: []portSpec{p("value", "F32", bh...), p("scale", "F32", float64(hidden)), p("offset", "F32", float64(hidden))},
				outputs: []portSpec{p("normalized", "F32", bh...)},
			},
			operationSpec{
				id: block + ".qkv_projection", operator: "linear.affine",
				inputs: []portSpec{p("data", "F32", bh...), p("weight", "F32", float64(hidden), float64(3*hidden)), p("bias", "F32", float64(3*hidden))},
				outputs: []portSpec{p("projected", "F32", bqkv...)},
			},
			operationSpec{
				id: block + ".causal_attention", operator: "attention.causal_scaled_dot_product",
				inputs: []portSpec{p("fused_query_key_value", "F32", bqkv...), p("causal_mask", maskType, float64(1), float64(1), float64(context), float64(context))},
				outputs: []portSpec{p("context", "F32", bh...)},
			},
			operationSpec{
				id: block + ".attention_output_projection", operator: "linear.affine",
				inputs: []portSpec{p("data", "F32", bh...), p("weight", "F32", float64(hidden), float64(hidden)), p("bias", "F32", float64(hidden))},
				outputs: []portSpec{p("projected", "F32", bh...)},
			},
			operationSpec{
				id: block + ".attention_output_dropout", operator: "regularization.dropout",
				inputs: []portSpec{p("value", "F32", bh...)},
				outputs: []portSpec{p("output", "F32", bh...)},
			},
			operationSpec{
				id: block + ".attention_residual_add", operator: "tensor.add",
				inputs: []portSpec{p("residual", "F32", bh...), p("update", "F32", bh...)},
				outputs: []portSpec{p("sum", "F32", bh...)},
			},
			operationSpec{
				id: block + ".mlp_norm", operator: "normalization.layer_norm",
				inputs: []portSpec{p("value", "F32", bh...), p("scale", "F32", float64(hidden)), p("offset", "F32", float64(hidden))},
				outputs: []portSpec{p("normalized", "F32", bh...)},
			},
			operationSpec{
				id: block + ".mlp_expansion", operator: "linear.affine",
				inputs: []portSpec{p("data", "F32", bh...), p("weight", "F32", float64(hidden), float64(inner)), p("bias", "F32", float64(inner))},
				outputs: []portSpec{p("projected", "F32", binner...)},
			},
			operationSpec{
				id: block + ".mlp_activation", operator: "activation.gelu_tanh",
				inputs: []portSpec{p("value", "F32", binner...)},
				outputs: []portSpec{p("output", "F32", binner...)},
			},
			operationSpec{
				id: block + ".mlp_contraction", operator: "linear.affine",
				inputs: []portSpec{p("data", "F32", binner...), p("weight", "F32", float64(inner), float64(hidden)), p("bias", "F32", float64(hidden))},
				outputs: []portSpec{p("projected", "F32", bh...)},
			},
			operationSpec{
				id: block + ".mlp_output_dropout", operator: "regularization.dropout",
				inputs: []portSpec{p("value", "F32", bh...)},
				outputs: []portSpec{p("output", "F32", bh...)},
			},
			operationSpec{
				id: block + ".mlp_residual_add", operator: "tensor.add",
				inputs: []portSpec{p("residual", "F32", bh...), p("update", "F32", bh...)},
				outputs: []portSpec{p("sum", "F32", bh...)},
			},
		)
	}
	ops = append(ops,
		operationSpec{
			id: "final.layer_norm", operator: "normalization.layer_norm",
			inputs: []portSpec{p("value", "F32", bh...), p("scale", "F32", float64(hidden)), p("offset", "F32", float64(hidden))},
			outputs: []portSpec{p("normalized", "F32", bh...)},
		},
		operationSpec{
			id: "language_model_head", operator: "linear.affine",
			inputs: []portSpec{p("data", "F32", bh...), p("weight", "F32", float64(vocab), float64(hidden))},
			outputs: []portSpec{p("logits", "F32", "batch", "sequence", float64(vocab))},
		},
	)
	return ops
}

type endpoint struct {
	kind      string
	name      string
	operation string
	port      string
}

func graphInput(name string) endpoint { return endpoint{kind: "graph_input", name: name} }
func graphOutput(name string) endpoint { return endpoint{kind: "graph_output", name: name} }
func tensor(name string) endpoint { return endpoint{kind: "tensor", name: name} }
func opOut(operation, port string) endpoint { return endpoint{kind: "operation_output", operation: operation, port: port} }
func opIn(operation, port string) endpoint { return endpoint{kind: "operation_input", operation: operation, port: port} }

func endpointKey(e endpoint) string {
	return strings.Join([]string{e.kind, e.name, e.operation, e.port}, "|")
}
func edgeKey(source, target endpoint) string {
	return endpointKey(source) + "->" + endpointKey(target)
}

func expectedEdges(layers int, tied bool) map[string]bool {
	result := map[string]bool{}
	add := func(source, target endpoint) { result[edgeKey(source, target)] = true }
	add(graphInput("token_ids"), opIn("embedding.token_lookup", "indices"))
	add(graphInput("position_ids"), opIn("embedding.position_lookup", "indices"))
	add(tensor("wte.weight"), opIn("embedding.token_lookup", "table"))
	add(tensor("wpe.weight"), opIn("embedding.position_lookup", "table"))
	add(opOut("embedding.token_lookup", "embeddings"), opIn("embedding.add", "token_embeddings"))
	add(opOut("embedding.position_lookup", "embeddings"), opIn("embedding.add", "position_embeddings"))
	add(opOut("embedding.add", "summed_embeddings"), opIn("embedding.dropout", "value"))

	previousOperation, previousPort := "embedding.dropout", "output"
	for layer := 0; layer < layers; layer++ {
		prefix := fmt.Sprintf("h.%d.", layer)
		block := fmt.Sprintf("block.%d", layer)
		ln1 := block + ".attention_norm"
		qkv := block + ".qkv_projection"
		attention := block + ".causal_attention"
		projection := block + ".attention_output_projection"
		attentionDropout := block + ".attention_output_dropout"
		attentionAdd := block + ".attention_residual_add"
		ln2 := block + ".mlp_norm"
		expand := block + ".mlp_expansion"
		activation := block + ".mlp_activation"
		contract := block + ".mlp_contraction"
		mlpDropout := block + ".mlp_output_dropout"
		mlpAdd := block + ".mlp_residual_add"

		add(opOut(previousOperation, previousPort), opIn(ln1, "value"))
		add(tensor(prefix+"ln_1.weight"), opIn(ln1, "scale"))
		add(tensor(prefix+"ln_1.bias"), opIn(ln1, "offset"))
		add(opOut(ln1, "normalized"), opIn(qkv, "data"))
		add(tensor(prefix+"attn.c_attn.weight"), opIn(qkv, "weight"))
		add(tensor(prefix+"attn.c_attn.bias"), opIn(qkv, "bias"))
		add(opOut(qkv, "projected"), opIn(attention, "fused_query_key_value"))
		add(tensor(prefix+"attn.bias"), opIn(attention, "causal_mask"))
		add(opOut(attention, "context"), opIn(projection, "data"))
		add(tensor(prefix+"attn.c_proj.weight"), opIn(projection, "weight"))
		add(tensor(prefix+"attn.c_proj.bias"), opIn(projection, "bias"))
		add(opOut(projection, "projected"), opIn(attentionDropout, "value"))
		add(opOut(previousOperation, previousPort), opIn(attentionAdd, "residual"))
		add(opOut(attentionDropout, "output"), opIn(attentionAdd, "update"))
		add(opOut(attentionAdd, "sum"), opIn(ln2, "value"))
		add(tensor(prefix+"ln_2.weight"), opIn(ln2, "scale"))
		add(tensor(prefix+"ln_2.bias"), opIn(ln2, "offset"))
		add(opOut(ln2, "normalized"), opIn(expand, "data"))
		add(tensor(prefix+"mlp.c_fc.weight"), opIn(expand, "weight"))
		add(tensor(prefix+"mlp.c_fc.bias"), opIn(expand, "bias"))
		add(opOut(expand, "projected"), opIn(activation, "value"))
		add(opOut(activation, "output"), opIn(contract, "data"))
		add(tensor(prefix+"mlp.c_proj.weight"), opIn(contract, "weight"))
		add(tensor(prefix+"mlp.c_proj.bias"), opIn(contract, "bias"))
		add(opOut(contract, "projected"), opIn(mlpDropout, "value"))
		add(opOut(attentionAdd, "sum"), opIn(mlpAdd, "residual"))
		add(opOut(mlpDropout, "output"), opIn(mlpAdd, "update"))
		previousOperation, previousPort = mlpAdd, "sum"
	}
	add(opOut(previousOperation, previousPort), opIn("final.layer_norm", "value"))
	add(tensor("ln_f.weight"), opIn("final.layer_norm", "scale"))
	add(tensor("ln_f.bias"), opIn("final.layer_norm", "offset"))
	add(opOut("final.layer_norm", "normalized"), opIn("language_model_head", "data"))
	if tied {
		add(tensor("wte.weight"), opIn("language_model_head", "weight"))
	} else {
		add(tensor("lm_head.weight"), opIn("language_model_head", "weight"))
	}
	add(opOut("language_model_head", "logits"), graphOutput("logits"))
	return result
}

func getEndpoint(value any) endpoint {
	item := asObject(value)
	if item == nil {
		return endpoint{}
	}
	return endpoint{
		kind: asString(item["kind"]), name: asString(item["name"]),
		operation: asString(item["operation"]), port: asString(item["port"]),
	}
}

type signature struct {
	dtype string
	shape []any
}

func verify(nsd, graph object) report {
	v := &verifier{}
	result := report{
		Schema: "in-formation-space.independent-neural-graph-verification.v0.1",
		Implementation: "Go standard library; separate implementation; no Python graph adapter imports",
		WeightPayloadBytesRead: 0,
	}
	source := asObject(nsd["source"])
	observed := asObject(nsd["observed"])
	config := object(nil)
	if observed != nil {
		config = asObject(observed["configuration"])
	}
	if source == nil || observed == nil || config == nil {
		v.add("nsd-structure", false, "NSD source, observed, and configuration objects are required")
		return finish(v, result)
	}
	if asString(nsd["schema"]) != "in-formation-space.neural-structure-description.v0.1" {
		v.add("nsd-schema", false, "unsupported Neural Structure Description schema")
	}
	if asString(graph["schema"]) != "in-formation-space.neural-computation-graph.v0.1" {
		v.add("graph-schema", false, "unsupported Neural Computation Graph schema")
	}
	if asString(source["repository"]) != asString(asObject(graph["source_observation"])["repository"]) ||
		asString(source["revision"]) != asString(asObject(graph["source_observation"])["revision"]) {
		v.add("source-identity", false, "graph source repository/revision differs from the NSD")
	} else {
		v.add("source-identity", true, "graph and NSD refer to the same repository and immutable revision")
	}
	adapter := asObject(graph["model_family_adapter"])
	v.add("family-identity", adapter != nil && asString(adapter["family"]) == "GPT2LMHeadModel",
		"graph declares the supported GPT2LMHeadModel family")

	hidden, okHidden := positiveInt(config, "n_embd")
	layers, okLayers := positiveInt(config, "n_layer")
	heads, okHeads := positiveInt(config, "n_head")
	context, okContext := positiveInt(config, "n_positions")
	vocab, okVocab := positiveInt(config, "vocab_size")
	if !(okHidden && okLayers && okHeads && okContext && okVocab) || hidden%heads != 0 {
		v.add("configuration-dimensions", false, "positive GPT-2 dimensions and integral head width are required")
		return finish(v, result)
	}
	activation := asString(config["activation_function"])
	if activation == "" {
		activation = "gelu_new"
	}
	if activation != "gelu_new" {
		v.add("activation-contract", false, "independent verifier supports the HFR-002 gelu_new contract only")
		return finish(v, result)
	}
	tied := true
	if raw, exists := config["tie_word_embeddings"]; exists {
		value, ok := raw.(bool)
		if !ok {
			v.add("tie-word-embeddings", false, "tie_word_embeddings must be boolean")
			return finish(v, result)
		}
		tied = value
	}
	if config["add_cross_attention"] == true || config["scale_attn_by_inverse_layer_idx"] == true ||
		config["reorder_and_upcast_attn"] == true || config["scale_attn_weights"] == false {
		v.add("attention-family-contract", false, "observed attention flags exceed the supported GPT-2 adapter contract")
		return finish(v, result)
	}
	headWidth := hidden / heads

	manifest := asArray(observed["tensor_manifest"])
	manifestByName := map[string]object{}
	duplicateManifest := false
	for _, raw := range manifest {
		item := asObject(raw)
		if item == nil || asString(item["name"]) == "" {
			duplicateManifest = true
			continue
		}
		name := asString(item["name"])
		if _, exists := manifestByName[name]; exists {
			duplicateManifest = true
		}
		manifestByName[name] = item
	}
	inner := 0
	if first := manifestByName["h.0.mlp.c_fc.weight"]; first != nil {
		if dims := asArray(first["shape"]); len(dims) == 2 {
			inner, _ = asInt(dims[1])
		}
	}
	if inner <= 0 {
		v.add("mlp-width", false, "first block MLP expansion width must be observed as a positive integer")
		return finish(v, result)
	}
	if configured, exists := config["n_inner"]; exists && configured != nil {
		value, ok := asInt(configured)
		if !ok || value != inner {
			v.add("configured-mlp-width", false, "configured n_inner disagrees with observed expansion tensor")
		} else {
			v.add("configured-mlp-width", true, "configured n_inner agrees with observed expansion tensor")
		}
	} else {
		v.add("configured-mlp-width", true, "MLP width is derived from observed projection shape because n_inner is not fixed in config")
	}

	expectedTensors := expectedTensorSpecs(layers, hidden, context, inner, vocab, tied)
	actualNames := make([]string, 0, len(manifestByName))
	for name := range manifestByName {
		actualNames = append(actualNames, name)
	}
	sort.Strings(actualNames)
	expectedNames := make([]string, 0, len(expectedTensors))
	for name := range expectedTensors {
		expectedNames = append(expectedNames, name)
	}
	sort.Strings(expectedNames)
	v.add("nsd-gpt2-tensor-template", !duplicateManifest && jsonEqual(actualNames, expectedNames),
		fmt.Sprintf("expected %d template tensors; observed %d unique tensor names", len(expectedNames), len(actualNames)))

	shardFiles := map[string]object{}
	for _, raw := range asArray(observed["files"]) {
		file := asObject(raw)
		if file != nil && asString(file["role"]) == "safetensors-shard" {
			shardFiles[asString(file["path"])] = file
		}
	}
	tensorShapeFailures := []string{}
	maskTypes := map[string]string{}
	for name, specification := range expectedTensors {
		item := manifestByName[name]
		if item == nil {
			tensorShapeFailures = append(tensorShapeFailures, name+":missing")
			continue
		}
		if !jsonEqual(item["shape"], specification.shape) {
			tensorShapeFailures = append(tensorShapeFailures, name+":shape")
		}
		if asString(item["dtype"]) == "" {
			tensorShapeFailures = append(tensorShapeFailures, name+":dtype")
		}
		shard := asString(item["shard"])
		if shardFiles[shard] == nil {
			tensorShapeFailures = append(tensorShapeFailures, name+":missing-shard")
		}
		if strings.HasSuffix(name, ".attn.bias") {
			maskTypes[name] = asString(item["dtype"])
		}
		if offsets := asArray(item["data_offsets"]); len(offsets) != 2 {
			tensorShapeFailures = append(tensorShapeFailures, name+":offsets")
		} else {
			start, okStart := asInt(offsets[0])
			end, okEnd := asInt(offsets[1])
			dataBytes, okBytes := asInt(item["data_bytes"])
			if !okStart || !okEnd || !okBytes || start < 0 || end < start || end-start != dataBytes {
				tensorShapeFailures = append(tensorShapeFailures, name+":byte-span")
			}
		}
	}
	v.add("nsd-tensor-shapes-and-shards", len(tensorShapeFailures) == 0,
		fmt.Sprintf("independent GPT-2 shape contract and shard membership; mismatches=%v", first(tensorShapeFailures, 8)))

	sourceObservation := asObject(graph["source_observation"])
	sourceFiles := map[string]object{}
	for _, raw := range asArray(sourceObservation["source_files"]) {
		item := asObject(raw)
		if item != nil {
			sourceFiles[asString(item["path"])] = item
		}
	}
	fileFailures := []string{}
	observedFiles := asArray(observed["files"])
	if len(sourceFiles) != len(observedFiles) {
		fileFailures = append(fileFailures, "file-count")
	}
	for _, raw := range observedFiles {
		item := asObject(raw)
		if item == nil {
			fileFailures = append(fileFailures, "malformed-observed-file")
			continue
		}
		path := asString(item["path"])
		graphFile := sourceFiles[path]
		if graphFile == nil || !jsonEqual(graphFile["role"], item["role"]) ||
			!jsonEqual(graphFile["sha256"], item["sha256"]) ||
			!jsonEqual(graphFile["sha256_scope"], item["sha256_scope"]) ||
			!jsonEqual(graphFile["size_bytes"], item["size_bytes"]) {
			fileFailures = append(fileFailures, path)
		}
	}
	v.add("source-file-provenance", len(fileFailures) == 0,
		fmt.Sprintf("NSD file inventory and hashes match graph provenance; mismatches=%v", first(fileFailures, 8)))

	graphTensors := map[string]object{}
	duplicateGraphTensors := false
	for _, raw := range asArray(graph["tensors"]) {
		item := asObject(raw)
		if item == nil {
			duplicateGraphTensors = true
			continue
		}
		name := asString(item["name"])
		if name == "" || graphTensors[name] != nil {
			duplicateGraphTensors = true
		}
		graphTensors[name] = item
	}
	tensorFailures := []string{}
	for name, specification := range expectedTensors {
		observedTensor := manifestByName[name]
		graphTensor := graphTensors[name]
		if observedTensor == nil || graphTensor == nil {
			tensorFailures = append(tensorFailures, name+":missing")
			continue
		}
		sourceRecord := asObject(graphTensor["source"])
		shard := asString(observedTensor["shard"])
		file := shardFiles[shard]
		if asString(graphTensor["dtype"]) != asString(observedTensor["dtype"]) ||
			!jsonEqual(graphTensor["shape"], observedTensor["shape"]) ||
			asString(sourceRecord["file"]) != shard ||
			!jsonEqual(sourceRecord["data_offsets"], observedTensor["data_offsets"]) ||
			!jsonEqual(sourceRecord["data_bytes"], observedTensor["data_bytes"]) ||
			file == nil || asString(sourceRecord["header_sha256"]) != asString(file["sha256"]) ||
			asString(sourceRecord["header_hash_scope"]) != asString(file["sha256_scope"]) {
			tensorFailures = append(tensorFailures, name+":observed-metadata")
		}
		classification := asObject(graphTensor["classification"])
		if asString(asObject(classification)["role"]) != specification.role ||
			asString(classification["status"]) != "family-interpreted" {
			tensorFailures = append(tensorFailures, name+":role")
		}
	}
	if len(graphTensors) != len(expectedTensors) || duplicateGraphTensors {
		tensorFailures = append(tensorFailures, "catalog-bijection")
	}
	v.add("graph-tensor-catalog", len(tensorFailures) == 0,
		fmt.Sprintf("all %d tensors bind to the independently derived name/role/shape and NSD header evidence; mismatches=%v", len(expectedTensors), first(tensorFailures, 8)))

	dimensions := asObject(graph["dimension_symbols"])
	dimensionFailures := []string{}
	requireDimension := func(name, kind string, value any, minimum any, maximum any) {
		item := asObject(dimensions[name])
		if item == nil || asString(item["kind"]) != kind || !jsonEqual(item["value"], value) {
			dimensionFailures = append(dimensionFailures, name)
			return
		}
		if minimum != nil && !jsonEqual(item["minimum"], minimum) {
			dimensionFailures = append(dimensionFailures, name+":minimum")
		}
		if maximum != nil && !jsonEqual(item["maximum"], maximum) {
			dimensionFailures = append(dimensionFailures, name+":maximum")
		}
	}
	requireDimension("batch", "runtime", nil, float64(1), nil)
	requireDimension("sequence", "runtime", nil, float64(1), float64(context))
	requireDimension("hidden", "fixed", float64(hidden), nil, nil)
	requireDimension("vocabulary", "fixed", float64(vocab), nil, nil)
	requireDimension("context", "fixed", float64(context), nil, nil)
	requireDimension("heads", "fixed", float64(heads), nil, nil)
	requireDimension("head_width", "fixed", float64(headWidth), nil, nil)
	requireDimension("mlp_width", "fixed", float64(inner), nil, nil)
	v.add("dimension-symbols", len(dimensionFailures) == 0,
		fmt.Sprintf("runtime and fixed dimensions independently reconstructed from config and tensor shapes; mismatches=%v", dimensionFailures))

	batchSequence := shape("batch", "sequence")
	graphInputFailures := []string{}
	inputs := map[string]object{}
	for _, raw := range asArray(graph["inputs"]) {
		item := asObject(raw)
		if item != nil {
			inputs[asString(item["name"])] = item
		}
	}
	for name, role := range map[string]string{
		"token_ids": "input_token_identifiers",
		"position_ids": "learned_absolute_position_indices",
	} {
		item := inputs[name]
		if item == nil || asString(item["dtype"]) != "I64" || !jsonEqual(item["shape"], batchSequence) || asString(item["semantic_role"]) != role {
			graphInputFailures = append(graphInputFailures, name)
		}
	}
	if len(inputs) != 2 {
		graphInputFailures = append(graphInputFailures, "input-count")
	}
	outputs := map[string]object{}
	for _, raw := range asArray(graph["outputs"]) {
		item := asObject(raw)
		if item != nil {
			outputs[asString(item["name"])] = item
		}
	}
	logitShape := shape("batch", "sequence", float64(vocab))
	logit := outputs["logits"]
	if logit == nil || asString(logit["dtype"]) != "F32" ||
		!jsonEqual(logit["shape"], logitShape) ||
		asString(logit["semantic_role"]) != "next_token_vocabulary_scores" || len(outputs) != 1 {
		graphInputFailures = append(graphInputFailures, "logits-output")
	}
	v.add("graph-interface", len(graphInputFailures) == 0,
		fmt.Sprintf("token IDs, position IDs, and vocabulary logits match the independent interface contract; mismatches=%v", graphInputFailures))

	operationList := operationSpecs(layers, hidden, context, inner, vocab, heads, maskTypes)
	operations := map[string]object{}
	duplicateOperations := false
	for _, raw := range asArray(graph["operations"]) {
		item := asObject(raw)
		if item == nil {
			duplicateOperations = true
			continue
		}
		id := asString(item["id"])
		if id == "" || operations[id] != nil {
			duplicateOperations = true
		}
		operations[id] = item
	}
	operationFailures := []string{}
	for _, specification := range operationList {
		item := operations[specification.id]
		if item == nil || asString(item["operator"]) != specification.operator {
			operationFailures = append(operationFailures, specification.id+":operator")
			continue
		}
		for _, direction := range []struct {
			key string
			expected []portSpec
		}{{"inputs", specification.inputs}, {"outputs", specification.outputs}} {
			ports := map[string]object{}
			invalid := false
			for _, raw := range asArray(item[direction.key]) {
				port := asObject(raw)
				if port == nil || asString(port["name"]) == "" || ports[asString(port["name"])] != nil {
					invalid = true
					continue
				}
				ports[asString(port["name"])] = port
			}
			if invalid || len(ports) != len(direction.expected) {
				operationFailures = append(operationFailures, specification.id+":"+direction.key+":count")
				continue
			}
			for _, expected := range direction.expected {
				actual := ports[expected.name]
				if actual == nil || asString(actual["dtype"]) != expected.dtype || !jsonEqual(actual["shape"], expected.shape) {
					operationFailures = append(operationFailures, specification.id+":"+direction.key+"."+expected.name)
				}
			}
		}
		provenance := asObject(item["provenance"])
		semantics := asObject(provenance["operator_semantics"])
		portShapes := asObject(provenance["port_shapes"])
		if asString(semantics["status"]) != "family-interpreted" ||
			asString(portShapes["status"]) != "dimensionally-derived" {
			operationFailures = append(operationFailures, specification.id+":provenance")
		}
	}
	if len(operations) != len(operationList) || duplicateOperations {
		operationFailures = append(operationFailures, "operation-bijection")
	}
	v.add("operation-and-port-contract", len(operationFailures) == 0,
		fmt.Sprintf("expected %d operations with independently specified port names, dtypes, and shapes; mismatches=%v", len(operationList), first(operationFailures, 10)))

	// Validate key family attributes separately from the local port contract.
	attributeFailures := []string{}
	for _, specification := range operationList {
		item := operations[specification.id]
		if item == nil {
			continue
		}
		attributes := asObject(item["attributes"])
		switch {
		case specification.id == "language_model_head":
			expectedBinding := "family-contract-tied"
			if !tied {
				expectedBinding = "separate-observed-tensor"
			}
			if asString(attributes["binding_status"]) != expectedBinding ||
				asString(attributes["weight_layout"]) != "output_by_input" ||
				asString(attributes["weight_view"]) != "transpose" {
				attributeFailures = append(attributeFailures, specification.id)
			}
		case strings.HasSuffix(specification.id, ".causal_attention"):
			if attributes["causal"] != true || attributes["scale_by_sqrt_head_width"] != true {
				attributeFailures = append(attributeFailures, specification.id)
			}
			count, okCount := asInt(attributes["head_count"])
			width, okWidth := asInt(attributes["head_width"])
			if !okCount || !okWidth || count != heads || width != headWidth {
				attributeFailures = append(attributeFailures, specification.id+":heads")
			}
		case strings.HasSuffix(specification.id, ".mlp_activation"):
			if asString(attributes["family_activation_name"]) != "gelu_new" {
				attributeFailures = append(attributeFailures, specification.id+":activation")
			}
		}
	}
	v.add("family-operation-attributes", len(attributeFailures) == 0,
		fmt.Sprintf("causality, attention partition dimensions, activation identity, and tied-head mode; mismatches=%v", attributeFailures))

	expected := expectedEdges(layers, tied)
	actual := map[string]bool{}
	duplicateEdges := false
	edgeProvenanceFailures := 0
	for _, raw := range asArray(graph["edges"]) {
		item := asObject(raw)
		if item == nil {
			duplicateEdges = true
			continue
		}
		key := edgeKey(getEndpoint(item["source"]), getEndpoint(item["target"]))
		if actual[key] {
			duplicateEdges = true
		}
		actual[key] = true
		provenance := asObject(item["provenance"])
		if provenance == nil || asString(provenance["status"]) != "inferred-connection" || asString(provenance["basis"]) == "" {
			edgeProvenanceFailures++
		}
	}
	missingEdges, unexpectedEdges := []string{}, []string{}
	for key := range expected {
		if !actual[key] {
			missingEdges = append(missingEdges, key)
		}
	}
	for key := range actual {
		if !expected[key] {
			unexpectedEdges = append(unexpectedEdges, key)
		}
	}
	sort.Strings(missingEdges)
	sort.Strings(unexpectedEdges)
	edgeExact := len(missingEdges) == 0 && len(unexpectedEdges) == 0 && !duplicateEdges
	v.add("independently-derived-directed-edges", edgeExact,
		fmt.Sprintf("expected exact edge set of %d; actual=%d; missing=%v; unexpected=%v", len(expected), len(actual), first(missingEdges, 6), first(unexpectedEdges, 6)))
	v.add("edge-provenance", edgeProvenanceFailures == 0,
		fmt.Sprintf("all edges declare inferred-connection provenance; malformed=%d", edgeProvenanceFailures))

	// Resolve every edge independently and enforce type/shape agreement,
	// single input producers, complete output use, and acyclicity.
	signatures := map[string]signature{}
	for name, item := range inputs {
		signatures[endpointKey(graphInput(name))] = signature{asString(item["dtype"]), asArray(item["shape"])}
	}
	for name, item := range graphTensors {
		signatures[endpointKey(tensor(name))] = signature{asString(item["dtype"]), asArray(item["shape"])}
	}
	for id, item := range operations {
		for _, raw := range asArray(item["inputs"]) {
			port := asObject(raw)
			if port != nil {
				name := asString(port["name"])
				signatures[endpointKey(opIn(id, name))] = signature{asString(port["dtype"]), asArray(port["shape"])}
			}
		}
		for _, raw := range asArray(item["outputs"]) {
			port := asObject(raw)
			if port != nil {
				name := asString(port["name"])
				signatures[endpointKey(opOut(id, name))] = signature{asString(port["dtype"]), asArray(port["shape"])}
			}
		}
	}
	for name, item := range outputs {
		signatures[endpointKey(graphOutput(name))] = signature{asString(item["dtype"]), asArray(item["shape"])}
	}
	incoming, outgoing := map[string]int{}, map[string]int{}
	usedTensors := map[string]int{}
	adjacency := map[string]map[string]bool{}
	edgeTypeFailures := 0
	for _, raw := range asArray(graph["edges"]) {
		item := asObject(raw)
		if item == nil {
			edgeTypeFailures++
			continue
		}
		src, dst := getEndpoint(item["source"]), getEndpoint(item["target"])
		sourceSig, sourceOK := signatures[endpointKey(src)]
		targetSig, targetOK := signatures[endpointKey(dst)]
		if !sourceOK || !targetOK || sourceSig.dtype != targetSig.dtype || !jsonEqual(sourceSig.shape, targetSig.shape) {
			edgeTypeFailures++
		}
		incoming[endpointKey(dst)]++
		outgoing[endpointKey(src)]++
		if src.kind == "tensor" {
			usedTensors[src.name]++
		}
		if src.kind == "operation_output" && dst.kind == "operation_input" {
			if adjacency[src.operation] == nil {
				adjacency[src.operation] = map[string]bool{}
			}
			adjacency[src.operation][dst.operation] = true
		}
	}
	v.add("edge-endpoint-types-and-shapes", edgeTypeFailures == 0,
		fmt.Sprintf("every edge resolves and joins equal dtype/shape endpoints; failures=%d", edgeTypeFailures))

	inputPortCount, outputPortCount := 0, 0
	inputPortFailure := false
	for name := range inputs {
		inputPortCount++
		if outgoing[endpointKey(graphInput(name))] != 1 {
			inputPortFailure = true
		}
	}
	for id, item := range operations {
		for _, raw := range asArray(item["inputs"]) {
			port := asObject(raw)
			if port != nil {
				inputPortCount++
				if incoming[endpointKey(opIn(id, asString(port["name"])))] != 1 {
					inputPortFailure = true
				}
			}
		}
		for _, raw := range asArray(item["outputs"]) {
			port := asObject(raw)
			if port != nil {
				outputPortCount++
				if outgoing[endpointKey(opOut(id, asString(port["name"])))] < 1 {
					inputPortFailure = true
				}
			}
		}
	}
	for name := range outputs {
		if incoming[endpointKey(graphOutput(name))] != 1 {
			inputPortFailure = true
		}
	}
	for name := range graphTensors {
		if usedTensors[name] < 1 {
			inputPortFailure = true
		}
	}
	v.add("single-producer-complete-use", !inputPortFailure,
		fmt.Sprintf("%d operation/graph input ports and %d operation output ports are connected; tensors-used=%d/%d", inputPortCount, outputPortCount, len(usedTensors), len(graphTensors)))

	indegree := map[string]int{}
	for id := range operations {
		indegree[id] = 0
	}
	for source, targets := range adjacency {
		if operations[source] == nil {
			continue
		}
		for target := range targets {
			if operations[target] != nil {
				indegree[target]++
			}
		}
	}
	queue := []string{}
	for id, degree := range indegree {
		if degree == 0 {
			queue = append(queue, id)
		}
	}
	sort.Strings(queue)
	visited := 0
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		visited++
		targets := make([]string, 0, len(adjacency[current]))
		for target := range adjacency[current] {
			targets = append(targets, target)
		}
		sort.Strings(targets)
		for _, target := range targets {
			if indegree[target] > 0 {
				indegree[target]--
				if indegree[target] == 0 {
					queue = append(queue, target)
				}
			}
		}
	}
	v.add("acyclic-directed-operation-graph", visited == len(operations),
		fmt.Sprintf("topologically visited %d of %d operations", visited, len(operations)))

	completeness := asObject(graph["completeness"])
	expectedTensorCount := 13*layers + 4
	if !tied {
		expectedTensorCount++
	}
	complete := completeness != nil &&
		asString(completeness["status"]) == "complete-for-supported-family-template" &&
		asIntEqual(completeness["observed_tensor_count"], expectedTensorCount) &&
		asIntEqual(completeness["classified_tensor_count"], expectedTensorCount) &&
		asIntEqual(completeness["bound_tensor_count"], expectedTensorCount) &&
		len(asArray(completeness["unclassified_tensors"])) == 0 &&
		len(asArray(completeness["unused_tensors"])) == 0
	v.add("complete-family-inventory", complete,
		fmt.Sprintf("independent template expects %d tensors; graph completeness counts and unresolved lists agree", expectedTensorCount))

	expectedOperationCount := 12*layers + 6
	expectedEdgeCount := 27*layers + 13
	result.ObservedTensorCount = len(manifestByName)
	result.OperationCount = len(operations)
	result.ExpectedEdgeCount = len(expected)
	result.ActualEdgeCount = len(asArray(graph["edges"]))
	v.add("topology-cardinality", result.OperationCount == expectedOperationCount && len(expected) == expectedEdgeCount && result.ActualEdgeCount == expectedEdgeCount,
		fmt.Sprintf("operations=%d/%d; edges=%d/%d", result.OperationCount, expectedOperationCount, result.ActualEdgeCount, expectedEdgeCount))

	return finish(v, result)
}

func asIntEqual(value any, expected int) bool {
	actual, ok := asInt(value)
	return ok && actual == expected
}

func first(values []string, limit int) []string {
	if len(values) > limit {
		return values[:limit]
	}
	return values
}

func finish(v *verifier, result report) report {
	result.Checks = v.checks
	result.FailedCheckCount = v.failed
	result.PassedCheckCount = len(v.checks) - v.failed
	result.Status = "passed"
	if v.failed > 0 {
		result.Status = "failed"
	}
	return result
}

func main() {
	nsdPath := flag.String("nsd", "", "path to the Neural Structure Description JSON")
	graphPath := flag.String("graph", "", "path to the Neural Computation Graph JSON")
	reportPath := flag.String("report", "", "optional path for the independent verification report JSON")
	flag.Parse()
	if *nsdPath == "" || *graphPath == "" {
		fmt.Fprintln(os.Stderr, "usage: independent-verifier --nsd observation.json --graph topology.json [--report report.json]")
		os.Exit(2)
	}
	nsd, err := readJSON(*nsdPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "read NSD:", err)
		os.Exit(2)
	}
	graph, err := readJSON(*graphPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "read graph:", err)
		os.Exit(2)
	}
	result := verify(nsd, graph)
	encoded, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "encode verification report:", err)
		os.Exit(2)
	}
	encoded = append(encoded, '\n')
	if *reportPath != "" {
		if err := os.WriteFile(*reportPath, encoded, 0o644); err != nil {
			fmt.Fprintln(os.Stderr, "write verification report:", err)
			os.Exit(2)
		}
	}
	fmt.Print(string(encoded))
	if result.Status != "passed" {
		os.Exit(1)
	}
}
