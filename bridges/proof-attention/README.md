# Bridge: intention-scoped proof attention

**Status:** experimental planning bridge.  
**Purpose:** turn an existing VGI ProofGround into a reproducible attention frontier without flattening its AND/OR structure or promoting tactic claims into kernel results.

## Why this bridge exists

VGI's ProofGround represents each tactic application as an OR alternative, with every subgoal on that hyper-transition jointly required (AND). It also distinguishes candidate, elaborated, timed-out and rejected tactic attempts, and keeps kernel acceptance behind a separately supplied VerifiedKernelReceipt.

A proof-search host still needs to decide what to inspect or execute next. The ordinary partial-transition navigator is not the right abstraction: one tactic may create several jointly required obligations, while a theorem may have several alternative tactics. This bridge keeps those semantics intact and adds an explicit active-intention layer.

## API

```python
from proof_attention import build_proof_attention_plan

plan = build_proof_attention_plan(
    proof_ground,
    root_obligation_ids=(root_obligation_id,),
)
```

root_obligation_ids is required. The planner never guesses the theorem or goal of interest from insertion order, surface text, or the shape of the graph.

The returned document contains:

- a deterministic digest of the source proof Ground and a separate digest of the plan;
- the confirmed reachable frontier for the supplied root intentions;
- candidate tactic actions, each retaining its complete proposed AND bundle;
- the set of root intentions that structurally reach each obligation;
- kernel status for each child, with only kernel_accepted counting as accepted;
- recorded timeout/rejection counts, without automatically retrying failed attempts.

## Traversal and attention rules

Only elaborated hyper-transitions expand the currently observed frontier. Each of their subgoal_ids is traversed as part of that edge's AND bundle. Multiple elaborated hyper-transitions remain alternative OR routes. Cycles are handled by per-root breadth-first traversal.

A candidate transition is returned as an action for its source obligation, but its proposed children remain conditional and do not become reachable obligations until a later proof trace records the tactic as elaborated. This prevents an unexecuted tactic proposal from silently expanding the active proof state. Distinct candidate tactics remain distinct actions; their subgoal bundles are never flattened into a list of interchangeable successors.

The default structural order is:

1. larger number of explicit root intentions reaching the source first;
2. shorter distance through recorded elaborations first;
3. stable transition identifier as a deterministic tie-break.

Root coverage is structural reachability, not a probability or confidence estimate. The planner does not infer that a frequently shared subgoal is more likely to succeed.

## Measured tactic costs (optional)

An existing EmpiricalProbeCostModel may be supplied through its provenance_for(method_id) interface:

```python
plan = build_proof_attention_plan(
    proof_ground,
    root_obligation_ids=(root_obligation_id,),
    cost_model=empirical_probe_cost_model,
)
```

The model's method IDs must be explicitly bound to tactic labels (for example, simp to lean.tactic.simp) using ProbeCostBinding. It must contain sufficient successful samples for every candidate tactic, all measured on the same clock actor, process/clock segment and percentile. Only when every candidate method is bound and comparable does the planner use empirical p90/p95 nanoseconds as an additional tie-break after intention coverage and elaboration distance.

If one or more tactic methods lack a binding, latency ordering is disabled for the entire candidate set. Missing costs are not treated as zero, and partially calibrated costs are not compared against unknown costs. Cost evidence changes candidate ordering only; it does not become proof evidence, a success probability, or an authorization to execute a tactic.

The optional interface reuses bridges/observation-path/operation_spans.py and empirical_probe_costs.py; it does not duplicate their measurement or validation logic.

## Trust and interpretation boundaries

- The bridge does not run Lean, execute tactics, construct proof terms, or verify a kernel receipt.
- An elaborated tactic is not a kernel-accepted theorem. Even an empty subgoal bundle still requires a receipt for the parent obligation.
- A kernel-rejected receipt describes a rejected proof term; it does not prove that the proposition is unprovable. Other candidate tactics remain visible.
- Raw kernel_claims retained by VGI are included in the source digest but never promoted to accepted status.
- A candidate's declared subgoals are conditional until the trace records elaboration. They remain visible inside that candidate action's AND bundle.
- The frontier is the union of nodes reachable through recorded elaborations across alternative OR routes. It is an inspection map, not a minimum proof, proof-completeness result, or scheduling-optimality claim.
- Measured operation spans describe the named synchronous call boundary. They do not measure theorem difficulty, proof quality, or generalize automatically across clock segments or execution environments.

