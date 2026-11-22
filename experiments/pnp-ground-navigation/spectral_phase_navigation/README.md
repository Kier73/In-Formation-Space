# SPN-001/002 — Phase-preserving spectral restriction and proof-carrying SAT navigation

**2026-11-21 · exact arithmetic · Python standard library · experimental research**

Companion to [PNG-001](../README.md), which implements an exact #SAT frontier/factor-elimination Ground. Here we study a *different representation*: signed Walsh characters of a fixed-width clause-violation energy. We ask whether exact transformations of that description can yield a witness or a separately checkable proof of exclusion, while explicitly charging for construction, branching and verification.

**No general polynomial-time SAT algorithm, P-vs-NP claim, or quantum speedup is established.** Conditional expectation and exhaustive proof branching are classical techniques; the experiment makes their evidence and costs explicit in the spectral/observer-ground framing.

## 1. Exact description and phase

For a 3-clause that is violated when bits on distinct indices `v=(i,j,k)` equal forbidden pattern `b=(b_i,b_j,b_k)`, its violation indicator is

\[
2^{-3}\prod_{v\in\{i,j,k\}}(1+(-1)^{b_v}\chi_{\{v\}}(x)),\qquad
\chi_S(x)=(-1)^{\sum_{i\in S}x_i}.
\]

Therefore \(E(x)=\sum_S \widehat E(S)\chi_S(x)\), and a representation as integer `c[S]=8*E_hat(S)` requires at most `8m` nonzero construction events for `m` three-literal clauses. Coefficient **signs** must be retained; squared magnitudes are not a complete observation.

### Finite counterexample: identical Fourier magnitudes, opposite SAT answers

All eight length-three clauses correspond to a unique forbidden assignment. Use the number of copies in each row as the clause multiplicity:

| Forbidden assignment (binary `x2 x1 x0`) | A | B |
|---|---:|---:|
| 000 | 0 | 1 |
| 001 | 1 | 1 |
| 010 | 1 | 1 |
| 011 | 2 | 1 |
| 100 | 1 | 1 |
| 101 | 2 | 1 |
| 110 | 2 | 1 |
| 111 | 1 | 3 |

Both have ten clauses, \(\widehat E(\varnothing)=5/4\), and \(|\widehat E(S)|=1/4\) for every nonempty `S`. Each has degree-wise power `(3/16, 3/16, 1/16)` and \(\kappa_2=6/7\). Nevertheless A is satisfiable (`000`) and B is unsatisfiable (`E_min=1`). The signed coefficients differ; the third centered moments are `-3/32` and `21/32` respectively. This is an exact, exhaustive finite counterexample to **power-only** sufficiency, not to using the full signed Fourier representation.

The general phase-sensitive cubic statistic is

\[
\mathbb E[(E-\mathbb E E)^3]
=\sum_{S,T:\,S,T,S\triangle T\ne\varnothing}
\widehat E(S)\widehat E(T)\widehat E(S\triangle T).
\]

It captures interactions between coefficients lost by degree-wise power. Its distinguishing ability here does **not** imply it decides arbitrary SAT.

### Correct interpretation of the random-width expectation

For independent uniformly signed random width-`k` clauses, \(\mathbb E[W_w]=m{ k \choose w}4^{-k}\); this raw expectation scales with clause count `m`. The *ratio of expectations* is \(\sum_{j=1}^w {k\choose j}/(2^k-1)\). It does not follow that an individual instance's low-degree power is statistically independent of its satisfiability.

## 2. Restrict without enumerating the hypercube

On fixing variable `i` to bit `b`, exact signed coefficients transform by

\[
\widehat E_{i=b}(S)=\widehat E(S)+(-1)^b\widehat E(S\cup\{i\}).
\]

This is an exact source-preserving transformation for all subsets `S` of remaining variables. It operates on at most `m*2^k` clause-generated terms (fixed-width `k`) without constructing the full `2^n` energy array. Repeated restrictions use a deterministic phase-preserving conditional-mean heuristic and directly verify the final assignment against the original clauses.

**Proposition (conditional expectation).** If a restricted energy has mean \(\mu\), choosing each next bit with no greater conditional mean returns a full assignment `x` with \(E(x)\leq\mu\). When \(\mu<1\), integer/nonnegative clause energies guarantee that assignment satisfies all clauses. When \(\mu\geq1\), a failed greedy path is *not* a proof of UNSAT.

**Proposition (spectral lower bound).** For every completion of a partial assignment `p`,

\[
E_p(x)\ge L_p:=\widehat E_p(\varnothing)
-\sum_{S\ne\varnothing}|\widehat E_p(S)|.
\]

Thus \(L_p>0\) gives a sound UNSAT certificate for that restricted branch. The triangle bound can be very weak; failure to obtain `L_p>0` is **UNKNOWN**.

## 3. SPN-002 typed receipts and independent checking

`produce_receipt` constructs a finite proof tree with four node kinds:

- `sat`: complete explicit witness, evaluated against the original clauses by the checker;
- `positive_lower_bound`: exact reduced rational lower bound, recomputed independently by expanding *residual original clauses*, not trusting the producer's stored Fourier coefficients;
- `split`: both assignments of one free variable are checked; only two UNSAT children entail UNSAT, while either SAT child proves SAT;
- `unknown`: valid explicit refusal when the search-node budget is exceeded.

A canonical, ordered source-formula digest binds a receipt to the intended CNF. Hash identity is conditional on collision resistance; it is not a proof of formula equivalence. The verifier never accepts a claimed status merely from the producer's label. A receipt can be checked with only the original clauses, integer/rational arithmetic, and clause evaluation; nevertheless the verifier and builder are in the same experimental codebase and have not undergone independent formal verification.

