# SRE-002 execution plan

## Question

Compare exact sparse model encodings across every SRE-001 workload/compiler pair. Determine whether CSR, bitmask, and adaptive hybrid layouts reduce serialization size relative to the current COO JSON snapshot and to a dense baseline.

## Procedure

1. Reuse the exact RCN-001 workload builder and independent scalar references.
2. Compile each workload with minterm, direct-DAG, and live-DAG compilers.
3. Convert each dense model to the exact E-CPU SparseTransitionReLUNetwork.
4. Encode the same model as COO JSON, CSR JSON, row-mask JSON, CSR binary, row-mask binary, and adaptive hybrid binary.
5. Also encode the dense source as canonical JSON and exact dense binary.
6. Decode all payload formats and verify the reconstructed sparse identity or dense matrices are identical to their source; tamper with encoded source metadata and require each decoder to reject it.
7. Exhaust every Boolean input row for every decoded sparse representation.
8. Compare dense and decoded sparse outputs with independent references under a semantic TranslationContract.
9. Record byte counts, exact coefficient dtype, encode/decode timings, source revisions, and aggregate digests.

## Measurement semantics

- JSON byte counts use sorted compact UTF-8 canonical serialization.
- Binary envelopes use a compact JSON metadata header plus an exact binary body, with a SHA-256 body digest.
- Int8 is used only for exact integer coefficients in [-128, 127]; otherwise float64 preserves coefficients exactly.
- Encoding and decoding timings exclude dense model compilation and sparse model construction.

## Acceptance

Every encoding must round-trip to the same source identity and exact sparse parameters. All formats must reject deliberate payload/source-metadata tampering (JSON payload digest or binary header/body digests). Every decoded sparse realization must match the independent scalar reference and dense model over the complete declared Boolean domain. The dense binary baseline must reconstruct identical matrices and biases and produce matching outputs.

## Limitations

This is a finite benchmark of selected compiler artifacts. JSON and binary byte counts are serialization properties; neither establishes resident memory or transport throughput. The binary encodings are prototypes and are not integrated into E-CPU runtime or communication paths.
