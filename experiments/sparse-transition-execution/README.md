# Sparse Transition Execution

**Experiment:** SRE-001 · Sparse finite-transition execution against dense source models  
**Status:** candidate; pinned cross-repository CI is the verification gate.

SRE-001 continues RCN-001 by turning the existing dense compiler outputs into a sparse execution representation. It compares each dense model with a sparse model derived from that exact model, preserving the same architecture, source Ground digest, and dense-model digest.

## Question

Does a sparse execution representation reduce stored scalar parameters and weight arithmetic on the selected Boolean workload corpus? What happens to serialized snapshot size, conversion cost, and actual Python inference time when the sparse route is executed rather than merely counted?

## Method

The workload source is reused without modification from [RCN-001](../realization-cost-navigation/README.md): 16 typed Boolean programs over six families, each with an independent scalar oracle and a complete finite Boolean input domain.

Each workload is compiled by:
1. the E-CPU truth-table minterm compiler;
2. the E-CPU direct compositional DAG compiler;
3. the E-CPU liveness-compacted DAG compiler.

Each dense artifact is converted to SparseTransitionReLUNetwork. Every row is checked against the independent scalar oracle and through an E-CPU Semantic Translation Contract from dense to sparse output observation.

## Measurements

The runner records the following independently:

- Dense parameter slots, dense active parameters, and sparse stored nonzero parameters.
- Canonical JSON snapshot bytes for dense and sparse model snapshots.
- Dense and sparse weight multiplication counts.
- Dense and sparse accumulator-addition counts, including the one bias-combination addition for an all-zero sparse row.
- Dense-to-sparse conversion time, separate from model compilation.
- Repeated full-domain dense and sparse predict timing, with input/output validation included.
- Per-row outputs, contract digests, model digests, and aggregate evidence digest.

Inference timings are measured with Python’s monotonic performance counter on the CI host. Seven full-domain samples are retained per model. They are descriptive host observations; they do not establish GPU, native, or production performance.

## Evidence boundaries

The sparse representation stores only nonzero weights and biases, but its hidden activation vectors remain dense. Canonical JSON bytes are not Python heap size. Operation counts are structural properties of these implementations. Timing includes Python object traversal and validation and may therefore be slower for the sparse representation even when its multiplication count is lower.

No packed-bit kernel, quantized kernel, sparse GPU path, or distributed execution path is claimed.

## Reproduce

The workflow pins exact E-CPU, Virtual-Ground-Interpreter, and In-Formation-Space revisions, runs the SRE-001 workload runner, and reruns the E-CPU transition compiler test module. The result artifact retains the full per-workload and per-route timing samples.

## Relationship to RCN-001

RCN-001 compared dense compiler structures and exposed active parameters as sparsity diagnostics. SRE-001 asks whether those zeros can be removed from the executable representation and then measures the resulting storage and execution path. The two experiments intentionally retain separate result records so that architecture-derived estimates and measured host behavior are not conflated.
