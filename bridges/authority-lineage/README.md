# Bridge: Append-only authority lineage

**Status:** experimental, hash-chained decision-history model with proposal, review, supersession, and branch-merge semantics.  
**Purpose:** let an authority decision change when justified by later evidence without rewriting the fact that an earlier decision was issued.

## Why this bridge exists

An observation event may be finalized as AUTHORIZED, CONFLICT, or REFUSED. Later evidence, a corrected interpretation, a source-identity review, or a policy reassessment may make a different decision appropriate. That does not make the earlier decision disappear.

This bridge separates four operations:

1. **Evidence arrival:** a new observation or artifact is retained; it does not mutate authority.
2. **Revision proposal:** a proposer identifies the exact prior decision frontier, cites digest-addressed evidence, and explains why review is warranted.
3. **Proposal adjudication:** an explicit actor records ACCEPTED, REJECTED, INCONCLUSIVE, or STALE. Acceptance authorizes a new decision to be issued; it does not itself change authority.
4. **Superseding decision:** a new immutable decision names the exact decision IDs it supersedes, the evidence-set digest, policy digest, representative (when authorized), issuer, and rationale.

Every operation is a new hash-chained ledger entry. Earlier proposals, decisions, and their digests are retained.

## Decision branches and ambiguous frontiers

The model permits two independently accepted proposals to be evaluated against the same base decision before either issues a successor. If both issue decisions, the history has two frontier branches. The ledger reports AMBIGUOUS_FRONTIER; it does not pick whichever branch was written last.

A later reconciliation proposal can name the full frontier as its base. If accepted, its decision may supersede both branches, creating one new frontier tip. This is a multi-parent merge, not deletion of either branch. It preserves both histories and explicitly records how they were reconciled.

A proposal can be marked STALE if its base frontier has changed before adjudication. A stale proposal cannot be accepted against a different frontier. It remains in the ledger as a record of work that was considered but no longer applies to the current branch state.

## Core invariants

- A new finalized decision for an event requires an accepted revision proposal.
- Each proposal is anchored to the entire frontier at the time it is proposed.
- An accepted proposal must be resolved while its base is still the current frontier.
- One accepted proposal can authorize only one superseding decision.
- A decision can supersede one or more prior decisions for the same event only.
- The decision generation is derived from its parents; it is not an editable label.
- AUTHORIZED decisions must name a representative evidence reference. CONFLICT and REFUSED decisions must not.
- Competing successors remain multiple frontier tips until an explicit decision merges them.
- Ledger entries, proposals, resolutions, and decisions are append-only; validation reconstructs the chain and every lineage relationship from the retained entries.

## What the digests do—and do not do

Entry digests form a SHA-256 hash chain, and decisions separately carry a digest over their immutable decision content. Evidence references include a caller-supplied SHA-256 digest. The validator checks integrity and internal consistency.

These digests do not authenticate an actor, prove that evidence exists, fetch or validate evidence artifacts, prove that a signer was entitled to decide, or establish that the supplied policy was correct. Actor identifiers and approval outcomes are provenance declarations supplied to the ledger. Authentication, authorization, signatures, evidence verification, and key management are separate integration obligations.

## API and portable representation

The Python API is in authority_lineage.py:

- create_ledger()
- issue_decision() for the initial decision
- propose_revision() for late evidence or review proposals
- resolve_proposal() to append an explicit adjudication
- issue_decision() with an accepted proposal_id to append a revision
- decision_frontier() to detect a single current decision or ambiguous branches
- decision_history() / event_entries() to inspect the full history
- validate_ledger() to rebuild the hash chain and semantic constraints

The JSON Schema defines the portable envelope. The Python validator adds cross-entry rules that JSON Schema alone cannot establish, including parent existence, proposal acceptance order, same-event ancestry, generation calculation, and frontier consistency.

## Observation evidence adapter

The companion observation_adapter.py connects the existing evidence-gated observation records to this lineage ledger without changing E-CPU.

- issue_initial_decision_from_attempt() accepts a finalized attempt and its retained evidence records. It checks attempt/observation identity, event identity, source-set equality, evidence count, payload digests, and the representative before issuing the first authority decision. Its evidence-set digest is rebuilt from the exact source/channel/sequence/payload identities.
- propose_revision_from_new_evidence() binds a later evidence set to the complete current decision frontier and requires the known evidence records to reconstruct the prior decision's evidence-set digest. A genuinely new source becomes a revision proposal, not an authority mutation.
- An exact repeat from an already represented source raises DuplicateObservationEvidenceError. A changed payload from that source raises SourceEquivocationError. The adapter never turns same-source equivocation into an ordinary new-source proposal.
- The adapter currently requires a single current decision frontier. If the generic lineage ledger exposes competing tips, they must be reconciled through an explicit multi-parent merge before this strict observation adapter can propose another source-based revision.

The adapter still does not fetch/authenticate source artifacts, authenticate actors, or verify external policy correctness. It checks the supplied evidence references and binds their digests to the decision history.

## Reproduce

    python -m unittest discover -s bridges/authority-lineage -p 'test_*.py' -v

The branching test creates two accepted revisions from one base, verifies that the current frontier becomes ambiguous, then issues a multi-parent reconciliation decision that supersedes both branches. The stale-proposal test ensures a proposal cannot be accepted after its cited base has been superseded.

## Limits and next integrations

This is a local decision-history model, not an authority service or consensus protocol. It does not select reviewers, calculate whether new evidence is true, choose an optimal policy, authenticate issuer identities, or decide whether a proposal should be accepted. It handles explicit decision history for one event at a time and uses caller-supplied policy and evidence digests.

The next useful integration is a bridge from the E-CPU finalized-event snapshot and observation evidence ledger into a revision proposal, followed by a validator that ensures the proposal's cited evidence was actually admitted or independently reviewed. A future multi-party protocol should add signer identity, quorum certificates for revision decisions, and replay/rollback policy without weakening the append-only history.
