# RIV-005: Heterogeneous evidence accumulation

**Status:** finite exact experiment, version 0.1.  
**Question:** When sensor reliability varies, what compact state preserves the evidence needed for an optimal decision?

## Relationship to RIV-004

RIV-004 demonstrated that the number of positive signals is sufficient for MAP classification when every observation uses the same binary sensor channel and observations are conditionally iid. RIV-005 generalizes the observation process: each position may have a different, known sensor reliability.

The key improvement is to update the posterior itself after each signal. This is the standard Bayesian filtering recursion for a fixed hidden hypothesis with conditionally independent observations. The experiment does not claim a new statistical theorem. It makes the exact update transitions, history equivalence classes, and failure of the unweighted count visible in one reproducible model.

## Model and posterior accumulator

The hidden hypothesis is fixed and binary, H in {A, B}. At position i, sensor i emits A or B with known probabilities:

\[
\alpha_i=P(X_i=A\mid H=A),\qquad
\beta_i=P(X_i=A\mid H=B).
\]

Signals are independent conditional on H, but alpha and beta may vary by position. The observer begins with prior \(p=P(H=A)\). On observing signal s from sensor i, it updates:

\[
p'=\frac{p\,P(s\mid H=A,i)}
{p\,P(s\mid H=A,i)+(1-p)\,P(s\mid H=B,i)}.
\]

If the denominator is zero, that observation is impossible under both hypotheses at the current posterior and the transition is marked unreachable.

The posterior is sufficient for future Bayesian updates when the future sensor schedule is known: the next update requires only the current posterior and the next sensor's likelihoods. The implementation builds the reachable posterior states at every layer and stores an exact transition table for each sensor event.

## Why a simple count fails

The example uses two strong sensors and two weaker sensors, with equal prior odds:

- Strong sensors: \(P(A\mid H=A)=9/10\), \(P(A\mid H=B)=1/10\).
- Weak sensors: \(P(A\mid H=A)=3/5\), \(P(A\mid H=B)=2/5\).

Consider two histories with the same total count of two A signals:

- AABB: both strong sensors signal A and both weak sensors signal B. Posterior \(P(H=A\mid AABB)=36/37\), so MAP chooses A.
- BBAA: both strong sensors signal B and both weak sensors signal A. Posterior \(P(H=A\mid BBAA)=1/37\), so MAP chooses B.

The total count is identical, but the evidence is not. A single unweighted count cannot preserve even the MAP decision in this case.

The posterior accumulator groups all 16 ordered histories into 9 terminal posterior states. Across the five layers (before the first signal and after each of four signals), its state counts are [1, 2, 3, 6, 9]: 21 layered posterior states instead of 31 nodes in the full raw-history prefix tree. The fixed sensor schedule is supplied with each signal; stage-specific update rules are therefore explicit.

## Reproduction

From the repository root:

    python -m py_compile experiments/heterogeneous-evidence-accumulator/heterogeneous_evidence.py experiments/heterogeneous-evidence-accumulator/example.py
    python -m unittest discover -s experiments/heterogeneous-evidence-accumulator -p 'test_*.py' -v
    python experiments/heterogeneous-evidence-accumulator/example.py

The implementation uses only the Python standard library and exact rational arithmetic. It enumerates every ordered history up to max_histories, compares the result with sequential posterior updates, and rejects a report that cannot be reconstructed from its retained inputs. SHA-256 is a content-integrity identifier, not an authentication signature.

## Evidence scope and limitations

- The hidden hypothesis is fixed over the sensor schedule.
- Observations are conditionally independent given the hidden hypothesis. Sensor response probabilities may vary by position, but correlated signals, sensor drift conditioned on hidden intermediate state, and intervention-dependent observations are not modeled.
- Sensor identity and its likelihood model are supplied with each signal or are known from the fixed schedule.
- The posterior is sufficient for future Bayesian updates under that known schedule. It may still have as many as \(2^n\) distinct values for n signals; sufficiency does not guarantee compression.
- The example happens to merge 16 raw histories into 9 posterior states. This ratio is model-specific.
- The unweighted total count is not sufficient in the example; the posterior is. Other sensor schedules may admit smaller grouped-count or likelihood-ratio statistics.
- The task is binary MAP classification. Multi-class hypotheses, unknown sensor parameters, sequential stopping, utility-sensitive actions, and physically measured sensor behavior are not included.
- Exact exhaustive verification is exponential and bounded. The limit fails closed; it is not an approximation setting.
- A verified report establishes the supplied finite probabilistic model, not that a real observer or sensor system obeys its assumptions.

## Files

- heterogeneous_evidence.py — posterior updates, reachable layered states, complete history enumeration, and report reconstruction.
- test_heterogeneous_evidence.py — twelve tests for weighted evidence, count failure, exact posterior merging, identical-sensor reduction, impossible events, and tamper rejection.
- example.py — runnable four-sensor schedule.
- README.md — model, update equation, example, evidence scope, and limitations.


## Follow-on experiment

[RIV-006: Context-switching evidence accumulation](../context-switching-evidence-accumulator/README.md) relaxes the conditional-iid structure further by adding a persistent hidden Markov operating regime. RIV-005's scalar hypothesis posterior remains sufficient when the known sensor schedule is conditionally independent given H. RIV-006 shows why a joint posterior over H and the next regime is needed when hidden context persists and creates hypothesis-context correlation.
