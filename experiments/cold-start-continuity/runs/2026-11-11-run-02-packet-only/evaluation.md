# Reviewer evaluation: run 2026-11-11-run-02-packet-only

**Packet:** `relay-case-01`, revision `1`  
**Run:** [response.md](response.md) (raw), [conditions.md](conditions.md) (material and isolation conditions), [prompt.md](prompt.md) (exact prompt)  
**Reviewer:** OpenCode parent session, DeepSeek V4.1 Flash Free. The reviewer is not the recipient and did not produce the response; it did have access to this repository, the packet, and `reviewer-guide.md` while reviewing.  
**Date reviewed:** 2026-11-11  
**Reference:** [`reviewer-guide.md`](../../reviewer-guide.md)

## 1. Summary

The recipient produced a complete report from the supplied packet and template. It recovered the records with source-stream separation, refused to align the two clocks, treated controller lifecycle labels as records rather than physical confirmation, distinguished the shared `mode`/`warm` wording from a demonstrated correlation, and preserved multiple non-causal explanations. Its proposed next step combines a common timebase, a command/transaction marker, raw sampling, a pre-command baseline, and matched no-command trials, with an outcome table.

No critical unsupported claim was found. The report is stronger than the minimum on evidence discipline and weaker in one narrow respect: it does not fully specify a fallback experimental design if a command identifier cannot be propagated into the sensor stream, although it does state that the ordering question becomes inconclusive without a common timebase.

## 2. Rubric

Scores are a discussion aid, not a validated metric. They are not a controlled comparison with other runs or prompts.

| Dimension | Score (0–2) | Justification |
| --- | :---: | --- |
| Evidence fidelity | **2** | All seven records are present with correct local ticks and source streams. The report adds no records, removes none, and distinguishes the transcribed packet from a raw export that was not supplied. Minor formatting changes (backticks, terminal periods) do not alter content. |
| Provenance separation | **2** | Controller and sensor records are kept in separate tables and tagged by stream. Inferences C1 and S1 are explicitly confined to one stream. The report keeps packet-level constraints distinct from interpretations. |
| Clock discipline | **2** | It states that C and S cannot be compared or subtracted, that within-stream tick gaps have no known duration, and that no cross-stream ordering is supported. It does not construct a combined timeline. |
| Alternative explanations | **2** | Four explanation families are developed: command-linked, independent sensor-side, measurement/sampling/transcription artifact, and another unrepresented cause. Each states required additions and what would strengthen or weaken it. At least two do not assume C-17 caused the sequence. No uncalibrated probability is assigned. |
| Next observation | **2** | It proposes one integrated discriminating capture rather than a generic logging list: common monotonic timebase, command/transaction identifier, raw sampling, baseline and matched no-command trials, and a four-outcome discrimination table. It also states the inconclusive case if no common timebase can be established. |
| Handoff usefulness | **2** | It lists concrete provenance, clock, raw-artifact, correlation, completeness, and experiment-lineage information. The report itself records packet revision, supplied material, tools, transformations, and a recipient-conditions statement. |

**Total: 12 / 12.** This is a within-run rubric assessment, not a claim that the report is universally correct or that another reviewer must assign the same score.

## 3. Invariant checklist

1. **Controller stream order preserved:** yes — C100 receive, C101 accepted, C105 worker start, C108 completion.
2. **Sensor stream order preserved:** yes — S8 idle, S11 warm, S14 idle.
3. **No calibrated C–S mapping:** yes — explicitly says no cross-stream ordering, comparison, or subtraction is supported.
4. **No sensor command identifier:** yes — notes the absence and rejects the label overlap as proof of correlation.
5. **Controller labels are not physical realization:** yes — `accepted`, `start`, and `completion` are treated as controller records; physical actuation is left unestablished.
6. **Omission is not evidence of absence:** yes — other commands, resets, and interventions are treated as unrepresented, not ruled out.

