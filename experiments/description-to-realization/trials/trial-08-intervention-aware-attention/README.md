# Trial 08: Intervention-aware attention

**Question:** What should an observer inspect when inspecting something can change it?

[Trial 06](../trial-06-adaptive-attention-policy/README.md) models adaptive observations as deterministic and non-intervening: each observation partitions the remaining hypotheses, and the next observation is selected after seeing the previous result. That is a useful baseline, but it assumes the observed system remains in the same state while attention is spent.

Real probes can advance time, consume a resource, alter a machine, move a process, or change the conditions available to a later measurement. An observation plan must then track both what the observer learns and what its actions do.

## Model

A hypothesis has four fields:

- `hypothesis_id`: stable identity for the possible initial situation;
- `initial_state`: its initial world state;
- `query_value`: the Boolean answer sought about that initial hypothesis;
- `prior`: an exact positive rational probability, with all priors summing to one.

A probe maps every declared current world state to:

\[
T_a(x) = (y, x', i)
\]

where `y` is the visible outcome, `x'` is the next hidden world state, and `i` is the intervention cost incurred for that transition. The probe also has a separate observation/acquisition cost `c_a`.

The observer sees `y`, not `x'`. Every hypothesis in the same outcome branch therefore continues with its own updated hidden state. Hypothesis identity and its original query value remain fixed; only the current world state changes.

A policy is complete when every leaf contains only hypotheses with the same original query value. This explicit query scope avoids silently changing the question from "what was initially true?" to "what is true after my probes?"

## Four-dimensional cost frontier

The planner returns Pareto-nondominated policies over four separate quantities:

1. expected observation cost;
2. expected intervention cost;
3. worst-case observation cost;
4. worst-case intervention cost.

It does not collapse these into one weighted score. A slower, low-impact probe and a fast, invasive probe may both remain on the frontier because neither is better on every dimension.

For a surviving candidate set `B`, let `p(h | B)` be the normalized prior. For a selected probe `a`, the path costs for each hypothesis are tracked separately:

\[
C_a^{obs}(h) = c_a + C_{child}^{obs}(h)
\]

\[
C_a^{int}(h) = i_a(x_h) + C_{child}^{int}(h)
\]

Expected costs are the prior-weighted path costs, while worst-case costs are the maximum path costs over the same surviving hypotheses. Keeping per-hypothesis paths matters: adding the largest current intervention to the largest future intervention can combine two different hypotheses and produce an invalid worst-case total.

The policy dynamic program explores every probe and every combination of feasible child-frontier plans within explicit bounds. A constant-output probe is not automatically discarded: it may change different hidden states differently and create a useful distinction for a later probe. A probe that gives every survivor the same outcome and same next state is uninformative and is skipped.

## Reproduction

From the repository root:

```bash
python -m py_compile experiments/description-to-realization/trials/trial-08-intervention-aware-attention/intervention_attention.py
python -m unittest discover -s experiments/description-to-realization/trials/trial-08-intervention-aware-attention -p 'test_*.py' -v
```

The implementation and tests use only the Python standard library.

## Example model

Two hypotheses begin in states `a0` and `b0`. A `prepare` probe returns the same visible outcome (`ready`) for both, but changes their hidden states to `a1` and `b1`. A later `read` probe distinguishes `a1` from `b1`, although it cannot distinguish `a0` from `b0`.

The planner therefore selects `prepare -> read`. This is not a case where the first probe tells the observer which hypothesis is true. It is useful because it changes what the next probe can reveal.

The fixture gives each probe an observation cost of 1 and charges the `prepare` state transition an intervention cost of 1. With equal priors, the complete policy has expected observation cost 2, expected intervention cost 1, worst-case observation cost 2, and worst-case intervention cost 1.

A second fixture offers a safe probe with observation cost 3 and zero intervention cost, or a fast probe with observation cost 1 and intervention cost 2. Both resolve the same query immediately, so both remain on the Pareto frontier.

## Relationship to neighboring work

- **Trial 06** is the non-intervening special case: every probe preserves the current state and has zero intervention cost. A regression fixture preserves its published expected-cost optimum of 1.5.
- **VGI partial attention** supplies candidate probes and counterfactual outcomes for partial Grounds. This trial asks a different question: what if performing one of those probes changes the state on which later probes operate?
- **Evidence-gated Observation Path** remains the execution/provenance boundary. Trial 08 produces a plan over a supplied model; it does not dispatch probes, construct Encounter Envelopes, or claim a real intervention occurred.
- **Transition conformance bridge** compares completed admitted/interpreted attempts with the pinned Trial 08 transition table. Before/after state witnesses are references, not silently accepted state changes. Full mismatches can become proposed transition overrides, but they require explicit validation and activation into a new immutable model revision. Operation-span duration remains separate from intervention cost; see the [bridge design](../../../../bridges/observation-path/transition-conformance.md).

## Interpretation limits

- The model is finite, deterministic, and completely supplied by the caller.
- Query values refer to initial hypotheses, not the final world state.
- Priors and costs are exact rational inputs, not measurements.
- Intervention cost is a caller-supplied model value; the planner does not infer physical harm, risk, or energy from timing.
- No stochastic outcome, unmodelled clock drift, concurrent action, or external disturbance is included.
- `unresolved_within_depth` means no complete policy was found within the stated horizon and limits. It is not a proof that no policy exists at any depth.
- Pareto optimality is relative to the four declared cost dimensions and the supplied transition model.

## Files

- `brief.md` - construction requirements and discrimination questions.
- `intervention_attention.py` - exact bounded planner and independent result reconstruction.
- `test_intervention_attention.py` - ten unit tests covering state-changing probes, Pareto trade-offs, Trial 06 reduction, exact costs, path-correlated worst-case accounting, compositional nested-frontier pruning, and tamper rejection.
- `construction-report.md` - algorithm, evidence, and remaining questions.
