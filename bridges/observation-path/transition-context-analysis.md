# Context-stratified transition evidence

**Status:** finite descriptive analysis experiment  
**Builds on:** [repeated transition evidence](transition-evidence.md), [transition conformance](transition-conformance.md), and the Trial 08 intervention-aware attention model.

## Question

When repeated observations of one `(probe_id, current_state)` cell disagree, does an explicitly recorded context partition reduce the disagreement that remains within each stratum?

A collection of different transitions is not, by itself, evidence of a stochastic process. The differences may instead align with a context distinction that was omitted from the original model: for example, an observed runtime revision, a device mode, a host, a clock segment, or a declared environment category.

This experiment makes that question testable without treating a context label as a causal explanation or silently changing the active transition model.

## Input contract

The analysis accepts the same self-contained transition-conformance records as [transition evidence](transition-evidence.md), plus optional context-assignment records. A context assignment is bound to exactly one:

- `attempt_id`;
- `conformance_digest`;
- named set of context dimensions;
- `assignment_digest` over the canonical assignment content.

A dimension is either:

- `{"status": "observed", "value": ...}`, where the value is a JSON scalar; or
- `{"status": "unknown", "reason": "..."}`.

A missing assignment, an omitted dimension, and an explicit unknown value remain three distinct cases. Context records are caller-supplied; the digest makes their contents reproducible and detects mutation, but does not authenticate the producer or prove the truth of a context claim.

Example:

```python
from transition_context import (
    build_transition_context_assignment,
    build_transition_context_analysis,
)

assignments = [
    build_transition_context_assignment(
        attempt_id=record["attempt_id"],
        conformance_record=record,
        dimensions={
            "runtime_revision": {"status": "observed", "value": "rev-12"},
            "clock_segment": {"status": "observed", "value": "process-a/segment-3"},
            "device_mode": {"status": "unknown", "reason": "not captured"},
        },
        source_ref="artifact://run-12/context-record",
    )
    for record in conformance_records
]

analysis = build_transition_context_analysis(
    model_document=trial_08_model,
    conformance_records=conformance_records,
    context_assignments=assignments,
)
```

Assignments are optional and may cover only part of the sample. A supplied assignment must bind to a conformance record in the same analysis; duplicate, stale, foreign, or digest-mismatched assignments are rejected.

## Comparison method

The module reconstructs every conformance record against the pinned Trial 08 model before counting it. For each observed context dimension, and for the joint partition of attempts with every dimension observed, it compares full transition witnesses using exact unordered-pair counts.

For a sample of (n) full transition witnesses, there are (inom{n}{2}) unordered pairs. A pair disagrees when its `(outcome, next_state)` values differ.

The report keeps three quantities separate:

1. **Pooled disagreement:** all pairs in the context-covered full-transition sample, before partitioning.
2. **Within-stratum disagreement:** disagreeing pairs whose members share the same observed context value (or complete joint context).
3. **Between-stratum disagreement:** disagreeing pairs whose members belong to different observed context groups.

The partition is described as separating the supplied sample only when at least two full-transition strata and within-stratum pairs exist, pooled transition diversity exists, and no within-stratum disagreement remains. Where disagreement falls but remains non-zero, the report says that the partition reduces within-stratum disagreement. Exact fractions accompany counts when a denominator exists; no statistical significance test or probability model is fitted.

Outcome-only observations remain visible in context-group counts and outcome histograms, but never enter full-transition pair denominators.

## Reading the result

A useful pattern is repeated within-group agreement alongside between-group disagreement. This is evidence that the supplied context distinction organizes the observed sample. It is a reason to investigate whether the original state description omitted a meaningful distinction.

It does **not** establish that the context caused the transition, that the context is a hidden state, that the partition generalizes to future observations, or that the system is deterministic within each stratum. Small samples, adaptive selection, context measurement error, unmeasured conditions, process drift, and concurrency can all affect the result.

The joint partition is deliberately stricter than each one-dimensional analysis: an attempt enters it only when every dimension observed anywhere in that cell has an explicit observed value for that attempt. Unknown, omitted, and unassigned attempts are listed as incomplete instead of being mapped to a synthetic category.

## Reproduction

With Python 3.11 and the repository's Trial 08 files available:

```bash
python -m pip install "jsonschema>=4,<5"
python -m py_compile bridges/observation-path/transition_context.py
python -m unittest discover -s bridges/observation-path -p 'test_transition_context.py' -v
```

The [focused contextual-transition workflow](../../.github/workflows/contextual-transition-evidence.yml) runs compilation, JSON Schema validation, and the focused tests.

## Evidence boundary

- Source conformance is reconstructed from its embedded ObservationPath; external Encounter Envelope and state-witness artifacts are not fetched or authenticated here.
- Context assignment digests provide content identity, not signatures, authority, or source authentication.
- Pairwise comparison uses only the supplied full `(outcome, next_state)` witnesses. Outcome-only returns are excluded from those denominators.
- Context categories are descriptive labels. No causal effect, hidden-state identity, deterministic law, or stochastic law is inferred.
- Frequencies and pairwise fractions describe the supplied, potentially policy-selected sample. Selection bias is not corrected.
- No transition candidate is created or activated; no model, intervention cost, or attention policy is changed.

## Next discriminating experiment

A later active-attention study could rank *which missing context observation* would most efficiently distinguish competing explanations for residual within-stratum disagreement. That would need an explicit candidate-observation model, costs, and independently recorded execution evidence. This analysis does not invent those candidates or claim that an unmeasured context has already been observed.
