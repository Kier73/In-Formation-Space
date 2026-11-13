# RE-006 — Scope-bound intervention receipts and negative controls

**Question:** can RE-005's externally supplied `controlled_exclusion_assured` flag be replaced by independently checked evidence of an intervention window, environmental checks and negative-control probes?

**Answer:** only **within a declared closed finite model**. The receipts can verify which assertions were made by enrolled roles, the consistency of an intervention window under native E-CPU causal-stamp semantics, and whether specified controls pass. Neither passing controls nor authenticated event assertions prove the absence of an unmonitored influence. Without an explicit model-completeness premise, RE-005's causal ambiguity **remains**.

## What is tested

- **A** issues an `open` intervention-command receipt, then on a separately resumed job issues a `close` completion receipt bound to both independent observations. The command is synthetic; a signed claim of completion does not prove actual physical actuation.
- **M** issues a signed event/sentinel observation tied to A's start. It reports the external-event value and sentinel at three declared instants (`pre`, `during`, `post`). The three samples are **not continuous monitoring**.
- **N** independently issues signed **sham** (expected change 0) and **positive-control** (expected change 1) measurements, also linked to A's opening. The positive control detects a sensor stuck at zero; the sham is a negative control for unwanted effects.
- **B** records the synthetic plant's output (`Y=2`), linked to A's close. B has no signing key and its raw outcome is not physically authenticated.
- **V** reconstructs the chain from public receipts and separately provided enrollment keys. Role HMACs bind key identity, challenge, role, data, and E-CPU stamp. The verifier checks the exact causal vector and `CausalStamp.relation()`; an unkeyed SHA-256 digest alone never authenticates a role.

This extends [RE-005](RE005_README.md), [MOR-001](../multi-observer-causal-reconstruction/README.md), the [evidence-gated observation bridge](../../bridges/observation-path/README.md) and [VGI's local-clock investigations](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md).

## Scientific result

For the RE-005 three-hypothesis example, passive outputs already admit `event_causal`, `common_cause_marker`, and `common_cause_alias`. The controlled readout `Y=2` is predicted by the marker/alias models but not by the event-causal model **if** the controlled exclusion hypothesis is true. RE-006 replaces the injected control-success flag with receipts that are recomputed and checked independently, while preserving the remaining model-completeness assumption.

| Verification setting | Controls | Finite-model survivors | Physical causal proof |
| --- | --- | --- | --- |
| `open_world` (default) | pass | all three | **No** |
| `declared_closed_world` (explicit verifier-supplied assumption) | pass | marker + alias | **No** |
| `declared_closed_world` | sentinel changes during window | all three | **No** |
| `declared_closed_world` | refusal, missed samples, sham failure, positive failure, or incomplete action | all three | **No** |

**Distinguishing counterexample:** a transient, unmeasured disturbance between `pre`, `during` and `post` can leave all three sentinel observations equal. Both worlds produce identical receipts. The verifier therefore sets `unobserved_channels_excluded=false` and `physical_causation_proved=false` even for a conditional finite-model success. Likewise, `declared_closed_world` is **not** inferred from a MAC or a control result—it is an independently supplied *model assumption*. Malformed, missing, replayed, rehashed, mis-keyed or contradictory records fail closed.

## Real E-CPU temporal integration

The hosted workflow `.github/workflows/re006-scoped-intervention-audit.yml` uses the **pinned** E-CPU temporal implementation at `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. The producer roles run in separate GitHub-hosted jobs with independent process-local clock contexts. M and N receive A's `open` causal stamp; the resumed A actor merges M and N before emitting `close`; B receives that close stamp before producing its own observation. The independent verifier checks these relations:

- `A_open before M` and `A_open before N`;
- `M concurrent N` (vector-clock concurrency, **not** physical simultaneity);
- `M before A_close`, `N before A_close`, `A_close before B`.

No cross-host elapsed time is computed. A's logical actor continuation on a distinct job is not hardware identity continuity. The workflow's ephemeral HMAC keys live in the same GitHub Actions trust domain; they are **not secure isolated hardware credentials**, physical sensors, or externally attested authorities. Host B receives only the public key identifiers; the verifier receives the role keys to validate MACs. This does not secure key confidentiality from a hostile workflow participant capable of accessing its artifacts.

## Reproduction

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/scoped_intervention_audit.py > /tmp/re006_report.json
cmp experiments/response-equivalence/re006_report.json /tmp/re006_report.json
```

With a checkout of the pinned E-CPU revision at `external/E-CPU`:

```bash
PYTHONPATH=external/E-CPU:experiments/response-equivalence \
  python experiments/response-equivalence/ecpu_re006_cases.py
```

No runtime dependencies are added to the existing research series. The standalone exact model uses only the Python standard library. Hosted tests must pass before merge.

## Next frontier

A production-capable exclusion study needs **independently verified sensor coverage and fidelity**, instrument calibration, genuinely randomized or otherwise defensible intervention assignment, trustworthy actuator execution receipts, and explicit treatment of unmeasured confounders. Even fully authentic logs that actions and events were observed cannot, by themselves, prove physical effects. A valuable subsequent experiment is an instrumented interventional design with sealed capture windows and adversarial sensor-dropout experiments, measuring the epistemic cost of missing evidence instead of converting it into a negative observation.

