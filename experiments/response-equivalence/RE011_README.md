# RE-011 — Controlled event detection calibration, common-mode loss, and collusion

**Question.** After RE-010's independently signed event-origin reports, can deliberate source-side event injections establish a defensible *detection reliability* statement, and how does that statement fail when observers share a fault or collude?

**Result.** We can independently reconstruct **reported detection counts relative to a signed synthetic injection ledger**. A confidence limit on a future miss probability additionally requires IID sampling, truthful physical injection labels, stationary conditions, and an unbiased test population. The deterministic fixture establishes none of these physical premises. It demonstrates why naive multiplication of two observer miss rates is unsafe without within-trial conditional independence.

## Experimental construction

- An enrolled synthetic source S produces a sealed, hash-chained challenge ledger with **60 commanded event injections** and **20 sham (no-event) trials**, one declaration per trial.
- Enrolled observers A and B each produce a distinct signed, hash-chained report for every declared trial. Accepted statuses are `detected`, `not_detected`, `unavailable`, and `refused`. Injections with unavailable/refused reports count against detection success without pretending to be negative measurements.
- An independently executed verifier checks source and observer role-HMACs, session challenge, event identity, exact trial indexing, parent links, final seals, and the separation of injected and sham trials.
- A host-oriented adapter carries the **real pinned E-CPU** `TemporalContext` and `CausalStamp` across S → A and S → B GitHub Actions artifacts. The verifier checks S precedes both observers and the observer stamps are mutually concurrent. No local-clock arithmetic or physical simultaneity is inferred.

All source labels and observations are generated from the same declared *synthetic* model. CI jobs and role keys are distinct, but neither the injection nor any sensor is a physical device. The signed source history is a fixture truth **only by stipulation**.

## Exact finite-sample observations

| Deterministic regime | A non-detections / 60 | B non-detections / 60 | Joint non-detections / 60 |
| --- | ---: | ---: | ---: |
| Complementary faults (different missed events) | 12 | 12 | **0** |
| Common-mode faults (same missed events) | 12 | 12 | **12** |
| Colluding silence (both report no detection) | 60 | 60 | **60** |

The first two have identical individual non-detection counts, yet their joint outcomes differ by twelve trials. A source-ledger challenge can *expose this difference within the supplied fixture*. It does not establish why the observers failed. An intentional false report can be correctly HMAC-signed. And if the source and observers collude, physical reality could disagree with *all* public claims.

The twenty sham trials allow false-positive *reports* to be measured separately; an explicit test injects a sham false positive. Other tests cover source or observer archive loss, signer's key substitution, challenge replay, status modification, fabricated event identity, and a source false-injection counterexample.

## Conditional statistical interpretation

`upper_binomial_miss(k,n,alpha=.05)` numerically inverts the binomial CDF to produce a one-sided 95%-confidence upper bound for the population **non-detection** probability *if and only if* the `n` trials are IID Bernoulli measurements of a truthful, stable and representative source population. The routine uses the observed joint failure indicator directly, so **it never assumes A and B fail independently within a trial**. The point-estimate product of separate miss rates is invalid under correlated failure.

For the synthetic 60-positive examples, these **hypothetical IID** upper limits are:

| Regime | Individual A/B upper bound | Joint upper bound |
| --- | ---: | ---: |
| Complementary (0 joint non-detections) | ≈ 30.38% each | ≈ 4.87% |
| Common-mode (12 joint non-detections) | ≈ 30.38% each | ≈ 30.38% |
| Both silent (60 joint non-detections) | 100% | 100% |

These are **not** confidence guarantees for the fixed deterministic patterns themselves. Computing them requires the caller to explicitly select `iid_assumed=True`, and the report states that assumptions were not established by CI. A claimed 0/60 observed joint miss rate is therefore not proof of zero future risk. An unbounded adversary has no quantitative detection guarantee from this experiment.

### Two indistinguishable physical worlds

In world W1, S actually produces an event and both sensors fail. In W2, S signs the same injection declaration but no physical event occurs and both sensors correctly see nothing. Their **public signed records can be identical**. Source signatures, cross-host vector timestamps, positive/sham controls and matching event IDs cannot distinguish these worlds absent an independent physical source-truth premise.

The experiment makes that uncertainty explicit: `physical_injections_verified=false`, `source_truthfulness_verified=false`, `independence_between_observers_verified=false`, `physical_instrument_identity_verified=false`, and `adversarial_miss_bound=null`.

## Reproduction and verification

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/detection_calibration.py > /tmp/re011-report.json
cmp experiments/response-equivalence/re011_report.json /tmp/re011-report.json
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re011_cases.py
```

`.github/workflows/re011-calibrated-faults.yml` checks out pinned E-CPU revision `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`, runs tests on Python 3.11/3.13, and creates distinct hosted source, A, B and verifier jobs. CI HMAC keys are test secrets stored in GitHub Actions artifacts—not physical attestation credentials. The report belongs to the pinned implementation and challenge contract; this is a bounded simulation, not a sensor calibration performed in a laboratory.

## Research lineage and next question

- [RE-008](RE008_README.md): recoverable signed observation coverage within declared intervals.
- [RE-009](RE009_README.md): source counter detects common-mode disagreement, not its physical cause.
- [RE-010](RE010_README.md): origin-event identities triangulate claims without establishing physical occurrence.
- [VGI temporal event graphs](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md): event correspondence must be verified, not inferred from similar temporal patterns.
- [E-CPU temporal model](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py): actor-local readings and causal partial orders are different forms of evidence.

**RE-012 question:** how can a verifier test whether *past calibration conditions still apply* after sensor repairs, latency changes, operator/model updates or shifts in the event population? The immediate next experiment is change-point detection and online calibration under explicitly bounded drift, including an adversary that selectively changes only unobserved regions.