# Multi-Model Virtual-Layer Arbitration & Recursive Meta-Scheduling (`MVA-001`)

- **Epistemic Status:**
  - **Verified (Finite Local & Reference Equivalence):** `Llama` (`SmolLM2`), `Qwen2` (`DeepSeek-R1-Distill`), and `GLM-4` (`GLM-Z1`) `vld` realizers match PyTorch `transformers` (`4.51.3`, FP32) with `max_abs_logit_diff <= 1.2e-7`. Recursive Depth-1 $\to$ Depth-2 `InLayerMetaArbitratorModel` continuity receipts pass zero-import verification (`bridges/vld-independent-verifier`).
  - **Observation (Live HTTP `206` Range & Local Checkpoint Execution, 2026-11-18):** Empirical execution across 7 distinct open-weight checkpoints (`DeepSeek`, `GLM`, `Qwen`, `SmolLM`) recorded in [`evidence/live_7model_campaign.json`](evidence/live_7model_campaign.json).
  - **Unknown / Out-of-Scope:** Sustained multi-token generation across full `510 GB` `DeepSeek-V4.1-Flash` or `1.51 TB` `GLM-5.3-BF16` checkpoints across geographically separated hosts remains an open multi-host benchmark.

## Arbitrated Model Fleet & Recorded Observations

| Model Repository | Pinned Git SHA | Architecture | Execution Mode in `vld` (`v0.6.0`) | Observed Bytes / Result |
|---|---|---|---|---|
| `HuggingFaceTB/SmolLM2-135M-Instruct` | `12fd25f77366...` | `llama` (30 layers) | Live HTTP `206` Range coalesced (`5` spans, `8` requests) + full 30-layer greedy decode | `269.06 MB` $\to$ *"Information in transit across a communication network is a key factor in determining the reliability and reliability of the communication"* (`ckpt = d6ae996b...`) |
| `Qwen/Qwen3-0.6B` | `c1899de289a0...` | `qwen3` (28 layers) | Local Safetensors Ground + full 28-layer greedy decode | `310` tensors $\to$ *"Information in transit across a communication network is called what? A. Data B. Information C. Data"* (`ckpt = cd3b3540...`) |
| `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` | `ad9f0ae0864d...` | `qwen2` (biased QKV) | Live HTTP `206` Range Layer 0 execution | `93.65 MB` (`2.635%` of `3.55 GB` shard), `head8[0] = -0.023489` |
| `THUDM/GLM-Z1-9B-0414` | `b221b06fefb2...` | `glm4` (4-norm sandwich + `0.5` interleaved RoPE) | Live HTTP `206` Range Layer 0 execution | `408.00 MB` (`2.171%` of `18.79 GB` checkpoint), `head8[0] = 0.004465` |
| `deepseek-ai/DeepSeek-V4.1-Flash` | `314113f8a7da...` | `deepseek_v41_text` (`510.29 GB`) | Live HTTP `206` structural glance + Depth-2 sub-arbitration | `7.50 MB` (`0.00147%` of checkpoint), `128.0x` Sink-MLA KV compression, `6/384` `FP4` experts |
| `zai-org/GLM-5.3-BF16` | `abf42e6c0e53...` | `glm_moe_dsa` (`1.507 TB`) | Live HTTP `206` structural glance + Depth-2 sub-arbitration | `5.42 MB` (`0.00036%` of checkpoint), `56.89x` Latent MLA compression, `8/256` experts |
| `Qwen/Qwen3-30B-A3B` | `e18783663704...` | `qwen3_moe` (`61.06 GB`) | Live HTTP `206` structural glance + Depth-2 sub-arbitration | `1.83 MB` (`0.0030%` of checkpoint), `8/128` sparse experts |

## Recursive In-Layer Model-Arbitrating-Model Structure

Instead of external hardcoded Imperative loops, `arb.meta.depth1` (`InLayerMetaArbitratorModel`, capsule digest `a6dd5f3e195b28e6...`, admitted via whole-domain $\mathbb{Q}^4$ multivariate ReLU ridge verification) evaluated candidate utility:

$$U(c, s, b, h) = 4c + 2\operatorname{ReLU}\!\left(s - \frac{1}{2}\right) - 2\operatorname{ReLU}\!\left(b - \frac{1}{4}\right) - 8\operatorname{ReLU}(1 - h),$$

and under `ReceiverHypervisor` `AgentCapability.ARBITRATE_MODEL` (`max_arbitration_depth = 2`) scheduled **both** direct model Grounds **and** `in_layer.frontier_sub_arbitrator` (`arb.meta.depth2`), which itself arbitrated the 3 frontier MoE checkpoints inside a nested quorum lineage (`final_continuity_digest = b3437cfdbd8407e71a395bd7c9d97cf9c7f326827e7161a89f9077dad89d85d2`).

## Reproduction

```bash
python -m pytest experiments/multi-model-virtual-layer-arbitration/test_live_arbitration_evidence.py -v
```
