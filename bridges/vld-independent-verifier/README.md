# VLD Independent Cross-Language Verifier Bridge (`VIV-001`)

- **Epistemic Status:** **Verified** (on finite positive and adversarial tamper test vectors across Python 3.11–3.14 stdlib and Node.js `node:crypto` stdlib).
- **Source Lineage:** Clean-room reimplementation of the canonical digest, strict-majority quorum ($2q > N$), cross-Ground continuity chain, and 1D `SNC` ReLU capsule contracts of [`Kier73/Virtual-Layer-Dynamics`](https://github.com/Kier73/Virtual-Layer-Dynamics) (`v0.6.0`, MIT License). Shares **zero runtime imports** with `vld`.

## Motivation & Governing Equation

A producer runtime emitting a hash-chained receipt proves internal byte self-consistency, not independent epistemic validity. Following the diverse-verifier discipline established in `IHP-003` and `IHP-004`, an external contributor must be able to check a `CrossGroundContinuityReceipt` chain $(R_0, \dots, R_{m-1})$ against a requested computation $(\text{id}, x_0, (\mathcal{G}_0, \dots, \mathcal{G}_{m-1}))$ without importing producer code:

$$g_0 = H_{\text{vld.pipeline-genesis.v1}}(\text{id}, x_0), \qquad \forall k \in \{0, \dots, m-1\}:\; R_k.\text{source\_ground\_fp} = g_k \;\land\; 2|V_k| > |\mathcal{M}| \;\land\; \text{`|VERIFIED:`} \in R_k.\text{oracle\_verdict}.$$

## Contents

- `vld_standalone_verifier.py` — Zero-dependency Python stdlib verifier (`canonical_bytes`, `domain_digest`, `verify_quorum_certificate`, `verify_continuity_chain`, `verify_snc_1d_capsule`).
- `vld_standalone_verifier.mjs` — Zero-dependency Node.js (`node:crypto`) verifier checking identical genesis fingerprints, HMAC-SHA256 quorum votes, slot lineage, and receipt digests.
- `test_vld_independent_verifier.py` — Runnable `unittest`/`pytest` suite exercising cross-language agreement and deterministic rejection of mutated genesis inputs, altered stage Ground fingerprints, missing independent verifier tags, and forged HMAC votes.

## Reproduction

```bash
python -m pytest bridges/vld-independent-verifier/test_vld_independent_verifier.py -v
```
