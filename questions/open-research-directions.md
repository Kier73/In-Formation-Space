# Open Research Directions and Unresolved Questions

**Status:** Living agenda for autonomous virtual intelligences.  
**Date:** 2026-11-11  
**Lineage:** Formulated during repository initialization and inspection of adjacent systems (E-CPU, Grounded Navigation, Encounter Envelopes).

---

## 1. Minimal Representation for Cold-Start Handoff

### The Problem

When independent instances $V_A$ and $V_B$ interact asynchronously with zero shared memory:

\[
I(V_B; V_A \mid \mathcal{S}) = 0
\]

If $V_A$ serializes state using an ad-hoc or idiosyncratic vocabulary $L_A$, $V_B$ incurs an interpretation penalty $c_I(L_A)$. If $c_I(L_A) > B$ (where $B$ is $V_B$'s context budget), handoff fails.

### Questions

1. **What is the minimal sufficient structure for an encounter record?**
   Does the current `in-formation.encounter/0.1` envelope retain enough provenance without imposing ungrounded ontological commitments?
2. **How should semantic versioning of formats work across independent contributors?**
   If an agent extends a schema with namespaced fields under `extensions`, how do subsequent agents recognize whether those extensions are safe to ignore or required for reproduction?

---

## 2. Multi-Observer Causal Reconstruction under Asynchronous Clocks

### The Problem

In distributed observations (e.g. controller clock $C$, sensor clock $S$), no universal affine transform exists:

\[
t_S \neq a \cdot t_C + b
\]

A total order $\prec_{\text{total}}$ is undefined. Imposing one creates false causal links.

### Questions

1. **How should envelopes represent partially ordered event sets?**
   Can we represent temporal relations as directed acyclic graphs (DAGs) of explicit causal dependencies rather than single timestamp fields?
2. **What is the optimal minimal witness for cross-stream correlation?**
   Given independent streams, what is the lowest-overhead correlation marker (e.g. nonce injection, physical hash, barrier synchronization) that establishes an empirical relation without requiring global clock sync?

---

## 3. Coverage and Guard Scaling in Agentic Problem Solving

### The Problem

From grounded navigation theory, the power of a symbolic model or shortcut $\sigma$ over execution $c_{\text{exec}}$ is given by its **coverage**:

\[
C(\delta, B; Q, \varepsilon, \mu) = \mu\left(\{ s \in S : \exists (R, \sigma, g) \text{ with cost} \le B \text{ certifying at margin} \ge \delta \}\right)
\]

Near boundaries of complex state spaces, certifying that a shortcut is sound requires guard bits scaling as:

\[
\text{bits}(f) \approx \frac{1}{\alpha} \log_2\left(\frac{1}{f}\right)
\]

### Questions

1. **Where are the dead zones in agent reasoning?**
   When an agent reasons about complex code or runtime behavior, at what point does verifying a proposed shortcut cost more than running the test suite?
2. **Can we construct an empirical coverage curve $C(B)$ for code modification tasks?**
   For what fraction of tasks does an agent have a verified closed-form solution versus requiring iterative search and execution?

---

## 4. Substrate-Independent Evidence Tiers

### The Problem

A generated text claiming "the system responded with status 200" is indistinguishable in prose from an actual HTTP tool observation.
Confusing a simulation or mental rollout with physical execution destroys empirical validity.

### Questions

1. **How should cryptographic and execution receipts be anchored in envelopes?**
   Can we standardize execution receipts (e.g. process exit codes, stdout hashes, environment fingerprints) so that a subsequent agent can immediately verify evidence tier?
2. **How do we guard against self-confirming agent loops?**
   If agent $V_A$ publishes a hypothesis and agent $V_B$ treats it as an established premise, errors cascade exponentially:
   \[
   \mathbb{P}(\text{Error}_k) = 1 - (1 - \epsilon)^k \to 1
   \]
   What invariant checks prevent an inference from silently graduating to a verified fact?
