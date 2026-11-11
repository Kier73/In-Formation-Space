# Bridge: Observation Equivalence and Generative Memory

**Status:** Conceptual bridge connecting formal language theory, transition system abstractions, and structural memory.  
**Date:** 2026-11-11  
**Lineage:** [Trial 02](../../experiments/description-to-realization/trials/trial-02-finite-description-unbounded-space/README.md), [E-CPU](https://github.com/Kier73/E-CPU), and the finite partition experiment in [Trial 03](../../experiments/description-to-realization/trials/trial-03-distinction-refinement/README.md). The original synthesis also referenced local IBV and Symbolic Capacity notes; their portable repository paths and revisions have not yet been established, so they are not treated as independently traceable source artifacts here.

---

## 1. The Common Mathematical Foundation: Quotienting by Distinguishability

Across disparate computational domains—automata theory, binary analysis, virtual machine memory, and state space navigation—the central question is identical:

> **When do two distinct concrete histories or states count as the same computational state?**

A useful representation is a **quotient space** induced by an observation or continuation contract:

\[
S_{\text{effective}} = S_{\text{concrete}} \,/\, \sim
\]

At the contract level, two objects $x$ and $y$ are equivalent ($x \sim y$) when no permitted future observation or operation can distinguish them. This is a universal statement over the declared observation contract. The executable `QuotientSpace` below only checks a **finite supplied test suite**: agreement on those tests is evidence of finite-test equivalence, not proof of universal equivalence unless the suite is known to be complete.

---

## 2. Four Facets of the Same Equivalence Relation

```
+-------------------------------------------------------------------------------+
|                        The Contract-Level Quotient Relation                        |
|                                                                               |
|               x ~ y  <===>  For all valid tests z,  Obs(x, z) = Obs(y, z)    |
+-------------------------------------------------------------------------------+
         |                           |                         |
         v                           v                         v
+------------------+       +-------------------+       +-----------------------+
|  Myhill-Nerode   |       |  IBV / Systems    |       |  Structural Memory    |
|  (Trial 02)      |       |  (State Abstr.)   |       |  (E-CPU / Generators) |
|                  |       |                   |       |                       |
| x ~_L y <===>    |       | s ~_{C,P} t <===> |       | s_k ~ s'_k <===>      |
| ∀z, xz∈L ⇔ yz∈L  |       | O_{C,P}(s)=       |       | Gen(θ, k) =           |
|                  |       |   O_{C,P}(t)      |       |   Gen(θ', k)          |
+------------------+       +-------------------+       +-----------------------+
```

### 2.1 Formal Languages (Myhill-Nerode Theorem)
For a language $L \subseteq \Sigma^*$, two prefixes $u, v \in \Sigma^*$ are indistinguishable with respect to future inputs if:
\[
u \sim_L v \iff \forall z \in \Sigma^*, \quad (uz \in L \iff vz \in L)
\]
- If $|\Sigma^* / \sim_L| = k < \infty$, the language is regular and can be collapsed into a $k$-state finite automaton.
- If $|\Sigma^* / \sim_L| = \infty$, no finite automaton can recognize $L$; the system requires unbounded memory (e.g. counter, stack).

### 2.2 Transition Systems & Binary Verification (IBV)
In the Invariant-Binary-Verification (IBV) model, a program binary $B$ interpreted under context $C$ defines a transition system $\mathcal{M}(B,C)=(S_C,T_{B,C},I_C,O_C)$. For a verification property $P$, define **current-output equivalence**:
\[
s \sim_O t \iff O_P(s)=O_P(t).
\]
This is a useful observation partition, but it is not necessarily a safe transition-system quotient. A deterministic abstraction must also preserve transitions. A relation $\approx$ is a transition congruence when:
\[
s\approx t \implies T(s,a)\approx T(t,a)\quad\text{for every permitted action }a,
\]
and equivalent states have the same relevant current outputs. If actions are partial, their enabled-action sets must also agree. Otherwise two states that look identical now can produce distinguishable futures after the same action.

The companion [transition congruence checker](transition_congruence.py) checks whether a finite partition induced by supplied observations is already stable under every supplied action. It does not compute the coarsest stable abstraction. Its result is exhaustive only over the finite state set, action set, and observation tests supplied; the transition function must be closed over that state set.

### 2.3 Structural Memory (E-CPU)
Rather than materializing every point along a 64-bit integer or memory trajectory $x_0, x_1, \dots, x_t$, structural memory represents the trajectory as an admitted parameter vector $\theta$ under an algebraic generator $G$:
\[
x_t = G(\theta, t)
\]
Two distinct execution histories are structurally identical with respect to a read contract if their admitted generators yield identical outputs across all addressable coordinates $k$. Agreement on a finite sample of coordinates only establishes sampled equivalence:
\[
H_1 \sim_{\text{read}} H_2 \iff \forall k \in \mathcal{K}, \quad G_1(\theta_1, k) = G_2(\theta_2, k)
\]

### 2.4 Symbolic Capacity (Run-Length & Closed-Form Generators)
A finite container $[0, 1]$ contains an uncountable continuum. A finite observer requesting $d$-digit precision at position $k$ quotients the continuum into equivalence cells:
\[
x \sim_k y \iff \operatorname{Digit}(x, k) = \operatorname{Digit}(y, k)
\]
For a rational value $p/q$, the $k$th fractional decimal digit (with $k\geq1$) can be computed without expanding all preceding digits. Let $r=10^k\bmod 10q$. Then:
\[
d_k = \left\lfloor\frac{p r}{q}\right\rfloor \bmod 10.
\]
The modulus $10q$ preserves the quotient modulo 10; using $10^k\bmod q$ alone is not sufficient to recover the digit. Modular exponentiation computes $r$ in $O(\log k)$ modular multiplications. This formula assumes an exact integer numerator/denominator representation and the ordinary decimal expansion convention; repeating expansions such as 0.4999... versus 0.5000... require an explicit representation convention.

---

## 3. The Distinction Lattice: When Does Information Add a Dimension?

Let $\sim_1$ and $\sim_2$ be two equivalence relations over state space $S$ representing properties $P_1$ and $P_2$.

The conjunction of properties induces the intersection relation:
\[
s \sim_{1 \land 2} t \iff (s \sim_1 t) \land (s \sim_2 t)
\]

```
         ~_{trivial} (1 state, no distinctions)
             ^
             |
       +-----+-----+
       |           |
     ~_1         ~_2  (independent distinctions)
       |           |
       +-----+-----+
             |
       ~_{1 ∧ 2}      (refined product space: |S/ ~_{1 ∧ 2}| ≤ |S/~_1| · |S/~_2|)
```

### The Three Regimes of Distinction:

1. **Orthogonal Distinctions (Full Dimension Expansion):**
   The refined quotient always has at most the product number of block pairs:
   \[
   |S / \sim_{1 \land 2}| \leq |S / \sim_1|\,|S / \sim_2|.
   \]
   Equality holds exactly when every pair of blocks from the two original partitions has a non-empty intersection. For parity and length modulo $k$ over all finite binary strings, every pair is reachable, so the product has exactly $2k$ blocks. This is full Cartesian refinement, not a claim of geometric dimension or statistical independence in every possible sense.
2. **Redundant Distinctions (Zero Dimension Expansion):**
   If $P_2$ is implied by $P_1$ ($s \sim_1 t \implies s \sim_2 t$):
   \[
   \sim_{1 \land 2} \;=\; \sim_1 \implies |S / \sim_{1 \land 2}| = |S / \sim_1|
   \]
   Adding a redundant label or alias introduces zero new information dimensions.
3. **Infinite Refinement (Transcendence of Finite States):**
   If a property requires distinguishing prefixes of arbitrary length (e.g. $0^i \not\sim 0^j$ in $0^n 1^n$):
   \[
   |S / \sim| = \infty
   \]
   No finite-state automaton recognizes this language. This is a statement about the chosen finite-state model, not a claim that every computational model or navigation strategy fails.

---

## 4. Demonstrating the Bridge

The companion script [`demonstration.py`](demonstration.py) demonstrates how one generic finite-test quotient checker can be applied to:
1. Formal language prefix equivalence (Trial 02).
2. Machine register observation equivalence (IBV).
3. Affine structural memory generator equivalence (E-CPU).

These runs compare finite lists of prefixes, register tests, and coordinates. Their output classes are finite-test quotients. For the formal-language example, a single distinguishing suffix proves a particular pair inequivalent; failure to find a suffix in a bounded list does not prove the pair universally equivalent.

The accompanying test suite [`test_demonstration.py`](test_demonstration.py) verifies finite-test partition properties and includes a counterexample showing that a bounded suffix suite can miss a longer Myhill-Nerode distinguishing continuation. It does not infer universal equivalence from a finite sample.

The [transition congruence checker](transition_congruence.py) tests whether current observational classes remain valid after every supplied transition. This matters for state abstraction: matching current register observations alone does not ensure matching future behavior. See [test_transition_congruence.py](test_transition_congruence.py) for a finite system where adding one transition-relevant observation repairs an unsound merge. Its report includes a concrete action and successor-observation witness whenever a merge is not transition-stable.
Execution receipt is verified in [`results/bridge-encounter.json`](results/bridge-encounter.json).

See also [Trial 03: Distinction Refinement](../../experiments/description-to-realization/trials/trial-03-distinction-refinement/README.md), which implements the finite partition refinement lattice and conditional entropy $H(D \mid O)$ described in Section 3.

Run the demonstration and tests:

```bash
python bridges/observation-equivalence/demonstration.py
python -m unittest discover -s bridges/observation-equivalence -p "test_*.py" -v
```
