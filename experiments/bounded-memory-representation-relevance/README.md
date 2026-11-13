# RIV-003: Bounded-memory realization of useful history

**Status:** finite experimental protocol, version 0.1.  
**Question:** What is the smallest tested controller memory that preserves the task value of a full observation history?

## Relationship to RIV-001 and RIV-002

RIV-001 established a counterfactual task-relative value for distinctions in the current representation. RIV-002 showed that an earlier observation can remain useful after two hidden states become observationally identical. RIV-003 asks whether the complete observation trace is necessary, or whether a compact finite-state controller can preserve the same outcome.

Finite-state controllers are a standard representation for bounded-memory policies in partially observable environments. Meuleau et al. describe finite-memory policies as automata that use observation history to compensate for limited instantaneous observability ([UAI 1999](https://mlanthology.org/uai/1999/meuleau1999uai-learning/)). RIV-003 adopts a deterministic, finite-horizon subset of that model and measures exact values over supplied finite transition systems.

## Controller model

For K controller memory states Q = {0, ..., K-1} and observation alphabet O, a controller contains:

\[
\gamma: Q\times O\rightarrow A
\]

\[
\eta: Q\times O\rightarrow Q.
\]

The initial memory state is 0. At each step the controller observes the current representation cell o, chooses action gamma(q,o), and after the action updates its memory to eta(q,o). The next decision sees that updated memory together with the next state's observation.

A conventional deterministic controller may write its update as eta(q,o,a). Since gamma is deterministic, a is already fixed by (q,o), so the action argument is redundant in this experiment's update table.

For each representation, RIV-003 also computes the exact full-history optimum used by RIV-002. It enumerates controllers for each requested memory size and records:

- number of possible controllers in the enumerated class;
- exact maximum survival probability;
- a concrete action table and memory-update table;
- gap from the full-history optimum;
- smallest tested K that attains the full-history value.

If no tested memory size attains the target, the minimum is reported as null. It means no listed size attained it, not that no finite controller can.

## Exact enumeration and cost

For K memory states and m observation cells, the action table has K*m entries and the update table has K*m entries. With |A| actions, the exact deterministic controller count is:

\[
|A|^{Km}\,K^{Km}=(|A|K)^{Km}.
\]

Every controller in each requested class is enumerated. The max_controllers bound fails closed; it never returns a partial optimum. This exact approach is appropriate for the small finite fixtures here, not large general POMDPs.

## Main result

For the RIV-002 two-state memory fixture:

| Representation | One memory state | Two memory states | Full-history target | Minimum tested K |
| --- | ---: | ---: | ---: | ---: |
| Fine (A vs B initially) | 1/2 | 1 | 1 | 2 |
| Coarse (A and B merged) | 1/2 | 1/2 | 1/2 | 1 |

The fine observer needs two memory states to retain whether its first observation was A or B after the current observation becomes C. A one-state controller reproduces the stationary RIV-001 value. The coarse observer cannot recover the distinction by adding memory after it has been removed from the input; no memory state can reconstruct an observation that was never received.

In the example, the fine two-state controller achieves the full-history optimum. Its memory update sends the initial A and B observations to distinct memory states; those states then select different protective actions on observation C. This is a constructive witness, not a claim that two states are universally sufficient.

## Reproduction

From the repository root:

    python -m py_compile experiments/bounded-memory-representation-relevance/bounded_memory_relevance.py experiments/bounded-memory-representation-relevance/example.py
    python -m unittest discover -s experiments/bounded-memory-representation-relevance -p 'test_*.py' -v
    python experiments/bounded-memory-representation-relevance/example.py

The implementation uses only the Python standard library. Probabilities are exact rationals; floats are rejected. The report is reconstructed from its retained inputs by validate_report. SHA-256 identifies the report content but does not authenticate its author.

## Evidence scope and limitations

- The transition system is finite, deterministic, complete, and supplied by the experimenter.
- The viability set and initial distribution are caller-defined.
- Only deterministic controllers with the declared action/update maps are enumerated.
- The update map depends on current memory and current observation. Stochastic memory updates, randomized actions, external recurrent state, and action-dependent update variants are not modeled separately.
- The initial controller memory is fixed to state 0.
- Memory sizes are selected explicitly by the caller. A minimum is reported only among those tested sizes.
- The full-history target and bounded-memory controllers share the same finite horizon and observation mapping.
- Controller synthesis is exponential in K and the observation alphabet; the explicit cap must not be interpreted as an approximation.
- Results are task-, model-, horizon-, and controller-class-relative. They do not establish an intrinsic measure of meaning, semantic information, agency, or consciousness.

## Files

- bounded_memory_relevance.py — exact full-history target, bounded finite-state controller synthesis, ablation comparison, and report reconstruction.
- test_bounded_memory_relevance.py — ten tests for memory compression, policy nesting, exact inputs, explicit bounds, partition order, and tamper rejection.
- example.py — runnable RIV-002 continuation.
- README.md — controller equations, results, reproduction, and evidence scope.
