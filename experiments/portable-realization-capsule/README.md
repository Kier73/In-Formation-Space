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



## Independent sparse-binary decoding and differential stateful replay

The Node.js receiver independently decodes all three exact SRE-002 binary
sparse encodings:

- **Row-mask binary:** per-output-row little-endian input masks and compact
  coefficient streams.
- **CSR binary:** explicit row pointers, input indices, coefficient streams,
  and separate bias indices/values. The decoder checks pointer endpoints and
  monotonicity, strict in-row index ordering, index bounds, scalar widths,
  coefficient counts, and trailing bytes.
- **Adaptive hybrid binary:** one dense/sparse storage decision per output row,
  with a separate dense/sparse decision for each layer's biases.

All three decoders validate the inner canonical header, header/body digests,
layer dimensions, stored-parameter count, source/model/interface identity, and
reconstructed E-CPU sparse-model digest. They share a single independent
execution and replay path after decoding.

The differential integration test uses E-CPU's typed reset-dominant two-bit
counter (`state_1`, `state_0`, `advance`, `reset` → two next-state bits)
and the live compositional compiler. One output-disconnected ReLU feature is
added as a controlled hybrid-codec probe: its dense input row has an all-zero
outgoing column, so it cannot alter the represented transition function. This
ensures the hybrid fixture actually exercises both dense-row and sparse-row
branches.

Python builds three capsules from the same sparse realization, one for each
binary codec. Each includes an encoding-specific payload, receipt, and
translation contract. Node independently decodes and replays all three,
requiring their reconstructed sparse-model SHA-256 digests and stored
parameter counts to match exactly. Their payload digests must be distinct.

For each codec, Node checks all 16 one-step Boolean assignments against a
separately implemented scalar transition oracle. It then replays all four
initial states and every length-four sequence over the four advance/reset
control pairs: 1,024 trajectories and 4,096 transition steps per encoding.
An intentionally altered recurrent output must be rejected.

This is cross-language differential execution over a finite, declared Ground.
It does not establish arbitrary typed-Ground parsing, general compiler
interoperability, continuous-input equivalence, concurrent/distributed
execution, or hardware performance.


## PSC-001: portable stateful checkpoint and cross-environment resume

The companion [Portable Stateful Checkpoint v1](PORTABLE-STATEFUL-CHECKPOINT-V1.md)
format binds a live state/time projection and its complete event lineage to
one PRC realization capsule per model revision. It deliberately avoids
duplicating dense floating-point model snapshots inside the state-history
record: exact executable sparse models travel in the nested realization
capsules.

The checkpoint receiver independently validates every nested capsule,
interprets each typed Boolean transition program, decodes and exhaustively
checks its sparse realization over the complete finite domain, replays every
step and revision event, and checks the terminal state, logical tick, model
revision, and chain head.

The end-to-end test transfers a reset-dominant two-bit counter after a model
revision. The receiver reconstructs state `10` at logical tick 3 / revision 1,
then computes the next transition for the supplied controls. The restored
E-CPU runtime independently executes the same input; both must produce state
`11` at tick 4 and the same next event digest. A forged event whose hashes
and terminal state were recomputed must still fail semantic replay.

This is a portable checkpoint and one-step continuation prototype. It is not
yet a concurrent or distributed host handoff, signed checkpoint protocol,
encrypted transport, or general VM process checkpoint.

## SRH-001: quorum-fenced stateful recovery rehome

The companion [Stateful Runtime Recovery Handoff](STATEFUL-RECOVERY-HANDOFF-001.md)
experiment composes PSC-001 with E-CPU's existing quorum-anchored
`TransferableExecutionClaimStore`. The portable checkpoint carries exact
state, time, model revision, event lineage, and realization capsules; the
claim carries the live owner assignment, checkpoint binding, typed resume
operator, and implementation identity.

After a source-loss reassignment, the receiver must verify the current quorum
high-water and exact target identity before replaying the PSC runtime and
publishing one continuation checkpoint. The claim epoch fences stale result
publication; it does not stop an isolated source CPU from continuing local
pure computation. A successor checkpoint receives a new claim for its next
transition.

