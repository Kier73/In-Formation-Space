"""Consistent, portable checkpoints for the E-CPU proof-action host/worker pair.

A checkpoint captures both protocol endpoints and the transport's own state.
Call export only at a quiescent cut (no concurrent send/receive/tick operation).
The transport backend owns its persistence semantics; restore receives an
explicit backend-specific restoration function.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
from typing import Any

from mailcpu.reliability import ReliabilityPolicy, ReliableChannel
from mailcpu.transport import Transport

from proof_action_execution import ProofAttentionSession
from proof_action_protocol import (
    ProofActionProtocolError,
    build_proof_action_request,
    validate_proof_action_request,
)
from proof_action_reliable_channel import (
    ProofActionReliableChannelError,
    ProofActionReliableHost,
    ProofActionReliableWorker,
)


HOST_FORMAT = "in-formation.proof-action-host-checkpoint/0.1"
WORKER_FORMAT = "in-formation.proof-action-worker-checkpoint/0.1"
PAIR_FORMAT = "in-formation.proof-action-pair-checkpoint/0.1"


class ProofActionCheckpointError(ValueError):
    """A proof-action endpoint or paired transport checkpoint is inconsistent."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProofActionCheckpointError(
            "checkpoint values must be finite canonical JSON"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _policy_payload(policy: ReliabilityPolicy) -> dict[str, int]:
    return {
        "lease_ticks": policy.lease_ticks,
        "max_attempts": policy.max_attempts,
        "window_size": policy.window_size,
    }


def _policy_from_payload(payload: Any) -> ReliabilityPolicy:
    if not isinstance(payload, Mapping) or set(payload) != {
        "lease_ticks", "max_attempts", "window_size"
    }:
        raise ProofActionCheckpointError("reliability policy fields are invalid")
    values = [payload[key] for key in ("lease_ticks", "max_attempts", "window_size")]
    if any(type(value) is not int or value <= 0 for value in values):
        raise ProofActionCheckpointError("reliability policy values must be positive integers")
    return ReliabilityPolicy(
        lease_ticks=payload["lease_ticks"],
        max_attempts=payload["max_attempts"],
        window_size=payload["window_size"],
    )


def _seal(core: dict[str, Any]) -> dict[str, Any]:
    return {**core, "snapshot_digest": _digest(core)}


