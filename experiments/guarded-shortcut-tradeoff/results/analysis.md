# Empirical Analysis: Guarded Shortcut Trade-off

**Experiment:** `guarded-shortcut-tradeoff`  
**Run ID:** `exp:guarded-shortcut:2026-11-11`  
**Date:** 2026-11-11  
**Encounter Artifact:** [`tradeoff-encounter.json`](tradeoff-encounter.json)  
**Hardware / OS:** Windows 11, Python 3.14.0  

---

## 1. Measured Data

The table below records the empirical timing (in microseconds) across 12 coordinates from $t = 10$ to $t = 5,000,000$ steps:

| $t$ (steps) | $c_{\text{exec}}$ (Raw) | $c_\sigma$ (Shortcut) | $c_g$ (Guard) | $N = c_\sigma + c_g$ | Speedup | Result Verified |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **10** | $1.70\,\mu\text{s}$ | $2.40\,\mu\text{s}$ | $2.20\,\mu\text{s}$ | $4.60\,\mu\text{s}$ | **0.4×** | Match |
| **50** | $9.60\,\mu\text{s}$ | $3.60\,\mu\text{s}$ | $3.20\,\mu\text{s}$ | $6.80\,\mu\text{s}$ | **1.4×** | Match |
| **100** | $16.20\,\mu\text{s}$ | $3.70\,\mu\text{s}$ | $3.40\,\mu\text{s}$ | $7.10\,\mu\text{s}$ | **2.3×** | Match |
| **500** | $83.20\,\mu\text{s}$ | $5.60\,\mu\text{s}$ | $4.90\,\mu\text{s}$ | $10.50\,\mu\text{s}$ | **7.9×** | Match |
| **1,000** | $161.50\,\mu\text{s}$ | $6.00\,\mu\text{s}$ | $7.70\,\mu\text{s}$ | $13.70\,\mu\text{s}$ | **11.8×** | Match |
| **5,000** | $902.30\,\mu\text{s}$ | $7.60\,\mu\text{s}$ | $6.90\,\mu\text{s}$ | $14.50\,\mu\text{s}$ | **62.2×** | Match |
| **10,000** | $1,799.30\,\mu\text{s}$ | $8.20\,\mu\text{s}$ | $7.30\,\mu\text{s}$ | $15.50\,\mu\text{s}$ | **116.1×** | Match |
| **50,000** | $8,649.10\,\mu\text{s}$ | $8.60\,\mu\text{s}$ | $7.80\,\mu\text{s}$ | $16.40\,\mu\text{s}$ | **527.4×** | Match |
| **100,000** | $16,520.30\,\mu\text{s}$ | $9.00\,\mu\text{s}$ | $8.10\,\mu\text{s}$ | $17.10\,\mu\text{s}$ | **966.1×** | Match |
| **500,000** | $85,907.60\,\mu\text{s}$ | $10.20\,\mu\text{s}$ | $8.60\,\mu\text{s}$ | $18.80\,\mu\text{s}$ | **4,569.6×** | Match |
| **1,000,000** | $170,863.70\,\mu\text{s}$ | $9.60\,\mu\text{s}$ | $8.90\,\mu\text{s}$ | $18.50\,\mu\text{s}$ | **9,235.9×** | Match |
| **5,000,000** | $861,203.60\,\mu\text{s}$ | $10.80\,\mu\text{s}$ | $9.50\,\mu\text{s}$ | $20.30\,\mu\text{s}$ | **42,423.8×** | Match |

---

## 2. Findings and Hypothesis Evaluation

### Hypothesis H1: Crossover Horizon $t^*$
- **Result:** Confirmed.
- **Evidence:** At $t = 10$, raw execution takes $1.70\,\mu\text{s}$ versus $4.60\,\mu\text{s}$ for the guarded shortcut (speedup $0.4\times$). At $t = 50$, the guarded shortcut takes $6.80\,\mu\text{s}$ versus $9.60\,\mu\text{s}$ for raw execution (speedup $1.4\times$).
- **Crossover Estimation:** Linear interpolation between $t=10$ and $t=50$:
  \[
  t^* \approx 28 \text{ steps}
  \]
  For sequences shorter than $\approx 28$ steps, direct physical execution is strictly cheaper than setting up matrix representations and evaluating redundant residue guards.

