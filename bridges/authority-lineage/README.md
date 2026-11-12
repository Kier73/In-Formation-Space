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

## Deterministic review certificates

`review_certificates.py` adds a review record between proposal creation and proposal resolution:

1. `build_review_certificate()` binds the complete proposal payload, its base decision IDs and decision digests, the ledger identity, and the exact frozen policy definition.
2. Each submitted reviewer receipt records a seat, reviewer reference, APPROVE / REJECT / ABSTAIN vote, rationale, review-artifact reference, and SHA-256 digest of that artifact.
3. The evaluator reconstructs missing seats as ABSENT, applies the selected policy, and records the full outcome and threshold explanation.
4. `record_review_certificate()` appends the complete certificate to the same authority-lineage hash chain.
5. `resolve_reviewed_proposal()` resolves from that recorded certificate. The resolution includes `review_certificate_digest`; the ledger validator rejects a contradictory outcome.
6. If the authority frontier changes after certification but before resolution, the review is retained and the proposal resolves as STALE. It cannot authorize a superseding decision.

The current certificate profile intentionally reuses the finite three-seat model in [Authority Adjudication Policy Space](../../experiments/authority-adjudication-space/README.md): R00 is the proposer and R01/R02 are independent-review roles. A policy that excludes the proposer still retains an R00 vote if supplied, but the evaluator explicitly excludes it from eligible counts. Abstentions count as participation, not approval or rejection. Missing seats are not invented.

The certificate can be reconstructed with `validate_review_certificate()`; `validate_review_certificates_in_ledger()` checks every embedded certificate. The example runner creates an initial decision, a revision proposal, two independent review receipts, a recorded certificate, a certificate-bound resolution, and a superseding decision:

    python bridges/authority-lineage/review_certificate_demo.py --output results/review-certificate-example.json

The CI workflow runs this example and uploads the resulting ledger/certificate artifact. The tests also alter votes, base-decision digests, and resolution outcomes to ensure the reconstruction and binding checks reject those inconsistencies.

### Security and trust boundary

The certificate is **deterministic and tamper-evident, not authenticated**. Reviewer references such as `agent://reviewer-one` are labels; the implementation cannot establish that they represent separate agents, that a receipt was actually authored by that reviewer, or that the reviewer was eligible and independent. A review-artifact digest binds bytes only when an independent verifier obtains and hashes the referenced artifact. The ledger's SHA-256 chain likewise does not authenticate actors or prevent a party who can rewrite the entire ledger from recomputing it.

The policy evaluator is a frozen, versioned application contract, not a proof that the policy is wise or accurate. An accepted certificate authorizes the lineage workflow to issue a new decision; it does not by itself establish that the reviewed claim is true, that an E-CPU VM applied it, or that any external party must accept it.

