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

## HFR-002 — Structural interpretation and typed topology reconstruction

HFR-002 turns the pinned HFR-001 observation into a **framework-independent typed computation graph**. The GPT-2 adapter remains family-specific, but the graph representation does not use GPT-2 tensor names as its operation vocabulary and does not depend on PyTorch, Transformers, or a particular runtime.

The compiler is `neural_graph_ir.py`; its contract is `neural-computation-graph.schema.json`. The live run is `live_reference/run_gpt2_topology.py`, with workflow [HFR-002 typed neural topology](../../../.github/workflows/hfr-002-topology.yml).

### What the graph contains

| Representation | Contents |
| --- | --- |
| Source observation | Repository, immutable revision, source file hashes and hash scopes |
| Dimension symbols | Fixed dimensions plus runtime dimensions such as batch and sequence |
| Graph interface | Typed token-id and position-id inputs; typed vocabulary-logit output |
| Tensor catalog | Every observed tensor's name, dtype, shape, shard, offsets, header digest and interpreted role |
| Operations | Canonical operators such as `embedding.lookup`, `linear.affine`, `normalization.layer_norm`, `attention.causal_scaled_dot_product`, `activation.gelu_tanh`, `regularization.dropout`, and `tensor.add` |
| Ports | Named, typed input and output values with explicit shapes |
| Edges | Directed connections between graph inputs, tensor sources, operation outputs, operation inputs and graph outputs |
| Completeness | Unclassified, unused, unsupported and missing components |
| Verification | Edge/type/shape, operator dimension, inventory and DAG checks |

Every operation input has exactly one producer. Operation outputs may fan out, which is necessary for residual paths. The graph validator checks dtype/shape equality across each edge, local contracts for the supported operator vocabulary, acyclicity, full input/output connectivity, and a one-to-one classification of observed tensor names.

### Evidence is not collapsed

HFR-002 maintains these separate evidence levels:

- **Observed:** source identity, file/header hashes, tensor names, dtypes, shapes and data offsets from the NSD.
- **Interpreted:** tensor roles and operator meaning supplied by the GPT-2 family adapter.
- **Inferred:** the directed connections, port shapes and dimensional compatibility derived from the supported family contract and checked against the observations.
- **Generated:** no alternate parameters or replacement architecture are generated in this stage.

For example, the causal role of `h.i.attn.bias` is inferred from the GPT-2 family contract and its structural position. The numeric contents of that buffer are not read. Similarly, tied use of `wte.weight` for the output vocabulary projection is explicitly labelled as family-contract evidence where there is no separate `lm_head.weight` entry.

### First complete GPT-2 topology

For the pinned observation, the intended live verification is:

- 160/160 tensor entries classified and connected to operation inputs
- 149 operations across the 12 transformer blocks and surrounding embedding/output path
- 337 directed typed edges
- Runtime batch/sequence dimensions, with sequence bounded by the configured 1,024 positions
- Six primitive operator families represented through the canonical vocabulary, including separate dropout and residual operations
- Zero tensor payload bytes read

The graph makes the GPT-2 structure inspectable without being a GPT-2-specific graph format. A future family adapter can map another architecture into the same operator, port, tensor and edge contract. HFR-002 does **not** yet prove that the graph's inferred semantics reproduce numerical forward behavior; that requires a separate interpreter and differential execution experiment.

Run the live zero-payload reconstruction with:

```bash
python -m experiments.external_neural_structure_reading.live_reference.run_gpt2_topology \
  --output experiments/external_neural_structure_reading/results/gpt2-typed-topology.json
```

The workflow uploads the resulting topology as `hfr-002-gpt2-typed-topology`. The complete offline test suite also exercises missing tensors, invalid edges, bad dimensions, cycles, unsupported families, tied and untied output heads, and provenance separation.

## Selected weight geometry: first and last GPT-2 blocks

The next stage, `weight_geometry.py`, performs an explicit, byte-budgeted numerical observation of two matching fused QKV matrices:

- `h.0.attn.c_attn.weight`
- `h.11.attn.c_attn.weight`

Both are observed as F32 matrices of shape `[768, 2304]`. The selected payloads total 14,155,776 bytes. The live workflow sets a 16 MiB total allowlist budget and an 8 MiB per-tensor ceiling.

Before any selected payload request, `fetch_selected_tensor_payloads`:

