# RIV-002: History-dependent representation relevance

**Status:** finite experimental protocol, version 0.1.  
**Question:** When does remembering an earlier observation improve what an observer can accomplish after the relevant distinction disappears from its current input?

## Relationship to RIV-001

[RIV-001](../task-relative-representation-relevance/README.md) measures whether coarsening an observation partition changes survival value for stationary observation-to-action mappings. RIV-002 extends the comparison without replacing that baseline. It separates three controller classes so a gain from knowing the time step is not mistaken for a gain from remembering observations.

The distinction between reactive and finite-memory control is established in the partially observable control literature. Meuleau et al. represent finite-memory policies as finite-state automata and show how past observations can compensate for limited instantaneous observability ([UAI 1999 paper](https://mlanthology.org/uai/1999/meuleau1999uai-learning/)). Cohen and Parmentier show that memoryless policies can nevertheless perform reasonably for broad classes of POMDP instances, challenging the assumption that memory is always needed ([Operations Research Letters, 2023](https://doi.org/10.1016/j.orl.2023.02.011)). RIV-002 therefore measures the gain on an explicit finite task rather than presuming memory is always beneficial.

## Three controller classes

For a finite horizon H and observation alphabet O, each state is assigned to one observation cell.

1. **Stationary reactive:** a mapping from current observation cell to action. This is the RIV-001 controller class.
2. **Time-aware reactive:** a mapping from (step, current observation cell) to action. It knows where it is in the finite horizon but cannot remember previous observations.
3. **History-dependent:** a mapping from the complete observation sequence up to and including the current step to action. It may retain an earlier distinction after two hidden states become observationally identical.

All controllers are deterministic. The action history is not included as a separate input: under a deterministic policy, the controller's previous actions are already determined by its observation history and policy.

For each representation R, the evaluator computes exact maximum survival probabilities:

- V_s(R): stationary reactive value;
- V_t(R): time-aware reactive value;
- V_h(R): finite-history value.

The two additional gains are:

\[
G_{time}(R)=V_t(R)-V_s(R)
\]

\[
G_{memory}(R)=V_h(R)-V_t(R)
\]

A finer baseline representation R_f and a coarser ablation R_c produce three corresponding losses:

\[
L_k(R_f\Rightarrow R_c)=V_k(R_f)-V_k(R_c),
\quad k\in\{s,t,h\}.
\]

The nested policy classes imply V_h(R) >= V_t(R) >= V_s(R). The implementation checks these inequalities rather than assuming them.

## Reachable-history enumeration

A history key is a finite sequence of observation-cell identifiers. The implementation first explores all state/history pairs reachable from positive-prior viable initial states under at least one action sequence that remains within the viable set. It enumerates policies only on those reachable histories.

This pruning is exact for the survival objective: impossible histories cannot occur, and histories after a trajectory has already left the viable set cannot affect whether that trajectory survives. It avoids assigning arbitrary actions to every word over the full observation alphabet. Enumeration remains exponential in the number of reachable histories and fails closed when any controller class exceeds max_policies; the cap is not an approximation setting.

## Main example

The world begins in state a or b, each with probability 1/2. The first observation distinguishes them (A versus B). A prepare action moves them to different hidden states (after-a and after-b) that share the same current observation (C). The second action must therefore depend on the remembered initial observation.

| Representation | Stationary | Time-aware reactive | History-dependent |
| --- | ---: | ---: | ---: |
| Fine (A vs B) | 1/2 | 1/2 | 1 |
| Coarse (merge A and B) | 1/2 | 1/2 | 1/2 |

After ablation, stationary and time-aware controllers show zero loss. A history-dependent observer reveals a task-relative viability loss of 1/2. The fine representation's memory gain is also 1/2; the coarse representation's is zero.

A separate timing control has one observation for two successive phases. A stationary controller achieves 0, a time-aware reactive controller achieves 1, and the history-dependent controller also achieves 1. This verifies that the evaluator distinguishes time-awareness from memory.

These results show that retained history can carry a distinction forward after current observations converge. They do not show that all useful meaning requires memory or that history is always worth its computational cost.

## Reproduction

From the repository root:

    python -m py_compile experiments/history-dependent-representation-relevance/history_dependent_relevance.py experiments/history-dependent-representation-relevance/example.py
    python -m unittest discover -s experiments/history-dependent-representation-relevance -p 'test_*.py' -v
    python experiments/history-dependent-representation-relevance/example.py

The implementation uses only the Python standard library. Probabilities are exact rational values; floats are rejected. Reports retain the full input model and are reconstructed by validate_report. SHA-256 is an integrity identifier, not an authentication signature.

## Evidence scope and limitations

- The model is finite, deterministic, fully supplied, and has no stochastic transitions or unmodelled drift.
- Viability is caller-declared; it is not inferred from an organism, system, or external environment.
- Only deterministic stationary, deterministic time-aware reactive, and deterministic observation-history policy classes are compared. Randomized policies and general finite-state controller synthesis are outside this version.
- All policies have full knowledge of the finite horizon. This is a modeling assumption, not a claim about real observers.
- The history controller is allowed to retain the complete finite observation sequence. This is a finite-horizon reference class, not a compact fixed-size memory architecture.
- Exact enumeration can grow exponentially; exceeding the explicit cap returns an error rather than a partial optimum.
- A positive ablation loss is relative to the supplied task, model, initial distribution, viability set, horizon, and controller class. It is not an intrinsic measure of semantic information, meaning, agency, or consciousness.
- A verified report does not establish that the external model is complete or that a real observer uses the supplied representation.

## Files

- history_dependent_relevance.py — exact model normalization, controller enumeration, diagnostics, ablation comparisons, and report reconstruction.
- test_history_dependent_relevance.py — ten tests for memory retention, time-awareness, policy-class nesting, viability, rational inputs, bounds, partitions, and tamper rejection.
- example.py — runnable two-step example.
- README.md — model, equations, literature context, interpretation, and evidence scope.


## Follow-on experiment

[RIV-003: Bounded-memory realization of useful history](../bounded-memory-representation-relevance/README.md) synthesizes deterministic finite-state controllers and measures the smallest tested memory size that preserves the full-history optimum from this experiment.
