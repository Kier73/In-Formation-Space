# Repeated transition evidence

**Status:** finite descriptive aggregation experiment  
**Builds on:** [Trial 08: Intervention-aware attention](../../experiments/description-to-realization/trials/trial-08-intervention-aware-attention/README.md) and the [transition-conformance bridge](transition-conformance.md).

## Question

After several probes have been performed from the same `(probe_id, current_state)` cell, what do the actual witnessed transitions show?

A single conformance record compares one execution with one predicted transition. Repeated observations can reveal that the same cell has produced one observed transition value or several distinct values. They can also include returns where the visible outcome is known but the next state was not independently witnessed.

This experiment aggregates those records without silently promoting a descriptive frequency into a stochastic transition probability.

## Aggregation rules

1. Every input conformance record is reconstructed from the pinned Trial 08 model and its embedded ObservationPath snapshot before it is counted.
2. Records are grouped by `(probe_id, current_state)`; records from different cells remain separate.
3. Full transition witnesses are counted by the canonical pair `(outcome, next_state)`.
4. Outcome-only records are counted in a separate histogram and are excluded from full-transition denominators.
5. Each sample retains its attempt ID, conformance digest, returned Encounter Envelope reference, payload digest, and before/after state witness references.
6. Duplicate attempt identities, duplicate conformance digests, model mismatches, and mixed model references are rejected.

Frequencies are exact rational sample fractions such as `2/3`. They describe the supplied observations only.

## What the classifications say

- `no_full_transition_witnesses`: no sample had a witnessed next state.
- `one_distinct_full_transition_observed`: all full samples had the same observed outcome/next-state pair.
- `multiple_distinct_full_transitions_observed`: at least two different full transition pairs were observed.

A separate `prediction_status` indicates whether all full samples match the pinned model or at least one does not.

These labels deliberately avoid calling a cell deterministic or stochastic. Repeated identical observations do not prove deterministic dynamics. Different outcomes do not, by themselves, prove stochastic dynamics: hidden context, unmodelled state drift, concurrency, measurement error, or policy selection effects may explain the variation.

## No automatic learning

The summary is a review artifact. It does not create transition proposals, alter the active transition model, infer transition probabilities, recalibrate intervention cost, or change Trial 08's attention policy.

A future stochastic model should be a separately versioned formulation with explicit context, process-noise and observation-noise assumptions, sampling design, and independent validation. Until then, preserve the empirical diversity and the unresolved explanations.

## Reproduce

From the repository root:

```bash
python -m py_compile bridges/observation-path/transition_evidence.py
python -m unittest discover -s bridges/observation-path -p 'test_transition_evidence.py' -v
```

Files:

- `transition_evidence.py` — exact, digest-bound aggregation and reconstruction.
- `transition-evidence-summary.schema.json` — portable summary schema.
- `test_transition_evidence.py` — repeated, varied, outcome-only, mixed-cell, duplicate, tampering, reconstruction, and schema checks.

The bridge retains evidence references and digests but does not fetch or authenticate the referenced external artifacts. It also does not correct for adaptive sampling bias.
