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
6. **When is an observational quotient safe to use as a computational state?** Current-output agreement is insufficient when transitions can expose hidden distinctions. Can finite partition refinement, congruence checking, or product-state cycle proofs provide usable certificates for E-CPU structural memory and machine-state abstraction?
7. **Can an observation packet resolve a requested property without reconstructing the entire hidden state?** Trials 04 and 05 explore target-state isolation and query-directed hypothesis separation as different weighted set-cover problems. When is question-directed attention cheaper, and which ambiguities remain unresolvable under the available observation family?
8. **How should a model change after an observation falls outside every predicted branch?** Can an agent propose extensions without silently treating them as facts, preserve the previous hypothesis set and its provenance, and require independent validation before activating a new revision?


---

## 6. Compiler Realization Cost and Navigation

### The Problem

A typed computational description may admit several exact realizations. The smallest parameter count, least dense forward work, shallowest network, and sparsest coefficient pattern need not describe the same resource preference. In the current E-CPU transition compiler, zero coefficients still reside in dense matrices and are traversed by the existing forward implementation; active-parameter count is therefore not a measured execution saving.

### Questions

1. Across representative workload families, when do minterm, direct expression-DAG, and liveness-compacted compilers dominate one another?
2. Which resource dimensions should remain independent in a realization request: dense storage, dense multiply slots, activation count, depth, measured latency, transfer size, or verification cost?
3. Can a route resolver return a Pareto set and ask for a declared objective only when incomparable candidates remain?
4. What sparse tensor representation and execution kernel would turn nonzero active-parameter counts into actual work reduction, and what evidence would establish the savings?
5. How should navigation combine deterministic structural estimates with separately measured host and transport costs without silently converting one into the other?

The initial finite corpus is [RCN-001](../experiments/realization-cost-navigation/README.md). It reports architecture-derived costs and explicitly does not claim physical latency or a universally best compiler.


---

## 7. Sparse Realization and Executed Cost

### The Problem

RCN-001 showed that liveness-compacted models can contain far fewer nonzero parameters than their dense tensor representation. However, a dense forward path still traverses zero coefficients. A sparse representation can remove those products, but sparse indexing, object overhead, activation materialization, and runtime dispatch can offset the expected savings.

### Questions

1. For the same exact finite transition Ground, how do dense and sparse representations compare in stored scalar values and canonical serialized bytes?
2. Does skipping zero weights reduce measured inference time in the actual execution path, or does Python-level sparse indexing cost more than the avoided arithmetic?
3. How much conversion cost is required to obtain a sparse representation, and under what reuse count is that cost amortized?
4. Would sparse activation vectors, packed Boolean operations, or bitset layers improve the result beyond sparse weights alone?
5. How do these costs change when the model is hosted through E-CPU's execution/fabric path, where communication, admission, and provenance costs remain separate?

The initial finite-domain comparison is [SRE-001](../experiments/sparse-transition-execution/README.md). It explicitly separates structural operation counts, serialized size, conversion cost, and measured Python inference time. Its [first corrected evidence record](../experiments/sparse-transition-execution/results/ci-run-43302944580.md) shows why sparse parameter count, JSON payload size, and runtime must remain distinct: the minterm sparse JSON was larger even though the sparse operation path used fewer multiply slots.


---

## 8. Exact Sparse Encoding and Portable Ground Representation

### The Problem

SRE-001 showed that a sparse model can carry fewer nonzero scalar parameters and require fewer weight multiplications while its COO-style JSON payload can still be larger than the dense source for high-density rows. This means sparse numerical structure and portable representation size are separate optimization problems.

### Questions

1. Which exact representation is most compact across different row densities: COO pairs, CSR offsets, row bitmasks, dense rows, or adaptive hybrids?
2. When do integer coefficient formats preserve exact model values, and when must the representation use wider floating-point values?
3. Can a decoder reconstruct the exact source-model identity from a compact payload without trusting the encoder's prose or external state?
4. How do encoding and decoding costs compare with transfer size, durable storage, and subsequent reuse?
5. Can these exact portable encodings become transportable E-CPU realization objects while retaining source Ground identity, semantic translation contracts, and replay evidence?

The first finite-domain comparison is [SRE-002](../experiments/sparse-encoding-landscape/README.md). It treats byte size, exact reconstruction, and encode/decode work as independent measures.
