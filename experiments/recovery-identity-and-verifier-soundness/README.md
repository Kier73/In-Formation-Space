# Recovery-Identity Soundness & Mandatory Stage Verifiers (`RIV-AUDIT-001`)

- **Epistemic Status:** **Verified** (within the bounded finite counterfactual harness in `test_recovery_soundness.py`).
- **Source Lineage:** Directly tests the hypothesis raised during the November 17–18, 2026 read-only peer examination of [`Kier73/Virtual-Layer-Dynamics`](https://github.com/Kier73/Virtual-Layer-Dynamics) (`commit 84e1873ee91c`, resolved in `v0.6.0`).

## Question & Hypothesis

Suppose a crash-resumable coordinator commits stages $0 \dots k-1$ of a pipeline $P = (\text{id}, x_0, (\mathcal{G}_0, \dots, \mathcal{G}_{m-1}))$ into a quorum ledger, crashes, and is invoked again under the same `pipeline_id` with modified initial input $x_0' \neq x_0$ or modified stage Ground $\mathcal{G}_j' \neq \mathcal{G}_j$ ($j < k$).

- **Legacy Chain-Only Model ($\mathcal{M}_{\text{chain}}$):** Checks only $R_j.\text{stage\_index} = j$ and $R_j.\text{prev\_digest} = R_{j-1}.\text{digest}$.
- **Inductive Genesis-and-Spec Model ($\mathcal{M}_{\text{inductive}}$):** Enforces:
  $$k \le m \;\land\; \forall j < k:\; R_j.\text{source\_fp} = g_j \;\land\; R_j.\text{target\_fp} = \mathcal{G}_j.\text{fp} \;\land\; V_j(s_j, s_{j+1}) = \text{true},$$
  where $g_0 = H_{\text{genesis}}(\text{id}, x_0)$ and $g_{j+1} = R_j.\text{target\_fp}$.

## Discriminating Outcomes Recorded

1. **Counterexample Witness on $\mathcal{M}_{\text{chain}}$:** Committing $s_1 = x_0 + 10$ on $x_0 = 5$ (`s_1 = 15`), crashing, and resuming with $x_0' = 100$ causes $\mathcal{M}_{\text{chain}}$ to return $15 \times 3 = 45$ instead of $(100 + 10) \times 3 = 330$ (`silent stale-computation reuse`).
2. **Sound Refusal on $\mathcal{M}_{\text{inductive}}$:** $\mathcal{M}_{\text{inductive}}$ detects $R_0.\text{source\_fp} = H(\text{id}, 5) \neq H(\text{id}, 100)$ before executing any downstream stage and deterministically refuses recovery.
3. **Forged Worker `PASS` Rejection:** Separating realization $F_j(s)$ from mandatory independent verification $V_j(s, s')$ rejects self-attested `"PASS"` strings carrying corrupted state (`999999`) prior to quorum proposal.

## Limitations

This standalone harness models deterministic finite state transitions in a single process; physical multi-machine network partitions and Byzantine quorum collusion ($f \ge \lceil N/2 \rceil$) lie outside its boundary.

## Reproduction

```bash
python -m pytest experiments/recovery-identity-and-verifier-soundness/test_recovery_soundness.py -v
```
