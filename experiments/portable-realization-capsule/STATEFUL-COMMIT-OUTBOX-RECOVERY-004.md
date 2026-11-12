# Stateful Commit-to-Outbox Recovery

**Experiment:** SRH-004  
**Version:** 0.1  
**Status:** implementation and CI validation in progress

SRH-004 closes the process-crash interval identified by SRH-003 for deterministic pure continuations. The durable E-CPU completed claim now serves as the commitment from which a replacement worker can reconstruct a missing response outbox.

The new worker path no longer trusts the received portable ticket's proof to remain the latest global ledger root. It resolves the stable claim ID through the live TransferableExecutionClaimStore, obtains the latest quorum-anchored ticket, and then validates the exact session, checkpoint, operator, Ground, Host, and implementation. This permits unrelated claim publications to advance the global root without making a still-current assignment unusable.

## 1. Recovery rule

A worker receiving an input envelope first resolves the claim's latest committed state:

- **Assigned:** verify the live quorum ticket and exact target, replay the PSC history, compute the exact next checkpoint and typed continuation receipt, and commit both result digests through the existing assignment epoch.
- **Completed:** verify the current quorum proof and exact semantic/owner binding, replay the same deterministic transition from the same PSC bytes, and require both the output checkpoint digest and receipt digest to equal the completed claim's committed values.
- **After validation:** create or recover the content-addressed successor claim, then write the digest-bound durable response outbox before consuming and acknowledging the inbound ReliableChannel request.

The output checkpoint digest binds the runtime state, tick, revision, event journal, and next resume controls. The receipt digest binds the input checkpoint, assignment epoch, target identity, implementation fingerprint, transition state/time result, model/program identity, transition event digest, and output checkpoint digest.

The replacement does not simply trust an output file, nor does it accept any replay that merely reaches the same terminal state. It must reproduce the exact checkpoint bytes' digest and exact continuation receipt digest committed in the completed quorum claim.

## 2. Crash cuts exercised

The worker process test is now parameterized across three hard process exits:

1. **After outbox fsync, before inbound ACK.** The replacement reads the durable outbox and sends the cached response.
2. **After quorum claim completion, before successor creation and outbox write.** The replacement finds the completed claim, deterministically reconstructs the output, creates the missing successor, writes the outbox, and answers the retransmitted request.
3. **After successor claim publication, before outbox write.** The replacement verifies the completed claim, reproduces the exact result, recovers the already-assigned successor idempotently, writes the outbox, and answers the retransmitted request.

In all cases, the sender retains sequence 1 as pending, restores the ReliableChannel snapshot on a new TCP stream, retransmits the exact original envelope, receives the response, and observes the acknowledgement. The remote E-CPU quorum authority processes are restarted from their member-local journals before the replacement worker proceeds.

Additional unit tests show that:
- reusing the completed input envelope reproduces the same result and same successor claim;
- changing the next resume controls yields a different output checkpoint/receipt and is rejected against the completed claim;
- a later, unrelated claim generation does not invalidate the older work ticket when the worker resolves its claim from the live ledger.

## 3. What this improves

The two persistence systems are not made into one atomic database. Instead, the worker's recovery protocol is idempotent across their boundary for this deterministic pure operation:

- Before quorum completion, the input claim remains assigned and the operation can be safely replayed.
- After quorum completion, the claim records the exact result and receipt digests.
- If the successor exists, the claim store's exact content-addressed assigned-claim creation returns that same assignment for the same owner/Host/implementation.
- If the successor does not yet exist, the replacement creates it from the verified checkpoint.
- If the outbox exists, it is used only when all input binding fields and its canonical digest validate.
- ReliableChannel ACK is emitted only after either the existing outbox or its reconstructed replacement has been made durable.

The test establishes a recoverable pure-result protocol across the claim ledger and response outbox. It does not establish a general ACID transaction across the two storage systems.

## 4. Scope and remaining conditions

This remains a logical-host/process experiment over loopback TCP. The recovery worker process and the B/C quorum authority processes are distinct interpreters with durable local journals, but they do not occupy separate physical hosts or fault domains. The process helper is not TLS-authenticated; production deployment should use E-CPU's mutual-TLS authority service. SHA-256 gives integrity/content identity, not authentication.

Completed-result reconstruction requires the same deterministic replay contract, exact input checkpoint, same continuation controls, same assignment epoch, and same target peer/Host/implementation binding. A successor already assigned to a different Host must first undergo its own explicit quorum reassignment; the current worker does not silently steal that next assignment.

No arbitrary external side effects are supported. The operation remains typed, deterministic, and pure. If a future operator invokes an external service, writes a device, performs a payment, or changes state outside the checkpoint, this replay rule alone is not sufficient.

This test does not qualify storage against power loss, corruption outside the tested digest checks, Byzantine authority members, WAN partitions, TLS certificate rotation, or production deployment. It is a controlled crash-cut experiment.

## 5. Next direction

The next useful extension is to separate continuation result construction from authority publication so the source, worker, and authority can exchange an explicit prepared result record before claim completion. That would allow a broader transfer protocol to stage large result payloads, independently validate them, and then publish a small quorum receipt without placing arbitrary execution or side effects in the recovery path.
