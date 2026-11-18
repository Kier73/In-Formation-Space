# VRU-001 — Verified Realization Across an Unstable Computational Fabric

Executes the flagship five-stage systems & mathematical experiment proposed in Peer Examination A (`examination and research direction - a.md`):

1. **Reference Ground:** Pinned `Qwen/Qwen3-0.6B` (`c1899de289a04d12100db370d81485cdf75e47ca`, 28 layers, `151,936` vocabulary) evaluated on `"Information is a dimension, and the virtual layer makes it a"`, checked against an independent `PyTorch 2.7.0 FP32` (`transformers`) reference.
2. **Multiple Qualified Realizations:**
   - Monolithic `PyTorch FP32` reference (`3,207.50 ms`),
   - Conventional local single-process `vld` control (`2,820.34 ms`, reading `1,192.16 MB` by skipping redundant tied `lm_head.weight`),
   - 3-shard distributed streaming KV attention (`OnlineFlashStreamState` rescaling monoid: `max_err = 5.33e-15` vs `4.497` error on premature-normalization negative control),
   - Unstable 2-process X.509 v3 mTLS execution surviving `os._exit(73)` after Layer 13, 1 simulated TLS link drop (`522,177` M1 bytes streamed), and quorum rotation `(q0, q1) -> (q1, q2)` with **`0` replayed layers**.
3. **Asymmetric Public-Key Quorum (`ed25519-rfc8032`, Zero Secret Disclosure):**
   Ephemeral OS-entropy Ed25519 private keys are destroyed prior to writing `evidence/vru001_bundle.json`. Both standalone zero-import Python (`vld_standalone_verifier.py`) and zero-dependency Node.js (`vld_standalone_verifier.mjs`, OpenSSL `node:crypto`) verify all 4 stages (`final_continuity_digest = 7c026e1f1a780f66...`) using **only** the 32-byte public keys.
4. **Proof-Carrying Numerical Accuracy (`IDEA-007`):**
   Exact `Fraction` Lipschitz error propagation certifies top-1 token invariance (`12871` = `" dimension"`, `max_abs_logit_diff = 0.00001621` vs PyTorch FP32, exact top-5 match `[12871, 6961, 4108, 6193, 1931]`).
