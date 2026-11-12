# Bridge: Evidence-gated observation path

**Status:** experimental protocol model.  
**Purpose:** preserve the difference between selecting an observation, sending a request, receiver admission, returned raw data, interpretation, and query resolution.

## Why this bridge exists

Trials 04–06 choose which observations would be useful. They do not execute those observations. A real communication path has additional stages, and collapsing them creates false evidence:

- A plan is not a dispatch.
- A successful dispatch is not receiver admission.
- Receiver admission is not evidence authorization when a source quorum or authority policy is required.
- Quorum authorization is not application of the representative value to receiver state.
- A timeout or rejection is not a negative sensor reading.
- A raw return is not yet an interpretation.
- A query determined over a supplied hypothesis set is not automatically a universal fact about the external world.

## Lifecycle

    planned -> dispatched -> admitted -> returned -> interpreted -> query_determined
                                    |            |
                                    |            +-> evidence_authorized -> applied
                                                           |                   |
                                                           v                   v
                                                   sender_ack_progress -> sender_acknowledged (optional)
                                    |                         |
                                    +-> no_result             +-> evidence_refused
         |          |           |           |              | 
         v          v           v           v              +-> continued -> next attempt
    dispatch_failed  rejected  no_result  returned_unadmitted  unresolved
                           (unadmitted return and other failures are terminal)

Each request attempt is append-only. `admitted` records receiver-side intake; `evidence_authorized` records a separate consensus/authority decision; `applied` records verified receiver-side state mutation; and optional `sender_ack_progress` / `sender_acknowledged` records partial and complete sender-side ACK processing. A progress event is cumulative and names the exact sequences still pending; later calls can complete the same path without erasing the earlier partial receipt. An intent can require the authority gate, then an `applied` receipt, and optionally sender-side ACK processing after that. `sender_ack_required` implies `application_required`, which itself implies authority. Interpretation cannot proceed until every declared gate has been recorded. A direct one-receiver path can leave all three requirements false. An interpreted observation can end in `query_determined`, `unresolved`, or `continued`; `continued` records which next observation the adaptive policy selected and closes the current request attempt before a new attempt begins. Failure paths are terminal and do not silently become observations. A payload that returns without an admission receipt is preserved as `returned_unadmitted` and cannot advance to interpretation within that attempt.

## Live E-CPU integration

