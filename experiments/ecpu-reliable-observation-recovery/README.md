# E-CPU reliable observation loss and recovery matrix

**Status:** controlled pilot; live execution is part of CI.  
**Runtime:** E-CPU commit 800f94f83ffd6f527ed093c8d1c1e93e153c34f6.  
**Purpose:** separate source-count and quorum-width effects, then exercise first-frame loss and first-ACK loss through the actual evidence-gated observation path.

## Why this follows the cost–information matrix

The preceding matrix measured the authorized path under matching, loss-free sender inputs. Its source-count and quorum settings were coupled as (2,2), (4,2), and (4,4), so it could not estimate those dimensions independently. It also deferred loss and partial acknowledgement to another experiment.

This matrix independently crosses source count {4, 8} with quorum width {1, 2, 4}. Every quorum level is valid at both source counts. It also crosses two independent fault flags: drop the first data frame at one source, and drop that source's first ACK. The full design has 24 conditions and three repetitions per condition (72 attempts).

## Actual E-CPU path

The runner uses E-CPU's own ReliableChannel, FaultInjectingTransport, DurableMailboxTransport, ResolverObservation, GatedObservationCoordinator, and MailCPU VM.

Each source has its own fault-injection wrapper, all backed by the same durable mailbox log. The first source is the only one subjected to loss. The two drop flags remain orthogonal: when data loss is also enabled, its retry changes the first ACK's local send index from 2 to 3. The fault schedule explicitly accounts for this.

## Recovery protocol under test

**Data-frame loss:** the first intake is expected to admit every source except the selected one. The sender advances one reliability tick and retransmits the same sequence. A second intake must admit exactly the missing source. Only after every configured source has a retained evidence link does the coordinator finalize the event, regardless of whether the configured quorum is smaller.

**ACK loss:** the receiver commits the authorized event, applies the representative once, consumes the source frames, and emits ACKs. The selected ACK is dropped. Initial sender ACK processing must therefore leave exactly sequence 1 pending at that source. The sender retries the original data frame. Because the receiver has already consumed and applied that sequence, its reliable channel treats the replay as a stale duplicate: the coordinator's duplicate-cleanup path consumes it and emits another ACK without creating a new evidence link or applying the observation again. A final ACK pass must clear the pending sequence.

The combined data-plus-ACK condition tests both recoveries in one attempt. For that case the injected send indices at the target source are 1 (lost data) and 3 (lost ACK after the data retry).

## Verification and retained artifacts

Every attempt must establish all of the following:

1. the exact configured source set eventually appears in the event's retained evidence links;
2. quorum finalization returns AUTHORIZED;
3. VM application count is exactly one and the resolver register reads back the expected hit;
4. data loss, when injected, requires exactly one retry and admits exactly one previously missing link;
5. ACK loss, when injected, leaves one pending sender sequence, then performs one duplicate cleanup and one ACK retry;
6. every sender has an empty pending set at completion;
7. the receiver checkpoint digest is independently reconstructed;
8. the durable mailbox log's hash-chain replay reproduces the in-memory durable state.

The runner records synchronous operation spans around sends, retry ticks, intake, finalization, commit, each checkpoint write, and ACK processing. Per-condition profiles are rebuilt independently from those raw spans; they are descriptive only and never update an attention policy.

CI uploads run-manifest.json, attempt-results.json, operation-spans.json, and operation-cost-profiles.json as ecpu-reliable-observation-recovery.

## Interpretation boundaries

- The experiment uses deterministic local loss injection, not packet timing or a real network.
- The transport is a single local durable mailbox log; the run does not claim a multi-process or multi-host durability guarantee.
- Loss is targeted at one configured source channel. It does not estimate arbitrary burst loss or independent random loss rates.
- All sources provide matching typed observations. Conflicting evidence, receiver refusal, and missing quorum remain separate semantics.
- All observations are collected before finalization. A low quorum does not cause the coordinator to stop waiting for sources; it changes the declared authority threshold only.
- Three repetitions provide a first descriptive profile, not a confidence interval or stable tail estimate.
- The cost and information layers remain separate. This experiment does not derive information from time or calculate an information-per-cost ratio.

## Reproduce

    export ECPU_ROOT=external/E-CPU
    export PYTHONPATH=external/E-CPU
    python experiments/ecpu-reliable-observation-recovery/run_recovery_matrix.py --output-dir results
    python -m unittest discover -s experiments/ecpu-reliable-observation-recovery -p 'test_*.py' -v

The runner rejects any E-CPU checkout whose Git revision differs from the pinned commit. The initial live numbers and exact artifact digests should be added here only after the CI artifact has been inspected and independently summarized.
