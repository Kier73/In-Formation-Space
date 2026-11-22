# SPN-004 — Rank-bounded parity Grounds and constructive realization

**Status:** Exact theorem, executable rank-three block proof receipts, independently source-recomputed verification, exhaustive small-instance checks; 21 November 2026. Companion to [SPN-003 phase-cycle certificates](SPN-003_PHASE_CYCLE_CERTIFICATES.md) and [PNG-001 factor-frontier grounds](../README.md).

**Research question:** When a desired result is represented by a signed Fourier description, can the observer construct a small *compatible parity coordinate* in which an exact minimization and a checkable proof are tractable, despite a much larger source variable space?

No claim is made to resolve P versus NP, to establish a quantum acceleration, or to invent the classical Fourier transform, XOR linear algebra, or bounded-rank optimization. The distinctive experimental contribution here is an explicit source-preserving representation, proof-producing rank-bounded decomposition, executable witness reconstruction, and measured comparison with the preceding spectral receipts.

## 1. Formal result: exact minimization depends on the Fourier rank

Write a real pseudo-Boolean function in signed Walsh form

\[
E(x) = a_\varnothing + \sum_{S\in\mathcal S} a_S (-1)^{\langle S,x\rangle},
\quad x\in\mathbb F_2^n,
\]

where the finite set `S` contains distinct, nonzero bitmasks, and the inner product is over `F_2`.

**Proposition 1 (rank Ground).** If the linear span of `S` has rank `r`, the exact minimum of `E` can be calculated by examining exactly `2^r` parity coordinates; one minimizing full `n`-bit assignment can then be reconstructed by solving `r` linear equations over `F_2`.

*Proof.* Choose a basis `B_1,...,B_r` of the support span. Every observed character `χ_S` is a product of a unique subset of the basis characters. Therefore `E(x)` factors through the linear map `x -> (<B_1,x>,...,<B_r,x>)`. Since its `r` rows are independent, the map is surjective onto `F_2^r`: each of the `2^r` parity coordinates has at least one full Boolean preimage. The minimum over `x` is thus exactly the minimum over `2^r` basis coordinates. Ordinary GF(2) elimination constructs one full preimage of the minimizing coordinate, proving realizability. QED.

The arithmetic costs are bounded by `O(2^r t + poly(n,r,t))` given a sparse list of `t` signed coefficients, plus the cost of deriving those coefficients. This is fixed-parameter tractability in *known Fourier-support rank*, not polynomial-time unrestricted SAT. The necessary rank can be linear in `n`, and obtaining a useful Fourier description can itself be difficult for general formulas.

`exact_rank_ground()` implements this full-landscape theorem with a user-selected rank budget. On an abstract polynomial whose masks reference variable indices 0 through 120, a rank-three support was minimized exactly and a 121-bit witness reconstructed without enumerating `2^121` states. This deliberately uses an **abstract high-degree Walsh polynomial**, not a claim to have generated such supports from the fixed-width-three SAT compiler.

## 2. Block form: certified exclusion without solving the full global rank

The whole spectrum can have large rank even when it decomposes into *term-disjoint* low-rank blocks. Partition selected nonconstant Fourier terms into blocks `B_j`, with no Fourier support used more than once. Let `m_j` be the exact minimum of `sum_{S in B_j} a_S χ_S`, computed by the rank theorem. Then

\[
\boxed{ E(x)\ge
 a_\varnothing-\sum_{S\ne\varnothing}|a_S|
 +\sum_j\left[m_j+\sum_{S\in B_j}|a_S|\right]. }
\]

*Proof.* Apply the exact block lower bound to each selected block and the triangle inequality to all unselected terms, and sum. Intersections of **variables** between blocks do not invalidate the bound; only reuse of the exact same Fourier *term* is forbidden. QED.

A strictly positive bound certifies UNSAT for the corresponding restricted original CNF. A weak or nonpositive bound says only `UNKNOWN` until further navigation or a witness.

