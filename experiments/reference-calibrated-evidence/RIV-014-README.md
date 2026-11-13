# RIV-014: Signed review of verified reference evidence

**Status:** finite two-reviewer cryptographic attestation, version 0.1.  
**Question:** How can a verified reference-evidence bundle receive independent, cryptographically attributable reviewer approval under a root-authenticated and expiring reviewer trust manifest?

## Relationship to RIV-013

RIV-013 validates inline Encounter Envelopes, per-source payload digests, policy-path bindings, and append-only Authority Lineage decisions. That establishes content integrity and reconstruction consistency. It does not prove who produced the original sensor payload or whether a physical reference standard is true.

RIV-014 adds a separate review event over the complete RIV-013 bundle. It reuses the existing Authority Lineage review-certificate, signed-review receipt, and trust-manifest mechanisms:
- the independent_two_of_two policy excludes the proposer and requires approval by both distinct reviewer seats R01 and R02;
- each reviewer signs the exact review vote using Ed25519 and the existing DSSE receipt format;
- the reviewer public-key trust store is embedded in a generation-1 manifest;
- a root key signs that trust manifest;
- validation uses caller-pinned root public keys, the expected registry, generation, and an explicit verification time;
- the accepted proposal is resolved into a new Authority Lineage decision bound to the signed review bundle.

Reviewer and root private keys are supplied by the caller and are never stored in the output record. Public trust material, signed votes, the trust-manifest envelope, review artifacts and ledger receipts are retained for independent verification.

## What is being attested

The reviewers approve a narrow proposition: the RIV-013 Encounter Envelope payloads, source-evidence digests, ObservationPath bindings, and Authority Lineage decisions are internally consistent under their declared schemas and reconstruction contracts.

The review explicitly does **not** attest to physical sensor identity, sensor custody, the truth or custody of the physical reference standard, authenticity of the source devices that allegedly produced payload values, or external transport identity.

This is a signature-backed reviewer approval of the content bundle, not a signature-backed measurement.

## Review process

1. RIV-013 bundle validation reconstructs the envelope and source evidence bundle.
2. A separate Authority Lineage event is created for the bundle-review question. The first decision records machine-verified content integrity only.
3. A proposal requests independent review of that bundle digest and its trust boundary.
4. The two review seats build a review certificate under independent_two_of_two.
5. Each reviewer signs their vote. Signed receipts are recorded in Authority Lineage.
6. A root-signed, expiring trust manifest binds the reviewer public keys to the declared registry and generation.
7. The trust manifest, the two reviewer signatures, the review artifacts, and ledger receipt are verified.
8. The accepted review proposal becomes a new AUTHORIZED decision whose representative is the signed-review bundle digest.

The review event is separate from the underlying sensor event. It must not be confused with sensor-level source authentication or quorum verification.

## Reproduction

From the repository root:

    python -m py_compile experiments/reference-calibrated-evidence/signed_reference_evidence_review.py
    python -m unittest discover -s experiments/reference-calibrated-evidence -p 'test_signed_reference_evidence_review.py' -v

The workflow compiles the RIV-013 verifier and existing Authority Lineage review modules, validates the Draft 2020-12 record schema, runs the tests, and executes a deterministic example. Test signing keys are ephemeral and never included in output bundles.

## Trust and rollback boundary

- Ed25519 reviewer signatures authenticate the reviewer approvals relative to the trust store.
- The root signature authenticates the trust-store manifest relative to caller-pinned root public keys.
- Manifest expiry, registry ID, and generation are checked at the supplied verification time.
- A caller must persist and enforce an appropriate minimum generation or expected predecessor digest across updates to prevent trust-manifest rollback.
- The trust manifest cannot establish its own root of trust. Root public-key pins must come from an independent channel.
- The review record contains no private keys. It includes public reviewer keys and public signatures so that a separate verifier can reproduce all checks.
- No signature in RIV-014 proves that a physical sensor generated a payload or that the reference standard was physically correct.

## Files

- signed_reference_evidence_review.py — initial content decision, review proposal, two-seat certificate, signed votes, root trust manifest, review resolution and record verification.
- test_signed_reference_evidence_review.py — valid dual approval, key pinning, manifest time validity, signature tampering, reviewer artifact tampering, and private-key exclusion.
- signed-reference-evidence-review.schema.json — portable signed review record schema.
