# Construction Report: Trial 06 (Adaptive Attention Policies)

**Trial:** 06  
**Brief:** `d2r-adaptive-attention-06`  
**Parent Trials:** Active Distinction Selection (Trial 04) and Query-Directed Attention (Trial 05)  
**Implementation:** [`adaptive_attention.py`](adaptive_attention.py)  
**Tests:** [`test_adaptive_attention.py`](test_adaptive_attention.py)  
**Execution receipt:** [`results/test-encounter.json`](results/test-encounter.json)  

---

## 1. Problem Formulation

Prior trials established:
- **Trial 04 (State Isolation):** Static observation packet minimizing $\sum c_i$ to isolate target $s^*$.
- **Trial 05 (Query Resolution):** Static observation packet minimizing $\sum c_i$ to cover bipartite cross-pairs $H^+ \times H^-$.

In both Trial 04 and Trial 05, the observation set is **static**: all chosen observations must be collected in advance. In real systems, observations occur sequentially: learning the outcome of observation $O_1$ shrinks the hypothesis space, potentially rendering observation $O_2$ completely unnecessary.

**Trial 06** asks:
> *Can an observer reduce expected observational cost by constructing an adaptive decision tree, where each subsequent observation is selected conditionally based on prior outcomes?*

### 1.1 The Decision Tree Model
A policy $\pi$ is a rooted directed tree:
- **Internal Node:** Labeled by candidate observation $O \in \mathcal{C}$ with cost $c(O) > 0$. Outgoing edges correspond to possible observed values $v \in \mathcal{V}(O)$.
- **Leaf Node:** Labeled by query decision $q \in \{\text{True}, \text{False}\}$, with all surviving hypotheses agreeing on $q$.
- **No-Repeat Invariant:** An observation is never queried on a branch where its outcome is already constant.

### 1.2 The Optimality Recurrence
Let $M \subseteq H$ be a subset of surviving hypotheses, and let $w: H \to (0, \infty)$ be strictly positive prior weights. The conditional probability of hypothesis $h \in M$ is:
\[
P(h \mid M) = \frac{w(h)}{\sum_{h' \in M} w(h')}
\]

If $Q(h)$ is constant for all $h \in M$, $M$ is a terminal leaf:
\[
C^*(M) = 0.0, \qquad W^*(M) = 0.0
\]

Otherwise, the observer chooses candidate observation $O_k$ that splits $M$ into partition $\{M_v\}_{v \in \mathcal{V}_k}$ ($|\mathcal{V}_k| > 1$). The minimum expected additional cost satisfies Bellman's equation:
\[
C^*(M) = \min_{k : |\mathcal{V}_k| > 1} \left[ c(O_k) + \sum_{v \in \mathcal{V}_k} P(M_v \mid M) C^*(M_v) \right]
\]
The corresponding worst-case path cost is:
\[
W^*(M) = \min_{k : |\mathcal{V}_k| > 1} \left[ c(O_k) + \max_{v \in \mathcal{V}_k} W^*(M_v) \right]
\]

---

## 2. Implementation Architecture

[`adaptive_attention.py`](adaptive_attention.py) implements exact subset dynamic programming:

1. **Pre-Evaluation Matrix:**
   - Evaluates each candidate $O_k$ over each hypothesis $h \in H$ once, creating an $m \times |H|$ observation lookup table.
2. **Pairwise Pre-Check:**
   - Pre-checks every true/false hypothesis pair $(h^+, h^-) \in H^+ \times H^-$.
   - If any pair has identical outputs across all candidate observations, returns immediately with `complete=False` and `unresolved_pairs`, avoiding exponential tree search.
3. **Memoized Bitmask Dynamic Programming:**
   - Encodes subsets $M \subseteq H$ as integer bitmasks.
   - Computes $C^*(M)$ via `@lru_cache(maxsize=None)` with numerically stable `math.fsum` probability scaling.
   - Enforces the strict hard constraint: rejects inputs exceeding `max_hypotheses` (default 18) to avoid unbounded runtime.
4. **Result Reporting:**
   - Returns [`AdaptiveAttentionPlan`](adaptive_attention.py#L35-L43) containing root [`PolicyNode`](adaptive_attention.py#L25-L32), total expected cost, worst-case cost, and traversed observation names.

---

## 3. Test Evidence

The test suite in [`test_adaptive_attention.py`](test_adaptive_attention.py) passes 6 unit tests covering:
- **Static vs Adaptive Cost Advantage:** Demonstrates a 4-hypothesis fixture where the cheapest static packet costs 2.0, direct sensing costs 2.5, and collecting all three inexpensive observations costs 3.0. The adaptive policy achieves expected cost 1.5 and worst-case path cost 2.0.
- **Prior Sensitivity:** Verifies that changing prior weights changes expected path cost and observation ordering without affecting query correctness.
- **Reference Recurrence Cross-Check:** Verifies exact policy costs against an independent reference recurrence on random small instances.
- **Trivial Resolution:** Pre-resolved queries return zero-cost terminal leaf immediately.
- **Unresolvable Cross-Pairs:** Properly identifies and reports hypotheses that cannot be separated.
- **Validation:** Rejects unhashable outputs, negative costs, duplicate names, and non-callable queries.

Encounter receipt is captured in [`results/test-encounter.json`](results/test-encounter.json).


## 4. Static-packet comparison correction

A follow-up brute-force enumeration over all subsets of the four candidate observations found that the minimum static packet is the pair of branch-specific refinements (`left-refinement` and `right-refinement`), costing 2.0. The earlier comparison against the three-observation packet at cost 3.0 was not the strongest static baseline. The adaptive policy still wins: expected cost 1.5, worst-case path cost 2.0. A new unit test enumerates every static subset and verifies this comparison.