For interoperable signatures, the next layer should use a standard canonicalization and credential/signature format rather than treating the current Python JSON serializer as a cross-language signing specification. See [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) and the [W3C Verifiable Credentials Data Model 2.0](https://www.w3.org/TR/vc-data-model-2.0/). Those standards inform future work; this iteration does not claim conformance.

## Signed reviewer receipts (DSSE / Ed25519)

`signed_review_receipts.py` adds an optional signature envelope for each vote receipt in a deterministic review certificate. This is a detached bundle: it binds signatures to the certificate without changing the authority-lineage ledger format or requiring every consumer to use the same key provider.

Each signed payload contains the vote **and the exact context in which the vote was cast**:

- certificate digest and proposal ID/digest;
- event key and the complete base-decision ID/digest set;
- policy digest;
- assigned reviewer seat and principal reference;
- APPROVE, REJECT, or ABSTAIN, rationale, review-artifact reference, and its claimed SHA-256 digest.

That context binding is important: a signature over the word APPROVE alone could be copied into another proposal. Here, changing the proposal, event, base decisions, policy, vote, or payload type changes the signed bytes and invalidates the signature.

Each receipt is serialized to UTF-8 JSON bytes and wrapped in a DSSE envelope. The implementation signs DSSE's pre-authentication encoding:

    PAE(type, payload) =
      "DSSEv1" + SP + LEN(UTF8(type)) + SP + UTF8(type)
      + SP + LEN(payload) + SP + payload

The UTF-8 byte lengths matter. The payload type is included in the signed PAE, so changing the declared interpretation of the payload invalidates the signature. Each vote currently has exactly one Ed25519 signature and an envelope-local key ID. Per DSSE, a key ID is only an unauthenticated lookup hint; verification uses the actual public key selected from the supplied trust store.

### Verification flow

- `build_trust_store()` creates a portable map from a reviewer seat and principal label to an Ed25519 public key. The key ID is the SHA-256 fingerprint of the raw 32-byte public key.
- `sign_review_vote(certificate, vote, private_key)` signs the vote plus its certificate/proposal/authority context and returns a DSSE envelope containing base64 payload and signature bytes.
- `verify_signed_review_vote()` checks the envelope, DSSE PAE signature, public-key fingerprint, assigned seat, and principal reference.
- `build_signed_review_bundle()` requires one valid signed envelope for every vote already present in the authority review certificate. It rejects extra, duplicate, missing, or altered receipts and refuses signatures made for another proposal or base frontier.
- `validate_signed_review_bundle()` reconstructs the bundle against the certificate and supplied trust store. The bundle records the digest of that exact trust-store version.
- When the caller supplies the referenced review-artifact bytes, artifact digests are checked too. Without those bytes, `review_artifacts_verified` is false; a signature over a claimed digest is not a fetch or verification of the artifact.

Portable schemas are supplied for the trust store, signed bundle, and decoded signed vote payload. JSON Schema covers structure; Python validation adds signature, trust binding, context reconstruction, duplicate-key rejection, and exact receipt coverage.

The trust store is supplied separately to the verifier. Its digest pins the version used for a bundle, but does not establish who approved or distributed that trust store. A deployment must obtain and pin the trust store through its own independent governance or configuration channel. Key creation, enrollment, rotation, revocation, expiration, compromised-key response, and multi-organization delegation are not implemented here.

### Reproduce

    python -m pip install "cryptography>=42,<50"
    python -m unittest discover -s bridges/authority-lineage -p 'test_*.py' -v
    python bridges/authority-lineage/signed_review_demo.py --output results/signed-review-example.json

The demonstration generates ephemeral keys, signs both reviewer receipts, validates the signatures and the supplied review-artifact bytes, and writes a self-contained example with public keys only. The private keys are never included. Its successful verification proves possession of those ephemeral keys within that one run; it is not proof of persistent or externally authenticated agent identities.

### Standards and compatibility boundary

The implementation follows the DSSE envelope/PAE model described in the [DSSE specification repository](https://github.com/secure-systems-lab/dsse) and uses Ed25519 as specified by [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html). DSSE signs both the payload and its payload type; the DSSE specification treats `keyid` as an unauthenticated hint, not as the source of trust. Ed25519 supplies a public-key signature check, but the trust relationship still comes from the verifier's provisioned public-key mapping.

This implementation signs the exact serialized payload bytes carried in the DSSE envelope. Its deterministic Python JSON serialization is not claimed to be RFC 8785/JCS, a cross-language signing canonicalization, a W3C Verifiable Credential, or a full in-toto attestation. A verifier must check the original envelope bytes rather than reserialize an equivalent JSON object before signature verification.

## Anchoring signed receipts in the authority ledger

`record_signed_review_bundle()` appends a new immutable `proposal_review_signed` event after the `proposal_review_certified` event and before proposal resolution. The new event contains the complete DSSE bundle, its digest, the certificate digest, and the public trust-store snapshot used to verify the envelope signatures. It does not store private keys.

The lifecycle is now explicitly ordered:

    revision_proposed
      -> proposal_review_certified
      -> proposal_review_signed
      -> proposal_resolved
      -> decision_issued

The signed event is part of the authority-lineage hash chain and is returned by `event_entries()`. Ordinary `validate_ledger()` reconstructs embedded review certificates and verifies the signed envelopes against the embedded public-key snapshot. If the entire ledger and its hashes are recomputed after changing a signature, validation still fails.

A resolution for a proposal with a recorded signed bundle must include both:

- `review_certificate_digest`, identifying the deterministic policy evaluation and receipt set;
- `signed_review_bundle_digest`, identifying the cryptographic envelope set and trust-store version.

Calling the ordinary `resolve_proposal()` without the exact signed-bundle digest is rejected once a signed event exists. Use `resolve_signed_reviewed_proposal()` with the independently supplied `trusted_trust_store`; this compares its digest to the snapshot in the ledger before resolving. When a frontier changes after the signed event but before resolution, the original signed review is retained and the proposal resolves as STALE.

### Trust-store boundary in a ledger

The ledger retains a public trust-store snapshot so signature verification is reproducible. The snapshot is not a root of trust. Ordinary ledger validation proves that the private keys corresponding to the embedded public keys signed the contextual review payloads; it does not prove that those keys belong to the named agents or were approved by the right authority.

A production caller should use `validate_signed_review_bundles_in_ledger(..., trusted_store_digests=...)` or `resolve_signed_reviewed_proposal(..., trusted_trust_store=...)` with a digest/key map provisioned independently from the ledger. Trust-store enrollment, organizational delegation, key rotation, expiry, revocation, and recovery remain out of scope. When the bundle states that review-artifact bytes were checked at creation, a later verifier can repeat that check only by supplying those bytes through `review_artifacts_by_proposal`; signature verification alone does not fetch them.

The ledger schema now includes the signed event and the resolution's signed-bundle digest. Reproduce the complete lifecycle with:

    python bridges/authority-lineage/signed_review_ledger_demo.py --output results/signed-review-ledger-example.json

The example uses ephemeral keys, includes public keys only, records the signed event, resolves against the caller-supplied trust store, and issues a successor decision. It proves the mechanics of the workflow, not persistent agent identity.

## Observation evidence adapter

The companion observation_adapter.py connects the existing evidence-gated observation records to this lineage ledger without changing E-CPU.

- issue_initial_decision_from_attempt() accepts a finalized attempt and its retained evidence records. It checks attempt/observation identity, event identity, source-set equality, evidence count, payload digests, and the representative before issuing the first authority decision. Its evidence-set digest is rebuilt from the exact source/channel/sequence/payload identities.
- propose_revision_from_new_evidence() binds a later evidence set to the complete current decision frontier and requires the known evidence records to reconstruct the prior decision's evidence-set digest. A genuinely new source becomes a revision proposal, not an authority mutation.
- An exact repeat from an already represented source raises DuplicateObservationEvidenceError. A changed payload from that source raises SourceEquivocationError. The adapter never turns same-source equivocation into an ordinary new-source proposal.
- The adapter currently requires a single current decision frontier. If the generic lineage ledger exposes competing tips, they must be reconciled through an explicit multi-parent merge before this strict observation adapter can propose another source-based revision.

The adapter also supports a REFUSED attempt with an empty evidence set when the caller supplies the event key explicitly; it does not invent event coordinates from an empty list. An AUTHORIZED decision must select a representative within the recorded winning evidence group, not merely any received source.

The adapter still does not fetch/authenticate source artifacts, authenticate actors, or verify external policy correctness. It checks the supplied evidence references and binds their digests to the decision history.

## Reproduce

    python -m unittest discover -s bridges/authority-lineage -p 'test_*.py' -v

The branching test creates two accepted revisions from one base, verifies that the current frontier becomes ambiguous, then issues a multi-parent reconciliation decision that supersedes both branches. The stale-proposal test ensures a proposal cannot be accepted after its cited base has been superseded.

## Limits and next integrations

This is a local decision-history model, not an authority service or consensus protocol. It does not select reviewers, calculate whether new evidence is true, choose an optimal policy, authenticate issuer identities, or decide whether a proposal should be accepted. It handles explicit decision history for one event at a time and uses caller-supplied policy and evidence digests.

The next useful integration is a bridge from the E-CPU finalized-event snapshot and observation evidence ledger into a revision proposal, followed by a validator that ensures the proposal's cited evidence was actually admitted or independently reviewed. A future multi-party protocol should add signer identity, quorum certificates for revision decisions, and replay/rollback policy without weakening the append-only history.
