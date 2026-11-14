# PNF-004: functional models addressed through admitted Grounds

## Functional benchmark

An E-CPU observer-host should be able to resolve a model description and its
admitted parameter coordinates into a typed inference operation; use its
results to propose or prioritize Ground construction; independently verify
those proposals; and reconstruct the same model and admitted task Grounds
after a host restart or a change of inference implementation. Measure semantic
agreement, rejected invalid proposals, receiver authority, persistent identity,
work counts and actual local time separately.

This builds on [PNF-003](../procedural_neural_formation/NATIVE-REALIZATION-003.md).
The first functional case is deliberately small: a **hand-designed 2-input,
2-ReLU, 1-output neural ranker** helps choose between integer-step and affine
modular laws. It is neither trained nor a language model. The ranker orders
proposals; the existing E-CPU structural-memory verifier and receiver policy
own Ground admission.

## Existing E-CPU mechanisms used

| Concern | Actual mechanism |
| --- | --- |
| Model description | `ComputationalObjectStore` M1 manifest and verified pages |
| Persistent bytes | Existing `RemotePageStore` local CAS, single-node mailbox backing |
| Parameter field | Admitted `lcg` structural-memory revision with exact context |
| Parameter addresses | `VirtualStructuralMemoryRef` at 10^12 and 10^12 + 1 |
| Execution context | Admitted `SystemSeedEnvelope` and `VirtualGroundRef` |
| Model inference | Schema-v2 `VirtualLayerWorkload`, registered pure operator, Hypervisor |
| Read authority | Runtime resolves declared structural bindings after receiver authorization |
| Task Ground creation | `StructuralMemoryRegistry.propose` / `admit`, independent witnesses |
| State persistence | E-CPU checkpoint save/load, externally pinned checkpoint bytes |
| Restart | Supervisor forcibly terminates the first interpreter at a durable barrier |

The earlier E-CPU exploration found `ProceduralWeightField`, but the current
structural-memory generator ABI admits `int`, `lcg`, `gf2` and `fgraph`, not an
arbitrary SHA-based float field. This experiment therefore uses an existing
admitted LCG law rather than declaring an unsupported neural Ground family.
The LCG is a chosen parameter-generation definition, not an inferred model of
unknown pretrained weights.

## Model, input encoder and inference paths

The immutable M1 description declares architecture, fixed identity up-matrix,
zero biases, coefficient decoder and the complete revision/context/digest
bindings. No dense parameter array is persisted. The two integer field values
are resolved through E-CPU's guarded coordinate navigator. They become exact
dyadic coefficients:

```
error_weight = -(1 + (word_0 mod 1024) / 1024)
cost_weight  = -(1 + (word_1 mod 1024)) / 1048576
score        = error_weight * ReLU(residual) + cost_weight * ReLU(complexity)
```

The 1,067-byte description is not the full persistent footprint: the checkpoint
also stores the parameter law, task observations, receipts, read cache and
execution ledger; M1 storage pads its page. Reports separately measure the
checkpoint and page-backing files. Zero persisted dense arrays does not mean
zero parameter information or zero reconstruction cost.

The input encoder accepts bounded nonnegative integer feature pairs. Candidate
laws are fitted from the first four observations. Ranking features use only
the first eight: summed absolute residual and a simple complexity indicator.
The remaining eight observations are withheld from fitting and inference and
are supplied only to the independent Ground verifier. A bad withheld value
must reject admission even when the ranker confidently selects a law.

No text tokenizer is needed for this numeric task. The input encoder is
versioned as part of model identity. A later text/token adapter must similarly
bind vocabulary, normalization, token IDs and output interpretation; changing
those is a semantic change, not an interchangeable transport detail.

The initial process uses PNF's NumPy dense affine/ReLU/affine evaluator. The
restored process uses an independent scalar evaluation without building those
matrices. Both run as native E-CPU operators with distinct implementation
contract digests. All admitted input values and coefficients are dyadic within
the stated bounds; tests additionally compare the results against integer
arithmetic divided by the exact common power-of-two denominator.

## Recovery and authority

The first process performs the task suite, saves the real HeadlessOS checkpoint
and M1 pages, publishes the externally held identity record, then waits. The
supervisor kills it and starts a new interpreter with only those persisted
files and the explicit policy record. The second host rebinds trusted operator
code, admits a fresh execution context and grants fresh local capabilities.
Its model identity, parameter references, numeric outputs and previously
admitted task Ground revisions must match the original.

Fresh inference has a fresh observer-generation channel. Reusing the old event
identity for a new execution Ground correctly produces E-CPU's conflicting
retransmission rejection; it is not silently treated as replay. Same-context
exact replay is separately tested. Reconstruction recomputes inference; it
does **not** claim exactly-once inference across a crash.

The trust record is provided by the test supervisor, not a publisher signature
or hardware attestation. Checks reject changed checkpoint bytes even if their
internal checksum is recomputed, corrupted M1 pages, replaced manifest/model
pins, unsupported decoders, wrong parameter context/certificate and missing
receiver compute or structural-read rights. The forced stop occurs after a
completed durable checkpoint, not during an arbitrary in-flight commit.

## Results and interpretation

The benchmark uses 16 explicitly synthetic modular trajectories: four integer
steps and twelve affine recurrences. Each accepted law is also navigated to
coordinate 10^12 and compared with an independent binary affine-composition
reference built from the fixture's known generator.

Local results are retained in [local-restart.json](results/local-restart.json).
The initial and restored processes each completed **16/16** tasks. Fixed
candidate order required **28** candidate-verification attempts, while ranked
order required **16**. This counts candidate attempts, not all underlying
verifier calls: admission rechecks evidence, and ranking also has feature and
inference costs. The reported elapsed time includes baseline work.

This is evidence of functional integration and stable addressability, **not**
an optimization or learned-generalization result. A simple non-neural ordering
by residual and complexity could choose identically on this suite. Future
optimization claims require broader held-out task families and a measured
end-to-end advantage over that inexpensive baseline.

Task certificates remain `witness_grounded`: finite witness agreement does not
prove an arbitrary observed process follows the selected law forever. Large
coordinate agreement here uses synthetic fixtures with known generators.
Likewise a model is represented by a typed M1 description plus an admitted
parameter Ground; this does not turn arbitrary neural networks into a new
universally certified Ground family. VGI/kernel proof integration remains a
separate endeavor.

## Reproduce and extend

With the E-CPU repository on `PYTHONPATH` and NumPy installed:

```bash
python -m unittest experiments.ground_model_addressability.test_ground_model -v
python -m experiments.ground_model_addressability.run_benchmark --output pnf004.json
```

The [CI workflow](../../.github/workflows/ground-model-addressability.yml) pins
E-CPU `3b57adcc2baaaa7e56e4bab943946f4e87e95c65` and VGI
`093f11e458aff1c223d639ede413000619767ba6`, and runs Linux Python 3.11/3.13
and Windows Python 3.13. Each job runs the 14 new tests, PNF's 17 formation
regressions, and an independently launched forced-stop benchmark.

Next: introduce additional independently checked task families and compare the
ranker with residual sorting under measured cost. Then resolve the same model
address through the existing host catalogue/admission coordinator on another
receiver. Keep model identity, execution Ground, placement and authority
distinct; changing physical placement alone should not redefine the model.
