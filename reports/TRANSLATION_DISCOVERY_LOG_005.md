# Translation Discovery Log — TDL-005

## Live authenticated observer evidence and the identity of a measurement attempt

**Round:** 2026-11-22. [TDL-001](TRANSLATION_DISCOVERY_LOG.md) · [TDL-002](TRANSLATION_DISCOVERY_LOG_002.md) · [TDL-003](TRANSLATION_DISCOVERY_LOG_003.md) · [TDL-004](TRANSLATION_DISCOVERY_LOG_004.md) · [VL-I TDL-005 implementation contract](https://github.com/Kier73/VL-I/blob/main/docs/AUTHENTICATED_REFINEMENT_TDL005.md).

This document translates existing E-CPU IOS-003 live mTLS measurement semantics, VGI policy-finalized transition evidence and VL-I's exact source-row refinement into a single verifiable construction. **I** means inspected/implemented code; **M** mathematical consequence; **O** observed execution; **H** next falsifiable construction.

## TDL-005/A — A mathematical observation has both a question and an authenticated reporter

**I:** [VL-I's IOS-003 adapter](https://github.com/Kier73/VL-I/blob/main/src/vli/authenticated_refinement.py) constructs an exact row observation specification for each selected feature \(a_i\) from the TDL-003 plan. It explicitly binds source Ground digest, plan digest, old native coordinate, offer ID, row identity, and native E-CPU `ObserverContract` semantics. A provider \(\pi\) receives a distinct contract whose observer ID is the expected pinned peer:

\[
\mathrm{RowGround}_i=H(\mathrm{source},\mathrm{plan},a_i,\mathrm{offer}_i),
\qquad
\mathrm{Contract}_{i,\pi}=H(\mathrm{RowGround}_i,\pi,\mathrm{context}).
\tag{TDL5-A1}
\]

The IOS-003 service accepts only a preinstalled `HostedMeasurement`, and its live `MeasurementPeerClient.resolve` validates the observer contract and the receipt from a CA-verified mutual-TLS session pinned to an expected DNS SAN.

**M:** A source-relative measurement requires two non-equivalent references: the **semantic question** \(a_i x\) and the **authority/identity** of the observer \(\pi\). Two signed or transport-authenticated reports for different questions are not votes on the same evidence event. Two reports on the same question from the same source identity are not two independent votes.

**H:** extend E-CPU's existing peer directory/qualification to search for sources with admitted implementation of the exact row law, then require a source credential, row digest and receiver authority epoch to be bound in one typed capability. Falsify by reusing the same peer under two aliases or reporting a different row with an otherwise valid TLS identity.

## TDL-005/B — Live TLS authentication and portable record checking are separate proof obligations

**I:** E-CPU [IOS-003](https://github.com/Kier73/E-CPU/blob/main/mailcpu/intention_measurement_fabric.py) authenticates a live peer TLS stream (CA verification, peer DNS SAN, required mutual certificate), correlates a request's challenge, scheduler, Ground and observer contract, and uses its durable measurement completion ledger. The adapter accepts readings **only via that real client call**, then creates a VGI `ChannelMessage`, encounter, transport receipt and evidence claim attributed to the connected peer.

**I:** The [independent record verifier](https://github.com/Kier73/VL-I/blob/main/src/vli/authenticated_refinement_verify.py) rederives native row contracts and IOS request digests, strict VGI per-peer evidence and finalizations, and the exact reconstructed coordinate. It intentionally has no API for checking historical TLS authentication from an exported JSON hash.

**M:** the conjunction

\[
\mathrm{LiveSessionAuthenticated}(\pi)
\land\mathrm{IOSContractValid}(i,\pi)
\land\mathrm{VGIQuorumAuthorized}(i)
\land\mathrm{RowDecodeValid}(i)
\tag{TDL5-B1}
\]

establishes the receiver's *live admission process*. It is not equivalent to a portable signature on the output. Re-hashing an unkeyed receipt cannot reproduce a previously authenticated TLS session. The adapter's exported receipt explicitly calls itself **live-session-verified, not portable-source-signed**.

**H:** study a *portable measurement authority certificate*: source/epoch-signed measurement assertion, trust-root and revocation evidence, exact row+challenge, native IOS receipt and VGI event commitment. Acceptance: offline independent verifier rejects altered output, wrong peer/row/epoch, replay after rotation, and unauthorized signature without reopening a network connection.

## TDL-005/C — VGI strict quorum over per-peer source claims

**I:** For each selected row \(i\), a bounded peer set \(P\) (2–8 distinct pinned identities) must supply a bit; VGI policy uses exactly \(P\), quorum \(|P|\), and `strict=True`. No caller-supplied serialized receipt may replace a `MeasurementPeerClient`; all native measurements are performed synchronously in the adapter.

\[
\mathrm{Accept}(i)\iff
\forall\pi\in P:\ b_{i,\pi}\in\{0,1\}
\land(\forall\pi,\rho\in P:\ b_{i,\pi}=b_{i,\rho})
\land\mathrm{VGI.Finalize}(i)=\mathrm{AUTHORIZED}.
\tag{TDL5-C1}
\]

TDL-003 then reconstructs \(z_n=L(z_o,b_{i_1},\dots,b_{i_k})\) only from the finalized VGI Ground.

**M:** this is *identity-diverse network agreement*, not a theorem of physical independence or ground truth. Both local test servers may derive observations from the same hidden state. Future experiments must distinguish correlated software implementations, independently owned physical sensors, network peers, and distinct cryptographic identities.

**H:** qualify independence through separately owned attestations and source provenance before allowing VGI consensus to become stronger physical evidence. Benchmark strict-quorum pricing (multiple peers per row), partial failures, and retry escalation under unchanged intent.

## TDL-005/D — A fresh observation challenge is part of time navigation

**I:** E-CPU's `MeasurementReceiptLedger` retains the result for a `(challenge,feature)` and rejects conflicting requests that reuse the same key. Its read-only operation is deterministic and recoverable. The TDL-005 bridge includes a 256-bit receiver-selected nonce and the observation context, peer ID and row ID when constructing the challenged native request:

\[
\mathrm{Challenge}_{i,\pi,t}
=H(\mathrm{nonce}_t,\mathrm{context}_t,\pi,i).
\tag{TDL5-D1}
\]

**M — newly exposed:** an old observer coordinate \(B_ox\) does not uniquely identify the underlying source state \(x\). Two different source states \(x\ne y\) can have \(B_ox=B_oy\) while \(a_ix\ne a_iy\). Consequently, simply reusing the same old-native-state as an acquisition epoch would allow a durable cache to return a now-stale measurement. **A fresh challenge distinguishes a new observation attempt from an idempotent retransmission.** If the same challenge is deliberately retried, the cached result is appropriate only for that original observation attempt.

**H:** derive durable challenge/lease clocks from E-CPU's existing orbit/assignment epochs and VGI's revision lineage. Verify that a host killed after measurement commit but before VGI finalization can rejoin using the *same* attempt identity, while a genuinely later source observation always obtains a new challenge.

## TDL-005/E — Verification inventory and scope

| Exact integration contract | Source/test |
|---|---|
| Live CA-verified pinned peer identities and client certificates | [TDL-005 mTLS integration test](https://github.com/Kier73/VL-I/blob/main/tests/test_authenticated_refinement.py) |
| Strict VGI quorum for each selected bit | Same integration test; VGI exact evidence ledger |
| Native IOS-002 finite model, request/observer/epoch identities | [Producer](https://github.com/Kier73/VL-I/blob/main/src/vli/authenticated_refinement.py) + [independent verifier](https://github.com/Kier73/VL-I/blob/main/src/vli/authenticated_refinement_verify.py) |
| Conflict, wrong context, out-of-domain bit and report substitution refusals | New adversarial tests |
| Durable reconnection with same challenge and new nonce measurements | New recovery/epoch tests |
| Previous TDL-004 and TDL-003 regressions | [CI workflow](https://github.com/Kier73/VL-I/blob/main/.github/workflows/tdl005-authenticated-refinement.yml) |

**Initial test-status scope:** these are authored integration assertions, pending matching CI verification. The early workflow failed at finite Ground construction because its two state IDs were not lexically ordered; the producer and independent verifier were corrected to use canonical IDs. Do not count that pre-test failure as evidence of successful mTLS behavior.

The test peers have separate certificates and separate native servers but share one loopback environment, operating system and test harness. They are not claimed to be independently administered physical observers.

## Next construction: join the two existing execution paths

TDL-004 forms **host/path-admitted** observation tasks from the receiver's E-CPU SAB-001 inventory and policy; TDL-005 independently authenticates the **live IOS-003 measurement session** and uses VGI strict source quorum.

The next exact integration should bind the TDL-004 typed route/operation identity and epoch to the TDL-005 native authenticated feature request and peer endpoint, rather than choosing an unconstrained peer after routing:

\[
\begin{array}{c}
\mathrm{SourceRow}\ (a_i,\mathrm{source\ Ground})\\
\downarrow\\
\mathrm{SAB\ AdmittedPath}\ (i,\pi,\mathrm{route},\mathrm{authority},\tau)\\
\downarrow\\
\mathrm{IOS\ LiveMTLSRead}\ (i,\pi,\mathrm{challenge})\\
\downarrow\\
\mathrm{VGI\ Finalization}\ (\mathrm{per\ row,\ strict\ peer\ set})\\
\downarrow\\
\mathrm{VL\ new\ coordinate}\ z_n.
\end{array}
\]

The crucial acceptance criterion is: **the peer certified by the live TLS stream must be the exact receiver-admitted endpoint of the selected E-CPU route.** Preserve existing typed route and native observer contracts; do not introduce a competing authority system. Extend tests to two independently controlled processes and process-kill recovery, and benchmark the real costs of the observed network, not only the declared quanta.
