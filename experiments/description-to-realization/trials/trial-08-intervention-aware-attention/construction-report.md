# Construction report: Trial 08 - Intervention-aware attention

**Brief ID:** `d2r-intervention-aware-attention-08`  
**Implementation:** `intervention_attention.py`  
**Tests:** `test_intervention_attention.py`  
**Local verification environment:** Python 3.13.5  
**Status:** focused local prototype passed its nine-test suite; the repository workflow is the independent Python 3.11 check.

## 1. Result

Constructed a finite-horizon policy planner for observations that also alter hidden world state. Each candidate retains its original hypothesis identity and query value while carrying a current state through the policy tree. The planner returns a Pareto frontier rather than choosing an arbitrary weighted compromise between information acquisition and intervention impact.

The useful distinction is between an observation result and its transition effect. A probe may return the same visible result for every candidate and still be valuable when it moves candidates into different next states that a later probe can distinguish.

## 2. Recurrence and path accounting

For hypothesis `h` at current state `x_h`, probe `a` supplies `(y_a(x_h), x'_h, i_a(x_h))` and has observation cost `c_a`. The visible outcome selects a branch; each candidate in that branch carries its own `x'_h`.

A terminal node is allowed only when the original Boolean query is constant across every surviving hypothesis.

For each complete policy and each surviving hypothesis, the solver retains its complete path costs:

\[
O_\pi(h) = \sum_{a \in path_\pi(h)} c_a
\]

\[
I_\pi(h) = \sum_{a \in path_\pi(h)} i_a(x_{h,a})
\]

The four reported values are:

\[
E_O = \sum_h p(h \mid B) O_\pi(h), \quad
E_I = \sum_h p(h \mid B) I_\pi(h)
\]

\[
W_O = \max_h O_\pi(h), \quad W_I = \max_h I_\pi(h)
\]

This per-hypothesis representation is necessary for exact worst-case intervention accounting. A sum of independently maximized immediate and future costs can overstate the true path maximum if those maxima belong to different hypotheses. A regression test verifies that a fixture with path totals 2 and 10 reports worst case 10, not the invalid cross-hypothesis sum 12.

All inputs and outputs use exact rational values. Floats are rejected; result documents contain reduced numerator/denominator pairs. The model and plan have SHA-256 digests, and `validate_intervention_attention_document()` rebuilds the policy frontier from the embedded model and requires exact equality.

## 3. Search

The memoization key is the ordered set of `(hypothesis_id, current_state)` pairs plus remaining depth. Every recursive call reduces the remaining depth, so finite-horizon search is acyclic even when probes can be repeated or world states cycle.

For each probe, the solver groups candidates by visible outcome, updates their hidden states, recursively obtains each branch's frontier, enumerates combinations of feasible child policies, and removes dominated four-dimensional cost vectors. Equal vectors are deduplicated with deterministic policy tie-breaking.

Explicit limits cover hypothesis count, maximum Pareto-frontier size, and memoized/child-policy combination search. Crossing a limit raises `FrontierLimitError`; it does not silently replace exact enumeration with a heuristic.

The state space can grow with the number of hypotheses, world states, depth, and distinct Pareto policies. This is a small finite research model, not a claim of scalable general POMDP planning.

## 4. Focused verification

Ten tests cover:

1. A probe changes hidden state before a later probe resolves the original query.
2. The zero-intervention, state-preserving special case retains Trial 06's expected-cost optimum of `3/2`.
3. A safe/slow and fast/invasive choice both remain on the Pareto frontier.
4. Worst-case intervention cost is computed on each hypothesis's own path.
5. A constant visible outcome can still be useful when next states differ.
6. A horizon with no complete policy reports `unresolved_within_depth`.
7. Embedded-model reconstruction succeeds, while altered derived output is rejected.
8. Exact rational inputs and normalized priors are required.
9. Pareto-frontier limits fail explicitly.
10. Nested Pareto pruning preserves per-hypothesis path costs when an ancestor adds state-dependent intervention costs.

The focused local run completed ten tests successfully under Python 3.13.5. The repository workflow runs the same directory under Python 3.11 as an independent environment check.

## 5. What this establishes - and what it does not

The tests establish implementation behavior on the supplied finite fixtures, including exact arithmetic, state-dependent transitions, Pareto filtering, path-cost correlation, and deterministic reconstruction. Trial 06's non-intervening result provides a useful reduction check.

They do not establish that any real sensor/action pair has the modeled transition table, that intervention cost is calibrated to physical risk, or that the deterministic model is complete. The planner is not connected to a transport or execution adapter. A selected action remains a proposed policy node until a host actually performs it and records the outcome through the existing evidence-gated path.

## 6. Next discriminating experiments

- Add stochastic outcomes and transitions with exact finite distributions, keeping process noise distinct from prior uncertainty.
- Add autonomous state evolution between probes, with an explicit temporal transition model.
- Compare the current finite-horizon Pareto frontier with a small exhaustive policy enumerator on random tiny models.
- Define a query about the post-intervention state as a separate query scope rather than reusing the initial-hypothesis semantics.
- Bind one real, reversible observation adapter to the evidence-gated path and compare predicted state transitions with independently observed outcomes.
