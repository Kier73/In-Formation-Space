# CKN-002 — Composed atlases: navigating state spaces no table can hold

- **Status:** Experiment. All checks listed below passed in a staged run (see *Provenance*). Theory sections are labelled Inference / Hypothesis.
- **Lineage:** CKN-001 (rho atlas, kernel navigation); E-CPU `law_certifier`, Latent Path Capacity; In-Formation-Space `guarded-shortcut-tradeoff`.
- **Scope:** one process, one machine, numpy. The "sender → receiver" coupling is an in-process model of a symbol stream, **not** a network measurement.
- **Reproduce:** `python run_ckn2.py` (writes `results_ckn2.json`; about 1–2 min, about 0.5 GB RAM).

## 1. Question

CKN-001's atlas looks once at *every* state, so its cost is |S| = 2^bits. Real systems are combinations of parts. Can we look at each part once and navigate the whole, so memory grows with the **sum** of the parts rather than the **product**?

Two combination laws are tested:

| Law | Coupling | Joint states here | What is stored |
|---|---|---|---|
| **Product** | independent parts run side by side | 8 × 20 bits = **2^160** | 8 atlases (8.4M entries) |
| **Cascade** | a sender drives a receiver through a 4-bit port: (a, b) → (f(a), g(σ(a), b)) | 20 + 20 bits = **2^40** | sender atlas + one *period-return map* per sender cycle |

## 2. Formalism (Inference)

**Product.** For independent parts, the state after t steps is each part's own state after t steps. A joint observation "all parts show their targets at the same moment" becomes a set of congruences: for t ≥ max tail, part i matches iff t mod λᵢ ∈ Rᵢ, where Rᵢ is a finite residue set read off its atlas. The first joint occurrence is a **Chinese-remainder problem over residue sets**:
- a solution gives the first time;
- an empty intersection is a **proof that it never happens**.

Memory is Σ|Sᵢ| instead of Π|Sᵢ|.

**Cascade (period-return map).** Let the sender sit on a cycle C of length λ with base point a₀. Going once around C applies a fixed sequence of λ symbols to the receiver, so one sender period acts on the receiver as one map

  H_C = g(σ(a_{λ−1}), ·) ∘ … ∘ g(σ(a₀), ·),

the transformation accumulated by going once around a loop, in the spirit of monodromy/holonomy. Then for any t:
1. walk the sender's tail and align to a₀ (at most h + λ steps);
2. apply **H_C^m** for the m whole periods in one look, using an atlas of H_C;
3. walk the remainder r < λ.

The dots are the sender's period boundaries, and the line between two dots is H_C. Build cost is p_C · |B| element-steps, where p_C is the **minimal period of the symbol stream the receiver actually perceives**, not the sender's state period.

> **The receiver pays for the period of what it perceives, not for the size of the sender.**

## 3. Results

### 3a. Product machine — 2^160 states
Components were chosen by a rule fixed before any query: the first 8 seeds ≥ 1000 with ≤ 12 cycles and a longest cycle ≥ 300. The atlases build in 7.7 s total, and their cycle lengths include 2276, 948, 773, 768, 627, 540, 384, 339.

| Check | Result |
|---|---|
| Forward jumps: 300 joint states × t ∈ {12345, 10^18, 2^89+7, 10^30+3} vs Brent cycle-detection oracle | **0 mismatches**; 5.2 µs per joint query |
| Joint first-occurrence, 2–4 parts, **complete sieve** over the whole joint period (400 queries) | **400/400 agree**: 211 first hits, **189 proofs of "never"**, 12 answered in the pre-periodic window |
| Joint, all 8 parts, independent targets (200) | **198 proofs of "never"**, 2 hits at t ≈ 10^11.4 and 10^12.3; all sound; 200/200 agree with oracle-derived residues |
| Joint, all 8 parts, *realizable* targets (what the machine shows at a random far time T*, median 10^20.4) (200) | **200/200 found and sound**, all ≤ T*; first occurrence median **10^12.0**, max 10^14.9; joint period median 10^14.2; up to 2,500 residue classes; **7.3 ms** per query |

**Why "never" dominates (Observation + Inference).** For independent targets the median expected match density is 10^−15.6 per step, so a joint period usually contains no solution at all. Coincidences across independent subsystems are rare, and the atlas makes their absence *provable* rather than merely unobserved. When the target is a real joint observation, its first occurrence usually lies about 8 orders of magnitude earlier than the time it was sampled from.

### 3b. Cascade — 2^40 states, sender → receiver
- **Sender:** seed 1010, cycles 540 / 158 / 76 / 26, max tail 2,296.
- **Receiver:** the first seed ≥ 5000 whose period-return map over the sender's longest cycle keeps a receiver cycle ≥ 50, i.e. a receiver that is *not* entrained. That was seed 5000.