def _open(payload: Mapping[str, Any], expected_format: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ProofActionCheckpointError("checkpoint must be an object")
    supplied = _copy(dict(payload))
    if supplied.get("format") != expected_format:
        raise ProofActionCheckpointError("unsupported checkpoint format")
    snapshot_digest = supplied.pop("snapshot_digest", None)
    if not _is_sha256(snapshot_digest) or snapshot_digest != _digest(supplied):
        raise ProofActionCheckpointError("checkpoint digest mismatch")
    return supplied


def _validate_channel_route(
    snapshot: Any,
    *,
    source: str,
    destination: str,
    channel: str,
    peer: str,
    policy: dict[str, int],
) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise ProofActionCheckpointError("reliable channel snapshot must be an object")
    copied = _copy(dict(snapshot))
    if (
        copied.get("source") != source
        or copied.get("destination") != destination
        or copied.get("channel") != channel
        or copied.get("peer") != peer
        or copied.get("policy") != policy
    ):
        raise ProofActionCheckpointError(
            "reliable channel route or policy does not match its endpoint"
        )
    if type(copied.get("version")) is not int:
        raise ProofActionCheckpointError("reliable channel snapshot version is invalid")
    return copied


def _verify_quarantine(
    entries: Any,
    *,
    result_channel: str,
) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise ProofActionCheckpointError("quarantined results must be an array")
    restored: list[dict[str, Any]] = []
    previous = "0" * 64
    required = {
        "sequence", "response_sequence", "channel", "attempt_id",
        "request_digest", "reason", "canonicalization", "payload",
        "payload_repr", "payload_digest", "previous_event_digest", "event_digest",
    }
    for index, raw in enumerate(entries, 1):
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise ProofActionCheckpointError("quarantine event fields are invalid")
        event = _copy(dict(raw))
        if (
            type(event["sequence"]) is not int
            or event["sequence"] != index
            or type(event["response_sequence"]) is not int
            or event["response_sequence"] <= 0
            or event["channel"] != result_channel
            or type(event["reason"]) is not str
            or not event["reason"]
            or event["previous_event_digest"] != previous
            or not _is_sha256(event["payload_digest"])
            or not _is_sha256(event["event_digest"])
        ):
            raise ProofActionCheckpointError("quarantine event coordinates are invalid")
        if event["attempt_id"] is not None and (
            type(event["attempt_id"]) is not str or not event["attempt_id"]
        ):
            raise ProofActionCheckpointError("quarantine attempt identity is invalid")
        if event["request_digest"] is not None and not _is_sha256(event["request_digest"]):
            raise ProofActionCheckpointError("quarantine request digest is invalid")

        if event["canonicalization"] == "canonical-json-v1":
            if event["payload_repr"] is not None:
                raise ProofActionCheckpointError("canonical quarantine payload has an unexpected repr")
            payload_bytes = _canonical(event["payload"]).encode("utf-8")
        elif event["canonicalization"] == "python-repr-fallback-v1":
            if event["payload"] is not None or type(event["payload_repr"]) is not str:
                raise ProofActionCheckpointError("fallback quarantine payload is incomplete")
            payload_bytes = event["payload_repr"].encode("utf-8")
        else:
            raise ProofActionCheckpointError("quarantine canonicalization is unknown")
        if hashlib.sha256(payload_bytes).hexdigest() != event["payload_digest"]:
            raise ProofActionCheckpointError("quarantine payload digest mismatch")

        core = {key: value for key, value in event.items() if key != "event_digest"}
        calculated = _digest(core)
        if calculated != event["event_digest"]:
            raise ProofActionCheckpointError("quarantine event chain digest mismatch")
        previous = event["event_digest"]
        restored.append(event)
    return restored


def snapshot_proof_action_host(host: ProofActionReliableHost) -> dict[str, Any]:
    """Export the host's session, active action, reliable channels and quarantine ledger."""
    if not isinstance(host, ProofActionReliableHost):
        raise ProofActionCheckpointError("host must be a ProofActionReliableHost")
    active = host.active_attempt
    core = {
        "format": HOST_FORMAT,
        "host_id": host.host_id,
        "worker_id": host.worker_id,
        "request_channel": host.request_channel,
        "result_channel": host.result_channel,
        "policy": _policy_payload(host.policy),
        "session": host.session.to_dict(),
        "proof_ground_digest": host.session.plan["proof_ground_digest"],
        "request_sender": host._request_sender.snapshot(),
        "result_receiver": host._result_receiver.snapshot(),
        "active_attempt_id": active.attempt_id if active is not None else None,
        "active_request": host.active_request,
        "request_sequence": host._request_sequence,
        "request_channel_failed": host.request_channel_failed,
        "quarantined_results": list(host.quarantined_results),
    }
    return _seal(core)


def restore_proof_action_host(
    snapshot: Mapping[str, Any],
    proof_ground: Any,
    transport: Transport,
    *,
    cost_model: Any | None = None,
) -> ProofActionReliableHost:
    """Restore the host against a freshly imported, digest-matching VGI ProofGround."""
    supplied = _open(snapshot, HOST_FORMAT)
    required = {
        "format", "host_id", "worker_id", "request_channel", "result_channel",
        "policy", "session", "proof_ground_digest", "request_sender",
        "result_receiver", "active_attempt_id", "active_request",
        "request_sequence", "request_channel_failed", "quarantined_results",
    }
    if set(supplied) != required:
        raise ProofActionCheckpointError("host checkpoint fields are invalid")
    for field in ("host_id", "worker_id", "request_channel", "result_channel"):
        if type(supplied[field]) is not str or not supplied[field]:
            raise ProofActionCheckpointError(f"host checkpoint {field} is invalid")
    if supplied["host_id"] == supplied["worker_id"]:
        raise ProofActionCheckpointError("host and worker identities must be distinct")
    if supplied["request_channel"] == supplied["result_channel"]:
        raise ProofActionCheckpointError("request and result channel names must be distinct")
    if not _is_sha256(supplied["proof_ground_digest"]):
        raise ProofActionCheckpointError("host ProofGround binding is invalid")
    if type(supplied["request_channel_failed"]) is not bool:
        raise ProofActionCheckpointError("host request-channel failure flag is invalid")

    policy = _policy_from_payload(supplied["policy"])
    policy_document = _policy_payload(policy)
    try:
        session = ProofAttentionSession.from_snapshot(
            supplied["session"], proof_ground, cost_model=cost_model
        )
    except (ValueError, TypeError) as exc:
        raise ProofActionCheckpointError(f"proof session restore failed: {exc}") from exc
    if session.plan["proof_ground_digest"] != supplied["proof_ground_digest"]:
        raise ProofActionCheckpointError("host ProofGround binding differs from restored session")

    host = ProofActionReliableHost(
        session,
        proof_ground,
        transport,
        host_id=supplied["host_id"],
        worker_id=supplied["worker_id"],
        request_channel=supplied["request_channel"],
        result_channel=supplied["result_channel"],
        policy=policy,
    )
    request_sender = _validate_channel_route(
        supplied["request_sender"],
        source=host.host_id,
        destination=host.worker_id,
        channel=host.request_channel,
        peer=host.worker_id,
        policy=policy_document,
    )
    result_receiver = _validate_channel_route(
        supplied["result_receiver"],
        source=host.host_id,
        destination=host.host_id,
        channel=host.result_channel,
        peer=host.worker_id,
        policy=policy_document,
    )
    host._request_sender = ReliableChannel.from_snapshot(request_sender, transport)
    host._result_receiver = ReliableChannel.from_snapshot(result_receiver, transport)

    active_id = supplied["active_attempt_id"]
    active_request = supplied["active_request"]
    request_sequence = supplied["request_sequence"]
    if active_id is None:
        if active_request is not None or request_sequence is not None:
            raise ProofActionCheckpointError("inactive host cannot retain a request or sequence")
        host._active_attempt = None
        host._active_request = None
        host._request_sequence = None
    else:
        if type(active_id) is not str or not active_id:
            raise ProofActionCheckpointError("active attempt identity is invalid")
        active = session.active_attempt
        if active is None or active.attempt_id != active_id:
            raise ProofActionCheckpointError("host active attempt does not match the restored session")
        if active.status not in ("planned", "dispatched", "admitted"):
            raise ProofActionCheckpointError("host active attempt stage cannot be resumed")
        if active_request is not None:
            try:
                normalized = validate_proof_action_request(active_request)
                expected = build_proof_action_request(session, proof_ground)
            except (ProofActionProtocolError, ValueError, TypeError) as exc:
                raise ProofActionCheckpointError(f"active request validation failed: {exc}") from exc
            if normalized != active_request or normalized != expected:
                raise ProofActionCheckpointError(
                    "active request is not the exact request reconstructed from the session and ProofGround"
                )
            host._active_request = _copy(normalized)
        else:
            host._active_request = None

        if active.status == "planned":
            if request_sequence is not None:
                raise ProofActionCheckpointError("planned attempt cannot have a reliable request sequence")
            if active_request is None:
                host._active_request = None
        else:
            if type(request_sequence) is not int or request_sequence <= 0 or active_request is None:
                raise ProofActionCheckpointError("dispatched or admitted attempt lacks request identity")
            pending = set(host._request_sender.pending_sequences())
            failed = set(host._request_sender.failed_sequences)
            if request_sequence in failed:
                raise ProofActionCheckpointError("active request sequence is already marked failed")
            if active.status == "dispatched" and request_sequence not in pending:
                raise ProofActionCheckpointError("dispatched request is not pending acknowledgement")
            if active.status == "admitted" and request_sequence in pending:
                raise ProofActionCheckpointError("admitted request is still pending acknowledgement")
        host._active_attempt = active
        host._request_sequence = request_sequence

    failed_sequences = host._request_sender.failed_sequences
    if failed_sequences and not supplied["request_channel_failed"]:
        raise ProofActionCheckpointError("host failed reliable sequence is missing its fenced flag")
    host._request_channel_failed = supplied["request_channel_failed"]
    host._quarantined_results = _verify_quarantine(
        supplied["quarantined_results"], result_channel=host.result_channel
    )
    return host


def snapshot_proof_action_worker(worker: ProofActionReliableWorker) -> dict[str, Any]:
    """Export worker admission identities, result deduplication and reliable channels."""
    if not isinstance(worker, ProofActionReliableWorker):
        raise ProofActionCheckpointError("worker must be a ProofActionReliableWorker")
    core = {
        "format": WORKER_FORMAT,
        "worker_id": worker.worker_id,
        "host_id": worker.host_id,
        "request_channel": worker.request_channel,
        "result_channel": worker.result_channel,
        "policy": _policy_payload(worker.policy),
        "request_receiver": worker._request_receiver.snapshot(),
        "result_sender": worker._result_sender.snapshot(),
        "admitted_requests": dict(sorted(worker._admitted_requests.items())),
        "result_sent_attempt_ids": sorted(worker._result_sent_attempt_ids),
        "request_channel_failed": worker.request_channel_failed,
        "result_channel_failed": worker.result_channel_failed,
    }
    return _seal(core)


def restore_proof_action_worker(
    snapshot: Mapping[str, Any],
    transport: Transport,
) -> ProofActionReliableWorker:
    """Restore worker channel cursors and application-level idempotency records."""
    supplied = _open(snapshot, WORKER_FORMAT)
    required = {
        "format", "worker_id", "host_id", "request_channel", "result_channel",
        "policy", "request_receiver", "result_sender", "admitted_requests",
        "result_sent_attempt_ids", "request_channel_failed", "result_channel_failed",
    }
    if set(supplied) != required:
        raise ProofActionCheckpointError("worker checkpoint fields are invalid")
    for field in ("worker_id", "host_id", "request_channel", "result_channel"):
        if type(supplied[field]) is not str or not supplied[field]:
            raise ProofActionCheckpointError(f"worker checkpoint {field} is invalid")
    if supplied["worker_id"] == supplied["host_id"]:
        raise ProofActionCheckpointError("worker and host identities must be distinct")
    if supplied["request_channel"] == supplied["result_channel"]:
        raise ProofActionCheckpointError("request and result channel names must be distinct")
    if type(supplied["request_channel_failed"]) is not bool or type(
        supplied["result_channel_failed"]
    ) is not bool:
        raise ProofActionCheckpointError("worker channel failure flags are invalid")
    if supplied["result_channel_failed"] and not supplied["request_channel_failed"]:
        raise ProofActionCheckpointError("failed result channel must fence the worker request route")

    policy = _policy_from_payload(supplied["policy"])
    policy_document = _policy_payload(policy)
    worker = ProofActionReliableWorker(
        transport,
        worker_id=supplied["worker_id"],
        host_id=supplied["host_id"],
        request_channel=supplied["request_channel"],
        result_channel=supplied["result_channel"],
        policy=policy,
    )
    request_receiver = _validate_channel_route(
        supplied["request_receiver"],
        source=worker.worker_id,
        destination=worker.worker_id,
        channel=worker.request_channel,
        peer=worker.host_id,
        policy=policy_document,
    )
    result_sender = _validate_channel_route(
        supplied["result_sender"],
        source=worker.worker_id,
        destination=worker.host_id,
        channel=worker.result_channel,
        peer=worker.host_id,
        policy=policy_document,
    )
    worker._request_receiver = ReliableChannel.from_snapshot(request_receiver, transport)
    worker._result_sender = ReliableChannel.from_snapshot(result_sender, transport)

    admitted = supplied["admitted_requests"]
    if not isinstance(admitted, Mapping):
        raise ProofActionCheckpointError("worker admitted request registry must be an object")
    restored_admitted: dict[str, str] = {}
    for attempt_id, request_digest in admitted.items():
        if type(attempt_id) is not str or not attempt_id or not _is_sha256(request_digest):
            raise ProofActionCheckpointError("worker admitted request identity is invalid")
        restored_admitted[attempt_id] = request_digest
    sent = supplied["result_sent_attempt_ids"]
    if not isinstance(sent, list) or any(type(item) is not str or not item for item in sent):
        raise ProofActionCheckpointError("worker result-sent attempt IDs must be strings")
    if sent != sorted(set(sent)) or not set(sent).issubset(restored_admitted):
        raise ProofActionCheckpointError("worker result-sent index is inconsistent")
    if worker._result_sender.failed_sequences and not supplied["result_channel_failed"]:
        raise ProofActionCheckpointError("worker failed result sequence is missing its fenced flag")

    worker._admitted_requests = restored_admitted
    worker._result_sent_attempt_ids = set(sent)
    worker._request_channel_failed = supplied["request_channel_failed"]
    worker._result_channel_failed = supplied["result_channel_failed"]
    return worker


def export_proof_action_checkpoint(
    host: ProofActionReliableHost,
    worker: ProofActionReliableWorker,
) -> dict[str, Any]:
    """Export a paired endpoint+transport checkpoint from one quiescent state cut.

    The host and worker must share the same Transport instance. Its snapshot is
    included so in-flight DATA and ACK mailboxes can be reconstructed as well
    as endpoint sequence cursors and application-level state.
    """
    if not isinstance(host, ProofActionReliableHost) or not isinstance(
        worker, ProofActionReliableWorker
    ):
        raise ProofActionCheckpointError("paired checkpoint requires a host and worker")
    if host.transport is not worker.transport:
        raise ProofActionCheckpointError("host and worker must share the same transport instance")
    if (
        host.host_id != worker.host_id
        or host.worker_id != worker.worker_id
        or host.request_channel != worker.request_channel
        or host.result_channel != worker.result_channel
        or _policy_payload(host.policy) != _policy_payload(worker.policy)
    ):
        raise ProofActionCheckpointError("host and worker routes or policies do not match")
    snapshot_method = getattr(host.transport, "snapshot", None)
    if not callable(snapshot_method):
        raise ProofActionCheckpointError(
            "transport backend must expose snapshot() for a paired portable checkpoint"
        )
    try:
        transport_snapshot = _copy(snapshot_method())
    except (TypeError, ValueError) as exc:
        raise ProofActionCheckpointError(f"transport snapshot is not portable JSON: {exc}") from exc
    core = {
        "format": PAIR_FORMAT,
        "host": snapshot_proof_action_host(host),
        "worker": snapshot_proof_action_worker(worker),
        "transport": transport_snapshot,
    }
    return _seal(core)


def restore_proof_action_checkpoint(
    checkpoint: Mapping[str, Any],
    proof_ground: Any,
    *,
    restore_transport: Callable[[Mapping[str, Any]], Transport],
    cost_model: Any | None = None,
) -> tuple[Transport, ProofActionReliableHost, ProofActionReliableWorker]:
    """Restore a paired checkpoint using the transport backend's explicit restorer.

    For E-CPU's deterministic InMemoryTransport, pass
    InMemoryTransport.from_snapshot. A network or durable mailbox backend must
    provide its own restorer for the transport snapshot it created.
    """
    supplied = _open(checkpoint, PAIR_FORMAT)
    if set(supplied) != {"format", "host", "worker", "transport"}:
        raise ProofActionCheckpointError("paired checkpoint fields are invalid")
    if not callable(restore_transport):
        raise ProofActionCheckpointError("restore_transport must be callable")
    transport_state = supplied["transport"]
    if not isinstance(transport_state, Mapping):
        raise ProofActionCheckpointError("transport snapshot must be an object")
    try:
        transport = restore_transport(_copy(dict(transport_state)))
    except Exception as exc:
        raise ProofActionCheckpointError(f"transport restoration failed: {exc}") from exc

    host = restore_proof_action_host(
        supplied["host"], proof_ground, transport, cost_model=cost_model
    )
    worker = restore_proof_action_worker(supplied["worker"], transport)
    if (
        host.host_id != worker.host_id
        or host.worker_id != worker.worker_id
        or host.request_channel != worker.request_channel
        or host.result_channel != worker.result_channel
        or _policy_payload(host.policy) != _policy_payload(worker.policy)
    ):
        raise ProofActionCheckpointError("restored host and worker routes do not pair")
    return transport, host, worker


__all__ = [
    "ProofActionCheckpointError",
    "snapshot_proof_action_host",
    "restore_proof_action_host",
    "snapshot_proof_action_worker",
    "restore_proof_action_worker",
    "export_proof_action_checkpoint",
    "restore_proof_action_checkpoint",
]
