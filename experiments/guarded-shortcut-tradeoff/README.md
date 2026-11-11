# Guarded Shortcut Trade-off: Execution vs Description

**Status:** Initial benchmark recorded; the original guard interpretation is under correction. See [independent review](review-note.md) and the [quotient-aware v2 experiment](run_tradeoff_v2.py).  
**Date:** 2026-11-11  
**Lineage:** Derived from `grounded_navigation_theory.md` (Sections 2, 5, 9) and E-CPU Structural Memory affine recurrence specifications.

---

## 1. Research Question and Problem Shape

In grounded navigation theory, navigating a state space by description beats raw execution only inside pockets where a shortcut $\sigma$ and a cheap, sound guard $g$ both exist.

The total cost of description-based navigation is:

\[
N(t) = c_I + c_g(t) + c_\sigma(t) + p_{\text{exit}} \cdot c_{\text{exec}}(t)
\]

versus step-by-step physical execution:

\[
E(t) = c_{\text{exec}}(t)
\]

### 1.1 Mathematical Formulation: Affine Modular Recurrence

Consider the discrete dynamical system:

\[
x_{k+1} = (a \cdot x_k + b) \pmod M, \quad x_0 \in \mathbb{Z}_M
\]

over prime modulus $M = 2^{61} - 1$ (Mersenne prime $M_{61}$).

#### 1. Raw Execution ($c_{\text{exec}}$)
Iterating $t$ transitions requires $t$ modular multiplications and additions:
\[
c_{\text{exec}}(t) = \kappa_{\text{exec}} \cdot t, \quad \text{where } \kappa_{\text{exec}} \approx 0.17\,\mu\text{s/step}
\]

#### 2. Descriptive Shortcut ($c_\sigma$)
The recurrence lifts to a 2×2 affine matrix power in $GL_2(\mathbb{Z}_M)$:
\[
\begin{pmatrix} x_t \\ 1 \end{pmatrix} = \begin{pmatrix} a & b \\ 0 & 1 \end{pmatrix}^t \begin{pmatrix} x_0 \\ 1 \end{pmatrix} \pmod M
\]
Evaluated via binary exponentiation in $\lfloor \log_2 t \rfloor$ multiplications:
\[
c_\sigma(t) = \kappa_\sigma \cdot \log_2(t)
\]
Shortcut exponent $\gamma = 0$ (logarithmic speedup).

#### 3. Redundant Residue Guard ($c_g$)
To ensure the state has not exited the nominal orbit (e.g., due to memory bit-flips or exogenous faults), a guard verifies consistency over an independent coprime check modulus $M_c = 2^{31} - 1$ ($M_{31}$):
\[
\text{Guard}(x_t) \iff \left( x_t \pmod{M_c} \equiv \text{Shortcut}(x_0, t \pmod{M_c}) \right)
\]
Cost of guard evaluation:
\[
c_g(t) = \kappa_g \cdot \log_2(t)
\]

#### 4. The Crossover Horizon ($t^*$)
Assuming nominal operation ($p_{\text{exit}} = 0$):
\[
\kappa_{\text{exec}} \cdot t^* = c_I + (\kappa_\sigma + \kappa_g) \log_2(t^*)
\]
- For $t < t^*$: Raw execution is faster ($E(t) < N(t)$) due to setup overhead.
- For $t > t^*$: Descriptive navigation dominates with speedup $S(t) \sim \frac{t}{\log_2 t} \to \infty$.

---

## 2. Testable Hypotheses

| Hypothesis | Operational Test | Discriminating Criterion |
| :--- | :--- | :--- |
| **H1: Crossover threshold** | Sweep $t \in [10, 5\times 10^6]$ | There exists a finite $t^* \in [10, 100]$ below which execution is faster and above which description wins. |
| **H2: Logarithmic scaling** | Measure $c_\sigma(t)$ and $c_g(t)$ across 6 orders of magnitude | Time scales logarithmically ($\approx 2\,\mu\text{s}$ per factor of 10), while $c_{\text{exec}}(t)$ scales strictly linearly. |
| **H3: Fault detection power** | Inject a bit-flip at intermediate coordinate $\tau = 5000$ | Guard detects orbit exit on the check modulus ($M_c$) without materializing the intermediate steps. |

---

## 3. Files

- [run_tradeoff.py](run_tradeoff.py) — original benchmark; its secondary-modulus guard claim is invalid as reviewed below.
- [run_tradeoff_v2.py](run_tradeoff_v2.py) — corrected quotient-aware check, median-based measurements, and explicit no-fault baseline.
- [test_tradeoff_v2.py](test_tradeoff_v2.py) — deterministic tests for projection, fault checks, and collision limits.
- [review-note.md](review-note.md) — mathematical review of the original residue guard and timing claims.
- [results/tradeoff-encounter.json](results/tradeoff-encounter.json) — original run, retained as historical evidence.
- [results/tradeoff-v2-ci-run-11.json](results/tradeoff-v2-ci-run-11.json) — corrected CI benchmark output with run provenance and SHA-256 integrity receipt.
- [results/analysis.md](results/analysis.md) — Detailed analysis and empirical verification report.

---

## 4. Reproduction

Run the benchmark and capture an encounter envelope:

```bash
python formats/encounter-envelope/capture_encounter.py cmd "python experiments/guarded-shortcut-tradeoff/run_tradeoff.py" --id "exp:guarded-shortcut:manual-run" --out my-result.json
python formats/encounter-envelope/validate_envelope.py my-result.json
```

For the corrected benchmark, run:

```bash
python -m unittest discover -s experiments/guarded-shortcut-tradeoff -p 'test_*.py' -v
python experiments/guarded-shortcut-tradeoff/run_tradeoff_v2.py --json
```

The original run is retained as historical evidence. Its raw-versus-shortcut recurrence results remain useful, but its secondary-modulus fault-detection claim must not be relied upon. The corrected CI run found the first tested guarded-navigation win at 100 steps; at 50 steps it still lost. Thus the measured crossover is bracketed by 50 and 100 steps on the recorded Ubuntu/Python runner, not established as a universal threshold.
