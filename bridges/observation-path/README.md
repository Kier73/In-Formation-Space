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
                                    |            +-> evidence_authorized -> applied (optional) -> interpreted
                                    |                         |
                                    +-> no_result             +-> evidence_refused
         |          |           |           |              | 
         v          v           v           v              +-> continued -> next attempt
    dispatch_failed  rejected  no_result  returned_unadmitted  unresolved
                           (unadmitted return and other failures are terminal)

Each request attempt is append-only. `admitted` records receiver-side intake; `evidence_authorized` records a separate consensus/authority decision. An intent can require that gate, and can additionally require an `applied` receipt for a receiver-side state mutation before interpretation. A direct one-receiver path can leave both requirements false. An interpreted observation can end in `query_determined`, `unresolved`, or `continued`; `continued` records which next observation the adaptive policy selected and closes the current request attempt before a new attempt begins. Failure paths are terminal and do not silently become observations. A payload that returns without an admission receipt is preserved as `returned_unadmitted` and cannot advance to interpretation within that attempt.

## Live E-CPU integration

The pinned E-CPU runtime integration passed in [GitHub Actions run 172](https://github.com/Kier73/In-Formation-Space/actions/runs/43115649399): two tests exercised real durable channels, quorum finalization, VM commit/checkpoint recovery, sender ACK processing, and conflict refusal. The [integration receipt](results/live-ecpu-integration-run-172.json) records the exact E-CPU and In-Formation-Space commits and test cases.

## E-CPU coordinator adapter

The [E-CPU gated adapter](ecpu_gated_adapter.py) is a dependency-injected bridge over the existing `GatedObservationCoordinator`. It does not import or reimplement E-CPU. It records a finalized decision only after checking the coordinator's policy, finalized status, evidence-link source set, and representative. After `commit_event()`, it checks the durable applied marker, complete receiver consumption, absence of outstanding commit intents, the VM's exact idempotence receipt, and actual register readback before recording `applied`. It then saves a final E-CPU checkpoint and records its digest.

The adapter verifies receiver-side ACK emission through the completed consume path. It does **not** claim that the remote sender has processed its ACK and cleared its pending frame; E-CPU's sender-side `process_acks()` is a separate operation. Nor does it create transport or Encounter Envelope evidence on its own: dispatch, receiver-intake, and raw-return artifacts must be supplied by the surrounding host adapter.

## Explicit authority and application gates

An intent may set `authority_required=true` when a source quorum, consensus policy, or other evidence-authorization decision must occur after the raw return. The path must then record `evidence_authorized` or `evidence_refused` before interpretation. An intent may additionally set `application_required=true` when the authorized representative must be applied to receiver state; this implies authority is required, and an `applied` receipt must precede interpretation. An application or authorization failure is terminal and cannot be interpreted as a negative measurement.

For the E-CPU-specific mapping of transport enqueue, receiver evidence intake, quorum finalization, VM commit/ACK, and later Ground realization, see the [E-CPU adapter map](../adaptive-attention-execution/ecpu-adapter-map.md).

## Evidence and clocks

Dispatch, receiver admission, raw return, evidence authorization/refusal, optional receiver-state application, interpretation, and query-resolution events can each reference their own receipt or artifact. A returned payload must reference an Encounter Envelope and include its encounter ID, payload digest, and declared canonicalization. The path ledger records those declarations; it does not fetch or authenticate the referenced artifact. The Encounter Envelope validator remains responsible for validating the referenced envelope when it is available.

Clock values are retained only alongside their clock-domain labels. The path model does not subtract or align values from different domains. Unknown timing remains unknown.

## Query resolution boundary

The terminal `query_determined` stage requires a Boolean result, the hypothesis-set digest against which it was derived, and a basis reference. This means the query was resolved relative to that stated hypothesis set and evidence basis. It does not claim that the hypothesis set is exhaustive or that the result is a universal property of the external system.

An adaptive coordinator now uses this ledger for one-request-at-a-time policy execution: [Adaptive Attention Execution](../adaptive-attention-execution/README.md). It records a continuation between attempts, while an outcome outside the predicted policy branches is retained as an unresolved model mismatch.

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