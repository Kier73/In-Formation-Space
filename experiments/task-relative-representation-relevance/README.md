# RIV-001: Task-relative representation relevance

**Status:** finite experimental protocol, version 0.1.  
**Question:** When does a distinction in an observer's representation matter to what the observer can accomplish?

## Motivation

Information content and task relevance are different quantities. A representation may distinguish states without improving any declared task. Conversely, merging two states can make a task impossible when the states require different actions. RIV-001 makes this counterfactual: retain a representation, ablate some distinctions by replacing it with a coarser partition, and measure the change in the best achievable survival probability under a fixed controller class.

This experiment complements rather than replaces [Trial 03: Distinction Refinement](../description-to-realization/trials/trial-03-distinction-refinement/README.md), the [Observation Equivalence bridge](../../bridges/observation-equivalence/README.md), and [Trial 08: Intervention-aware Attention](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md). Those study information partitions, transition stability, and probes that change the observed world. RIV-001 asks what a representation distinction is worth to a particular finite task.

## Model and measurement

The input is a finite deterministic transition system, an exact initial probability distribution, a caller-declared viable-state set, a finite horizon H, and one or more state-to-observation partitions. A controller sees only the current partition cell and uses a stationary deterministic mapping from cells to actions. It has no hidden-state access, memory, or time-varying policy. Every controller in that declared class is enumerated exactly.

A trajectory survives when its initial state and every state reached over H transitions belong to the declared viable set. For representation R, let V_H(R) be the maximum exact survival probability over the allowed controller class. For a finer baseline R_f and a coarser ablation R_c, RIV-001 reports:

\[
L_H(R_f \Rightarrow R_c) = V_H(R_f) - V_H(R_c)
\]

The baseline must refine the ablated partition. Any coarse policy can then be copied to every fine cell inside its coarse cell, so the loss cannot be negative. A negative result is treated as a model or implementation error.

Each profile separately reports cell count, enumerated policy count, maximum survival probability, an optimal policy witness, transition congruence, and viability-label homogeneity. Congruence and viability alignment are diagnostics, not synonyms for task value.

## Example

Two equally likely viable states, low and high, require different protective actions. Either incorrect action moves the state to dead.

- With the state-aware representation, the controller selects the matching action in each state and survival is 1.
- When low and high are merged into one observation cell, the controller must choose one action for both and the best survival probability is 1/2.
- If either action instead preserves both states, the same representational ablation has zero loss: the distinction exists but is not needed for this task.

These are exact results over the supplied model, not observations about an external organism, machine, or agent.

## Reproduction

From the repository root, run:

    python -m py_compile experiments/task-relative-representation-relevance/task_relative_relevance.py experiments/task-relative-representation-relevance/example.py
    python -m unittest discover -s experiments/task-relative-representation-relevance -p 'test_*.py' -v
    python experiments/task-relative-representation-relevance/example.py

The implementation uses only the Python standard library. Probabilities accept integers, rational strings, or numerator/denominator objects; floats are rejected. Exhaustive enumeration is bounded by max_policies; exceeding that cap raises PolicyLimitError rather than returning an incomplete optimum. validate_report independently reconstructs all derived profiles and ablation values from the retained inputs. Its digest is an integrity identifier, not an authentication signature.

## Evidence scope and limitations

- The transition system and viable-state predicate are finite, deterministic, complete inputs supplied by the experimenter.
- The viability objective is survival in the caller-supplied set; it is not inferred biological or physical viability.
- Only stationary deterministic observation-based policies are compared. A memoryful, history-dependent, stochastic, or partially observed policy class may achieve a different value.
- The result depends on the initial distribution, horizon, transition model, viable set, representation, and controller class.
- A positive loss establishes task relevance only within this model and contract. It is not an intrinsic or universal measure of semantic information, meaning, agency, or consciousness.
- A verified report does not establish that the external model is complete or that a real observer uses the supplied representation.

## Files

- task_relative_relevance.py — exact finite-model evaluation, diagnostics, ablation comparison, and report reconstruction.
- test_task_relative_relevance.py — focused tests for relevant and redundant distinctions, exact probabilities, viability over the full horizon, partition order, explicit policy bounds, and tamper rejection.
- example.py — runnable two-state illustration.
- README.md — model, equations, interpretation, and evidence scope.


## Follow-on experiment

[RIV-002: History-dependent representation relevance](../../history-dependent-representation-relevance/README.md) extends the controller comparison with time-aware reactive and finite observation-history policies. It separates the value of knowing the current step from the value of retaining a past distinction, and tests a case where two hidden states become observationally identical after the first action.
