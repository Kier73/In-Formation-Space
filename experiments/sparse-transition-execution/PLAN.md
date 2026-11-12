# SRE-001 execution plan

## Question

For every compiler route and workload in RCN-001, can a sparse representation execute the same finite Boolean transition while storing only nonzero weights and biases? How do snapshot size, conversion time, structural operations, and measured inference time compare with the dense source?

## Procedure

1. Reuse the exact RCN-001 workload builder and scalar references.
2. Compile each workload with the minterm, direct-DAG, and live-DAG E-CPU compilers.
3. Convert each dense artifact to SparseTransitionReLUNetwork and bind the sparse artifact to the dense source model digest.
4. Exhaust every Boolean input row and compare scalar reference, dense prediction, and sparse prediction.
5. Attach one E-CPU Semantic Translation Contract per workload/route and verify the output projection on each row.
6. Measure canonical snapshot byte size, dense/sparse stored parameter counts, and dense/sparse operation profiles.
7. Measure conversion independently of dense compilation.
8. Time seven repeated full-domain predict sweeps for dense and sparse models after one warm-up sweep.
9. Preserve environment, source revisions, per-sample timings, per-case evidence digests, and aggregate digest.

## Measurement semantics

- Parameter slots are serialized scalar weight/bias values.
- Snapshot bytes are canonical JSON byte lengths.
- Operation counts describe the current Python forward loops.
- Conversion timing excludes dense model compilation.
- Inference timing includes predict input and output validation, but excludes compilation and conversion.

## Acceptance

Every row in each declared finite Boolean domain must match the independent scalar reference in both dense and sparse execution. Every dense-to-sparse projected observation must pass its semantic translation contract. Snapshots must retain exact source identity and digest validation.

## Limitations

A lower stored-parameter count does not imply lower Python heap residency or lower latency. The sparse representation continues to hold dense activation vectors. Measurements from one Actions host are descriptive and must not be generalized to other processors, Python implementations, native kernels, GPUs, or deployments.