## Reproduction

The focused workflow checks this bridge against the pinned public VGI implementation and tests both structural behavior and optional cost binding:

```bash
PYTHONPATH=bridges/proof-attention:bridges/observation-path:/path/to/Virtual-Ground-Interpreter/virtual_ground_interpreter \\
  python -m unittest discover -s bridges/proof-attention -p 'test_*.py' -v
```

The workflow records its exact VGI commit in .github/workflows/proof-attention.yml.

## Next experiments

A later increment could admit new elaboration frames from a real tactic runner, then replan from the newly observed frontier. Another could compare the structural intention policy with a separate AND/OR cost-to-go algorithm on finite proof graphs. Neither should weaken the external kernel receipt boundary or infer a proof from an empty child list.


## Proof-action execution and replanning

The [proof-action execution session](proof_action_execution.py) adds the next interface after planning: one selected tactic candidate can be handed to an external proof worker, carried through an evidence-gated execution lifecycle, and correlated with a refreshed VGI ProofGround before the next plan is generated.

```python
from proof_action_execution import ProofAttentionSession

session = ProofAttentionSession(
    proof_ground,
    root_obligation_ids=(root_obligation_id,),
    attempt_id_prefix="proof-run",
    query_label="establish the theorem",
)

attempt = session.begin_next()
# The host performs the real operation, then reports its receipts:
attempt.mark_dispatched("sender", "dispatch://...")
attempt.mark_admitted("worker", "admission://...")
attempt.record_return(
    "worker",
    evidence_ref="encounter://...",
    encounter_id="encounter-...",
    payload_digest="...",
    canonicalization="canonical-json-v1",
)

# Import the refreshed trace through VGI's ProofGroundAdapter first.
session.interpret_result(
    refreshed_proof_ground,
    actor="proof-trace-adapter",
    interpretation_ref="interpretation://...",
)
next_attempt = session.begin_next()
```

### Lifecycle and correlation

Each attempt has its own SHA-256-linked event sequence:

`planned → dispatched → admitted → returned → interpreted`

Transport or execution failures are explicit terminal events: `dispatch_failed`, `execution_rejected`, `returned_unadmitted`, `no_result`, or `interpretation_failed`. They are never converted into tactic outcomes.

A result can be interpreted only after an admitted raw return. The refreshed ProofGround must:

- preserve the exact proof environment and all previously known obligation fingerprints;
- retain the selected source obligation;
- contain exactly one result hyper-transition for the selected source and tactic;
- bind that result edge's `evidence_ref` to the exact `attempt_id`;
- report one of VGI's observed result statuses: `elaborated`, `timeout`, or `rejected`.

The attempt ID is the correlation key the external trace adapter must write into the resulting VGI hyper-transition. This connects the raw return receipt to the normalized proof trace without pretending this bridge authenticates either artifact. The adapter remains responsible for checking that the trace was derived from the returned proof-worker output.

### Replanning and completion

After a result is correlated, the session rebuilds the attention plan from the refreshed ProofGround. The prior attempt is closed with a `continued` event before a next candidate is opened. Candidate transition IDs already attempted in this session are skipped, even if the refreshed Ground still carries their original candidate records.

The session reaches `complete` only when every explicit root intention has a matched `kernel_accepted` receipt in the refreshed ProofGround. A timeout, rejected tactic, empty tactic subgoal list, or exhausted candidate frontier cannot establish completion. When no unattempted candidates remain and roots are not all kernel-accepted, the session becomes `exhausted` and the last interpreted attempt records `unresolved`; this is a scheduling result, not a theorem of unprovability.

The session and every attempt expose deterministic JSON snapshots and digests. Each attempt event includes its sequence, prior event digest, and current event digest, so a later reader can verify the local event chain.

A later worker can restore the orchestration state against the exact refreshed ProofGround:

