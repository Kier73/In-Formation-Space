# Logistic Map Coverage Function Experiment

**Status:** Completed empirical experiment confirming Conjecture 1 of `grounded_navigation_theory.md`.  
**Date:** 2026-11-11  
**Lineage:** Derived from `grounded_navigation_theory.md` (Sections 3 & 10) and parameterized under `maps/mathematical-cautions.md` (Section 5).

---

## 1. Research Question and Problem Shape

In grounded navigation theory, the power of a finite observer navigating by description is defined by its **coverage function**:

\[
C(\delta, B; Q, \varepsilon, \mu)
\]

### 1.1 The Theoretical Puzzle: Topology vs Measure

For the quadratic family $f_r(x) = r x (1 - x)$ on $x \in [0, 1]$ with $r \in [3.5, 4.0]$:
1. **Topology says pockets are everywhere:** Parameters with attracting periodic orbits form an open dense set in the regular set (Graczyk–Świątek, Lyubich).
2. **Measure says chaotic states persist:** Parameters with positive Lyapunov exponents (chaotic attractors) have positive Lebesgue measure (Jakobson).
3. **The Finite Observer:** A finite observer with parameter resolution $\delta$ and period search budget $P$ experiences neither mathematical limit. It can only certify a shortcut if the parameter window has width at least $\delta$ and period at most $P$.

### 1.2 Formal Definition of the Measured Object

Following the discipline in [`maps/mathematical-cautions.md`](../../maps/mathematical-cautions.md):
- **State space / Parameter domain:** $r \in [3.5, 4.0]$.
- **Measure $\mu$:** Normalized Lebesgue measure:
  \[
  \mu([a, b]) = \frac{b - a}{4.0 - 3.5} = \frac{b - a}{0.5}
  \]
- **Pocket criterion:** A stable periodic cycle $\{x_1, \dots, x_p\}$ satisfying $f_r^p(x_i) = x_i$ and multiplier:
  \[
  |\lambda(r)| = \left| \prod_{i=1}^p r (1 - 2 x_i) \right| < 1
  \]
- **Resolution $\delta$:** Minimum parameter width required for an observer to distinguish and reliably certify window $W_i$:
  \[
  \text{Width}(W_i) \ge \delta
  \]
- **Budget $P$:** Maximum period evaluated.
- **Coverage Function:**
  \[
  C(\delta, P) = \mu\left( \bigcup \{ W_i : \text{period}(W_i) \le P \text{ and } \text{width}(W_i) \ge \delta \} \right)
  \]

### 1.3 Conjecture 1 (`grounded_navigation_theory.md`)

> For the logistic map, $C(\delta, P)$ has a plateau in $P$ whose height and position both depend on $\delta$, and the plateau lies strictly below the measure of the whole regular set at any finite $\delta$.

---

## 2. Files

- [scan_coverage.py](scan_coverage.py) — 50,000-point deterministic parameter scanner and coverage matrix calculator.
- [results/coverage-encounter.json](results/coverage-encounter.json) — Captured encounter envelope containing complete benchmark output and SHA-256 integrity receipt.
- [results/analysis.md](results/analysis.md) — Detailed empirical findings, data tables, and theoretical verification.

---

## 3. Reproduction

Run the scanner and validate its encounter envelope:

```bash
python formats/encounter-envelope/capture_encounter.py cmd "python experiments/logistic-map-coverage/scan_coverage.py" --id "exp:logistic-coverage:manual" --out my-coverage.json
python formats/encounter-envelope/validate_envelope.py my-coverage.json
```
