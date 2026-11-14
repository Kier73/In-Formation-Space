# RE-013 — Active recalibration and append-only renewal of scoped detection claims

**Status:** exact synthetic research fixture; CI status must be checked in GitHub Actions. No physical detector, externally attested sensor, or demonstrated statistical sampling premise.

## Question

Once RE-012 suspends a previously issued detection certificate because the event population changes, can a system **choose the new observations it needs**, account for observation and intervention cost, and issue a separately verified **new** revision without erasing the old failure or confusing passive and actively changed systems?

## Connection to existing research

- [RE-011](RE011_README.md) established conditional stratum-wise binomial upper miss limits under explicitly assumed IID, truthful labels and within-trial paired observer dependence.
- [RE-012](RE012_README.md) established that population shift, altered instrument identity, or latency can suspend an existing claim even if a fresh window reports no joint misses. Its old certificate cannot be silently revived.
- [Trial 08: intervention-aware attention](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md) distinguishes acquisition cost from state-changing intervention and requires policies to preserve their query scope.
- [E-CPU temporal implementation](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py) preserves causal handoffs without converting unrelated local clocks.
- [VGI Builds 14–17](https://github.com/Kier73/Virtual-Ground-Interpreter/tree/main/theory_development) motivate observer-relative representations and the limits of transfer across representation changes.

## Exact controlled experiment

`old_fixture()` creates the **existing** signed RE-012 calibration and a separately checked shifted monitoring window. The verifier recomputes the original HMACs and detects `event_population_shift`; it does not accept a supplied Boolean suspension claim. The predecessor remains revision 1 in status `suspended`.

RE-013 targets an event population with exactly **2/3 edge and 1/3 ordinary** events. It enumerates up to eight eight-event batches per stratum, under a synthetic menu of separate observation and intervention costs. Two ten-event sham batches are required in every policy. Each candidate zero-miss plan must satisfy a *hypothetical*, simultaneous one-sided 95%-confidence joint non-detection limit below **15%**; each stratum uses a Bonferroni-adjusted alpha of 0.025. This is a **planning calculation**, not an assertion that future data will have zero misses.

| Explicit protocol and claim | Selected positive batches | Shams | Observation cost | Intervention cost | Hypothetical upper miss bound |
| --- | --- | ---: | ---: | ---: | ---: |
| **Passive detection** | 24 ordinary + 24 edge | 20 | **68** | **0** | **14.25%** |
| **Stimulated detection** | 24 ordinary + 24 edge | 20 | **50** | **15** | **14.25%** |

These are **different observable contracts**. Stimulating the plant alters a documented synthetic state counter and yields evidence only for `fixture-stimulated-stratified-detection`. The apparently cheaper strategy must **not** be used to certify `fixture-passive-stratified-detection`. The costs are arbitrary model units, not empirically measured runtime or elapsed time; the planner minimizes observation cost and then intervention cost within each protocol.

## Evidence and revision protocol

1. A preissued baseline and suspension report are independently rechecked. The source S signs a new plan tied to the old certificate digest and a digest of the recomputed invalidation, not to a mutable replacement.
2. A and B independently record every planned batch with event identities, role-HMACs, parent-linked receipts, signed final seals, declared sensor and firmware, and a synthetic `state_before/state_after` relation. They can prepare receipts without possession of S's signing key; the verifier authenticates S.
3. V verifies S/A/B role enrolment, exact batch completeness, identity, state evolution, tampering/replay, the original suspension, and both stratum miss counts. Unavailable/refused observations count against joint detection when neither role sees the event; they are never negative measurements. Sham false positives disqualify the fixture's strict renewal condition.
4. By default **no revision is admitted**, even if all signed fixture reports pass: the IID, truthfulness, stationarity and representativeness assumptions remain unproved. Only when an independent verifier **explicitly accepts** these premises does it issue a **role-V-signed revision 2** with parent/revision history, new scope and evidence seal identities. Revision 1 remains `suspended`.
5. `verify_revision()` recomputes the entire evidence predicate and checks V's new HMAC. An independent replay process may not treat an existing V signature as a substitute for verifying evidence.

**Local counterexamples:** missing or reordered signed receipts, altered HMACs, forged event identities, missing seals, source policy manipulation even with a valid S signature, sensor replacement, mismatched stimulated/passive scope, targeted joint missed event, sham false positive, bad predecessor evidence, and synthetic intervention-state inconsistency. A sensor that honestly reports an event but was physically mistaken remains possible; a CI key does not prove device identity.

## Cross-host integration

`.github/workflows/re013-active-recalibration.yml` runs the complete RE regression suite on Python 3.11 and 3.13 with pinned E-CPU revision `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`, then creates independently scheduled S, A, B and V GitHub jobs plus an independent replay job. In CI, S receives only S's signing key, A and B receive only their own keys, and V holds test-enrollment verification material. Prior baseline is a preissued **synthetic fixture** created in the enrollment step, not a prior physical production campaign. All observers generate response values using declared test code; CI job separation does **not** establish physical fault-domain separation. V uses the real pinned `TemporalContext`/`CausalStamp` to check `S before A`, `S before B`, and `A concurrent B` (no physical simultaneity). No cross-host elapsed time is claimed.

## Reproduction

From the In-Formation-Space repository root:

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/active_recalibration.py > /tmp/re013_report.json
cmp /tmp/re013_report.json experiments/response-equivalence/re013_report.json
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re013_cases.py
```

The result always includes `physical_detection_guarantee=null`, `adversarial_detection_guarantee=null`, `physical_source_truth_established=false`, and `hardware_identity_established=false`.

## Next research question

Can a **durable, independently managed** applicability authority validate source truth and sensor context across actual deployments, and revoke a new revision when sampling conditions change after it is issued, rather than trusting an explicit synthetic verifier assumption? That is an open problem for VGI's reconstructable Grounds and E-CPU structural-memory certificates.
