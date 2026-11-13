# One proof, two independently observed checks, one authenticated VGI receipt

**UNIFIED-KERNEL-001** — fixed-theorem experimental verification contract.

## Research question

Previous merged experiments established these separately:

1. A pinned Lean 4.15.0 runner elaborates `KernelTrial.identity`; another job repeats the source check and signs its reconstruction (PRs #137 and #141).
2. A GitHub/Sigstore-authenticated workflow checks a signed source result, its public key and exact VGI obligation (PRs #147–#148).
3. A second hosted job independently decodes a structurally serialized proof term and type and invokes Lean's kernel without importing the original theorem module (PR #150).

**Can VGI issue a single admitted receipt only when all three conditions refer to the exact same proof term, theorem type, environment and obligation?**

The answer requires treating each kind of evidence separately. A signed source/process recheck is not a kernel-term recheck, and a kernel-term recheck does not, by itself, authenticate the checker or establish GitHub authority.

## Trust/admission sequence

`lean-unified-kernel-receipt.yml` schedules four jobs on hosted runners:

1. `proof_runner`: runs pinned Lean 4.15.0, records structural theorem type/proof and VGI obligation, and attests the exact runner JSON on `main`.
2. `independent_checker`: separately re-elaborates the fixed source, checks its exact identity, signs a scoped recheck result with a fresh Ed25519 key, and attests the original checker observation, signed statement and public key.
3. `serialized_kernel_checker`: **without importing KernelTrial**, reconstructs the exact proof and theorem type from the original runner JSON. It calls `Lean.Kernel.check` and `Lean.Kernel.isDefEq`; it must reject three mutated cases. It attests the exact kernel report.
4. `vgi_unified_admission`: only runs for a trusted `main` push, never on a PR or manual dispatch. It verifies all five attested subjects using a patched GitHub CLI and the GitHub/Sigstore trust root. It checks the source signature, compares both evidence paths against the same scope-sensitive obligation, verifies kernel checker source identity, all controls and exact input hashes, and **then** constructs a new VGI `VerifiedKernelReceipt` with a digest committing to both reports and their attested provenance. It attests this final decision.

A missing or swapped report, mismatched obligation or theorem type, changed source hash, a different run/commit, modified proof bytes, invalid Ed25519 key, absent/forged negative controls, or an untrusted artifact fails closed. No output receipt may be admitted on PR CI, where the signature authority cannot be established via the main-only attestation policy.

The five trusted subject types are not interchangeable: `runner`, `checker`, `signed`, `public_key`, and `serialized_kernel`. Each is verified against its own exact digest, not merely a JSON `accepted` field.

## Checker authority and exact identity

The admission policy pins:

- repository `Kier73/In-Formation-Space` and GitHub repository ID `1454466415`;
- exact workflow certificate SAN `https://github.com/Kier73/In-Formation-Space/.github/workflows/lean-unified-kernel-receipt.yml@refs/heads/main`;
- exact `refs/heads/main` source ref and the `GITHUB_SHA` commit;
- GitHub-hosted runners only, and SLSA v1 provenance predicate;
- GitHub CLI **>=2.102.0** (patches for signer-workflow and source-ref verification bypasses);
- source and kernel checker report host/run identifiers from the same scheduled workflow;
- SHA-256 of the original serialized proof, theorem type, VGI obligation and environment commitment;
- deterministic input bytes of the valid proof and all three negative controls;
- direct invocation of Lean kernel checking on the decoded term under Lean 4.15.0.

The authority does not come from a public key embedded in a checker artifact. The verifier first authenticates that key's **bytes and workflow origin** using GitHub/Sigstore. Only afterward may its Ed25519 signature validate the scoped source recheck.

## Type-level separation in the adapter

`unified_kernel_receipt.py` separates three frozen dataclass contracts:

- `ExactObligationBinding`: immutable obligation, proof-term, theorem-type and environment fingerprints, plus original runner digest;
- `AttestedSourceRecheck`: the signed source-recheck binding;
- `SerializedKernelAcceptance`: the separately verified reconstructed-proof kernel report, with positive/negative controls, source-code digest and workflow run.

Neither evidence type independently creates the new unified receipt. The adapter issues `VerifiedKernelReceipt` only after checking that both typed bindings are equal, both original reports and the key pass attestation verification, and all source-signature/kernel control checks succeed. This creates a local in-process VGI `ProofGround` with `kernel_accepted` for one exact obligation.

**The receipt is not a transferable self-authenticating signature by itself.** A remote VGI importer must verify the final GitHub-attested receipt and its upstream evidence chain and enforce its own authorized-issuer policy. An arbitrary caller providing a Python `VerifiedKernelReceipt` object to VGI is not thereby authenticated.

## What this does *not* establish

- Independent physical or administrative host fault domains, or implementation-diverse kernel checking (both jobs use the same Lean kernel).
- A general deserializer for arbitrary Lean proofs or a complete transitive environment/option fingerprint. The tested environment is a fixed-source/import commitment.
- Authenticity of the source workflow's code beyond the pinned commit/provenance; the experiment assumes that permitted `main` workflow modifications are reviewed and trustworthy.
- A theorem-equivalence relation; different proof terms can establish the same proposition while having different exact fingerprints.
- Independent validation of arbitrary external claims by VGI: this is one fixed proof in a restricted, typed admission profile.

## Reproduction

PR CI runs synthetic adversarial *policy tests*, using a **mock GitHub verifier**. These are not live Sigstore tests or Lean kernel evidence:

```bash
python -m unittest discover -s experiments/lean-kernel-independent-recheck -p "test_unified_kernel_receipt.py" -v
```

The actual four-job main-branch workflow performs independent Lean execution and live GitHub attestation verification. Inspect the `unified-vgi-kernel-receipt` artifact and its own GitHub attestation after a passing main run.

## Next frontier

Prove the safety of replaying these receipts across E-CPU hosts: an independently authenticated recipient must reconstruct the entire trust chain (not merely accept an in-memory VGI object), enforce expiration/revocation policy and avoid cross-run or cross-obligation replays. Beyond that, broaden the proof-term/environment serializer under explicit versioned canonicalization, rather than claiming semantic identity from source text alone.