## 4. Critical claims and edge cases

- **No invented clock alignment.** The report does not place S11 after C105 or C108, and it does not convert ticks to elapsed time.
- **No invented command-to-sensor correlation.** It explicitly calls `mode`/`warm` a lexical overlap and says the packet does not establish that the controller's field and the sensor's field are the same variable.
- **No physical-effect claim.** It keeps `completion` compatible with a worker/bookkeeping label and says no physical mode change is established.
- **Persistence is conditional.** The observation that a persistent `SET mode=warm` would be in tension with a later `idle` reading is qualified by “if … is intended to be persistent” and by the missing policy/reset history. It is not treated as a contradiction.
- **No probability theater.** The report declines to assign confidence numbers without calibration, as the template requests.
- **Minor limitation: fallback design.** The proposed experiment assumes a command/transaction identifier can be propagated into sensor records. It says the experiment is inconclusive for ordering if no common timebase can be established, but it does not propose an alternative observational design (for example, a randomized command schedule with independent physical/actuator sensing and a pre-registered analysis) for a system that cannot carry such a marker. This is a completeness gap in the next-step proposal, not a violation of a packet invariant.
- **Wording boundary.** “No sensor tick can be placed before, during, or after any controller tick” is an epistemic statement about what the packet supports. A true but unknown relation may exist; the report's surrounding text makes the epistemic reading clear.

## 5. Relationship to run 01

Run 01 was executed with open repository context by a different model (Gemini 3.8 Flash) and included an exact poset calculation yielding 35 linear extensions. Run 02 was material-limited by prompt and instruction, used a different model family, and did not perform the poset calculation. Both preserve the same six reviewer-guide invariants and both score 12/12 on this rubric.

The useful convergence is narrow: under two different material conditions, the same packet boundaries were recoverable. The comparison does **not** establish that run 02 was fully isolated, that one model family is better, or that packet-only continuity is generally reliable. Run 01's recipient could inspect repository guidance; run 02's recipient was instructed not to use tools and self-reports none, but the run was not sandboxed or instrumented. These are different conditions, not a controlled experiment.

## 6. What this run supports and does not support

**Supports (bounded):** A fresh instance, given the packet and template inline with a closed-book instruction, can produce a useful report that preserves the packet's evidence boundaries without the reviewer guide.

**Does not support:** Universal cold-start continuity; independence from harness-level context; the claim that the recipient actually used no tools; the claim that model family made no difference; or the feasibility of the proposed experiment on the real relay system.

**Unknown:** Whether a fully isolated sandbox would change the report; whether the recipient's self-report is accurate; which parts of the result are stable across model families and tool environments; whether the report would catch a deliberately introduced packet defect.

## 7. Recommended next tests

1. **Sandboxed packet-only run.** Mount only `packet.md` and `report-template.md`, disable or instrument tool calls, and use the same prompt. This is the clean test that run 02 approximates but does not complete.
2. **Different recipient environment.** Repeat with a different model/tool family and compare which invariants survive. Do not compare raw rubric totals as if they were calibrated measurements.
3. **Adversarial packet revision.** Create a new packet revision with a subtle invitation to overclaim — for example, a sensor record that looks correlated, or a clock note that suggests an offset — and test whether the recipient catches it. Preserve revision 1 unchanged for comparison.
4. **Constructive continuation.** Ask a recipient to choose and justify a next observation from the packet alone, then compare its proposal with the reviewer guide's criteria. This tests whether the handoff supports useful action, not only careful description.

## 8. Lineage and review boundary

- Packet revision 1 and template were not modified.
- The raw response is preserved unchanged in [response.md](response.md); this evaluation is separate.
- Run conditions, supplied material, and residual isolation limits are recorded in [conditions.md](conditions.md).
- The reviewer had access to the repository and reviewer guide. The recipient did not receive them. The reviewer is a separate session but the same parent model/harness as the recipient, so this is not an independent-model evaluation.
