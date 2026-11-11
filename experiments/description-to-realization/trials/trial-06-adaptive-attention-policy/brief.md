# Trial 06: adaptive attention policies

**Brief ID:** d2r-adaptive-attention-06  
**Parent trials:** Active Distinction Selection and Query-directed Attention  
**Status:** exact finite expected-cost policy solver and unit tests supplied.

## Question

Can an observer reduce cost by choosing the next observation only after seeing the previous observation's outcome, rather than collecting a static packet up front?

## Desired construction

Given finite hypotheses, a Boolean query, deterministic candidate observation functions, positive costs, and an optional positive prior, construct a decision tree. Each internal node selects one observation. Each outgoing edge represents an observation outcome. Each leaf must resolve the query to true or false.

Optimize expected total observation cost under the supplied prior. Also report worst-case path cost.

## Hard constraints

- Standard-library Python only.
- Candidate outputs are hashable and candidate observation functions are deterministic.
- Costs and prior weights are finite and strictly positive.
- The policy must not ask an observation again in a branch where it is already constant.
- Return the minimal-cost complete adaptive policy for inputs within the configured hypothesis limit.
- If any true/false hypothesis pair is observationally identical under every candidate, report the pair and no complete policy.
- Bound exact subset search explicitly; do not silently fall back to an unlabelled heuristic.

## Interpretation boundaries

The model assumes observations do not alter the hidden state, costs add along a path, and the prior weights describe the hypotheses before any additional observation. It optimizes expected cost; it does not optimize worst-case cost, though it reports that cost for the selected policy.

The policy is a plan over predicted outcomes, not evidence that observations were performed.