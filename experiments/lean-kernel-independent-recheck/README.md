# Lean kernel observations independently rechecked

**Status:** isolated proof-runner experiment (does not replace the signed completion-receipt or SQLite-authority workflows).

## Research question

The existing [signed completion receipt](../proof-runner-completion-receipts/README.md) and [independent SQLite-authority reconstruction](../proof-runner-independent-reconstruction/README.md) can verify which authorized worker signed an exact proof-action result. They cannot establish that Lean actually checked the claimed theorem. This experiment tests the next smaller claim: can **two separately scheduled GitHub-hosted jobs each invoke the same pinned Lean compiler** on an identical fixed proof, preserve their direct observations, and reject common false-positive examples?

The experiment intentionally uses one closed and auditable proof obligation:

```lean
theorem KernelTrial.identity (n : Nat) : n = n := by rfl
```

The fixed Lean 4 version is `leanprover/lean4:v4.15.0`, selected to match the VGI proof bridge's example environment. No Mathlib dependency, model weights, external theorem search, or arbitrary user-submitted Lean program is involved.

## What runs

The `proof_runner` GitHub job checks out the repository, installs the pinned Lean toolchain through `leanprover/lean-action`, and runs the four fixtures:

1. `KernelTrial.lean`: definitional equality via `rfl`. The process must exit successfully and Lean's `#print axioms KernelTrial.identity` must report no axioms for the **exact named theorem**.
2. `KernelTrialSorry.lean`: superficially elaborated proof with `sorry`. It must **not** count as accepted, even if Lean exits successfully.
3. `KernelTrialInvalid.lean`: false equality with `rfl`. A nonzero process exit must not count as acceptance.
4. `KernelTrialAxiom.lean`: theorem derived from a custom axiom. A successful Lean process exit must **not** count as axiom-free acceptance.

The runner saves source SHA-256, process exit code, version, toolchain, stdout/stderr digests, exact theorem label, and the source-limited acceptance observation. All fields are committed by a canonical SHA-256 document digest. The workflow preserves this record as a GitHub artifact.

The separate `independent_checker` job checks out the same repository commit, downloads that artifact, validates every runner document digest and pinned source SHA-256, checks run and job identity correlation, independently invokes Lean on all four checked-in sources, checks the four outcomes, then emits its own report, including the two sets of case-observation digests. It does **not** treat the runner's claimed acceptance as authoritative. The final report is checked against `independent-report.schema.json` and preserved as a workflow artifact. On `main`, GitHub also attests the exact report bytes.

## What a green run establishes

For this exact bounded fixture, the separate checker directly observed the pinned Lean process accept an axiom-free proof of `KernelTrial.identity`, while it independently rejected the `sorry`, false-statement, and custom-axiom controls. It established source, toolchain, Git SHA, run ID, and job-role correlation and recorded separate process-output digests.

The two GitHub Actions jobs are separately scheduled; that does not establish independent physical machines, toolchain implementation diversity, or separate administrative fault domains. Their records travel through GitHub Actions artifacts rather than E-CPU ReliableChannel.

**Crucial distinction:** `#print axioms` is a Lean-produced observation of a named theorem's dependencies, coupled with successful Lean elaboration/checking. The script's text check is an external observer of that command; it is not itself a kernel verifier. This experiment trusts the pinned Lean executable. It does not use a second independent theorem checker.

## What remains in development

This does **not** yet provide a VGI `VerifiedKernelReceipt`. It does not extract and canonically fingerprint Lean's elaborated `Expr` or establish a signed checker receipt that binds that term, obligation and environment with a verifiable authority identity. The report explicitly records `vgi_verified_kernel_receipt_issued=false` and `proof_term_fingerprint_observed=false`. A separate trusted-checker interface and authenticated receipt are needed before importing a `kernel_accepted` status into VGI.

It also does not prove arbitrary tactics, generalized theorem correctness beyond the checked fixture, secure arbitrary-code execution, distributed proof worker authorization, or formal verification of E-CPU.

## CI and reproduction

GitHub Actions: [Lean independent kernel recheck workflow](../../.github/workflows/lean-kernel-independent-recheck.yml).

With a working Lean 4 installation (the local `lean-toolchain` is pinned) and Python 3.11+:

```sh
cd experiments/lean-kernel-independent-recheck
lake build
python -m unittest -v test_kernel_evidence
python kernel_evidence.py produce --output ./runner-report.json
python kernel_evidence.py verify --runner-report ./runner-report.json --output ./checker-report.json
```

The last command is a **local same-host diagnostic**, not a two-host observation. Only the two-job CI workflow tests separate hosted executions. The Python unit tests also mock Lean to test parser, digest and identity failure paths; their passing is not evidence that Lean actually ran.
