# RE-008 — Sealed observation coverage and recoverable multi-observer evidence

**Question:** Can separate observers establish defensible *scoped* coverage guarantees through declared sequence numbers, overlapping observation windows, loss detection, delayed responses, and recoverable evidence logs, without implying that every physical event was seen?

**Result:** In the exact eight-epoch synthetic fixture, each witness drops distinct epochs but the union of its verified recorded readings leaves zero blind **declared** epochs. Signed seals and hash chains detect missing archived records; recovery of the original signed record restores continuity. A pending capture is not a negative reading; its signed delayed completion is attached to the original capture epoch, not to delivery time. None of these operations proves global physical coverage or a bound on completely unseen physical events.

## Connection to previous work

- [RE-007](RE007_README.md) selected costed probes with bounded missing observations, but did not establish its loss assumption from retained evidence.
- [RE-006](RE006_README.md) demonstrated that passing discrete negative controls does not exclude transient unmonitored disturbances.
- [VGI Build 15](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md) models independent observer clocks and inferred correspondences; similar signatures do not certify shared latent events.
- [MOR-001](../multi-observer-causal-reconstruction/README.md) and [E-CPU TemporalContext](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py) separate actor-local clocks from vector-clock causal relations.
- [Evidence-gated observation path](../../bridges/observation-path/README.md) distinguishes missing/denied response from a negative reading.

## Evidence contract

The controller declares capture epochs `0..7`. Synthetic observers `A` and `B` each produce one role-HMAC-bound, hash-chained slot record per epoch. The possible readout statuses are `present`, `absent`, `dropout`, `pending`. A pending capture can be completed by a **separately signed** later delivery bound to the original capture digest; completion does not mutate the already sealed log. Each actor seals the declared range, count and final record digest using its enrolled CI HMAC key. GitHub-hosted jobs are separately scheduled but do not imply independent physical sensors or trusted hardware.

An independent verifier checks keys, session challenge, exact fixed range, per-epoch sequence, record HMAC, adjacent chain and signed final seal. **An archive gap disables any numeric coverage bound**, even when surviving slots look plausible; a retained original signed record can be restored and verified without rewriting a different history. A missing seal similarly disables coverage. A correctly HMAC-signed but dishonest observation remains possible, so every result stays conditional on trusting the enrolled observer's report.

## Controlled results

| Evidence | Verifier result | Interpretation |
| --- | --- | --- |
| A drops epochs `2,5`; B drops `1,4`; A holds a pending `6` | Zero blind declared epochs, one-sided status at `1,2,4,5,6` | Complementary views cover the *declared fixture slots* |
| Delayed A reading for epoch `6` is admitted | A/B corroborate `present` at `6` | Capture slot remains epoch `6`, not delivery time |
| B archive loses record `3` while signed head remains | `unresolved_log_continuity`; no bound | Detectable evidence gap, **not** a sensor dropout |
| Original signed record `3` restored | B chain verified again | Recovery of retained proof |
| Both sensors drop epoch `3` | One blind declared epoch | Unobserved, **not** established absence |
| One says `present` and one says `absent` | Conflict | Disagreement remains unresolved |
| Both say `absent` | Corroborated **sensor-relative** absence | Does not prove no physical event occurred |

`blind_epoch_bound` is the exact count of **declared** epochs with no admitted readout from either witness; it is **not a probabilistic bound**, **not** the number of undiscovered events, and **not** a bound on physical event loss. The policy can suggest a signed-log retrieval, capture-bound delivery, disagreement review or fresh authorized observation, but suggestion never creates an observed result. Fresh observation cannot retroactively establish the history of a missed past event.

## Hosted verification

`.github/workflows/re008-coverage-reconstruction.yml` runs the combined RE test suite under Python 3.11/3.13 and checks the reproducible RE-008 report. Independent controller, A and B GitHub-hosted jobs use the **actual pinned** E-CPU `TemporalContext` and `CausalStamp` at `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`, with signed bindings from each slot digest to its genuine causal stamp. The independent verifier requires `C before A`, `C before B`, within-actor ordering, and `A concurrent B`; it does **not** infer physical simultaneity, a shared wall clock, a cross-host elapsed duration, or real sensor identity. CI role keys travel through GitHub artifact storage, which is not a trusted external key authority.

## Reproduce

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/coverage_reconstruction.py > /tmp/re008_report.json
cmp experiments/response-equivalence/re008_report.json /tmp/re008_report.json
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re008_cases.py
```

All computations use the Python standard library. The E-CPU integration requires the separately checked-out pinned dependency. Test signatures are integrity witnesses for CI keys, not real device attestations. Complete physical time, unbiased sample coverage, absence of common-mode sensor failure, and source truthfulness remain **active research questions**, not proven properties.

## Next frontier

Introduce an independent source-side event counter, periodic source-sealed boundary receipts, and observer-side acknowledgements, then check how far a joint loss **bound conditional on the source clock/counter honesty** can be reconstructed when both observers may share a correlated blind interval. A source claim alone cannot certify events never represented in any observed channel.
