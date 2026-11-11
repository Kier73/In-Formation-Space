# Review note: cold-start run 2026-11-11-run-01

**Purpose:** Add an independent methodological reading of the first recorded relay run. This note supplements the run artifacts; it does not replace or silently edit them.

**Materials inspected:** `packet.md`, `response.md`, `evaluation.md`, and `reviewer-guide.md`, as present on `main` at the time of review.

## What the run demonstrates

The response successfully reconstructs the two local event chains, preserves the lack of a calibrated clock relationship, and distinguishes controller lifecycle labels from verified physical actuation. It proposes multiple explanations and a concrete intervention with a null phase and an active phase.

The response also adds a useful mathematical representation: treating each local stream as an ordered chain and the combined record as a partially ordered set. Given only the two within-stream orders, the number of possible interleavings is

\[
\binom{4+3}{4}=35.
\]

That count is correct under the stated model: four controller events and three sensor events, with no cross-stream ordering constraints.

## Important limits on the conclusions

### 1. This was not a strictly blind handoff

The response metadata says that repository guidelines were inspected in read-only mode. The evaluation itself notes that a recipient with workspace access may discover the reviewer guide and other repository files.

Therefore this run should be described as an **open-context handoff** (or a handoff with possible rubric exposure), not a blind or double-blind test. It still provides evidence that a separate instance could produce a useful analysis from the packet, but it cannot isolate what the packet alone enabled.

For a true packet-only trial, use a fresh isolated directory or branch/worktree containing exactly the packet, the report template, and the explicit task prompt. Do not mount the repository root. Record the file manifest and hashes supplied to the recipient.

### 2. Thirty-five interleavings are not thirty-five equally likely explanations

The count of 35 is a combinatorial count of linear extensions of the two-chain partial order. It does not imply that each ordering is equally likely, nor that one proposed causal ordering has probability 1/35.

No probability distribution over clock offset, clock rate, event generation, or capture-window selection was supplied. The report's phrase that one particular ordering is "1 of 35" is correct as a count-membership statement, but its accompanying "calibration" language should not be read as a probability or confidence estimate.

A safe formulation is: **35 total orders are consistent with the retained within-stream order constraints; the packet supplies no basis for assigning probabilities to them.**

### 3. The affine clock model is an assumption, not a measured relationship

Writing \(T_S=\alpha T_C+\beta\) is a useful idealized model if both clocks are monotonic and their rates are constant over the interval. The packet does not establish those conditions. Real clocks may drift, reset, wrap, pause, or be transformed by buffering and export processes.

The report correctly identifies the absence of a mapping, but the affine parameterization should be labelled as a simplifying model. Without the affine assumption, the safe conclusion remains simply that cross-stream ordering is unknown.

### 4. A positive intervention result needs controls before it establishes causality

A shared strobe can establish a clock correspondence or synchronization event, but a coincident warm reading after a command does not alone prove that the command caused the state change. A causal claim needs an intervention design that controls alternative inputs, establishes the actuator-to-sensor path, and includes repeated active and null trials where practical.

Similarly, observing a warm reading during a null phase weakens a simple command-only explanation, but does not by itself distinguish autonomous cycling, external intervention, replay, or sensor artifact.

The proposed experiment is a good direction. Its outcome table should be read as hypothesis-updating guidance, not as a set of logically guaranteed falsifications unless the corresponding controls are actually established.

## Suggested revised interpretation of the run

- **Evidence fidelity:** strong on the retained records.
- **Within-stream ordering:** correctly recovered, subject to the capture notes' stated ordering.
- **Cross-stream ordering:** correctly left unresolved; the count of 35 linear extensions is valid under the two-chain model.
- **Causal attribution:** appropriately unresolved.
- **Experiment design:** promising, but some predicted outcomes are stated more strongly than the proposed controls warrant.
- **Handoff condition:** useful open-context handoff; not a packet-only blind trial.

The original evaluator's 12/12 score is its own assessment. This review does not endorse the score as a validated measurement. In particular, the clock-discipline dimension should distinguish a correct combinatorial count from unsupported probability calibration, and the handoff dimension should account for possible access to repository guidance.

## Next experiment: two-condition handoff

Run two recipients under separately recorded conditions:

**Condition A — packet-only**
- Isolated workspace containing only `packet.md` and `report-template.md`.
- Supply the task prompt verbatim and record its hash.
- No network, repository, or additional file access if the environment allows.

**Condition B — repository-open**
- Same packet and task prompt, but repository browsing is allowed.
- Record which additional files the recipient accessed, if the environment exposes that information.

Compare the reports for:
- observations recovered from the packet;
- assumptions imported from outside it;
- unsupported causal or temporal claims;
- novel useful deductions;
- next-experiment quality.

Do not assume that a difference between A and B is caused only by the extra files unless other conditions are held constant. The two reports need not agree to be useful.

## Further technical checks exposed by this review

The current envelope validator is a helpful standard-library starting point. Before treating it as equivalent to the JSON Schema, test and document its boundary conditions:

- RFC 3339 `date-time` values require a timezone; Python's `fromisoformat` also accepts naive datetimes.
- Unsupported digest algorithms currently produce no computed digest; the CLI should report an explicit unsupported-algorithm result rather than leaving the record looking simply valid.
- Digest verification currently covers only inline `payload.value`, not referenced payload bytes. The CLI should say that a referenced payload was not checked.
- Structural validation should be tested against the JSON Schema with shared positive and negative fixtures, rather than assumed equivalent because both implement some of the same constraints.

These are candidate follow-up fixes, not claims that the existing tool is unusable.

## Closing observation

The first run produced more than a handoff report: it exposed a distinction between **continuity under shared workspace access** and **continuity from a deliberately minimal record**. Those are different capabilities and deserve separate experiments.

Keep the original run intact. Future contributors should be able to inspect both its useful work and the limits discovered afterward.
