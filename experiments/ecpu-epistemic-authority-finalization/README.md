# E-CPU epistemic authority, dissent, and finalization matrix

**Status:** controlled state-transition experiment; live pinned-runtime execution is part of CI.  
**Runtime:** E-CPU commit 800f94f83ffd6f527ed093c8d1c1e93e153c34f6.  
**Question:** What does the observation system do when evidence is incomplete, when observed sources disagree, and when new evidence arrives after the event has been explicitly finalized?

## Core distinction

This experiment treats four states as different objects:

- **Evidence received:** a typed observation has crossed a reliable channel and has an evidence link.
- **Quorum reached:** one equivalence class of observations has at least the configured number of matching sources.
- **Authority finalized:** the coordinator has closed the event as AUTHORIZED, CONFLICT, or REFUSED.
- **VM realization:** the authorized representative is applied and its admitted source frames are consumed.

A count of received observations is not a confidence score. A quorum is not automatically an agreement. An authorized representative does not erase the fact that dissent was present.

## Matrix

The experiment crosses two policy modes with five deterministic evidence shapes, three repetitions each: ten conditions and 30 attempts.

| Scenario | Evidence shape |
| --- | --- |
| partial_unanimous | Two sources agree; two are absent |
| full_unanimous | All four sources agree |
| majority_dissent | Three agree; one disagrees |
| tied_split | Two agree on one value; two agree on another |
| subquorum_partial | One source is present; three are absent |

All conditions use four configured sources and quorum two. The two policy modes are the E-CPU strict=true and strict=false settings. Every observation is a typed ResolverObservation with one synthetic hit or miss fixture value. These values are not external DNS truth.

## Pinned E-CPU behavior under test

The experiment executes the actual ReliableChannel, DurableMailboxTransport, GatedObservationCoordinator, ObservationConsensus, checkpoint restoration, and VM commit path.

In the pinned implementation:

- strict=true requires the complete configured source set and treats any dissent as CONFLICT.
- strict=false may authorize when one winning equivalence class reaches quorum, even while other sources are missing or dissenting.
- finalize_event() maps a quorum state to AUTHORIZED, a conflict to CONFLICT, and a pending state to REFUSED.
- Consensus rejects a new, previously unseen source observation after finalization. It also rejects a changed observation for an already-known source.
- Authorized commits consume all admitted evidence links, including links from dissenting sources, while applying only the selected representative.

The matrix makes these implementation behaviors observable and retains the underlying evidence partition in each attempt receipt.

## Particularly important edge case: tied quorum

With quorum two, the tied_split case has two groups of size two. In strict=false, the current consensus implementation can still report QUORUM and authorize one group via a deterministic canonical-payload ordering. That makes the result reproducible, but the ordering is not evidence that the selected group is more accurate. The experiment records the tie flag, both groups, selected representative, dissenting group, and actual VM register value.

This is a behavior to evaluate, not a recommendation to enable permissive authority in a real system. A future policy may require a unique plurality, a margin over the next group, or explicit human/authority adjudication. Those alternatives must be evaluated separately rather than smuggled into this experiment.

## Late evidence and checkpoint continuation

For each attempt, the coordinator writes a gated checkpoint, the mailbox journal is copied and independently replayed, and load_gated_checkpoint() reconstructs the finalized coordinator. The restored snapshot must match the live snapshot before late evidence is introduced.

The late-evidence probe then submits either:
- a previously absent source for partial-evidence scenarios; or
- a changed value for a source already represented in a full-evidence scenario.

The system must not silently add the late observation to the finalized event. In partial-evidence scenarios, the new source is sent through the real reliable transport after finalization; coordinator intake reaches the new source and consensus rejects it. The late frame remains queued because it was not admitted or acknowledged. In full-evidence scenarios, the probe submits a changed observation for an already represented source directly to consensus; this is also rejected. All 30 attempts record the unchanged finalized status and an unchanged coordinator snapshot after the late proposal.

The distinction retained in each receipt is between a transport frame being present, transport intake reaching it, and consensus refusing to add it to an already finalized event. A rejected late frame is not silently discarded, and the established authority is not silently revised.

## First live CI result

