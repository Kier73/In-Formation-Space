# Experiment: independently authenticated checker-workflow authority

**Question:** Can a VGI `VerifiedKernelReceipt` be admitted after authenticating *who supplied the checker key and result* using a trust root independent of those artifacts?

The earlier `term_receipt.py admit` checked an Ed25519 signature over matching Lean theorem, environment, proof-term fingerprint and VGI obligation, but the public key was transferred from the same checker job. That only established possession of a **self-supplied key**.

This experiment adds `attested_admission.py` and a **main-branch-only** `vgi_attested_admission` job. It authenticates the bytes of three subjects using GitHub's artifact attestations and the public Sigstore trust root *before* permitting the VGI admission:

- the independent checker observation;
- the checker-signed recheck statement;
- the ephemeral checker Ed25519 public key.

Each is checked through GitHub CLI's attestation verifier against an **explicit authority policy**: repository `Kier73/In-Formation-Space`, stable GitHub repository ID `1454466415`, source commit equal to `GITHUB_SHA`, ref exactly `refs/heads/main`, signer workflow `Kier73/In-Formation-Space/.github/workflows/lean-term-receipt.yml` authenticated via the exact workflow signing certificate SAN (GitHub CLI rejects combining `--cert-identity` with `--signer-workflow`), GitHub-hosted-runner-only policy, SLSA provenance predicate and the actual file's SHA-256 digest. The verifier fetches attestations from GitHub rather than accepting an artifact-supplied bundle as the root of trust.

The GitHub CLI version must be **2.102.0 or newer**. Earlier builds contained known flaws in `--signer-workflow` prefix matching and case-insensitive `--source-ref` comparison (GitHub advisories GHSA-wjmr-j3rp-mh2g and GHSA-4mq3-hpgx-9cx8, patched in 2.102.0). Unsupported, missing, or failing verification rejects admission.

Only after all three subjects pass the provenance verification does the adapter call the existing `term_receipt.admit`, which itself checks the Ed25519 signature and exact runner/checker/VGI identity binding. The new admission observation records the source workflow/commit/run, verifier version, subject hashes, attestation-verification output digests, and accepted VGI receipt identity.

## Distinguishing the two admission paths

- `vgi_fixture_admission` remains an explicit *fixture-only* diagnostic. Its key is self-supplied, so its `kernel_accepted` observation must not be promoted to independently authorized theorem acceptance.
- `vgi_attested_admission` is the authoritative **GitHub-workflow-provenance-gated experiment**. The job runs only for a `main` push. Pull-request jobs execute offline adversarial authority-policy tests but do not issue GitHub-authorized checker receipts. The attested path also attests its final admission report on `main`.

## Boundaries retained

A cryptographically authenticated workflow identity proves that the bytes were attested by a workflow with that identity and source revision. It does **not** prove that the workflow implementation is correct, that a privileged actor could not alter the code or evidence before signing, that separately scheduled jobs used independent hardware, or that the checker rechecked a serialized proof term using a distinct implementation of Lean.

The key is still ephemeral per run. It is provisionally authorized through the **GitHub Actions workflow authority**; this is distinct from a persistent checker-key registry with rotation, revocation and independent approval. A malicious change to the authorized workflow on `main` can alter what its jobs attest, so main-branch review/protection and workflow governance remain significant security assumptions. The signer workflow's certificate identifies a workflow, **not an independently demonstrated checker job or honest executor**.

The Lean experiment still extracts and rechecks the fixed `KernelTrial.identity` theorem via Lean 4.15.0. It is **not** a stand-alone parser and kernel verifier for arbitrary serialized `Expr` trees. Proof-term fingerprints establish identity of encoded representations, not mathematical equivalence.

The provenance verifier is a trust-boundary adapter, not a distributed consensus system or general proof checker.

## Reproduce and inspect

The related GitHub Actions workflow is [`lean-term-receipt.yml`](../../.github/workflows/lean-term-receipt.yml). The new path is observable in retained artifacts after a successful main run. The main-only `attested_admission.py` rejects local or PR use; reproducible local checks exercise its **contract** against a mocked GitHub CLI and should not be counted as a live Sigstore verification:

```sh
python -m unittest discover -s experiments/lean-kernel-independent-recheck -p test_attested_admission.py -v
```

The next question is to isolate the kernel itself: given a named VGI obligation, a closed serialized Lean `Expr` proof term and a complete environment, can a separately constructed checker reconstruct and kernel-check that term without using the original elaborator? This remains open after authenticated workflow provenance.
