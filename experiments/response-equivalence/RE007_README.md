# RE-007 — Partial observation, delayed evidence and active response discrimination

**Research question:** if two observers share no global clock and their sensors can miss or delay evidence, can active probes still reconstruct an observable generating law without treating absence of observation as absence of an event?

**Status:** bounded exact synthetic model; no physical sensors, complete environmental surveillance, externally trusted signatures, universal semantic distance or proof of physical causation. The hosted workflow separately exercises genuine pinned E-CPU temporal stamps, not E-CPU peer transport or physical host independence.

## Results and distinct claims

This extends [RE-006](RE006_README.md)'s conditional exclusion audit, [Trial 08](../description-to-realization/trials/trial-08-intervention-aware-attention/README.md)'s state-changing attention and [VGI Build 15](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/main/theory_development/build_15/BUILD_15.md)'s clock-local observational geometry.

Three finite laws (`quiet`, `transient`, `coupled`) share the same instantaneous snapshot and unprepared response (all zero). The `transient` and `coupled` laws contain an external event between snapshot instants 0 and 2; the event is compensated before the second sample. Thus sampled traces `(0,0,0)` at instants `(0,2,4)` cannot establish that no event occurred. Even sampling every declared coordinate does **not** prove that no event was missed outside the model's represented time/event domain.

A `prime` action changes an internal excitation flag without identifying any law by itself. A subsequent `resonance` read then outputs `0`, `1`, or `2`, respectively. An alternative `deep` observer can distinguish the laws non-invasively but at higher observation cost. The words *resonance* and *deep* are abstract fixture readouts, **not acoustic vibrations or physical frequencies**.

The bounded planner enumerates finite adaptive decision trees using exact integer observation and intervention costs. It minimizes *worst-case* additive cost along each path, accounting for adversarial dropped readings up to a **supplied finite loss budget**. `prime` is modeled as a reliably acknowledged state change, not a fallible actuation. The query is fixed to the **original generating-law identity**, not the post-probe world state.

| Assumptions / policy objective | Action strategy | Worst observation cost | Worst intervention cost | Guarantee |
| --- | --- | ---: | ---: | --- |
| At most one dropped sensor result, minimize observation cost | `prime` then `resonance`, retry if needed | **3** | **1** | Within the 3-law model only |
| At most one dropped result, prioritize no intervention | `deep`, retry if needed | **8** | **0** | Within the 3-law model only |
| Arbitrarily many dropped results | No finite guaranteed identification | — | — | **None** |
| Only sparse passive snapshots and event-presence archive | Two laws remain observationally equivalent | — | — | **None** |

The planner does **not** infer a statistical packet-loss rate or probabilities. The finite-dropout budget, sensor-response truth table, action receipt reliability, candidate catalogue completeness and probe costs are assumptions, not facts learned from the environment. Lower cost can mean a deliberately state-altering strategy.

## Delayed evidence

A sensor request binds `session`, unique `request_id`, `probe` and **capture revision**. A pending receipt contains **no measurement**. A completion can be `returned`, `dropped`, or `refused`; dropped/refused cannot carry zero or any other value. The late response is interpreted against its **capture revision**, never the state at delivery time.

The deliberately discriminating case is a `resonance` reading captured **before** `prime`, returning zero **after** `prime` occurred. A fresh reading captured after `prime` returns 1 for the `transient` fixture. Mistaking the late zero for a post-prime sample would falsely reject the generating law. HMAC binds the reply to the request and temporal evidence. It authenticates possession of a role key *as distributed within this CI fixture*, **not** an external sensor or physical event.

## Cross-host evidence and limitations

Workflow `.github/workflows/re007-partial-observation.yml` uses the already verified E-CPU temporal revision `c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65`. A controller job issues the original request and stamps it using genuine `TemporalContext`; a separate sensor job merges that causal stamp, records the early capture, applies `prime`, delivers the late response and captures/delivers a later response; a separate verifier job reconstructs exact source→capture→prime→delivery→new capture→new delivery precedence using `CausalStamp.relation()`. Its only provenance is fixture-controlled GitHub Actions artifact exchange, a CI-shared ephemeral HMAC enrollment key, and the records' typed E-CPU stamps.

The verifier **does not** infer an across-host elapsed duration, physical simultaneity, physical event attribution, physical independence, or the absence of unobserved disturbances. HMAC + SHA-256 are not physical identity attestations. The synthetic plant law is selected by the fixture; the host workflow does not interrogate an unknown real-world system.

## Reproduce

```bash
python -m unittest discover -s experiments/response-equivalence -p 'test_*.py' -v
python experiments/response-equivalence/partial_observation.py > /tmp/re007_report.json
cmp experiments/response-equivalence/re007_report.json /tmp/re007_report.json

# Optional, after the workflow's pinned E-CPU checkout:
PYTHONPATH=external/E-CPU:experiments/response-equivalence \
  python experiments/response-equivalence/ecpu_re007_cases.py
```

## What this tells us about VGI / E-CPU

The measurement geometry is observer-, probe-, and *capture-state*-relative. A zero sample or similar normalized temporal motif need not correspond to the absence of a generating event. Active intention can change which distinctions are visible, but its mutating effect belongs in the evidence trail. A structural-memory description should therefore retain the observation request, capture revision, reported value or no-value status, admission context, causal relation and declared completeness assumptions, rather than collapsing them into a single derived state.

**Next falsifiable question:** how can a real monitoring source produce evidence supporting a finite bound on missed events or measurement dropout, instead of supplying that bound as a fixture premise? This might require hardware-backed counters, loss-detecting sequence numbers, independent observer overlap, explicitly audited coverage gaps, and signed source logs, none of which alone establishes universal completeness.