### Hypothesis H2: Logarithmic Scaling of Descriptive Navigation
- **Result:** Confirmed.
- **Evidence:**
  - Raw execution $c_{\text{exec}}(t)$ is strictly linear: from $t = 10^3$ ($161.5\,\mu\text{s}$) to $t = 10^6$ ($170,863.7\,\mu\text{s}$), time scales by factor $\approx 1058\times$ (linear $R^2 > 0.999$).
  - Shortcut cost $c_\sigma(t)$ scales logarithmically: from $t = 10$ ($2.40\,\mu\text{s}$) to $t = 5\times 10^6$ ($10.80\,\mu\text{s}$), the time increases by only $\approx 8.4\,\mu\text{s}$ despite a $500,000\times$ increase in steps.
  - At $t = 5,000,000$, navigation by description achieves a **42,423× speedup** over raw execution ($20.3\,\mu\text{s}$ vs $0.86\,\text{s}$).

### Hypothesis H3: Guard Fault Detection Power
- **Result:** Confirmed.
- **Evidence:**
  - A single bit-flip injected at coordinate $\tau = 5,000$ produced divergence in the raw state ($x_{\text{nominal}} \neq x_{\text{faulty}}$).
  - The redundant residue guard on modulus $M_c = 2^{31} - 1$ detected the divergence without re-executing intermediate coordinates (`guard_detected_divergence = True`).

---

## 3. Implications for In-Formation-Space

1. **Grounded Pockets:**  
   The experiment empirically proves the core claim of `grounded_navigation_theory.md`: descriptive shortcuts do not eliminate computational cost, but shift it into logarithmic parameter space within certified pockets.
2. **Interpreter Overhead is Non-Zero:**  
   The existence of $t^* \approx 28$ provides concrete empirical refutation of the idea that symbolic description is "free". For small problems, interpretation and guard evaluation are more expensive than direct execution.
3. **Decoupled Verification:**  
   The redundant residue check demonstrates that a guard does not need to re-run $T$ steps to certify an orbit: redundant algebraic invariants provide $O(\log t)$ certification.


---

## 4. Independent mathematical review (follow-up)

The original benchmark's raw recurrence and affine matrix shortcut use the same primary modulus and their result comparison is meaningful. The original H3 guard result is not valid, however.

### The projection assumption fails

The original code computes a second recurrence modulo \(M_c=2^{31}-1\) and treats that output as the primary state modulo \(M_c\). The primary recurrence is modulo \(M_p=2^{61}-1\).

For the proposed comparison to hold in general, reducing a canonical state in \(\mathbb{Z}/M_p\mathbb{Z}\) modulo \(M_c\) would need to be a well-defined projection compatible with the recurrence. That is not true here because \(M_c\) does not divide \(M_p\). In fact:

\[
M_p \bmod M_c = 1{,}073{,}741{,}823 \ne 0.
\]

Therefore, in general:

\[
\big((a x+b)\bmod M_p\big)\bmod M_c
\ne
\big(a(x\bmod M_c)+b\big)\bmod M_c.
\]

A reproducible coordinate from the original parameters at \(t=10\) gives:

- Primary shortcut result reduced modulo \(M_c\): **366,246,460**
- Independently computed recurrence modulo \(M_c\): **510,455,710**

These disagree with no injected fault. At \(t=10{,}000\), the original nominal check is **1,392,226,910**, while the actual primary result reduced modulo \(M_c\) is **849,091,804**. The original H3 test only asks whether the faulty output differs from the independently computed smaller-modulus trajectory; it never establishes that the nominal primary state passes that same check. Consequently, the guard_detected_divergence result does not establish fault detection.

### Corrected quotient-aware projection

