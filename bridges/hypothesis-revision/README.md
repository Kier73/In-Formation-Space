# Bridge: Append-only hypothesis revision

**Status:** experimental counterexample-guided model-revision ledger.  
**Connects:** adaptive policy model mismatch, returned observation evidence, and finite hypothesis-set planning.

## Why it exists

An adaptive policy can encounter an interpreted observation value that matches none of its predicted branches. That is not automatically a new fact about the world, nor proof of one particular explanation. It is evidence that the current hypothesis or observation model may be incomplete.

This bridge records the resulting model-revision process without rewriting history:

1. Preserve the active hypothesis-set revision and its digest.
2. Propose a new hypothesis, tied to the mismatching observation attempt, Encounter Envelope, interpretation artifact, and proposal method.
3. Keep the candidate in proposed status.
4. Record an explicit validation outcome: supported, rejected, or inconclusive, with a validation reference and validator.
5. Create a new revision only when at least one candidate has been explicitly marked supported.

## Retention rule

Activating a revision retains every hypothesis from its parent revision and adds only supported candidates. No previous revision is overwritten. Rejected and inconclusive proposals remain in the candidate/event history but do not enter the active set.

This is deliberately an expansion-only operation. Hypothesis removal or retraction would require a separate explicit revision operation with its own evidence and review contract.

## Files

- hypothesis_revision.py — append-only revision and proposal ledger.
- test_hypothesis_revision.py — validation, provenance, retention, activation, and immutability tests.

## Reproduce

    python -m unittest discover -s bridges/hypothesis-revision -p 'test_*.py' -v

## Limits

The ledger does not generate or validate hypotheses by itself. It records who proposed a candidate, what observation artifacts motivated it, and which validation result was explicitly supplied. A validation label is a provenance claim, not an independently authenticated proof. Candidate selection and external evidence checking remain separate operations.