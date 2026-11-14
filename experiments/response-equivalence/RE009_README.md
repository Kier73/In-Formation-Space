# RE-009 — Independent source-counter reconciliation and common-mode blindness

**Question:** when two sealed observers agree and cover every declared capture epoch, can an independently signed source-side event count expose a shared omission? What, precisely, can be concluded when the source counter is itself fallible?

**Status:** reproducible **exact synthetic fixture** with 22 new core tests. Hosted E-CPU integration is conditional on GitHub Actions results; separate GitHub jobs and CI role-HMAC keys do **not** attest physical sensors, independent physical fault domains, genuine external events, or a trusted hardware source counter.

## Research lineage

- [RE-008](RE008_README.md) proved scoped coverage across eight **declared capture intervals** with observer-HMAC seals, dropout reporting, delayed receipts and original-record recovery. Its `blind_epoch_bound == 0` does *not* establish an event-loss bound.
- [RE-006](RE006_README.md) showed that sampled controls cannot exclude an unobserved disturbance between samples.
- [E-CPU TemporalContext](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py) supplies distinct causal and local clock domains; the hosted adapter uses the repository-pinned real implementation, not an invented global timeline.
- [VGI local-clock experiments](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md) distinguish recurrent response similarity from independently established event identity.

## Evidence and hypotheses

The synthetic source S claims cumulative counts at exclusive boundaries `0,4,8`: `(0,2,4)`. Each boundary is an S-key HMAC receipt linked to its predecessor. The source's three receipt messages are bound to an exact session challenge and, in hosted runs, to the original E-CPU controller envelope digest. The *source assertion* is not an independently verified physical event occurrence.

Observers A and B retain RE-008's signed, sealed, continuous logs. A drops epochs `2,5`, with a delayed capture at `6`; B drops `1,4`. Each observer signs an **acknowledgement of source-head and its own observer-seal digest**. The independent verifier authenticates S, A and B under CI-enrolled keys, verifies all chains and delayed receipts, and recomputes deduplicated observed event counts. The observer acknowledgement signifies acceptance of a source claim *by digest*, not agreement that its count is correct. The observers are not issued the source signing key.

| Exclusive window | S-reported event count | Deduplicated A/B present readouts | Count difference |
| --- | ---: | ---: | ---: |
| `[0,4)` | 2 | 1 | +1 |
| `[4,8)` | 2 | 2 | 0 |
| **Total** | **4** | **3** | **+1** |

The observer logs have **zero blind declared capture intervals**. Both independently report `absent` at epoch 3, yet the source counter claims one additional event somewhere in the first window. This is a **source–observer count disagreement**, not a proof that the omitted physical event occurred at epoch 3, nor that the source count was accurate.

### Indistinguishable underlying worlds

1. There truly was an event missed by both observers and counted by source S.
2. There was no such event and the source counter overstated the number of events.

The two worlds yield the **same public receipts and observer logs**. Since the source's truthfulness is not derived from its HMAC, the verifier is not permitted to select one world. Equally, when source counts are `(0,1,3)` and match the three recorded events, hidden events *missed by all three parties* remain possible: agreeing counters do not prove physical completeness.

Boundary counts identify a *window-level discrepancy*, not a specific event instant or causal influence. The synthetic fixture additionally assumes at most one source event per declared interval and stable event fingerprints. Real counters may overflow, skip, coalesce or duplicate events; such behavior requires separate contracts, tests and independent evidence. No probabilistic loss bound is claimed.

## Admission and failure modes

- Loss of an archived A/B record, or a missing observer seal, produces `unresolved_archive_continuity`. The verifier computes **no count discrepancy** until the original signed record is restored.
- Contradictory observations produce `unresolved_conflicting_observers`; neither side is silently selected.
- Missing A/B acknowledgements or wrong source-head and seal bindings are rejected. Rehashed tampering fails HMAC verification. A valid source record from another challenge cannot be replayed.
- A delayed observation is attributed to its **capture epoch**, not its delivery timestamp, and a duplicated delivery fails closed.
- An auditor can *plan* a request for independent event-origin evidence for `[0,4)`. The plan does not invent a historical observation or a permission grant.

## Hosted E-CPU integration

`.github/workflows/re009-common-mode-counter.yml` has separate **enrollment**, **source**, **observer-A**, **observer-B** and **independent verifier** jobs, plus Python 3.11 and 3.13 tests. The source generates a real E-CPU controller causal frame, signs its counter receipts with a session/key identity and exact controller digest, and passes public source claims to A and B. Those independent hosted jobs consume the controller's actual causal stamp, produce their own E-CPU slot-bound causal frames, and sign their own source-head/observer-seal acknowledgements. The independent verifier invokes the existing proven RE-008 causal/frame-binding verifier and RE-009 counter verifier.

The actual pinned dependency is E-CPU commit `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. Host ordering demonstrates `controller before A`, `controller before B` and E-CPU vector-clock **concurrency** between observer streams. It does **not** show simultaneous observation, synchronized wall clocks, real external-event origin, or a cryptographically protected hardware counter. Enrollment keys are synthetic secrets passed through GitHub Actions artifacts, not a secure external PKI; a party holding its role key can sign false observations.

## Reproduce

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/common_mode_counter.py > /tmp/re009.json
cmp experiments/response-equivalence/re009_report.json /tmp/re009.json
# With E-CPU pinned at external/E-CPU:
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re009_cases.py
```

## Scientific interpretation and next question

**Established in the finite model:** signed source-boundary assertions can expose a discrepancy that complete, mutually consistent observer logs cannot detect on their own. Sealed records, source–observer acknowledgement, and E-CPU causal ordering can make that discrepancy independently reconstructable without granting the source infallibility.

**Not established:** which side is correct, genuine common-mode physical event loss, source-device integrity, exhaustiveness of the event ontology, real device enrollment, and physical causation.

**Next discriminating question:** Can a third, independently sourced *event-origin commitment*, with a non-colluding authority boundary and verified association to the event itself, refine the discrepancy while preserving a meaningful `unknown` outcome when attribution remains underdetermined? Even then, event-origin attestation is not proof that every event was counted.
