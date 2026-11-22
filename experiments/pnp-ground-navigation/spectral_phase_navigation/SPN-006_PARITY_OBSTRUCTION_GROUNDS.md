# SPN-006 — Gaussian parity obstructions and direct realizable Grounds

**Status:** Exact elementary theorem, executable constructive proof receipts, source-recomputed checker, seeded experiments and explicit negative controls; 21 November 2026 research session (November 22 UTC). This extends [SPN-005](SPN-005_NONLOCAL_RANK_GROUNDS.md), [SPN-004](SPN-004_RANK_GROUNDS.md), and [PNG-001](../README.md). It is an application of established parity linear algebra, not a new general SAT algorithm or proof that P=NP.

## Central result: spectral preferences themselves form a linear system

For the real-valued Walsh polynomial

\[
E(x)=a_0+\sum_{S\ne\varnothing}a_S(-1)^{\langle S,x\rangle},
\qquad L=a_0-\sum_{S\ne\varnothing}|a_S|,
\]

an individual term `a[S]*chi_S` reaches `-|a[S]|` exactly when

\[
\langle S,x\rangle = b_S:=\mathbf 1[a_S>0]\pmod 2.
\]

All termwise preferences are therefore a linear system over `GF(2)` with rows given by *Fourier support masks*, not original clauses.

**Proposition 1 (compatibility ⇔ attainability).** The triangle-inequality lower bound `L` equals the actual global minimum if and only if the nonzero Fourier-support system `S·x=b_S (mod 2)` is consistent.

*Proof.* Every Fourier contribution satisfies `a[S]*chi_S >= -|a[S]|`. Equality in their sum occurs precisely when each term independently achieves equality, i.e. precisely when all the stated parity equations hold simultaneously. Gaussian elimination decides consistency; when consistent, back substitution constructs a full source assignment. The constructed witness has energy `L`, certifying that no lower-energy state exists. QED.

The equivalence is exact and does **not** require low total Fourier rank. Computing the preference solution (given coefficients) uses ordinary bit-matrix elimination, polynomial in the number of sparse coefficients and source bit length. For *incompatible* systems it tells us only that `L` is not tight, not what the true ground energy must be. General SAT remains difficult because its interacting terms often have incompatible preferences.

**Proposition 2 (certified parity obstruction).** Let `C` be a set of distinct nonzero Fourier supports with

\[
\bigoplus_{S\in C} S=0, \qquad
\bigoplus_{S\in C}b_S=1.
\]

For every assignment, at least one term in `C` cannot achieve its individual minimum. Consequently

\[
\sum_{S\in C}a_S\chi_S(x)\ge
-\sum_{S\in C}|a_S|+2\min_{S\in C}|a_S|.
\]

*Proof.* Multiplying all characters in `C` gives `+1` because their XOR support is zero. The characters required to minimize all terms would have product `(-1)^(sum b_S)=-1`, a contradiction. At least one term must flip sign, losing `2|a[S]|` relative to its termwise minimum. QED.

The circuit length is unrestricted. SPN-003 used length three and SPN-005 used length four/rank three; this test spans dependencies whose rank can be much greater than three. Requiring **disjoint Fourier terms** between separately counted obstruction circuits makes the sum of all gains a sound lower bound. These are elementary weighted inconsistent-XOR constraints; no claim is made that greedy extraction gives the strongest possible packing.

## Constructive protocol

`parity_obstruction_grounds.py` contains:

