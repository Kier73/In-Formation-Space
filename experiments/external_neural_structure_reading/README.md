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

## Fail-closed checks

The reader rejects duplicate JSON keys, non-finite JSON constants, oversized JSON/header regions, non-commit revision labels, invalid tensor entries, negative dimensions or offsets, offsets beyond the data section, overlapping tensor ranges, symbolic links, path traversal, duplicate tensor names across shards, and any mismatch between a shard index and observed headers.

It does not validate architecture semantics, tensor element counts against dtype sizes, model-card claims, tokenizer behavior, custom code, or weight payload integrity. These are intentionally not silently inferred.

## Next discriminating stages

1. Add a read-only Hugging Face resolver with immutable revision resolution and HTTP range reads for Safetensors headers. A server that ignores range requests must fail closed rather than trigger a full weight download.
2. Add architecture-family adapters that translate declared config plus tensor names/shapes into typed operation graphs. Unknown or unsupported operations must remain explicit.
3. Compare architecture-only internal construction against a declared reference contract on a small, deterministic model fixture.
4. Add weight-space observations—norms, sparsity, rank/singular spectra, and cross-tensor relations—as separately versioned evidence. Do not equate statistical resemblance with retained function.
5. Generate independent parameters or parameter rules and compare them with architecture-only baselines using task-specific observations.
6. Only then explore selective inheritance and functional reconstruction.

## Repository responsibilities

- **In-Formation-Space:** external source observation, NSD versioning, structural analysis, experiment design, and retained evidence.
- **E-CPU:** a possible later realization and distribution target for typed graphs and generated parameters. Existing finite-domain neural compilers are useful references, not generic transformer loaders.
- **VGI:** an independent bounded semantic interpreter/reference where an adapter can be stated in its supported instruction language. The present VGI core is not claimed to execute arbitrary transformer graphs.

## Evidence boundary

A valid NSD establishes that the supported metadata and header fields were parsed and cross-checked under this implementation. It does not establish that the model is safe, useful, licensed for a particular derivative, functionally understood, or reproducible from its weight payload. The source revision identifies the upstream snapshot; no original runtime dependency is introduced into an NSD consumer.
