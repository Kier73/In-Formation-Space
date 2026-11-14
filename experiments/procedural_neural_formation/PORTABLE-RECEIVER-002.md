# PNF-002: portable generated models and a separate E-CPU receiver

**Verified milestone:** the [first live CI run](results/ci-run-43530863142.md)
transferred and checked the observed/generated pair successfully. A subsequent
Windows reconstruction of its exact downloaded capsule is also retained.

PNF-001 checked widening inside one process and retained hashes. PNF-002 exports
the actual binary32 parameters, sends them through E-CPU ReliableChannel over
mutual TLS, and reconstructs and checks both source and generated models in a
fresh interpreter. The receiver never calls `widen` or `procedural_block`.

## A restricted, honest generated-model contract

The portable `.pnf` object has this wire layout:

1. Eight-byte magic `IFSPNF02` and little-endian unsigned 32-bit header length.
2. Canonical UTF-8 JSON, at most 256 KiB.
3. Source then generated arrays, each in the fixed order `up_weight`, `up_bias`,
   `down_weight`, `down_bias`; little-endian binary32 in row-major order.

The total capsule is at most 64 MiB. The header includes the two content-addressed
block descriptions, their activation identifiers, the widening certificate,
source provenance, explicit generated origin, and bounded probe inputs. Shapes
derive the exact payload spans; no caller-controlled strides, paths, compression,
pickle or executable source is interpreted. Duplicate JSON keys, unknown fields,
noncanonical encoding, wrong sizes, nonfinite parameters, malformed dimensions,
trailing bytes and mismatched payload hashes are refused.

This is a fixed **affine -> shared elementwise activation -> affine** model
language, with ReLU and GELU-tanh. It does not pretend to be a newly observed
Hugging Face graph. A richer generated graph language remains future work.
The original HFR typed graph stays unchanged. In the live sender, E-CPU still
projects its 150 operations and VGI retains all 654 unresolved source obligations.

The receiver is configured separately with the expected capsule hash/size and
source/generated model digests. These values cannot be learned from the capsule
being admitted. The experiment coordinator supplies this policy through a small
local file containing no parameters; deployments must establish their own trusted
policy authority. The exported `.policy.json` sidecar is a reproducibility aid,
not self-authenticating authority. Replacing both a model and its accepted policy
can change which model is accepted.

## Execution and receipt

The harness creates an ephemeral test CA and two SAN-separated identities. Each
side verifies the certificate chain, expected DNS identity and exact peer
certificate fingerprint. Request IDs, receiver PID, implementation digest and
capsule identity are bound to the response. The implementation digest covers the
capsule decoder, coefficient checker/scalar oracle, block definitions and service.
It is an implementation identity check, not hardware or remote-code attestation.

E-CPU carries 64 KiB parameter chunks in bounded 256 KiB frames. Its real
ReliableChannel sequences messages and acknowledges each chunk after validated
in-memory staging. A final verification request succeeds only after all bytes
have arrived. ACK therefore means staged bytes, **not** semantic acceptance or
durable storage. The separate response distinguishes `verified` from `rejected`.

The receiver:

- Checks the externally supplied identities and all tensor hashes before array
  materialization; independently reconstructs explicit source/generated arrays.
- Checks the complete dyadic coefficient law using the PNF-001 checker, including
  all incoming weights/biases, outgoing halves, output biases and activation.
- Executes two probes with the separately written scalar `math.fsum` oracle,
  comparing three selected output coordinates (all outputs for smaller models).
  The report retains the actual source/generated outputs and numerical error.
- Returns the correlated result through the authenticated E-CPU response channel.

This is a second process using a separately written numerical evaluator, but it
shares the PNF coefficient-checking implementation and the physical host. It does
not establish independent hardware failure domains, a malicious-host guarantee,
durable restart/retry recovery, offline signed receipt authenticity, or external
proof-kernel acceptance. The receiver verifies the content-bound relationship;
it does not independently re-observe Hugging Face or authenticate its publisher.

The workflow additionally sends the exported capsule through GitHub artifact
storage to a separately scheduled Windows/Python 3.13 replay job. That job pins
the expected source and generated model identities in its checked-in workflow,
not from the producer's sidecar, and reconstructs the arrays again. This is
cross-runner artifact replay; the actual E-CPU mTLS transfer remains the earlier
Linux process-to-process session. These two evidence scopes are kept separate.

## Two concrete paths

| Starting coefficients | Source block | Generated block | External payload read |
| --- | --- | --- | --- |
| Procedural ReLU | 8 -> 1,024 -> 8 | 8 -> 2,048 -> 8 | 0 bytes |
| Procedural GELU-tanh | 8 -> 1,024 -> 8 | 8 -> 2,048 -> 8 | 0 bytes |
| Pinned GPT-2 MLP, layer 0 | 768 -> 3,072 -> 768 | 768 -> 4,096 -> 768 | 18,889,728 bytes |

