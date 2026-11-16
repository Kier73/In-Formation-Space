# USM-003 — Independent observation of a model operating E-CPU

**Research status:** executable cross-repository experiment; execution results
must be determined by the linked CI run, not inferred from this document.

## Question

Can an independent host reconstruct a separate process-model's sequence of
E-CPU observations, Ground-construction requests, receiver admissions and
state navigations, without importing the model, E-CPU or VGI implementations?

This builds on [E-CPU USM-001](https://github.com/Kier73/E-CPU/pull/138)
and [USM-002](https://github.com/Kier73/E-CPU/pull/139).

## Use the system on two independent runners

The workflow [model-native-operations.yml](../../.github/workflows/model-native-operations.yml)
uses two separately scheduled GitHub Actions jobs:

**Producer host:** Checks out the exact pinned E-CPU commit, trains the model
controller, runs four operating sessions, and publishes an evidence bundle.

- Two control sessions use a high-request model: one affine, one nonlinear.
  They require real service execution to establish a positive read and an
  E-CPU refusal. High confidence does **not** grant admission.
- Two further sessions use the actually trained controller. Its proposals or
  deferrals are not overridden. These measure learned operating behavior.
- Model inference runs in a *separate Python subprocess* on the producer.
  E-CPU's StructuralMemoryRegistry owns certification, admission, source
  observations and state navigation.

**Independent verifier host:** Checks out only In-Formation-Space. It does
not install the E-CPU package, and it receives only the producer's JSON
artifact across the job boundary. A standard-library Python implementation
reconstructs the operation chronology, validates the receiver's digest-linked
event chain, and independently computes the source value.

For the test fixture, source observations are defined by:

```text
affine(t)    = (7 + seed + 5*t) mod 97
nonlinear(t) = ((t+seed)^3 + 17*t^2 + 3) mod 97
```

The verifier regenerates all 40 source samples from each declared seed and
checks the observed-stream digest and the receiver's first 24 returned samples.
If navigation completes, it computes the expected result at logical time
`10^12 + 137` directly from the source formula and compares it with the
E-CPU receiver's read result. This is an independent implementation of the
specific source oracle: it cannot prove that an unrelated environmental
process obeys that law.

It additionally rejects replayed/misaligned sequence indices, inconsistent
session IDs, wrong phase transitions, changed operation digests, unadmitted
reads, model decisions inconsistent with their reported threshold, and
fabricated or rewritten target coordinates. A forged result must not pass
merely because all its JSON digests were recomputed.

## Run locally

From the In-Formation-Space root, to test the independent verifier without
E-CPU installed:

```bash
python -m unittest discover -s bridges/model-native-operations -p 'test_*.py' -v
```

To run the producer, additionally check out the pinned E-CPU source under
`ecpu/` and set `PYTHONPATH=ecpu`. The main CI workflow performs those
steps and retains both artifacts.

## Evidence classes and honest scope

- This is **real** E-CPU structural-memory activity, orchestrated by a
  subprocess model: it exercises the receiver's live certifier, admission
  gate, revision-pinned read and receipt production.
- This is **real independent host reconstruction** at the evidence artifact
  stage. The two GitHub runner jobs are distinct; the artifact is transferred
  by GitHub Actions. It does *not* establish a direct authenticated model-to-
  E-CPU network operation between the runners.
- Digest-linked records demonstrate *internal content integrity under the
  stated canonicalization*; they do **not** establish a cryptographic
  signature, attest the physical origin, or prove a source is truthful.
- The verifier independently checks the known fixture source and its query,
  but does not independently reimplement every E-CPU law-admission rule.
  Witness/Ground certification remains a separate verification claim.
- The high-request controller is deliberately not the trained controller.
  Both are reported to avoid confusing guaranteed execution with learned
  policy quality.
- This experiment treats the external formula as an independent fixture
  oracle. A future step is to use an authenticated physical sensor/compute
  host with VGI-admitted observational equivalence evidence.

## Next frontier

Move the model process to a separately authenticated E-CPU observer-host and
transfer only capability-bounded system calls over the existing mutual TLS
fabric. Preserve session-epoch fencing, receiver-owned authority, and
independent VGI reconstruction through process loss and rehoming. That would
advance from *model using E-CPU services* toward *model operating a
substrate-adaptive E-CPU environment* with independently testable continuity.
