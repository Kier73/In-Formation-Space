# SPN-005 — Nonlocal rank-three Fourier Grounds from pair-XOR collisions

**Status:** Executable, reproducible research; 21 November 2026 research session (November 22 UTC). Companion to [SPN-004](SPN-004_RANK_GROUNDS.md), [SPN-003](SPN-003_PHASE_CYCLE_CERTIFICATES.md), and [PNG-001 factor frontiers](../README.md). Standard-library Python, exact arithmetic, and a source-recomputed proof checker. No resolution of P versus NP is claimed.

## Research question

Can a small exact computation space be *discovered* from interacting Fourier terms even when those terms do not fit in any one original clause? Does the cost of discovering that space outweigh the saved SAT proof search?

### Proposition: four-term nonlocal frustration

Let `a[S]` be nonzero real Walsh coefficients and let four **distinct** nonzero supports `S,T,U,V` obey `S xor T xor U xor V = 0`. The characters satisfy `χ_S χ_T χ_U χ_V=1` for every Boolean assignment. If `a[S]a[T]a[U]a[V]<0`, independently minimizing the four contributions would require character signs with product `-1`, an impossibility. Therefore

\[
\sum_{Q\in\{S,T,U,V\}} a_Q \chi_Q(x) \ge -\sum_Q |a_Q| + 2\min_Q |a_Q|.
\]

More generally, the four supports have GF(2) rank three. Enumerating the eight compatible parity configurations gives their **exact** combined minimum, potentially stronger when the rank-three span contains additional observed terms. This is classical XOR linear algebra, signed-graph frustration for pairwise supports, and finite Fourier analysis; the experiment's contribution is the proof-producing, cost-accounted use of these facts on source-derived SAT energies.

The four supports may reference more than three variables and may be in different source clauses. No dependency on their *literal variable-span* enters the eight-state exact minimum. The representation is nevertheless sparse and fully source-dependent; detecting its useful subspaces can remain difficult.

## Algorithm and verifiable receipt

`nonlocal_rank_grounds.py` adds:

- `nonlocal_four_circuits(coeff, pair_budget, candidate_budget)`: examine pairs of nonzero support masks, index by XOR, and identify collisions `S xor T = U xor V`. Reject repeated terms; retain only sign-frustrated four-circuits. For each, evaluate the four-term subset and all observed nonzero terms in its GF(2) rank-three span. Candidates retain a measured gain over independent coefficient minima. Enumeration is ordered by pair-index gap to spread a partial scan across the Fourier list, but no optimal discovery guarantee follows.
- `nonlocal_rank_bound`: combine candidates with SPN-004's clause-local blocks and SPN-003 triangles; greedily select non-reused Fourier terms. Retain at least the prior SPN-004 bound. Stop when a local certificate already establishes UNSAT; do not spend extra discovery work to prove what is proved.
- `produce_nonlocal_receipt`: first try a *directly checked* SAT witness; otherwise attempt certified lower bounds and bounded branching. Receipt `SPN-005-v1` contains the canonical input hash, the actual proof tree, rational bounds, block masks, and producer-only cost counters. `UNKNOWN` is retained on budget exhaustion.
- `verify_nonlocal_receipt`: independently regenerate exact rational restricted Fourier coefficients from original clauses, then invoke the existing SPN-004 rank-block proof checker on a versioned envelope. The producer's candidate enumeration, stored coefficients and performance claims are not trusted by the verifier. This is source-recomputation independence, **not** a separately implemented or formally verified kernel.

A rank-three block verifies by at most `2^3=8` parity assignments. Term-disjoint lower bounds can be combined even when the blocks share original variables. Certificate checking does **not** assume that the presented blocks were the best partition.

**Discovery complexity:** with `t` nonzero terms there are `t(t-1)/2` possible pairs. Pair and candidate budgets explicitly truncate enumeration; the examined XOR collisions and minimum evaluations are billed, not declared free. Dense collision buckets are sampled up to an explicit constant `bucket_limit`; the resulting heuristic is incomplete but sound. The full SAT search tree can still be exponential.

## Separating CNF construction

