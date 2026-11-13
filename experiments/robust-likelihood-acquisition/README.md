# RIV-015: Robust reference acquisition under likelihood ambiguity

**Status:** finite exact minimax decision experiment, version 0.1.  
**Question:** When several sensor-response models remain plausible but there is no justified probability distribution over those models, which measurement and outcome-to-decision rule have the best worst-case expected loss?

## Relationship to RIV-008 through RIV-014

- **RIV-008** ranks context readers by one-step expected Bayes decision-risk reduction under one supplied likelihood model.
- **RIV-009** updates a session-shared calibration posterior from known standards using supplied response likelihoods.
- **RIV-010** evaluates a reference by its downstream target-decision value.
- **RIV-011** optimizes an adaptive finite-horizon reference policy.
- **RIV-012** executes one policy edge only through an authorized ObservationPath.
- **RIV-013** reconstructs inline Encounter Envelopes, source payload digests and Authority Lineage consistency.
- **RIV-014** adds root-authenticated reviewer signatures over the integrity bundle, with an explicitly limited attestation scope.

These layers improve decision planning and evidence provenance, but they do not establish that a supplied sensor-response likelihood table is correct. A signed review can authenticate who approved a bundle relative to a pinned trust root; it cannot turn an uncertain physical response model into a known probability law.

RIV-015 isolates that remaining assumption. It takes a finite set of plausible candidate-sensor likelihood models and assigns **no probabilities** to model identity. For each sensor it enumerates one deterministic outcome-to-action rule that must be used across every scenario, then selects the rule minimizing maximum expected loss. This is a robust decision problem, not Bayesian model averaging.

## Model and input contract

The observer starts from one exact joint posterior over a binary target hypothesis H and a finite context state Z:

[
b(h,z)=P(H=h,Z=zmid 	ext{current evidence}).
]

The belief is content-bound to an upstream source reference and report digest, using the same portable joint-belief contract as RIV-008. Its probabilities must sum exactly to one.

A candidate sensor declares:
- a unique identifier and context dimension;
- an exact positive cost in a common caller-declared unit;
- a finite set of outcome labels.

The ambiguity set contains one or more named model scenarios. Every scenario must define a complete conditional likelihood table for **every candidate** and **every outcome**:

[
P_m(omid h,z,s),
]

where m is the scenario, s the candidate sensor, and each state's outcome probabilities sum exactly to one. Scenarios are complete alternatives for the candidate set; none is weighted or treated as a nominal truth.

For a given candidate, a policy is one deterministic mapping from its outcomes to the available decisions A or B:

[
delta:mathcal{O}_sightarrow{A,B}.
]

Crucially, (delta) is shared across all model scenarios. The decision maker is not told which likelihood scenario is true after the observation.

## Exact robust objective

For a loss matrix L and a candidate policy (delta), expected loss under scenario m is:

[
R_m(delta,s)=
sum_{h,z}b(h,z)
sum_{oinmathcal{O}_s}
P_m(omid h,z,s)L(delta(o),h).
]

The robust post-measurement risk for sensor s is:

[
R_{mathrm{robust}}(s)=
min_{delta:mathcal{O}_s	o{A,B}}
max_{minmathcal{M}}R_m(delta,s).
]

The current no-measurement decision chooses the best constant action from the same joint belief. Its risk is (R_0). Since a constant policy is also available after every candidate outcome, it is always possible to ignore the measurement. Therefore:

[
operatorname{RobustValue}(s)=R_0-R_{mathrm{robust}}(s)geq0.
]

Candidates are ranked by robust value divided by exact cost. A cost/risk Pareto frontier is retained. If no eligible candidate has strictly positive worst-case value, the selected action is **stop**.

For each candidate the report also includes:
- all outcome-to-action policies enumerated;
- expected decision loss under each model scenario;
- each scenario's oracle risk, which assumes its model identity is known;
- the chosen shared policy's regret against those scenario-oracle risks;
- the worst-case scenario IDs and exact cost-normalized robust value.

The scenario-oracle values are diagnostics, not implementable policies under unresolved model ambiguity. The tie-break first minimizes worst-case expected loss, then worst-case regret to scenario-oracle policies, then uses lexical A/B mapping. Candidate-level ties prefer higher robust value, lower cost, and lexical sensor ID.

## Exact fixture

The example begins with equal prior probability on H=A and H=B, so the current zero-one Bayes risk is (1/2). Four readers are compared under two unweighted possible calibration scenarios.