1. **`compatible_preference_ground`**: eliminate the full preferred-sign linear system; if consistent, back-substitute an assignment achieving the exact global Fourier lower bound. If inconsistent, return no witness and label the original bound inconclusive.
2. **`first_inconsistent_circuit`**: Gaussian elimination retaining an *expression over original Fourier terms* for every pivot row. At a contradictory zero row, that expression is an explicit nonlocal XOR relation with odd preferred-sign parity.
3. **`obstruction_bound`**: greedily remove disjoint contradiction circuits, adding `2*min|a[S]|` for each. No quadratic pair enumeration or `2^r` enumeration is needed to validate an obstruction.
4. **`produce_obstruction_receipt`**: witness-first search, SPN-004 rank bounds, then parity-obstruction bounds. If still unresolved, branch with a finite search-node budget, preserving UNKNOWN. The versioned `SPN-006-v1` proof tree contains the source digest, explicit XOR support lists, exact bound, or a directly checked SAT witness.
5. **`verify_obstruction_receipt`**: recomputes rational Fourier coefficients *from the original clauses and each branch restriction* using the existing independent source-expansion kernel. A parity-circuit leaf is accepted only if masks are canonical, source-nonzero, disjoint, XOR to zero, have inconsistent preferred signs, and recompute precisely the claimed strictly positive bound. Source witnesses and split nodes are independently checked. Producer elimination traces and counters are **not** trusted.
6. **`produce_compatible_ground_receipt` / `verify_compatible_ground_receipt`**: a separate `SPN-006-ground-v1` exact-energy receipt. The verifier checks that the explicit full witness's direct clause energy equals a globally valid lower bound *independently* recomputed from original clauses. When the producer cannot establish preference consistency, it emits UNKNOWN rather than guessing a ground state.

All these tests are within the same Python codebase; the rational source-expansion checker is separate from the producer's integer Fourier restriction, but this is **not a separately implemented/language-verified formal kernel**. SHA-256 binds source identity assuming collision resistance.

### Complexity and an important distinction

For `t` nonzero Fourier terms and source variable count `n`, ordinary GF(2) elimination is polynomial in `t` and `n` (Python bitsets make individual row operations inexpensive). The current greedy circuit-packing routine repeats elimination after removing each conflicting circuit and therefore can require roughly `O(t^2*n)` elementary bit work; it is not a linear-time general solver. SPN-004's local rank-block construction also contributes to the proof producer's time. Source Fourier construction has at most `m*2^k` clause-generated terms for fixed clause width `k`, but **the residual SAT proof tree can remain exponential**.

For some structured families, global sign compatibility gives an exact minimum and one concrete original assignment without enumerating `2^rank` parity configurations. For a general CNF, linear inconsistency of termwise preferences does *not* prove the CNF itself is unsatisfiable. It merely supplies a bound correction that may or may not close the proof.

## 120-variable SAT and UNSAT controls

`parity_cycle_cnf(B, frustrated=...)` emits actual width-three clauses for signed four-edge parity cycles, with separated source coordinates. The auxiliary third variable cancels in the final Walsh energy. Each cycle's edge energy is `(1+sign*chi_uv)/2`, yielding exactly `16B` original clauses on `5B` variables.

- When `frustrated=False`, all four edge signs are `+1`, and the parity-preference equations are compatible. With `B=24`, the total Fourier rank is **72**, the original system has 120 variables and 384 clauses, and Gaussian elimination constructs a concrete **zero-energy assignment** without examining `2^72` parity states. The source-derived `SPN-006-ground-v1` receipt independently verifies that the witness achieves the exact lower bound `0`.
- When `frustrated=True`, the final edge sign is `-1`. Each four-edge cycle is incompatible and has minimum energy `1`; there are 24 term-disjoint contradiction circuits. The producer creates **one UNSAT leaf** with a positive root lower bound `24`, verified against the same 384 original clauses. The 120-variable serialized receipt is **2,439 bytes excluding the CNF**.

This is a constructed, decomposable parity family; textbook Gaussian elimination and bounded-treewidth algorithms also solve it efficiently. It is a controlled example of *source problem → discovered compatible coordinate → constructed assignment or obstruction*, not proof of a universal efficient navigation method.

An additional abstract Walsh polynomial supported across seven independent coordinates plus their XOR has an **eight-term** frustration circuit of rank seven. SPN-006 detects and bounds it without a rank-three assumption. This is an abstract polynomial control, not a width-three SAT input.

## Matched random experiment: lower proof cost is not the same as faster search