The observed/generated live pair contains 44,075,008 parameter bytes, plus the
small capsule header. Both source and generated coefficients cross the stream;
the receiver reads no parameter file. Tests also reject a wrong external source
pin, a rehashed false coefficient certificate, and an incorrect TLS receiver pin.

Unlike PNF-001's hashes-only reports, this stage can retain a reusable parameter
capsule. The live CI artifact includes selected public GPT-2 coefficients and
their generated realization, with upstream repository/revision and declared MIT
license in the header. It contains no private keys or executable upstream model
code. The raw source is neither a full GPT-2 checkpoint nor a newly trained model.

## Architecture and activation: the motivating distinction

Architecture can constrain admissible dimensions and activation contracts, and
a declared rule can procedurally choose parameters. Architecture alone generally
does not identify learned parameters or useful task behavior. A regression test
constructs two blocks with identical dimensions and activation, different seeds,
different parameter identities, and different outputs on the same probe.

Accordingly the capsule binds **architecture + activation + explicit parameters
+ construction relationship**, instead of inferring one from the other. A useful
next research question is whether task observations can select among several
compatible activation/parameter rules while preserving unknown outcomes when
the evidence does not distinguish them.

## Reproduction and provenance

Import/reuse E-CPU `3b57adcc2baaaa7e56e4bab943946f4e87e95c65` and VGI
`093f11e458aff1c223d639ede413000619767ba6`; use PNF-001 from IFS
`95cbb60b1441465669fdd5f9524b424c29701466`. No related repository source is copied.
The mTLS test design follows the existing SRH-007 verifier-peer pattern.
The public GPT-2 source pin remains
`607a30d783dfa663caf39e06633721c8d4cfcd7e`.

With NumPy, jsonschema and OpenSSL installed, and the E-CPU root plus VGI's
`virtual_ground_interpreter` directory on `PYTHONPATH`, run from the IFS root:

```bash
python -m unittest experiments.procedural_neural_formation.test_capsule -v
python -m unittest experiments.procedural_neural_formation.test_transfer -v
python -m experiments.procedural_neural_formation.run_transfer \
  --output /tmp/pnf-transfer.json --capsule-output /tmp/procedural.pnf
python -m experiments.procedural_neural_formation.run_transfer --live \
  --output /tmp/pnf-live-transfer.json --capsule-output /tmp/observed.pnf
```

`unpack_pair` restores arrays; `verify_capsule` checks a retained object with an
externally accepted policy. `transfer_pair` starts a fresh receiver and performs
the actual mTLS handoff. The [workflow](../../.github/workflows/portable-neural-formation.yml)
tests Python 3.11/3.13 and then exercises the live observed-source path.

Local Windows verification: all 16 capsule/assembly tests passed. The four actual
socket tests reached receiver startup but failed at connection with `WinError
10013` (sandbox permissions); they were not skipped or represented as passed.
The Linux CI run is required to establish actual transfer success.

After the initial successful CI, the actual 44,107,195-byte capsule was downloaded
and checked on the local Windows environment (Python 3.13, NumPy 2.2.5). Its SHA-256
matched the CI log and its archive matched GitHub's artifact digest. Full
coefficient verification and the source/generated scalar comparison passed.
This replay did not require or establish a local socket connection. The later
export-policy test adds an explicit negative control for independently configured
model identities.

## Relationship to subsequent repository work

Current source examined: IFS `005af23e9adb180ff86485a9c9434815590405df`.

- [SNC-001](../semantic_neural_compilation/README.md) already constructs exact
  rational ReLU parameters from a specified piecewise-affine behavior.
  [SNC-003](../semantic_neural_compilation/SNC-003.md) adds durable semantic
  hosting and source-policy checks. This is a concrete route from **behavioral
  description to activation structure and parameters**, stronger than trying to
  infer a unique model from architecture alone, within its one-input function
  language. PNF retains the complementary observed/binary32 realization path.
- [SNC-004B](../semantic_neural_compilation/SNC-004B.md) has a dedicated overlay
  protocol and third-host audit, with separate federation prerequisites. Its
  protocol is useful future integration material; PNF does not claim its
  cross-host route has been executed here.
- [TCR-003 native admission](../tensor_cut_realization/native_admission.py)
  now registers resident tensor-cut handlers through E-CPU's real
  `VirtualLayerRuntime`, `HeadlessOS`, and receiver-local Hypervisor capability.
  The next PNF integration should provision a verified generated realization,
  then let that receiver authority admit observation requests. Capsule delivery
  or successful coefficient verification alone must not grant execution rights.

## Next experiment

Move the receiver to a separately hosted machine with an independently provisioned
policy and authenticated identity. Add durable staging and a receipt outbox so
loss after the final chunk or after verification can be recovered without
silently treating a transport ACK as accepted model execution.
Compose with SNC's existing persistence and TCR's native admission where their
contracts fit, rather than inventing another authority or hosting abstraction.
