# Distributed Stateful Recovery Handoff

**Experiment:** SRH-002  
**Version:** 0.1  
**Status:** process-separated quorum integration

SRH-002 extends SRH-001 by placing the E-CPU recovery-lineage authority members in independent child interpreters. The owner process keeps its own authority journal and coordinates the other members through E-CPU's existing DistributedRecoveryLineageCoordinator, RecoveryLineagePeerClient, ReliableChannel, and SocketTransport implementation.

## What the experiment changes

SRH-001 exercised three durable authority journals through an in-process RecoveryLineageCoordinator. SRH-002 uses the same checkpoint, assignment, rehome, continuation, and result-publication protocol, but replaces the two remote authority objects with TCP-connected authority processes.

Each remote authority process owns one journal. The owner sends typed prepare, commit, and inspect requests over the established ReliableChannel protocol. The remote participant persists its decision before returning its response. The test then closes the owner streams, hard-kills both remote interpreters, starts fresh interpreters against the same journal paths, and constructs a new distributed coordinator.

The new coordinator must read the same quorum-supported generation and state root from the reopened journals. It then re-loads the completed claim and the successor claim from the persistent claim store and verifies both against the restored live quorum.

## Tested sequence

1. Start authority B and C as separate Python processes, each with its own journal and loopback TCP listener.
2. Start the owner authority A in the test process and construct a DistributedRecoveryLineageCoordinator.
3. Issue a PSC-bound execution claim for the exact checkpoint.
4. Reassign the claim to a recovery worker identity under the distributed strict-majority quorum.
5. Restore the PSC runtime, advance the reset-dominant counter from state 10 / tick 3 to state 11 / tick 4, commit the checkpoint result and receipt, and publish its successor claim.
6. Record the exact quorum high-water, close streams, and hard-kill B and C.
7. Start fresh B and C interpreters using the same journal files and reconstruct the owner authority from its journal.
8. Construct a new distributed coordinator and claim store. Verify the restored high-water, completed claim, and exact successor target binding.

The base counter fixture and its PRC realization capsules are reused from PSC-001. No new model or transition semantics are introduced.

## What is actually demonstrated

This experiment demonstrates a process-separated recovery authority path: remote members are independent Python interpreters, their journals survive hard process termination, and a newly constructed owner can recover the same quorum-backed state after their restart. The quorum messages use E-CPU's existing reliable request/response channels over TCP.

The checkpoint payload and recovery execution are still local to the integration test process. The test does not yet send PSC bytes over that network path or run the recovery computation in a separate worker process. The TCP authority test also uses the existing loopback non-TLS process helper; it is not a deployment of the mutual-TLS authority service.

This is process-level separation, not physical-host or fault-domain separation. The test does not prove power-loss durability, physical host identity, WAN behavior, independent storage-controller failure, authentication of the supplied failure-evidence digest, or exactly-once physical computation.

## Next integration

The next experiment should bind the PSC envelope itself to an E-CPU transport message, receive it in a separate worker process, reconstruct the runtime there, and publish the receipt through the distributed quorum authority. That gives the state payload, execution endpoint, and ownership authority three separately observable paths. The production transport should use the mutual-TLS RecoveryLineageAuthorityService and explicit endpoint identity rather than the local test helper.