The first integration fixture exercises repeated recovery reassignment,
stale-owner rejection, JSON envelope reconstruction, a resumed counter
transition, idempotent completion, and tamper/target-mismatch rejection. It
uses three durable authority journals in one test environment: it is not yet
a multi-machine transport test or a graceful source-coordinated migration.

## SRH-002: process-separated recovery authorities

The companion [Distributed Stateful Recovery Handoff](DISTRIBUTED-STATEFUL-RECOVERY-HANDOFF-002.md) test uses E-CPU's `DistributedRecoveryLineageCoordinator` with two authority members running in separate Python interpreters. Their durable journals survive hard process termination; a newly constructed owner reconnects to fresh processes, recovers the same quorum high-water, and revalidates the completed and successor claims.

The existing PSC-001 counter and PRC capsules are reused. The quorum messages travel over E-CPU ReliableChannel/SocketTransport TCP connections. The PSC payload and continuation still run in the integration-test process, so this is not yet end-to-end state transfer to a separate worker or physical host.

## SRH-003: PSC over ReliableChannel and durable worker response recovery

The [Stateful Worker Transport Recovery](STATEFUL-WORKER-TRANSPORT-RECOVERY-003.md) experiment sends the actual PSC checkpoint envelope over E-CPU ReliableChannel to a distinct Python recovery worker. After it commits the continuation claim and successor and fsyncs a response outbox, the test hard-kills the worker before request ACK. The requester restores its pending sequence on a fresh stream; a replacement worker replays the digest-bound outbox response without recomputing the transition. This proves one carefully selected process-crash cut over loopback TCP, not atomicity across the E-CPU claim journal and outbox: a crash between those commits and the first outbox fsync remains untested.

## SRH-004: recover a completed claim when no outbox exists

The [Commit-to-Outbox Recovery](STATEFUL-COMMIT-OUTBOX-RECOVERY-004.md) extension resolves a request's stable claim ID against the live quorum ledger. If that claim is already completed, a replacement deterministically replays PSC and requires the output checkpoint digest and typed receipt digest to match the completed claim before recovering/creating the successor and writing the outbox. Crash-cut tests cover after claim completion, after successor creation, and after outbox fsync. This recovery applies to deterministic pure operations and the same target identity; it is not a cross-store transaction or a licence to replay arbitrary side effects.

## SRH-005: durable prepared continuation result

The [Prepared-Result Recovery](STATEFUL-PREPARED-RESULT-RECOVERY-005.md) extension writes the complete proposed PSC output and its typed receipt to a digest-bound, fsynced prepared record before completing the quorum claim. A replacement validates the record against the exact input checkpoint, assignment epoch, target, and deterministic replay. The prepared output checkpoint carries the next-step controls, so recovery can continue even when the replacement worker's local defaults differ. Four hard-crash cuts cover prepare, claim completion, successor publication, and outbox acknowledgement. This remains a pure-operation, process-level loopback experiment, not a cross-store ACID transaction or physical-host deployment.

## SRH-006: independent prepared-result verification

The [Independent Prepared-Result Verification](INDEPENDENT-PREPARED-RESULT-VERIFICATION-006.md) layer invokes a separate Node process after the prepared checkpoint has been fsynced and before the claim is completed. It independently verifies the handoff envelope and claim self-identities, replays both PSC checkpoints and every nested PRC realization/program revision, confirms the exact one-step state/time/event-chain transition, and validates the continuation receipt. Its deterministic receipt digest is added to the final child receipt committed by the E-CPU quorum. A tampered prepared checkpoint is tested with its wrapper digest recomputed and must still be refused before claim completion. This is process/language diversity on the same worker host, not yet a remote validation peer or distinct fault domain.

## SRH-007: remote validator peer

The [Remote Validator Peer](REMOTE-VALIDATOR-PEER-007.md) stage moves independent prepared-result verification to a separate service with no E-CPU claim-store or quorum-publication capability. The recovery worker uses mutual TLS, verifies the validator certificate pin and DNS SAN, and pins the worker peer/Host/implementation tuple at both sides. The validator independently checks the prepared PSC transition and returns a receipt bound to validator identity, worker identity, verifier implementation, request and response digests, and its exact validation report. Only after that receipt is persisted does the recovery worker complete the E-CPU claim. The CI topology is process-separated loopback TCP on one host; it is not yet physical-host or separate fault-domain validation, and the receipt is not a standalone offline digital signature.