`parity_cycle_cnf(B, span_layout=True, frustrated=True)` constructs `B` disjoint signed four-edge cycles as genuine width-three clauses. Each edge uses a third auxiliary bit `z`, and includes four clauses (two forbidden pair patterns × two `z` bits), yielding exactly

\[
E_{uv}(x)=\tfrac12(1+\sigma_{uv}\chi_{\{u,v\}}(x)).
\]

Choosing three edge signs `+1` and the fourth `-1` frustrates the cycle. The complete energy per cycle has constant coefficient `2`, four edge coefficients of magnitude `1/2`, and minimum **1**, independently of the auxiliary bit. The Fourier supports form a four-term XOR dependency but **no single width-three source clause contains all four supports**. The SPN-004 clause-local rank-three heuristic has a root bound of `0`; SPN-005 discovers a rank-three block whose minimum raises that bound to `1`.

For `B` cycles, `n=5B` and `m=16B`. Strided placement locates each connected cycle's source variables far apart in the bit coordinate order. The decomposition is deliberately easy for conventional exact solvers; it is a **separating test for the previous spectral discovery heuristic**, not an adversarial lower bound against SAT algorithms.

| `B` | `n` | Local SPN-004 (64-node budget) | SPN-005 (same budget) | Pair scans at root |
| ---: | ---: | --- | --- | ---: |
| 1 | 5 | UNSAT, 7 nodes | UNSAT, 1 node | 6 |
| 2 | 10 | UNSAT, 15 nodes | UNSAT, 1 node | 28 |
| 4 | 20 | UNSAT, 63 nodes | UNSAT, 1 node | 120 |
| 8 | 40 | UNKNOWN | UNSAT, 1 node | 496 |
| 16 | 80 | UNKNOWN | UNSAT, 1 node | 2,016 |
| 24 | 120 | UNKNOWN | UNSAT, 1 node | 4,560 |

The 120-variable receipt consists of one UNSAT leaf with 24 rank-three blocks and bound `24`, independently checked from 384 original clauses. Its compact serialized receipt is 2,587 bytes *excluding the source CNF*. The remaining result size and discovery costs are not free.

## Matched random control and the cost of finding a coordinate

`nonlocal_rank_results.json` records one seeded run (`73176`), 30 formulas for each `(n,m)=(8,34),(10,43),(12,51)`, 256-node budget, compared against SPN-004 and exhaustive truth tables. All 90 are correctly classified (69 SAT, 21 UNSAT). The following times include each producer's self-verification and are **not calibrated timing benchmarks**:

| Random cases | SPN-004 nodes | SPN-005 nodes | SPN-004 ms | SPN-005 ms |
| --- | ---: | ---: | ---: | ---: |
| `n=8`, 30 | 99 | 93 | 108.8 | 439.3 |
| `n=10`, 30 | 194 | 170 | 259.0 | 1,251.2 |
| `n=12`, 30 | 391 | 313 | 568.2 | 2,731.3 |
| **90 total** | **684** | **576** | **936.0** | **4,421.8** |

This is a **negative control against confusing smaller proof trees with lower total execution cost**. SPN-005 reduced nodes but spent materially more time on general random instances because it scanned 242,391 Fourier-term pairs, evaluated 132,939 block minima and considered 1,063,512 parity states (summed over visited search nodes). The number of examined Fourier pairs and the number of parity states are measured independently.

Witness-first admission avoids the additional spectral discovery scan for SAT witnesses found immediately; the heuristic still spends too much time on many UNSAT branches. There is no evidence of a general complexity breakthrough.

## Tests and next action

```
python -m unittest -v test_nonlocal_rank_grounds.py
python nonlocal_rank_campaign.py
```

Seven dedicated tests include 120 randomly restricted CNFs checked against exhaustive minima, 60 additional randomized receipt checks against exhaustive SAT classification, 120-bit nonlocal receipt reconstruction, tampering, duplicate Fourier-term rejection, and hard budgets that return UNKNOWN.

The strongest next hypothesis is that *testing all termwise preferred parities for consistency* may yield contradictory circuits in near-linear-algebra cost, avoiding quadratic pair scanning. This is developed separately as [SPN-006](SPN-006_PARITY_OBSTRUCTION_GROUNDS.md).
