# Adaptive attention policies

**Question:** Can an observer spend less by choosing each next observation after seeing the previous result?

Trial 04 selects a static packet for isolating a target. Trial 05 selects a static packet for resolving a Boolean query. Trial 06 takes the next step: it builds a decision tree whose later observations depend on earlier outcomes.

## Model

Each leaf of the policy tree must contain hypotheses that all agree on the query. Each internal node selects an observation and branches on its predicted value. The solver minimizes expected total cost under a supplied positive prior (uniform by default), and also reports worst-case path cost.

Exact memoized subset dynamic programming is used for a bounded finite hypothesis set. The policy pre-evaluates deterministic observation functions over all hypotheses, then solves each reachable subset. If a true and false hypothesis are identical under every candidate observation, the planner reports the unresolved pair and no complete policy.

## Static packet versus adaptive policy

An observation that is useful in one branch may be unnecessary in another. The adaptive policy can therefore avoid collecting every possible test. One fixture uses four hypotheses and three inexpensive observations. The optimal policy first uses a refinement that already resolves two of the four hypotheses; only the remaining two-hypothesis branch needs a second observation. Its expected cost is 1.5 and its worst-case cost is 2, while collecting the whole three-observation packet costs 3 and a direct query sensor costs 2.5.

This is not a universal claim that adaptive policies are cheaper. The result depends on the prior, observation costs, possible outcomes, and deterministic model.

## Limits

The exact solver has worst-case exponential behavior in the number of hypotheses and rejects inputs above its configured limit. The objective is expected cost under the supplied prior. Costs are additive along a path, and observations are assumed deterministic and non-intervening. Stochastic sensors, actions that alter the system, or order-dependent costs require a different model.

## Files

- brief.md — construction requirements
- adaptive_attention.py — expected-cost decision-tree planner
- test_adaptive_attention.py — branching, prior, impossibility and reference-recursion tests
- construction-report.md — optimality recurrence, complexity, and CI result
- results/test-encounter.json — provenance record for the successful CI test run

## Reproduce

    python -m unittest discover -s experiments/description-to-realization/trials/trial-06-adaptive-attention-policy -p 'test_*.py' -v