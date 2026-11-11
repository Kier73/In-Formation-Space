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
