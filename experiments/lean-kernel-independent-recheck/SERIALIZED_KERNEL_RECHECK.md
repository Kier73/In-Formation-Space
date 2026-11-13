# Independent serialized Lean kernel recheck

**Status:** distinct fixed-theorem experiment. Complements the GitHub-authority-gated VGI receipt workflow; does not replace it.

## Question

Can a separately scheduled checker receive only the runner's *structured elaborated Lean Expr*, reconstruct a closed proof term and its expected theorem type, and call Lean's kernel on that term **without elaborating the original theorem source**?

The prior Lean workflows established separately scheduled execution of the same pinned Lean source, a structural term fingerprint, and verified GitHub workflow provenance of a checker-signed report. None had yet kernel-checked a newly reconstructed proof term from serialized bytes.

## Implementation

- `TermIdentity.lean` from PR #141 serializes the elaborated type and proof of `KernelTrial.identity` using a versioned, fail-closed structural Expr representation.
- The original runner runs Lean 4.15.0 and records the exact VGI obligation, environment/source commitment, and structural type/proof fingerprints.
- The separate `serialized_kernel_checker` hosted job receives that exact runner observation. It checks the runner document's integrity and VGI binding; it **does not import `KernelTrial`** when evaluating the received term.
- `SerializedKernelCheck.lean` imports `Lean` alone, decodes Names, universe Levels, and supported Expr constructors into fresh Lean objects, then calls **`Lean.Kernel.check`** on the decoded proof, followed by **`Lean.Kernel.isDefEq`** against the separately decoded claimed theorem type.
- The same job runs explicit adversarial controls: an unbound de Bruijn variable, a valid proof presented against a wrong theorem type, and an unsupported metavariable-like constructor. Every control must fail.
- The checker reports exact serialized input byte digests, process return codes, stdout/stderr hashes, structural fingerprints, source checker digest, the runner observation digest, and a VGI obligation fingerprint. On `main`, GitHub attests the exact independent report.

## Why this is a new distinction

A successful Lean compiler run and `#print axioms` observation is not the same claim as directly kernel-checking a proof reconstructed from external serialization. This experiment establishes the latter for **one fixed theorem** under a pinned Lean environment. It does not reinterpret `by rfl` or run a tactic as its acceptance criterion. The checker constructs a new term representation from the prior observation and calls the Lean kernel to check it.

It remains **implementation-identical rechecking**: both hosts trust Lean 4.15.0 and the same kernel implementation. It does not prove the two GitHub jobs occupy separate physical or administrative fault domains. The Lean environment still comes from the installed imports, and the source/import fingerprint is not a fully recursive semantic closure.

This standalone serialized checker deliberately **does not issue a VGI `VerifiedKernelReceipt`** or authenticate its checker authority. The independently attested workflow from PRs #147/#148 provides a separate provenance gate; bridging these observations into a single trusted receipt would need an explicitly typed checker-policy contract, not an implicit promotion of a signed result.

No general-purpose proof-term deserializer, theorem-equivalence oracle or arbitrary theorem environment is established. This is an isolated fixed-fixture measurement suitable for further adversarial refinement.

## Reproduce

With Lean 4.15.0, Python 3.11+, and VGI's pinned implementation on `PYTHONPATH`:

```sh
python -m unittest discover -s experiments/lean-kernel-independent-recheck -p test_serialized_kernel_evidence.py -v
python experiments/lean-kernel-independent-recheck/term_receipt.py produce --output runner-observation.json
python experiments/lean-kernel-independent-recheck/serialized_kernel_evidence.py \
  --runner runner-observation.json --output serialized-kernel-report.json
```

The last command is a **local diagnostic**, not independent host evidence. The [two-job workflow](../../.github/workflows/lean-serialized-kernel-recheck.yml) establishes separately scheduled live kernel execution.

## Next question

Can a trusted VGI checker policy combine a source-observation authority receipt with this exact independently kernel-checked serialized term, while preventing the two distinct report kinds from being substituted for one another? This should come before generalizing arbitrary proof obligations.
