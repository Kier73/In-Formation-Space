# RIV-007: Calibration-aware joint evidence accumulation

**Status:** finite exact experiment, version 0.1.  
**Question:** When calibration uncertainty is shared across a session, what belief state must an observer retain to continue making exact Bayesian updates?

## Relationship to RIV-004 and RIV-005

- RIV-004 showed that a count is sufficient for a fixed binary hypothesis and repeated conditionally iid observations from one known channel.
- RIV-005 allowed position-specific, non-identical sensor channels while keeping each channel's parameters known.
- RIV-006 models a context regime that changes as a Markov process. RIV-007 instead makes the calibration profile uncertain but fixed for a complete observation session. The two latent-context contracts are complementary, not interchangeable.

The calibration state is a latent variable, not a new independent draw at every reading. Signals are conditionally independent given both the hidden hypothesis and the shared calibration state. Once the calibration variable is marginalized out, signals can be dependent conditional on the hidden hypothesis alone.

This distinction is consistent with sensor-calibration research that treats calibration parameters as uncertain latent processes and models the dependencies induced by shared or colocated sensor observations. Smith et al. model calibration functions using Bayesian priors over slowly varying parameters and report posterior dependencies between calibration processes (Journal of the Royal Statistical Society: Series C, 2023: https://doi.org/10.1093/jrsssc/qlad075). Work on sensor-network metrology also emphasizes that common calibration references, shared environmental conditions, and repeated readings can induce correlated measurement errors (Sensors, 2025: https://www.mdpi.com/2673-8244/5/1/3). Those studies use richer continuous models; RIV-007 is a small discrete finite-state analogue, not a reproduction of their methods or data.

## Model

The hidden hypothesis is H in {A, B}, with a supplied prior. A calibration profile C is drawn once at the beginning of the session, independently of H, according to a supplied discrete prior. Each profile specifies a binary observation channel for each scheduled sensor type.

For sensor i under calibration profile c:

\[
\alpha_{i,c}=P(X_i=A\mid H=A,C=c),\qquad
\beta_{i,c}=P(X_i=A\mid H=B,C=c).
\]

Observations are independent conditional on the pair (H,C). The same C is retained across all scheduled readings, even when the sensor type changes. The independent-redraw comparator uses the same calibration prior at each position but draws a fresh calibration profile for every observation. These are two different generative models, not two equivalent implementations.

## Joint-belief accumulator

The sufficient Bayesian state for the shared-calibration model is the joint posterior over the hidden hypothesis and calibration profile:

\[
b_t(h,c)=P(H=h,C=c\mid x_{1:t}).
\]

For the next signal x from scheduled sensor i:

\[
b_{t+1}(h,c)=
\frac{b_t(h,c)P(x\mid h,c,i)}
{\sum_{h',c'}b_t(h',c')P(x\mid h',c',i)}.
\]

The marginal \(P(H=A)\) is useful for a current MAP decision, but it need not retain enough information for the next exact update. The posterior distribution over C can differ even when two histories have the same marginal \(P(H=A)\).

## Main example: same scalar posterior, different next update

Two calibration profiles have equal prior probability. The hidden hypotheses also have equal prior probability. The scheduled sensor response probabilities are:

| Sensor | Profile 1: alpha / beta | Profile 2: alpha / beta |
| --- | ---: | ---: |
| sensor-1 | 9/10 / 1/10 | 3/5 / 2/5 |
| sensor-2 | 7/10 / 3/10 | 4/5 / 1/5 |
| sensor-3 | 9/10 / 1/10 | 1/10 / 3/5 |

The second profile deliberately includes a reversed response for sensor-3. This is a constructed calibration profile, not a claim about an actual device.

After the first two readings, histories AB and BA both give the same marginal:

\[
P(H=A\mid AB)=P(H=A\mid BA)=\frac12.
\]

However, their joint posteriors over (H,C) differ. On receiving A from sensor-3:

| Prior history | Shared-calibration posterior P(H=A) | MAP |
| --- | ---: | --- |
| AB, then A | 255/454 | A |
| BA, then A | 95/194 | B |

If calibration were independently redrawn at each observation, both histories would instead update to 10/17 and select A. The scalar hypothesis posterior alone cannot distinguish the two shared-calibration histories for the next update; the joint belief retains the calibration information needed to continue correctly.

## Full finite-history comparison

The implementation enumerates all eight three-signal histories, independently reconstructs their joint posteriors from the latent likelihoods, and compares the resulting terminal belief set with the sequential accumulator.

For this fixture:
- Shared-calibration MAP accuracy: 153/200 = 76.5%.
- Independent-redraw model's own MAP accuracy: 249/320 = 77.8125%.
- Accuracy of the independent-redraw classifier when evaluated against the shared-calibration model: 763/1000 = 76.3%.
- The two models' MAP decisions disagree on 39/200 = 19.5% of probability mass under the shared-calibration model.
- All eight raw histories produce distinct terminal joint-belief states. Layer counts are 1, 2, 4, and 8, so this example does not demonstrate a reduction in terminal state count. It demonstrates why the state must carry calibration uncertainty, not just the hypothesis marginal.

The different headline accuracies are measured under different data-generating assumptions. The cross-model policy score and disagreement probability are included to avoid comparing those accuracies as though they came from the same world.

## Reproduction

From the repository root:

    python -m py_compile experiments/calibration-aware-joint-evidence/calibration_aware_evidence.py experiments/calibration-aware-joint-evidence/example.py
    python -m unittest discover -s experiments/calibration-aware-joint-evidence -p 'test_*.py' -v
    python experiments/calibration-aware-joint-evidence/example.py

The implementation uses only the Python standard library and exact rational arithmetic. It fails closed if the full raw-history count exceeds max_histories. The report validator rebuilds the joint posterior trajectory, comparator model, and all derived metrics from the retained inputs. SHA-256 is an integrity identifier, not an authentication signature.

## Evidence scope and limitations

- The hidden hypothesis is fixed over the session.
- One discrete calibration profile is drawn once, independently of the hidden hypothesis, and remains fixed through the session.
- Signals are conditionally independent given both H and C. Correlation remaining after conditioning on those variables, hidden-state evolution, calibration drift within the session, and unknown calibration-profile priors are not modeled.
- Each calibration profile supplies known conditional likelihoods for every sensor type in the schedule. The example does not infer these likelihoods from real calibration observations.
- The independent-redraw comparator changes the generative model: it redraws C separately at each observation. It is not a universal baseline or inherently inferior model.
- The finite calibration family and exact transition tables are small, supplied inputs. This is not continuous calibration inference, a general dynamic Bayesian network, or a model of arbitrary correlated noise.
- The full-history comparison is exponential in the number of observations and bounded by max_histories. The cap fails closed; it is not an approximation parameter.
- Results are conditional on the supplied priors, sensor schedule, and likelihoods. They do not establish any real sensor's calibration behavior.

## Files

- calibration_aware_evidence.py — exact joint Bayesian update, shared-calibration and independent-redraw comparison, reachable belief layers, and report reconstruction.
- test_calibration_aware_evidence.py — thirteen tests for same-marginal/different-joint-state behavior, cross-model decision differences, exact probabilities, deterministic channels, unreachable histories, and tamper rejection.
- example.py — runnable three-sensor calibration-profile experiment.
- README.md — latent model, update equation, numerical results, literature context, and evidence scope.


## Decision-value follow-on

[RIV-008: Decision-value context acquisition](../decision-value-context-acquisition/README.md) accepts a joint posterior over hypothesis and calibration profile, including beliefs produced by this session-shared calibration model. It scores declared calibration/context readers by exact expected Bayes decision-loss reduction per cost; the measurement remains a proposal until a separate evidence-gated execution path is used.
