# PNF-003: generated capsules through native E-CPU execution

PNF-003 connects PNF-002's authenticated capsule receiver to TCR-003's existing
`NativeCut`, operator contract, capability checks, and native replay. The
receiver reconstructs the generated block, divides it into four contiguous
hidden-neuron cuts, and executes their contributions through E-CPU's actual
`VirtualLayerRuntime` and Hypervisor. No replacement runtime is introduced.

## Admission and execution

1. The receiver's local configuration pins the capsule bytes, original model,
   and generated model. The PNF capsule verifier checks all tensor hashes,
   exact widening coefficient conservation, and its declared scalar probes.
2. Only after successful verification does the receiver call TCR preparation
   on the **generated** block. The TCR manifest's `source_digest` is therefore
   the generated model digest; the original parent remains explicit in the
   manifest's provenance. Shards are constructed locally, not accepted from
   the sender as authority.
3. TCR owns two fixed numerical probes, four local receiver runtimes, operator
   contracts, capability admission, and pure partial execution. The sender's
   chunk/completion protocol has no capability field. A locally configured
   denial must yield four `deny` decisions and zero native handler calls.
4. Each authorized operation is submitted twice with the same native event.
   The second submission must replay the same fingerprint, request identity,
   payload and receipt, with no second handler call.
5. Existing TCR receipt validation and E-CPU DAG aggregation check all output
   coordinates against the generated dense reference, selected coordinates
   against its independent scalar oracle, and checkpoint reconstruction.
   PNF additionally checks the reconstructed output against the original
   parent: all dense coordinates plus selected scalar coordinates.

`status: verified` describes capsule validity. Nested native status is either
`executed` or `denied`. Native denial does not prohibit the verification and
reference calculations necessary to admit this experiment's capsule.

The four runtimes have distinct receiver/system identities. Their initial
Ground **content** can be identical because `VirtualGroundRef` describes seed
state, coordinate and frontier, rather than receiver identity. Reports count
both runtimes and distinct Ground content hashes rather than assuming these
counts are equal.

## Verification and reproduction

The new tests cover both activations, exact replay, local capability denial,
wrong external identities, rehashed invalid widening evidence, a forged and
rehashed numerical contribution, changed replay receipts, sender attempts to
add compute authority, and bounded work. Two additional tests use actual
separate-process mTLS sockets for native execution and denial. CI also runs
the existing TCR native-admission tests and the PNF-001/002 workflows.

With the pinned E-CPU checkout on `PYTHONPATH`:

```bash
python -m unittest experiments.procedural_neural_formation.test_native_execution -v
python -m experiments.procedural_neural_formation.run_native \
  --output pnf-native-procedural.json
```

Add `--live` with VGI on `PYTHONPATH` and `numpy jsonschema` installed to read
the pinned GPT-2 layer-0 tensors, widen 3,072 hidden neurons to 4,096, transmit
the resulting capsule and execute its cuts. Hugging Face failure is an error,
not a procedural fallback. `--direct` is explicitly local execution without
sockets. Saved exports require `--capsule`, `--policy`, `--expected-source`
and `--expected-generated` so a sidecar cannot supply its own trusted identity.

The [workflow](../../.github/workflows/native-neural-formation.yml) pins E-CPU
`3b57adcc2baaaa7e56e4bab943946f4e87e95c65` and VGI
`093f11e458aff1c223d639ede413000619767ba6`. Reports preserve model identities,
native decisions and replay fingerprints, numeric errors, DAG snapshots and
transport evidence. No ephemeral private keys or shard files are retained.

## Scope and next experiment

### Local evidence

The [Windows native report](results/pnf003-local-native.json) records two
procedural cases and the retained PNF-002 observed capsule (44,107,195 bytes).
All three executed four native handlers and replayed their results without
recomputation. The observed case checked all 1,536 outputs against the parent,
with maximum absolute dense error `1.4210854715202004e-14` and selected scalar
error `1.7763568394002505e-15`. The denial control called zero native handlers.
This was direct execution without sockets or a fresh Hugging Face read. Local
Python 3.13/NumPy 2.2.5 and source checkouts were used; pinned-runtime transport
and fresh-source evidence are delegated to the dedicated CI run.

The local PNF-001, capsule and new native suites passed **42 tests**. Socket
tests run on CI because the workstation sandbox denies loopback binding.

The sender and receiver are separate processes connected through real E-CPU
ReliableChannel/mTLS loopback transport. All four native cuts run inside that
one receiver process. This is not four network workers, cross-machine
attestation, generic Transit worker admission, or durable crash recovery.
Replay is in-memory within a live runtime. Receiver temporary shard files
are locally provisioned after transfer; no sender parameter file is shared.

Arithmetic is float64 evaluation of admitted float32 coefficients. Comparisons
use TCR's `atol=1e-9, rtol=1e-10`; they do not establish bitwise equivalence,
training quality, or a speedup. VGI's 654 original topology obligations remain
unverified and no kernel proof is claimed. Capsule provenance is bound to
bytes but is not independently re-observed by the receiver.

The next experiment can persist the admitted capsule and native execution
identity across a killed receiver, then reconstruct and replay under freshly
checked receiver authority. Existing SNC durable admission work is a useful
foundation; its recovery semantics must be demonstrated for these parameter
capsules before any durable execution claim.
