# Stateful Prepared-Result Recovery

**Experiment:** SRH-005  
**Version:** 0.1  
**Status:** implementation and CI validation in progress

SRH-005 adds a durable prepared-result stage before E-CPU quorum completion. The worker no longer has to infer the intended next checkpoint from its own post-restart configuration: the proposed output checkpoint and its receipt are first written as a content-bound prepared record. A replacement validates that record against the original input and deterministic replay, then continues the authority transition.

This is a staged protocol, not a cross-store ACID transaction. The prepared record is evidence of what the worker intended to publish; it is not itself an authority decision. The quorum claim still decides which exact assignment may publish the result.

## 1. Prepared-result record

The new ifs.psc.stateful-recovery-worker-prepared.v1 record is keyed by the input claim ID and binds:

- ReliableChannel request sequence;
- input claim ID, PSC checkpoint digest, and complete envelope digest;
- exact assignment epoch, peer, logical Host, and implementation fingerprint;
- canonical Base64 of the complete output PSC checkpoint and its SHA-256;
- the typed continuation receipt core and its SHA-256;
- a canonical prepared-record SHA-256.

The worker writes a temporary file with restrictive local permissions, flushes and fsyncs it, atomically renames it to the prepared-record path, then fsyncs the parent directory. This durable prepare occurs inside the transition function before TransferableExecutionClaimStore.complete is called.

## 2. Receiver recovery

When a worker receives an envelope:

1. It first returns an existing, valid response outbox if one is already durable.
2. Otherwise it looks for the prepared-result record bound to this exact request and assignment.
3. If the record exists, it validates its canonical digest, checkpoint bytes, receipt digest, input identity, and target identity. It decodes the stored output checkpoint and takes the next-step controls from that checkpoint, not from the replacement process's local defaults.
4. It refreshes the live claim from the quorum ledger and requires the exact assignment epoch and target. It replays the input PSC and recomputes the output checkpoint and receipt.
5. The replay must match the prepared checkpoint bytes and receipt exactly before the completion can be committed or accepted.
6. After quorum completion, it creates or recovers the content-addressed successor claim, writes the response outbox, and only then allows ReliableChannel to consume and acknowledge the request.

Thus the prepared checkpoint can survive a worker crash before claim completion. The authority commit can survive a crash before successor creation. The successor can survive a crash before the response outbox. The outbox can survive a crash before ReliableChannel ACK.

## 3. Crash cuts

The worker-process test now exercises four hard-exit points:

- **After prepared-result fsync, before quorum completion.** Exit code 94. The replacement sees an assigned claim, validates the prepared result by replay, and commits it.
- **After quorum completion, before successor creation and outbox.** Exit code 92. The replacement sees a completed claim, validates its committed output and receipt digests against the prepared record and replay, then creates the successor.
- **After successor claim publication, before outbox.** Exit code 93. The replacement validates the completed claim and prepared record, then recovers the exact existing successor idempotently.
- **After response outbox fsync, before request ACK.** Exit code 91. The replacement replays the already durable outbox.

The requester restores its original ReliableChannel sender snapshot and retransmits sequence 1 on a fresh TCP stream. The recovery authority B and C processes are also killed and restarted against their durable member journals before the replacement worker proceeds.

The replacement deliberately starts with different next_resume_controls defaults from the original worker. When a prepared record exists, those defaults are ignored: the output checkpoint carries the control values which are replayed and verified. This tests that recovery is anchored in the prepared artifact, not a coincidentally unchanged worker configuration.

## 4. Authority and integrity

The prepared record is not an authorization token. A local file can be modified by an attacker with filesystem access; its SHA-256 only detects accidental or uncoordinated changes. The receiver's replay check prevents a changed output checkpoint or receipt from being committed as the result of the original deterministic operation. The E-CPU quorum claim records the final result and receipt digests under the exact assignment epoch.

The worker now also rejects an envelope whose assignment epoch differs from the current live claim, even if the same logical Host and implementation later reacquire the work. Ownership epochs therefore remain monotone fencing tokens, not just a descriptive counter.

The design still uses separate durable stores. It creates a recoverable ordering across them for this pure operation; it does not make them one atomic database transaction.

## 5. Evidence boundary

This is process-separated loopback TCP testing. The checkpoint itself travels over E-CPU ReliableChannel to a separate Python worker; the authority participants run as separate child interpreters with their own journals; processes are hard-killed and restarted. All are still in one CI host and one local storage fault domain. The process helper is not TLS-authenticated. This is not a deployment on separate physical machines, a WAN/network partition test, a power-loss durability qualification, or mutual-TLS endpoint authentication.

The operation is constrained to a typed deterministic pure state transition. Exact replay is not a safe substitute for a durable side-effect protocol. Payments, device actions, external writes, arbitrary callbacks, and other non-idempotent effects remain outside this experiment.

## 6. Next direction

A natural next step is to make the prepared result independently portable and verifiable by a second receiver before it is committed. That could separate result construction, result validation, and authority publication into independently inspectable messages, while retaining the checkpoint and semantic Ground identities already carried by PSC-001 and SRH.