**Implemented producer heuristic (rank caps 2 and 3):** enumerate candidate positive phase triangles from SPN-003; additionally form a closure of the observed nonzero Fourier supports contained in each original three-variable clause scope, retaining candidates with GF(2) rank at most three. Compute each candidate's exact minimum via `2^r` parity configurations. Select high-gain candidates greedily without reusing Fourier terms. Because greedy rank-three packing can displace multiple useful triangles, also compute the SPN-003 packing and choose whichever yields the larger certified bound. This guarantees *bound dominance* over SPN-003 for the same coefficients; it does **not** produce an optimal global block partition or discover arbitrary nonlocal rank-three subspaces.

For `m` width-three clauses and `t` nonzero Fourier terms, this finite heuristic uses `O(m t)` clause-local candidate scans and up to `O(t^2 log t)` positive-cycle candidate enumeration/sorting (with small `2^3` block evaluations). Per-node work is larger than SPN-003; an exponential number of proof nodes is still possible.

## 3. Two separating constructions

### A. Four-term parity circuit: no eligible triangle

Take three independent characters `u=χ_a`, `v=χ_b`, `w=χ_c`. Since `χ_{abc}=uvw`, consider

\[
E = 3 + u + v + w - uvw.
\]

Every assignment has energy **1 or 5**, so `E_min=1`. This is a valid 24-clause width-three CNF energy: include the clause uniquely violated by each 3-bit assignment with multiplicity equal to that assignment's energy.

The four nonconstant supports are `{a,b,c,abc}`. No two XOR to one of the other two, so SPN-003 finds **no** three-term phase cycles. Its root bound is `3 - 4 = -1`, inconclusive. All four supports, however, have rank three, and their exact block minimum is `-2`. Thus the SPN-004 root bound is `3 + (-2) = 1`, proving UNSAT without branching. It captures a **four-term dependency invisible to all three-term probes on the same support set**.

### B. Seven nonzero characters in three dimensions

The seven nonzero characters of `F_2^3` comprise a rank-three support. Set

\[
E = 2 + \sum_{\varnothing\ne S\subseteq\{a,b,c\}}\chi_S.
\]

The energy is 9 at `000` and 1 at the other seven assignments, yielding a valid 16-clause width-three CNF. All seven nonconstant coefficients are `+1`. There are many eligible SPN-003 triples, but any two rank-two planes in `F_2^3` intersect in a nonzero Fourier support, so a disjoint-triangle packing captures at most one: its root lower bound is `2 - 7 + 2 = -3`, inconclusive. The exact *rank-three* block minimum of all seven terms is `-1`, giving ground bound `2 - 1 = 1`, a complete UNSAT certificate.

Repeat this block on `B` independent triples of source variables: `n=3B` and `m=16B`, with `B` term-disjoint rank-three blocks. SPN-004's source-recomputed certificate has one root proof node and `B` blocks, with lower bound `B`. At `B=32` (96 variables, 512 clauses), SPN-003 returns `UNKNOWN` after its 256-node budget and SPN-004 certifies `UNSAT` with 32 blocks and 3,929 serialized JSON bytes excluding the input formula. The family is explicitly decomposable and easy for standard bounded-treewidth elimination, so this is **not** a general SAT complexity breakthrough.

## 4. Proof receipts and verification

`rank_block_bounds.py` implements `produce_rank_receipt()` and `verify_rank_receipt()`. Its four proof node kinds are `sat`, `rank_block_bound`, `split`, and `unknown`. Receipts include version, a canonical formula SHA-256, a declared rank cap, status, and producer cost counters. The builder maintains integer Walsh coefficients scaled by 8; the verifier rebuilds exact **rational** Fourier coefficients from the original clauses and the claimed branch prefix using SPN-002's separate source-expansion routine.

For each proposed block the verifier checks canonical nonempty distinct masks, no term reuse, nonzero source-derived coefficients, exact GF(2) rank within the declared budget, and exact `2^r` block minimum; it recomputes the full rational lower bound and demands a positive value equal to the claimed rational numerator/denominator. SAT witnesses are checked clause-by-clause. The verifier accepts `UNKNOWN` but never mistakes it for UNSAT. Negative-control tests reject false bounds, repeated terms, unsupported rank caps, missing terms, forged digest and false SAT witnesses.