```python
restored = ProofAttentionSession.from_snapshot(
    saved_session_document,
    freshly_imported_proof_ground,
)
```

Restoration verifies the session and attempt digests, each per-attempt event chain, the attempt sequence, and the supplied Ground's reproduction of the saved current plan. An active worker can resume at its recorded lifecycle stage; attempted transition IDs remain excluded from future selection. A mismatched environment or changed proof frontier is rejected rather than silently rebased. These digests provide integrity checks, not authentication of the previous worker or trusted kernel.

### Deliberate boundary

This is a coordinator and receipt ledger, not a tactic runner. It does not launch Lean or another proof assistant, dispatch network messages, parse arbitrary Lean syntax, authenticate an Encounter Envelope, or cryptographically validate a VerifiedKernelReceipt. Those operations remain with the host, trace adapter, and trusted kernel/checker integration.

A proof action deliberately has a proof-specific lifecycle rather than being forced into the ordinary partial-transition probe interface: a tactic result is a hyper-transition with AND subgoals and OR alternatives, not a single state/action outcome that directly revises a transition Ground.

Focused tests cover stage ordering, return/admission gates, attempt correlation, environment and obligation continuity, timeout/rejection handling, frontier exhaustion, receipt-gated completion, and deterministic event-chain export. The existing `.github/workflows/proof-attention.yml` discovers both proof-attention test modules against the pinned VGI revision.


## E-CPU trajectory persistence

The [trajectory adapter](proof_attention_trajectory.py) persists the current proof-attention session into E-CPU's existing indexed binary trajectory and EventJournal formats:

```python
from proof_attention_trajectory import (
    export_proof_attention_trajectory,
    restore_proof_attention_trajectory,
)

manifest = export_proof_attention_trajectory(
    session,
    proof_ground,
    "proof-session.mtrj",
    "proof-session.mtrj.idx",
    "proof-session.manifest.json",
    stride=64,
)

restored = restore_proof_attention_trajectory(
    "proof-session.manifest.json",
    "proof-session.mtrj",
    "proof-session.mtrj.idx",
    freshly_imported_proof_ground,
)
```

The adapter reuses E-CPU's `TrajectoryWriter`, `TrajectoryReader`, and `EventJournal`; it does not fork or reimplement those formats. Every attempt event becomes one trajectory frame. Frames carry the original session snapshot digest, global event sequence, attempt sequence/ID, attempt-local event sequence/digest, and the complete attempt event.

Two independently reconstructed integrity views accompany the portable session manifest:

1. The binary trajectory receipt chain covers ordered frame payloads and local event coordinates.
2. The EventJournal projection covers the same ordered attempt events, with attempt IDs, local sequence numbers, event actors, evidence references, details, and original event-chain links.

The manifest contains attempt headers plus the session core, so the full event stream is reconstructed from the binary trajectory rather than duplicated into the manifest. Restore verifies the manifest digest, trajectory header/stride, all frame identities, contiguous per-attempt sequences, attempt-group ordering, trajectory receipt head, EventJournal projection head, and the reconstructed session digest. It then delegates session and action-event validation to `ProofAttentionSession.from_snapshot` against a caller-supplied fresh VGI ProofGround.

### Time and trust boundaries

The trajectory logical time is the one-based append order of session events. It is a deterministic coordinate for seeking and replay—not elapsed time, proof-assistant time, scheduler time, or a cross-process clock measurement. E-CPU's trajectory layer preserves this order; it does not align it to other time domains.

The data stream, sparse index, and manifest are separate files, not a transactional distributed store. SHA-256 chains and manifest digests detect inconsistent modification relative to a trusted head; they are not signatures or external authentication. The restored session is only as trustworthy as the supplied proof trace and upstream evidence/kernel-receipt validation. The trajectory adapter preserves and cross-checks those records; it does not authenticate a previous worker or execute Lean.

The workflow pins E-CPU to `c82d795e6b7602cc3d6e8c41e8622820914f5cbf` and runs the trajectory tests alongside the planner and proof-action lifecycle suites.


## Portable proof-worker handoff protocol

