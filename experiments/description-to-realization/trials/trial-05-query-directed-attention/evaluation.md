# Independent Evaluation: Trial 05 (Query-Directed Attention)

**Brief ID:** `d2r-query-attention-05`  
**Evaluator:** Antigravity Evaluator VI  
**Date:** 2026-11-11  
**Artifacts Inspected:** [`brief.md`](brief.md), [`README.md`](README.md), [`query_attention.py`](query_attention.py), [`test_query_attention.py`](test_query_attention.py), [`construction-report.md`](construction-report.md), [`results/test-encounter.json`](results/test-encounter.json)  

---

## 1. Compliance with Hard Constraints ($C_h$)

| Constraint | Stated Requirement | Verification Method | Outcome | Notes |
| :--- | :--- | :--- | :---: | :--- |
| **$C_{h,1}$** | Standard-library Python only | Import audit of `query_attention.py` | **PASS** | Only uses `math`, `dataclasses`, and `typing`. Zero external dependencies. |
| **$C_{h,2}$** | Hashable hypotheses and candidate outputs | Runtime type checking | **PASS** | Validates `hash(hyp)` and `hash(obs_val)`; raises `TypeError` if unhashable. |
| **$C_{h,3}$** | Boolean query requirement | Return value type check | **PASS** | Evaluates `query(h)` for all hypotheses; enforces boolean return type (`TypeError` otherwise). |
| **$C_{h,4}$** | Finite, strictly positive candidate costs | Cost validation logic | **PASS** | Rejects non-finite, zero, negative, or boolean cost values with explicit `ValueError`. |
| **$C_{h,5}$** | Explicit unresolved cross-boundary reporting | Set difference audit | **PASS** | Uncovered true/false pairs are captured in `unresolved_cross_pairs`; plan marked `complete=False`. |
| **$C_{h,6}$** | Exact 0/1 bitmask DP within threshold | Algorithmic audit & tests | **PASS** | Solves weighted set cover over cross-pairs $H^+ \times H^-$ for $|P_{\text{coverable}}| \le \text{max\_exact\_pairs}$. Cross-checked against 35 random brute-force instances. |
| **$C_{h,7}$** | Labelled greedy fallback for large pair sets | Threshold overflow test | **PASS** | Cases exceeding threshold return `exact=False` and `solver="greedy-set-cover"`. |
| **$C_{h,8}$** | Zero-cost trivial plan when query determined | Partition cardinality check | **PASS** | When all hypotheses agree on the query ($|H^+|=0$ or $|H^-|=0$), returns `total_cost=0.0`, `selected_names=()`, `solver="exact-trivial"`. |

---

## 2. Mathematical Rigor & Bipartite Separation

Trial 05 formalizes task-directed observation as **Bipartite Boundary Separation**:

### 2.1 The Cross-Boundary Pair Universe
Let $H$ be the set of surviving hypotheses. A Boolean query $Q: H \to \{0, 1\}$ induces a 2-block partition:
\[
H^+ = \{h \in H \mid Q(h) = 1\}, \qquad H^- = \{h \in H \mid Q(h) = 0\}
\]
To resolve $Q$, an agent does not need to reconstruct the true hypothesis $h^* \in H$. It only needs to establish whether $h^* \in H^+$ or $h^* \in H^-$.

Therefore, the only distinctions with non-zero utility are those separating cross-boundary pairs in the Cartesian product:
\[
\mathcal{U}_{\text{cross}} = H^+ \times H^-
\]
The total number of pairs to cover is:
\[
p = |H^+| \cdot |H^-| \le \frac{|H|^2}{4}
\]
Intra-class pairs $(h_1, h_2) \in (H^+ \times H^+) \cup (H^- \times H^-)$ have zero value for resolving $Q$. The implementation strictly enforces this: candidates that only split within $H^+$ or within $H^-$ receive zero coverage mask credit.

### 2.2 Constructive Poset Resolution Witness
The test suite includes a direct witness connecting Trial 05 with Trial 01 (Poset Causal Interleaver) and the Cold-Start Relay:
- Two 2-event chains ($C_0 \prec C_1$ and $S_0 \prec S_1$) induce $\binom{4}{2} = 6$ linear extensions.
- Query: *"Does $C_0$ precede $S_0$?"* splits the extensions into $|H^+| = 3$ and $|H^-| = 3$, requiring $p = 9$ cross-boundary pairs to be covered.
- When candidates only measure non-query relations (e.g. $C_1$ vs $S_0$, $C_1$ vs $S_1$), two pairs remain identically indistinguishable:
  \[
  (C_0, S_0, C_1, S_1) \quad \text{vs} \quad (S_0, C_0, C_1, S_1)
  \]
  \[
  (C_0, S_0, S_1, C_1) \quad \text{vs} \quad (S_0, C_0, S_1, C_1)
  \]
- The solver rigorously flags these pairs in `unresolved_cross_pairs`.
- Introducing a shared-clock observation $C_0 \prec S_0$ immediately covers the remaining pairs and yields `complete=True`.

---

## 3. Epistemic Synthesis: The Logic of Pragmatic Attention

Trial 05 completes the foundational arc of the Description-to-Realization series:

1. **Trial 01 (Structure):** Formulates the latent causal space as a partially ordered set and counts linear extensions ($|\Omega|$).
2. **Trial 02 (Quotient Index):** Distinguishes bounded finite-state quotient spaces from unbounded prefix distinguishability ($|\Sigma^* / \sim|$).
3. **Trial 03 (Passive Refinement):** Quantifies observational distinction via combinatorial split pairs $\Delta \text{pairs}$ and Shannon entropy $H(D \mid \mathcal{O})$.
4. **Trial 04 (State Identification):** Actively selects minimum-cost observations to isolate a single point hypothesis $s^*$.
5. **Trial 05 (Task-Directed Decision):** Actively selects minimum-cost observations to resolve a specific property $Q$, demonstrating that goal-directed agents can act with provably lower observational cost than agents attempting full state estimation.

---

## 4. Evaluator Conclusion

**Status:** Accepted. Trial 05 provides an elegant, executable, and zero-dependency implementation of query-directed observation planning, with verified test receipts and mathematical proofs.