1. Requires exact tensor names supplied in the allowlist and checks declared shape/dtype against the byte span.
2. Re-resolves the NSD's immutable Hub revision.
3. Re-reads each selected shard's header using strict HTTP byte ranges.
4. Requires the shard size, header digest, and selected tensor header entry to match the original NSD.
5. Requests only the exact data interval for each selected tensor, verifies the response interval and length, and calculates a SHA-256 digest over the complete selected payload.

The analysis runs in memory. It partitions each fused matrix into Q, K, and V columns and records distribution summaries, Frobenius norms, deterministic power-iteration estimates of spectral norms and stable rank, exact/near-zero fractions, and row/column norm summaries. It also compares the first and last block matrices and their Q/K/V partitions using cosine similarity and relative Frobenius distance.

The retained result is `weight-geometry.schema.json` JSON containing numerical summaries, selected-payload hashes, source header hashes, and the exact selected byte intervals. It does **not** contain raw weight arrays. These are descriptive coordinates in the source checkpoint; similarity or low rank does not by itself establish learned meaning, causal importance, or functional equivalence.

The live workflow is [HFR-001 selected weight geometry](../../../.github/workflows/hfr-001-weight-geometry.yml). Its artifact is `hfr-001-gpt2-weight-geometry`.

## First selected-weight observation