The [proof-action protocol](proof_action_protocol.py) defines the request and result documents exchanged with an external proof worker. It fills an important gap between “select a tactic” and “interpret a returned trace”: a worker needs the complete scoped proof state, and a returned trace must identify the exact request and already-admitted raw return it answers.

### Build a request

```python
from proof_action_protocol import build_proof_action_request

attempt = session.begin_next()
request = build_proof_action_request(session, proof_ground)
```

The request is JSON-serializable and includes:

- the active attempt ID, query label, plan digest and ProofGround digest;
- all active root intention IDs;
- the complete source obligation document, including the structured goal, local context, metavariables, assumptions and proof environment;
- the selected candidate transition, its tactic and proposed AND subgoal IDs;
- the attention context and a request digest.

The request declares that the candidate is not an observation, its proposed subgoals are jointly required if the tactic is later elaborated, alternative tactic transitions are OR routes, and kernel acceptance still requires a separate verified receipt.

### Return and import a result

After the host has actually dispatched the request, recorded receiver admission and preserved the raw return, the result envelope can be constructed and imported:

```python
from proof_action_protocol import (
    make_proof_action_result,
    import_proof_action_result,
)

result_document = make_proof_action_result(
    request,
    return_evidence={
        "evidence_ref": returned_encounter_ref,
        "encounter_id": encounter_id,
        "payload_digest": payload_digest,
        "canonicalization": canonicalization,
    },
    proof_trace=normalized_vgi_lean_trace,
)

imported = import_proof_action_result(
    session,
    proof_ground,
    request,
    result_document,
    actor="proof-trace-adapter",
    interpretation_ref=interpretation_ref,
    verified_receipts=kernel_receipts,
)
proof_ground = imported.proof_ground
```

Before importing, the bridge:

1. recomputes the request from the current session and ProofGround and requires exact request-digest equality;
2. requires the session's active attempt to be at the admitted `returned` stage;
3. compares the result's attempt ID, request digest, Encounter reference, Encounter ID, payload digest and canonicalization with the exact return event already recorded on that attempt;
4. imports the normalized trace through VGI's `ProofGroundAdapter`, passing through separately supplied `VerifiedKernelReceipt` objects;
5. delegates the final source/tactic/attempt correlation and environment/obligation continuity checks to `ProofAttentionSession.interpret_result`.

The worker must write the exact attempt ID into the result hyper-transition's `evidence_ref`. A trace that references another attempt, a different environment, an unknown source, or duplicate matching result edges is not accepted as the result of this action.

### Interpretation and trust boundaries

The request digest binds the portable action description; the result digest binds its request reference, return receipt and normalized proof trace. These are deterministic integrity digests, not signatures. The importer checks equality with the host-recorded return but does not fetch or authenticate the Encounter Envelope itself. The caller remains responsible for validating the transport receipt and any external signature.

The VGI adapter parses normalized Lean trace JSON; it does not execute Lean. A supplied `VerifiedKernelReceipt` is checked for consistency and environment binding by VGI, but a production host must authenticate the upstream checker receipt and proof-term fingerprint. Neither a tactic candidate, an elaborated hyper-transition, an empty subgoal bundle, nor a result digest is kernel acceptance.

The protocol therefore supplies a portable interchange contract, not an autonomous proof worker. A host still chooses the process, launches the proof assistant, records actual dispatch/admission/return receipts, and provides authenticated kernel results.


## E-CPU reliable-channel host/worker adapter

The [ReliableChannel adapter](proof_action_reliable_channel.py) connects the portable request/result protocol to E-CPU's existing sequenced at-least-once channel. It does not implement a second transport or retry system.

A host-side session and worker endpoint can share an E-CPU `Transport` implementation:

