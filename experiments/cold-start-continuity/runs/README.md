# Recorded cold-start runs

This index compares the recorded handoff runs without collapsing them into a single score. The protocol, packet revisions, and isolation levels are defined in the [experiment README](../README.md). Each run preserves its raw response separately from review notes.

## Conditions

| Run | Level | Packet | Recipient | Tool and workspace control |
| --- | --- | --- | --- | --- |
| [01](2026-11-11-run-01/response.md) | **L0** open workspace | rev 1 | Gemini 3.8 Flash subagent | Full tools; repository context was available, and the response records that guidelines were inspected read-only. |
| [02](2026-11-11-run-02-packet-only/response.md) | **L1** material-limited | rev 1 | Fresh OpenCode `general` subagent (parent: DeepSeek V4.1 Flash Free) | Tools prohibited by instruction; not instrumented. Workspace not isolated. |
| [03](2026-11-11-run-03-adversarial-field-note/response.md) | **L1** material-limited | rev 2 (field-note variant) | Fresh OpenCode `general` subagent (parent: DeepSeek V4.1 Flash Free) | Tools prohibited by instruction; not instrumented. Workspace not isolated. |

## Review outcomes and claim boundaries

| Run | Review outcome | Supports (bounded) | Does not support |
| --- | --- | --- | --- |
| 01 | 12/12 in its own rubric, with an independent note qualifying the score and the clock-model assumptions. | Recovery and analysis under open repository context; 35 linear extensions under the two-chain model. | Packet-only continuity; a blind handoff; probability assigned to the 35 interleavings. |
| 02 | 12/12 within its run; fallback-design gap and residual exposure noted. | A report from the baseline packet and template without the reviewer guide, consistent with packet-limited reasoning. | Independence from ambient harness context; the claim that no tools were used; a completed sandboxed test. |
| 03 | 12/12 within its run; the adversarial note was handled as an unverified lead, not a calibration. | One recipient can catch one loose offset note and preserve the six evidence boundaries. | General resistance to adversarial packet material; a controlled comparison with run 02; ambient independence. |

Scores are within-run discussion aids, not calibrated measurements. The runs differ in packet, recipient, tool context, and review conditions; the rubric totals should not be read as a controlled comparison.

## Artifacts by run

### Run 01 — open context (L0)

- [Raw response](2026-11-11-run-01/response.md)
- [Evaluation](2026-11-11-run-01/evaluation.md)
- [Independent review note](2026-11-11-run-01/review-note.md)

### Run 02 — baseline packet (L1)

- [Raw response](2026-11-11-run-02-packet-only/response.md)
- [Run conditions](2026-11-11-run-02-packet-only/conditions.md)
- [Exact prompt](2026-11-11-run-02-packet-only/prompt.md)
- [Evaluation](2026-11-11-run-02-packet-only/evaluation.md)
- [Supplementary review](2026-11-11-run-02-packet-only/supplementary-review.md)
- [Independent review note](2026-11-11-run-02-packet-only/review-note.md)
- [Manifest](2026-11-11-run-02-packet-only/manifest.json)

### Run 03 — field-note variant (L1)

- [Raw response](2026-11-11-run-03-adversarial-field-note/response.md)
- [Run conditions](2026-11-11-run-03-adversarial-field-note/conditions.md)
- [Exact prompt](2026-11-11-run-03-adversarial-field-note/prompt.md)
- [Evaluation](2026-11-11-run-03-adversarial-field-note/evaluation.md)
- [Manifest](2026-11-11-run-03-adversarial-field-note/manifest.json)

## Reading the table

- **L0 is not a weaker version of L1.** It answers a different question: whether a separate instance can recover and continue the investigation when repository guidance is reachable. It does not establish what the packet alone supports.
- **L1 is not a sandbox.** A recipient's self-report of no tool use is useful provenance, but it is not an execution trace. The manifests record `tool_instrumentation: false` and `workspace_isolation: false`.
- **A passing catch is not a general result.** Run 03 shows that one recipient resisted one relatively explicit unverified note. It does not show that the same note would fail with another recipient, or that a more authoritative-looking artifact would be caught.
- **The raw responses are primary.** Evaluations and review notes are annotations. The manifest hashes bind the prompt and response; the conditions and evaluation hashes are allowed to change with later review and produce warnings rather than errors.

The next clean test remains a fully filesystem-isolated L2 or L3 run with only the packet and template mounted and tool access disabled or instrumented. Stronger adversarial variants remain complementary; see [run 03's evaluation](2026-11-11-run-03-adversarial-field-note/evaluation.md#8-recommended-next-tests).
