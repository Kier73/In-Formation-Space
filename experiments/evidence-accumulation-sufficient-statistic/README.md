# RIV-004: Evidence accumulation as a sufficient statistic

**Status:** finite exact experiment, version 0.1.  
**Question:** When can an observer discard the order and details of a noisy observation history while preserving the best decision it can make?

## Relationship to RIV-001 through RIV-003

- RIV-001 measured the task-relative value of distinctions in a current state representation.
- RIV-002 showed that an earlier observation can remain useful after distinct hidden states share the same current observation.
- RIV-003 synthesized a small deterministic finite-state controller that retains that distinction.
- RIV-004 changes the observation model: signals are noisy. It asks whether an observer needs to retain the entire sequence, or whether an exact evidence statistic is enough for a specified inference task.

The result is a classical statistical sufficiency property, not a newly discovered theorem. The Neyman–Fisher factorization theorem states that a statistic is sufficient when the parameter-dependent part of the data likelihood depends on the sample only through that statistic. See the University of Texas likelihood and sufficiency notes (https://web.ma.utexas.edu/users/gordanz/notes/likelihood_color.pdf), the Berkeley STAT 135 Spring 2026 lecture (https://stat135.berkeley.edu/spring-2026/lectures/lecture-18.html), and Purdue's exponential-family notes (https://www.stat.purdue.edu/~dasgupta/expfamily.pdf).

## Model

A hidden hypothesis H remains fixed over a window and is either A or B. The observer receives exactly n signals, each in {A, B}. Conditional on H, signals are independent and identically distributed:

\[
P(X_i=A\mid H=A)=\alpha,\qquad
P(X_i=A\mid H=B)=\beta.
\]

The prior is \(P(H=A)=\pi\). Every probability is an exact rational supplied by the experimenter. The model permits asymmetric channels (\(\beta\) need not equal \(1-\alpha\)).

For any ordered history \(x=(x_1,\ldots,x_n)\), let k be the number of A signals. Conditional independence and identical sensor probabilities give:

\[
P(x\mid H=A)=\alpha^k(1-\alpha)^{n-k},
\]
\[
P(x\mid H=B)=\beta^k(1-\beta)^{n-k}.
\]

The likelihood therefore depends on the ordered history only through \(k\). By Bayes' rule, histories with the same count have the same posterior and the same maximum-a-posteriori (MAP) decision. The count of A observations is a sufficient statistic for this fixed binary hypothesis family and observation process.

For each count k, the implementation stores both exact joint masses:

\[
m_A(k)=\pi\alpha^k(1-\alpha)^{n-k},
\]
\[
m_B(k)=(1-\pi)\beta^k(1-\beta)^{n-k}.
\]

It chooses A when \(m_A(k)\ge m_B(k)\), B otherwise, and marks a count class unreachable when both masses are zero. Its exact MAP accuracy is:

\[
\sum_{k=0}^{n}\binom{n}{k}\max\{m_A(k),m_B(k)\}.
\]

The binomial coefficient accounts for every ordered history having that count.

## The accumulator

The implementation constructs a deterministic transducer with states \(k\in\{0,\ldots,n\}\), initialized at 0:

- On signal A, increment k.
- On signal B, leave k unchanged.
- On END after exactly n signals, emit the MAP decision associated with k.

The stream's END marker establishes the fixed observation boundary; the accumulator does not need a second step counter. For a fixed n, the machine has n+1 count states, compared with \(2^n\) possible ordered histories. This is a state-cardinality comparison for the declared task and input contract, not a byte-level benchmark of a deployed implementation.

The report also enumerates every raw observation string (up to an explicit cap), recalculates its joint masses independently, and checks that its MAP decision matches the count-class decision. It compares raw-history accuracy with the count-statistic formula exactly.

## Example

Take equal prior odds, five observations, and a symmetric sensor that is correct with probability 3/4:

\[
\pi=\frac12,\quad \alpha=\frac34,\quad \beta=\frac14,\quad n=5.
\]

The resulting exact MAP accuracy is \(459/512\), approximately 89.65%. The observer need not retain all 32 ordered signal strings; it can retain one of six count states (0 through 5). The raw-history enumeration and count accumulator produce exactly the same MAP decisions and accuracy. The count statistic therefore reduces the number of represented history classes from 32 to 6 for this model, while preserving the optimal decision.

This does not mean all six states are equally likely, nor that the same statistic is sufficient for every sensor, temporal process, or task.

## Reproduction

From the repository root:

    python -m py_compile experiments/evidence-accumulation-sufficient-statistic/evidence_accumulation.py experiments/evidence-accumulation-sufficient-statistic/example.py
    python -m unittest discover -s experiments/evidence-accumulation-sufficient-statistic -p 'test_*.py' -v
    python experiments/evidence-accumulation-sufficient-statistic/example.py

The implementation uses only the Python standard library. Probability inputs accept integers, rational strings, or numerator/denominator objects; floats and booleans are rejected. The finite raw-history check fails closed when the number of possible strings exceeds the configured maximum. The report validator rebuilds the likelihood ledger, MAP decisions, accumulator, and raw-history comparison from the retained inputs. SHA-256 is a content-integrity identifier, not an authentication signature.

## Evidence scope and limitations

- The hidden hypothesis is fixed across the observation window.
- Observations are conditionally independent and identically distributed given the hidden hypothesis. Correlated signals, drifting environments, changing sensor channels, and intervention-dependent observations require a richer model and may need a different sufficient statistic.
- The task is binary MAP classification after a fixed number of observations. Sequential stopping, utility-sensitive decisions, parameter estimation, and multi-class hypotheses are not implemented here.
- The statistic is sufficient for the declared binary iid observation family and decision problem. It is not a universal representation of meaning or information.
- State counts compare possible raw histories with count-accumulator states. They do not measure implementation bytes, update latency, energy, or a physical sensor's reliability.
- Exact full-history verification is exponential and bounded. The count-based likelihood calculation is polynomial in n, but the verification cap is not an approximation parameter.
- A verified report establishes equivalence for the supplied finite model, not that a real observer's sensor obeys the model.

## Files

- evidence_accumulation.py — exact likelihood calculation, MAP decision ledger, accumulator, raw-history equivalence check, and report reconstruction.
- test_evidence_accumulation.py — ten tests for exact accuracy, asymmetric channels, uninformative/perfect sensors, unreachable count classes, bounds, and tamper rejection.
- example.py — runnable five-observation experiment.
- README.md — statistical derivation, controller, evidence, and scope.
