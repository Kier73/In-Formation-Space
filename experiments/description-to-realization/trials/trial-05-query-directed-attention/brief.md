# Trial 05: query-directed attention

**Brief ID:** d2r-query-attention-05  
**Parent experiments:** Distinction Refinement, Active Distinction Selection, Poset Causal Interleaver  
**Status:** finite query-resolution model and tests supplied.

## Question

When evidence leaves several hypotheses possible, what is the least-cost set of observations sufficient to decide a particular question, without reconstructing the entire hidden state?

## Desired construction

Treat the remaining hypotheses as a finite state set. A Boolean query partitions the set into true and false classes. Each candidate observation predicts an output for each hypothesis. An observation separates a cross-boundary pair when its outputs differ.

Select a minimum-cost set of candidate observations that separates every true/false hypothesis pair. Differences between hypotheses on the same side of the query are irrelevant to resolving that question.

## Hard constraints

- Standard-library Python only.
- Hypotheses, candidate outputs, and names must be hashable or valid non-empty strings as required.
- Query must return a Boolean for each hypothesis.
- Candidate costs must be finite and strictly positive.
- If a true/false pair cannot be distinguished by any available candidate, report it as unresolved.
- Exact weighted set-cover optimization for small cross-boundary pair sets; explicitly labelled greedy approximation for larger sets.
- A query already determined by all remaining hypotheses requires no observation.

## Interpretation boundaries

This is a static information-design model. Candidate functions describe predicted observations under each hypothesis; they are not executed by the planner. The model assumes observations are deterministic, non-intervening, and have additive costs.

A complete plan means only that the selected observation signatures would determine the query across the supplied hypothesis set. It does not claim the observations have occurred, that the hypothesis set is exhaustive, or that the query's real-world interpretation is correct.