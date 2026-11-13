# RIV-010: Reference acquisition by downstream decision value

**Status:** finite exact one-reference-step lookahead and evidence-gated RIV-009 handoff, version 0.1.  
**Question:** Which known-standard observation should be acquired when its immediate value is calibration information, but its practical value appears in a later target decision?

## Why RIV-008's immediate objective is not enough

RIV-008 evaluates the expected change in the current Bayes decision loss after one observation. That is appropriate when the observation can change the decision being made now.

A calibration reference is different. The known standard tells us about the session-shared calibration profile C, while the target hypothesis H has not yet been observed. Under RIV-009's independent prior P(H,C)=P(H)P(C), a known-reference likelihood has the form P(r|C,h_ref,sensor). It is independent of the unknown target H. The current marginal decision about H therefore does not change, and RIV-008 correctly reports zero immediate EVSI for this measurement.

That does not imply the reference is worthless. Once target sensor readings arrive, the improved calibration posterior can change their likelihood interpretation and the downstream Bayes decision. RIV-010 values the reference against that later decision.

## One-reference-step lookahead

Inputs are:
- a target-hypothesis prior;
- the current discrete calibration-profile prior and fixed sensor response models;
- a future target sensor schedule;
- candidate known-reference actions, each with a sensor ID, known standard hypothesis, standard reference and digest, and exact positive cost.

For each candidate reference a, RIV-010 enumerates the two reference signals r in {A,B}:

\[
P(r\mid a)=\sum_c P(c)P(r\mid c,a),
\qquad
P(c\mid r,a)=\frac{P(c)P(r\mid c,a)}{P(r\mid a)}.
\]

It passes each updated calibration prior into RIV-007's target filter and evaluates the expected target MAP accuracy after the complete declared target sensor schedule:

\[
V(a)=\sum_r P(r\mid a)\,\operatorname{Acc}_{target}(P(C\mid r,a))
-\operatorname{Acc}_{target}(P(C)).
\]

The value is exact expected downstream decision-accuracy gain. Candidates are ranked by V(a)/cost(a), then absolute value, lower cost, and candidate ID. A cost/target-risk Pareto frontier is retained. If no positive-value action is eligible, no candidate is selected.

This is a one-reference-step lookahead followed by a fixed target schedule. It is not a multi-reference dynamic programme. After an admitted reading updates the calibration posterior, the planner can be rerun with the new prior; a longer-horizon policy remains future work.

## Exact fixture

The fixture uses the RIV-007 two-profile, three-sensor calibration model, an equal target-hypothesis prior, four candidate known-standard actions, and declared cost 1/2 for each candidate.

The baseline expected target MAP accuracy with no new reference is:

\[
\frac{153}{200}=0.765.
\]

For a reference standard A measured by sensor-3:

| Reference signal | Predictive probability | Posterior profile-1 | Posterior profile-2 | Future target MAP accuracy |
|---|---:|---:|---:|---:|
| A | 1/2 | 9/10 | 1/10 | 4507/5000 |
| B | 1/2 | 1/10 | 9/10 | 4031/5000 |

Its expected target MAP accuracy is:

\[
\frac12\left(\frac{4507}{5000}+\frac{4031}{5000}\right)
=\frac{4269}{5000}.
\]

Therefore the expected downstream value is:

\[
\frac{4269}{5000}-\frac{153}{200}
=\frac{111}{1250},
\]

and value per declared cost 1/2 is 111/625.

The other candidate values are also computed exactly. For this fixture, sensor-3 with standard A is selected.

The RIV-008 myopic comparator reports zero immediate EVSI for all four candidates because each known-reference likelihood depends on the calibration profile but not on the unknown target hypothesis. RIV-010's nonzero value is not a correction to RIV-008; it is a different horizon with the future target observations explicitly included.

## Evidence-gated execution and RIV-009 handoff

The function new_reference_acquisition_observation_path() creates a planned-only ObservationPath bound to the RIV-010 report digest and selected reference candidate. It does not dispatch a sensor.

A reference result is accepted only when the path independently reconstructs through exactly:

planned → dispatched → admitted → returned → evidence_authorized → interpreted

The returned and interpreted events must agree on candidate ID, sensor ID, known standard, standard digest, report digest, and signal. The authority event must satisfy the existing ObservationPath AUTHORIZED structure. Out-of-plan or mismatched readings are rejected.

build_reference_execution_record() creates an RIV-009 reference-observation row directly from the authorized return, then calls and validates RIV-009's existing builder. RIV-009 remains responsible for the exact calibration-posterior update and target filtering. The resulting record binds the ObservationPath, return payload, authority evidence, reference row, RIV-009 report, and content digests.

The example uses a fixture path with synthetic event references to demonstrate the contract. It is not a real dispatch, sensor reading, verified standard, or authenticated authority decision. The adapter independently reconstructs path structure; it does not fetch or authenticate external evidence, signatures, or the physical standard.

## Reproduction

From the repository root, run:

    python -m py_compile experiments/reference-calibrated-evidence/reference_acquisition_lookahead.py
    python -m unittest discover -s experiments/reference-calibrated-evidence -p 'test_reference_acquisition_lookahead.py' -v
    python experiments/reference-calibrated-evidence/reference_acquisition_example.py

The workflow validates both Draft 2020-12 schemas, compiles the adapter/example and upstream RIV-007/RIV-008/RIV-009 modules, runs the exact tests, and executes the fixture.

## Evidence scope and limitations

- Calibration profiles and response probabilities are supplied, finite, discrete, and fixed over the reference-plus-target session.
- The known standard hypothesis and its custody are supplied assumptions, not authenticated facts.
- The reference sensor must also occur in the target sensor schedule in this version, matching RIV-009's current input contract.
- Reference and target observations are assumed conditionally independent given the same calibration profile and their supplied known/unknown hypothesis values.
- Costs are exact caller-declared values in one common unit. They are not measured latency, dispatch, receiver admission, authority, interpretation, transport, or energy costs.
- The planner's exact expected value is conditional on the supplied likelihoods, priors, target schedule, and decision rule. It is not measured sensor performance.
- The selected path's authority fields are structurally checked through ObservationPath reconstruction, but the external authority actor, signer, policy and source membership are not authenticated by this module.
- Digests provide content identity and reproducibility, not signatures or proof of physical provenance.
- An authorized reference update changes the calibration posterior report; it does not revise the sensor likelihood model, source Ground, or physical calibration hardware.
- The current horizon is one candidate reference followed by one fixed target schedule. Sequential multi-reference control, unknown reference labels, continuous calibration, calibration drift, and robust likelihood uncertainty are not included.

## Files

- reference_acquisition_lookahead.py — exact reference lookahead, RIV-008 myopic comparator, RIV-007 downstream target scoring, planned ObservationPath, and RIV-009 authorized reference handoff.
- test_reference_acquisition_lookahead.py — exact scores, branch posteriors, zero-myopic/nonzero-lookahead comparison, budget behavior, path authority, metadata mismatch, and report tamper tests.
- reference_acquisition_example.py — reproducible exact planner and fixture execution.
- reference-acquisition-lookahead.schema.json — planning report schema.
- reference-acquisition-execution.schema.json — authorized execution record schema.
