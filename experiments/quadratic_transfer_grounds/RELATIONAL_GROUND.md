# TCN-010 — Relation-Constructed Computational Grounds

**Status:** executable research prototype; 20 November 2026. This extends [TCN-009](SYSTEM_GROUND.md) and [TCN-008](INTENTION_GROUND.md) in `experiments/quadratic_transfer_grounds`. The implementation is `relational_ground.py`; its 26 independent regression tests and deterministic example runner are `test_relational_ground.py` and `run_relational_ground.py`.

## Goal: the intention determines the variables

TCN-009 constructs polynomial transition laws over an **already given** scalar variable. TCN-010 receives only a **finite set of named states**, a complete deterministic table of available actions, exact observable outputs, an observer's selected channels, a set of safe states, an intended observable conjunction, and declared host capabilities. It constructs:

1. The **observer-relative state quotient**. Two named states become equivalent only when they have the same selected outputs and safety status and no declared action sequence can distinguish them.
2. A **state coordinate space** and the mathematical representation of each operator. Its dimension is inferred, not declared.
3. Exact **observable decoders** in those coordinates.
4. An **invariant guard** for every action, rejecting transitions whose destination leaves the permitted state set.
5. An **intention-directed action/host plan** under finite execution and host-switch costs, or a specific refusal witness.
6. A SHA-256-bound **reconstructable mathematical receipt**, with optional export through VGI's existing typed finite maps and an actual phase readout delegated to TCN-008.

**Important:** The full transition table, output records, and safety classifications are supplied as part of the intention. TCN-010 does *not* discover unknown physical laws from partial observations. Unlike VGI's three-valued partial comparison, a missing edge is rejected at specification validation rather than interpreted as a negative edge. This is finite **model construction**, not general intelligence or arbitrary system synthesis.

## Compact family: a character Ground constructed from action relations

If the induced observer-quotient actions are commuting involutive permutations, the group they generate is a quotient of \((\mathbb Z/2\mathbb Z)^m\). In the supported **single transitive orbit** case it is an elementary abelian group of size \(2^r\), where \(r\) is discovered through independent action-generator doubling.

For each quotient state, compute its derived binary coordinate \(b=(b_0,\ldots,b_{r-1})\). Embed that state into \(\mathbb F_p^r\) for odd prime \(p\) as **character coordinates**:

\[
z_j=(-1)^{b_j}\pmod p.
\]

Every action becomes an exact **diagonal** linear operator

\[
z'_j=(-1)^{\delta_{a,j}}z_j\pmod p,\qquad
D_a=\operatorname{diag}((-1)^{\delta_{a,0}},\ldots,(-1)^{\delta_{a,r-1}}).
\]

The compiler checks every edge of the original transition table against these matrices; no floating-point approximation or fitted eigenspectrum is involved. The computational state has only \(r\) field coordinates, but source evidence (the supplied finite graph) remains retained for reconstruction. This is **not** a claim that the full evidence record is of size \(r\).

### Why \(r\) coordinates are necessary in this algebra

For a faithful affine action of the group \((\mathbb Z/2)^r\) on \(\mathbb F_p^d\), \(p\) odd, averaging the orbit of the origin yields a common fixed point because the group order is invertible in the field. Translate that fixed point to zero, leaving a faithful linear representation. Commuting involutions are simultaneously diagonalizable over the field (their minimal polynomials divide \(X^2-1\), whose roots are distinct). Every linear generator is therefore a pattern of \(d\) signs, so there are at most \(2^d\) distinct group elements. **Therefore \(d\ge r\)**. Our character construction attains \(d=r\).

The proof is conditional on **faithful affine representation of the whole observer quotient**, odd characteristic, and a single transitive elementary-abelian action. One arbitrary scalar *lookup table* may encode four distinct states in \(\mathbb F_7\); it does not make their two independent affine swap operations one-dimensional. The tests independently exhaust all 840 injections of four labels into \(\mathbb F_7\) and confirm that no scalar affine pair implements the two independent swaps.

### Observable readouts are synthesized, too

For a requested observable \(f\) defined on the derived hypercube, a normalized Walsh transform over \(\mathbb F_p\) yields an **exact multilinear polynomial**

\[
f(z)=\sum_{S\subseteq\{0,\ldots,r-1\}}\widehat f(S)\prod_{j\in S}z_j,
\quad \widehat f(S)=2^{-r}\sum_b f(b)(-1)^{\sum_{j\in S}b_j}\pmod p.
\]

Every visible output is checked at **all** quotient states. Unselected output channels are recorded as `null`; the compiler **does not reconstruct unobserved variables** by picking an arbitrary representative of an equivalence class. Observer scope can change the required dimension: the same eight-node input needs three character coordinates when three bits are visible, but only one when the observer asks for their parity.

## Construct a different Ground when the first algebra fails

Commuting involutions are *not* universal. If the quotient actions do not commute, are non-involutive, or act on several disconnected orbits, a character Ground is not admitted. TCN-010 may instead construct a generic **finite one-hot Ground**: class \(i\) is basis vector \(e_i\) and the action \(a\) has \(M_a e_i=e_{a(i)}\). These matrices may be non-invertible (for a reset action), and need not commute. Observable decoders are exact linear functionals of the one-hot vector.