The pinned E-CPU runtime integration passed in [GitHub Actions run 217](https://github.com/Kier73/In-Formation-Space/actions/runs/43118348220); the expanded temporal binding and conservative latency analysis then passed in [run 242](https://github.com/Kier73/In-Formation-Space/actions/runs/43121611521), with 251 tests across the repository workflow. The [run 242 encounter receipt](results/live-ecpu-temporal-analysis-run-242.json) records the exact repository revisions, suite counts, two live runtime cases, and clock-interpretation limits. The successful path now exercises `planned → dispatched → admitted → returned → evidence_authorized → applied → sender_acknowledged`, including real durable channels, quorum finalization, VM commit/checkpoint recovery, sender pending-set clearance, and portable path validation after the final ACK. The conflicting-source case ends in `evidence_refused` without VM mutation. The [run 217 receipt](results/live-ecpu-integration-run-217.json) records the exact E-CPU and In-Formation-Space commits and the full suite summary; the earlier [run 172 receipt](results/live-ecpu-integration-run-172.json) preserves the predecessor integration boundary.

## E-CPU coordinator adapter

The [E-CPU gated adapter](ecpu_gated_adapter.py) is a dependency-injected bridge over the existing `GatedObservationCoordinator`. It does not import or reimplement E-CPU. It records a finalized decision only after checking the coordinator's policy, finalized status, evidence-link source set, and representative. After `commit_event()`, it checks the durable applied marker, complete receiver consumption, absence of outstanding commit intents, the VM's exact idempotence receipt, and actual register readback before recording `applied`. It then saves a final E-CPU checkpoint and records its digest.

The adapter verifies receiver-side ACK emission through the completed consume path. The separate `record_sender_acknowledgements()` operation calls E-CPU's sender-side `process_acks()`. If only some event sequences have been cleared, it appends `sender_ack_progress` with the cumulative acknowledged set and exact missing set. A later call merges new removals and appends `sender_acknowledged` only when every event sequence is absent from sender pending state. A path may intentionally stop at `applied` when sender confirmation is not required. Nor does it create transport or Encounter Envelope evidence on its own: dispatch, receiver-intake, and raw-return artifacts must be supplied by the surrounding host adapter.

## Explicit authority and application gates

An intent may set `authority_required=true` when a source quorum, consensus policy, or other evidence-authorization decision must occur after the raw return. The path must then record `evidence_authorized` or `evidence_refused` before interpretation. An intent may additionally set `application_required=true` when the authorized representative must be applied to receiver state; this implies authority is required, and an `applied` receipt must precede interpretation. An application or authorization failure is terminal and cannot be interpreted as a negative measurement.

For the E-CPU-specific mapping of transport enqueue, receiver evidence intake, quorum finalization, VM commit/ACK, and later Ground realization, see the [E-CPU adapter map](../adaptive-attention-execution/ecpu-adapter-map.md).

## Temporal checkpoint analysis

[`ecpu_temporal_binding.py`](ecpu_temporal_binding.py) binds each observation-path event to one typed E-CPU `TemporalFrame` and preserves E-CPU's interval deltas. [`analyze_temporal_binding.py`](analyze_temporal_binding.py) provides a conservative reader over that verified binding. It names each value as elapsed time between adjacent local frame captures, reports a total only when every adjacent monotonic interval is comparable and measured, and preserves wall-clock, causal, scheduler, event, chemical, and phase fields separately. A missing monotonic interval is not treated as zero. The [analysis schema](temporal-path-analysis.schema.json) defines the portable report shape.

These are checkpoint-to-checkpoint measurements, not isolated operation runtimes. For example, `dispatched → admitted` includes the interval between the adapter's local capture points after those stages; it is not a CPU-time profile of `ingest_available()` alone.

## Operation spans and empirical cost profiles

[`operation_spans.py`](operation_spans.py) adds a separate measurement boundary around one supplied synchronous callable. The recorder samples a local monotonic clock immediately before and after the invocation, preserves the callable's exact result or re-raises its original exception, and records successful and raised calls separately. A clock failure does not prevent the operation from running. A regressed clock is retained as a regressed span with no duration.

This is intentionally distinct from the temporal checkpoint trace above. A span around `GatedObservationCoordinator.finalize_event()`, for example, measures that synchronous call boundary (including any blocking inside it); it does not claim to measure CPU time or to isolate the call's internal sub-operations. The span carries a clock actor and segment identity so measurements from different processes or clock lifetimes cannot silently be combined.

`build_operation_cost_profiles()` summarizes repeated spans by operation, clock actor, clock segment, and outcome. It reports sample counts, median, nearest-rank p90/p95, and range. Regressed spans do not enter duration statistics; raised calls remain a separate outcome partition. A minimum-sample threshold controls only whether a partition is labelled `insufficient_samples` or `descriptive_only`. Even above the threshold, the report's `policy_effect` is always `none`: profiles are evidence for later review, not automatic adaptive-attention costs.

The [operation-span schema](operation-span.schema.json) and [cost-profile schema](operation-cost-profiles.schema.json) define the portable artifacts. [`test_operation_spans.py`](test_operation_spans.py) tests call semantics, failures, clock regression and failure, partitioning, source reconstruction, and schema validity.

Saved artifacts can be analyzed offline and combined as inputs without losing clock boundaries:

```bash
python bridges/observation-path/operation_spans.py \
  --input run-a/operation-spans.json \
  --input run-b/operation-spans.json \
  --minimum-samples 5 \
  --output operation-cost-profiles.json
```

Each input may be a top-level span array or the CI artifact object containing `spans`. Duplicate `(attempt_id, span_id)` identities are rejected so replaying the same artifact cannot inflate sample counts. The CLI validates each source span and independently rebuilds the output profile. Different clock segments remain separate partitions even when they come from the same named operation.

These profiles describe only observed invocations. They do not estimate the cost of a candidate that was never executed, correct for selection bias, or justify changing a policy without a separate validation experiment.

### Live pinned-runtime measurements

The live integration now instruments the actual calls to `ReliableChannel.send()`, `GatedObservationCoordinator.ingest_available()`, `finalize_event()`, `commit_event()`, `save_checkpoint()`, and `process_acks()`. The wrappers sit directly around those calls and retain their synchronous call-boundary scope. They do not replace or emulate E-CPU behavior.

The live CI probe now executes five additional authorized paths in the same pinned E-CPU process, alongside the primary success and conflict cases. It emits 46 spans: 14 sends, seven receiver-intake calls, seven finalizations, six VM commits, six additional checkpoint saves, and six sender ACK polls. With a five-sample threshold, every operation partition reaches `descriptive_only`. The raw spans and independently reconstructed cost profile are uploaded as the `live-ecpu-operation-spans` artifact on the workflow run. These are repeated samples under one controlled CI workload and clock segment, not a stable production benchmark or an adaptive policy input.


## Transition conformance and model revision

The [transition-conformance bridge](transition-conformance.md) closes one gap between Trial 08 planning and actual probe evidence. It compares a completed, admitted, interpreted ObservationPath against one pinned model transition, embedding the source path snapshot and binding the returned Encounter Envelope references and optional before/after state witnesses. Proposal intake reconstructs the record before allowing a transition override candidate.

The record distinguishes `matched`, `outcome_mismatch`, `next_state_mismatch`, `transition_mismatch`, and two outcome-only states where no after-state witness exists. An outcome-only return is never promoted to full transition conformance.

An optional operation span is attached only as performance evidence. Its elapsed nanoseconds, clock actor, and clock segment are preserved; they are not converted into Trial 08 intervention cost.

`TransitionModelRevisionLedger` then records a mismatching observed transition as a proposal. The active model changes only after an explicit `supported` validation result and an explicit activation that creates a new immutable Trial 08 planner document. The transition's existing intervention-cost value is preserved. Digests and validation references are provenance aids, not authentication of referenced artifacts or reviewers.

- [Implementation](transition_conformance.py)
- [Schema](transition-conformance.schema.json)
- [Tests](test_transition_conformance.py)
- [Focused CI](../../.github/workflows/intervention-transition-conformance.yml)

## Repeated transition evidence

The [repeated-transition evidence experiment](transition-evidence.md) aggregates independently reconstructed conformance records by `(probe_id, current_state)`. It retains exact observed outcome/next-state counts, separate outcome-only counts, sample frequencies, and source evidence references. It reports whether one or multiple distinct transitions have been observed without inferring a deterministic or stochastic process.

This is descriptive evidence only: the aggregation does not activate a revised transition model, infer probabilities, or change attention policy. Adaptive sampling bias and unmodelled process/context changes remain open.

- [Implementation](transition_evidence.py)
- [Schema](transition-evidence-summary.schema.json)
- [Tests](test_transition_evidence.py)
- [Focused CI](../../.github/workflows/repeated-transition-evidence.yml)

## Context-stratified transition evidence

The [context-stratified analysis](transition-context-analysis.md) takes repeated conformance records plus optional, attempt-bound context assignments. For each observed context dimension and complete joint context, it compares exact unordered-pair disagreement before partitioning with disagreement within and between strata. Full transition witnesses use the `(outcome, next_state)` pair; outcome-only returns remain visible but never enter the transition-pair denominators.

Unknown context, a dimension not supplied, and an attempt with no assignment remain distinct. A context value is a supplied partition label, not a causal explanation. The report can show that a partition separates or reduces disagreement in the supplied sample; it does not establish hidden-state identity, stochasticity, determinism, future generalization, or a model update. Context digests provide content identity, not source authentication.

- [Implementation](transition_context.py)
- [Schema](transition-context-analysis.schema.json)
- [Tests](test_transition_context.py)
- [Focused CI](../../.github/workflows/contextual-transition-evidence.yml)

## VGI context-attention policy

The [context-attention bridge](context-attention-policy.md) converts repeated attempts from one transition cell into a synthetic VGI observer-space Ground. Context-capture methods become actions, declared values become finite outcome branches, and the pinned VGI minimax planner proposes an AND/OR measurement policy. Existing observed context is represented separately from unknown, not-supplied, and unassigned cells. The report also counts residual `(outcome, next_state)` disagreement among currently context-equivalent full-transition pairs.

This is a plan only: no context observation is dispatched and no source Ground, transition model, or attention policy changes. Declared branches are not probability or exhaustiveness claims; a future out-of-set measurement must be treated as model mismatch.

- [Implementation](context_attention.py)
- [Schema](context-attention-policy.schema.json)
- [Tests](test_context_attention.py)
- [Focused CI](../../.github/workflows/context-attention-policy.yml)
- [Pinned VGI policy planner](https://github.com/Kier73/Virtual-Ground-Interpreter/tree/ac13c1bbd92dfd09f17de51adef7adb2d2088bf6)

## Authorized context-measurement evidence

The [context-measurement evidence bridge](context-measurement-evidence.md) closes the VGI context-attention loop. It creates a planned `ObservationPath` for the exact next `(attempt_id, method_id, dimension)`, then accepts a measurement only after the path is reconstructed through dispatch, admission, returned Encounter Envelope, explicit AUTHORIZED decision, and exact scalar interpretation.

The observed context value must exactly match a declared VGI scenario value. An out-of-set value is a model mismatch and is not coerced or silently admitted. Accepted evidence creates a new immutable context assignment whose `source_ref` binds to a digest of the complete measurement manifest, then rebuilds the context analysis. The original analysis and transition model remain unchanged; a new attention policy must be computed from the updated analysis.

- [Implementation](context_measurement.py)
- [Schema](context-measurement-evidence.schema.json)
- [Tests](test_context_measurement.py)
- [Focused CI](../../.github/workflows/context-measurement-evidence.yml)

## Observation outcomes and information value

The companion [observation-outcome implementation](observation_outcomes.py) records what a candidate observation was expected to distinguish and what outcome was actually observed. It is deliberately separate from the operation-span cost profiler.

A record is keyed by the attempt identity and an explicit observation identity. Its evidence reference/digest and exact prior model are retained. Each hypothesis supplies a prior probability, the outcome predicted by this deterministic observation model, and optionally the Boolean value of one query. The builder independently derives prior entropy, expected posterior entropy, expected information gain (mutual information averaged over every predicted outcome), probability that the observation is expected to resolve the supplied Boolean query, probability and posterior for the one observed outcome, and the signed entropy change on that realized branch.

**Expected information gain is not the same as the entropy change on one realized branch.** A particular outcome can leave a more uncertain posterior than the prior even while the observation has positive expected information gain. The ledger preserves both quantities rather than forcing every individual outcome to appear informative.

A result not predicted by the model is retained as model_mismatch; the builder does not fabricate a posterior or reinterpret it as zero information. Model predictions and query labels remain supplied assumptions, not independently established facts. Evidence references and digests are preserved but are not fetched or authenticated here. This first version handles deterministic partitions; noisy likelihood models and cost-weighted policy selection are intentionally out of scope.

### Build and verify an outcome record

Create a JSON request containing attempt_id, observation_id, evidence_ref, evidence_digest (lowercase SHA-256), model_ref, prior_hypotheses, and observed_outcome, then run:

```bash
python bridges/observation-path/observation_outcomes.py \
  --input observation-request.json \
  --output observation-outcome.json
```

Every hypothesis needs hypothesis_id, prior_probability, and predicted_outcome. Add query_value to every hypothesis to evaluate one Boolean query, or omit it from every hypothesis. The module's validate_observation_outcome() rebuilds all derived values and both digests. The companion JSON Schema checks the portable document shape. Tests include a counterexample where expected information gain is positive while the realized branch increases entropy.

The live E-CPU spans now carry the same explicit observation_id convention in their context in addition to attempt identity. This establishes a correlation field; it does not invent a prior model for E-CPU timing symbols or claim that informational outcomes have already been measured on the live path. A domain-specific hypothesis model must be independently specified before such outcomes can be attached.

## Controlled E-CPU workload matrix

The companion [controlled observation cost–information experiment](../../experiments/observation-cost-information/README.md) varies payload-field size, per-source queue depth, source count/quorum, and synchronized independent receiver intake against the pinned E-CPU runtime. It records actual synchronous spans around send, receiver intake, finalization, commit, each internal checkpoint-save call, and sender ACK processing.

The experiment builds cost profiles separately for each workload condition and separately reports the full queue-drain path versus the target observation's own event. It also records each typed resolver outcome against an explicit deterministic hit/miss fixture model. These information records are not inferred from timing and are not fed into an adaptive policy.

The matrix is a controlled same-host pilot. It does not establish production performance or external sensor truth. See the experiment's [workload definition, reproducibility instructions, and limits](../../experiments/observation-cost-information/README.md).

## Evidence and clocks

Dispatch, receiver admission, raw return, evidence authorization/refusal, optional receiver-state application, interpretation, and query-resolution events can each reference their own receipt or artifact. A returned payload must reference an Encounter Envelope and include its encounter ID, payload digest, and declared canonicalization. The path ledger records those declarations; it does not fetch or authenticate the referenced artifact. The Encounter Envelope validator remains responsible for validating the referenced envelope when it is available.

Clock values are retained only alongside their clock-domain labels. The path model does not subtract or align values from different domains. Unknown timing remains unknown.

## Query resolution boundary

The terminal `query_determined` stage requires a Boolean result, the hypothesis-set digest against which it was derived, and a basis reference. This means the query was resolved relative to that stated hypothesis set and evidence basis. It does not claim that the hypothesis set is exhaustive or that the result is a universal property of the external system.

An adaptive coordinator now uses this ledger for one-request-at-a-time policy execution: [Adaptive Attention Execution](../adaptive-attention-execution/README.md). It records a continuation between attempts, while an outcome outside the predicted policy branches is retained as an unresolved model mismatch.

## VGI partial-aware probe execution

The [VGI partial-attention planner](https://github.com/Kier73/Virtual-Ground-Interpreter/blob/cedcc4540a9d75228cf83aaf21e1ba960fe8a555/virtual_ground_interpreter/vgi/partial_attention.py) scores one currently unknown or ambiguous Ground state/action cell by evaluating explicit counterfactual outcomes. It reports scenario bounds when no calibrated distribution is supplied, and exact expected pair-resolution only when every scenario has an exact rational weight. This bridge reuses that planner; it does not duplicate its scoring or refinement algorithms.

`partial_probe_execution.py` binds the score to:

- the exact source Ground fingerprint and cell record;
- observer actions/channels and the horizon;
- the pinned VGI source revision;
- the cell, every proposed outcome, exact rational scenario weights, and per-scenario score;
- the score summary and a canonical SHA-256 plan/scenario digest.

The digest-bound plan is a proposal reference, not a measurement receipt. The bridge does not execute the probe. A host adapter still has to report dispatch, receiver admission, and an admitted raw return. The actual interpreted `TransitionOutcome` is then compared with the proposal's scenario set. An outcome outside the set is preserved as an `unresolved` model mismatch; it is not mapped to the nearest prediction.

An unresolved VGI mismatch can be handed to the [append-only hypothesis-revision ledger](../hypothesis-revision/README.md) with `attempt.propose_hypothesis_revision(ledger, ...)`. The handoff rechecks that this attempt contains a dispatched, admitted, returned, interpreted, terminal-unresolved sequence with the exact VGI mismatch reason, then carries the Encounter Envelope reference, encounter ID, payload digest, canonicalization, and interpretation reference into a new candidate. It calls the ledger's proposal operation only: the candidate remains proposed, the active hypothesis revision is unchanged, and the VGI Ground is not modified. Validation and activation remain separate explicit operations.

A matched observation changes no Ground by itself. A caller must first record the existing explicit `evidence_authorized` stage (normally through the E-CPU gated adapter); declared application and sender-ACK requirements must also be satisfied before interpretation. `build_ground_revision()` then returns a new VGI Ground value with every available append-only path reference (plan, dispatch, admission, raw return, authorization, optional application/ACK, and interpretation) in its evidence list and a revision entry in Ground metadata. The original Ground remains unchanged, and a stale source fingerprint is rejected.

The update semantics preserve uncertainty:

- an unknown cell may become a singleton known transition from the admitted observation;
- an ambiguous cell keeps every prior alternative and remains ambiguous, even when the new observation matches one of those alternatives;
- the new return increments support count once; it does not silently adjudicate competing alternatives;
- an unauthorized, unadmitted, mismatching, or stale attempt cannot produce a Ground revision.

The module intentionally has no VGI runtime dependency. The interoperability tests import the real VGI implementation from pinned commit `cedcc4540a9d75228cf83aaf21e1ba960fe8a555`; CI checks the cross-repository contract against that exact revision. The bridge's evidence references are retained, not fetched or authenticated by this module. The E-CPU adapter and Encounter Envelope validation remain the relevant trust boundaries.

Reproduce the cross-repository contract test from a checkout with that VGI revision available:

```bash
PYTHONPATH=external/Virtual-Ground-Interpreter/virtual_ground_interpreter python -m unittest discover -s bridges/observation-path -p 'test_partial_probe_execution.py' -v
```

## Stateful partial-attention navigation

`partial_attention_navigator.py` adds a one-probe-at-a-time controller above VGI's existing ranker and the evidence-gated partial-probe execution bridge. It does not implement another scoring rule. The caller supplies:

- the current VGI Ground and observer;
- a `probe_factory(system, observer, cycle_index)` that regenerates explicit counterfactual candidates for the *current* Ground;
- VGI's pinned `rank_partial_probes` callable and its revision;
- the horizon and query label.

`preview()` ranks without opening a request. `begin_next()` binds the highest-ranked candidate to a digest-bound `PartialProbeExecution` and its existing `ObservationPath`. Only one attempt may be active. The host then uses that same path for real dispatch, receiver admission, raw return, and the selected E-CPU authorization/application/ACK gates. The E-CPU adapter can consume `selection.execution.path` directly; no new lifecycle or authority ledger is introduced.

After those gates, `complete_active(actual_transition_outcome, ...)` interprets the actual result. A matching scenario produces a new immutable Ground revision; the navigator adopts that revision and calls the candidate factory again on the next `preview()` / `begin_next()`. This is the adaptive loop: the next candidate ranking is based on the newly observed Ground, not a policy tree computed once against an old model.

A result outside the scenario set leaves Ground unchanged and pauses the navigator in `model_mismatch`. The caller may pass an append-only hypothesis ledger proposal in `hypothesis_proposal`; this still creates only a proposed candidate. Resuming requires an explicit `resume_after_mismatch(probe_factory=...)`, allowing the caller to supply a candidate source updated from separately validated model context.

A terminal non-observation failure can be closed with `finish_terminal_attempt()`. It appends the failed path to navigation history, leaves Ground and hypotheses untouched, and returns the navigator to `ready` so a host may make a new attempt. This includes dispatch failure, receiver rejection, unadmitted return, timeout/no-result, evidence refusal, application failure, and interpretation failure. The next attempt receives a new identity; none of these failure states becomes a negative sensor reading.

The navigator intentionally does **not** dispatch transport or manufacture Encounter Envelopes. A host adapter remains responsible for actual send/intake/return artifacts. It also does not assume scenario probabilities: the VGI ranker preserves exact expectations when exact weights were supplied and otherwise ranks using conservative scenario bounds.

### Minimal cycle

```python
from partial_attention_navigator import PartialAttentionNavigator
from vgi.partial_attention import rank_partial_probes

navigator = PartialAttentionNavigator(
    system, observer, probe_factory, rank_partial_probes, horizon,
    attempt_id_prefix="attention-run",
    query_label="refine the current Ground",
    vgi_revision="cedcc4540a9d75228cf83aaf21e1ba960fe8a555",
)

selection = navigator.begin_next()
attempt = selection.execution

# Host transport records dispatched, admitted, and returned on attempt.path.
# ECPUGatedObservationAdapter records authority, application, and optional ACK
# on this exact same path after its real E-CPU operations have completed.

result = navigator.complete_active(
    actual_transition_outcome,
    actor="domain-interpreter",
    interpretation_ref="interpretations/attempt-0000.json",
)

# On a Ground revision, the next begin_next() regenerates and re-ranks probes
# against navigator.system. On model mismatch, explicitly review and resume.
```

`navigator.to_dict()` preserves the active attempt identity, selected cell, plan/scenario digests, ranked alternatives, append-only path history, and Ground fingerprint. It is a continuity record, not a serialized VGI Ground; the actual Ground remains a separately versioned value.

The cross-repository tests use VGI commit `cedcc4540a9d75228cf83aaf21e1ba960fe8a555`. The navigator itself remains dependency-injected and does not import VGI or E-CPU at module import time.

## Empirical operation costs in partial-attention ranking

`empirical_probe_costs.py` connects the existing operation-span evidence to VGI's exact positive `TransitionProbe.cost` field. The binding is always caller-declared: each probe label is a method ID and maps to one measured `operation_id`, clock actor, and clock segment. The helper then:

1. validates every source span and independently rebuilds the supplied cost profile from those exact span documents;
2. requires a successful operation profile with at least the configured number of measured samples;
3. requires all compared methods to share one monotonic clock actor and segment, and one percentile basis;
4. defaults to the integer `p90_ns` statistic (or permits `p95_ns`), then supplies that duration as an exact `Fraction` nanosecond cost to a copied VGI probe;
5. preserves profile digest, model digest, source span digests, sample count, clock domain, statistic, and measurement scope in the navigator's ranked candidate record.

This is a cost-only connection. Scenario weights and counterfactual outcomes remain VGI inputs; timing does not establish a transition, increase a scenario's probability, or authorize execution. The probe's original cost/object is not mutated. A missing method binding, failed-only profile, under-sampled group, zero-resolution duration, mismatched clock segment, or incomparable actor blocks calibrated ranking rather than falling back to an unmeasured estimate.

All candidates being compared in one model must share the same clock actor and segment. This is stricter than merely sharing units: monotonic timestamps from different processes or boot segments are not assumed comparable. The default p90 is an empirical high-percentile estimate of the supplied synchronous callable boundary, not a worst-case bound, CPU time, or total physical energy. The operation recorder's declared scope includes blocking inside that call and excludes later work; a caller should instrument the whole comparable method boundary when that is the intended cost.

### Connect to the navigator

Build a profile from the measured span artifacts using the existing `operation_spans.py` workflow, then declare explicit operation bindings:

```python
from empirical_probe_costs import (
    EmpiricalProbeCostModel,
    ProbeCostBinding,
)
from partial_attention_navigator import PartialAttentionNavigator

cost_model = EmpiricalProbeCostModel(
    span_documents,
    profile_report,
    (
        ProbeCostBinding(
            "sensor-fast",
            "adapter.probe_fast",
            "host-process",
            "process-boot-7",
        ),
        ProbeCostBinding(
            "sensor-wide",
            "adapter.probe_wide",
            "host-process",
            "process-boot-7",
        ),
    ),
    minimum_samples=5,
)

navigator = PartialAttentionNavigator(
    system, observer, probe_factory, rank_partial_probes, horizon,
    attempt_id_prefix="measured-attention",
    query_label="refine the current Ground",
    vgi_revision="cedcc4540a9d75228cf83aaf21e1ba960fe8a555",
    cost_model=cost_model,
)
selection = navigator.begin_next()
# Every ranking entry now carries the cost basis and source-span digests.
```

The probe factory must use those declared method IDs as each `TransitionProbe.label`. The navigator applies the model on each freshly generated candidate set, so candidate costs remain tied to the supplied profile and the same methods can be compared again after each Ground revision. The resulting ranked history includes cost provenance alongside VGI's separate expected-gain / scenario-bound metrics.

## Recorded verification

The integrated lifecycle, schema, and adaptive-coordinator suites passed in [GitHub Actions run 112](https://github.com/Kier73/In-Formation-Space/actions/runs/43108746664). The machine-readable [CI encounter receipt](results/ci-run-112.json) records the tested commit, job, suite counts, and integrity digest.

## Portable record format

- [observation-path.schema.json](observation-path.schema.json) defines the JSON structure independently of Python.
- [validate_observation_path.py](validate_observation_path.py) checks schema shape, first and final stages, legal adjacent transitions, and terminal-flag consistency.
- [examples/happy-path.json](examples/happy-path.json) is illustrative only; its referenced evidence artifacts are not present and it is not an executed observation.

The schema validates structure. The Python state machine and tests validate legal construction. The CLI combines the schema with the lifecycle transition rules. A schema-valid record is not proof that its referenced transport or sensor artifacts are authentic.

## Reproduce

    python bridges/observation-path/validate_observation_path.py bridges/observation-path/examples/happy-path.json
    python -m unittest discover -s bridges/observation-path -p 'test_*.py' -v