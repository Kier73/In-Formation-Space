# Lean proof-term identity → VGI authenticated-admission experiment

**Status:** Experimental, deliberately bounded to the fixed `KernelTrial.identity` theorem with Lean 4.15.0. This is additive to the existing independent Lean recheck, SQLite authority, and proof-action receipt workflows.

## Research question

Can we observe a Lean elaborated declaration as a structural object, independently reproduce *that same object*, and admit a VGI `VerifiedKernelReceipt` only after checking a signature against an explicitly supplied trusted checker key? The prior independent Lean experiment checked source/process behavior and negative controls, but did not extract an elaborated proof term.

## What is implemented

- `TermIdentity.lean` imports the compiled fixed theorem, reads `ConstantInfo.type` and `ConstantInfo.value?`, and emits versioned structural JSON for the theorem type and proof. The encoder records de Bruijn variables, constant/name/universe structures, applications, lambda/forall/let forms, literals, projections and binder annotations; binder *names* are omitted to retain alpha-invariant identity. It fails closed on unresolved metavariables, free variables and metadata.
- `term_receipt.py produce` runs the pinned Lean build/export and the existing four-fixture Lean controls, then binds the structural type, proof term, restricted environment/import-source commitment, and VGI scope-sensitive obligation to SHA-256 digests.
- A separately scheduled checker reruns the same Lean extraction, requires exact structural identity and obligation/environment equality, and signs its recheck statement with an ephemeral Ed25519 **fixture** key.
- A third GitHub job verifies the signature under a caller-supplied public key, checks exact runner/source/type/proof/environment/obligation correlation and the checker policy, then constructs an actual VGI `VerifiedKernelReceipt`. It demonstrates the VGI `kernel_accepted` status only after that adapter succeeds.
- Offline adversarial tests reject changed terms, theorem types, VGI environments, changed runner records, bad signatures, wrong checker keys, wrong checker IDs, mismatched execution roles/runs and duplicate JSON keys.

## Trust and semantic distinctions

This has **three independent identity checks**: source-bound VGI obligation, elaborated structural proof representation, and restricted environment/import commitment. The Lean compilation checks the source theorem, and the prior independently checked axiom/dependency controls are reused. This proof-term exporter **does not perform a fresh stand-alone kernel check of arbitrary submitted serialized terms**; it observes an elaborated theorem compiled by pinned Lean.

A structural term digest is **not** a semantic equivalence oracle: different proof terms can establish the same theorem. This encoder is versioned for a fixed Lean release and must not be called a general canonical cross-version representation. The environment commitment hashes known fixture source/import configurations but **not** the complete transitive semantic closure or compiled toolchain supply chain.

**Important authorization caveat:** The workflow's public verification key originates in the checker artifact itself. The experiment proves a real Ed25519 signature check **relative to that supplied key** but does not independently establish the key owner's authority. On `main`, GitHub artifact attestation records provenance for the signed evidence and public key; this experiment does not yet verify that attestation before the final VGI admission. A production host must pin or authenticate an independently provisioned checker key, plus enforce identity/version/revocation policy, before treating the returned receipt as an authorized theorem acceptance. The CLI does not use a receipt's self-declared key as authority; it takes a separate `--trusted-public` input.

Each GitHub job is separately scheduled, not implementation-diverse or a distinct demonstrated physical fault domain. This experiment does **not** assert distributed consensus, physical host independence, arbitrary Lean program safety, generalized kernel correctness, theorem-equivalence, or authenticated E-CPU transport.

## Run

The CI workflow is [lean-term-receipt.yml](../../.github/workflows/lean-term-receipt.yml). It checks out VGI at pinned revision `ac13c1bbd92dfd09f17de51adef7adb2d2088bf6` and uses Python 3.11 / `cryptography>=42,<47`.

With Lean 4.15 and the pinned VGI implementation on `PYTHONPATH`, from the repository root:

```sh
python -m unittest discover -s experiments/lean-kernel-independent-recheck -p 'test_term_receipt.py' -v
python experiments/lean-kernel-independent-recheck/term_receipt.py produce --output term-observation.json
```

The `recheck` command intentionally issues signed results only in the actual GitHub `independent_checker` job (rather than allowing a same-process local command to be presented as independent execution). Offline unit tests exercise the signature and admission contracts without representing a local execution as independent host evidence.

## Next experiment

Replace the fixture-generated key with an externally authenticated checker identity, verify the GitHub attestation and exact signer/subject policy at admission, and build a separate kernel-checking interface for an exact serialized proof term. Only then generalize to arbitrary VGI obligations or deploy over E-CPU ReliableChannel.
