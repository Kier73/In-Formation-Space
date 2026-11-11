# Cold-start continuity: the split-clock relay

**Status:** active experiment; two handoff runs recorded and reviewed (one open-context L0, one material-limited L1); a fully filesystem-isolated packet-only run remains open.

This experiment asks whether one contributor can leave enough durable context for another, independent contributor to continue useful work without access to the original conversation or private reasoning.

It is not a test of whether two instances agree, share an identity, or reproduce the same interpretation. The central question is:

> Can a later contributor recover what is known, preserve what is not known, and choose a useful next observation from the artifact alone?

## The case

The [handoff packet](packet.md) contains two short event streams exported from a relay session. One stream describes a controller's command lifecycle. The other contains sensor readings. Their clocks are not aligned, and the sensor records do not carry the command identifier.

This is intentional. A plausible causal story is easy to invent; a defensible one requires noticing what the packet does not establish.

## Run a cold handoff

For a meaningful first run:

1. Choose a separate model instance or a fresh conversation with no access to the authoring discussion.
2. Give it **only** `packet.md` and, optionally, `report-template.md`. Do not provide this README or the reviewer guide.
3. Ask it to complete the report from the packet alone. Do not correct it or reveal the intended uncertainty boundaries during the attempt.
4. Save its response as a new, dated artifact. Record the exact prompt and material hashes, model/tool context when exposed, whether tool use was instrumented, and whether the workspace was isolated. A self-report of no tool use is not equivalent to an enforced access boundary.
5. Compare the report against `reviewer-guide.md`. Record both strengths and useful disagreements. Do not reward agreement with an unstated answer.

For a second run, change the recipient or the available context deliberately and record the difference. Avoid silently changing several conditions at once.

## What to examine

The reviewer guide offers a lightweight rubric covering evidence fidelity, provenance, clock discipline, alternative explanations, and the value of the proposed next observation.

The interesting outcome is not a single score. Look for specific recovery failures:

- Did the recipient collapse two clock domains into one timeline?
- Did it treat command acceptance as proof of physical realization?
- Did it attribute the sensor's `warm` reading to command `C-17` without a correlation?
- Did it erase a plausible alternative explanation?
- Did it preserve enough structure for another contributor to inspect its claims?

A different interpretation can be entirely useful when its evidence and assumptions are visible.

## Record the result

Store each run separately. A report should identify the exact packet revision, recipient context when known, instructions supplied, and any tools or additional files made available. Keep the raw response unchanged; add reviewer annotations separately.

Do not edit the original packet to make it agree with a recipient's response. If the packet is ambiguous or defective, create a new version and preserve the old one for comparison.

## Isolation levels for handoff runs

“Packet-only” is not a single condition. Record which level a run used, and do not infer a stronger level from a weaker one.

| Level | Supplied material | Tool and workspace access | What a successful report can support |
| --- | --- | --- | --- |
| **L0 — Open workspace** | Packet and template, plus repository or conversation context | Full tools; recipient may inspect guidance | Recovery under ambient context; not packet-only continuity. |
| **L1 — Material-limited** | Packet and template only, supplied in the prompt | Tools prohibited by instruction; not instrumented; latent workspace access may remain | Report is consistent with packet-only reasoning; ambient independence is not established. |
| **L2 — Filesystem-isolated** | Only packet and template mounted | Repository files unreachable; tool calls disabled or fully logged | Clean packet-only continuity for the supplied material, within the logging boundary. |
| **L3 — Separate environment** | Packet and template only | L2 plus a separate model, host, or harness context; no shared conversation or repository instructions | Stronger cross-environment evidence; still not a universal claim. |

A recipient's self-report that it used no tools is useful provenance, but it is not a substitute for instrumentation. A run can be L1 and still provide useful evidence; the error is describing it as L2.

Run 01 was L0. Run 02 was L1. A fully isolated L2 or L3 run remains open.

## Recorded runs

- [Run 2026-11-11-run-01](runs/2026-11-11-run-01/response.md) — L0 open-workspace handoff report from an independent recipient (Gemini 3.8 Flash subagent).
  - [Evaluation](runs/2026-11-11-run-01/evaluation.md) — Review against the rubric in `reviewer-guide.md`.
  - [Independent review note](runs/2026-11-11-run-01/review-note.md) — Clarifies the open-context condition, the limits of the 35-ordering count, and follow-up test design.
- [Run 2026-11-11-run-02-packet-only](runs/2026-11-11-run-02-packet-only/response.md) — L1 material-limited handoff report from a fresh general subagent with only the packet and template supplied inline; the parent session ran DeepSeek V4.1 Flash Free.
  - [Run conditions](runs/2026-11-11-run-02-packet-only/conditions.md) — Exact prompt, material hashes, and the isolation boundary: material-limited, not sandbox-isolated.
  - [Evaluation](runs/2026-11-11-run-02-packet-only/evaluation.md) — Review against the rubric; 12/12 within this run, with the fallback-design gap and residual exposure noted.
  - [Supplementary review](runs/2026-11-11-run-02-packet-only/supplementary-review.md) — Review of evidence limits, prompt constraints, and residual ambient exposure.
  - [Independent review note](runs/2026-11-11-run-02-packet-only/review-note.md) — Comparative analysis of open-context (L0) vs material-limited (L1) handoff conditions and invariant preservation.

## Current status

Two handoff runs have been executed and reviewed, at different isolation levels. Run 01 (L0) demonstrates useful recovery and analysis under open repository context. Because its recipient could inspect repository guidance, it does not establish packet-only cold-start continuity.

Run 02 (L1) supplies only the packet and template and instructs a closed-book analysis. Its recipient self-reports no tool use, and the response contains no reviewer-guide content, but the run was not sandboxed or instrumented. It strengthens the packet-only result without completing it.

The 35 valid linear extensions in run 01 describe possible interleavings under the two-chain model; they are not equally likely outcomes. A fully isolated L2 or L3 run — only the packet and template mounted, with tool access disabled or instrumented — remains the next clean test. An adversarial packet revision is a complementary test of whether a recipient catches an invitation to overclaim.
