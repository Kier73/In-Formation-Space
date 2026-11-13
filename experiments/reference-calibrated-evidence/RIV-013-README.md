# RIV-013: Verified reference evidence and authority lineage

**Status:** finite evidence-bundle verification bridge, version 0.1.  
**Question:** How can an authorized reference-policy execution retain and independently reconstruct its inline measurement payloads, per-source evidence records, and append-only authority decisions?

## Relationship to RIV-012

RIV-012 verifies that each reference action follows the current RIV-011 policy node and advances only through a structurally valid ObservationPath:

planned → dispatched → admitted → returned → evidence_authorized → interpreted

RIV-012's payload digest is a content reference in the path. RIV-013 adds the actual inline Encounter Envelope, verifies its structure and SHA-256 integrity under an explicit canonicalization, and checks the per-source evidence records embedded in the envelope payload. It then uses the existing observation_adapter in the authority-lineage bridge to record an initial append-only decision for each reference attempt.

RIV-013 does not replace RIV-012's policy-prefix verification or RIV-009's Bayesian update. It wraps the RIV-012 record with stronger content and authority-lineage consistency evidence.

## Verification layers

For each policy-prefix step, RIV-013 requires one Encounter Envelope whose:
- id matches the returned encounter ID;
- source.kind is sensor, with source.reference matching the selected sensor;
- inline payload.value matches the policy report, policy state, policy node, signal prefix, selected candidate, known standard, and returned signal;
- integrity declares sha256 and json-sort-keys-utf8-v1;
- digest recomputes exactly from the inline payload.

The inline payload also contains one evidence record per observed source. Each source record binds the same attempt, observation, and logical event; source and channel identity; a positive sequence; and a payload_value whose canonical digest is checked independently.

After source records match the path's AUTHORIZED observed_sources, RIV-013 calls the existing ObservationEvidence adapter to issue an initial Authority Lineage decision. The ledger retains an append-only digest chain and an evidence-set digest. Each receipt binds the path authority event, the reconstructed lineaged decision, the exact source set, and the verified Encounter Envelope.

## Reproduction

From the repository root:

    python -m py_compile experiments/reference-calibrated-evidence/verified_reference_evidence_bundle.py
    python -m unittest discover -s experiments/reference-calibrated-evidence -p 'test_verified_reference_evidence_bundle.py' -v

The workflow validates the Draft 2020-12 bundle schema, compiles the Encounter Envelope validator, Authority Lineage adapter, RIV-012 execution module and RIV-013 verifier, then runs the exact tests.

## Evidence scope and limitations

- VERIFIED means the inline payload matches the envelope's declared SHA-256 under the stated canonicalization. It does not authenticate the sensor or prove the physical standard's truth.
- Per-source payload digests are checked against payload_value retained inside the envelope. This is internal consistency, not proof that a physical source generated those values.
- Authority Lineage records an append-only hash-chained decision from the supplied attempt, policy digest and source records. It does not authenticate the issuer, source identities, quorum membership, policy correctness, or a signature.
- The supplied AUTHORIZED ObservationPath event is structurally reconstructed; its external evidence reference is not fetched.
- This version requires inline envelopes. Referenced payloads are not fetched or treated as verified.
- SHA-256 and an append-only hash chain provide content integrity and reconstruction, not digital signatures, a pinned trust root, or verified transport identity.
- The bundle adds no changes to the Bayesian calibration posterior, source Ground, or sensor likelihood model.

## Files

- verified_reference_evidence_bundle.py — Encounter Envelope validation, source-record digest verification, Authority Lineage decisions, and bundle reconstruction.
- test_verified_reference_evidence_bundle.py — valid envelope/source evidence, altered payload, missing source, representative mismatch, referenced payload refusal, and bundle tamper tests.
- verified-reference-evidence-bundle.schema.json — portable bundle schema.
