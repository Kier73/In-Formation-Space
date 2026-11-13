# PNF-001: procedural neural formation from observed or generated blocks

Question: can the same construction system form a new neural architecture from
either explicit procedural coefficients or a bounded external-model observation,
while retaining a checkable relationship to its starting function?

This experiment connects **HFR observation -> parameter construction -> E-CPU
dependency execution -> coefficient and numerical verification**, with VGI
retaining the source graph's structural proof obligations. It produces explicit
standalone feed-forward blocks with changed hidden widths; it does not train a
language model or assert that a wider architecture improves model quality.

## Construction and evidence

For `f(x) = activation(x W + b) V + c`, duplicate selected hidden neurons,
copy their incoming columns and biases, and halve each duplicated outgoing row.
The two identical activation values then contribute the original outgoing sum.
The activation must be the same elementwise function in both blocks. This
implementation supports ReLU and GELU-tanh, with no intermediate normalization,
stochastic dropout, attention coupling, or other cross-neuron operation.

This is a new repository integration and an independent implementation of a
known [Net2Wider-style construction](https://arxiv.org/abs/1511.05641)
(Chen, Goodfellow and Shlens, 2015/2016), not a claim to invent widening.
No implementation code from that paper's accompanying projects is copied.

- **Procedural:** deterministic PCG64 dyadic parameter rules create 4 -> 16 -> 4
  blocks, widened to 4 -> 24 -> 4 and 4 -> 32 -> 4, for both activations.
- **Observed:** HFR reads the four tensors of GPT-2 layer 0's MLP, rechecks the
  pinned revision and header, then reads exactly **18,889,728 payload bytes**
  under a 20 MiB aggregate / 10 MiB per-tensor cap. The standalone block is
  widened from **768 -> 3,072 -> 768** to **768 -> 4,096 -> 768**.
- **Generated:** the child has new arrays, dimensions, typed tensor hashes,
  a parent-index map, and separate source/generated identities. The original
  HFR graph and its observed tensor catalog are never overwritten or relabeled
  as generated evidence.
- **Checked coefficient law:** a checker that does not call the constructor
  verifies every incoming column/bias, the activation, output bias, and exact
  dyadic split of every outgoing coefficient. Width can grow by at most two
  per source neuron per step. Binary32 values and their halves are exactly
  representable in binary64; loss of a smallest subnormal during binary32
  materialization is rejected. Checking each half avoids accepting a tiny
  unmatched contribution hidden by floating-point addition.
- **Measured:** two deterministic probes compare every source/generated output
  with `atol=rtol=1e-10` in float64 arithmetic over binary32 coefficients.
  A separately written Python-loop `math.fsum` oracle checks up to three selected
  output coordinates in both models. This is an independent implementation
  check, not a second machine or a reference Transformers execution.
- **Negative control:** a modified outgoing coefficient is rejected even after
  recomputing the generated-model digest. Hash agreement alone is insufficient.

The algebraic argument concerns real arithmetic with shared elementwise
activation semantics. It is not a kernel-checked theorem or a claim of bitwise
floating-point equality. Finite numerical comparisons are reported separately.

## Actual use of the three repositories

| Repository | Executed responsibility | Evidence scope |
| --- | --- | --- |
| In-Formation-Space | HFR bounded reader, graph adapter, procedural generator, independent checker, scalar oracle | Observed bytes, generated parameters and numerical agreement remain distinct |
| E-CPU | `ComputationNode` / `NavigableComputationDAG` schedule construction, source forward, generated forward and verification; commit results and restore checkpoint | Local dependency/commit/reconstruction semantics, not federated transport |
| E-CPU | `compile_neural_graph_dag` projects the original live GPT-2 topology | Source topology description only, not full-model execution |
| VGI | `build_neural_topology_proof_ground` independently validates original source graph and retains all 654 unresolved obligations | No generated-model admission or kernel acceptance is claimed |

Related source is **imported/reused**, not copied. CI pins:

- E-CPU: `3b57adcc2baaaa7e56e4bab943946f4e87e95c65`
- VGI: `093f11e458aff1c223d639ede413000619767ba6`
- IFS starting inspection: `8770581cab06470d060f95afb801ab5313ae0cbe`
- Public model: `openai-community/gpt2`, revision
  `607a30d783dfa663caf39e06633721c8d4cfcd7e`, declared license MIT.

Only `h.0.mlp.c_fc.weight`, `h.0.mlp.c_fc.bias`,
`h.0.mlp.c_proj.weight`, and `h.0.mlp.c_proj.bias` are allowlisted.
No model code, Transformers runtime, arbitrary pickle, or full checkpoint is
loaded. Raw source/generated parameters exist in memory during this experiment;
reports retain descriptions, hashes, certificates, probes, and results only.
The live report records the individual selected payload hashes and header hash.
HTTPS/revision/header checks do not constitute an independent publisher signature.

## Reproduction

From the repository root, with NumPy and jsonschema installed and the E-CPU
root plus VGI's `virtual_ground_interpreter` directory on `PYTHONPATH`:

```bash
python -m unittest experiments.procedural_neural_formation.test_formation -v
python -m experiments.procedural_neural_formation.run --output /tmp/pnf-procedural.json
python -m experiments.procedural_neural_formation.run --live --output /tmp/pnf-live.json
```

The [dedicated workflow](../../.github/workflows/procedural-neural-formation.yml)
tests Python 3.11/3.13, regresses HFR tests, runs four procedural cases, then runs
the live Hugging Face case only after those jobs pass. Network failure fails the
live job; it never substitutes generated coefficients for an observed model.
The parameter and oracle budgets are accounting guards, not measured peak-RAM
guarantees. The E-CPU checkpoint carries descriptions and receipts, not executable
tensor buffers, so restoring it alone does not restore model inference state.

## Next experiments

1. Encode a generated block as a portable realization with a generated-source
   graph contract, rather than forging the existing observation-only HFR fields.
2. Transport that realization through E-CPU to a separate receiver and recompute
   the coefficient certificate there against a pinned source identity.
3. Introduce intentional function changes under explicit task observations and
   compare trained/generated alternatives. Width preservation itself adds no
   evidence of better semantics or useful task performance.
4. Formally check the dyadic-split law in a proof kernel and bind that result to
   VGI's own generated-model obligations. The current source obligations stay
   unverified throughout.
