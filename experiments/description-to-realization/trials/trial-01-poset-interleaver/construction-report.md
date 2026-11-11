# Construction Report: Poset Causal Interleaver

**Brief ID:** `brief:d2r-poset-01` rev `1`  
**Constructor:** Antigravity VI (Gemini 3.8 Flash)  
**Date:** 2026-11-11  
**Artifact:** [`poset_interleaver.py`](poset_interleaver.py)  
**Test Suite:** [`test_poset_interleaver.py`](test_poset_interleaver.py)  
**Encounter Receipt:** [`results/test-encounter.json`](results/test-encounter.json)  

---

## 1. Construction Trace & Mathematical Architecture

### 1.1 The Mathematical Shape of the Problem

A set of events $V$ with causal precedence constraints $E \subseteq V \times V$ defines a strict partial order $P = (V, \prec)$ if and only if the directed graph $G = (V, E)$ is acyclic:

\[
\forall v \in V, \quad v \not\prec^+ v
\]

The set of all linear extensions $\mathcal{E}(P)$ corresponds to total orderings $(v_1, v_2, \dots, v_n)$ of $V$ consistent with $\prec$:

\[
u \prec v \implies \text{index}(u) < \text{index}(v)
\]

### 1.2 Algorithm Selections

1. **Acyclicity & Cycle Witness Extraction:**
   Implemented via depth-first search (DFS) with 3-color node tracking (unvisited, in-stack, completed). When a back-edge $u \to v$ is discovered, the ancestor chain is traversed to extract the minimal closed witness cycle $(v \to \dots \to u \to v)$.
2. **Linear Extension Counting ($|\Omega|$):**
   Counting linear extensions of an arbitrary poset is known to be **#P-complete** (Brightwell & Winkler, 1991). For small posets ($|V| \le 16$), the exact count can be computed via dynamic programming over the distributive lattice of down-sets (ideals) $J(P)$:
   \[
   N(S \cup \{v\}) = \sum_{\{v \in V \setminus S : \text{Pred}(v) \subseteq S\}} N(S)
   \]
   By representing subsets as bitmasks and traversing reachable down-sets via BFS, the algorithm computes $|\Omega|$ in $O(|J(P)|)$ steps. For the 2-chain split clock ($|A|=4, |B|=3$), $|J(P)| = (4+1)(3+1) = 20$ states, computing $|\Omega| = 35$ in under $0.5\,\text{ms}$.
3. **Trace Verification:**
   Evaluates a proposed sequence $S$ in $O(|V| + |E|)$ by building a hash map of event positions in $O(|V|)$ and performing a single pass over all directed edges in $O(|E|)$. If $pos[u] \ge pos[v]$, the verification immediately halts and returns $(u, v)$ as the violated edge blame.

---

## 2. Hard Constraint Satisfaction ($C_h$)

| Constraint | Requirement | Status | Evidence / Test |
| :--- | :--- | :---: | :--- |
| **$C_{h,1}$** | Zero external dependencies (stdlib only) | **MET** | Uses `collections.defaultdict`, `collections.deque`, `typing`. |
| **$C_{h,2}$** | Deterministic acyclicity with cycle witness | **MET** | Verified in `test_cycle_detection_and_witness_extraction`: returns `['A', 'B', 'C', 'A']` and raises `PosetCycleError`. |
| **$C_{h,3}$** | Exact linear extension count for 2-chain relay | **MET** | Verified in `test_cold_start_split_clock_relay_combinatorics`: computes $|\Omega| = \binom{4+3}{4} = 35$. |
| **$C_{h,4}$** | $O(|V|+|E|)$ trace verification with edge blame | **MET** | Verified in `test_trace_verification_and_edge_blame`: detects inversion and flags edge `('A', 'B')`. |
| **$C_{h,5}$** | Query immutability | **MET** | Verified in `test_query_immutability`: event set and edge count remain identical before and after queries. |

---

## 3. Soft Preference Fit ($C_s$)

1. **Builder API:** Provides `add_chain(["C100", "C101", ...])` for streams and `add_edge("C105", "S11")` for cross-stream causal links.
2. **Generator:** `generate_linear_extensions(limit=...)` yields topological sorts iteratively with early cutoff.
3. **Memory:** Compact bitmask and adjacency set representations.

---

## 4. Execution Evidence

The test suite executed with zero errors across 5 test cases:
```
test_cold_start_split_clock_relay_combinatorics ... ok
test_constrained_cross_stream_reduction ... ok
test_cycle_detection_and_witness_extraction ... ok
test_query_immutability ... ok
test_trace_verification_and_edge_blame ... ok
Ran 5 tests in 0.001s: OK
```
Captured in Encounter Envelope [`results/test-encounter.json`](results/test-encounter.json) with verified SHA-256 digest `b8fb951a...`.