```python
from mailcpu.reliability import ReliabilityPolicy
from mailcpu.transport import InMemoryTransport
from proof_action_reliable_channel import (
    ProofActionReliableHost,
    ProofActionReliableWorker,
)

transport = InMemoryTransport()  # Replace with a Transport backed by the host's substrate.
policy = ReliabilityPolicy(lease_ticks=3, max_attempts=4, window_size=8)

host = ProofActionReliableHost(
    session,
    proof_ground,
    transport,
    host_id="proof-host",
    worker_id="proof-worker",
    policy=policy,
)
worker = ProofActionReliableWorker(
    transport,
    host_id="proof-host",
    worker_id="proof-worker",
    policy=policy,
)

dispatch = host.dispatch_next()
request = worker.receive_request()
admitted = host.observe_request_admission()
# The worker's external tactic runner consumes request.request, then packages
# a result with make_proof_action_result(...).
# The worker sends it with worker.send_result(result_document).
# kernel_receipts comes from the host's separately trusted kernel-checker adapter.
imported = host.receive_result(verified_receipts=kernel_receipts)
worker.process_result_acknowledgements()
```

### Delivery and proof semantics

- The host marks `dispatched` only after E-CPU admits the frame to the reliable sender.
- The worker validates the request digest and format in ReliableChannel's receive-side commit callback. Invalid request payloads are not consumed or acknowledged.
- The host records `admitted` only after the request sequence's E-CPU acknowledgement returns. That ACK means the worker's receive endpoint validated and consumed the request; it is not proof that a tactic ran or succeeded.
- A dropped request or ACK is retried using the original reliable sequence. A duplicate request is consumed and acknowledged by E-CPU but is not delivered to the worker a second time. The worker also deduplicates by proof `attempt_id`: an identical request replayed under a new reliable sequence is ACKed without a second tactic handoff, while a conflicting digest for the same attempt is rejected before ACK.
- Request retry exhaustion is represented as `delivery_unconfirmed`. This means delivery/admission was not confirmed; it is not an execution rejection, timeout observation, or theorem result. Because E-CPU channels are strictly in-order and the receiver may or may not have advanced (for example, data delivered but every ACK lost), the affected endpoint is fenced after retry exhaustion. Do not reuse it for later attempts; recreate host/worker endpoints with fresh route identities/channel epoch so an uncertain old sequence cannot block or collide with new work.
- A worker result uses the response ReliableChannel. The host records the raw returned payload after the response frame is consumed and ACKed, then checks the result envelope against the active attempt, request digest and recorded return evidence before importing the VGI trace.
- A response duplicate is acknowledged without a second proof interpretation. A malformed or mismatched result remains a recorded raw return followed by `interpretation_failed`. A late or uncorrelated JSON response is retained in the quarantine ledger as its full canonical payload plus a payload digest and hash-chained reason record; non-JSON payloads retain a representation and digest.
- The worker's response sender can clear its pending sequence only after it receives the host's response ACK. A transport ACK is never promoted to a kernel receipt. Result-channel retry exhaustion fences both directions of that worker endpoint: it can no longer send a result or receive another proof request. A rejected in-order request also fences the worker request receiver because it cannot skip an unacknowledged sequence. In either case, replace both endpoints with a fresh channel epoch before continuing. The host supplies independently verified kernel receipts to `receive_result(verified_receipts=...)`; they remain separate from the worker's transport ACK and result digest.

The adapter's `Transport` is injected. The in-memory and fault-injecting E-CPU transports make the lifecycle reproducible in tests; an external host must supply a transport implementation that routes the mailboxes between its processes. This merge does not claim that a remote network backend, Lean tactic runner, or physical worker has been deployed.

### Failure separation

| Event | Session outcome | Meaning |
|---|---|---|
| Request retry limit reached before worker ACK | `delivery_unconfirmed` | No confirmed worker admission |
| Worker admits request but returns nothing by host deadline | `no_result` | Execution result unavailable |
| Raw response arrives but envelope/trace cannot be imported | `interpretation_failed` | Return exists; semantic interpretation failed |
| Normalized trace records tactic timeout | Interpreted result `timeout` | A tactic timeout was actually observed |
| Normalized trace records tactic rejection | Interpreted result `rejected` | That tactic attempt was rejected; proposition not proven impossible |
| VGI trace carries a matched verified kernel receipt for every active root | Session `complete` after replanning | The supplied external kernel receipts satisfy the declared root intentions |

The transport adapter therefore preserves the distinction between delivery, admission, raw return, interpretation and kernel acceptance. It uses E-CPU's reliability semantics unchanged; it does not infer theorem truth from message delivery.

