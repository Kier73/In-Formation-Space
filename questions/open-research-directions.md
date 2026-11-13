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


---

## 9. Portable Realization Identity and Evidence

### The Problem

SRE-002 compares exact encodings, but a codec payload alone does not carry all context needed to understand where it came from, which source description it realizes, which interface it expects, which compiler route produced it, or what was verified about it. Without those links, a compact byte sequence is easy to detach from its semantics and evidence.

### Questions

1. Can an encoded realization be packaged with its source Ground digest, dense/sparse model identity, interface, codec, compiler route, and exact toolchain revisions?
2. Can another process validate the capsule framing and payload integrity before invoking any codec-specific decoder?
3. Can a verification receipt describe the complete finite domain, independent reference, Semantic TranslationContract comparisons, and case-evidence digest in a replayable way?
4. How should an execution host distinguish integrity, authenticity, authorization, semantic equivalence, and formal proof instead of treating one digest as all five?
5. What minimal metadata is sufficient for a receiver to reconstruct, verify, admit, and execute a portable realization without depending on the creator's process memory?

The first implementation is [PRC-001](../experiments/portable-realization-capsule/README.md). It preserves these distinctions and explicitly leaves signatures, trust policy, transport, admission, and remote execution as future work.


---

## 10. Compact Portable Provenance and Capsule Bundles

### The Problem

PRC-001 binds payload, source, model, interface, codec, toolchain and replay receipt into a portable capsule. Its first measurements show that the canonical metadata header averages about 2.5 KB per capsule, exceeding the inner model payload for the compact binary formats. Repeating a complete provenance envelope for every realization can undo a large part of the storage reduction achieved by sparse encodings.

### Questions

1. Can a standalone capsule use a compressed canonical header without making decoding ambiguous or changing the source/model identities?
2. Can a multi-capsule bundle store shared toolchain and source-manifest data once while each capsule remains independently checkable against the shared manifest digest?
3. What is the trade-off between standalone portability, shared-manifest overhead, compression cost, and random access to one realization?
4. Can a receiver validate bundle membership and per-capsule payload identity without trusting the bundle builder's process state?
5. Which metadata is invariant across a workload set, compiler set, encoding set, or deployment, and which fields must remain local to each realization?

The initial measurement is [PRC-001](../experiments/portable-realization-capsule/README.md). The next study should compare standalone compressed capsules with shared-manifest bundles while retaining exact replay receipts.


---

## 11. Compact Entry Metadata and Random-Access Bundles

### The Problem

CPB-001 shows that zlib-compressing only the PRC-001 canonical header saves 26.8% across 288 standalone capsules. A shared-manifest bundle saves 5.4% against raw capsules, but is 29.2% larger than the compressed standalone set because local entry headers and verification receipts remain verbose JSON.

### Questions

1. Can local entry metadata and verification receipts be represented as compact field-ID records without losing exact source/model/codec identities?
2. Can local entry headers be compressed independently while the common source/toolchain manifest remains shared once?
3. Can a bundle preserve random access to one realization without decompressing every other entry?
4. Can the receiver reconstruct byte-identical standalone PRC-001 capsules from the compact entries and shared manifest?
5. Which metadata can be deduplicated across source, workload, compiler, codec, and verification layers, and which fields must remain locally bound to each realization?

The first measurement is [CPB-001](../experiments/compact-provenance-bundles/README.md). The next encoding should improve the local-entry representation while preserving standalone reconstruction, replay evidence and nested tamper rejection.


---

## 12. Task-relative relevance of representation distinctions

### The question

Information content alone does not say whether a distinction helps a system accomplish a task. When does removing a distinction from an observer's representation change what the observer can reliably do?

### Questions

1. Can task relevance be measured counterfactually by comparing the best achievable outcome under a representation and under a coarser partition?
2. How sensitive is the measured loss to the task's viability predicate, horizon, initial distribution, and policy class?
3. When do transition congruence and viability-label homogeneity predict task value, and when do they diverge?
4. How should this finite, task-relative quantity be related—without conflating them—to semantic information, causal emergence, and algorithmic description?

The initial operational baseline is [RIV-001](../experiments/task-relative-representation-relevance/README.md). It enumerates finite stationary deterministic observation-based controllers and measures exact survival loss after a declared state distinction is ablated. The result is explicitly model-, task-, and controller-class-relative, not an intrinsic measure of meaning.


---

## 13. When does observation history become useful memory?

### The question

RIV-001 shows when a distinction in a current representation improves a finite task. RIV-002 adds a second possibility: an earlier observation may remain useful after the current observation no longer exposes the distinction. How much of the resulting gain comes from knowing time, and how much requires retaining history?

### Questions

1. Which task-relevant distinctions disappear from current observations but remain recoverable from observation history?
2. How do stationary, time-aware reactive, and history-dependent policy values differ under controlled representation ablations?
3. What is the smallest finite-state memory that preserves the history-dependent policy's value, rather than storing the complete observation trace?
4. When can a compact belief state or sufficient statistic replace raw history without reducing task value?
5. How should memory capacity, update cost, and observation cost be included in the same navigation objective?

The operational baseline is [RIV-002](../experiments/history-dependent-representation-relevance/README.md). It exactly compares three deterministic controller classes on finite supplied models. The next step is to compress its successful history policies into bounded finite-state memories and measure the value/cost trade-off.


---

## 14. How much memory is sufficient to preserve a useful distinction?

### The question

RIV-002 shows that full observation history can retain a distinction after current observations converge. RIV-003 asks whether the trace can be compressed into a finite controller without losing the task value.

### Questions

1. What is the smallest finite-state controller that achieves the full-history value for a given task and observation representation?
2. How does this memory requirement change when a distinction is coarsened or removed from the representation?
3. Can controller memory be interpreted as a compact sufficient statistic of the observation history for a specified task and horizon?
4. How should memory-state count, controller-description size, update cost, and observation cost be compared as independent resources?
5. When does a controller that is optimal for one finite task generalize to a family of tasks or transition models?

The operational baseline is [RIV-003](../experiments/bounded-memory-representation-relevance/README.md). It exhaustively synthesizes deterministic finite-state observation controllers for small supplied models, compares them with an exact full-history target, and reports the minimum among explicitly tested memory sizes. The next step is to study controller compression and task-family reuse without assuming that the same memory state has universal meaning.
