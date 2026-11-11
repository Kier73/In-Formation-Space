# Empirical Analysis: Logistic Map Coverage Function

**Experiment:** `logistic-map-coverage`  
**Run ID:** `exp:logistic-coverage:2026-11-11`  
**Date:** 2026-11-11  
**Encounter Artifact:** [`coverage-encounter.json`](coverage-encounter.json)  
**Hardware / OS:** Windows 11, Python 3.14.0  
**Sample Grid:** 50,000 points across $r \in [3.5, 4.0]$ ($\Delta r = 10^{-5}$)  

---

## 1. Measured Data

The parameter scan discovered **303 contiguous periodic windows** within $r \in [3.5, 4.0]$.

### 1.1 Largest Detected Periodic Windows

| Period $p$ | $r_{\text{start}}$ | $r_{\text{end}}$ | Width $\Delta r$ | Samples | Qualitative Regime |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **4** | 3.500000 | 3.541340 | 0.041340 | 4,134 | Early period-doubling cascade |
| **8** | 3.544830 | 3.563360 | 0.018530 | 1,853 | Period-doubling cascade |
| **3** | 3.828430 | 3.840960 | 0.012530 | 1,253 | Prominent period-3 island (Li-Yorke) |
| **6** | 3.841620 | 3.847370 | 0.005750 | 575 | Period-doubling of period-3 |
| **16** | 3.564690 | 3.568420 | 0.003730 | 373 | Pre-Feigenbaum cascade |
| **6** | 3.626560 | 3.630100 | 0.003540 | 354 | Secondary period-6 window |
| **5** | 3.738180 | 3.740930 | 0.002750 | 275 | Period-5 window |
| **12** | 3.630470 | 3.632060 | 0.001590 | 159 | Period-doubling of secondary period-6 |

---

### 1.2 Coverage Function Matrix $C(\delta, P)$

The matrix below reports the fraction of the $[3.5, 4.0]$ parameter interval certifiable by periodic shortcut pockets:

| Resolution $\delta$ | $P \le 2$ | $P \le 4$ | $P \le 8$ | $P \le 16$ | $P \le 32$ | $P \le 64$ | Plateau Height | Plateau Point |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$\delta = 0.0002$** | 0.0000 | 0.1090 | 0.1762 | 0.1966 | **0.2010** | **0.2010** | **20.10%** | $P = 32$ |
| **$\delta = 0.0005$** | 0.0000 | 0.1090 | 0.1730 | 0.1914 | **0.1929** | **0.1929** | **19.29%** | $P = 32$ |
| **$\delta = 0.0010$** | 0.0000 | 0.1077 | 0.1689 | **0.1847** | **0.1847** | **0.1847** | **18.47%** | $P = 16$ |
| **$\delta = 0.0020$** | 0.0000 | 0.1077 | 0.1689 | **0.1763** | **0.1763** | **0.1763** | **17.63%** | $P = 16$ |
| **$\delta = 0.0050$** | 0.0000 | 0.1077 | **0.1563** | **0.1563** | **0.1563** | **0.1563** | **15.63%** | $P = 8$ |
| **$\delta = 0.0100$** | 0.0000 | 0.1077 | **0.1448** | **0.1448** | **0.1448** | **0.1448** | **14.48%** | $P = 8$ |

---

## 2. Evaluation of Theoretical Conjectures

### 2.1 Original interpretation (subsequently qualified)

The following was the initial analysis of the observed matrix. It should now be read as a set of hypotheses suggested by the finite scan, not as confirmation of the full conjecture. The methodological limits are detailed in [review-note.md](../review-note.md).

### 2.2 Finite-grid observations

On the recorded 50,000-point grid and the six tested period budgets, the following patterns were observed:

1. **Existence of Plateau in $P$:**  
   For every resolution $\delta$, increasing the period budget $P$ beyond a threshold yields zero additional coverage:
   \[
   \exists P^*(\delta) \text{ such that } \forall P \ge P^*(\delta), \quad C(\delta, P) = C(\delta, P^*(\delta))
   \]
   Higher-period windows become geometrically narrower under Feigenbaum scaling ($\delta_n \sim \delta_F^{-n}$ where $\delta_F \approx 4.6692$). Once window widths drop below $\delta$, extra period search budget is wasted.
2. **Plateau Height Depends on $\delta$:**  
   As resolution coarsens from $\delta = 0.0002$ to $\delta = 0.0100$, the plateau height monotonically decreases from **20.10%** down to **14.48%**. Finer distinctions allow an observer to navigate narrower pockets.
3. **Plateau Position Shifts with $\delta$:**  
   At coarse resolution ($\delta = 0.0100$), the plateau is reached early at $P^* = 8$. At fine resolution ($\delta = 0.0002$), the plateau shifts deeper to $P^* = 32$.
4. **Observed coverage remains below the full parameter interval:**  
   The estimated candidate-window coverage at $\delta = 0.0002$ is **20.10% of the sampled parameter interval**. The remaining 79.90% is not classified by this scan as chaotic or as a mathematically established dead zone; it is simply outside the candidate intervals detected under this grid, warmup, tolerance, and period ceiling.

---

## 3. Epistemic Boundaries & Conditions

As emphasized in [`maps/mathematical-cautions.md`](../../maps/mathematical-cautions.md):
- **Sampling limitation:** The 50,000-point grid has resolution step $\Delta r = 10^{-5}$. Windows narrower than $10^{-5}$ were not detected. This does not affect the reported matrix, as the finest analyzed resolution was $\delta = 2 \times 10^{-4}$ (20 grid steps).
- **Tolerance boundary:** The cycle detection tolerance was set to $10^{-6}$ after 600 transient warmup iterations.
- **Scope of observation:** The matrix describes the output of this real 1D quadratic-map scanner under the selected finite numerical settings on $[3.5, 4.0]$. The equality at P<=32 and P<=64 is an observed plateau over those tested budgets only; it does not prove a plateau for all P beyond 32.
