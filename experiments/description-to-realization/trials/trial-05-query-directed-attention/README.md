# Query-directed attention

**Question:** What is the least-cost set of observations sufficient to answer one question, without identifying the entire hidden state?

Given the remaining hypotheses H and a Boolean query q, partition H into q-true and q-false hypotheses. Each candidate observation assigns an expected output to each hypothesis. It separates a cross-boundary pair when the two hypotheses predict different outputs.

The planner builds a universe of all true/false hypothesis pairs. It then selects a minimum-cost observation packet whose union separates every pair. This is weighted set cover.

## Why this differs from target-state isolation

Trial 04 asks which observations identify one particular target state. Trial 05 asks only which observations decide a predicate. It does not pay to distinguish two hypotheses when they agree on the question.

This is useful for causal investigation. A researcher may not need to reconstruct the entire chronology; they may only need to determine whether event A preceded event B, whether a physical effect occurred, or whether a candidate explanation remains viable.

## Poset connection

The test constructs the six linear extensions of two two-event chains C0<C1 and S0<S1. It asks whether C0 preceded S0. Pairwise ordering observations among the other event pairs cannot distinguish one true and one false extension that differ only on the queried relation. The planner therefore reports the unresolved pair. Adding a shared-clock comparison of C0 and S0 resolves the query.

This illustrates an important boundary: no amount of inference over observations that are identical under two competing hypotheses can separate those hypotheses. The required distinction must enter through a measurement or an additional assumption.

## Complexity and limits

With m candidate observations and p cross-boundary pairs, exact bitmask dynamic programming has worst-case time O(m * 2^p) and auxiliary space O(2^p). Above the configured threshold, deterministic greedy weighted set cover is used and labelled non-exact.

The model assumes candidate observations are deterministic, non-intervening, and additive-cost. It is a plan over predicted outcomes, not an execution engine.

## Files

- brief.md — construction requirements
- query_attention.py — exact/greedy query-resolution planner
- test_query_attention.py — poset example and brute-force checks

## Reproduce

    python -m unittest discover -s experiments/description-to-realization/trials/trial-05-query-directed-attention -p 'test_*.py' -v