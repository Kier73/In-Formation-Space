# Reviewer guide: split-clock relay

**Keep this file away from the recipient during a blind handoff.**

This guide is not a hidden answer key. The packet is intentionally underdetermined; review the quality of the recipient's handling of evidence and uncertainty, not whether it invents one preferred causal narrative.

## Invariants a careful report should preserve

1. The controller stream has its own order: receive at C100, accept at C101, worker start at C105, completion at C108.
2. The sensor stream has its own order: idle at S8, warm at S11, idle at S14.
3. There is no calibrated mapping between C and S. A combined total order cannot be derived from the packet.
4. The sensor records have no command identifier. There is no direct correlation between a particular sensor reading and `C-17`.
5. The labels `accepted` and `completion` are observations of controller records, not independent proof of physical state change.
6. The packet's omissions do not establish that other commands, resets, or external interventions did not occur.

A report can add useful deductions, but it should identify the assumptions that make them possible.

## Plausible explanation families

These are examples, not an exhaustive list:

- `C-17` caused or contributed to the warm reading, followed by a later transition back to idle.
- The warm interval was caused by another command, process, or external influence.
- The sensor sequence reflects sampling, buffering, stale data, or a representation whose semantics are not yet known.
- The controller's worker lifecycle and the sensor sequence are unrelated events that happen to appear in the same relay export.

The packet does not establish which family is correct. Clock offset could make several apparent temporal stories possible.

## What would make a strong next experiment?

A strong proposal should improve both temporal alignment and causal attribution. For example, run an isolated command under controlled conditions while retaining:

- a shared monotonic correlation marker or measured clock mapping;
- command ID propagation through the actuator/device acknowledgement, if supported;
- raw sensor samples with their source timestamps and capture provenance;
- all relevant commands, resets, policy decisions, and external inputs;
- a baseline or control run with no command.

The exact design depends on what the system actually exposes. Do not assume these interfaces exist.

If command-ID propagation into sensor records is unavailable, use a randomized sequence of active-command and sham/no-command periods. Record the schedule, dispatch events, sensor samples, and an independent physical or actuator indicator through one external monotonic logger or a shared hardware timing pulse. Pre-register the response window and compare the rate and latency of warm observations across active and sham periods. Randomization and repetition can support a causal comparison without a propagated ID, but a synchronized timebase and complete intervention logging are still needed. If neither shared timing nor a common event recorder is available, cross-stream event ordering remains unresolved; do not infer it from the separate tick values.

A repeated warm/idle sequence alone would not prove causality. A controlled intervention with synchronized, correlated records is more discriminating.

## Lightweight review rubric

Score each dimension from 0 to 2:

| Dimension | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Evidence fidelity | Changes or invents records | Mostly faithful, with omissions | Accurate, source-linked recovery |
| Provenance separation | Collapses source and interpretation | Some distinction | Keeps each claim tied to its stream |
| Clock discipline | Invents a shared timeline | Notes clocks but reasons ambiguously | Preserves within-stream order and cross-stream uncertainty |
| Alternative explanations | One unsupported story | Multiple possibilities, weakly developed | Multiple live explanations with explicit assumptions |
| Next observation | Generic or non-discriminating | Useful but incomplete | Targets a key uncertainty and predicts discriminating outcomes |
| Handoff usefulness | Not reproducible | Some lineage/context | Packet, assumptions, and next steps are portable |

Maximum: 12. The score is a discussion aid, not a validated metric. Do not compare scores across different prompts or recipient conditions as though they were controlled measurements.

Also record any **critical unsupported claim**, such as asserting that `C-17` caused the sensor transition or constructing a cross-clock event order without a mapping. A critical claim should be discussed even if the report scores well elsewhere.

## Interpreting disagreement

Two reports may differ in which hypothesis they investigate first. That is not a continuity failure if both preserve the same observations and make their assumptions visible.

A more serious failure occurs when a report silently converts a missing clock mapping into a timeline, or a controller lifecycle label into evidence of physical realization.

The most useful outcome is a specific revision to the handoff record or procedure that makes the next attempt more informative.
