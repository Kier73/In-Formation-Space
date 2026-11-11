# E-CPU adapter map: observation and realization boundaries

**Status:** read-only interface mapping against the E-CPU `main` source inspected on 2026-11-11. No E-CPU source was modified by this bridge.  
**Purpose:** show where the generic In-Formation-Space observation path can reuse existing E-CPU interfaces without duplicating transport, consensus, VM application, Structural Memory, or Hypervisor authority.

## The most important distinction

E-CPU exposes several different meanings of “accepted”:

1. **Sender enqueue:** `ReliableChannel.send(payload)` emits an `RDATA` message, assigns a channel sequence, and stores the frame in the sender's pending map until an ACK is processed. A returned sequence number is not proof of receiver admission.
2. **Receiver frame validation / consensus intake:** `GatedObservationCoordinator.ingest_available()` peeks at queued frames, validates/decodes the typed substrate observation, creates `EvidenceLink` records, and submits them to `ObservationConsensus`. It does not consume the reliable frame or send its ACK.
3. **Evidence authorization:** `ObservationConsensus.finalize()` or `ObservationTraceBuilder.capture_authorized()` finalizes a quorum-ready event. Only `AUTHORIZED` produces a representative observation. `CONFLICT` or `REFUSED` must not be interpreted as a negative sensor value.
4. **Receiver-side application:** `GatedObservationCoordinator.commit_event()` is permitted only for `AUTHORIZED`. It persists the consume intent, consumes/ACKs non-representative sources, idempotently applies the representative to the VM, saves the checkpoint, then consumes/ACKs the representative.
5. **Interpretation and Ground use:** `ObservationTraceBuilder` turns authorized values into a typed `ObservedOrbitTrace`; `ObservationGroundBuilder.propose()` and `.admit()` are a later Structural Memory construction/admission process; `VerifiedGroundRealizer` is a further receiver-authorized read path.

These are not interchangeable events. In particular, transport send, receiver intake, quorum authorization, and VM application must not be compressed into one generic admission receipt.

## Mapping to In-Formation-Space ObservationPath

| In-Formation stage | E-CPU interface / evidence | What it establishes |
|---|---|---|
| `planned` | Trial 06 policy node and `AdaptivePolicyExecution.begin_attempt()` | A candidate observation was selected. No operation has been sent. |
| `dispatched` | `ReliableChannel.send(payload)` and an adapter-owned send record containing channel, sequence, destination, and payload digest | The sender emitted/enqueued an `RDATA` frame and tracks it as pending. It does not establish delivery or receiver admission. |
| `admitted` | `GatedObservationCoordinator.ingest_available()` returns an `EvidenceLink` after validating the queued frame and feeding the typed observation into consensus | A receiver-side frame was inspected and entered as candidate evidence. The frame is still queued; it has not yet been consumed/ACKed and the event is not yet quorum-authorized. |
| `returned` | An Encounter Envelope created from the exact typed observation payload/EvidenceLink, with source, channel, sequence, and digest lineage | The raw observation payload is preserved independently of its interpretation. This event may precede the consensus decision. |
| `evidence_authorized` | `ObservationConsensus.finalize()` / `ObservationTraceBuilder.capture_authorized()` returning `AUTHORIZED`; persist the decision's policy, digest, quorum, strictness, source set, dissent, missing sources, and representative source | The configured evidence rule accepted a representative observation. It is not yet proof that the representative has been applied to VM state. |
| `evidence_refused` | Consensus decision `CONFLICT` or `REFUSED` with its decision receipt | The evidence set did not satisfy the declared authorization rule. Preserve the payload and the refusal; do not interpret as a negative physical reading. |
| `applied` | `GatedObservationCoordinator.commit_event()` plus an adapter-owned checkpoint/application receipt and verified applied/consumed markers | The authorized representative was applied to the receiver VM and the event's reliable frames were consumed/ACKed according to the commit protocol. The commit method returns an `ObservationDecision`; a portable application receipt must be constructed from verified post-state/checkpoint evidence, not invented from the return value alone. |
| `interpreted` | Domain interpreter operating on `ObservedOrbitSample` / `ObservedOrbitTrace`, with its own method and artifact reference | The authorized, and when required applied, observation was interpreted under a named rule. |
| `query_determined` | A query/proof record tied to the active hypothesis-set digest and observation basis | The query was resolved relative to the stated hypothesis set. It does not assert that the set is exhaustive. |

The path intent flags `authority_required` and `application_required` make the required gates explicit. `application_required` implies `authority_required`. Direct single-receiver observations can leave both false. A quorum-gated E-CPU intake should set `authority_required=true`; a flow that also commits the selected observation to receiver VM state should set both flags true.

## E-CPU flow in more detail

### 1. Reliable transport

