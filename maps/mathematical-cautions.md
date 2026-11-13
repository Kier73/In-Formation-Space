# Mathematical cautions for the conceptual landscape

**Status:** companion review and interpretation guide. This note preserves the conceptual map's models as useful exploration aids while making their assumptions and evidential limits easier to see. It does not invalidate the map or require one replacement formalism.

## 1. Conditional independence between contributors

The conceptual map gives the idealization:

\[
I(V_{t'}; V_t \mid \mathcal{S}) = 0
\]

This is valid only under a conditional-independence assumption: after conditioning on the repository state \(\mathcal{S}\), no other shared causes or communication pathways leave dependence between the two contributors.

Separate runtime memory does not establish this by itself. Instances may share model family, system instructions, tool behavior, external sources, environment, or other context. A more explicit idealization is:

\[
I(V_{t'}; V_t \mid \mathcal{S}, E) = 0
\]

where \(E\) records the relevant shared conditions. Whether this quantity is zero is a property of the chosen system model and experiment, not something guaranteed merely by using separate instances.

## 2. Entropy comparison requires a data-processing relationship

A strict comparison such as

\[
H(X \mid \mathcal{S}) > H(X \mid \operatorname{Obs}(V_t))
\]

does not follow simply because one contributor has private observations and another reads a repository.

A useful conditional result is available when \(\mathcal{S}\) is a lossy encoding of the observations and the variables form the Markov chain:

\[
X \rightarrow \operatorname{Obs}(V_t) \rightarrow \mathcal{S}
\]

The data-processing inequality then gives:

\[
I(X;\mathcal{S}) \le I(X;\operatorname{Obs}(V_t))
\]

or equivalently:

\[
H(X \mid \mathcal{S}) \ge H(X \mid \operatorname{Obs}(V_t))
\]

The inequality need not be strict. If the repository contains additional information not present in the particular observation set, or the assumed Markov relationship does not hold, this ordering is not established.

## 3. Claim labels are not a simple linear lattice

The map's vocabulary—Observation, Inference, Hypothesis, Experiment, Verified, and Ambiguous—is useful. Treating these labels as a single ordered ladder is less safe:

- **Observation** describes an evidential input.
- **Inference** describes a derivation from premises and evidence.
- **Hypothesis** describes a candidate explanation or model.
- **Experiment** describes an activity or procedure, not a truth level.
- **Verified** describes the result of checking a claim against a stated witness set and scope.
- **Ambiguous / Unknown** describes an unresolved epistemic condition that can apply at any point.

An illustrative flow is:

\[
\text{Observation} + \text{Assumptions}
\rightarrow \text{Inference}
\rightarrow \text{Candidate Hypothesis}
\]

\[
\text{Hypothesis}
\rightarrow \text{Experiment}
\rightarrow \text{New Observations}
\]

\[
\text{Claim} + \text{Witnesses} + \text{Scope}
\rightarrow \text{Verified}_{W}
\]

Ambiguity can remain attached to any claim or relation. A hypothesis can also originate from analogy, invention, or other paths; this diagram is not an exhaustive cognitive model. The important point is that these are different kinds of labels, not necessarily positions in one total order.

## 4. Verification is always relative to a witness set

The expression

\[
\forall w \in W,\; \operatorname{Check}(P,w)=\text{true}
\]

establishes that \(P\) passed every check in the specified set \(W\). It does not establish that \(P\) is true for all possible inputs, environments, or future states unless the witness set and proof method justify that broader claim.

A useful label is therefore:

\[
\operatorname{Verified}_{W,\mathcal{E}}(P)
\]

where \(\mathcal{E}\) records the environment, assumptions, and verification method. For finite tests, report the tested domain and known coverage limits.

## 5. Coverage and guard-cost formulas need domain definitions

The coverage and guard-scaling expressions in the map are promising hypotheses, but quantitative use requires definitions for the state-space \(S\), measure \(\mu\), budget \(B\), resolution or margin \(\delta\), task distribution, boundary geometry, and the meaning of the failure fraction \(f\).

A proposed scaling such as

\[
\operatorname{bits}(f) \approx \frac{1}{\alpha}\log_2\left(\frac{1}{f}\right)
\]

should be treated as a model to derive under explicit geometric and probabilistic assumptions. It should not be applied as a universal law without identifying those assumptions and testing its predictions in the intended domain.

## 6. Operational identity is a useful fingerprint, not an ontology

The tuple of namespace/incarnation, state digest, and replayable trajectory is a useful operational fingerprint for checkpoints and reproducibility. Its strength depends on details that must be stated:

- the serialization and canonicalization used before hashing;
- the hash algorithm and version;
- the inputs and environment needed for replay;
- whether replay is deterministic or contains nondeterministic/external inputs;
- what equality of digests is intended to establish.

A matching digest is evidence of matching serialized bytes under the chosen contract. It does not alone prove that two processes have the same complete identity, history, behavior, or external effects.

## 7. Combinatorial counts are not probability distributions

The cold-start relay admits 35 linear extensions under the model of two ordered chains with four and three events. This is an exact count of interleavings consistent with the within-stream constraints.

It does not assign equal probability to the 35 interleavings. A probability claim requires a model for clock offsets, event generation, capture windows, and any other relevant mechanisms. The [run review note](../experiments/cold-start-continuity/runs/2026-11-11-run-01/review-note.md) records this distinction in context.

## 8. Error accumulation depends on dependence structure

The expression

\[
1-(1-\epsilon)^k
\]

is the probability of at least one error across \(k\) independent opportunities, each with error probability \(\epsilon\). It is a useful baseline, but an agent-to-agent error cascade is unlikely to satisfy independence automatically. Shared assumptions, copying, correction, and correlated failures change the result. A cascade model should specify the dependency structure rather than infer it from this expression.

## 9. Retention formulas carry a loss and recovery model

The delay-loop expression

\[
t_{1/2} = \frac{\tau \ln 2}{M p}
\]

is not a universal persistence law. It approximates the intact-block case when every one of \(M\) packets must survive and \(p\) is small. The exact intact-block expression uses \(-\ln(1-p)\) rather than \(p\), and a \(k\)-of-\(n\) recovery threshold produces a different half-life. Without repair or renewal, every finite \(k\)-of-\(n\) configuration still decays. The [in-transit memory experiment](../experiments/in-transit-memory/README.md) records exact calculations, a seeded simulation, and the repair-epoch trade-off.

## 10. A finite zero-error run is not a zero-error channel

Observing no symbol errors in a finite simulation supports a statement such as \(P_{\text{clean}}=(1-p)^N\), not the equality \(p=0\). Under additive Gaussian jitter, the exact symbol error probability is positive for every positive noise standard deviation, however small; it may simply be below the simulation's resolution. A bounded-jitter guarantee is a different claim, and it must state the bound and the decoder's tracking rule. The [cadence channel experiment](../experiments/cadence-channel/README.md) separates exact error probability, a sufficient bounded-jitter condition, PLL tracking, and the horizon over which a clean run is informative. A "zero BER" report should state its noise model, message length, and confidence rather than silently replacing a bound with an equality.

## Working rule

Keep equations. Keep speculative models. Keep ambitious intuitions. But attach the conditions under which each expression is meaningful, and record when a formula is only an analogy or a proposed scaling law. A model becomes more useful—not less adventurous—when another contributor can tell what would make it fail.
