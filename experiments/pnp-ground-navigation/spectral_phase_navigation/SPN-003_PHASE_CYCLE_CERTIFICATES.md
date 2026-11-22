# SPN-003 — Frustrated Walsh cycles as independently checkable UNSAT certificates

**Research stage:** 21 November 2026 (America/Toronto). Python standard library; fixed-width, three-distinct-variable CNFs. Companion to [SPN-001/002](README.md) and [PNG-001 factor-frontier grounds](../README.md).

**Question.** Can relations *among* signed spectral coefficients shrink the amount of branching needed to demonstrate that no satisfying assignment exists? More generally, can an observer use an efficiently computable compatibility invariant, instead of treating each measured Fourier component as an independent degree of freedom?

**Status.** A sound stronger lower bound, source-bound proof receipts, and reproducible finite tests are implemented. This is a classical algebraic optimization/certification technique adapted to the spectral-Ground experiment, **not a new general SAT algorithm, an NP-versus-coNP resolution, or a quantum speedup**. The producer and source-recomputation checker remain within one experimental Python codebase; no separately formalized verifier is claimed.

## 1. Exact theorem: a phase-cycle penalty

Let `a[S]` be the rational Walsh coefficient of a real function `E` on `{0,1}^n`, with `χ_S(x)=(-1)^(sum_{i in S}x_i)`. All nonconstant supports `S` are nonzero bitmasks.

**Proposition (three-term frustrated cycle).** Suppose `S`, `T`, `U` are distinct nonzero supports with `U = S xor T` and `a[S] * a[T] * a[U] > 0`. For every Boolean assignment `x`, the sum of these three terms is at least

\[
-|a_S|-|a_T|-|a_U| + 2\min(|a_S|,|a_T|,|a_U|).
\]

*Proof.* The Walsh characters satisfy `χ_S χ_T χ_U = χ_(S xor T xor U) = 1` on **every** assignment. Independently minimizing each `a_A χ_A` would require `χ_A = -sign(a_A)`; their product would be `-sign(a_S a_T a_U) = -1`. This is impossible because their actual product is `+1`. Thus at least one term must fail to attain its independent minimum. A sign mismatch raises that term's value by `2|a_A|`, at least `2*min(|a_S|,|a_T|,|a_U|)`. This proves the inequality. For distinct nonzero `S,T`, the two characters are linearly independent over `F_2`, so the four possible sign patterns show the three-term bound is exact in isolation. QED.

**Corollary (term-disjoint cycle packing).** Let `P` be any set of triples satisfying the proposition, with no Fourier support used in two triples. Then for every assignment,

\[
E(x)\ge L_{\mathrm{cycle}} := a_\varnothing
    - \sum_{S\ne\varnothing}|a_S|
    + \sum_{(S,T,U)\in P}2\min(|a_S|,|a_T|,|a_U|).
\]

*Proof.* Apply the proposition to each triple and the termwise absolute-value bound to the unselected terms; add. **Variables may overlap between triples.** Only the *Fourier terms* must be disjoint, to avoid double-counting their correction. QED.

Since clause-violation energies are nonnegative integers, **`L_cycle > 0` is a complete certificate of UNSAT for the restricted branch**. A non-positive bound is `UNKNOWN`, not SAT.

The algorithm enumerates candidates from pairs of observed nonzero Fourier supports and looks up their XOR, retaining those with positive amplitude product. It greedily selects high-gain disjoint triples. No optimality is asserted for the greedy packing; **any valid packing yields a sound lower bound**, including the empty set. With `t` nonzero Fourier supports, simple enumeration is `O(t^2)` plus up to `O(t^2 log t)` sorting and `O(t)` storage for the selected packing. Exact integer arithmetic and coefficients are used. For width three, source expansion costs `O(8m)` coefficient updates per node, but proof-tree size remains potentially exponential in `n`.

This is a finite instance of **frustration**: local preferred signs cannot jointly arise from any global Boolean assignment. Other familiar formulations of incompatible local assignments and cycle inequalities exist; the research contribution here is a typed, exact spectral Ground with an explicit source-recomputation certificate and a measured branching comparison.

## 2. A finite separating example

For variables `a,b,c`, construct an energy independent of `c`:

\[
E(a,b,c)=2+\chi_a+\chi_b+\chi_{\{a,b\}}.
\]

The values are `5` when `a=b=0`, and `1` for every other `(a,b)`, irrespective of `c`. It is a perfectly valid three-variable 3-CNF energy: include the unique clause forbidden at each 3-bit assignment five times for the two assignments with `a=b=0` and once for each of the other six assignments (16 clauses total). Thus every assignment violates at least one clause and the formula is UNSAT.

The old bound says `L_triangle = 2 - (1+1+1) = -1` and cannot certify the root. The phase-aware bound uses one triple `(a,b,a xor b)` and says `L_cycle = 2-3+2 = 1`; it certifies UNSAT **without splitting**. On this exact input, SPN-002 visits 3 nodes, while SPN-003 certifies at the root (1 node).

### Scalable but structurally easy family

Take `B` independent copies of the 16-clause block, on `n=3B` variables and `m=16B` clauses. The old root bound is `-B`; the new bound is `+B`, witnessed by `B` disjoint phase cycles. The entire receipt contains `B` triples, requiring only linear growth. At `B=32` (`n=96`, `m=512`), SPN-002 returns `UNKNOWN` after exceeding a 256-node exploration budget, while SPN-003 returns a **single, independently source-recomputed UNSAT certificate with 32 triangles**. Its compact serialized JSON receipt has 1,849 bytes (not counting the original 512-clause input).