The pinned proof-attention workflow already checks out E-CPU and VGI and discovers the reliable-channel tests along with the planner, protocol, execution and trajectory suites.

## Distributed endpoint checkpoints

The [paired checkpoint adapter](proof_action_checkpoint.py) extends continuity from the proof-session event history to the two live ReliableChannel endpoints and their shared transport state. It records:

- the complete ProofAttentionSession snapshot and active ProofGround digest;
- host request-sender and result-receiver sequence state;
- worker request-receiver and result-sender sequence state;
- pending frames, receive cursors, delivered identities, received payload digests, retry ticks, policies and failed sequences from E-CPU's ReliableChannel snapshots;
- the worker's admitted attempt-to-request-digest registry and result-once index;
- the host's active request/sequence, endpoint fence state and complete hash-chained quarantine ledger;
- the transport backend's own snapshot, so queued DATA and ACK frames are part of the same exported cut.

For E-CPU's deterministic in-memory backend:

```python
from mailcpu.transport import InMemoryTransport
from proof_action_checkpoint import (
    export_proof_action_checkpoint,
    restore_proof_action_checkpoint,
)

checkpoint = export_proof_action_checkpoint(host, worker)
# Persist the JSON-compatible checkpoint as one atomic document.

transport, host, worker = restore_proof_action_checkpoint(
    checkpoint,
    freshly_imported_proof_ground,
    restore_transport=InMemoryTransport.from_snapshot,
)
```

The restore path reconstructs the session against the freshly imported ProofGround, verifies that the current plan and active request are exactly reproduced, restores each ReliableChannel against the supplied transport, and checks that host and worker identities, channel names and policies agree. It preserves in-flight requests, ACKs and results rather than inventing a new channel sequence or silently repeating an admitted action.

### Consistent-cut and trust requirements

Export is intended for a **quiescent cut**: no concurrent send, receive, retry tick or ACK processing may mutate either endpoint or the transport while the three snapshots are taken. A process supervisor or storage layer must persist the paired checkpoint as one atomic unit. A backend that cannot snapshot and restore its mailbox state may instead provide its own durable transport checkpoint and restoration callback; endpoint snapshots alone cannot recreate messages that the transport has lost.

The `InMemoryTransport` implementation is a deterministic test substrate, not a remote network deployment. A production transport must define how mailbox durability, message identity, ordering and atomic checkpoint boundaries survive process or machine failure.

The checkpoint digests detect inconsistent modification relative to a trusted checkpoint head; they are not signatures, identity authentication, or proof of origin. Restoring a session does not authenticate an earlier worker, validate an Encounter Envelope, execute Lean, or manufacture a `VerifiedKernelReceipt`. The caller still supplies a freshly imported ProofGround and independently trusted kernel evidence. The earlier trajectory/EventJournal adapter remains the append-oriented session history; this adapter captures the live communication state needed to continue it.

## Bind live endpoints to append-only session history

The [continuity bundle](proof_action_continuity.py) binds the paired endpoint checkpoint to one exact E-CPU trajectory manifest and its receipt heads. This keeps two forms of memory distinct while making their relationship verifiable: the trajectory is the append-oriented history of proof-action events; the pair checkpoint is the live communication state required to continue from a particular cut.

After exporting the trajectory from the host's current session, bind its manifest to the paired checkpoint:

```python
from proof_action_continuity import (
    export_proof_action_continuity_bundle,
    restore_proof_action_continuity_bundle,
)

manifest = export_proof_attention_trajectory(
    host.session, proof_ground, data_path, index_path, manifest_path
)
bundle = export_proof_action_continuity_bundle(host, worker, manifest)

transport, host, worker, history = restore_proof_action_continuity_bundle(
    bundle,
    freshly_imported_proof_ground,
    restore_transport=InMemoryTransport.from_snapshot,
    trajectory_manifest_path=manifest_path,
    trajectory_data_path=data_path,
    trajectory_index_path=index_path,
)
```

Export refuses a trajectory manifest whose session digest differs from the host's exact session snapshot. Restore checks the persisted manifest against the bundle's manifest digest, session digest, event counts, stride, trajectory receipt head and EventJournal projection head; it then independently restores the trajectory against the fresh ProofGround and the paired endpoints against the same ProofGround/transport, and requires the two reconstructed session documents to be identical.

