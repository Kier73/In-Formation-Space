# RIV-008 execution: Decision-value context measurement evidence

**Status:** finite evidence-gated execution adapter  
**Planner:** [RIV-008 decision-value acquisition](README.md)  
**Lifecycle:** [Observation Path](../../bridges/observation-path/README.md)

## Planning is not observation

RIV-008 computes the expected value of candidate context readers from a joint belief, likelihoods, decision loss, and caller-supplied exact costs. The selected sensor is a proposal. This adapter provides the separate execution/evidence boundary:

```text
joint belief + candidate models
    -> expected decision-value report
    -> planned ObservationPath
    -> dispatch
    -> receiver admission
    -> returned Encounter Envelope
    -> explicit AUTHORIZED decision
    -> exact outcome interpretation
    -> Bayes conditioning under selected likelihood model
    -> new joint-belief snapshot
```

`new_acquisition_observation_path(...)` validates and reconstructs the decision-value report, selects its one eligible candidate, and creates a planned-only ObservationPath. It does not dispatch a measurement. The executor must append the actual dispatch, admission, return, authority and interpretation events.

## Required evidence path

A record is accepted only after independent replay through the existing `ObservationPath` contract with exactly these stages:

1. `planned`
2. `dispatched`
3. `admitted`
4. `returned`
5. `evidence_authorized`
6. `interpreted`

The ObservationIntent binds the report digest through both `hypothesis_set_digest` and `plan_ref`, names the selected sensor, and requires authority. Application and sender ACK are not part of this passive context-reading operation.

The returned Encounter reference must include its encounter ID, payload digest, canonicalization, exact selected sensor and dimension, decision-value report digest, and observed outcome. The interpreted event repeats the selected sensor, dimension, report digest, and outcome with method `exact-decision-value-context-outcome-v1`. The returned and interpreted outcomes must match exactly, including JSON type: `true` is not integer `1`.

The existing ObservationPath validates the declared AUTHORIZED decision shape, quorum field, source lists and representative source. This adapter checks those fields through lifecycle replay, but it does not fetch or authenticate the external decision artifact or establish the truth of its membership claims.

## Exact Bayesian update

The observed outcome must exactly match a declared outcome for the selected candidate. For an outcome (o), the adapter calculates

[
P(omid b)=sum_{h,z}b(h,z)P(omid h,z)
]

and, if this predictive probability is positive,

[
b_o(h,z)=rac{b(h,z)P(omid h,z)}{P(omid b)}.
]

Two cases are rejected without creating a posterior revision:

- the outcome is not present in the selected candidate's declared outcome set;
- the outcome is declared, but has zero predictive probability under the supplied joint belief.

These are model mismatches. The adapter does not coerce the result, add an undeclared likelihood, infer a nearest category, or revise the source model.

A valid update creates a new joint-belief document with exact normalized rational probabilities. Its `source_ref` points to the measurement-manifest digest, and its source report digest points to the decision-value report used for planning. The original decision-value report and prior joint belief remain embedded unchanged in the measurement record.

## Expected value versus realized branch

The decision-value report's EVSI is an expectation over *all* declared outcomes. The execution record is for one realized outcome only. It therefore also computes

[
R^*(b_o)-R^*(b),
]

the realized Bayes decision-risk change for the actual branch, under the same decision-loss matrix.

This realized change can be positive or negative. A measurement can make the posterior decision risk worse for one particular outcome while having non-negative expected value before execution. Expected value is not a guarantee that every realized observation improves a decision.

## API

```python
from acquisition_execution import (
    new_acquisition_observation_path,
    build_acquisition_measurement_record,
    validate_acquisition_measurement_record,
)

path = new_acquisition_observation_path(
    decision_value_report=decision_value_report,
    attempt_id="context-read-001",
)

# The executor records real dispatch, admission, return and AUTHORIZED events.
# After interpreting the returned value, append the final event:
path.append(
    "interpreted",
    "context-interpreter",
    evidence_ref="interpretation://context-read-001",
    details={
        "method": "exact-decision-value-context-outcome-v1",
        "sensor_id": decision_value_report["selection"]["selected_sensor_id"],
        "dimension": selected_candidate["dimension"],
        "decision_value_report_digest": decision_value_report["report_digest"],
        "observed_outcome": "good",
    },
)

measurement = build_acquisition_measurement_record(
    decision_value_report=decision_value_report,
    observation_path=path,
)
validate_acquisition_measurement_record(measurement)
next_belief = measurement["updated_joint_belief"]
```

The example omits the intermediate events for brevity; all five post-plan events are required. Tests use synthetic receipt references and do not dispatch to a physical sensor.

## Reproduction

The [focused RIV-008 workflow](../../.github/workflows/decision-value-context-acquisition.yml) compiles the adapter, validates both RIV-008 schemas, and runs tests for the value calculations and the evidence-gated execution path.

## Evidence boundary

- Replaying an ObservationPath checks its serialized lifecycle against the repository's transition rules. It does not establish that external URIs resolve to authentic artifacts.
- The authority event's structure is validated by the existing ObservationPath. The adapter does not cryptographically authenticate the authority service, quorum members, sensors, or interpreter.
- Digests bind supplied values and record contents; they are not digital signatures or external source authentication.
- Posterior updating is exact relative to the supplied prior joint belief and selected outcome likelihoods. It does not prove that either is the true physical model.
- The candidate sensor is assumed passive: reading context does not itself change the hidden hypothesis or context while the sample is acquired.
- The adapter creates a new belief snapshot only. It does not modify an E-CPU Ground, transition model, likelihood model, intervention-cost model, or active VGI attention policy.
- A model mismatch is preserved as a rejected update; expanding the candidate model requires a separate review and immutable model revision.
