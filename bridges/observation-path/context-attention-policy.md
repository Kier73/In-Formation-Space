# VGI context-attention policy bridge

**Status:** finite proposal generator, built on VGI's current exact partial-probe policy planner  
**Source evidence:** [context-stratified transition analysis](transition-context-analysis.md)  
**Runtime:** [Virtual-Ground-Interpreter](https://github.com/Kier73/Virtual-Ground-Interpreter), pinned at `ac13c1bbd92dfd09f17de51adef7adb2d2088bf6`

## Question

After repeated attempts from one `(probe_id, current_state)` cell have been collected, which missing context observation should be requested next to separate attempts into observer-relative context classes?

The preceding context analysis can compare supplied context partitions, but it does not choose what to measure next. VGI already has an exact finite AND/OR partial-probe planner. This bridge expresses context capture in that planner's vocabulary rather than adding a second attention algorithm.

## Representation

For one selected transition cell:

- Each original attempt ID becomes a state in a **synthetic observer-space Ground**.
- Each caller-declared context capture method is an action.
- Each finite possible context value is an output code for that action.
- A known context assignment is represented as a known self-transition with the encoded value.
- Unknown, not-supplied, and unassigned context cells remain missing transitions.
- A proposed capture for one missing `(attempt_id, method_id)` cell becomes a VGI `TransitionProbe`.
- Every declared possible value becomes an AND branch; the planner chooses which measurement to make as an OR choice.

The synthetic Ground is a model of the information available to the context-attention planner. Its states are attempt identifiers, not claims about physical hidden states. Each value is mapped to an injective base-8 output vector. Wider vectors are used when a method has more than eight distinct categories.

The bridge currently accepts one capture method per context dimension. This deliberately avoids implying that two different instruments or procedures are interchangeable measurements of the same field. Values already observed in the source analysis are automatically included in that method's encoding, even if omitted from the caller's prospective value list.

## Objective

The pinned VGI planner searches a finite AND/OR policy:

1. Minimize the worst-branch number of unresolved attempt pairs.
2. Minimize the exact worst-branch cumulative measurement cost.
3. Minimize the maximum number of measurements on a path.
4. Break remaining ties deterministically.

Costs are exact integers or rational values. Floating-point costs are rejected. The search is exact only over the supplied methods, declared values, selected attempts, and configured search bound. When the state cap is exceeded, VGI fails closed and returns no partial policy labelled optimal.

This policy does **not** use empirical frequencies as probabilities. It does not assume the declared values are exhaustive, and it does not assign probabilities to branches.

## Residual transition disagreement

Before planning, the bridge applies VGI's sparse one-step observer comparison to the already observed context values. It records, for every pair of attempts, whether the selected context dimensions currently imply:

- **equivalent:** every selected method is observed on both attempts and produces the same value;
- **distinguishable:** at least one selected method produces different observed values;
- **unresolved:** the supplied context evidence is insufficient to classify the pair.

For full transition witnesses only, the report also counts whether the original `(outcome, next_state)` values disagree within each relation class. A disagreement among context-equivalent attempts is residual variation that the selected context dimensions do not explain. It is not hidden-state proof or a causal result. Outcome-only attempts may participate in context attention, but are not included in full-transition pair counts.

This is a baseline over the observed context fields, not a forecast of what a not-yet-executed policy will reveal. The VGI plan is retained separately as a future measurement proposal.

## API

The focused CI checks out the VGI pin and exercises the bridge. The report records that CI dependency pin, but a runtime API object passed by a caller is not cryptographically attested by the bridge; independent reproduction requires using the same pinned source revision:

```python
from fractions import Fraction
import vgi

from context_attention import (
    ContextProbeMethod,
    build_context_attention_plan,
    validate_context_attention_plan,
)

methods = (
    ContextProbeMethod(
        method_id="capture-runtime",
        dimension="runtime_revision",
        possible_values=("rev-a", "rev-b", "rev-c"),
        cost=Fraction(3, 2),
        source_ref="protocol://runtime-revision-reader-v1",
    ),
    ContextProbeMethod(
        method_id="capture-host",
        dimension="host_class",
        possible_values=("host-a", "host-b"),
        cost=Fraction(2),
    ),
)

proposal = build_context_attention_plan(
    context_analysis=context_analysis,
    model_document=trial_08_model,
    probe_id="inspect",
    current_state="state-0",
    methods=methods,
    vgi_api=vgi,
    budget=Fraction(8),
    max_probes=8,
    max_states=10_000,
)

validate_context_attention_plan(
    proposal,
    context_analysis=context_analysis,
    model_document=trial_08_model,
    vgi_api=vgi,
)
```

The report embeds the synthetic Ground, exact method/value encodings, initial pair relations, complete VGI policy tree and digest, plus an optional `next_measurement` summary for the tree's first OR choice. Its outer digest covers the complete proposal. Validation rebuilds it from the independently reconstructed context analysis, method definitions, plan settings, and caller-supplied VGI API. The CI workflow pins the implementation used for the reference tests; the report digest alone cannot authenticate which runtime implementation a separate caller supplied.

## Evidence and execution boundary

- **Proposal only:** this module does not dispatch a context measurement, advance an ObservationPath, apply a Ground revision, or modify the source transition model.
- **Actual measurements remain evidence-gated:** a future execution adapter must route the chosen attempt/method through the existing dispatch, receiver-admission, return, authority, application, interpretation and revision contracts as applicable.
- **Out-of-set values:** an observed value not represented among the declared branches is a model mismatch. It must not be coerced to the nearest value or silently added to the report.
- **Context truth:** assignments are validated and bound to their source conformance records, but the context source itself is not authenticated by this bridge.
- **Causation:** equal context values mean equivalent only under the selected finite observer actions. They do not prove physical identity or that context caused the transition.
- **Selection:** the source evidence may be adaptively selected. The report does not correct for policy-selection bias, unmeasured conditions, concurrency, drift, or observation error.
- **Revision:** neither the active context Ground nor the original transition model is revised by planning.

## Reproduction

The [focused workflow](../../.github/workflows/context-attention-policy.yml) checks the bridge against the pinned VGI source. The repository-wide [Encounter Envelope workflow](../../.github/workflows/encounter-envelope-tests.yml) also checks this bridge while preserving the older VGI checkout used by the existing partial-probe execution bridge.

