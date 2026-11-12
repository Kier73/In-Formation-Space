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

A matched observation changes no Ground by itself. A caller must first record the existing explicit `evidence_authorized` stage (normally through the E-CPU gated adapter); declared application and sender-ACK requirements must also be satisfied before interpretation. `build_ground_revision()` then returns a new VGI Ground value with the return, authorization, optional application/ACK, and interpretation references in its evidence list and an append-only revision entry in Ground metadata. The original Ground remains unchanged, and a stale source fingerprint is rejected.

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