# Context measurement evidence binding

**Status:** evidence-gated context-measurement bridge  
**Planner:** [VGI context-attention policy](context-attention-policy.md)  
**Evidence lifecycle:** [Observation Path](README.md)  
**Analysis target:** [context-stratified transition evidence](transition-context-analysis.md)

## Closed loop

The preceding bridge can choose a missing context observation, but a recommendation is not a measurement. This bridge closes that distinction:

```text
context analysis
    -> VGI minimax attention policy
    -> planned ObservationPath
    -> dispatch
    -> receiver admission
    -> returned Encounter Envelope
    -> explicit authority decision
    -> exact context interpretation
    -> new context assignment
    -> rebuilt context analysis
    -> recomputed attention policy
```

The planner's first OR choice identifies one `(attempt_id, method_id, dimension)`. An executor uses `new_context_measurement_path(...)` to create a planned-only `ObservationPath` bound to the policy digest and exact measurement cost. The executor is responsible for recording real dispatch, admission, return, and authorization evidence. The bridge does not fabricate these events or initiate a transport.

## Required path contract

A measurement is accepted only when the supplied path can be independently replayed through the existing `ObservationPath` implementation and has exactly these stages:

1. `planned`
2. `dispatched`
3. `admitted`
4. `returned`
5. `evidence_authorized`
6. `interpreted`

The intent must identify the policy's exact attempt and `context-capture:<method_id>`, bind the policy digest in both `hypothesis_set_digest` and `plan_ref`, and require authority. Application and sender ACK are not part of this context-read path. The return records its Encounter ID, payload digest, canonicalization, method, dimension, report digest, and value. The authority event must satisfy the existing `ObservationPath` AUTHORIZED decision contract. The interpreter records `exact-context-scalar-v1` with the same method, dimension, report digest, and scalar value.

The returned and interpreted values are compared by canonical JSON type and value; for example, Boolean `true` is not interchangeable with integer `1`.

## Exact scenario membership

The observed value must exactly match one of the selected policy's declared scenario values. An out-of-set value raises `ContextMeasurementMismatch` and creates no new context assignment. It must be retained as an out-of-model encounter and investigated as a branch-set/model mismatch. It is never coerced to the nearest category, added to the old policy, or silently treated as equivalent.

## Immutable context-analysis revision

On accepted evidence, the bridge:

- finds the exact conformance record selected by the policy;
- carries forward all of that attempt's previous context dimensions;
- replaces only an unknown or not-supplied descriptor for the selected dimension with the exact observed scalar;
- creates a new context assignment bound to the conformance digest;
- creates a measurement manifest containing the policy, prior assignment, ObservationPath digest, return, authority, and interpretation references;
- points the new assignment's `source_ref` to the manifest digest;
- rebuilds the complete context analysis from the original conformance records and the new assignment set.

The prior assignment and prior analysis are retained unchanged. The updated analysis is a new descriptive evidence snapshot, not a VGI Ground revision or a Trial 08 transition-model revision.

A caller can now recompute `build_context_attention_plan` over the updated analysis. The next proposal is therefore selected from the newly observed context and remaining unresolved context cells, rather than reusing the stale policy.

## API

```python
from context_attention import ContextProbeMethod, build_context_attention_plan
from context_measurement import (
    new_context_measurement_path,
    build_context_measurement_record,
    validate_context_measurement_record,
)

policy = build_context_attention_plan(
    context_analysis=context_analysis,
    model_document=trial_08_model,
    probe_id="inspect",
    current_state="state-0",
    methods=methods,
    vgi_api=vgi,
    max_probes=8,
)

path = new_context_measurement_path(
    context_analysis=context_analysis,
    policy_report=policy,
    model_document=trial_08_model,
    vgi_api=vgi,
)

# The executor appends real dispatch/admission/return/authority events.
# After interpreting the returned context scalar, it appends:
path.append(
    "interpreted",
    "context-interpreter",
    evidence_ref="interpretation://context-read-17",
    details={
        "method": "exact-context-scalar-v1",
        "method_id": policy["next_measurement"]["method_id"],
        "dimension": policy["next_measurement"]["dimension"],
        "context_attention_report_digest": policy["report_digest"],
        "context_value": "region-east",
    },
)

measurement = build_context_measurement_record(
    context_analysis=context_analysis,
    policy_report=policy,
    model_document=trial_08_model,
    observation_path=path,
    vgi_api=vgi,
)

validate_context_measurement_record(
    measurement,
    context_analysis=context_analysis,
    policy_report=policy,
    model_document=trial_08_model,
    vgi_api=vgi,
)
next_policy = build_context_attention_plan(
    context_analysis=measurement["updated_context_analysis"],
    model_document=trial_08_model,
    probe_id="inspect",
    current_state="state-0",
    methods=methods,
    vgi_api=vgi,
    max_probes=8,
)
```

The example omits the executor's intermediate lifecycle events for brevity; they are required, not optional. Tests build the full path with synthetic receipts.

## Reproduction and verification

The [focused workflow](../../.github/workflows/context-measurement-evidence.yml) checks the module against the pinned VGI policy planner, validates the JSON Schema, and runs the path-replay, scenario-membership, assignment-revision, and adaptive-replanning tests. The repository-wide [Encounter Envelope workflow](../../.github/workflows/encounter-envelope-tests.yml) also runs the focused tests.

## Evidence boundary

- Replaying an ObservationPath verifies its recorded structure and transition rules, not the truth or availability of external artifacts referenced by its evidence URIs.
- The bridge checks the supplied authority event's declared status and fields. It does not fetch the authority decision artifact, authenticate its signature, or independently establish quorum membership.
- Digests identify the content of supplied paths, manifests, assignments, and analysis snapshots; they do not authenticate actors, sensors, context sources, or authority services.
- The context analysis preserves its original Trial 08 model reference and digest. No transition, intervention-cost, VGI Ground, or active attention policy is modified by recording the measurement.
- A newly computed policy must be built from the updated context analysis. The old policy is stale once its source evidence changes.
- Adaptive selection can induce sample-selection effects. The descriptive analysis does not correct for that selection, unmeasured context, drift, concurrency, or measurement error.
