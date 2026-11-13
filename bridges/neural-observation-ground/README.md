# Executable neural Ground: first synthetic observation experiment

**Status:** experimental, numeric sandbox on an independently checked HFR-002 typed graph.

This experiment connects three existing systems without replacing their
definitions of evidence:

- **HFR-002** supplies the typed operator DAG, its observed tensor metadata,
  and its explicitly family-interpreted semantics.
- **VGI** supplies `build_neural_topology_proof_ground`, an AND/OR `ProofGround`
  of 654 unverified structural obligations for the pinned GPT-2 graph
  (or the corresponding obligation count for a smaller graph).
- **IFS ObservationPath** records the planned, dispatched, admitted,
  returned, interpreted, and determined/unresolved lifecycle of every local
  operator-level numerical measurement.

## What actually executes

The `ExecutableNeuralGround` class constructs synthetic tensor arrays with a
seeded deterministic PRNG and executes the seven canonical operator families:
embedding lookup, tensor addition, evaluation-mode dropout, layer normalization,
affine projection, GELU-tanh, and causal scaled-dot-product attention. The
interpreter follows **actual typed producer/consumer edges** of the imported
graph, not a hardcoded GPT-2 layer runner. It tests one operation at a time,
after all parent operations have produced concrete arrays.

A bounded two-block example is built with HFR's existing tiny test fixture:
30 operations and 67 edges. The configured runtime inputs, synthetic
parameters, and intermediate results produce actual local numerical arrays;
the receipt stores *typed hashes*, not those arrays or raw weights. The
entire sequence can be deterministically replayed from the same pinned graph,
seed, and runtime configuration.

The planner selects a ready operation by downstream fan-out and stable
operation ID; each observed success makes its children eligible. A mismatched
shape/dtype or non-finite output stops execution with an unresolved
observation, rather than promoting a failure into proof. This is a greedy,
measurement-gated execution policy, **not** an assertion that VGI's minimax
transition policy is now generalized to floating-point neural computation.

The result binds each operator to its exact
`ProofGround.obligation_keys["operation:<id>"]` identity. That obligation
**stays unverified**, even if the local measurement matches its declared
shape. No `VerifiedKernelReceipt` is fabricated.

## Evidence interpretation

- **Observed from source:** tensor names, shapes, dtypes, source revision,
  header provenance; never tensor payload values in the HFR-002 path.
- **Inferred/interpreted:** directed operator graph and expected numeric
  operator semantics, under the GPT-2 family adapter's contract.
- **Constructed:** synthetic parameter arrays and runtime input tokens.
- **Measured:** NumPy execution output descriptors on these synthetic arrays,
  ordered local ObservationPath receipts, and a final logit digest when all
  operator computations finish.
- **Reconstructable:** the local experiment from its graph, seed, runtime
  settings, and the retained step identities.
- **Not established:** numerical equivalence to GPT-2, recovered source
  parameters, externally authenticated sensor observations, independent
  numeric semantics, Lean/kernel acceptance, causal semantic understanding,
  or multi-host clock agreement.

This reference uses `authority_required=False` because all actors are local
test actors. Local admission and interpretation are not misrepresented as
federated receiver authority.

A receipt hash chain and deterministic replay detect accidental or
unsophisticated altered records. They do not authenticate actors or prevent
a hostile controller from replacing the whole experiment and its seed.

## Resource discipline

`max_elements` is an explicit fail-closed, conservative aggregate
element budget over synthetic parameter tensors, runtime graph inputs,
retained operator activations, and attention score/probability scratch space.
The preflight runs **before** materializing arrays. It is an element accounting
guard rather than an exact operating-system peak-memory measurement. Real GPT-2
would require much more memory; the pinned 160-tensor topology is admitted
into VGI as a `ProofGround` but numeric realization is refused by this
reference's budget. Real model weights are neither downloaded nor executed.

## Usage

With `numpy`, `jsonschema`, the local bridge modules, and VGI on
`PYTHONPATH`:

```python
from neural_graph_ir import compile_gpt2_topology
from test_neural_graph_ir import make_topology_nsd
from neural_execution_ground import ExecutableNeuralGround, verify_neural_observation_receipt

graph = compile_gpt2_topology(make_topology_nsd(layers=2))
ground = ExecutableNeuralGround(graph, seed=31, batch=1, sequence=3)
receipt = ground.run()
assert receipt["status"] == "complete"
assert receipt["observation_count"] == 30
assert receipt["vgi_proof_ground"]["kernel_accepted_obligations"] == 0
verify_neural_observation_receipt(graph, receipt)
```

Focused tests include causal-masking behavior, tied/untied output heads,
partial execution, mismatched numerical results, receipt tampering, and
pre-allocation budget refusal. CI pins VGI at
`a2a5eec0a778097819ace9a0db44f0b5b1594b4c`, executes the tiny fixture,
reconstructs the live HFR-002 graph, then checks that all 654 ProofGround
obligations remain unverified and unbudgeted GPT-2 numerical execution is
refused.

## Next experiment

Use the same typed observation format with a separately implemented numerical
oracle and a constrained, explicitly allowed slice of *observed* source
weights. Compare independent replays under identical typed inputs and record
mismatches. Only after those agreements should it be considered whether the
verified measurement can authorize a stronger Ground revision or inform
VGI's adaptive proof-search policies.
