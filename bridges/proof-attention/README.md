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
- A dropped request or ACK is retried using the original reliable sequence. A duplicate request is consumed and acknowledged by E-CPU but is not delivered to the worker a second time.
- Request retry exhaustion is represented as `delivery_unconfirmed`. This means delivery/admission was not confirmed; it is not an execution rejection, timeout observation, or theorem result. Because E-CPU channels are strictly in-order and the receiver may or may not have advanced (for example, data delivered but every ACK lost), the affected endpoint is fenced after retry exhaustion. Do not reuse it for later attempts; recreate host/worker endpoints with fresh route identities/channel epoch so an uncertain old sequence cannot block or collide with new work.
- A worker result uses the response ReliableChannel. The host records the raw returned payload after the response frame is consumed and ACKed, then checks the result envelope against the active attempt, request digest and recorded return evidence before importing the VGI trace.
- A response duplicate is acknowledged without a second proof interpretation. A malformed or mismatched result remains a recorded raw return followed by `interpretation_failed`.
- The worker's response sender can clear its pending sequence only after it receives the host's response ACK. A transport ACK is never promoted to a kernel receipt. Result-channel retry exhaustion also fences that endpoint; later result sequences cannot safely reuse an uncertain in-order cursor. The host supplies independently verified kernel receipts to `receive_result(verified_receipts=...)`; they remain separate from the worker's transport ACK and result digest.

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
