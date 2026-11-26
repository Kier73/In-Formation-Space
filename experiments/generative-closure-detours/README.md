# GLA-002 — Representation detours

Follow-up to [GLA-001](../generative-closure-discovery/README.md). The hypothesis is that a temporarily more expensive representation can expose a much cheaper one. This is an independently implemented finite-field experiment, not a claim of faster universal matrix multiplication.

## Algebra

Let D be the invertible first-difference operator (D x)[0]=x[0], (D x)[i]=x[i]-x[i-1] over F_65537. Its inverse is prefix summation. For any matrix A, define E_(r,c)=D^r A (D^T)^c. Then A b=D^(-r) E_(r,c) (D^(-T))^c b. Input reverse prefix sums, sparse multiplication, and output forward prefix sums recover the exact result. No approximation or discarded residual. Row and column differences commute; states can be indexed by (r,c), avoiding redundant paths. The cost for each RHS is exactly 2 nnz(E)+(r+c)(n-1) field operations in this implementation, with additions charged even when accumulating from zero.

## Experiment

Test direct sparse, greedy (strictly improving individual moves), fixed row-only and column-only search, full depth-three lookahead, and a budgeted lookahead. Each candidate transform costs n(n-1) subtractions plus n^2 cell inspections; initial and final encoding each cost n^2 inspections. Selected non-root states are independently reconstructed with inverse transforms and compared coefficient by coefficient, charged n^2 comparisons plus (r+c)n(n-1) additions. Candidate scans, including rejected candidates, are charged. Costs exclude allocation, JS runtime, indexing and storage traffic; not measured time. The budgeted variant stops generating candidates if cumulative candidate cost would exceed the direct application's entire q-column cost; this is a loose upper bound on possible savings, not a guarantee of a profitable search. Every search selects the best visited state including remaining certificate cost; discovery cost is sunk. Direct baseline is sparse multiplication, not the best general matrix algorithm.

Families: two row integrations, two column integrations, one integration on each axis, three row integrations, uniform-ish pseudorandom field entries, identity. Seeded inputs deliberately favor the tested transform vocabulary; the three-row family can wrap modulo the field. Four sizes (16,32,64,128), three seeds, five horizons. Search is not told the input family. Barrier means both immediate neighbors have application cost >= root, yet lookahead selects a multi-step path. Compare total cost including search, not merely the selected representation. No generalization beyond these finite cases is established.

## Reproduce

`node experiment.js > results.json`

Executed the same function in a JavaScript runtime: 6501 product/inverse/commutation comparisons passed, and 628 selected nontrivial representations were coefficient-certified. Raw per-instance results and aggregate means are retained. The finite-difference transform is a classical operation; the contribution is the controlled experiment on search and accounting.

## Next questions

Can a cheap observation predict whether to cross a barrier? Can learned candidate ordering improve the budget without concealing failures? Can the law vocabulary grow to include basis changes, permutations, recurrence operators and mixed representations while retaining exact semantics? Compare against stronger specialized algorithms and measure actual runtime before claiming practical speedup.