`parity_obstruction_results.json` uses exactly the same 90 seeded random 3-SAT instances as SPN-004 and SPN-005: 30 each at `(n,m)=(8,34),(10,43),(12,51)`, 256-node budgets, with exhaustive SAT ground truth. **All 90** return the correct SAT/UNSAT decision (69 SAT and 21 UNSAT).

| 90-instance total | SPN-004 local rank | SPN-005 nonlocal pair scan | SPN-006 Gaussian circuits |
| --- | ---: | ---: | ---: |
| Proof nodes | 684 | **576** | 648 |
| Producer + self-check time (one local run) | 920.5 ms | 4,267.9 ms | **822.9 ms** |

The SPN-006 circuit proof sometimes reduces node count, but in this finite random sample it was not as strong as the pair-scanned rank-three closure. Nevertheless its total measured time was much smaller than SPN-005, and slightly lower than SPN-004. This observation is **not a stable runtime speedup claim**. It motivates selecting the certification language and discovery algorithm based on measured work, rather than maximizing bound tightness without accounting for its construction cost.

| Formulas | SPN-004 nodes | SPN-005 nodes | SPN-006 nodes | SPN-006 circuit-bound leaves |
| --- | ---: | ---: | ---: | ---: |
| 30 at `n=8` | 99 | 93 | 97 | 1 |
| 30 at `n=10` | 194 | 170 | 188 | 3 |
| 30 at `n=12` | 391 | 313 | 363 | 12 |

One local run on the structured `B=24` UNSAT formula took about **17.45 ms** for SPN-006 producer plus its source-recomputed checker, versus about 39.05 ms for SPN-005 and 553 ms for the SPN-004 producer under its 64-node budget (which returned UNKNOWN). These timings are sensitive to system load and interpreter; structural proof-node and operation-count measurements are more reproducible.

## Reproduction and negative controls

```
python -m unittest -v test_parity_obstruction_grounds.py test_nonlocal_rank_grounds.py
python parity_obstruction_campaign.py
```

The dedicated SPN-006 tests compare random conditional lower bounds against exact brute-force minima for `n=3..8`, verify additional seeded SAT/UNSAT proof receipts against enumeration, reject malformed/duplicate/frustration-inconsistent proof circuits, forge false SAT or lower-bound claims, test explicit UNKNOWN on exhaustion, construct a rank-72 source SAT witness, and test an abstract high-rank compatible system. The exact-ground verifier rejects a mutated witness or forged energy.

Relevant established work: [analysis of Boolean functions](https://arxiv.org/abs/2105.10386), [testing Fourier dimensionality and sparsity](https://www1.cs.columbia.edu/~rocco/papers/icalp09sparse.html), [Fourier sparsity and dimension](https://theoryofcomputing.org/articles/v015a011/), and [signed-graph frustration](https://mathworld.wolfram.com/FrustrationIndex.html). These are context, not novelty claims for the parity algebra.

## Frontier for SPN-007

The exact algebra is no longer the dominant uncertainty on these controls. The next questions are **which representation to construct first**, and whether transportable Grounds from a large system can be discovered and checked with less work than standard exact inference:

1. Compare SPN-006 with PNG-001's variable-elimination factor frontier on **identical mixed** CNF instances, including parity chains and constraints whose Fourier circuit packing overlaps heavily.
2. Add a stand-alone proof checker with a genuinely separate implementation and a versioned JSON schema. Measure verifier arithmetic, proof bytes, and authenticated transport, independent of the producer's search.
3. Use precise preprocessing ledgers for choosing among clause-local blocks, GF(2) parity propagation, pair-collision closure, and conventional exact inference; test adaptive combinations that do not pay all costs on every branch.
4. Study whether the desired *observer property* permits still smaller exact interfaces than full SAT energy or #SAT counts, preserving unknown results when equivalence is unproved.

**Checkpoint:** a problem can generate a useful parity coordinate and a verified realizable result when its signed preferences are compatible. The cost and scope of discovering that coordinate remain explicit; no universal polynomial-time SAT algorithm follows.
