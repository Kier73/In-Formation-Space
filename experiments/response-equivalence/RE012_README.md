# RE-012 — Applicability of calibrated observation guarantees

**Question.** How can a distributed observer recognize that a *previously calibrated* detection guarantee should no longer be applied after the observed event mix, instrumentation, latency or failure structure changes?

**Result.** An independently replayable, role-HMAC-bound **scope certificate** can be conditionally admitted only while the monitored evidence remains within its declared coverage contract. The verifier suspends it when a monitored condition changes or when statistical assumptions are not explicitly supplied. Signed claims, conditional binomial bounds and real E-CPU causal order **do not** prove stationarity, physical truth, trusted device identity or adversarial detection guarantees.

This extends [RE-011](RE011_README.md)'s controlled injection experiment, [RE-008](RE008_README.md)'s sealed observer history and [RE-006](RE006_README.md)'s negative-control discipline. It also draws on VGI's [observer-relative event geometry](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md) and E-CPU's [typed temporal frames](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py).

## Calibration certificate and conditional mathematics

The signed, exact synthetic RE-011 calibration contains **60 commanded positive injections**, twenty shams and a complementary-dropout A/B fixture: no injected event is jointly missed. The new verifier splits these 60 positives into two **declared** strata:

| Event stratum | Positive samples | Joint misses | Hypothetical one-sided 97.5% binomial upper |
| --- | ---: | ---: | ---: |
| Ordinary | 48 | 0 | ~0.07397 |
| Edge | 12 | 0 | ~0.26465 |

The limits use Clopper-Pearson-style inversion of `Pr(Bin(n,p) <= k) = alpha/2`, with `alpha=0.05`. A Bonferroni union bound gives at least **95% simultaneous coverage**, **if** injections within each stratum are IID, honest, stable and representative of the future population. No independence **between observers** is assumed: the indicator is *joint non-detection*, counted directly for each injection. The weighted upper bound for a stipulated event mix of 80% ordinary and 20% edge is ~**0.11211**, below the model's explicitly chosen conditional tolerance of `0.15`.

None of those statistical premises follows from a signature or a deterministic test. In the default verifier mode, the certificate is **suspended** with reason `statistical_and_physical_assumptions_unestablished`, even if the measured checks pass. Passing `assumptions_accepted=True` is **a hypothetical model admission by the verifier**, not proof that external measurements satisfy them.

The certificate binds the exact three RE-011 baseline seal digests, sensor identities and firmware, sample counts, stratum limits, explicit assumptions, one-sensor-local latency budget of 50 ms, permitted event mix, monitoring joint-miss trigger, and logical window range `1..5`. Only claims matching the authenticated baseline can be admitted; **signing a different certificate does not change its evidential basis**. Fresh monitoring windows have a signed source plan with twelve challenge slots and separately signed A and B responses bound to the plan digest. Missing, altered, duplicated or replayed samples fail closed.

## Conditional validity states

| Monitoring observation | Result / reason |
| --- | --- |
| Two edge events in a twelve-event healthy window | Conditionally applicable **only when all explicit assumptions are accepted** |
| Eight edge events in twelve (population shift) | Suspended: `event_population_shift` and conditional miss limit exceeded, *even with zero observed misses* |
| Event of an uncalibrated stratum | Suspended: `unrepresented_event_stratum` |
| Sensor A replaced or either firmware changed | Suspended: `sensor_configuration_changed`, even with correctly signed reports |
| Any reporter's local elapsed measurement exceeds 50 ms | Suspended: `latency_envelope_exceeded`; **no cross-host elapsed time is computed** |
| Both reporters miss the same two targeted edge events | Suspended: `observed_joint_miss_trigger`; this is an operational trigger, **not** a statistical change-point proof |
| Window number exceeds certificate's declared validity | Suspended: `certificate_expired` |
| Prior window suspended, next window healthy | Still suspended: `previously_suspended_requires_new_calibration` |

A monitor is permitted to report `refused` or `unavailable`, but neither counts as a negative reading. These statuses count against operational detection success if both observers fail to detect the event. A recommendation to recalibrate is not a completed recalibration or permission to resume the old scope.

**Critical indistinguishability counterexample:** the same signed, healthy observation reports can come from an honest detector or from a compromised signer that hides precisely the events the source did not challenge. No cryptographic property of those records establishes detection of *unobserved* events. Similarly, a source that mislabels the event population can produce internally consistent monitoring records and an unjustified favorable scope. The protocol does **not** assert device attestation, real-time source truth, continuous monitoring, detection during arbitrary future events, or a causal source for anomalous measurements.

## Real pinned E-CPU integration

The optional `.github/workflows/re012-applicability-monitor.yml` runs Python 3.11 and 3.13 regressions, plus separate hosted source, A, B and independent-verifier jobs with actual `mailcpu.temporal.TemporalContext` from E-CPU commit `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. Source S emits the baseline and monitor plan, while A and B receive S's native vector stamp and produce separately signed observations. The verifier checks `S before A`, `S before B`, and `A concurrent B` using `CausalStamp.relation()` and binds each native stamp to the exact certificate and monitor report. This is cross-job causality **within CI**, not trusted physical instrument identity. The source baseline is centrally generated by the synthetic fixture, and CI enrollment keys are not hardware-backed.

## Reproduce

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/applicability_monitor.py > /tmp/re012_report.json
cmp experiments/response-equivalence/re012_report.json /tmp/re012_report.json
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re012_cases.py
```

All core code uses the Python 3.11+ standard library. The E-CPU adapter requires its pinned checkout and cannot be replaced with a stub for hosted verification.

## Next research question

Can the system **design a targeted recalibration** that minimizes cost and intervention while explicitly covering the newly observed event classes and preserving evidence of previous invalidation? A stronger step would use verified hardware provenance or independent metrology to justify some of the external premises rather than assuming them.
