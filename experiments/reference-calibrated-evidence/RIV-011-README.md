# RIV-011: Finite-horizon reference acquisition

**Status:** finite exact dynamic programme, version 0.1.  
**Question:** When multiple known-standard readings can be acquired, how does an adaptive finite-horizon policy compare with repeatedly applying RIV-010's one-step value-per-cost rule?

## Relationship to RIV-008 through RIV-010

- RIV-008 selects one immediate context observation by expected current Bayes decision-loss reduction per cost.
- RIV-009 turns known-reference evidence into an updated session-shared calibration posterior and reuses RIV-007 for target inference.
- RIV-010 selects one reference measurement by its expected downstream target-decision value before a fixed target schedule.
- RIV-011 extends that final objective across several possible reference observations. It can stop, choose another reference, or choose a different next reference after different observed signals.

The greedy comparator re-applies the RIV-010 one-reference-step value-per-cost rule after each signal. The dynamic programme instead compares complete bounded policy trees under the same pathwise cost budget.

## Finite-horizon recursion

A policy state consists of:
- the exact posterior distribution over the fixed calibration profiles;
- the number of reference acquisitions remaining;
- the exact remaining per-path cost budget.

At every state, stopping is an available action. For candidate reference a and possible signal r, the calibration posterior updates as:

\[
P(c\mid r,a)=
\frac{P(c)P(r\mid c,a)}
{\sum_{c'}P(c')P(r\mid c',a)}.
\]

Let T(q) be the exact target MAP accuracy under calibration posterior q, computed by RIV-007 across the complete declared target sensor schedule. The finite-horizon value is:

\[
V(q,n,B)=\max\left\{
T(q),\
\max_{a:\,cost(a)\leq B}
\sum_r P(r\mid q,a)V(q_{a,r},n-1,B-cost(a))
\right\}.
\]

All probabilities, costs and value comparisons use exact rational arithmetic. The budget is pathwise: no realized reference sequence may exceed it. Expected acquisition cost is reported separately. A memoized state cap fails closed if the requested exact policy exceeds the declared search budget.

## Exact adaptive counterexample

The fixture has two session-shared calibration profiles, three future target sensors, six candidate known-standard readings, a three-reference horizon, and a pathwise cost budget of 3/2.

The baseline target MAP accuracy is:

\[
\frac{623}{800}=0.77875.
\]

The finite-horizon policy achieves:

\[
\operatorname{Acc}_{DP}=\frac{5347}{6400}=0.83546875,
\qquad
E[cost_{DP}]=\frac{549}{400}=1.3725.
\]

Repeated one-step RIV-010 re-selection achieves:

\[
\operatorname{Acc}_{greedy}=\frac{13351}{16000}=0.8344375,
\qquad
E[cost_{greedy}]=\frac65=1.2.
\]

The finite-horizon policy's advantage is:

\[
\frac{5347}{6400}-\frac{13351}{16000}
=\frac{33}{32000}.
\]

Both obey the same 3/2 per-path budget and the same three-step horizon. The dynamic programme's expected cost is higher because it spends more of the available budget where later outcomes make that worthwhile.

More importantly, the policy is adaptive. Its first reference action is sensor-0 against standard A. If the first signal is A, its next action is sensor-1 against standard A. If the first signal is B, its next action is sensor-0 against standard A. The next action is therefore chosen from the updated calibration posterior, not fixed in advance.

This is a constructed finite-model counterexample to treating repeated greedy re-selection as generally optimal. It is not a claim that dynamic programming always produces a practical advantage; for other models, the greedy policy can coincide with the optimum.

## Reproduction

From the repository root:

    python -m py_compile experiments/reference-calibrated-evidence/finite_horizon_reference_policy.py
    python -m unittest discover -s experiments/reference-calibrated-evidence -p 'test_finite_horizon_reference_policy.py' -v
    python experiments/reference-calibrated-evidence/finite_horizon_reference_policy_example.py

The workflow also validates the JSON Schema and compiles the RIV-007, RIV-010, and RIV-011 modules. The test suite independently enumerates the small finite policy tree without memoization and compares it with the dynamic-programming result.

## Interpretation limits

- The optimizer is exact only for the finite supplied calibration family, reference action set, fixed target schedule, horizon and pathwise budget.
- The target objective is expected MAP accuracy. Different decision losses or downstream utility functions can change the optimal policy.
- Calibration remains discrete and fixed across the reference and target phases. Drift and residual dependence are not modeled.
- Repeated readings are conditionally independent given the shared calibration profile and known standard. Correlated readout errors or shared sample artifacts are not represented.
- Standards, response likelihoods and costs are supplied assumptions, not authenticated facts or measured sensor performance.
- Costs are declared rational values, not measured dispatch, receiver admission, transport, authority, interpretation, latency or energy.
- The module produces a policy tree only. It does not dispatch measurements, create ObservationPaths, authenticate authority receipts, or update a live RIV-009 report.
- The state cap fails closed; no approximate policy is silently substituted.

## Files

- finite_horizon_reference_policy.py — exact memoized dynamic programme and repeated RIV-010 greedy comparator.
- test_finite_horizon_reference_policy.py — exact counterexample, branch adaptation, path budget, brute-force enumeration, limits and tamper tests.
- finite_horizon_reference_policy_example.py — reproducible exact policy comparison.
- finite-horizon-reference-policy.schema.json — recursive policy/report schema.