This one-hot fallback has dimensional cost \(n\) and up to \(m n^2\) stored matrix entries, versus \(r\) coordinates and \(mr\) diagonal entries for the character Ground. The fallback is capped by `max_onehot_dimension` (default 32), and the compiler does **not** claim it is dimension-optimal. When both representations are feasible it selects by declared host execution cost, then dimension, then stored operator entries. This is a finite comparison of two *specified* families, not an open-ended Ground search or a universal minimum.

### Constructed safety and host-dependent navigation

The safety predicate is included in the observer's partition, and every action receives a guard: an action is admissible at a state only if that state **and its destination** are safe. Dijkstra's search then plans over `(quotient state, last declared host)`, including action cost and inter-host switch cost. This constructs a **guarded execution plan**; it does not claim all raw action maps preserve the invariant globally. A grouped fast-forward query is admitted only when every repeated action globally preserves the safe quotient, so no skipped intermediate action can hide a safety violation.

Declared host capability and cost are planning inputs, not authenticated E-CPU capacity or authority. `unreachable_under_safety_guards`, `unreachable_with_declared_hosts`, `refused_execution_budget`, `refused_search_budget`, `refused_representation_budget`, and out-of-family algebra statuses are deliberately distinct. A refused or unsupported **family** is not a theorem that no computational system exists.

## Reproduce and interpret

From the `In-Formation-Space` repository root (Python 3.11+ and NumPy, for the existing TCN-008 bridge):

```sh
python -m pip install numpy
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s experiments/quadratic_transfer_grounds -p 'test_relational_ground.py' -v
OPENBLAS_NUM_THREADS=1 python experiments/quadratic_transfer_grounds/run_relational_ground.py > tcn010-result.json
```

The regression suite covers exact construction across six odd prime fields, eight-bit/256-state derivation, observer-relative quotient contraction, polynomial readout completeness, finite safety guards, missing host and cost refusals, noncommuting and noninvertible fallback, a brute-force affine-obstruction oracle, large grouped action counts, representation-budget refusal, state-renaming invariance, tampered/rehashed receipts, and an **actual call to existing TCN-008** polynomial-phase generation and verification. The compiler has no new external dependencies; the integration test imports TCN-008's existing NumPy-dependent module.

Examples from the local deterministic run:

| Requirement | Generated Ground | Result |
| --- | --- | --- |
| Four named states, independent commuting bit flips, \(p=7\) | 2 character variables, 2×2 diagonal operators | Goal reached in one declared action with composite flip |
| Only two parity-safe states, same actions | 2 character variables + guards | Single-bit flips refused; composite flip reaches goal |
| Eight states and full three-bit observation | 3 character variables | All transitions and visible outputs reconstructed |
| Same eight states, parity-only observer | 1 character variable | Two abstract classes; hidden individual bits **not** reconstructed |
| Noncommuting swaps of three states | 3-coordinate one-hot Ground | Previously unsupported character relation becomes realizable |
| 256 named states, eight independent flips | 8 character variables | Full 256-state graph checked; no one-hot matrix constructed |
| Two action counts near \(10^{100}\) | Characters multiplied by signs based on count parity | No repeated physical steps claimed |

The runner records local timing with a single Python process. Its timings are **not** proof of hardware-neutral savings or a general speedup; graph/quotient construction and receipt verification costs are charged separately from symbolic action navigation.

## Reuse and interoperability

- **VGI:** The stable observer quotient and selected output channels follow the meanings in `virtual_ground_interpreter/vgi/relational.py`. The returned `vgi_space` matches VGI's `FiniteSpace` structural schema. `materialize_vgi_typed_maps` optionally instantiates the **real VGI `FiniteSpace` and `DenseMap` classes** when that package is separately installed. This optional bridge has not been exercised against a live VGI deployment here.
- **E-CPU:** The split between algebraic existence, conditional realization, and live authorization follows `mailcpu/law_certifier.py`, `mailcpu/navigation_admission.py`, and `mailcpu/ground_native_realization.py`. Neither synthesized plans nor SHA-256 receipts are grants of permission or attestations from an external host.
- **TCN-008/009:** `render_terminal_phase` calls the existing TCN-008 `make_intent`, `synthesize`, `make_receipt`, and `verify_receipt`. It uses an *explicit observer convention* to convert a selected terminal observable into a cubic relative-phase output. It does not infer an external phase law or execute the phase operation remotely.

## Context and next frontier

The algebra is established: deterministic finite-state partition refinement and characters of \((\mathbb Z/2)^r\), equivalently Walsh–Hadamard analysis. Relevant references include the [finite-state minimization survey](https://arxiv.org/abs/1010.5318) and [Fourier analysis of finite abelian groups lecture notes](https://www.cs.mcgill.ca/~hatami/comp760-2011/lectures2-3.pdf). The contribution is **joining finite observation scope, constructive coordinate selection, executable guards, cost-aware placement, and reconstructable witnesses** in the emerging TCN workflow—not a new theorem about finite groups.

Next: replace the fully supplied transition table with *partial evidence* and a **three-valued construction** that distinguishes observed, disproved, and still-unknown relations. That requires integrating VGI's native partial-observation contracts rather than calling missing transitions false. It is also necessary before any attempt to construct Grounds on changing, independently observed E-CPU hosts.
