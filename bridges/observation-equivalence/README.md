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

In the Invariant-Binary-Verification (IBV) model, a program binary $B$ interpreted under context $C$ defines a transition system $\mathcal{M}(B,C)=(S_C,T_{B,C},I_C,O_C)$. For a verification property $P$, define current-output equivalence:

\[
s\sim_O t \iff O_P(s)=O_P(t).
\]

This is a useful observation partition, but it is not necessarily a safe transition-system quotient. A deterministic abstraction must also preserve transitions. A relation $\approx$ is a transition congruence when:

\[
s\approx t \implies T(s,a)\approx T(t,a)\quad\text{for every permitted action }a,
\]

and equivalent states have the same relevant current outputs. If actions are partial, their enabled-action sets must also agree. Otherwise two states that look identical now can produce distinguishable futures after the same action.

The companion [transition congruence checker](transition_congruence.py) tests whether a finite partition induced by supplied observations is already stable under every supplied action. The same module now includes [refine_to_transition_congruence](transition_congruence.py), which repeatedly splits blocks by successor-block signatures until it reaches the coarsest transition-stable refinement contained in the initial observation partition. The checker and refiner are exhaustive only over the finite state set, action set, and observation tests supplied; each supplied action must be defined for every state and keep successors within the supplied state set.

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

A finite description can denote a much larger set than it explicitly stores. For example, the unit interval $[0,1]$ contains uncountably many real values, while a finite query may ask only for a particular digit or finite-precision observation.

For an exact rational $p/q$ and a fractional digit position $k\geq1$, the $k$th decimal digit can be obtained without expanding all preceding digits. Let $r=10^k\bmod 10q$. Then:

\[
d_k=\left\lfloor\frac{p r}{q}\right\rfloor\bmod 10.
\]

The modulus $10q$ preserves the quotient modulo 10; using $10^k\bmod q$ alone is not sufficient to recover the digit. Modular exponentiation computes $r$ in $O(\log k)$ modular multiplications. This statement assumes an exact integer numerator/denominator representation and a fixed ordinary-decimal convention; repeating expansions such as 0.4999... and 0.5000... require an explicit representation convention.


---

## 3. The Distinction Lattice: When Does Information Add a Distinction?

Let $\sim_1$ and $\sim_2$ be equivalence relations over state space $S$ representing properties $P_1$ and $P_2$. Their joint observation induces the intersection relation:

\[
s\sim_{1\land2}t\iff(s\sim_1t)\land(s\sim_2t).
\]

The quotient cardinality obeys:

\[
|S/\sim_{1\land2}|\leq |S/\sim_1|\,|S/\sim_2|.
\]

Equality holds exactly when every pair of blocks from the two original partitions has a non-empty intersection. For parity and length modulo $k$ over all finite binary strings, every combination is reachable, so the joint quotient has exactly $2k$ blocks.

### Three regimes of distinction

1. **Full Cartesian refinement.** Two observations separate every combination of their respective classes. Their joint partition reaches the product bound. This is an information-state expansion, not necessarily a geometric dimension or statistical-independence claim.
2. **Redundant refinement.** If $P_2$ is already constant on every $\sim_1$ class, then $\sim_1\cap\sim_2=\sim_1$. The second observation adds no new distinguishability relative to the first.
3. **Unbounded distinguishability.** The language $\{0^n1^n:n\geq0\}$ has infinitely many Myhill-Nerode equivalence classes because any two prefixes $0^i$ and $0^j$ with $i\ne j$ are distinguished by suffix $1^i$. Thus no finite-state automaton recognizes it. This is a statement about finite-state recognition, not a claim that every computational model or navigation strategy fails.


---

## 4. Demonstrating the Bridge

The companion script [`demonstration.py`](demonstration.py) demonstrates how one generic finite-test quotient checker can be applied to:
1. Formal language prefix equivalence (Trial 02).
2. Machine register observation equivalence (IBV).
3. Affine structural memory generator equivalence (E-CPU).

These runs compare finite lists of prefixes, register tests, and coordinates. Their output classes are finite-test quotients. For the formal-language example, a single distinguishing suffix proves a particular pair inequivalent; failure to find a suffix in a bounded list does not prove the pair universally equivalent.

The accompanying test suite [`test_demonstration.py`](test_demonstration.py) verifies finite-test partition properties and includes a counterexample showing that a bounded suffix suite can miss a longer Myhill-Nerode distinguishing continuation. It does not infer universal equivalence from a finite sample.

The [transition congruence checker](transition_congruence.py) tests whether current observational classes remain valid after every supplied transition, while its partition refiner computes the coarsest stable refinement without merging initially distinct blocks. Tests include a one-step state-phase example and a two-step example where a distinction propagates backward from future behavior. The separate [affine orbit checker](affine_orbit_equivalence.py) uses product-state cycle detection to prove all-future equality for two deterministic affine generators over a shared finite modulus, or returns `unknown` when a configured budget expires.
The initial [execution receipt](results/bridge-encounter.json) records the original demonstration run. Subsequent code changes are checked by the current CI test suite; the initial receipt is not a receipt for every later revision.

See also [Trial 03: Distinction Refinement](../../experiments/description-to-realization/trials/trial-03-distinction-refinement/README.md), which implements finite partition refinement and conditional entropy $H(D \mid O)$.

For affine structural generators over a shared finite modulus, [affine_orbit_equivalence.py](affine_orbit_equivalence.py) compares paired trajectories. If a pair-state repeats after every earlier output matched, deterministic evolution proves all future outputs match. A finite budget that expires first returns `unknown`, not `equivalent`.

Run the demonstration and tests:

```bash
python bridges/observation-equivalence/demonstration.py
python -m unittest discover -s bridges/observation-equivalence -p "test_*.py" -v
```
