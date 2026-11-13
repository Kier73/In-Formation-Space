# PROOF-TRANSFER-001 — independently verified proof receipt transfer

## Question

After `UNIFIED-KERNEL-001` creates an attested `VerifiedKernelReceipt`, can a *different receiving process/host* reconstruct and admit it without trusting the sending process, relying on receipt flags, or accepting a replay?

The receiver must observe three different realities without conflation:

- **Mathematical claim:** the serialized Lean 4.15.0 term was independently reconstructed and checked by Lean's kernel for the exact theorem type.
- **Issuer authority:** the specific workflow, source commit and report bytes were authenticated through GitHub's Sigstore attestations, then the source/term checker Ed25519 signature was verified against the independently attested public-key bytes.
- **Receiver admission:** a *recipient-owned, time-bounded intent* admits exactly one expected VGI obligation and a durable SQLite transaction prevents replay in its own scope.

## Implementation

`proof_receipt_receiver.py` takes **six different transferred artifacts** from the completed unified issuer workflow: originating runner observation, independent source checker observation, Ed25519 signed recheck, checker public key, independently kernel-checked serialized term report, and final unified VGI receipt.

The receiver independently authenticates **all six exact file byte digests** with a patched GitHub CLI (>=2.102.0). Attestation policy fixes repository `Kier73/In-Formation-Space`, GitHub repository ID `1454466415`, main-branch workflow certificate identity, `refs/heads/main`, the recipient-approved exact source commit, SLSA v1 provenance predicate, and GitHub-hosted runner requirement.

Only then does the receiver reconstruct the existing `UNIFIED-KERNEL-001` decision using the original five inputs and its installed VGI/Lean-checker contract. It independently rechecks the original source signature, validates all serialized kernel controls and exact inputs, and compares the complete reconstructed unified receipt **with the received receipt**. A typed VGI `kernel_accepted` observation is not trusted merely because a JSON document says so.

## Recipient-owned intention, without sender input

`recipient_intent.py` is run on the receiver's own checkout. With locally pinned Lean 4.15.0 it re-elaborates the fixed `KernelTrial.identity` theorem and independently derives the required scope-sensitive VGI obligation fingerprint. It does **not** read any file transferred from the sender.

The local JSON recipient policy also pins an expected issuer commit, run ID, run attempt, unique recipient scope, and a short local time interval. It supports locally provisioned `revoked_receipt_refs` and `revoked_source_shas` deny-lists. These are **recipient authorizations**, not values accepted from the incoming receipt.

A different host can supply its own trusted policy file without running the fixture generator, but MUST NOT derive the expected obligation or authorized issuance run from received artifacts.

The receiver makes no claim about a distributed time authority: expiry is enforced against its own local clock. Revocation is local, not synchronized through a global registry.

## Atomic replay admission

Only after full cryptographic provenance checks, signature validation, obligation matching and independent receipt reconstruction does the recipient issue a SQLite `BEGIN IMMEDIATE` insertion. The persistent table has two unique constraints: `(recipient_scope, receipt_ref)` and `(recipient_scope, obligation_id, source_sha, run_id, run_attempt)`. With full SQLite synchronous durability, only one process can admit a transfer for the same receipt or the same logical obligation/run in that recipient scope.

The workflow's `receipt_receiver` job demonstrates a new hosted recipient process receiving the prior jobs' transferred artifacts, independently deriving its goal, accepting the genuine receipt, and starting another fresh Python process using **the same SQLite file**. The second process must explicitly reject the replay; failing for any other reason does **not** satisfy this gate.

The SQLite file is retained as a workflow artifact, along with the receiver decision. It is not automatically mounted into later unrelated workflow runs; durable replay enforcement across those runs requires a genuinely persistent recipient-owned volume or database. Nor does this local uniqueness contract prevent another recipient with a different ledger from accepting the same otherwise authorized proof.

## What this establishes, and what it does not

This experiment establishes independent *verification and admission* of a transferred, fixed-theorem unified proof receipt under an explicit recipient policy. It is a reusable boundary between artifact transportation and VGI kernel admission.

It **does not** establish transport-layer confidentiality, E-CPU ReliableChannel interoperability, physically separate hosts, implementation-diverse Lean kernels, a general proof-term/environment serializer, coordinated global replay detection, a secure hardware trust root, or distributed consensus. Separately scheduled GitHub runners provide independent processes; GitHub's workflow and reviewed `main` branch remain trusted authorities. The receiver's installed code and local intent must be trusted independently of any sender data.

The provenance policy pins an exact workflow identity and source commit, not an independently demonstrated job-specific hardware identity.

## Tests and inspection

PR CI runs 16 recipient contract tests with a **mock GitHub CLI**. They exercise cross-run/source/obligation substitution, forged source signature, missing kernel proof, wrong final receipt reference, unpatched verifier, untrusted attestation, expired/revoked local authorization, noncanonical transfer bytes, symlinked artifacts, SQLite uniqueness and two concurrent insertions. Passing these tests does not authenticate GitHub.

On `main`, the five-job [unified workflow](../../.github/workflows/lean-unified-kernel-receipt.yml) performs the real hosted checks, live GitHub/Sigstore verification and the SQLite second-process replay test. Only a successful post-merge run confirms the full milestone.

## Next frontier

Carry the same six-artifact proof package over **authenticated E-CPU Transit / ReliableChannel** instead of GitHub Actions artifacts. Keep issuance proof authority separate from message transport identity, and provision the recipient policy and durable replay ledger at the destination independently. Cross-host replay prevention would then require a shared trusted ledger or coordinated scoped admission, not merely local SQLite files.