This is **source-recomputation independence**, not a separately written or formally proved proof kernel; the producer and checker still share some Python linear-algebra routines. SHA-256 names input bytes subject to usual collision-resistance assumptions. The rank-two/three proof grammar does not assert that its search can always close.

## 5. Experiment record and cost accounting

Reproduce from `experiments/pnp-ground-navigation/spectral_phase_navigation`:

```sh
python -m unittest -v test_spectral_receipts.py test_phase_cycle_bounds.py test_rank_block_bounds.py
python rank_block_campaign.py
```

The tests are pure Python standard library with deterministic seed values. Eight SPN-004 unit tests pass, including 180 randomly restricted formulas (`n=3..8`) checked for exact bound consistency and exhaustively compared against true minimum energy, 100 additional exact SAT/UNSAT receipt checks (`n=5..8`), tamper rejection, and a 121-coordinate abstract Walsh witness. The previous 12 tests still pass. This is a finite test suite, not independent formal verification.

`rank_block_results.json` records one seeded experiment (`seed=73176`, bounded search budget 256), on **the identical 90 random 3-SAT inputs** used to compare SPN-002/003, with exhaustive assignment truth tables as ground truth:

| n | m | sampled instances | SAT / UNSAT | SPN-002 nodes | SPN-003 nodes | SPN-004 rank-3 nodes | rank-3 better than cycles |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 8 | 34 | 30 | 24 / 6 | 205 | 105 | 99 | 2 |
| 10 | 43 | 30 | 23 / 7 | 430 | 206 | 194 | 5 |
| 12 | 51 | 30 | 22 / 8 | 915 | 441 | 391 | 8 |
| **Total** | | **90** | **69 / 21** | **1,550** | **752** | **684** | **15** |

All 90 decisions agree with brute-force truth tables. No instance was worse in *proof nodes*, because SPN-004 takes the larger of its own block bound and the prior cycle bound before branching. This says nothing by itself about CPU time: rank-three block construction and checking take additional arithmetic. For other data, finding a good decomposition may dominate the computation. The example is neither representative of general worst-case hardness nor evidence that fixed small rank is typical near larger random SAT thresholds.

## 6. Related research and next tests

- Ryan O'Donnell, [*Analysis of Boolean Functions*](https://arxiv.org/abs/2105.10386): Walsh characters and algebra on the Boolean cube.
- [FourierSAT](https://akyrillidis.github.io/pubs/Conferences/FourierSAT.pdf) (related Fourier-based Boolean constraint minimization) and [hybrid constraints in continuous Fourier space](https://www.sciencedirect.com/science/article/pii/S0004370221001107). The work here makes no novelty claim about Fourier-based SAT or optimization generally; its emphasis is *exact, source-bound verification* and the rank-bounded decomposition experiment.
- [Fourier Sparsity and Dimension](https://zesty.cs.uchicago.edu/articles/v015a011/) and [Tight Chang's-Lemma-Type Bounds](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.FSTTCS.2021.10): published theory of Fourier-support dimension/rank; no general low-rank promise is implied by our small experiments.

**Next research stages:**

1. Discover **nonlocal** low-rank Fourier blocks without requiring their support to lie inside a single source clause. Measure candidate-generation work and verify block partitions independently. A sparse but high variable-span algebra may be the valuable case.
2. Build a standalone verification kernel (separate implementation/language), with canonical receipt schema compatible with VGI's provenance semantics and E-CPU's authenticated execution receipts. Bound proof-file size, byte transport, arithmetic and reconstruction costs independently.
3. Compare GF(2) rank, factor-treewidth, proof width, Fourier support size, and work/preprocessing on *the same* adversarial families, including XOR chains, highly connected instances and mixed widths. Preserve `UNKNOWN` when an intended subspace is not found.
4. Extend rank caps beyond three and choose partitions with a measurable budget; avoid hiding exponential candidate discovery or `2^r` enumeration behind a navigation label.

**Central distinction:** a solution space's size, the rank of a relevant observable, the cost of *discovering* that observable, and the cost of independently verifying its realization are four different computational quantities. Navigation is genuinely efficient only when all required stages are accounted for.