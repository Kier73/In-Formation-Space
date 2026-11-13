# HFR-001 — External neural structure reading

**Status: prototype; verification pending CI.**

HFR-001 investigates whether an external neural model can be treated as an observed source of mathematical structure rather than as a runtime dependency. Its initial artifact is a framework-neutral **Neural Structure Description (NSD) v0.1**.

This is intentionally distinct from the existing weight-space experiments:

- [WSP-001: Cross-representation weight-space](../cross-representation-weight-space/README.md) constructs a small neural realization from a typed finite law and checks it against VGI and MailCPU.
- [WSP-002: Verified weight-space realization](../verified-weight-space-realization/README.md) compares several compilers and navigates equivalent parameterizations.
- **HFR-001 starts at the other end:** it observes an externally published model's declared configuration and tensor layout, then records what has and has not yet been interpreted.

The reader does not infer what a tensor means from its name, claim that tensor statistics encode learned knowledge, or construct a replacement network yet.

## Current slice: static snapshot observation

The current reader accepts a locally materialized snapshot pinned to an immutable 40-character repository commit SHA. It reads:

| Input | Treatment |
| --- | --- |
| `config.json` | Parsed and retained as an observed configuration object |
| `model.safetensors.index.json` | Parsed when present; checked against the actual tensor inventory |
| `*.safetensors` | Reads the 8-byte header length and bounded JSON header only |
| Tensor payload bytes | Not deserialized, interpreted, or hashed |
| Model implementation code | Never imported or executed |
| License identifier | Retained only when explicitly supplied by the caller; not adjudicated |

The parser is standard-library only. It does not need PyTorch, Transformers, or the Safetensors Python package.

### Knowledge-status separation

Every NSD has three deliberately separate regions:

- **Observed:** source repository and pinned revision, parsed configuration, file records, Safetensors tensor names/dtypes/shapes/offsets, and any declared shard map.
- **Inferred:** deterministic summaries calculated from those observations, currently tensor count, shard count, observed dtypes, and top-level tensor-name roots.
- **Generated:** reserved for a future internally produced architecture graph and parameter rules. In v0.1 the graph is explicitly `null` and the rule list is empty.

The NSD schema is [nsd.schema.json](nsd.schema.json). The parser records hash scope explicitly: configuration and index hashes cover their complete files, while a Safetensors hash covers only its 8-byte prefix and header. A header digest is **not** a digest of the weight payload.

## Run

First materialize the model snapshot at the exact revision you intend to study. For example, use a pinned revision with your preferred Hugging Face download workflow; do not use a moving branch name such as `main`.

Then run from the repository root:

```bash
python -m experiments.external_neural_structure_reading.nsd \
  --snapshot /path/to/pinned-snapshot \
  --repository org/model-name \
  --revision 0123456789abcdef0123456789abcdef01234567 \
  --license-id apache-2.0 \
  --output nsd.json
```

Omit `--license-id` when no reliable identifier is available. The example commit SHA is illustrative and must be replaced by the actual immutable revision.

Focused offline tests:

```bash
python -m pip install jsonschema
python -m unittest discover \
  -s experiments/external_neural_structure_reading \
  -p 'test_*.py' -v
```

The tests construct small synthetic Safetensors snapshots; they do not download a model or treat synthetic values as an external model observation.

## Read a public Hub model without materializing its weights

The companion `hub.py` reader resolves a public model at the exact supplied commit SHA, inspects the Hub sibling listing, then requests only the Safetensors header ranges. It supports public repositories and does not currently accept authentication tokens or private/gated models.

```bash
python -m experiments.external_neural_structure_reading.hub \
  --repository openai-community/gpt2 \
  --revision 607a30d783dfa663caf39e06633721c8d4cfcd7e \
  --license-id mit \
  --output gpt2-nsd.json
```

The revision above is an illustrative pinned GPT-2 revision; check the current Hub metadata and source license before using it. The reader requires the Hub's resolved SHA to equal the supplied SHA.

For each Safetensors shard, the remote reader performs two requests:

1. `Range: bytes=0-7` to obtain the header length.
2. `Range: bytes=8-(7 + header_length)` to obtain the header JSON.

Both responses must be HTTP 206 with an exact `Content-Range`; a server that ignores `Range` and returns HTTP 200 is rejected before its response body is read. The parser does not silently fall back to a full model download. Configuration and index JSON are separately bounded by the same size limit as the local reader.

The current remote path does not fetch model cards, tokenizer files, processor configuration, architecture code, or tensor payloads. It does not yet support private/gated models, authentication, alternate storage backends, or model formats other than Safetensors. The local snapshot reader remains useful for offline snapshots and fixtures.

The offline Hub tests inject a deterministic HTTP opener. They verify revision matching, indexed multi-shard reading, exact range intervals, schema validity, and fail-closed behavior when a server ignores or misreports range requests. They do not depend on live network availability.