A certificate for B above requires **five producer nodes**: a split on the first variable, one already-positive branch, and another split whose two leaves are positive. A receives a direct verified witness.

**Complexity account:** constructing sparse coefficients costs `O(m*2^k)` arithmetic and space up to `O(m*2^k)` terms, fixed k; one restriction costs at most linear in the current term count. Proof-tree exploration can use exponentially many nodes. The independent checker re-expands original clauses for each positive leaf, at `O(m*2^k)` per such leaf, plus witness evaluation. Serialized receipts and proof construction are charged separately from the original CNF description. No global polynomial bound follows.

## 4. Reproduction

From this directory:

```sh
python walsh_phase_navigation_probe.py
python -m unittest -v test_spectral_receipts.py
python spectral_receipts.py
python campaign.py
```

All commands use the Python standard library (tested locally on Python 3.11+). In the initial exact probe, 300 seeded random `n=8,m=30` 3-SAT cases produced 279 SAT formulas under exhaustive truth-table verification; greedy navigation returned a witness for 250. This is a small seeded sample, not a runtime scaling claim.

The SPN-002 tests: **6 passed**; 135 additional random 3-SAT formulas (`n=5..7`) were compared against exhaustive SAT ground truth, with all 135 receiving correct SAT or UNSAT receipts at budget 512, and tampering/UNKNOWN controls passed. The seeded `campaign.py` experiment, with a 256-node budget, produced:

| n | m | samples | exhaustive SAT/UNSAT | receipt SAT/UNSAT/UNKNOWN | avg/max nodes visited |
|---:|---:|---:|---:|---:|---:|
| 8 | 34 | 40 | 31 / 9 | 31 / 9 / 0 | 7.58 / 31 |
| 10 | 43 | 40 | 26 / 14 | 26 / 14 / 0 | 20.48 / 71 |
| 12 | 51 | 40 | 33 / 7 | 33 / 7 / 0 | 24.48 / 137 |

A full reference enumeration was used only for these small tests. These are observations on sampled formulas, not proofs of average-case or worst-case efficiency. For large formulas, a budget miss MUST remain `UNKNOWN`, not `UNSAT`.

## 5. Research continuity

This work answers only a first finite step of the question:

> Can relations among spectral components determine a sequence of transformations that constructs a satisfying state—or produces a verifiable explanation of why none exists—without materializing the full state space?

1. **Established:** Fourier magnitudes alone cannot decide SAT, even at identical individual-coefficient magnitudes; signed coefficients can be exactly restricted; the receipt grammar is sound relative to the independent checker for this restricted width-three model.
2. **Observed:** the produced witnesses, bound leaves and split proofs check successfully on the small stated instances, including explicit negative controls and a budget refusal.
3. **Not demonstrated:** a polynomial bound on search-tree nodes, uniformly short UNSAT certificates, tight positivity bounds, high-width generality, independence from the implementer's code, or an efficient path for arbitrary SAT.
4. **Next experiments:** measure bound strength and branch-tree size against PNG-001 factor-frontier width on identical planted, random, XOR, and adversarial families; expose algebraic structures where direct phase relations and factor elimination produce smaller exact interfaces; design a standalone verifier executable in a separate language or proof assistant; then attempt source-hash-bound receipts across independent hosts. Account for all communication bytes and preprocessing.

### Spectral and adiabatic interpretation

The companion conversation also studied \(H(s)=(1-s)H_B+sH_P\). For a degenerate final ground set of size `d>1`, the quantity \(\lambda_d-\lambda_0\) is not automatically the spectral gap controlling a unique-state adiabatic theorem; determining `d` can itself require counting. Nothing in this experiment uses a physical quantum Hamiltonian or infers a quantum acceleration from the positivity of a chosen indexed spectral separation.


## 6. Continued spectral-phase research (SPN-003 through SPN-006)

The initial SPN-001/002 source-derived Fourier engine has four additional,
standalone reproducible research stages:

- [SPN-003: three-term frustrated-phase certificates](SPN-003_PHASE_CYCLE_CERTIFICATES.md) — XOR triangle inequalities and source-recomputed receipt checks.
- [SPN-004: rank-bounded parity Grounds](SPN-004_RANK_GROUNDS.md) — exact `2^r` local minimization, term-disjoint decomposition, and witness lifting.
- [SPN-005: nonlocal rank-three discovery](SPN-005_NONLOCAL_RANK_GROUNDS.md) — exact four-term dependencies crossing source-clause scopes, with pair-scan budgets and explicit discovery costs.
- [SPN-006: Gaussian parity obstructions and realizable Grounds](SPN-006_PARITY_OBSTRUCTION_GROUNDS.md) — reconstruct exact minimizers when all signed term preferences agree; otherwise extract contradictory parity circuits and source-check their lower bounds.

All stages use pure standard-library Python, preserve `UNKNOWN` when a bounded
search cannot establish a claim, and count proof search separately from
coordinate discovery and checking. The parity constraints exploit a special
algebraic structure: **none of these experiments settles general P versus NP**.

Run the current regression suite from this directory:

```sh
python -m unittest -v test_spectral_receipts.py test_phase_cycle_bounds.py test_rank_block_bounds.py test_nonlocal_rank_grounds.py test_parity_obstruction_grounds.py
python nonlocal_rank_campaign.py
python parity_obstruction_campaign.py
```