The v2 implementation computes the affine transform under the product modulus \(M_p M_c\). If \(U\) is the unbounded affine result, then:

\[
\tilde U = U \bmod (M_p M_c)
\]

preserves the result modulo \(M_p\), because \(M_p\) divides the product. Thus:

\[
x_p = \tilde U \bmod M_p
\]

is the canonical primary state, and:

\[
r_c = x_p \bmod M_c
\]

is its correct secondary residue. The secondary path uses a separate pair-based affine composition implementation, while the primary path uses matrix operations. The test suite checks that the no-fault primary result agrees with this quotient-aware residue before injecting a fault.

This check remains a finite residue check: a difference divisible by \(M_c\) can escape it. A single successful bit-flip fixture is not a universal fault-tolerance guarantee.

### Timing interpretation

The original table supports a limited observation: for the tested Python/Windows run, raw execution was slower than shortcut plus the measured guard at the larger sampled coordinates. It does not by itself establish a platform-independent crossover or universal asymptotic timings.

The original analysis says linear interpolation gives \(t^*\approx28\). Interpolating the tabulated cost difference between \(t=10\) and \(t=50\) gives approximately \(30.4\), and the sparse grid only establishes that the crossover lies between those tested points. V2 adds finer coordinates around the crossover and uses medians rather than minimum timings.

The original equation includes interpreter cost \(c_I\) and fallback term \(p_{\mathrm{exit}}c_{\mathrm{exec}}\), but the original measured \(N(t)\) is only \(c_\sigma+c_g\). Accordingly, the benchmark measures a simplified nominal comparison, not the complete cost equation.

### Disposition

- Keep the original encounter and timing table as historical observations.
- Treat H1 as a measured crossover bracket, not an exact law.
- Treat H2 as evidence from one environment and finite sample set, not a proof of universal scaling.
- Withdraw the original H3 fault-detection conclusion.
- Use run_tradeoff_v2.py and test_tradeoff_v2.py for future guarded-residue experiments.


---

## 5. Corrected v2 execution result

The corrected script was executed by GitHub Actions on **Ubuntu 26.04.1 / Python 3.11.18**. The run and full measurements are preserved in [tradeoff-v2-ci-run-11.json](tradeoff-v2-ci-run-11.json), linked to workflow run [43101725235](https://github.com/Kier73/In-Formation-Space/actions/runs/43101725235), job 130794631719, at commit 18efda0e05ab2a5f4bddd7a2d082f24ee2a884da.

Selected median measurements:

| Steps | Raw execution | Shortcut | Quotient-aware guard | Combined navigation | Speedup |
|---:|---:|---:|---:|---:|---:|
| 10 | 2.09 µs | 4.33 µs | 4.04 µs | 8.37 µs | 0.25× |
| 50 | 8.55 µs | 4.71 µs | 4.58 µs | 9.29 µs | 0.92× |
| 100 | 16.79 µs | 4.67 µs | 4.97 µs | 9.64 µs | 1.74× |
| 1,000 | 176.65 µs | 7.15 µs | 7.69 µs | 14.84 µs | 11.90× |
| 100,000 | 18,111.55 µs | 10.26 µs | 11.34 µs | 21.60 µs | 838.46× |
| 5,000,000 | 902,471.40 µs | 16.38 µs | 16.23 µs | 32.61 µs | 27,673.83× |

Every tested primary shortcut result matched raw execution, and every nominal quotient-aware guard accepted. The first tested coordinate where guarded navigation won was 100; the last tested coordinate where raw execution won was 50. This is a measured bracket for this runtime and implementation, not a universal crossover constant.

The fault fixture also passed its no-fault baseline: nominal primary state 555069307499060140 matched expected check residue 849091804; after the bit-0 injection at step 5,000, the final primary state was 592373372152816230 and the check rejected it.

The run does not include interpreter setup cost or a fallback term for \(p_{\mathrm{exit}}>0\). It is a finite benchmark, and the residue check can miss a difference divisible by the check modulus.
