# Independent Evaluation: Trial 04 (Active Distinction Selection)

**Brief ID:** `d2r-active-distinction-04`  
**Evaluator:** Antigravity Evaluator VI  
**Date:** 2026-11-11  
**Artifacts Inspected:** [`brief.md`](brief.md), [`README.md`](README.md), [`attention_selection.py`](attention_selection.py), [`test_attention_selection.py`](test_attention_selection.py), [`construction-report.md`](construction-report.md), [`results/test-encounter.json`](results/test-encounter.json)  

---

## 1. Compliance with Hard Constraints ($C_h$)

| Constraint | Stated Requirement | Verification Method | Outcome | Notes |
| :--- | :--- | :--- | :---: | :--- |
| **$C_{h,1}$** | Standard-library Python only | Import audit of `attention_selection.py` | **PASS** | Only uses `math`, `dataclasses`, and `typing`. Zero external dependencies. |
| **$C_{h,2}$** | Hashable signatures and candidate outputs | Runtime type checking | **PASS** | Validates `hash(target_value)` and `hash(observed)`; raises `TypeError` for unhashable outputs. |
| **$C_{h,3}$** | Finite, strictly positive candidate costs | Cost validation logic | **PASS** | Rejects non-finite, negative, zero, and boolean cost values with explicit `ValueError`. |
| **$C_{h,4}$** | Unique candidate names | Set membership check | **PASS** | Raises `ValueError` on empty, whitespace, or duplicate names. |
| **$C_{h,5}$** | Explicit unseparable state reporting | Set difference audit | **PASS** | Alternatives not covered by any candidate mask are placed in `unseparable_states`; plan marked `complete=False`. |
| **$C_{h,6}$** | Exact minimum-cost solver within threshold | Algorithm inspection & tests | **PASS** | 0/1 bitmask dynamic program guarantees global cost minimum for $|A_{\text{coverable}}| \le \text{max\_exact\_alternatives}$. Cross-checked against brute-force powerset search. |
| **$C_{h,7}$** | Labelled greedy fallback for large sets | Solver threshold test | **PASS** | Cases exceeding threshold return `exact=False` and `solver="greedy-set-cover"`. |
| **$C_{h,8}$** | Zero-cost trivial case for unique target | Ambiguity check | **PASS** | When target is already unique, returns `total_cost=0.0`, `selected_names=()`, `solver="exact-trivial"`. |

---

## 2. Mathematical Rigor & Complexity Analysis

Trial 04 frames active sensing as an instance of **Weighted Set Cover**, bridging epistemic uncertainty and combinatorial optimization:

### 2.1 The Combinatorial Bound
Let $k = |A_{\text{coverable}}(s^*)|$ be the number of coverable alternatives and $m = |\mathcal{C}|$ be the candidate count:
- **Bitmask DP Time:** $O(m \cdot 2^k)$.
- **Bitmask DP Space:** $O(2^k)$.

For the default threshold $k \le 20$, $2^{20} \approx 1.05 \times 10^6$ states, which executes deterministically in fractions of a second. The implementation correctly isolates the ambiguity set $A(s^*)$ before building the DP table, avoiding exponential blowup over the total state space $|S|$.

### 2.2 Approximation Guarantee of Greedy Fallback
For $k > 20$, the solver switches to greedy set cover. By Chvátal's theorem (1979), the greedy heuristic for weighted set cover achieves an approximation ratio:
\[
\frac{\text{Cost}_{\text{greedy}}}{\text{Cost}_{\text{optimal}}} \le H(k) = \sum_{i=1}^k \frac{1}{i} \le \ln(k) + 1
\]
The implementation correctly marks `exact=False` so downstream consumers do not mistake an approximation for a certified minimum.

---

## 3. Epistemic Synthesis: What "Attention" Means Formally

In cognitive and machine learning literature, "attention" is frequently used as a vague metaphor. Trial 04 provides an exact operational definition:

1. **Target-Centered Equivalence:**
   Attention is not global refinement of the entire universe. It is the selection of distinctions specifically focused on the target's equivalence class $[s^*]_{\sim}$. Distinctions separating two states $s_1, s_2 \notin [s^*]_{\sim}$ are given zero utility.
2. **Cost-Aware Information Gathering:**
   Gathering data has concrete costs (latency, compute, energy). Attention is the optimal trade-off between eliminating epistemic ambiguity and conserving observational budget:
   \[
   \min \sum_{i \in I} \text{cost}_i \quad \text{s.t.} \quad [s^*]_{\sim \cup I} = \{s^*\}
   \]
3. **Epistemic Horizon Awareness:**
   If the candidate pool lacks distinctions capable of separating $s^*$ from an alternative $s'$, the solver reports $s' \in \text{unseparable\_states}$. This explicitly marks what cannot be known under the current observational instrument, upholding the core principle: *preserve unknown and ambiguous outcomes instead of silently choosing an interpretation*.

---

## 4. Evaluator Conclusion

**Status:** Accepted. Trial 04 successfully realizes the transition from passive distinction observation (Trial 03) to active, goal-directed, cost-bounded observational planning.
