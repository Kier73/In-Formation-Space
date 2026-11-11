# Construction report: query-directed attention

**Trial:** 05  
**Brief:** d2r-query-attention-05  
**Implementation:** query_attention.py  
**Tests:** test_query_attention.py  
**Execution receipt:** results/test-encounter.json

## Construction

The planner receives a finite set of hypotheses that remain possible after current evidence, a Boolean query over those hypotheses, and candidate observation functions with positive costs. The query divides the hypotheses into true and false classes.

Each candidate observation separates a cross-boundary pair when the two hypotheses predict different observation values. The planner must cover every pair consisting of one true and one false hypothesis. It does not need to distinguish hypotheses that agree on the query.

This is weighted set cover over the true/false cross-pair universe. The exact solver uses bitmask dynamic programming for small pair sets; larger cases use a labelled greedy approximation. Pairs that no candidate observation separates are reported explicitly.

## Why query-directed resolution is different

Trial 04 isolates one particular target state from every alternative. Trial 05 resolves only a predicate. For example, a researcher may want to know whether event A preceded event B, without reconstructing every other event relationship.

Suppose two hypotheses both satisfy the query. If they differ on some unrelated part of the state, an observation that distinguishes only those same-side hypotheses does not help answer the question. Trial 05 avoids paying for such unnecessary distinctions.

## Poset example

The test constructs the six linear extensions of two ordered chains:

- C0 precedes C1.
- S0 precedes S1.

The query is whether C0 precedes S0. Three extensions make the query true and three make it false, giving nine true/false hypothesis pairs.

When the candidate observation family contains pairwise comparisons among the other event pairs but omits the direct C0/S0 comparison, two cross-boundary pairs remain observationally indistinguishable:

- (C0, S0, C1, S1) versus (S0, C0, C1, S1);
- (C0, S0, S1, C1) versus (S0, C0, S1, C1).

In each pair, all other pairwise event-order relations agree; only the queried C0/S0 relation differs. No combination of the available non-query comparisons can resolve these pairs. The planner reports them as unresolved. Adding a shared-clock C0/S0 comparison covers the remaining pairs and resolves the query.

This is a constructive example of an information boundary: inference cannot separate hypotheses that agree on every available observation. The missing distinction must enter through a new measurement or an additional justified assumption.

## Exact and approximate optimization

Let p be the number of cross-boundary pairs and m the number of candidate observations. The exact solver has worst-case time O(m * 2^p) and auxiliary space O(2^p). Its dynamic program retains only the least-cost candidate subset for each pair-coverage mask.

Above the configured threshold, the implementation uses deterministic greedy weighted set cover and labels the result non-exact. The planner reports `complete=false` when at least one true/false pair remains indistinguishable under the entire candidate family.

## Verification

GitHub Actions run 54, commit 94a331765be18609436dc55d0982eda0ea9e7982, executed eight tests under Python 3.11.18 on ubuntu-latest. All eight passed.

The tests cover:

- a query already determined by the remaining hypotheses;
- the least-cost observation packet for a Boolean query;
- avoiding unnecessary distinctions within a single query class;
- unresolved cross-boundary pairs;
- the six-extension Poset example and its direct-clock-comparison resolution;
- the greedy fallback label;
- brute-force subset comparisons across 35 deterministic random small instances;
- malformed query, cost, and candidate definitions.

## Boundaries

The input hypothesis set is assumed to contain all relevant remaining possibilities. If the true state is absent, no observation plan over the supplied set can repair that omission.

Candidate observations are treated as deterministic predictions, non-intervening, and additive-cost. Real experiments may be stochastic, sequential, correlated, or state-changing; those require a richer experimental-design model.

A complete plan means the selected predicted observation signatures are sufficient to determine the query across the supplied hypothesis set. It does not mean the observations have been performed, the hypothesis set is exhaustive, or the real-world query has been verified.