The bundle does not embed or replace the trajectory files. Keep the manifest, binary stream, sparse index and paired checkpoint together as one application-level persistence unit. A later session event requires a newly exported trajectory cut and a newly bound bundle; a bundle is not a moving pointer to a future trajectory suffix.

This makes the history/runtime relationship inspectable, not magically transactional. The caller must still create a quiescent cut and persist all components atomically. Receipt and manifest digests detect inconsistency relative to a trusted head; they are not signatures or worker authentication. The trajectory and live transport retain their own semantics and trust boundaries.

## Restart one endpoint while its peer remains live

The host and worker checkpoint functions can also be used independently when only one process is replaced and the existing transport service plus peer endpoint remain available:

```python
from proof_action_checkpoint import (
    snapshot_proof_action_host, restore_proof_action_host,
    snapshot_proof_action_worker, restore_proof_action_worker,
)

host_state = snapshot_proof_action_host(host)
# Stop/fence the old host process, then restore the replacement:
host = restore_proof_action_host(
    host_state, freshly_imported_proof_ground, existing_transport
)

worker_state = snapshot_proof_action_worker(worker)
# Stop/fence the old worker process, then restore the replacement:
worker = restore_proof_action_worker(worker_state, existing_transport)
```

The focused restart tests exercise four cuts: a pending request while the worker stays live; a worker restart after request admission; a worker restart with a result still awaiting host intake/ACK; and a host restart with the result still waiting in its mailbox. They check that the same reliable sequence is resumed, application-level request identity is not admitted twice, results are interpreted once, and the surviving peer can complete ACK processing.