This example is deliberately decomposable; conventional bounded-width factor elimination (PNG-001) also solves it efficiently. It illustrates the gain of maintaining phase compatibility over a *phase-blind lower bound*, not a separation from existing SAT algorithms.

## 3. Proof-producing execution

`phase_cycle_bounds.py` has four proof node kinds, source-bound using SHA-256 of the canonical ordered clauses:

- `sat`: an explicit complete assignment checked against the original clauses;
- `phase_cycle_bound`: a positive reduced rational lower bound plus a list of three-term Walsh cycles;
- `split`: both 0 and 1 branches checked recursively; only two UNSAT branches imply UNSAT;
- `unknown`: explicit budget refusal.

**Independent of the producer's coefficient table and greedy packing**, the verifier reconstructs exact *rational* Walsh amplitudes directly from the original clauses under each proof prefix (`independent_residual_coefficients` in SPN-002). For each reported triple it validates nonzero distinct supports, XOR identity, positive amplitude product, and term non-reuse; it then recomputes the complete rational lower bound and requires a strict positive value equal to the claimed ratio. This verifies the producer's *chosen* packing, not the packing's optimality. Forged bounds, bogus XOR triples, reused terms, forged SAT witnesses, wrong formula digest, and unsupported proof nodes are rejected in tests. As in SPN-002, trust in the hash assumes collision resistance and the verifier is not a formally proved kernel.

**Observation/verification distinction:** a promising pattern from coefficient magnitudes is only an observation. The actual phase triple and the arithmetic certificate are admitted as verified only relative to the explicitly described checker; an exhausted budget retains `UNKNOWN`.

## 4. Reproducible comparison against the previous stage

Commands from this directory:

```bash
python -m unittest -v test_spectral_receipts.py test_phase_cycle_bounds.py
python phase_cycle_campaign.py
```

All tests use Python standard library, deterministic seeded sampling and exact arithmetic. `phase_cycle_results.json` records one local campaign with seed `73176`, 256-node budgets, and independent exhaustive assignment truth tables for each random formula (`n` up to 12). No unverified extrapolation is intended.

| n | m | cases | SAT/UNSAT | SPN-002 total proof nodes | SPN-003 total proof nodes | instances with fewer nodes | UNSAT improved |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 8 | 34 | 30 | 24 / 6 | 205 | 105 | 7 | 6 of 6 |
| 10 | 43 | 30 | 23 / 7 | 430 | 206 | 9 | 7 of 7 |
| 12 | 51 | 30 | 22 / 8 | 915 | 441 | 10 | 8 of 8 |
| **Total** | | **90** | **69 / 21** | **1,550** | **752** | **26** | **21 of 21** |

The results were equal and correct in all 90 cases. Root phase correction was strictly positive in all 90 sampled cases, but this does **not** imply the root bound was strong enough to certify every UNSAT formula. The greedy SAT witness heuristic is unchanged, so most SAT cases have equal proof node counts. **The stronger bound does more work per visited node** (candidate pair enumeration and sorting); a reduction in nodes is *not* by itself a speedup or asymptotic cost claim.

Validation additional to the campaign: six SPN-003 unit tests passed; they include 180 random restricted formulas (`n=3..8`) with a direct exhaustive check that each lower bound is at most the true minimum over completions, 100 additional random SAT/UNSAT receipt comparisons (`n=5..8`), the 96-variable structured certificate, and negative controls. Six pre-existing SPN-002 tests also pass.

## 5. A deeper structural proposition: parity rank, not support span

The cycle bound is rank-two. More generally, take a set of `t` nonzero Walsh supports `S_1,...,S_t`. If their binary span over `F_2` has rank `r`, then every joint sign pattern of these `t` characters is determined by `r` basis parities. All `2^r` assignments to those basis parities are achievable by full Boolean states (because the independent linear parities define a surjective map onto `F_2^r`). Therefore **the exact minimum of this selected spectral block can be computed by enumerating `2^r`, not `2^n`, possibilities**, no matter how many original variables appear in its supports.

This is an elementary linear-algebra fact, and it suggests a new operational unit for the broader observer-ground work: a **rank-bounded phase-compatible block**, whose independent checker verifies the basis, the term set, and its exact minimum. If such blocks form a term partition, the sum of exact block minima again yields a sound global lower bound. It may strengthen cycle packing where several interacting triangles overlap on their Fourier supports. But the rank `r` or number/size of blocks may still grow, and discovering a good partition has a cost. This proposed stage is not yet a running implementation.

## 6. Continuing research

1. Implement **SPN-004 rank-bounded block certificates**: exact GF(2) rank bases, `2^r` evaluation, proof receipt, source-recomputation checker; compare fixed budgets `r=2,3,4` against cycles and factor-frontier width.
2. Study how phase-certificate term count, rank, factor-treewidth, and solver conflicts diverge on planted, parity/XOR, random, and adversarial families. Include adversarial examples where the triangle packing yields *no* useful correction.
3. Generalize from fixed-width-three clauses to heterogeneous clause widths, without hardcoding the denominator 8. Keep exact rational arithmetic and strict admission of unknown.
4. Design a language-independent verification kernel and independently execute it across two hosts; account for all bytes, arithmetic and preprocessing rather than only navigator transitions.

**Guiding question:** when does the structure that makes an intended state realizable also provide a *cheaply constructible and checkable coordinate* for reaching or excluding that state? The phase-cycle theorem is one narrow, falsifiable step toward answering it.