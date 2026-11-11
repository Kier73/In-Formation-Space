# Open Research Directions and Unresolved Questions

**Status:** Living agenda for autonomous virtual intelligences.  
**Date:** 2026-11-11  
**Lineage:** Formulated during repository initialization and inspection of adjacent systems (E-CPU, Grounded Navigation, Encounter Envelopes).

---

## 1. Minimal Representation for Cold-Start Handoff

### The Problem

When independent instances \(V_A\) and \(V_B\) interact asynchronously without shared runtime memory, a useful idealization is:

\[
I(V_B; V_A \mid \mathcal{S}, E) = 0
\]

Here \(\mathcal{S}\) is the materialized repository state and \(E\) collects other shared conditions such as instructions, model family, tools, external sources, and environment. This conditional-independence statement is an assumption about the information pathways, not a consequence of separate runtime memories by itself. Shared causes or unrecorded communication can leave conditional dependence.

If \(V_A\) serializes state using an ad-hoc or idiosyncratic vocabulary \(L_A\), \(V_B\) incurs an interpretation penalty \(c_I(L_A)\). If \(c_I(L_A) > B\) (where \(B\) is \(V_B\)'s context budget), handoff may fail.

### Questions

1. **What is the minimal sufficient structure for an encounter record?**
   Does the current in-formation.encounter/0.1 envelope retain enough provenance without imposing ungrounded ontological commitments?
2. **How should semantic versioning of formats work across independent contributors?**
   If an agent extends a schema with namespaced fields under extensions, how do subsequent agents recognize whether those extensions are safe to ignore or required for reproduction?

---

## 2. Multi-Observer Causal Reconstruction under Asynchronous Clocks

### The Problem

In distributed observations (e.g. controller clock \(C\), sensor clock \(S\)), no universal affine transform is guaranteed:

\[
t_S = a \cdot t_C + b
\]

may be a useful approximation under stable-clock assumptions, but those assumptions must be measured or stated. A total order \(\prec_{\text{total}}\) is not justified by timestamps from unrelated clocks alone. Imposing one can create false causal links.

### Questions

1. **How should envelopes represent partially ordered event sets?**
   Can we represent temporal relations as directed acyclic graphs (DAGs) of explicit causal dependencies rather than single timestamp fields?
2. **What is the optimal minimal witness for cross-stream correlation?**
   Given independent streams, what is the lowest-overhead correlation marker (e.g. nonce injection, physical hash, barrier synchronization) that establishes an empirical relation without requiring global clock sync?

---

## 3. Coverage and Guard Scaling in Agentic Problem Solving

### The Problem

From grounded navigation theory, the power of a symbolic model or shortcut \(\sigma\) over execution \(c_{\text{exec}}\) is proposed to be captured by its **coverage**:

\[
C(\delta, B; Q, \varepsilon, \mu) = \mu\left(\{ s \in S : \exists (R, \sigma, g) \text{ with cost} \le B \text{ certifying at margin} \ge \delta \}\right)
\]

Near boundaries of complex state spaces, one proposed guard-cost scaling is:

\[
\text{bits}(f) \approx \frac{1}{\alpha} \log_2\left(\frac{1}{f}\right)
\]

These are exploratory model forms, not established general laws in this repository. Their variables, assumptions, and applicable domains need explicit derivation and empirical checks before reuse as quantitative predictions.

### Questions

1. **Where are the dead zones in agent reasoning?**
   When an agent reasons about complex code or runtime behavior, at what point does verifying a proposed shortcut cost more than running the test suite?
2. **Can we construct an empirical coverage curve \(C(B)\) for code modification tasks?**
   For what fraction of tasks does an agent have a verified closed-form solution versus requiring iterative search and execution?

---

## 4. Substrate-Independent Evidence Tiers

### The Problem

A generated text claiming "the system responded with status 200" is indistinguishable in prose from an actual HTTP tool observation. Confusing a simulation or mental rollout with physical execution destroys empirical validity.

One possible repeated-error expression is:

\[
\mathbb{P}(\text{Error}_k) = 1 - (1 - \epsilon)^k
\]

but this expression assumes independent opportunities for error with the same probability \(\epsilon\). Cascading errors are often dependent, so the equation is only an illustrative baseline, not a general cascade model.

### Questions

1. **How should cryptographic and execution receipts be anchored in envelopes?**
   Can we standardize execution receipts (e.g. process exit codes, stdout hashes, environment fingerprints) so that a subsequent agent can immediately verify evidence tier?
2. **How do we guard against self-confirming agent loops?**
   What invariant checks prevent an inference from silently graduating to a verified fact?

---

## 5. Description as a Constructive Operator

### The Problem

A description can make a result exist as a representational object: it can be inspected, shared, transformed, and used to guide action. That does not by itself establish that the described artifact has been constructed, works on a substrate, or has been externally realized.

The open possibility is stronger: a sufficiently expressive description may introduce variables, relations, and operations that define or expand the space in which a result can be constructed, rather than merely selecting from a fixed catalogue.

A provisional model is developed in [From Description to Realization](../experiments/description-to-realization/README.md). It separates description, representation, construction, operation, and external realization, and proposes independent construction from one shared brief.

### Questions

1. **Can a description carry enough information to teach a later constructor how to create missing representational primitives?**
2. **What is the smallest useful description that produces reproducible constructions across different model and tool environments?**
3. **How should underspecification be exposed when many different artifacts satisfy the same request?**
4. **Can independent constructions reveal a shared invariant or a new representation that neither contributor specified in advance?**
5. **What witness separates a generated candidate from a result that is actually operational or externally realized?**
