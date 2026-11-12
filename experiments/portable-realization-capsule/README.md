# Portable Realization Capsule

**Experiment:** PRC-001 · Bind an exact encoded realization to source identity and replay evidence  
**Status:** verified within the 16 declared complete finite Boolean domains. See the [PRC-001 verification record](results/ci-run-43317088331.md).

PRC-001 advances SRE-002 from encoded model snapshots to portable realization capsules. A capsule contains an exact codec payload and a canonical metadata header binding that payload to its source Ground, dense and sparse model digests, compiler route, interface, codec schema, toolchain revisions, and complete finite-domain verification receipt.

## Question

Can an encoded realization be moved independently of the process that created it while retaining enough identity and evidence for another process to validate, decode, and replay it?

## Capsule contents

Each capsule contains:
- source repository and exact IFS revision;
- source Ground kind, digest, typed program digest and transition-table digest;
- E-CPU repository/revision, compiler route, dense model digest and sparse model digest;
- ordered input/output names, architecture and finite Boolean domain declaration;
- codec name/schema and inner payload digest;
- a verification receipt with complete input-row count, independent reference-output digest, semantic-translation evidence digest and contract digest;
- exact IFS/E-CPU/VGI toolchain pins.

The binary framing starts with the 8-byte magic IFSPRC01, a framing version, a length-prefixed canonical JSON header, and the exact inner codec payload. The header includes its own SHA-256, a capsule identity digest over the canonical metadata, and the payload descriptor includes a SHA-256 and byte length.

## Verification

PRC-001 reuses the unchanged 16-workload RCN-001 corpus and all six SRE-002 codecs. For each workload/compiler/codec combination it:
1. evaluates the independent scalar reference, typed source and transition table over the complete Boolean domain;
2. checks dense and sparse outputs under the E-CPU Semantic TranslationContract;
3. records an evidence receipt;
4. packages the exact codec bytes into a capsule;
5. validates framing, header and payload integrity;
6. decodes the inner payload and checks source/model/interface/codec identity;
7. replays the complete finite domain after capsule restoration and compares the evidence digests;
8. deliberately tampers with header metadata and payload bytes and requires rejection.

The experiment produces 288 capsules: 16 workloads × three compiler routes × six encodings.

## Canonical metadata and independent receivers

Version 1 uses a deliberately restricted canonical JSON profile so another
language can reconstruct the exact header bytes:

- UTF-8 JSON with object keys sorted lexicographically; metadata object keys
  must be ASCII.
- Values may be strings, booleans, null, arrays, and objects.
- Integers must be within the interoperable IEEE-754 safe-integer range
  (−(2^53−1) through 2^53−1). Floating-point values are not permitted.
- Strings must encode as valid UTF-8 Unicode scalar values. The canonical
  representation uses unescaped UTF-8 characters and compact JSON separators.

The restrictions are part of the v1 format, not suggestions for one encoder.
A future format that needs floating-point metadata, non-ASCII object keys, or
another canonicalization rule must introduce an explicit versioned profile.

[verify_capsule.mjs](verify_capsule.mjs) is an independent Node.js receiver
using only Node built-ins. It checks the framing, canonical header bytes,
header/capsule/receipt/payload digests, and the cross-field identity rules
before returning a payload descriptor. The test suite generates a capsule in
Python and verifies it in Node, including Unicode string values and a tampered
payload. This is an interoperability check for the format implementation; it
does not independently replay the model semantics.

## Integrity versus authenticity

SHA-256 detects accidental or deliberate byte changes when the digest is not
recomputed. It does not prove who created a capsule, authorize its execution,
certify that a source repository is trusted, or make an embedded verification
receipt a formal proof. The verification receipt is replayable experiment
evidence, not a cryptographic attestation. A future signed format would need an
explicit trust and key-management model.

## Measurements

The runner records inner payload bytes, total capsule bytes, metadata/header overhead, capsule identity and header digests, receipt digests, replay evidence, tamper rejection, and local capsule encode/decode timing samples.

## Evidence boundary

The capsule format is currently an In-Formation-Space research artifact. It is not yet integrated into E-CPU admission, ReliableChannel, distributed fabric discovery, durable session storage, or remote execution. The capsule packages an existing sparse realization; it does not itself execute it. Verification covers the 16 selected finite Boolean workloads, not arbitrary models or continuous-valued domains.


## First verified capsule result

The [PRC-001 workflow](https://github.com/Kier73/In-Formation-Space/actions/runs/43317088331) created and replayed 288 capsules, covering 1,364 input rows and 49,104 pre/post-package semantic comparisons. All 288 header and payload tampering probes were rejected. The [retained evidence](results/ci-run-43317088331.md) exposes an important cost: metadata averages about 2.5 KB per capsule and exceeds the inner payload for the compact binary formats. This motivates a follow-on study of compressed headers and shared-provenance bundles.


## Final PR-head verification

The final PR-head [workflow run 43317477207](https://github.com/Kier73/In-Formation-Space/actions/runs/43317477207) passed all steps, including 288 capsules, 49,104 pre/post-package semantic comparisons, and 288/288 header plus 288/288 payload tamper rejections. The [final-head evidence record](results/ci-run-43317477207.md) preserves exact source revisions, byte totals, and artifact digests.


## Independent sparse decoding and semantic replay

The Node.js receiver now has a narrowly scoped `rowmask_binary` decoder.
It reconstructs each sparse layer from its little-endian row masks and exact
int8/float64 scalar streams, validates the inner SRE-002 envelope, rebuilds the
E-CPU sparse snapshot identity, and executes the decoded network.

The cross-language test creates a real parity-2 realization with the SRE-002
Python encoder, packages its row-mask binary payload in a PRC capsule, and
passes the capsule plus a separately generated scalar-reference table to Node.
The Node process must cover all four Boolean assignments, reproduce the
reference output for each, and match the declared sparse-model digest. The
reference table is checked against the SHA-256 recorded in the capsule receipt.
A changed reference is rejected.

A second replay applies an exact positive-homogeneity rescaling to the ReLU
network (first hidden layer × 1/2; next layer's incoming weights × 2). The
function and all four reference outputs remain unchanged, while the codec is
forced onto its float64 coefficient path. This checks independent binary64
decoding and cross-language sparse-model digest reconstruction in addition to
the int8 path.

This is a first semantic interoperability result for one codec and one small
finite Ground. It does not yet establish interoperability for the other five
encodings, arbitrary coefficient formats, or an independently implemented
typed-Ground parser/compiler.
