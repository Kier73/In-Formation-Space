# Construction report: append-only hypothesis revision

**Bridge:** hypothesis-revision  
**Implementation:** hypothesis_revision.py  
**Tests:** test_hypothesis_revision.py  
**CI receipt:** results/ci-run-131.json

## Construction

The ledger stores immutable hypothesis-set revisions and append-only events. Each initial hypothesis has a stable identifier and description. The set digest is SHA-256 over the canonical sorted list of those identifier/description pairs under the declared Python JSON serialization contract.

When an adaptive observation policy encounters an interpreted outcome that matches no predicted branch, the new propose_from_unresolved_attempt method can extract the source provenance directly from the unresolved attempt record. It requires the exact lifecycle sequence:

    planned -> dispatched -> admitted -> returned -> interpreted -> unresolved

The terminal reason must be the coordinator's explicit unpredicted-policy-outcome reason. The proposal records the attempt ID, Encounter Envelope reference and ID, payload digest, canonicalization, interpretation artifact reference, proposal method, and proposer.

## Proposal is not activation

A proposed candidate remains outside the active hypothesis set. It must receive an explicit validation result:

- supported
- rejected
- inconclusive

Only candidates marked supported can be added to a new revision. Rejected and inconclusive proposals remain in the candidate and event history but do not enter the active set. Activation creates a new revision whose parent is the prior active revision. All parent hypotheses are retained, and prior revision objects are never overwritten.

Candidates already active are not added a second time in later revisions. This makes activation idempotent with respect to previously incorporated candidate identifiers.

## Verification

GitHub Actions run 131, commit 74f5c9e9061ecd2bd346085bf9c7adc63f84cc53, executed 15 hypothesis-revision tests on ubuntu-latest with Python 3.11. All 15 passed.

The tests cover proposal/activation separation, supported/rejected/inconclusive validation, parent retention, multiple candidates, repeated revisions without duplicate activation, immutable event snapshots, ID uniqueness, explicit validation, provenance extraction from a model-mismatch attempt, and rejection of timeout/rejection/unadmitted-return or unrelated unresolved traces.

The machine-readable execution receipt is stored in results/ci-run-131.json.

## Limits

The ledger does not generate hypotheses, authenticate referenced evidence, or independently establish that a validation outcome is correct. It records an explicit validation claim and its reference. A production implementation should validate Encounter Envelopes and the actual validator's authority separately.

The current operation is expansion-only. It does not remove or retract a hypothesis. Retraction would require its own explicit event and evidence contract so a revision never silently erases prior possibilities.