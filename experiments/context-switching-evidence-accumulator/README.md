# RIV-006: Context-switching evidence accumulation

**Status:** finite exact Bayesian filtering experiment, version 0.1.  
**Question:** When sensor reliability is governed by a persistent hidden operating context, what belief state preserves the evidence needed for future updates?

## Relationship to RIV-004 and RIV-005

- **RIV-004** showed that a positive-signal count is sufficient for binary MAP classification under a fixed iid sensor channel.
- **RIV-005** allowed a known schedule of heterogeneous sensors. Under conditional independence given a fixed hidden hypothesis, the scalar posterior P(H=A | history) remains sufficient for future Bayesian updates when the next sensor is known.
- **RIV-006** changes the dependency structure. Sensor reliability is influenced by a two-state hidden regime that evolves as a Markov process. The current signal changes what the observer believes about both the hypothesis and the regime, and these two beliefs can become correlated.

The exact recursive state is now the **joint posterior over hypothesis and next context regime**. This experiment shows that retaining only the hypothesis posterior—or even retaining the two separate hypothesis and regime marginals—can discard information needed for the next update.

This is standard finite-state Bayesian filtering for a hidden Markov model, not a new statistical theorem. The contribution here is an executable exact-rational transducer, complete-history comparison, and a minimal explicit counterexample to scalar and separate-marginal filtering.

## Model

The hidden hypothesis H is fixed during the observation window and belongs to {A, B}. The operating context Z is one of:

- good — the sensor has a more discriminating response;
- degraded — the sensor is less discriminating.

The context regime follows a known two-state Markov transition:

- P(Z(next)=good | Z=current good);
- P(Z(next)=good | Z=current degraded).

The transition is independent of H. Each scheduled sensor has four known likelihoods: the probability of signal A under each hypothesis and each context regime. Signals are conditionally independent given H and the current regime. Sensor likelihoods may vary by schedule position, so the model retains RIV-005's heterogeneous sensor schedule.

The initial H and Z distributions are supplied independently. Every probability is an exact rational; floats and booleans are rejected.

## Joint posterior accumulator

Before sensor i, the accumulator stores:

b_i(h,z) = P(H=h, Z_i=z | signals observed before i).

For signal x from sensor i, first condition on the emission likelihood:

w_i(h,z) = b_i(h,z) P(x | H=h, Z_i=z).

Normalize w_i by the total signal probability, then predict the next regime:

b_(i+1)(h,z') = sum over z of
    [w_i(h,z) / sum(w_i)] P(Z_(i+1)=z' | Z_i=z).

H does not transition. The four joint coordinates are retained in a fixed order. This is a finite Bayesian belief-state update: under the declared model and known sensor schedule, the next joint belief is determined by the current joint belief and the next signal.

The implementation builds exact transition rows for signals A and B from every reachable joint belief at every schedule layer. It also enumerates every ordered signal history under an explicit cap and independently compares the final posterior, history probability, MAP decision, and total MAP accuracy.

## Exact counterexample: same marginals, different next update

The runnable example uses:

- Prior P(H=A) = 1/2.
- Prior P(Z=good) = 1/2.
- P(next good | current good) = 9/10.
- P(next good | current degraded) = 1/10.
- In the good regime, P(signal A | H=A) = 9/10 and P(signal A | H=B) = 1/10.
- In the degraded regime, both hypotheses produce signal A with probability 1/2.

After two signals, histories **AB** and **BA** have the same hypothesis marginal:

P(H=A | AB) = P(H=A | BA) = 1/2.

They also have the same context marginal:

P(Z=good | AB) = P(Z=good | BA) = 301/890.

But the joint distributions are different: the association between H and Z is reversed. The distinction matters immediately. Under the same next sensor, if the next signal is A:

- P(H=A | ABA) = 2747/4290.
- P(H=A | BAA) = 2907/4610.

So the two separate marginals do not determine the next posterior. The joint association is information that a pair of independent scalar summaries discards.

This does not say that every hidden-context process requires four states, or that the regime is a real physical cause. It establishes insufficiency for this declared model and schedule.

## Sufficiency is not the same as compression

For the four-sensor example, the raw terminal history set has 16 possible strings and the exact joint filter reaches 16 distinct terminal joint beliefs. The hypothesis marginal has only 9 distinct values, but it has merged histories that require different future updates.

In this case the sufficient joint belief does **not** compress the terminal history count. It retains the information required for future filtering at a higher state cardinality. A sufficient representation may be larger than a lossy summary.

A useful control case sets both regime-transition rows equal to 1/2. The next regime is then independent of the previous regime, so the predicted joint belief factorizes and is determined by the hypothesis posterior plus the fixed context prior. The implementation verifies that the scalar posterior no longer loses next-step information in that memoryless-context case.

## Reproduction

From the repository root:

    python -m py_compile experiments/context-switching-evidence-accumulator/context_switching_evidence.py experiments/context-switching-evidence-accumulator/example.py
    python -m unittest discover -s experiments/context-switching-evidence-accumulator -p 'test_*.py' -v
    python experiments/context-switching-evidence-accumulator/example.py

The implementation uses only the Python standard library and exact Fraction arithmetic. It verifies the complete ordered-history set up to max_histories; exceeding the cap fails closed. The report validator rebuilds the joint filtering transitions, reachable belief layers, marginal-collision diagnostics, history probabilities, MAP decisions, and accuracy from the retained model inputs. SHA-256 is a content-integrity identifier, not an authentication signature.

## Evidence scope and limitations

- H is fixed across the observation window.
- The context regime has two states and follows the supplied Markov transition matrix.
- The context transition is independent of H. Hypothesis-dependent context transitions are not represented.
- Signals are conditionally independent given H and the current regime. Residual within-regime sensor correlation is not modeled.
- Sensor likelihoods and the schedule are known. Unknown sensor calibration, online parameter learning, and sensor identity uncertainty are not included.
- The initial H and Z distributions are independent. A general caller-supplied joint prior is not part of this version.
- The task is binary MAP classification after a fixed schedule. Sequential stopping, utility-sensitive actions, and active sensor acquisition are not implemented.
- One-step marginal-divergence diagnostics test the next scheduled sensor at each prefix. Finding no one-step divergence is not a proof of sufficiency for every longer continuation.
- The joint posterior is a belief state under the specified model, not direct observation of a physical hidden regime or proof of causation.
- The experiment establishes exact behavior for its supplied finite model; it does not establish that a real sensor network follows the model.

## Files

- context_switching_evidence.py — exact joint filtering transducer, complete-history enumeration, marginal counterexamples, and report reconstruction.
- test_context_switching_evidence.py — exact posterior witness, memoryless-regime reduction, unreachable histories, heterogeneous schedules, bounds, and tamper tests.
- example.py — runnable AB versus BA illustration.
- README.md — model, filtering recursion, counterexample, and evidence limits.

## Follow-on question

The next useful bridge is not to presume that the hidden regime can be read directly. It is to ask whether an explicitly authorized context measurement—planned through VGI attention and recorded through the ObservationPath—can improve the joint posterior enough to change a declared decision, and at what observation cost. That requires a model linking context-capture actions to regime observations; this experiment does not invent that link.