| Candidate | Cost | Scenario 1 (P(yesmid A),P(yesmid B)) | Scenario 2 (P(yesmid A),P(yesmid B)) |
|---|---:|---:|---:|
| robust-reader | 1 | 9/10, 1/10 | 7/10, 3/10 |
| cheap-reader | 1/4 | 13/20, 7/20 | 13/20, 7/20 |
| perfect-audit | 2 | 1, 0 | 1, 0 |
| sign-flip-reader | 1/10 | 99/100, 1/100 | 1/100, 99/100 |

Under the default zero-one loss:

| Candidate | Chosen robust policy | Worst-case risk | Robust value | Value / cost |
|---|---|---:|---:|---:|
| robust-reader | yes→A, no→B | 3/10 | 1/5 | 1/5 |
| cheap-reader | yes→A, no→B | 7/20 | 3/20 | 3/5 |
| perfect-audit | yes→A, no→B | 0 | 1/2 | 1/4 |
| sign-flip-reader | constant action | 1/2 | 0 | 0 |

The cheap reader is selected by value per cost. The perfect audit has the largest absolute robust value, but its cost is higher. The sign-flip reader is highly informative if its scenario is known, but the response polarity reverses across the ambiguity set. No one outcome-to-action policy can exploit both models: the robust rule falls back to the constant baseline action and the sensor has zero robust value.

This is the key difference from averaging scenario-specific EVSI values. No probability is available to justify such an average, and no single outcome policy is allowed to know which model generated the signal.

## API

```python
from robust_likelihood_acquisition import (
    build_joint_belief_document,
    build_report,
    validate_report,
)

belief = build_joint_belief_document(
    joint_posterior=upstream_joint_posterior,
    source_ref="artifact://upstream-joint-filter",
    source_report_digest=upstream_report_digest,
)

report = build_report(
    joint_belief=belief,
    candidate_sensors=candidates,
    model_scenarios=unweighted_likelihood_scenarios,
    loss_matrix=None,  # default zero-one classification loss
    cost_budget="1/2",
)
validate_report(report)
```

The report retains the full belief, finite ambiguity set, every candidate policy, every scenario loss, scenario-oracle diagnostics, Pareto frontier, and selected proposal. The published [JSON Schema](robust-likelihood-acquisition.schema.json) defines its portable shape. Validation independently reconstructs the full policy enumeration and decision values from the retained inputs.

## Evidence scope and limitations

- The ambiguity set is caller-supplied and finite. The actual response model may lie outside it; the robust guarantee is only over the declared set.
- No probability is assigned to model identity. The report is a worst-case analysis, not Bayesian averaging or a posterior over model scenarios.
- Each sensor's outcome-to-action mapping must be shared across every model scenario. It cannot condition on hidden model identity.
- The scenario-oracle comparator assumes the model identity is known. It is only a lower-risk diagnostic.
- The target/context prior and loss matrix are fixed inputs. Uncertainty in those quantities is not included in this version.
- Only binary decisions A/B and deterministic outcome policies are supported. Randomized policies, multi-action tasks, continuous outcomes, and large policy spaces are not included.
- The finite action enumeration is capped. The implementation fails closed when candidate outcome or policy/scenario limits are exceeded.
- Costs are exact caller-declared rational values in one unit. They are not measured latency, transport, dispatch, receiver admission, authority, energy, or operation-span cost.
- The measurement is assumed passive and does not change H or Z while being acquired.
- Model provenance and signed review may establish where a likelihood set came from or who reviewed it; neither establishes that the true physical response model is included in the set.
- This is a proposal only. No sensor is dispatched, no ObservationPath is advanced, and no joint belief, calibration model, or Ground is revised.
- Digests provide content identity and deterministic reconstruction, not source authentication or physical measurement truth.

## Reproduction

From the repository root:

    python -m py_compile experiments/robust-likelihood-acquisition/robust_likelihood_acquisition.py
    python -m unittest discover -s experiments/robust-likelihood-acquisition -p 'test_*.py' -v
    python experiments/robust-likelihood-acquisition/example.py

The implementation uses only the Python standard library and exact `Fraction` arithmetic. Probabilities, losses, and costs are not sampled or converted to floating point.

## Next discriminating step

The next question is whether the ambiguity set itself can be constrained by authenticated reference observations without pretending that finite calibration evidence eliminates model misspecification. A future bridge could update the admissible likelihood set by explicit reference outcomes, retain excluded-but-not-disproved alternatives, and compare robust plans before and after that evidence. That operation must preserve the original ambiguity set and its reason for exclusion as an append-only revision.
