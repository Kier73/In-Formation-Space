# Independent Evaluation: Trial 06 (Adaptive Attention Policies)

**Brief ID:** `d2r-adaptive-attention-06`  
**Evaluator:** Antigravity Evaluator VI  
**Date:** 2026-11-11  
**Artifacts Inspected:** [`brief.md`](brief.md), [`README.md`](README.md), [`adaptive_attention.py`](adaptive_attention.py), [`test_adaptive_attention.py`](test_adaptive_attention.py), [`construction-report.md`](construction-report.md), [`results/test-encounter.json`](results/test-encounter.json)  

---

## 1. Compliance with Hard Constraints ($C_h$)

| Constraint | Stated Requirement | Verification Method | Outcome | Notes |
| :--- | :--- | :--- | :---: | :--- |
| **$C_{h,1}$** | Standard-library Python only | Import audit of `adaptive_attention.py` | **PASS** | Only uses `math`, `dataclasses`, `functools`, and `typing`. Zero external dependencies. |
| **$C_{h,2}$** | Hashable candidate outputs and deterministic observations | Runtime type validation | **PASS** | Validates `hash(value)` on pre-evaluation matrix; raises `TypeError` if unhashable. |
| **$C_{h,3}$** | Finite, strictly positive costs and prior weights | Parameter validation logic | **PASS** | Rejects non-finite, zero, negative, or boolean costs and weights with explicit `ValueError`. |
| **$C_{h,4}$** | No redundant re-observation on constant branches | Decision tree audit | **PASS** | Line 233 explicitly checks `if len(groups) <= 1: continue`, preventing observations from being repeated where outcomes are already determined. |
| **$C_{h,5}$** | Exact minimal-cost policy within hypothesis limit | Algorithmic audit & tests | **PASS** | Dynamic program solves Bellman optimality recurrence across all reachable subsets. Cross-checked against reference recursion. |
| **$C_{h,6}$** | Explicit unresolvable pair reporting | Pre-evaluation pairwise check | **PASS** | Unresolvable true/false pairs are captured in `unresolved_pairs`; plan marked `complete=False`. |
| **$C_{h,7}$** | Bounded subset search (no silent heuristics) | Limit enforcement check | **PASS** | Rejects inputs with $|H| > \text{max\_hypotheses}$ with explicit `ValueError`. |

---

## 2. Mathematical Rigor & Complexity Analysis

Trial 06 elevates active observation planning from static set cover to **Markov Decision Processes (MDP)** over finite belief states:

### 2.1 The Bellman Optimality Recurrence
Let $M \subseteq H$ be a non-empty subset of surviving hypotheses. The value function $C^*(M)$ represents the minimum expected cost to resolve query $Q$:
\[
C^*(M) = \begin{cases}
0.0 & \text{if } Q(h) = Q(h') \ \forall h, h' \in M \\
\min\limits_{k : |\mathcal{V}_k(M)| > 1} \left[ c_k + \sum\limits_{v \in \mathcal{V}_k(M)} P(M_v \mid M) C^*(M_v) \right] & \text{otherwise}
\end{cases}
\]
Every non-terminal observation used by the recurrence creates at least two non-empty, strict subsets of the current hypothesis set. The subset recursion is therefore acyclic and terminates on a finite state space. No contraction-mapping argument is needed; exactness follows from evaluating the Bellman recurrence over every available observation at each reachable subset.

### 2.2 Expected-cost optimality versus worst-case reporting

The implementation selects each observation by minimizing the expected-cost Bellman recurrence. `worst_case_additional_cost` is then computed for the resulting expected-cost-optimal policy. It is **not** a separately optimized minimax value. The minimax recurrence would require a distinct policy-selection objective:

\[
W^*(M)=\min_k\left[c_k+\max_v W^*(M_v)\right].
\]

The current solver does not use that recurrence to select its policy. Its returned worst-case field is the maximum path cost of the policy selected under expected cost.

### 2.3 Complexity Bounds
- **State Space:** At most $2^{|H|}$ reachable belief subsets.
- **Branching Factor:** At most $m$ candidate observations per subset.
- **Worst-Case Time:** $O(m \cdot |H| \cdot 2^{|H|})$.
- For default `max_hypotheses = 18`, $2^{18} \approx 2.62 \times 10^5$, executing in fractions of a second on commodity hardware.

---

## 3. Epistemic Synthesis: Static Packets vs Adaptive Policies

The transition from Trial 05 to Trial 06 formalizes the distinction between **open-loop** and **closed-loop** sensing:

1. **Static Attention (Trial 05):**  
   The observer commits to a fixed set of measurements $I \subseteq \mathcal{C}$ before observing any data:
   \[
   \text{Cost}_{\text{static}} = \sum_{i \in I} c_i
   \]
   This cost is invariant to which hypothesis is true.
2. **Adaptive Attention (Trial 06):**  
   The observer executes a policy tree $\pi$, branching conditioned on intermediate data:
   \[
   \mathbb{E}[\text{Cost}_{\text{adaptive}}] = \sum_{h \in H} P(h) \cdot \text{PathCost}(\pi, h)
   \]
3. **The Information Value of Pruning:**  
   In the canonical fixture of Trial 06, four hypotheses $H = \{A, B, C, D\}$ require distinguishing $Q(h)$. A static observation packet costs $3.0$, and a direct monolithic sensor costs $2.5$. The adaptive policy measures an initial feature at cost $1.0$; with probability $0.5$, this terminates immediately (total cost $1.0$); with probability $0.5$, it takes a second feature at cost $1.0$ (total cost $2.0$).  
   The minimum static packet uses `left-refinement` and `right-refinement`, costing 2.0. The direct sensor costs 2.5, and collecting every inexpensive observation costs 3.0. The adaptive policy has expected cost:
   \[
   0.25\times1.0+0.25\times1.0+0.5\times2.0=1.5<2.0.
   \]
   A new test enumerates every static candidate subset, verifies that 2.0 is the minimum static cost, and checks that the adaptive policy costs 1.5 in expectation.

---

## 4. Evaluator Conclusion

**Status:** Accepted. Trial 06 successfully completes the progression of attention models in `description-to-realization`, providing a mathematically rigorous, verified, and optimal adaptive observation policy engine.


## 5. Follow-up mathematical review

The original evaluation's use of a contraction-mapping justification was unnecessary and not appropriate for this finite subset recursion. Termination follows because each selected observation splits the current set into strict subsets. The exact expected-cost result follows by induction over subset size and the Bellman recurrence.

The evaluation also displayed a minimax recurrence for worst-case cost. The implementation does not optimize that recurrence: it optimizes expected cost and reports the worst-case path cost of that expected-optimal policy. A separate minimax policy solver would be needed to claim the minimum possible worst-case cost.

Finally, the original static comparison used the full three-observation packet at cost 3.0, not the cheapest static packet. The cheapest static packet is the two branch-specific refinements at cost 2.0. The adaptive policy's 1.5 expected cost still beats that baseline. This correction is independently cross-checked by brute-force subset enumeration in the new seventh test.
