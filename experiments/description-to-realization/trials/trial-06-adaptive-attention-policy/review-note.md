# Supplementary review: Trial 06 cost and optimality claims

## Static baseline correction

The original report compared the adaptive expected cost 1.5 with a static packet containing all three low-cost observations at cost 3.0, and with a direct sensor at cost 2.5. That is not the minimum static packet among the available candidates.

The two branch-specific refinement observations alone resolve all true/false hypothesis pairs:

| Hypothesis | Left refinement | Right refinement | Query |
|---|---|---|---|
| A | yes | same | true |
| B | same | yes | true |
| C | no | same | false |
| D | same | no | false |

Thus the cheapest static packet costs 2.0. The adaptive policy costs 1.5 in expectation and 2.0 in the worst branch. The adaptive advantage is therefore 0.5 cost units, or 25% relative to this static baseline, under the uniform prior and additive deterministic costs in the fixture.

A new test enumerates all subsets of the four observation candidates and verifies that 2.0 is the minimum static cost. The comparison no longer relies on choosing a non-minimal static packet.

## Worst-case cost semantics

The solver chooses observations by minimizing expected cost under the supplied prior. It then records the worst-case path cost of that expected-cost-optimal policy. It does not independently minimize worst-case cost. A separate minimax solver would use a second Bellman objective and may choose a different policy.

## Recurrence justification

The subset recursion is acyclic: every chosen observation partitions a non-terminal finite hypothesis set into at least two non-empty strict subsets. Each recursive child is therefore smaller than its parent. The memoized Bellman recurrence terminates by induction on subset size. No contraction-mapping claim is required.

## Disposition

Preserve the original run and evaluation as lineage, but use the corrected static baseline, the expected-versus-minimax distinction, and the strict-subset termination argument in subsequent descriptions.