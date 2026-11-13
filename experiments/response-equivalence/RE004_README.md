# RE-004 — Intervention effect versus unobserved external evolution

**Status:** Exact synthetic experiment; **23 new local tests** and **61 combined RE-001–004 local tests** passed. The optional four-job GitHub Actions workflow exercises the *real* pinned E-CPU temporal runtime on distinct hosted jobs, subject to CI results. The fixture does **not** prove physical source attribution, real disturbance sensing, source authentication, consensus, or distinct physical fault domains.

## Question

When a probe changes the system, can a later observer distinguish a state change produced by the commanded intervention from external evolution that occurred during the intervention window?

RE-001 established a minimal observable recurrence while separating it from internal identity. RE-002 selected probes based on the distinctions they could reveal. RE-003 replayed intervention histories from independent local processes. **RE-004 tests whether even perfect replay and causal ordering are sufficient to attribute the *source* of a state change.**

## Exact model

The bounded example has plant state `x` modulo 31 and an additional accumulated external-event counter `e`. Different hypotheses assign an action gain `g`, autonomous drift per declared interval `d`, and an external change triggered when a command is applied `t`:

- `apply`: `x' = x + g + d + t`, `e' = e + d + t`;
- `idle`: `x' = x + d`, `e' = e + d`;
- `read`: `x` without intervention;
- `witness`: observe `e`, if `environment:read` is authorized;
- `isolated_apply`: `x' = x + g` only if the declared *synthetic isolation assumption* is accepted and `external:isolate` is authorized.

All arithmetic is exact modulo 31. Host A's sensor is `y_A = x`; host B's raw sensor is `y_B = 3 value + 2`. Cross-host raw values and local clock readings must **not** be subtracted or treated as sharing units.

| Candidate | g | d | t | Distinguishing characteristic |
|---|---:|---:|---:|---|
| `high_gain` | 2 | 0 | 0 | Stronger commanded action |
| `triggered_external` | 1 | 0 | 1 | Weaker action plus external event on each act |
| `ambient_external` | 1 | 1 | 0 | Ambient change also appears during an idle interval |
| `low_gain` | 1 | 0 | 0 | Different primary output immediately |
| `coordinate_alias` | 2 | 0 | 0 | High-gain observable alias with additional invisible state |

The supplied catalogue is intentionally finite, complete *within the fixture*, and not claimed to cover an external machine or physical disturbance family.

### Central negative control

After `apply`, `high_gain`, `triggered_external`, and `ambient_external` all show `x=2`. A no-command `idle` control distinguishes ambient evolution (`x=3`), but **still cannot distinguish** the first two (`x=2`). Their primary response remains identical across every subsequent `apply`, `idle`, and `read` sequence in the declared model. Causal ordering of the observations cannot resolve that ambiguity.

After Host A's two actions, a later observer may use an explicitly admitted `witness` probe. `triggered_external` has `e=1`, so Host B reads `3×1+2=5`; `high_gain` reads `3×0+2=2`. This refines the surviving set from three candidates to **`triggered_external` alone** within the catalogue. If the witness permission is refused, no sensor value or state mutation is inferred and the three candidates remain.

A separate permitted `isolated_apply` experiment also discriminates the two laws, **but only because the isolation property is stipulated in the synthetic transition table**. An actual isolation mechanism requires independent verification, and an unknown external disturbance could invalidate either identification route.

The `coordinate_alias` and `high_gain` cannot be separated by any available authorized readout: this is observational equivalence, *not* recovered internal identity.

## Cross-process and independent-host experiment

The standard-library local experiment launches distinct A and B child processes plus a third verifier process. A produces `apply` and `idle`, and passes a private state checkpoint and 256-bit random nonce to B. A's public record retains a salted checkpoint commitment and an append-only record-hash chain. B verifies the commitment and links its observation to the exact A handoff. The verifier receives **public records only** and replays every candidate state history from the original initial condition.

The private nonce is used because the finite hidden-state space would otherwise permit easy dictionary enumeration of an unsalted commitment. A GitHub Actions artifact containing this nonce is not a confidential enclave. **SHA-256 commitments are not signatures, and a malicious producer able to replace all records can rewrite hashes.** The verifier must not treat the opaque commitment as a direct observation of hidden state.

The optional hosted workflow adds a real E-CPU temporal integration using pinned E-CPU revision [`c99af8c`](https://github.com/Kier73/E-CPU/commit/c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65), borrowed from the working MOR-001 integration. The source job uses `TemporalContext.emit_causal_stamp()` for its two events; the receiver job uses `CausalStamp.from_dict()` and **`TemporalContext.receive_causal_stamp()`** before its own measurement; and the verifier reconstructs precedence from actual E-CPU `CausalStamp.relation()` comparisons. A separate verifier job downloads only the two *public* artifacts, not the private checkpoint/nonce artifact.

That authenticates neither the external event nor the physical origin of the records. The GitHub Actions workflow supplies distinct jobs and artifact handoff, not an independently trusted signing authority. The verified causal result is `A0 before A1 before B0`; this establishes the documented handoff order, **not** that any external event caused a measured transition. No cross-host elapsed time is calculated.

## Reproduction

From the root of In-Formation-Space:

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/intervention_or_drift.py > /tmp/re004.json
cmp experiments/response-equivalence/re004_report.json /tmp/re004.json
```

The E-CPU integration requires its pinned checkout at `external/E-CPU` and a configured `PYTHONPATH`:

```bash
PYTHONPATH=external/E-CPU:experiments/response-equivalence \
  python experiments/response-equivalence/ecpu_re004_cases.py
```

The workflow `.github/workflows/re004-causal-hosts.yml` runs the local matrix on Python 3.11/3.13 and, in separate hosted jobs, source production, receiver continuation and an independent public-record verifier.

## What was learned, and what remains open

**Established by this controlled model:** effect attribution may be underdetermined even with correct intervention replay, causal order and two independently produced records; a newly permitted independent observation or a demonstrated isolation intervention can disambiguate candidate explanations; denied observations provide no negative measurement; no available probe separates the strong-gain alias from its internal coordinate variant.

**Not established:** true independent environmental sensing, source-authenticated physical event receipts, real-world isolation guarantees, causal discovery beyond a declared model class, secure state transfer, cryptographic host identity, or a universal invariant geometry.

**Next discriminating question:** can an independently signed *external event* record be causally joined to an E-CPU intervention receipt under concurrent disturbance, while preserving the distinction between `before`, `concurrent`, and genuinely `unobserved` relations, and without presuming that temporal adjacency implies physical causation?

## Lineage

- [VGI Builds 14–17](https://github.com/Kier73/Virtual-Ground-Interpreter/tree/main/theory_development): observer-relative temporal events and the failure of naive cross-clock correspondence.
- [In-Formation-Space Trial 08](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md): probes may change the state they reveal.
- [MOR-001](../multi-observer-causal-reconstruction/README.md): real E-CPU temporal stamps on independent hosted jobs.
- [Evidence-gated observation path](../../bridges/observation-path/README.md): refusal, receipt, authority and application are distinct.
- [RE-003](RE003_README.md): finite candidate reconstruction across separate processes with persistent state changes.
