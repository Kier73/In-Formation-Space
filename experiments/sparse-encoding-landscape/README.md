# Sparse Encoding Landscape

**Experiment:** SRE-002 · Exact sparse snapshot encodings  
**Status:** candidate; pinned cross-repository CI is the verification gate.

SRE-002 follows the storage finding from [SRE-001](../sparse-transition-execution/README.md): COO-style JSON pair records reduce scalar parameter count but can increase serialized bytes for dense minterm models. This experiment compares alternative encodings without changing the underlying sparse model or its semantics.

## Question

Can row-oriented and binary encodings preserve exact sparse model identity while avoiding per-coordinate JSON overhead? How do COO, CSR, row masks, adaptive dense/sparse rows and exact binary scalar formats compare against both dense JSON and dense binary baselines?

## Encodings

Each of the 48 dense compiler/model artifacts from the 16 RCN-001 workloads is converted into the same E-CPU SparseTransitionReLUNetwork. The study serializes that one sparse model in six formats:

1. **COO JSON** — the existing E-CPU sparse snapshot with per-row coordinate/value pairs.
2. **CSR JSON** — flat row offsets, input indices, values, bias indices and bias values.
3. **Row-mask JSON** — one integer bitmask per output row followed by its nonzero values.
4. **CSR binary** — packed row pointers, indices and exact coefficient values.
5. **Row-mask binary** — fixed-width row bitmasks followed by packed coefficient values.
6. **Hybrid binary** — each row chooses dense values or a sparse bitmask representation based on the smaller exact representation; biases make the same choice.

A dense binary baseline is also recorded. Coefficients use signed int8 only when every weight or bias in the corresponding tensor family is an exact integer in the range [-128, 127]; otherwise the encoder uses IEEE-754 float64. This is exact representation selection, not quantization.

## Verification

Every encoding has a decoder. Decoding must reconstruct the original sparse model digest and interface. Every input in every complete Boolean domain is then evaluated by the decoded sparse model and compared with the independent scalar reference and dense model through an E-CPU Semantic Translation Contract.

The dense binary baseline is decoded back to its exact dense matrices and biases and executed over the same input domain.

## Measurements

The report records dense JSON and dense binary byte lengths, all six sparse encoding byte lengths, byte reductions against both dense baselines, encoder and decoder timing samples, selected coefficient dtypes, decoded model digests, and per-row translation evidence digests.

Byte sizes are deterministic serialization/payload measurements. They are not resident Python memory or network throughput. Encoding/decoding times are descriptive Python-host observations.

## Evidence boundary

This tests only the selected finite Boolean workloads and exact compiler-generated coefficient sets. It does not yet integrate these formats into E-CPU's runtime, tensor transport, or durable session storage. No lossy quantization or hardware-specific path is used.

## Relationship to SRE-001

SRE-001 showed that a sparse representation can reduce stored parameters and arithmetic, while a pair-list snapshot can still grow in bytes for dense rows. SRE-002 asks which exact layout best preserves that sparsity in a portable artifact.
