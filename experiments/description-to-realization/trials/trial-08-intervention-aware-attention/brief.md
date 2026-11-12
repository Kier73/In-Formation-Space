# Construction brief: Trial 08 - Intervention-aware attention

**Brief ID:** `d2r-intervention-aware-attention-08`  
**Parent work:** Trial 06 (Adaptive Attention Policies), Evidence-gated Observation Path, VGI partial-aware probes  
**Question:** Can an observer select a sequence of probes when each probe may change the hidden system state, while keeping information cost and intervention cost distinct?

## Hard constraints

1. Model a finite, explicitly declared set of hidden hypotheses and world states.
2. Preserve each hypothesis identity and its Boolean query value about the **initial** hypothesis throughout the policy.
3. Model each probe as a deterministic mapping from current world state to `(observed outcome, next hidden state, intervention cost)`.
4. Branch only on the observed outcome. The next hidden state is not directly visible to the planner or observer.
5. Use exact rational priors and costs; reject binary floating-point inputs rather than silently approximating them.
6. Return all Pareto-nondominated policies for expected observation cost, expected intervention cost, worst-case observation cost, and worst-case intervention cost.
7. Bound depth, hypothesis count, frontier size, and exact policy-combination search explicitly.
8. Preserve unresolved status when no complete query-resolving policy exists within the declared depth.
9. Rebuild the result from its embedded model and reject altered derived output.
10. Use only Python's standard library in the implementation and tests.

## Questions the experiment should discriminate

- Can a probe with a constant immediate outcome still be useful because it changes different hypotheses into different future states?
- Does the model reduce to Trial 06 when all probes preserve state and have zero intervention cost?
- Can the planner preserve a real observation-cost/intervention-cost trade-off rather than inventing a scalar exchange rate?
- Are worst-case intervention totals computed along one hypothesis trajectory rather than by combining maxima from different hypotheses?

## Out of scope

Stochastic sensors, nondeterministic transitions, autonomous drift between probes, continuous state spaces, execution adapters, and post-intervention queries are not part of this finite first trial. A later study may add these as separately declared dimensions.
