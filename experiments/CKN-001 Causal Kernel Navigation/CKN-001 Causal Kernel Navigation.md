# CKN-001 — Causal Kernel Navigation: *invest memory into causality*

- **Status:** Experiment, Verified within the finite checks listed below. Theory sections are labelled Inference / Hypothesis.
- **Lineage:** E-CPU `law_certifier` navigation, Latent Path Capacity (CAPACITY-001), PATH-GROUND-004 observation equivalence; In-Formation-Space `guarded-shortcut-tradeoff`, `fluid-in-transit-computation` (FIT-001), `passive-orbit-cache`.
- **Scope:** One process, one machine, numpy. **No network is touched.** "Path", "segment" and "arrival" in Tier D are in-process simulations of message order, not measurements of a real link.
- **Reproduce:** `python run_ckn.py` (≈20 s, writes `results.json`).

## 1. The idea in one sentence

Store **what a span of time does** (a *causal kernel*: the transfer function of 2^k steps, or the complete orbit structure), and stop storing **what the state is**. Once memory holds causality, a request for "the state at time t" or "the first time output = y" becomes an act of **interpretation** (composing or indexing kernels), not **iteration**.

## 2. Formalism (Inference)

Let a process be a map f: S → S. Its future is fixed by f alone, so every orbit x, f(x), f²(x), … exists before anyone runs it. This is the "platonic" layer.

| Object | Meaning | Cost to use |
|---|---|---|
| state x_t | *where* the system is | iterate: Θ(t) |
| causal kernel K_k = f^(2^k) | *what 2^k ticks do* | navigate: ≤ popcount(t) compositions |
| rho atlas (tail h, cycle λ, entry e, phase) | *the whole orbit, seen once* | forward O(1), inverse O(log), "never" proofs |

**Navigability criterion.** A Ground is navigable when kernels stay *compact under composition*, i.e. the description size |f^t| grows much slower than t. Then

  cost(navigate to t) ≈ popcount(t) · cost(compose) + cost(investment),

and description beats iteration once queries Q satisfy investment / Q < cost(iterate t) − cost(query).

**The rho theorem.** Any deterministic map on a finite set is eventually periodic. Every orbit is a tail of length h(x) followed by a cycle of length λ. So for a finite machine, "general processing" means navigating a finite functional graph, and one complete *look* at that graph (the atlas) pays for all of time.

## 3. Results (Observation / Verified)

### Tier A — algebraic Ground: Rule 90, 1,000,003 cells, t = 10^18
Rule 90 is linear over GF(2)[S]. Frobenius gives (S + S⁻¹)^(2^k) = S^(2^k) + S^(−2^k), so **the kernel of 2^k steps is two dots**. Navigation connects the dots once for each set bit of t.

| | value |
|---|---|
| kernel operations for t = 10^18 | 24 (= popcount) |
| navigation time | **3.7 ms** |
| direct iteration | ~6,100 steps/s → **≈5.2 million years** |
| bit-ops: iterate vs navigate | 10^24 vs 2.4·10^7 |
| check 1: direct iteration, 44 checkpoints t < 3000 | 0 mismatches |
| check 2: independent Lucas/Kummer oracle (16.7M submask terms per cell, 25 cells at t = 10^18) | all agree |
| check 3: semigroup f^(a+b) = f^b∘f^a at a ≈ 7·10^17 | holds |

### Tier B — no algebra: a branching, nonlinear 22-bit program (4,194,304 states)
A 16-instruction machine (two 9-bit registers plus a PC) with conditional branches, rotations, and a non-invertible B ← B²+1. No shortcut law is assumed; we just look at the entire state space once.

| atlas | value |
|---|---|
| build (every state) | **1.0 s** |
| structure found | 4 cycles (lengths 2079, 547, 195, 25); 2,846 cyclic states; max tail 2,305; basins 2.50M / 1.69M / 4.7k / 2.9k |
| forward query f^t(x), t ≈ 10^18 | **1.6 µs** (iterating with a lookup table: ≈3,600 years) |
| inverse query: first t with register A = y | **≈100 µs**, *including proofs of "never"* |
| repayment | the build pays for itself after ≈9 queries at horizon 10^6 |

Verification:
- At t ∈ {10^18, 2^61−1, 10^12+7, 3000, 2305} the atlas matches an independent whole-map function power by repeated squaring, for **all 4,194,304 states**.
- For 8,192 random (x, y) pairs, 60,000 steps of direct iteration gave 0 forward mismatches and 0 inverse disagreements.
- 5,483 queries returned a first-hit time. **2,709 were answered "never, for any t"**, and direct iteration covered each of those orbits completely (h + λ < 60,000), confirming the never-claims.

Observing the whole orbit once let the system answer questions about *infinite* time. That is the inverse query from §1: navigating to the moment the output matches.

