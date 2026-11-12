# Stateful Worker Transport Recovery

**Experiment:** SRH-003  
**Version:** 0.1  
**Status:** implementation and CI validation in progress

SRH-003 moves the PSC-001 checkpoint and SRH-001 authority ticket into a separate recovery-worker process over E-CPU's existing ReliableChannel / SocketTransport path. It then tests one precise interruption point: the worker has committed the continuation claim and successor claim, and has durably written the response outbox, but has not yet consumed or acknowledged the inbound reliable request.

A replacement worker reconnects on a new TCP stream. The requester restores its original sender-side ReliableChannel snapshot and retransmits the exact pending sequence. The replacement checks the durable outbox against the request sequence, input claim, checkpoint digest, and envelope digest, then returns the stored result without rerunning the transition.

## 1. Topology

- **Source/test process:** constructs the PSC checkpoint, obtains the source claim, performs the source-loss reassignment, retains the sender's reliable request frame, then reconnects after the worker is killed.
- **Recovery worker process:** receives a JSON-portable checkpoint envelope through ReliableChannel, validates the claim against the live authority quorum, restores PSC, advances one typed transition, commits the result and successor through the claim store, and writes a digest-bound outbox record.
- **Authority members:** A is the worker-local owner journal; B and C are independent E-CPU authority child processes with their own durable journals, reached over the existing distributed recovery-lineage protocol.

The worker's ReliableChannel request and response use separate protocol channel identities. A new worker process binds a new TCP stream; the requester restores its original sequence/pending state and replays the exact request frame.

## 2. Durable response outbox

The response outbox is keyed by the stable input claim ID and contains:
- the ReliableChannel request sequence;
- the exact input claim ID;
- the exact input PSC checkpoint SHA-256;
- the exact serialized handoff-envelope SHA-256;
- the completed claim, continuation receipt, receipt digest, and successor envelope;
- a canonical outbox digest.

The worker writes a temporary file, flushes and fsyncs it, atomically replaces the final path, then fsyncs the containing directory. Only after this callback returns does ReliableChannel.receive(commit=...) consume the request and emit its ACK.

The negative crash-cut test calls a hard process exit immediately after the durable outbox write. That prevents Python cleanup, inbound request consumption, and ACK publication. A replacement worker then receives the retransmitted frame, validates the durable outbox binding, and emits the recorded response.

## 3. Counter experiment

The test reuses PSC-001's reset-dominant two-bit counter and its baseline plus revised PRC capsules. The source checkpoint represents state '10', logical tick 3, model revision 1. The recovery worker receives the checkpoint and applies the already-bound resume controls. It produces state '11' at tick 4, stores the result and successor claim, and writes the outbox.

After the process is killed, the requester still has sequence 1 pending. It reconnects to a new worker, restores the original ReliableChannel snapshots, retransmits sequence 1, and receives the response from the outbox. The response is bound to the same input envelope and contains the exact next checkpoint and receipt. The requester receives the ACK and the replacement worker exits successfully.

The test then reopens the authority journals and verifies the quorum high-water, completed input claim, result digest, child receipt digest, and current successor claim.

## 4. Evidence boundary

This is a process-level end-to-end checkpoint message path over loopback TCP. The PSC bytes really cross a socket into a distinct interpreter, that interpreter reconstructs and advances the runtime, and the response crosses back. The authority B/C participants are also separate processes and use E-CPU's reliable quorum RPC.

This does **not** establish separate physical hosts, fault domains, WAN behavior, TLS-authenticated endpoint identity, power-loss durability, or protection against malicious local filesystem access. The authority processes in this test use the existing loopback process helper; production use should deploy the mutual-TLS RecoveryLineageAuthorityService and explicit endpoint identity. SHA-256 provides integrity/content identity, not authentication.

The test covers one deterministic, pure transition. It does not authorize or make safe arbitrary external side effects, device actions, payments, or non-idempotent handlers. The execution can be repeated locally; the authority ticket gates accepted result publication.

### Important remaining crash window

The worker currently performs the E-CPU claim completion and successor-claim creation before writing its response outbox. The deliberate SRH-003 crash occurs **after** the outbox is durable and **before** request ACK. It does not yet cover a crash in the interval between the quorum claim commit and the first outbox fsync.

That gap matters: if the process dies after quorum completion but before an outbox exists, a replacement must reconstruct the exact prior result from durable claim state or resume through a dedicated idempotent completion protocol. A later protocol revision should make this recovery explicit rather than treating the outbox and quorum commit as one atomic transaction. The present test does not claim atomicity across those two storage systems.

## 5. Next experiment

The next step is to close the claim-commit/outbox gap. One candidate is a durable continuation intent prepared under the current assignment, followed by a content-addressed result record that can be reconstructed from a completed claim and checkpoint identity. Another is to place the continuation result and claim completion under one transactional storage boundary. Either approach must be crash-cut tested before stronger recovery guarantees are stated.