## Live reference observation

A separate [live-reference workflow](../../../.github/workflows/hfr-001-live-reference.yml) exercises the public Hub/CDN path against one pinned GPT-2 revision:

- Repository: `openai-community/gpt2`
- Revision: `607a30d783dfa663caf39e06633721c8d4cfcd7e`
- Expected configuration: `model_type=gpt2`, architecture `GPT2LMHeadModel`

The workflow writes `results/gpt2-nsd.json` and uploads it as the `hfr-001-gpt2-nsd` artifact. It also reports total Safetensors shard bytes (from validated Content-Range totals) alongside the bytes of Safetensors prefixes and headers actually requested. This is a metadata/header observation, not a model download or functional reconstruction. The exact run and artifact are the evidence; the pinned model's card and license should be rechecked before making any derivative.

## GPT-2 family interpretation: operation graph

The second-stage adapter, `gpt2_adapter.py`, consumes an NSD v0.1 record and checks whether the observed configuration and tensor inventory satisfy the declared `GPT2LMHeadModel` family template. It emits a separate typed operation graph under `gpt2-operation-graph.schema.json`; the original NSD remains unchanged.

For the pinned GPT-2 observation, the adapter checks:

- 12 transformer blocks, each with the expected 13 tensor entries
- 768-wide hidden state, 12 attention heads (64 dimensions per head), and 1,024-position causal mask
- Fused QKV projection shape `[768, 2304]` and output projection shape `[768, 768]`
- MLP projection shapes `[768, 3072]` and `[3072, 768]`
- Token and position embedding tables plus final layer normalization
- Output-language-model head binding according to the declared GPT-2 family contract

The MLP intermediate width is derived from the observed tensor shapes because `config.n_inner` is null in this snapshot. The model's `tie_word_embeddings` and `scale_attn_weights` fields are also absent from the observed config; the adapter records their effective values and provenance from the documented GPT-2 family defaults rather than presenting them as direct source observations.

The resulting graph expands each block into typed nodes for normalization, fused QKV projection, causal multi-head attention, attention projection, residual addition, MLP projections, activation, and the final vocabulary projection. A passed graph means the expected names and dimensions align with the family template. It does not execute the operations or establish numerical/functional equivalence.

The public Transformers documentation describes GPT-2 as causal attention, documents the configuration dimensions and defaults, and identifies `GPT2LMHeadModel` as using a language-model head tied to input embeddings. The adapter keeps those framework-level semantics in the interpretation layer rather than attributing them to tensor headers alone: [GPT-2 documentation](https://huggingface.co/docs/transformers/main/model_doc/gpt2).

## Fail-closed checks

The reader rejects duplicate JSON keys, non-finite JSON constants, oversized JSON/header regions, non-commit revision labels, invalid tensor entries, negative dimensions or offsets, offsets beyond the data section, overlapping tensor ranges, symbolic links, path traversal, duplicate tensor names across shards, and any mismatch between a shard index and observed headers.

It does not validate architecture semantics, tensor element counts against dtype sizes, model-card claims, tokenizer behavior, custom code, or weight payload integrity. These are intentionally not silently inferred.

## Next discriminating stages

1. Add a second architecture-family adapter so the NSD contract can be compared across different model families. Unsupported operators and unknown tensors must remain explicit rather than being coerced into a GPT-2-shaped template.
2. Add an opt-in selected-tensor range reader using header-declared offsets, with strict byte budgets and payload-scoped hashes. The present observer intentionally reads no tensor payload values.
3. Compute weight-space observations—norms, sparsity, rank/singular spectra, and cross-tensor relations—as separately versioned numerical evidence.
4. Generate independent parameters or parameter rules informed by those observations and compare them against architecture-only baselines.
5. Test functional preservation on explicit input domains; structural resemblance and parameter statistics alone are not behavioral equivalence.
6. Explore selective inheritance and cross-family realization only after the preceding evidence exists.

## Repository responsibilities

- **In-Formation-Space:** external source observation, NSD versioning, structural analysis, experiment design, and retained evidence.
- **E-CPU:** a possible later realization and distribution target for typed graphs and generated parameters. Existing finite-domain neural compilers are useful references, not generic transformer loaders.
- **VGI:** an independent bounded semantic interpreter/reference where an adapter can be stated in its supported instruction language. The present VGI core is not claimed to execute arbitrary transformer graphs.

## Evidence boundary

A valid NSD establishes that the supported metadata and header fields were parsed and cross-checked under this implementation. It does not establish that the model is safe, useful, licensed for a particular derivative, functionally understood, or reproducible from its weight payload. The source revision identifies the upstream snapshot; no original runtime dependency is introduced into an NSD consumer.
