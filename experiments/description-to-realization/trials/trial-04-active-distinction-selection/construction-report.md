# Construction report: active distinction selection

**Trial:** 04  
**Brief:** d2r-active-distinction-04  
**Implementation:** attention_selection.py  
**Tests:** test_attention_selection.py  
**Execution receipt:** results/test-encounter.json

## Construction

The planner takes a finite state set, a target, existing observation signatures, and a set of candidate observation functions with positive costs. Equal existing signatures define the target's current equivalence class. Only alternatives in that class need to be distinguished further.

Each candidate observation covers the alternatives whose observed value differs from the target's value. The planner selects a packet whose union covers every separable alternative. Alternatives no supplied candidate distinguishes from the target are returned as unseparable, and the plan is marked incomplete.

## Exact solver

For n coverable alternatives, represent each covered subset as an n-bit mask. Let DP_i[M] be the minimum cost of a subset of the first i candidates whose union covers M. Processing one candidate from a snapshot of the prior table gives the 0/1 recurrence: keep the old cost for M, or add the candidate cost to the best cost for any earlier mask that becomes M after union with this candidate's mask.

The implementation stores the cheapest candidate subset for each coverage mask. A more expensive subset with identical coverage can never improve a later solution, so it is dominated and discarded.

The exact solver has worst-case time O(m * 2^n) and auxiliary space O(2^n), for m candidate observations and n coverable alternatives. The threshold applies to coverable alternatives, not the full state set. Candidate order provides deterministic tie-breaking when represented float costs are exactly equal.

## Greedy fallback

Above the configured exact threshold, the planner repeatedly chooses the candidate with the largest newly covered alternative count per unit cost. This is the standard weighted set-cover greedy rule. Under the model's assumptions—positive additive costs and a coverable finite universe—it has the usual harmonic-number approximation guarantee H_n relative to an optimal cover. It is not generally optimal, so the output reports exact=false and solver=greedy-set-cover.

## Interpretation as active attention

An attention packet is not “observe everything.” It is a costed set of observations selected to resolve one target-relative ambiguity. If the target is already unique, the optimal packet is empty. If some alternative is indistinguishable under every candidate observation, it is reported as unseparable. This gives active attention a concrete operational meaning: allocate observation effort to the distinctions needed for a stated navigation objective.

The objective is target isolation, not full reconstruction of every alternative. Two non-target alternatives may remain mutually indistinguishable after the target is identified.

## Verification

GitHub Actions run 44, commit d7d19046267bfebb5b1fe2c7bc831ed327b303eb, executed ten tests under Python 3.11.18 on ubuntu-latest. All ten passed.

Coverage includes:

- a target already unique under existing observations;
- one observation that isolates the target;
- an exact minimum-cost packet where a cheaper two-observation solution beats a single expensive observation;
- randomized cross-checks against brute-force subset enumeration over 40 deterministic small instances;
- a strict cost comparison where a difference smaller than 1e-12 must still select the lower-cost solution;
- invalid candidate costs, malformed signatures, duplicate names, and invalid thresholds;
- the greedy fallback path;
- an explicitly incomplete result where a remaining state cannot be distinguished;
- restricting effort to the target's existing equivalence class.

## Boundaries

The plan assumes candidate observations are available, non-intervening, and have additive costs independent of order or previous outcomes. Real observations may change the system, have conditional costs, fail, or produce stochastic values. Those cases require a sequential decision or experimental-design model rather than static set cover.

The returned plan is a selection of proposed observations. It does not claim the observations have been performed, that their outputs are known, or that the target has actually been identified in an external system.