The first full pinned-runtime matrix completed successfully in [GitHub Actions run 310](https://github.com/Kier73/In-Formation-Space/actions/runs/43135518309). The digest-checked [run summary](results/ci-run-310-summary.json) records the artifact digest, attempt/evidence/trace digests, matrix counts, and exact outcomes.

**Observed coverage:** 10 policy/scenario conditions × 3 repetitions = 30 attempts; 90 typed evidence records; 30/30 checkpoint restorations; 30/30 durable mailbox verifications; and 30/30 rejected post-finalization consensus proposals.

| Evidence shape | strict=true | strict=false |
| --- | --- | --- |
| Two agreeing, two absent | REFUSED | AUTHORIZED |
| Four unanimous | AUTHORIZED | AUTHORIZED |
| Three agree, one dissents | CONFLICT | AUTHORIZED |
| Two versus two tie | CONFLICT | AUTHORIZED |
| One observation only | REFUSED | REFUSED |

Across the 30 attempts, final outcomes were 15 AUTHORIZED, 6 CONFLICT, and 9 REFUSED. Permissive mode authorized six attempts despite dissent (three majority/dissent and three tied splits), plus three attempts with two of the four sources missing.

**Tied-split result:** in all three strict=false 2–2 attempts, the canonical payload order selected the miss group, sources S02 and S03. The coordinator applied S02 as representative and the VM register resolver_hit read back as 0. This is a concrete demonstration that the current deterministic tie-break is reproducible but does not express greater evidential support: both groups had exactly two sources. Strict mode correctly classified those same ties as CONFLICT.

The majority-dissent condition shows a related behavior. Under strict=false, the three-source hit group was authorized despite S03 dissenting. Commit applied the winning representative but consumed all four admitted evidence links, including the dissenter's frame. The dissent remains explicit in the evidence partition and the source-link ledger; it is not the VM value chosen for realization.

For partial unanimous evidence, strict=false authorized the two-source quorum even though S02 and S03 were missing. The strict policy remained PENDING before finalization and then closed the event as REFUSED. A single observed source remained below quorum and was refused under both policy modes.

All 30 late proposals were rejected by consensus after finalization. Twelve partial-evidence cases also sent the late source through the real transport path; the new frame remained queued after consensus refused admission. The other 18 cases had all sources already represented and tested a changed value for an existing source directly against consensus. These are separate probes, not a general revision/supersession protocol.

This run is a finite state-contract experiment using synthetic resolver values, one logical event time, four source identities, fixed quorum two, and one local durable mailbox. It establishes the observed behavior of the pinned E-CPU implementation for these cases, not the safety of strict=false in a deployed system and not a universal theorem about all evidence configurations.

## Exhaustive finite policy-space comparison

The separate policy-space enumerator examines every four-source evidence state in which each source is absent, reports HIT, or reports MISS: 3^4 = 81 configurations. It assigns no probability to any configuration. Its output is a complete state-space comparison, not a sample of expected operating frequency.

Eight rules are compared:

- the pinned E-CPU strict and permissive rules;
- observed-source unanimity with quorum;
- unique plurality with quorum (ties abstain);
- strict majority of received evidence;
- majority of the configured roster;
- a minimum two-source plurality margin;
- complete-roster coverage with a unique quorum plurality.

The candidate rules expose different tradeoffs between coverage, dissent tolerance, and tie handling. A rule that authorizes more states is not inherently better: the counts say which finite configurations it accepts, not whether its selected value is true. They are useful for locating disagreement between policies and selecting cases for domain-specific calibration.

The current enumeration includes only absent/HIT/MISS per source. It does not yet include same-source equivocation, dependence between sources, source reliability priors, changing evidence over logical time, or appeal/supersession. Those should be added as separate dimensions, not hidden inside a scalar confidence value. CI uploads the complete per-pattern decision table and a digest-checked summary as the ecpu-epistemic-policy-space artifact.

## Retained artifacts

CI uploads:
- run-manifest.json — pinned revision, matrix and verification counts, digests;
- summary.json — digest-checked compact result;
- attempt-results.json — one complete transition receipt per condition/repetition;
- evidence-ledger.json — explicit source/channel/sequence and payload digests;
- transition-trace.json — evidence, status, finalization, realization, checkpoint, and late-evidence references.

No information-per-cost ratio is calculated and no adaptive policy is updated.

## Interpretation boundaries

- Synthetic resolver values are fixture observations, not external sensor truth.
- The matrix tests one fixed quorum (two), four sources, and two strictness modes.
- All observations occur at one logical event time; cross-time revision and supersession are separate problems.
- The current experiment tests finalized-event immutability, not a revision protocol or appeal/override protocol.
- Refused/conflicted events are not committed, so their input frames remain unconsumed. Late frames from other sources can still be examined by the intake loop; consensus, rather than a global FIFO blockage, is what rejects the post-finalization proposal in the tested partial-evidence cases.
- Three repetitions verify deterministic contracts; they do not yield statistical generalization.
- Passing tests establish the inspected finite cases, not a universal theorem about every evidence configuration.

## Reproduce

    export ECPU_ROOT=external/E-CPU
    export PYTHONPATH=external/E-CPU
    python experiments/ecpu-epistemic-authority-finalization/run_authority_matrix.py --output-dir results
    python -m unittest discover -s experiments/ecpu-epistemic-authority-finalization -p 'test_*.py' -v