[`mailcpu/reliability.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/reliability.py) defines `ReliableChannel.send()`, `peek()`, `receive()`, and `process_ack()`. `send()` allocates a sequence, sends the `RDATA` frame, and adds it to `_pending`. `peek()` validates the queued frame without consuming it. `receive()` consumes the frame and sends `RACK`; `process_ack()` removes the sender's pending entry. Therefore an adapter should record sender enqueue separately from receiver intake and final ACK completion.

### 2. Quorum evidence

[`mailcpu/gated_observation.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/gated_observation.py) contains `GatedObservationCoordinator.ingest_available()`, `finalize_event()`, and `commit_event()`. Its `_consume_source()` persists a consume intent, verifies the queued frame still matches the stored `EvidenceLink`, calls `ReliableChannel.receive()`, then persists the consumed marker. Its `_apply_representative()` persists an apply intent, calls `vm.apply_substrate_observation(...)`, checks that the VM returns a Boolean idempotence result, then persists the applied marker. `commit_event()` orders these actions for an authorized event.

[`mailcpu/observation.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/observation.py) defines the `ObservationConsensus` policy/decision model. The consensus policy is the source of the quorum, strictness, allowed-source, dissent, and missing-source facts recorded in the `evidence_authorized` event. The event digest should be computed from the actual decision payload; the adapter must not synthesize source agreement.

### 3. Authorized trace capture

[`mailcpu/observed_orbit_pipeline.py`](https://github.com/Kier73/E-CPU/blob/main/mailcpu/observed_orbit_pipeline.py) defines `ObservationTraceBuilder.capture_authorized()`. It checks the consensus status, finalizes a quorum-ready event if necessary, requires `AUTHORIZED`, retrieves the representative observation, extracts the configured integer register, and records the consensus metadata and decision digest in an `ObservedOrbitSample`. The trace separates the source/event `logical_time` from its ordinal sample `coordinate`.

The adapter should create the Encounter Envelope from the actual typed payload/EvidenceLink and link that raw envelope to the corresponding authorized sample. It should not turn a sample into a signed/authenticated claim: the E-CPU documentation explicitly states that consensus source IDs and trace digests do not cryptographically authenticate remote senders.

### 4. Structural Memory and verified realization

`ObservationGroundBuilder.propose()` uses a training prefix and withheld suffix to propose a law through `StructuralMemoryRegistry.propose_trace()`. `ObservationGroundBuilder.admit()` then invokes the registry admission method with an expected revision. The trusted host-supplied admission policy must return literal `True`; only then is a Ground binding and ObserverContract created.

`VerifiedGroundRealizer` then checks the receiver's own registry identity, dispatches through `HeadlessOS.hypervisor_dispatch()`, requires a Hypervisor `ALLOW`, and verifies the ObserverReceipt and Structural Memory read receipt against the requested Ground/context. This is a separate privileged read/realization operation, not the same event as evidence authorization or observation intake.

`ObserverReceipt` is content-addressed evidence, not a cryptographic signature and not a remote execution capability. The receiver Hypervisor remains the authority for the protected read.

## Adapter responsibilities

A production adapter should:

1. Use E-CPU's existing ReliableChannel and GatedObservationCoordinator rather than reimplementing their queue, deduplication, quorum, ACK, or checkpoint logic.
2. Construct Encounter Envelopes from the exact validated typed payload bytes/canonicalization and preserve `EvidenceLink` source/channel/sequence lineage.
3. Record `evidence_authorized` only after an actual `AUTHORIZED` decision; record `evidence_refused` for `CONFLICT`/`REFUSED`.
4. Record `applied` only after `commit_event()` has completed and the adapter has independently captured/checkpointed the receiver-side application state and ACK/consume outcome. `commit_event()` returning a decision alone is not an application receipt.
5. Record `interpreted` only after the declared authority/application gates have been satisfied and the actual interpreter has produced a traceable interpretation artifact.
6. Keep each clock coordinate paired with its own clock-domain identifier. E-CPU already carries source and receiver `TemporalFrame` values; the adapter must not subtract them unless an explicit calibrated mapping exists.
7. Keep `ObservationGroundBuilder.admit()` and Hypervisor `ALLOW` as later authorization boundaries. Do not treat an admitted Ground proposal or an observer digest as a substitute for receiver authorization.

## References inspected

- E-CPU `main` branch on 2026-11-11.
- `mailcpu/reliability.py`.
- `mailcpu/gated_observation.py`.
- `mailcpu/observation.py`.
- `mailcpu/observed_orbit_pipeline.py`.
- `mailcpu/observer_orbit.py`.
- `docs/OBSERVED_ORBIT_PIPELINE.md`.

**No E-CPU files were modified.** This map describes an adapter seam; it is not a claim that the two repositories are already connected.