The first live selected-weight run completed against the same pinned GPT-2 revision on GitHub-hosted CI: [run 43477077827](https://github.com/Kier73/In-Formation-Space/actions/runs/43477077827). The retained artifact is named `hfr-001-gpt2-weight-geometry`.

Observed result:

| Measurement | First block (0) | Last block (11) |
| --- | ---: | ---: |
| Fused QKV Frobenius norm | 265.537 | 170.899 |
| Approximate spectral norm (16 power iterations) | 44.745 | 14.811 |
| Approximate stable rank | 35.22 | 133.14 |
| Exact-zero fraction | 0 | 0 |

Cosine similarity between first and last stored matrices:

| Parameter slice | Cosine similarity |
| --- | ---: |
| Fused QKV | -0.00159 |
| Query | -0.00241 |
| Key | -0.00138 |
| Value | -0.00255 |

These values are recorded as a small, reproducible observation of two parameter arrays—not as a statement about what either layer computes or represents. In particular, the hidden-state coordinate systems can evolve through the network, so raw cross-layer weight cosine is not a basis-invariant functional comparison. Stable-rank values are approximate because the spectral norm is estimated by deterministic 16-step power iteration.

The selected payload hashes and exact absolute file ranges are retained in the geometry artifact. The two payloads total 14,155,776 bytes; no raw parameter values were written into the artifact.

## Basis-invariant Q/K/V spectral comparison

The raw first-vs-last block cosine result motivates a second comparison. Two matrices can have low coordinatewise cosine even when their singular-value spectra match. The singular values of a matrix are invariant under orthogonal transformations applied independently on the left and right; this makes spectra a useful, though still incomplete, cross-layer structural signature.

`spectral_invariants.py` computes the full singular-value spectrum for each Q, K, and V slice of the same two selected F32 matrices. It uses `numpy.linalg.svd(compute_uv=False)` in float64, then records:

- The singular-value vector and its Frobenius-normalized form
- Singular-value quantiles and top-1/8/32/64/128 energy fractions
- Exact stable rank, entropy effective rank, and participation ratio
- Mean absolute and root-mean-square distance between normalized spectra
- Jensen-Shannon divergence between squared-singular-value energy distributions

A synthetic test applies orthogonal row/column transformations and checks that the spectra remain equal. The new [QKV spectral invariants workflow](../../../.github/workflows/hfr-001-qkv-spectral-invariants.yml) repeats the live, pinned, 14.16 MB selection under the same 16 MiB total budget and retains the derived spectral record only.

This adds a comparison invariant under orthogonal basis changes, not under arbitrary invertible transformations. It does not assert that two projections implement the same function, that their latent spaces are aligned, or that similar spectra identify learned meaning.

## Five-point depth profile

The endpoint spectra were similar after Frobenius normalization, but two blocks cannot tell us whether that relationship persists through depth. The new `layer_spectral_profile.py` experiment samples fused QKV matrices from transformer blocks `0, 3, 6, 9, 11`.

This is an explicit five-tensor allowlist:

| Sampled block | Tensor |
| ---: | --- |
| 0 | `h.0.attn.c_attn.weight` |
| 3 | `h.3.attn.c_attn.weight` |
| 6 | `h.6.attn.c_attn.weight` |
| 9 | `h.9.attn.c_attn.weight` |
| 11 | `h.11.attn.c_attn.weight` |

For the pinned checkpoint, each tensor is F32 `[768, 2304]` (7,077,888 bytes), so the five payloads total 35,389,440 bytes. The live workflow budgets 48 MiB total and 8 MiB per tensor, within the reader's hard limits.

The analyzer computes the Q/K/V singular spectra at each sampled depth, all ten pairwise spectral comparisons per role, and the four adjacent-sample transitions per role. Each transition also records changes in stable rank and entropy effective rank. The output schema retains only derived spectra and source/payload hashes, never raw parameter arrays.

The sample is intentionally sparse. It does not claim the three unsampled blocks follow the same pattern, and its pairwise distances remain structural summaries rather than functional comparisons. The [five-point depth profile workflow](../../../.github/workflows/hfr-001-layer-spectral-profile.yml) retains the live result as `hfr-001-gpt2-layer-spectral-profile`.

### First live depth-profile result

The live pinned run completed at [workflow run 43478448713](https://github.com/Kier73/In-Formation-Space/actions/runs/43478448713). Across the ten sampled layer pairs, mean absolute distance between Frobenius-normalized spectra averaged:

| Projection | Mean pairwise distance | Maximum pairwise distance |
| --- | ---: | ---: |
| Query | 0.00141 | 0.00207 |
| Key | 0.00239 | 0.00390 |
| Value | 0.00224 | 0.00380 |

The squared-energy Jensen–Shannon divergences were also small across the sampled comparisons (maximum: query 0.0089 bits, key 0.0242 bits, value 0.0243 bits).

However, concentration measures were not stationary. Exact stable rank across the five sampled layers varied as follows:

| Block | Query | Key | Value |
| ---: | ---: | ---: | ---: |
| 0 | 66.38 | 19.61 | 31.21 |
| 3 | 47.63 | 42.42 | 83.04 |
| 6 | 66.05 | 65.51 | 78.61 |
| 9 | 58.42 | 55.89 | 157.03 |
| 11 | 40.69 | 42.85 | 130.85 |

This provides a more precise distinction than “the layers are similar”: normalized spectral shapes are close in this sparse sample, while the concentration of singular-value energy and overall scale change by depth and projection role. These measurements do not identify why those changes occur or what function each transformation performs.


## Fail-closed checks

The reader rejects duplicate JSON keys, non-finite JSON constants, oversized JSON/header regions, non-commit revision labels, invalid tensor entries, negative dimensions or offsets, offsets beyond the data section, overlapping tensor ranges, symbolic links, path traversal, duplicate tensor names across shards, and any mismatch between a shard index and observed headers.

It does not validate architecture semantics, tensor element counts against dtype sizes, model-card claims, tokenizer behavior, custom code, or weight payload integrity. These are intentionally not silently inferred.

## Next discriminating stages

1. Add a second architecture-family adapter that targets this same canonical graph IR; verify that the graph vocabulary is not accidentally encoding GPT-2 assumptions.
2. Add an independently implemented small-subgraph interpreter and compare its outputs against a trusted reference under explicit numerical tolerances. The graph schema and operator contracts should exist before this execution work.
3. Prove selected dimensional and topology obligations independently (for example with Lean or another proof kernel), retaining exact source tensor and operation provenance.
4. Explore whether the same graph IR can represent non-neural systems such as signal-processing pipelines, state machines and conventional algorithms without changing its core port/edge semantics.
5. Treat numerical weight geometry and procedural parameterization as separate follow-on evidence. Acquire parameter data only when a named structural question cannot be answered from the config and headers.

## Repository responsibilities

- **In-Formation-Space:** external source observation, NSD versioning, structural analysis, experiment design, and retained evidence.
- **E-CPU:** a possible later realization and distribution target for typed graphs and generated parameters. Existing finite-domain neural compilers are useful references, not generic transformer loaders.
- **VGI:** an independent bounded semantic interpreter/reference where an adapter can be stated in its supported instruction language. The present VGI core is not claimed to execute arbitrary transformer graphs.

## Evidence boundary

A valid NSD establishes that the supported metadata and header fields were parsed and cross-checked under this implementation. It does not establish that the model is safe, useful, licensed for a particular derivative, functionally understood, or reproducible from its weight payload. The source revision identifies the upstream snapshot; no original runtime dependency is introduced into an NSD consumer.