These are process-replacement tests over the same in-memory transport instance. A production deployment must preserve the actual mailbox substrate (or restore it through the backend's own durable mechanism). Only one process may own a given endpoint identity at a time: terminate or externally fence the old process before activating its replacement, otherwise two senders/receivers can create a split-brain endpoint. The paired checkpoint remains the appropriate atomic artifact when both sides and the transport are being restored together.

Standalone restore is for continuation of the same route epoch. It does not clear an endpoint that was fenced after ambiguous sequence exhaustion; such a route requires a fresh epoch rather than reusing uncertain sequence state.

## Route epochs, ownership generations and explicit handoff

The [route-epoch bridge](proof_action_route_epoch.py) records when a host/worker/channel identity tuple becomes active, which process generation owns it, why it is closed, and exactly which successor route may replace it.

A route identity consists of the host ID, worker ID, request/result channel names and reliability policy. The proof session itself is not part of that identity: its state evolves as actions are interpreted, while the route remains the same. Each epoch has a unique epoch ID and an owner generation. Restoring an endpoint pair and calling `bind_existing_proof_action_route_epoch` claims the route at the next generation; old endpoints holding the previous generation fail their next guarded operation.

```python
from proof_action_route_epoch import (
    ProofActionRouteEpochLedger,
    InMemoryRouteEpochLedgerStore,
    open_proof_action_route_epoch,
    handoff_proof_action_route_epoch,
)

# The in-memory CAS store is for tests. Production must inject a durable,
# linearizable implementation of RouteEpochLedgerStore.
store = InMemoryRouteEpochLedgerStore()
ledger = ProofActionRouteEpochLedger(store=store)
open_proof_action_route_epoch(
    host, worker, ledger, epoch_id="proof-route-1"
)

handoff = handoff_proof_action_route_epoch(
    host, worker, ledger,
    epoch_id="proof-route-1",
    reason_code="operator_rotation",
    reason="replace the worker route",
    successor_epoch_id="proof-route-2",
    successor_host_id="proof-host-2",
    successor_worker_id="proof-worker-2",
    successor_request_channel="proof-request-2",
    successor_result_channel="proof-result-2",
)
host, worker = handoff.host, handoff.worker
```

The close event retains the old paired checkpoint, the pre-close and post-close session digests, the complete post-close proof-session snapshot, an explicit reason code, the complete uncertain reliable-frame projection, and the exact successor epoch ID, owner ID and route identity. The post-close snapshot lets a later process reconstruct the route_closed lifecycle record instead of having only a digest of a state it cannot reproduce. The next open event must match that authorized successor and reference the close-event digest; it cannot substitute a different route. Old pending messages stay on the old channel names, so the successor cannot accidentally consume them.

The orchestrated handoff prepares the successor session first and appends the close and successor-open events in one ledger revision. With a shared CAS store, no competitor can insert a different route in between. The close operation rechecks the caller's exact owner ID and generation at commit time, preventing an owner that became stale during preparation from closing over a replacement.

### Route closure is not a tactic result

- A `planned` attempt has not entered the old route and remains planned for the successor host to dispatch with the same attempt ID.
- A `dispatched` or `admitted` attempt becomes `route_closed`. This records that its communication route ended before an interpreted result was accepted. It does not mean the tactic failed, timed out, or proved the goal impossible.
- The close event retains the original pre-close checkpoint, including the old attempt stage and message/ACK state. The post-close session digest records the explicit lifecycle update.
- Any already queued late result remains part of the old transport snapshot. It is not reinterpreted by the successor through a different channel epoch.

### Shared authority and process ownership

`RouteEpochLedgerStore` defines two operations: `load()` and `compare_and_swap(expected_ledger_digest, replacement, actor_id=...)`. The CAS operation must be linearizable across every process that can use the route. The actor ID lets a production adapter apply its own owner authorization to opens, claims, closes and atomic handoffs. `InMemoryRouteEpochLedgerStore` is a thread-safe reference implementation for tests only; it checks revision concurrency but does not authenticate identities. A production deployment can adapt a transactional database, consensus-backed record, or lease service to this contract.

Every guarded host/worker operation checks the active owner generation against the shared store. When a replacement claims the route, the compare-and-swap advances the owner generation; the previous process then fails its next operation even if it still holds an older local ledger copy. Two concurrent claims cannot both commit from the same expected ledger digest.

The route ledger's event hashes and CAS revision detect inconsistent or stale state relative to the authority store; they are not cryptographic identity proofs. Authentication of processes and authorization to claim an epoch belong to the durable authority/lease backend. A local ledger without a shared store coordinates objects only inside its own process; it must not be used to claim cross-process fencing.

Endpoint guards prevent stale workers from receiving another request or submitting a late result after their epoch has been superseded. They do not forcibly terminate an already-running external tactic process. A production worker runner must observe route fencing and apply its own cancellation/cleanup policy.

Focused tests cover route handoff with an in-flight request and queued ACK, exact successor authorization, planned-action adoption, owner-generation claims, stale-process rejection through a shared CAS store, rejection of stale CAS revisions, full uncertainty/checkpoint consistency, and route-ledger replay/tamper checks. These tests use E-CPU's in-memory transport and authority-store reference implementation; a remote transport and durable distributed authority remain separate integrations.

### Recover if the handoff process itself crashes

The route-close record is sufficient to finish activation even when the process that committed the handoff dies before constructing its replacement endpoints:

```python
from proof_action_route_epoch import (
    ProofActionRouteEpochLedger,
    restore_proof_action_route_handoff,
)
from mailcpu.transport import InMemoryTransport

# Load the authoritative ledger in the replacement process.
ledger = ProofActionRouteEpochLedger.from_dict(
    durable_store.load(), store=durable_store
)

transport, host, worker = restore_proof_action_route_handoff(
    close_event,
    ledger,
    freshly_imported_proof_ground,
    restore_transport=InMemoryTransport.from_snapshot,
    # Supply the same empirical cost model if the original planner used one.
    cost_model=restored_cost_model,
)
```

The recovery function verifies that the exact close event is present in the ledger and that its authorized successor is still active. It restores the pre-close transport snapshot, restores the separately recorded post-close ProofAttentionSession against a freshly imported ProofGround, then claims the successor under a fresh owner generation. The old transport queues remain available for inspection but are not consumed by the successor's fresh channel names.

Recovery therefore covers the commit-to-process-construction interruption window. It still relies on the transport backend's real persistence guarantees and on the authority store's linearizable, authenticated CAS implementation; the in-memory examples are deterministic reference tests, not a deployed distributed service.
