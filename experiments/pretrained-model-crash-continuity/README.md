# PMC-001 — Pretrained Model Crash-and-Resume Continuity Across Independent Environments

- **Status:** `Verified` (pinned 28-layer `Qwen/Qwen3-0.6B` checkpoint across real `os._exit(73)` process loss, X.509 v3 mTLS M1 state transfer, Paxos term-2 quorum fencing, and independent PyTorch FP32 reference comparison)

## Governing Equation

Partition a $L$-layer pretrained decoder $F = \Pi_{\text{logits}} \circ T_{L-1} \circ \dots \circ T_0 \circ E$ into stage blocks $B_0, \dots, B_{K-1}$. If Environment $\alpha$ seals $B_0, \dots, B_{m-1}$ in $2q > N$ quorum slots and terminates abruptly (`os._exit(73)`), Environment $\beta$ fences term $t' > t$, verifies the inductive genesis & Ground chain, streams $h_{m-1}$ over mTLS M1 pages, and evaluates ONLY $B_m, \dots, B_{K-1}$:

$$\Pi_{\text{logits}}\!\left((B_{K-1} \circ \dots \circ B_m)\big(\text{Recover}_{t'}(r_{m-1})\big)\right) \approx_{\epsilon} F_{\text{PyTorch}}(x_0), \qquad \text{replayed\_layers} = 0$$

## Contents

- `run_qwen3_crash_resume_benchmark.py`: Live two-process benchmark over `Qwen/Qwen3-0.6B @ c1899de289a04d12100db370d81485cdf75e47ca` vs PyTorch `AutoModelForCausalLM` (`FP32`).
- `evidence/qwen3_0_6b_crash_resume_vs_pytorch.json`: Recorded 4-stage continuity receipt bundle, mTLS byte counts, physical wall-clock timings, algebraic `NavigationCostVector`, and PyTorch logit comparison.
- `test_pretrained_crash_continuity.py`: Self-contained `os._exit(73)` subprocess test + Python/Node.js standalone audit of the recorded `Qwen3-0.6B` evidence.