### Tier C — negative control: the size of causality
This tier measures the algebraic normal form of the centre cell after t steps, as a function of its 2t+1 light-cone bits:

| t | Rule 90 deg / monomials | Rule 150 | Rule 30 | Rule 110 (universal) |
|---|---|---|---|---|
| 1 | 1 / 2 | 1 / 3 | 2 / 4 | 3 / 4 |
| 4 | 1 / 2 | 1 / 3 | 7 / 122 | 8 / 72 |
| 7 | 1 / 8 | 1 / 11 | 13 / 4,852 | 12 / 1,724 |
| 8 | 1 / **2** | 1 / 3 | 15 / 23,094 | 15 / 5,136 |

- **Linear rules:** the causal description stays degree 1 and periodically collapses back to a few dots at powers of two. For Rule 90 the count is exactly 2^popcount(t).
- **Rule 30 and Rule 110:** the description grows about 3–4× per step.

Observation: compact kernels exist where the rule's algebra permits them. Hypothesis: for universal rules they generally do not. The time-hierarchy theorem guarantees some computations admit no shortcut, so *no* system can navigate everything. The E-CPU's real job is to **find reducible pockets** (Grounds) and route the irreducible remainder through honest iteration.

### Tier D — causality is composition order (late binding)
- A 4.19M-character stream is cut into 256 segments that "arrive" in shuffled order.
- Each segment is summarized **before its start state is known**: for every one of the 12 KMP-automaton states, it records an end state and a match count, 192 bytes in total.
- Summaries compose associatively: (A then B)[q] = (B.end[A.end[q]], A.cnt[q] + B.cnt[A.end[q]]).

| method | matches of "abracadabra" |
|---|---|
| independent substring search | 3180 |
| sequential automaton | 3180 |
| shuffled arrival, tree-composed by causal index | **3180** |
| left fold | 3180 |
| **composed in arrival order (negative control)** | **3134** (wrong: seam-straddling matches lost) |

- Late binding holds: the same composite answers start states 4, 7 and 10, each checked by direct runs.
- Energy and time trade off directly: the work multiplier is ×12 (= |Q|), and the critical path shrinks from 4,194,304 to 16,392 steps.
- **All 256 segments synchronized:** each segment's end state was independent of its start state, so the automaton forgets its past within one segment. Only the seam counts carry causal memory across. This is the fading-memory property from reservoir computing, appearing in a symbolic system.

## 4. Interpretation (Inference / Hypothesis)

1. **Memory into causality.** Tier A stores kernels, Tier B stores one complete look at the orbit, and Tier D stores per-segment transfer functions. In each case the memory holds *how the past causes the future*, and answering a query becomes reading rather than running.
2. **Time is energy, made countable.** The ledger is bit-operations. Iteration spends ∝ t. Navigation spends a one-off investment plus ∝ popcount(t), or O(1) per query. Out-of-order processing spends ×|Q| energy to buy ÷K latency. The investment is stored potential: paid once, released every time a query uses it.
3. **Observation without takeover.** Every tier only *reads* f, a stream, or arrival order. In the eye analogy, the light supplies information and timing, and meaning arises from the interpreter's lens (algebraic kernel, atlas, automaton). The interpreter still needs a reliable signal, and Tier D shows the order must be preserved or reconstructed from causal indices.
4. **The Putnam guard.** The lens is fixed and declared before observation: f, the automaton, and the ANF basis. The decoder is never fit to the answer. Tier C is the guard's teeth: it shows where a fixed compact lens *fails*.
5. **Synchronization as compression (Hypothesis H-CKN-1).** If a stream's interpreter is synchronizing, a segment summary collapses from |Q| entries toward O(1) plus a short seam correction. Testable next: measure summary entropy versus segment length across automata, and relate it to reset-word length (Černý).

## 5. Limits

- These are finite checks on chosen instances: one VM program, one ring size, ANF up to t = 8. Not universal proofs.
- Atlas cost scales with |S| = 2^bits. It is tractable to roughly 2^26–2^30 states on commodity memory, not for real CPU state spaces. Larger machines need *composed* atlases (product, quotient or decomposition structure). That is the open frontier, not a solved step.
- Nothing here measures a physical network, energy in joules, or remote hosts.

## 6. Next experiments (proposals)

- **CKN-002 Composed atlases:** build atlases of subsystems and navigate their product using Krohn–Rhodes / cascade decomposition, beating 2^bits.
- **CKN-003 Kernel discovery:** given only black-box f, search for a lens (linear over GF(2), affine mod m, permutation conjugacy) using bounded probes and certify it on the whole domain, as CAPACITY-001 does for affine maps.
- **CKN-004 Synchronization compression:** H-CKN-1 above.
