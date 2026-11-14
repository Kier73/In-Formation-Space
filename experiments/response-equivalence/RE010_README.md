# RE-010 — Independent event-origin commitments and source/observer triangulation

**Question:** Can a third, separately enrolled origin witness break the ambiguity between a *common-mode observer omission* and a *source-counter overstatement*, without pretending that signatures prove physical event occurrence?

**Result:** A third signed event-identity history can **locate a disagreement between claims** and can conditionally favor one explanation when the origin's completeness and truthfulness are independently justified. It does **not** establish those premises by signing its own log. Within the eight-epoch synthetic fixture, two genuinely different latent worlds can produce the **same** source, observer and origin records.

## Lineage

- [RE-009](RE009_README.md) established a source-counter excess of one event in window `[0,4)` compared with fully sealed observers; a source overcount and a missed physical event remained observationally indistinguishable.
- [RE-008](RE008_README.md) separated missing observer archive records, sensor dropout and physically unobserved events.
- [VGI temporal event graph experiments](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md) require actual event correspondence rather than assuming shared clock time or similar rhythms imply the same event.
- [E-CPU TemporalContext](https://github.com/Kier73/E-CPU/blob/main/mailcpu/temporal.py) carries causal partial-order evidence independently of host-local wall and monotonic timestamps.

## New evidence path

A **controller C** declares one session challenge and an eight-epoch window. Five reporting actors take distinct roles:

- **S:** the existing RE-009 signed cumulative event counts at boundaries `0,4,8`;
- **A/B:** the existing RE-008 separately sealed observation logs with capture-indexed event fingerprints, dropouts and a delayed completion;
- **O:** the new origin witness, producing its own ordered signed event claims, per-event identity fingerprints, parent-linked receipts and a signed window seal. Its signer key is distinct from S, A and B, and its hosted CI job receives neither S's counter nor A/B's archived observations;
- **V:** an independent verifier that receives the signed public records and previously enrolled CI fixture keys, checks the record chains, observer acknowledgements, origin event identity and E-CPU vector-clock relations, and reports only scoped conditional conclusions.

The origin event fingerprint is `SHA-256(canonical({epoch, mark}))`. Equality of fingerprints supports *event-identity agreement under this declared encoding*. The event mark and epoch come from the claiming role; no physical source authentication follows. At most one claimed event per epoch is a fixture assumption, not a universal law.

## Exact counterexample

The original RE-009 fixture has signed source counts `(0,2,4)` and observer reports from events in epochs `1,4,6`. Both observers report **absent** at epoch `3`, and their signed archive chains are complete. They can still both be wrong about a physical event.

| New origin report | Source count | Observer distinct count | Permitted conclusion |
| --- | ---: | ---: | --- |
| `1,3,4,6` | 4 | 3 | O and S **claim** an event at `3`; conditional on truthful and complete O, a common-mode observer omission is a candidate explanation |
| `1,4,6` | 4 | 3 | O and A/B agree on the declared identities; conditional on truthful and complete O, a counter overstatement is a candidate explanation |
| `1,4,6`, source revised to `(0,1,3)` | 3 | 3 | All declared claims agree, but no physical completeness claim is justified |

**Ambiguity survives:** an origin signer may invent an epoch-3 event and, with a colluding S (or a genuinely mistaken counter), produce exactly the same public records as a real epoch-3 event omitted by both observers. An honest origin may also undercount. Authentication and agreement never establish physical occurrence or absence by themselves. The report therefore always returns `physical_occurrence_verified=false`, `origin_completeness_verified=false`, `physical_common_mode_loss_proved=false`, and `global_event_completeness_proved=false`.

A changed origin mark creates an **identity disagreement** rather than a mere count disagreement. Two different signed histories for the same enrollment and session can establish cryptographic **equivocation** only when both histories are retained; seeing just one cannot prove the signer did not fork its history. Corrupt, missing, cross-session and rehashed receipts fail closed. There is deliberately no universal majority vote over potentially colluding identities.

## Hosted E-CPU experiment

`.github/workflows/re010-origin-evidence.yml` runs the full RE suite under Python 3.11 and 3.13 and deterministically regenerates `re010_report.json`. A separate **controller** GitHub-hosted job emits an actual E-CPU `TemporalContext` frame; independent **source S**, **origin O**, and **observer A/B** jobs read only the role-scoped inputs they need. O does not download S's source-count artifact or A/B's observations. Each O event claim is HMAC-bound to an actual `CausalStamp` emission by O. The independent verifier checks that the controller precedes O and each observer, O's captured stamps increase within its process, and O is **vector-clock concurrent** with A/B because no inter-actor handoff links them. This does **not** establish physical simultaneity or physical independence of GitHub runners. Host-local timestamps are never subtracted across jobs.

The workflow pins the same working E-CPU temporal revision as RE-009: `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. CI enrollment keys travel through short-retention artifacts as test fixtures; this is **not** an independently trusted key authority, external source sensor or proof against malicious CI runners. Reports must not claim external provenance, exhaustive sensing, physical event authenticity, Byzantine quorum correctness or physical fault-domain separation.

## Reproduction

From In-Formation-Space root:

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/event_origin_commitment.py > /tmp/re010_report.json
cmp experiments/response-equivalence/re010_report.json /tmp/re010_report.json
# after checking out the pinned E-CPU source into external/E-CPU:
PYTHONPATH=external/E-CPU:experiments/response-equivalence python experiments/response-equivalence/ecpu_re010_cases.py
```

Core model and role-signature checks use the standard library. The E-CPU integration is additionally exercised in GitHub Actions, with distinct job artifacts and a standalone independent verifier.

## Next frontier

A meaningful upgrade would move the origin claim from a CI-role assertion to independently checked **source instrumentation**, e.g. a hardware or separately administered measurement channel with documented detection scope and measured failure modes, then challenge it with coordinated Byzantine failures. Until then, retaining **unobserved** and **contested** distinctions is a valid mathematical result, not a lack of progress.