# Stateful Runtime Recovery Handoff

**Experiment:** SRH-001  
**Version:** 0.1  
**Status:** implementation and CI validation in progress

SRH-001 composes the Portable Stateful Checkpoint (PSC-001) format with E-CPU's existing quorum-anchored \`TransferableExecutionClaimStore\`. The purpose is to move one pending state transition to a recovery host after the current source becomes unavailable, while preventing a stale source epoch from publishing a competing accepted checkpoint.

This is intentionally a recovery/rehome experiment, not yet a graceful source-coordinated migration protocol.

## 1. Composition

Two different objects move together:

- **State:** the exact PSC-001 checkpoint bytes, including the typed program, current state, logical tick, revision, event chain, resume controls, and one PRC realization capsule per model revision.
- **Authority:** a compact \`PortableExecutionClaimBundle\` whose claim binds the session identity, exact checkpoint digest, computational Ground, typed deterministic-pure resume operator, owner peer/Host, and implementation fingerprint.

The PSC bytes remain the portable runtime state. E-CPU's claim ledger remains the authority for which host may publish the result of the next deterministic continuation. SRH-001 does not create another consensus implementation.

The resume operator is declared as a deterministic pure \`OperatorSpec\`: it maps one exact checkpoint and its embedded controls to the next canonical checkpoint. The local computation may be repeated; the authority ledger decides which matching assignment may publish an accepted result.

## 2. Recovery sequence

1. **Issue.** The current host creates a PSC checkpoint and obtains an E-CPU execution claim assigned to its peer, logical Host, and implementation fingerprint.
2. **Source loss.** A recovery coordinator records evidence of source unavailability and calls the existing claim-store reassignment transition. The claim's assignment epoch advances under the configured fixed-membership recovery quorum.
3. **Receiver admission.** The recovery host checks the portable claim against the live quorum high-water and exact peer, logical Host, implementation fingerprint, session, checkpoint digest, operator contract, and Ground identity.
4. **Restore.** The receiver validates the PSC framing and digest, validates the embedded PRC realization capsules, and reconstructs the stateful runtime by replaying its full event history.
5. **Continue.** The receiver applies the checkpoint's already-bound resume controls, verifies the typed transition against its compiled realization through the E-CPU runtime, and creates the next PSC checkpoint.
6. **Commit.** The recovery host submits the output checkpoint digest and a typed continuation-receipt digest to the claim store. Completion is accepted only for the exact current assignment epoch and producer.
7. **Successor.** After completion, a new claim is issued for the output checkpoint and assigned to the continuing host. The session identity remains stable; each exact checkpoint creates a new semantic next-step claim.

A successor claim is published after the previous step is committed. A crash between those two operations is recoverable by re-issuing the claim for the already committed output checkpoint; claim creation is content-addressed and idempotent for the same semantic work and target.

## 3. Fencing semantics

The source's old portable ticket ceases to be current after quorum reassignment. A stale source may still finish CPU work already in progress, but its old assignment cannot commit an accepted checkpoint. If a recovery host also fails before continuing, the same claim may be reassigned again; each reassignment advances its assignment epoch and invalidates the preceding ticket.

This is **single-winner checkpoint publication**, not physical exactly-once computation. The guarantee is tied to the live fixed-membership E-CPU recovery authority. The global claim-ledger generation is the monotone state high-water; assignment epochs are monotone within one checkpoint's claim. Each successor checkpoint has a new semantic claim identity, linked by the runtime event chain and receipt digests.

Exact completion retries are idempotent. A retry with a conflicting output checkpoint or receipt is rejected. Receiver admission fails closed for stale tickets, mismatched Hosts, mismatched implementations, invalid PSC bytes, or altered portable claim material.

## 4. Experiment and tests

The tests reuse the PSC-001 reset-dominant two-bit counter and its exact baseline/revision PRC capsules. They exercise:

- source assignment followed by recovery reassignment;
- JSON-only serialization and reconstruction of the handoff envelope;
- stale-source rejection after rehome;
- exact receiver and implementation matching;
- restoration and one-step continuation from state \`10\`, tick 3, revision 1 to state \`11\`, tick 4;
- receipt-bound checkpoint completion and successor claim issuance;
- exact reassignment and completion retries;
- a second recovery after the first recovery host fails before resume;
- forged checkpoint bytes, altered claim ownership, invalid Base64, wrong receiver, and conflicting completion rejection.

The CI fixture uses three independent durable authority journals and the existing strict-majority \`RecoveryLineageCoordinator\`. The runtime and authority participants are logical peers in one test environment; this is not yet a test over separate physical machines or an actual network transport.

## 5. Limits and next experiments

SRH-001 currently handles a **deterministic pure next-transition continuation**. It does not authorize payments, device actions, arbitrary handlers, external side effects, or mutation outside the checkpoint result. A partitioned old host can continue local computation; only its result publication is fenced.

The current recovery claim API models reassignment after failure. A planned graceful migration should be a separate protocol with an explicit source-prepared receipt, durable source fence, destination commit, acknowledgement-loss recovery, and a carefully specified no-overlap ownership policy. That protocol must not overload failure evidence as a voluntary release signal.

The present test also does not establish:
- a signed identity for the peer, Host, or implementation;
- authenticated or encrypted checkpoint transport;
- a real E-CPU Transit/ReliableChannel delivery path;
- independent storage of PSC bytes across different hosts;
- atomic transfer of arbitrary process memory or external side effects;
- physical exactly-once execution.

SHA-256 values here provide integrity and content identity, not authentication. The next meaningful integration is to place the checkpoint and portable authority ticket on an actual E-CPU transport route, then exercise interrupted delivery and recovery across separate processes or hosts.
