# PRC-001 execution plan

## Question

Create a self-contained realization capsule whose metadata and payload can be independently checked, decoded, and replayed without relying on the process that created it.

## Procedure

1. Reuse the exact RCN-001 workload family and SRE-002 codecs.
2. Compile each workload through minterm, direct-DAG and live-DAG routes.
3. Convert each dense model into the exact E-CPU SparseTransitionReLUNetwork.
4. Verify each of the six codec payloads against the original sparse-model digest.
5. Exhaust the complete Boolean input domain and compare the independent scalar reference, typed source, table, dense model, and decoded sparse model.
6. Create a verification receipt containing source/program/table identity, row count, output/reference digest, semantic contract digest, and case evidence digest.
7. Package source Ground, realization, interface, codec, verification, toolchain pins, and payload digest into the portable capsule.
8. Decode the capsule and independently validate framing, canonical metadata, capsule/header digests, payload length/hash, provenance consistency, sparse model identity, and interface.
9. Replay every input row after restoration and compare case/contract evidence digests with the receipt.
10. Tamper with header metadata and payload bytes; require both to be rejected.
11. Preserve source revisions, capsule sizes, metadata overhead, integrity evidence, and encode/decode timing.

## Acceptance

All 288 capsules must round-trip. All 1,364 input rows must be covered for every workload/compiler/codec combination both before and after capsule packaging. Every restored result must match the scalar reference and dense model under the E-CPU Semantic TranslationContract. Every capsule must reject header and payload corruption.

## Explicit limits

The receipt is an experiment record, not a formal proof object or cryptographic signature. SHA-256 is an integrity primitive, not authentication or authorization. The capsule is not yet a transport, admission, storage, or execution integration in E-CPU.