| | |
|---|---|
| period-return maps, all 4 sender cycles | built in **3.5 s** (the 26-cycle's symbol stream has period 13, which halves its cost) |
| receiver after one period | 2^20 → **131,072 = 2^17** states; 20–30 receiver cycles, longest **57,107 periods** |
| longest joint period | up to **25.6 million** steps |
| query at t = 10^18 | **0.46 ms**; iterating would take ≈ **15,400 years** at 488 ns/step |
| memory | flat joint atlas ≈ **22 TB**; composed atlas **189 MB** |
| V1: brute-force joint iteration, 4,096 starts × 120,000 steps, 3,500 checked queries | **0 mismatches** |
| V2: *every* receiver state (2^20) for every sender cycle at t = 10^18 and 2^61−1, atlas jump vs independent repeated squaring of the period-return map | **all match** |
| V3: splitting the jump, f^(a+b) = f^b∘f^a at random phases, 300 trials | **0 mismatches** |

### 3c. What one period does to a receiver (Observation)

| Receiver | Bits erased in the first period | Period map on what remains | Reading |
|---|---|---|---|
| 5000 | **exactly 3.000** (2^20 → 2^17) on every sender cycle | **bijective** (a permutation of the 2^17-state core) | erases once, then **reversible** at period resolution: it keeps 17 bits of its own past forever |
| 5001 | ≈ **4.09** | **idempotent** (H∘H = H) on the two main sender cycles | **entrained**: after one period its state at period boundaries is frozen; the sender's phase alone decides what it shows |

Hypothesis H-CKN-2: receivers split into two archetypes, *interpreting* (erase-then-permute) and *entrained* (erase-then-freeze), detectable from one period-return map via two invariants: image size and bijectivity versus idempotence on the image. In Landauer terms, the erasure (and hence the irreducible energy cost) happens **once, in the first period**. Afterwards an interpreting receiver's period dynamics is reversible. This counts bits, not joules.

### 3d. Admission budget (negative control)
Holonomy cost = (perceived symbol period) × |receiver|, with a budget of 2·10^10 element-steps:

| Case | Cost | Decision |
|---|---|---|
| receiver reads one sender (period 540) | 5.7·10^8 | **admitted** |
| receiver reads the XOR of three senders (period bound lcm = 2.4·10^8) | ≤ 2.5·10^14 | **refused**: the minimal XOR period is not computed, so the system refuses rather than guesses |
| flat joint atlas of 2^40 states | 1.1·10^12 entries, 22 TB | **refused** |

## 4. Interpretation (Inference / Hypothesis)

1. **Independence is free; coupling direction is what costs.** Products compose at sum cost, and cascades at sum cost × perceived period. Mutual coupling (A reads B *and* B reads A) is not handled here. That strongly connected case is where a composed atlas is not known to beat 2^bits, and it is the open frontier.
2. **Perception sets the price.** The receiver never needs the sender's state, only the period of the symbols it observes. A huge sender with a short-period output is cheap, and a small sender whose output mixes long cycles is expensive. This is the eye analogy made quantitative: cost is set by what is distinguishable at the receiver, not by the source's complexity.
3. **Never as a first-class answer.** In the product machine most joint questions have provable negative answers. An observer-host that can certify "this joint observation does not occur at any time" is answering about all of time from a finite look.
4. **Memory into causality, again.** The period-return map is a causal kernel one level up. CKN-001 stored what 2^k steps do, and CKN-002 stores what one period of the sender does to the receiver.

## 5. Limits

- Finite checks on chosen instances: 8 product components, 1 sender, 2 receivers. Selection rules are stated and were fixed before queries, but they do select for non-degenerate dynamics.
- Residue-class sets can blow up (cap 4M classes, then refuse). The worst case seen was 3,420.
- Holonomy cost compounds in deep cascades: level 3 pays for level 2's joint period.
- Nothing here measures a real network, timing, or energy.

## 6. Provenance

The numbers in `results_ckn2.json` were produced by executing this script's sections in order inside one interpreter. Section 2 was run twice and the second run is recorded. `holonomy_structure` was computed by the same code in a separate call. Afterwards the script was edited to reduce memory (memoryview lookups, array-backed Brent sequences, reusing the driver atlas). Those edits were smoke-tested against the oracles on one component (0 mismatches) and the file compiles, but **the final file has not yet been run end to end**. Run it once (locally or in CI) before upgrading this experiment's label to Verified. Random-query statistics will differ slightly between runs. All structural results (cycles, holonomy images, bits erased) are deterministic.

## 7. Next

- **CKN-002b — deep cascades:** sender → relay → receiver; measure how perceived periods compound, and whether entraining relays cut the cost (an entrained relay's output period collapses to its sender's).
- **CKN-002c — weak feedback:** the receiver returns k bits to the sender; treat it as a product over 2^k feedback contexts and find where that stops beating 2^bits.
- **CKN-002d — cascade inverse queries:** "first t at which the receiver shows y", using residues over the joint cycle λ·μ.
- **H-CKN-2:** survey many receivers and classify interpreting vs entrained by the two invariants.
