# CKN-003 — Spectral navigation: what the critical line can and cannot carry

- **Status:** Experiment, verified end-to-end in a single clean run (25 s). Theory sections are labelled Inference / Hypothesis.
- **Lineage:** CKN-001/002 (causal kernels, residue/CRT navigation). On 20 Nov 2026 Levent Alpöge announced a claimed proof of the Riemann hypothesis developed with Claude, accompanied by Lean code. The present experiment does not establish or independently check that proof; its use of Schoenfeld's bound remains explicitly conditional on RH for this experiment.
- **Scope:** one process, numpy and the standard library only, no external zero tables, no network.
- **Reproduce:** `python run_ckn3.py` → `results_ckn3.json` and `zeta_zeros_t6000.npy` in this directory. The binary array is shared with sibling CKN-003c (see [series index](../CKN-INDEX.md)).

> **External theorem status, 21 Nov 2026:** Independent verification of the Alpöge/Claude announcement is being reported (see [MIT verification notes](https://math.mit.edu/~drew/grh/)), but the claimed proof and its wider mathematical acceptance are outside this experiment. A computed zero list, Gram-point checks, and 300 samples do not prove RH, zero completeness, or a general approximation error bound.

## 1. Question

CKN-002 navigated finite machines through **residues**: integer periods, exact answers via the Chinese remainder theorem, and proofs of "never". The primes have a second, **spectral** description. In the explicit formula

  ψ(x) = x − Σ_ρ x^ρ/ρ − log 2π − ½ log(1 − x⁻²),  ρ = ½ + iγ,

each zero contributes an oscillator x^½·e^{iγ log x}. The zeros form a fixed oscillator bank, and the primes are its interference pattern (a reservoir with a linear readout).

**Can encoding along the critical line offload memory into procedural generation?** Two kinds of question are tested:
- **local:** where exactly are the primes?
- **aggregate:** how large is ψ(x)?

## 2. The zeros (Observation / Verified)

The zeros were computed from scratch:
- a Riemann–Siegel scan of Z(t) on a 0.01 grid, up to t = 6000;
- each zero then refined by bisection with an *independent* Euler–Maclaurin evaluation of ζ(½+it).

| Check | Result |
|---|---|
| zeros found, t < 6000 | **5,598**, each with a sign change of Z confirmed by the independent evaluator, so each lies on the critical line |
| vs published values (γ₁…γ₁₀, γ₁₀₀, γ₁₀₀₀) | max error **3.3·10⁻¹⁰** |
| completeness: zero count below each "good" Gram point must equal n + 1 | **5,190 good Gram points, 0 deviations** |
| closest pair | gap 0.043 |

The completeness check is Gram/Rosser-style evidence, not a full Turing certificate. A missed pair would show up as a persistent count deficit of 2 after it, and none appears.

## 3. Local question: exact prime locations

**Decoder** (Putnam guard: fixed in advance, not fit to answers):
- D(n) = ψ_K(n+½) − ψ_K(n−½) with a cos² taper on the zeros;
- call n a prime power iff D(n) > ½ log 2.

Three tapers were tried and all are reported; cos² was the best.

| zeros K | height T | primes recovered **exactly** up to | n₀ / T | prime powers |
|---|---|---|---|---|
| 125 | 279 | 41 | 0.147 | 20 |
| 500 | 813 | 101 | 0.124 | 36 |
| 1000 | 1420 | 179 | 0.126 | 55 |
| 2000 | 2517 | 311 | 0.124 | 81 |
| 4000 | 4508 | 569 | 0.126 | 125 |
| 5598 | 6000 | **807** | 0.135 | 162 |

The log-log slope of n₀ against T is **0.96**. **Local resolution is linear in height: n₀ ≈ 0.13·T.** Taper choice matters (K = 2000: sharp 179, Fejér 191, cos² 311).

**Precision needed** (K = 2000; Gaussian noise added to every γ):

| noise ε | 0.1 | 0.03 | 0.01 | 0.003 and below |
|---|---|---|---|---|
| exact up to | 9 | 89 | 307 | 311 (no further gain) |

ε ≈ 0.01 suffices, so about **6.6 bits per zero** if the zeros are stored as gaps. Inference: a perturbation δγ shifts the phase by δγ·log x, so the requirement is δγ ≪ 1/log x.

**Accounting** (Inference, from the measured numbers):
- 5,598 zeros × 6.6 bits ≈ **37,000 bits** recover the primes up to 807.
- A bitmap needs 807 bits, or 403 for odd numbers only. That makes the zeros **46× larger**.
- A sieve program of a few hundred bytes regenerates the same primes.

Since zeros needed grow like T log T while the bitmap grows like T, the ratio grows like log x. **The critical line is not a compression of local prime data.**

## 4. Aggregate question: ψ(x) for x ∈ [10⁶, 10⁷] (300 random points)

The sampled values satisfied the numerical inequality corresponding to the **RH-conditional** Schoenfeld bound at all 300 points. Its worst ratio was 0.071, so even with **zero** zeros the smooth generator x lands within 7% of that conditional reference bound in the sampled range.

| zeros K | rms error / √x | max error / RH bound | median bits beyond the RH bound |
|---|---|---|---|
| 0 | 0.205 | 0.071 | 6.0 |
| 10 | 0.140 | 0.058 | 6.6 |
| 100 | 0.082 | 0.028 | 7.2 |
| 1000 | 0.039 | 0.013 | 8.4 |
| 5598 | **0.020** | 0.0078 | **9.3** |

- rms error ∝ K^−0.32, so each 10× increase in zeros adds about one bit.
- At x = 10⁷, 5,598 terms give an rms error of **65**, against an RH bound of 32,688. The exact answer needs a sieve of 10⁷ elements.
- **The spectral query's cost depends on K, not on x.**

Hypothesis H-CKN-3: the same K terms keep an error of order 0.02√x at much larger x, possibly growing slowly with log x. This was tested only up to 10⁷.

## 5. Interpretation (Inference / Hypothesis)

1. **Two kinds of navigation.**

   | | Residue (CKN-002) | Spectral (CKN-003) |
   |---|---|---|
   | clocks | integer periods λᵢ | frequencies γ (believed linearly independent) |
   | return | exact (lcm) | never exact, only near-returns |
   | answer | exact, including proofs of "never" | approximate; compared against an **RH-conditional bound for ψ(x) − x**, not a certified truncation-error bound |
   | best for | coincidences, phases | sizes, densities, counts |

2. **The ½ is a memory exponent.** RH puts every oscillator at amplitude x^½. The smooth generator x supplies the leading half of the bits of ψ(x) for free, and the remaining ~√x scale is what has to be stored or computed. Spectral terms cut it slowly (≈1 bit per decade of K), and only the sieve removes it entirely.
3. **An uncertainty principle on the critical line.** Being band-limited at height T in log-frequency means positions are resolved only to Δx ≈ x/(0.13·T). Global questions are cheap and local ones are expensive, which is the same split CKN-001 Tier C found: compact descriptions exist for aggregate observables, while local detail is irreducible.
4. **Answer to "encode systems along the critical line":** it works for *aggregate observables of systems already governed by ζ*, with procedural generation plus a proven error floor. It cannot store arbitrary local data. The zeros are completely fixed, so they have no free capacity, and a counting argument rules out compressing arbitrary data with any fixed generator.

## 6. Limits

- Zeros only up to t = 6000, x up to 10⁷, and three tapers tried. The decoder is simple; better deconvolution would raise 0.13, but would hand more work to the interpreter.
- The completeness check is not a full Turing proof.
- Information accounting uses the measured sufficient precision (ε = 0.01) and gap coding. Other codings shift the constants, not the log x growth.

## 7. Next

- **CKN-003b:** test H-CKN-3 at x ≈ 10¹²–10²⁰ against published π(x)/ψ(x) values.
- **CKN-003c — mixed navigation:** answer a query with smooth generator + K zeros + a short exact sieve window only where the spectral error leaves ambiguity. Measure total cost against a pure sieve and a pure spectral approach.
- **Bridge:** a residue clock built from a primitive root g mod p has period p−1, with g found within GRH's proven search limit. Combine residue clocks (exact phases) with spectral estimates (sizes) in one navigator.
