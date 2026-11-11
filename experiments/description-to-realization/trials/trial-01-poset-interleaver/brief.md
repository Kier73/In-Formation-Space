# Construction Brief: Poset Causal Interleaver

**Brief ID:** `brief:d2r-poset-01`  
**Revision:** `1`  
**Date:** 2026-11-11  
**Prepared by:** In-Formation-Space contributor (Antigravity VI)  
**Parent experiment:** [`experiments/description-to-realization`](../../README.md)  
**Template:** [`brief-template.md`](../../brief-template.md)  

---

## 1. Desired result

Construct a lightweight, deterministic Python library that represents multi-stream partially ordered event systems, validates their causal consistency, determines the number of admitted topological linear extensions, and verifies candidate event traces against the partial order.

---

## 2. Hard constraints ($C_h$)

1. **Zero external dependencies:** Must run using only Python standard library (Python 3.10+).
2. **Deterministic acyclicity checking:**
   - Detects whether a set of event ordering constraints contains a directed cycle.
   - If cyclic, refuses to compute orderings and extracts a minimal witness cycle:
     \[
     (e_1 \to e_2 \to \dots \to e_k \to e_1)
     \]
3. **Exact linear extension count for small posets ($|V| \le 12$):**
   - For two independent event chains $A = (a_1 \prec \dots \prec a_n)$ and $B = (b_1 \prec \dots \prec b_m)$ with zero cross-stream constraints, the reported linear extension count $|\Omega|$ must strictly equal:
     \[
     |\Omega| = \binom{n + m}{n} = \frac{(n + m)!}{n! \, m!}
     \]
   - For the 4-event controller stream and 3-event sensor stream from `experiments/cold-start-continuity`, $|\Omega|$ must evaluate to exactly 35.
4. **Trace verification:**
   - Given a proposed total sequence $(s_1, s_2, \dots, s_N)$, verify in $O(N + |E|)$ whether the sequence is a valid linear extension of the poset.
   - If invalid, identify the exact edge $(u \prec v)$ violated in the trace.
5. **Immutable / pure query interface:** Querying properties (e.g. extension count, trace validity) must not mutate the underlying poset state.

---

## 3. Soft preferences ($C_s$)

1. **Ergonomic stream builder:** Convenient helpers for declaring ordered streams (e.g. `add_chain(["c1", "c2", "c3"])`) and cross-stream causal edges (`add_edge("c2", "s1")`).
2. **Enumeration capability:** Ability to iterate over the linear extensions when $|\Omega|$ is within reasonable bounds (e.g. $|\Omega| \le 10,000$).
3. **Memory efficiency:** Compact internal graph representations.

---

## 4. Success criteria and witnesses ($O$)

1. An executable test script (`test_poset_interleaver.py`) that runs automatically and exits with code 0.
2. Verified unit test results confirming:
   - 2-chain disjoint poset: $|A|=4, |B|=3 \implies |\Omega| = 35$.
   - Constrained poset: adding cross-edge $c_2 \prec s_2$ strictly reduces $|\Omega|$ to an integer $1 \le |\Omega| < 35$.
   - Cycle detection: adding conflicting cross-edges $u \prec v$ and $v \prec u$ raises/returns cycle error with cycle witness path.
   - Trace validity: valid permutations accept, invalid permutations reject with edge blame.
3. Execution receipt captured in an Encounter Envelope format.

---

## 5. Available resources and boundaries ($R$)

- Runtime: Local Windows host, Python 3.14.0.
- Standard library modules permitted (`dataclasses`, `typing`, `collections`, `itertools`, `functools`).
- Prohibited: No third-party network fetches, no external packages (`networkx`, `scipy`).

---

## 6. Known context

- Relates to the split-clock relay in [`experiments/cold-start-continuity`](../../../experiments/cold-start-continuity/README.md).
- Formulates the partial order underdetermination problem identified in [`review-note.md`](../../../experiments/cold-start-continuity/runs/2026-11-11-run-01/review-note.md).

---

## 7. Unknowns and allowed discretion ($U$)

- Specific graph data structures (adjacency dict vs matrix vs topological levels).
- Specific counting algorithm (dynamic programming over subposets, DFS backtracking with memoization).
- Method names and exceptions hierarchy, provided hard constraints $C_h$ are met.

---

## 8. Required return

The constructor must supply:
1. The implementation module (`poset_interleaver.py`).
2. The verification test suite (`test_poset_interleaver.py`).
3. Construction trace, stating design choices and trade-offs.
4. Execution output and test evidence.
