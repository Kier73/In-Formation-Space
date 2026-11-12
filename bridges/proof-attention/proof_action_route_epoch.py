"""Explicit route epochs and fenced handoff for E-CPU proof-action endpoints.

A route epoch is one named pair of host/worker identities and ReliableChannel
names. Handoff preserves the old pair checkpoint and the uncertain-message
projection, closes any active action as route_closed (not as a tactic result),
then opens a successor with fresh identities and channel names.

The in-process ledger is a deterministic authority reference. Production
processes must consult a shared durable authority or lease service on every
operation; a locally cached ledger cannot fence a remote stale process by itself.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import threading
import uuid
from typing import Any, Protocol

from mailcpu.reliability import ReliabilityPolicy
from mailcpu.transport import Transport

from proof_action_checkpoint import (
    ProofActionCheckpointError,
    export_proof_action_checkpoint,
)
from proof_action_execution import ProofAttentionSession
from proof_action_reliable_channel import (
    ProofActionReliableChannelError,
    ProofActionReliableHost,
    ProofActionReliableWorker,
)


LEDGER_FORMAT = "in-formation.proof-action-route-ledger/0.1"
REASON_CODES = {
    "retry_exhaustion",
    "operator_rotation",
    "host_replacement",
    "worker_replacement",
    "transport_failure",
    "topology_change",
    "policy_change",
    "planned_migration",
}


class ProofActionRouteEpochError(ValueError):
    """A route epoch, ownership claim, or successor handoff is inconsistent."""


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
        raise ProofActionRouteEpochError(
            "route epoch values must be finite canonical JSON"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProofActionRouteEpochError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ProofActionRouteEpochError(f"{label} must be non-empty text")
    return value


def _policy_document(policy: ReliabilityPolicy) -> dict[str, int]:
    return {
        "lease_ticks": policy.lease_ticks,
        "max_attempts": policy.max_attempts,
        "window_size": policy.window_size,
    }


def _route_document(host: Any, worker: Any) -> dict[str, Any]:
    if not isinstance(host, ProofActionReliableHost) or not isinstance(
        worker, ProofActionReliableWorker
    ):
        raise ProofActionRouteEpochError("route requires a proof-action host and worker")
    if host.transport is not worker.transport:
        raise ProofActionRouteEpochError("host and worker must share one transport")
    if (
        host.host_id != worker.host_id
        or host.worker_id != worker.worker_id
        or host.request_channel != worker.request_channel
        or host.result_channel != worker.result_channel
        or _policy_document(host.policy) != _policy_document(worker.policy)
    ):
        raise ProofActionRouteEpochError("host and worker route identities or policies differ")
    return {
        "host_id": host.host_id,
        "worker_id": host.worker_id,
        "request_channel": host.request_channel,
        "result_channel": host.result_channel,
        "policy": _policy_document(host.policy),
    }


def _route_key(route: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        route["host_id"],
        route["worker_id"],
        route["request_channel"],
        route["result_channel"],
    )


def _validate_route(route: Any) -> dict[str, Any]:
    if not isinstance(route, Mapping):
        raise ProofActionRouteEpochError("route description must be an object")
    copied = _copy(dict(route))
    required = {
        "host_id", "worker_id", "request_channel", "result_channel",
        "policy",
    }
    if set(copied) != required:
        raise ProofActionRouteEpochError("route description fields are invalid")
    for field in ("host_id", "worker_id", "request_channel", "result_channel"):
        _text(copied[field], f"route.{field}")
    if copied["host_id"] == copied["worker_id"]:
        raise ProofActionRouteEpochError("host and worker identities must differ")
    if copied["request_channel"] == copied["result_channel"]:
        raise ProofActionRouteEpochError("request and result channel names must differ")
    policy = copied["policy"]
    if not isinstance(policy, Mapping) or set(policy) != {
        "lease_ticks", "max_attempts", "window_size"
    }:
        raise ProofActionRouteEpochError("route reliability policy is invalid")
    if any(type(policy[key]) is not int or policy[key] <= 0 for key in policy):
        raise ProofActionRouteEpochError("route reliability policy values must be positive integers")
    return copied


def _uncertainty_projection(pair_checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    """Retain complete pending reliable frames plus delivered/unacknowledged coordinates."""
    host = pair_checkpoint["host"]
    worker = pair_checkpoint["worker"]
    channels = {
        "host_request_sender": host["request_sender"],
        "host_result_receiver": host["result_receiver"],
        "worker_request_receiver": worker["request_receiver"],
        "worker_result_sender": worker["result_sender"],
    }
    channel_states: dict[str, Any] = {}
    pending_frames: list[dict[str, Any]] = []
    for label, raw in channels.items():
        pending = raw.get("pending", {})
        if not isinstance(pending, Mapping):
            raise ProofActionRouteEpochError("channel pending state is invalid")
        pending_records = []
        for raw_sequence, details in sorted(pending.items(), key=lambda item: int(item[0])):
            sequence = int(raw_sequence)
            record = _copy(dict(details))
            pending_records.append({"sequence": sequence, **record})
            pending_frames.append({
                "endpoint": label,
                "channel": raw.get("channel"),
                "sequence": sequence,
                "attempts": record.get("attempts"),
                "frame": record.get("frame"),
            })
        delivered = raw.get("delivered", [])
        failed = raw.get("failed_sequences", [])
        channel_states[label] = {
            "source": raw.get("source"),
            "destination": raw.get("destination"),
            "peer": raw.get("peer"),
            "channel": raw.get("channel"),
            "next_sequence": raw.get("next_sequence"),
            "next_receive_sequence": raw.get("next_receive_sequence"),
            "tick": raw.get("tick"),
            "pending": pending_records,
            "delivered": list(delivered),
            "received_digests": _copy(raw.get("received_digests", {})),
            "failed_sequences": list(failed),
        }

    transport = pair_checkpoint.get("transport", {})
    queues = transport.get("queues", {}) if isinstance(transport, Mapping) else {}
    queued_frames = []
    if isinstance(queues, Mapping):
        for address, messages in sorted(queues.items()):
            for message in messages:
                if not isinstance(message, Mapping):
                    raise ProofActionRouteEpochError("transport queue message is invalid")
                if message.get("op") not in ("RDATA", "RACK"):
                    continue
                queued_frames.append({
                    "mailbox": address,
                    "kind": message.get("op"),
                    "message": _copy(dict(message)),
                })
    return {
        "channel_states": channel_states,
        "pending_frames": pending_frames,
        "queued_reliable_frames": queued_frames,
        "uncertainty_digest": _digest({
            "channel_states": channel_states,
            "pending_frames": pending_frames,
            "queued_reliable_frames": queued_frames,
        }),
    }


def _validate_uncertainty_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProofActionRouteEpochError("uncertainty projection must be an object")
    copied = _copy(dict(value))
    required = {
        "channel_states", "pending_frames", "queued_reliable_frames", "uncertainty_digest"
    }
    if set(copied) != required:
        raise ProofActionRouteEpochError("uncertainty projection fields are invalid")
    digest = _sha256(copied["uncertainty_digest"], "uncertainty_digest")
    core = {key: item for key, item in copied.items() if key != "uncertainty_digest"}
    if _digest(core) != digest:
        raise ProofActionRouteEpochError("uncertainty projection digest mismatch")

    channel_states = copied["channel_states"]
    expected_channels = {
        "host_request_sender", "host_result_receiver",
        "worker_request_receiver", "worker_result_sender",
    }
    if not isinstance(channel_states, Mapping) or set(channel_states) != expected_channels:
        raise ProofActionRouteEpochError("uncertainty channel-state index is invalid")
    channel_fields = {
        "source", "destination", "peer", "channel", "next_sequence",
        "next_receive_sequence", "tick", "pending", "delivered",
        "received_digests", "failed_sequences",
    }
    for label, state in channel_states.items():
        if not isinstance(state, Mapping) or set(state) != channel_fields:
            raise ProofActionRouteEpochError(f"uncertainty state for {label} is invalid")
        for field in ("source", "destination", "channel"):
            _text(state[field], f"{label}.{field}")
        if state["peer"] is not None:
            _text(state["peer"], f"{label}.peer")
        for field in ("next_sequence", "next_receive_sequence"):
            if type(state[field]) is not int or state[field] <= 0:
                raise ProofActionRouteEpochError(f"{label}.{field} must be positive")
        if type(state["tick"]) is not int or state["tick"] < 0:
            raise ProofActionRouteEpochError(f"{label}.tick must be non-negative")
        if not isinstance(state["pending"], list) or not isinstance(state["delivered"], list):
            raise ProofActionRouteEpochError(f"{label} pending/delivered indexes are invalid")
        if not isinstance(state["received_digests"], Mapping):
            raise ProofActionRouteEpochError(f"{label} received digest map is invalid")
        if not isinstance(state["failed_sequences"], list):
            raise ProofActionRouteEpochError(f"{label} failed sequence index is invalid")
        sequences = []
        for pending in state["pending"]:
            if not isinstance(pending, Mapping) or set(pending) != {
                "sequence", "frame", "attempts", "last_sent_tick"
            }:
                raise ProofActionRouteEpochError(f"{label} pending frame record is invalid")
            if (
                type(pending["sequence"]) is not int or pending["sequence"] <= 0
                or type(pending["attempts"]) is not int or pending["attempts"] <= 0
                or type(pending["last_sent_tick"]) is not int or pending["last_sent_tick"] < 0
                or not isinstance(pending["frame"], Mapping)
            ):
                raise ProofActionRouteEpochError(f"{label} pending frame coordinates are invalid")
            sequences.append(pending["sequence"])
        if sequences != sorted(set(sequences)):
            raise ProofActionRouteEpochError(f"{label} pending sequence index is not ordered")
        for field in ("delivered", "failed_sequences"):
            values = state[field]
            if any(type(item) is not int or item <= 0 for item in values):
                raise ProofActionRouteEpochError(f"{label}.{field} contains an invalid sequence")
            if values != sorted(set(values)):
                raise ProofActionRouteEpochError(f"{label}.{field} must be sorted and unique")
        for key, received_digest in state["received_digests"].items():
            try:
                sequence = int(key)
            except (TypeError, ValueError) as exc:
                raise ProofActionRouteEpochError(f"{label} received digest sequence is invalid") from exc
            if sequence <= 0 or str(sequence) != str(key):
                raise ProofActionRouteEpochError(f"{label} received digest sequence is invalid")
            if received_digest is not None:
                _sha256(received_digest, f"{label}.received_digests[{key}]")

    pending_frames = copied["pending_frames"]
    queued_frames = copied["queued_reliable_frames"]
    if not isinstance(pending_frames, list) or not isinstance(queued_frames, list):
        raise ProofActionRouteEpochError("uncertainty frame indexes must be arrays")
    for frame in pending_frames:
        if not isinstance(frame, Mapping) or set(frame) != {
            "endpoint", "channel", "sequence", "attempts", "frame"
        }:
            raise ProofActionRouteEpochError("pending reliable frame projection is invalid")
        _text(frame["endpoint"], "pending_frame.endpoint")
        _text(frame["channel"], "pending_frame.channel")
        if type(frame["sequence"]) is not int or frame["sequence"] <= 0:
            raise ProofActionRouteEpochError("pending reliable frame sequence is invalid")
        if not isinstance(frame["frame"], Mapping):
            raise ProofActionRouteEpochError("pending reliable frame payload is invalid")
    for queued in queued_frames:
        if not isinstance(queued, Mapping) or set(queued) != {"mailbox", "kind", "message"}:
            raise ProofActionRouteEpochError("queued reliable frame projection is invalid")
        _text(queued["mailbox"], "queued_frame.mailbox")
        if queued["kind"] not in ("RDATA", "RACK") or not isinstance(queued["message"], Mapping):
            raise ProofActionRouteEpochError("queued reliable frame kind or message is invalid")
    return copied


def _validate_pair_checkpoint_binding(
    checkpoint: Any,
    *,
    route: Mapping[str, Any],
    preclose_session_digest: str,
) -> dict[str, Any]:
    if not isinstance(checkpoint, Mapping):
        raise ProofActionRouteEpochError("closed route pair checkpoint must be an object")
    copied = _copy(dict(checkpoint))
    if set(copied) != {"format", "host", "worker", "transport", "snapshot_digest"}:
        raise ProofActionRouteEpochError("closed route pair checkpoint fields are invalid")
    if copied["format"] != "in-formation.proof-action-pair-checkpoint/0.1":
        raise ProofActionRouteEpochError("closed route checkpoint format is unsupported")
    snapshot_digest = _sha256(copied["snapshot_digest"], "pair_checkpoint.snapshot_digest")
    core = {key: value for key, value in copied.items() if key != "snapshot_digest"}
    if _digest(core) != snapshot_digest:
        raise ProofActionRouteEpochError("closed route pair checkpoint digest mismatch")
    host = copied["host"]
    worker = copied["worker"]
    if not isinstance(host, Mapping) or not isinstance(worker, Mapping):
        raise ProofActionRouteEpochError("closed route endpoint checkpoints must be objects")
    for endpoint, label in ((host, "host"), (worker, "worker")):
        if (
            endpoint.get("host_id") != route["host_id"]
            or endpoint.get("worker_id") != route["worker_id"]
            or endpoint.get("request_channel") != route["request_channel"]
            or endpoint.get("result_channel") != route["result_channel"]
            or endpoint.get("policy") != route["policy"]
        ):
            raise ProofActionRouteEpochError(f"closed route {label} checkpoint identity differs")
    session = host.get("session")
    if not isinstance(session, Mapping) or session.get("session_digest") != preclose_session_digest:
        raise ProofActionRouteEpochError("closed route checkpoint does not match pre-close session digest")
    if not isinstance(copied["transport"], Mapping):
        raise ProofActionRouteEpochError("closed route transport checkpoint must be an object")
    return copied


def _validate_postclose_session_snapshot(
    payload: Any,
    *,
    expected_session_digest: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ProofActionRouteEpochError("post-close proof session snapshot must be an object")
    copied = _copy(dict(payload))
    required = {
        "format", "attempt_id_prefix", "query_label", "active_root_obligation_ids",
        "status", "current_proof_ground_digest", "current_plan_digest",
        "current_plan", "attempted_transition_ids", "attempts", "session_digest",
    }
    if set(copied) != required:
        raise ProofActionRouteEpochError("post-close proof session snapshot fields are invalid")
    if copied["format"] != "in-formation.proof-attention-session/0.1":
        raise ProofActionRouteEpochError("post-close proof session format is unsupported")
    digest = _sha256(copied["session_digest"], "postclose_session_snapshot.session_digest")
    core = {key: value for key, value in copied.items() if key != "session_digest"}
    if digest != expected_session_digest or _digest(core) != digest:
        raise ProofActionRouteEpochError("post-close proof session snapshot digest mismatch")
    _sha256(copied["current_proof_ground_digest"], "postclose.current_proof_ground_digest")
    _sha256(copied["current_plan_digest"], "postclose.current_plan_digest")
    if not isinstance(copied["current_plan"], Mapping):
        raise ProofActionRouteEpochError("post-close proof session current plan is invalid")
    if not isinstance(copied["attempts"], list):
        raise ProofActionRouteEpochError("post-close proof session attempts must be an array")
    if not isinstance(copied["active_root_obligation_ids"], list) or not copied["active_root_obligation_ids"]:
        raise ProofActionRouteEpochError("post-close proof session root intentions are invalid")
    return copied


class RouteEpochLedgerStore(Protocol):
    """Atomic durable authority contract for a route-epoch ledger.

    Implementations must make compare_and_swap linearizable across all hosts and
    workers. A local cache or eventually consistent document store is insufficient
    for fencing stale process owners.
    """

    def load(self) -> Mapping[str, Any] | None: ...

    def compare_and_swap(
        self,
        expected_ledger_digest: str | None,
        replacement: Mapping[str, Any],
        *,
        actor_id: str,
    ) -> bool: ...


class InMemoryRouteEpochLedgerStore:
    """Thread-safe CAS reference store for deterministic tests and simulations."""

    def __init__(self, initial: Mapping[str, Any] | None = None) -> None:
        self._lock = threading.RLock()
        self._document = None if initial is None else _copy(dict(initial))

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._document is None else _copy(self._document)

    def compare_and_swap(
        self,
        expected_ledger_digest: str | None,
        replacement: Mapping[str, Any],
        *,
        actor_id: str,
    ) -> bool:
        _text(actor_id, "actor_id")
        candidate = _copy(dict(replacement))
        if set(candidate) != {"format", "entries", "ledger_digest"}:
            raise ProofActionRouteEpochError("CAS replacement is not a route ledger document")
        supplied_digest = _sha256(candidate["ledger_digest"], "replacement.ledger_digest")
        candidate_core = {key: value for key, value in candidate.items() if key != "ledger_digest"}
        if _digest(candidate_core) != supplied_digest:
            raise ProofActionRouteEpochError("CAS replacement ledger digest is invalid")
        with self._lock:
            current_digest = (
                None if self._document is None else self._document["ledger_digest"]
            )
            if current_digest != expected_ledger_digest:
                return False
            self._document = candidate
            return True


class ProofActionRouteEpochLedger:
    """Append-only, hash-chained route ownership history with optional atomic authority."""

    def __init__(self, store: RouteEpochLedgerStore | None = None) -> None:
        self._entries: list[dict[str, Any]] = []
        self._store = store
        if store is not None:
            stored = store.load()
            if stored is not None:
                restored = type(self).from_dict(stored)
                self._entries = restored._entries

    @property
    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(_copy(item) for item in self._entries)

    @property
    def active_epoch(self) -> dict[str, Any] | None:
        active = None
        for entry in self._entries:
            if entry["event_type"] == "opened":
                active = {**entry, "owner_generation": entry["details"]["owner_generation"], "owner_id": entry["details"]["owner_id"]}
            elif entry["event_type"] == "claimed" and active is not None:
                active = {**active, "owner_generation": entry["details"]["owner_generation"], "owner_id": entry["details"]["owner_id"], "last_claim_event_digest": entry["event_digest"]}
            elif entry["event_type"] == "closed":
                active = None
        return None if active is None else _copy(active)

    def _build_event(
        self,
        *,
        sequence: int,
        previous_event_digest: str,
        event_type: str,
        epoch_id: str,
        epoch_number: int,
        route: Mapping[str, Any],
        details: Mapping[str, Any],
    ) -> dict[str, Any]:
        core = {
            "sequence": sequence,
            "event_type": event_type,
            "epoch_id": epoch_id,
            "epoch_number": epoch_number,
            "route": _copy(dict(route)),
            "route_digest": _digest(route),
            "details": _copy(dict(details)),
            "previous_event_digest": previous_event_digest,
        }
        return {**core, "event_digest": _digest(core)}

    def _append_many(
        self,
        drafts: list[tuple[str, str, int, Mapping[str, Any], Mapping[str, Any]]],
        *,
        actor_id: str,
    ) -> list[dict[str, Any]]:
        actor_id = _text(actor_id, "actor_id")
        previous = self._entries[-1]["event_digest"] if self._entries else "0" * 64
        events = []
        for offset, (event_type, epoch_id, epoch_number, route, details) in enumerate(drafts, 1):
            event = self._build_event(
                sequence=len(self._entries) + offset,
                previous_event_digest=previous,
                event_type=event_type,
                epoch_id=epoch_id,
                epoch_number=epoch_number,
                route=route,
                details=details,
            )
            events.append(event)
            previous = event["event_digest"]
        if self._store is not None:
            expected_digest = self.to_dict()["ledger_digest"] if self._entries else None
            next_entries = [*self._entries, *events]
            next_core = {"format": LEDGER_FORMAT, "entries": next_entries}
            replacement = {**next_core, "ledger_digest": _digest(next_core)}
            if not self._store.compare_and_swap(
                expected_digest, replacement, actor_id=actor_id
            ):
                raise ProofActionRouteEpochError(
                    "route ledger compare-and-swap conflict; refresh before retrying"
                )
        self._entries.extend(events)
        return [_copy(event) for event in events]

    def _append(
        self,
        event_type: str,
        epoch_id: str,
        epoch_number: int,
        route: Mapping[str, Any],
        details: Mapping[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        return self._append_many(
            [(event_type, epoch_id, epoch_number, route, details)],
            actor_id=actor_id,
        )[0]

    def refresh(self) -> None:
        """Reload the latest authoritative ledger revision from the configured store."""
        if self._store is None:
            return
        stored = self._store.load()
        if stored is None:
            if self._entries:
                raise ProofActionRouteEpochError("authoritative route ledger disappeared")
            return
        restored = type(self).from_dict(stored)
        self._entries = restored._entries

    def _all_routes(self) -> list[dict[str, Any]]:
        return [entry["route"] for entry in self._entries if entry["event_type"] == "opened"]

    def open_epoch(
        self,
        epoch_id: str,
        route: Mapping[str, Any],
        *,
        owner_id: str,
        predecessor_close_digest: str | None = None,
    ) -> dict[str, Any]:
        self.refresh()
        epoch_id = _text(epoch_id, "epoch_id")
        owner_id = _text(owner_id, "owner_id")
        checked_route = _validate_route(route)
        if any(entry["epoch_id"] == epoch_id for entry in self._entries):
            raise ProofActionRouteEpochError("route epoch IDs cannot be reused")
        if any(_route_key(old) == _route_key(checked_route) for old in self._all_routes()):
            raise ProofActionRouteEpochError("route identity tuple was already used by an earlier epoch")
        if self.active_epoch is not None:
            raise ProofActionRouteEpochError("a route epoch is already active")
        closed_entries = [entry for entry in self._entries if entry["event_type"] == "closed"]
        if closed_entries:
            previous_close = closed_entries[-1]
            expected_predecessor = previous_close["event_digest"]
            if predecessor_close_digest != expected_predecessor:
                raise ProofActionRouteEpochError("successor must reference the latest route-close event")
            if (
                epoch_id != previous_close["details"]["successor_epoch_id"]
                or checked_route != previous_close["details"]["successor_route"]
                or owner_id != previous_close["details"]["successor_owner_id"]
            ):
                raise ProofActionRouteEpochError(
                    "opened route or owner does not match the successor authorized by the close event"
                )
        elif predecessor_close_digest is not None:
            raise ProofActionRouteEpochError("initial route cannot name a predecessor close event")
        if any(
            entry["event_type"] == "opened" and entry["details"]["owner_id"] == owner_id
            or entry["event_type"] == "claimed" and entry["details"]["owner_id"] == owner_id
            for entry in self._entries
        ):
            raise ProofActionRouteEpochError("route owner ID was already used")
        epoch_number = len(self._all_routes()) + 1
        return self._append(
            "opened",
            epoch_id,
            epoch_number,
            checked_route,
            {"predecessor_close_digest": predecessor_close_digest, "owner_generation": 1, "owner_id": owner_id},
            actor_id=owner_id,
        )

    def claim_epoch(self, epoch_id: str, *, owner_id: str) -> dict[str, Any]:
        """Transfer ownership to a new process generation on the same route."""
        self.refresh()
        active = self.active_epoch
        owner_id = _text(owner_id, "owner_id")
        if active is None or active["epoch_id"] != epoch_id:
            raise ProofActionRouteEpochError("only the active route epoch can be claimed")
        if owner_id == active["owner_id"]:
            raise ProofActionRouteEpochError("new owner ID must differ from the current owner")
        return self._append(
            "claimed", epoch_id, active["epoch_number"], active["route"],
            {"owner_generation": active["owner_generation"] + 1, "previous_owner_id": active["owner_id"], "owner_id": owner_id},
            actor_id=owner_id,
        )

    def close_epoch(
        self,
        epoch_id: str,
        route: Mapping[str, Any],
        *,
        reason_code: str,
        reason: str,
        owner_id: str,
        owner_generation: int,
        pair_checkpoint: Mapping[str, Any],
        preclose_session_digest: str,
        postclose_session_digest: str,
        postclose_session_snapshot: Mapping[str, Any],
        uncertainty: Mapping[str, Any],
        successor_epoch_id: str,
        successor_owner_id: str,
        successor_route: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.refresh()
        active = self.active_epoch
        if active is None or active["epoch_id"] != epoch_id:
            raise ProofActionRouteEpochError("only the active route epoch can be closed")
        if type(owner_generation) is not int or owner_generation <= 0:
            raise ProofActionRouteEpochError("owner_generation must be a positive integer")
        if (
            active["owner_id"] != owner_id
            or active["owner_generation"] != owner_generation
        ):
            raise ProofActionRouteEpochError(
                "route close was submitted by a stale owner generation"
            )
        checked_route = _validate_route(route)
        if checked_route != active["route"]:
            raise ProofActionRouteEpochError("closing route does not match the active route binding")
        if reason_code not in REASON_CODES:
            raise ProofActionRouteEpochError("unsupported route-close reason code")
        reason = _text(reason, "reason")
        _sha256(preclose_session_digest, "preclose_session_digest")
        _sha256(postclose_session_digest, "postclose_session_digest")
        _text(successor_epoch_id, "successor_epoch_id")
        successor_owner_id = _text(successor_owner_id, "successor_owner_id")
        if any(
            entry["event_type"] == "opened" and entry["details"]["owner_id"] == successor_owner_id
            or entry["event_type"] == "claimed" and entry["details"]["owner_id"] == successor_owner_id
            for entry in self._entries
        ):
            raise ProofActionRouteEpochError("successor owner ID was already used")
        successor = _validate_route(successor_route)
        if _route_key(successor) == _route_key(checked_route):
            raise ProofActionRouteEpochError("successor must use a fresh route identity tuple")
        if any(_route_key(old) == _route_key(successor) for old in self._all_routes()):
            raise ProofActionRouteEpochError("successor route identity tuple was already used")
        if successor_epoch_id == epoch_id or any(
            entry["epoch_id"] == successor_epoch_id for entry in self._entries
        ):
            raise ProofActionRouteEpochError("successor epoch ID must be new")

        checkpoint = _copy(dict(pair_checkpoint))
        checkpoint_digest = _digest(checkpoint)
        checkpoint = _validate_pair_checkpoint_binding(
            checkpoint,
            route=checked_route,
            preclose_session_digest=preclose_session_digest,
        )
        uncertainty_copy = _validate_uncertainty_projection(uncertainty)
        expected_uncertainty = _uncertainty_projection(checkpoint)
        if uncertainty_copy != expected_uncertainty:
            raise ProofActionRouteEpochError(
                "uncertainty projection does not describe the preserved pair checkpoint"
            )
        details = {
            "owner_generation": active["owner_generation"],
            "owner_id": active["owner_id"],
            "reason_code": reason_code,
            "reason": reason,
            "preclose_session_digest": preclose_session_digest,
            "postclose_session_digest": postclose_session_digest,
            "postclose_session_snapshot": _validate_postclose_session_snapshot(
                postclose_session_snapshot,
                expected_session_digest=postclose_session_digest,
            ),
            "pair_checkpoint": checkpoint,
            "pair_checkpoint_digest": checkpoint_digest,
            "uncertainty": uncertainty_copy,
            "successor_epoch_id": successor_epoch_id,
            "successor_owner_id": successor_owner_id,
            "successor_route": successor,
        }
        return self._append(
            "closed",
            epoch_id,
            active["epoch_number"],
            checked_route,
            details,
            actor_id=owner_id,
        )

    def handoff_epoch(
        self,
        epoch_id: str,
        route: Mapping[str, Any],
        *,
        reason_code: str,
        reason: str,
        owner_id: str,
        owner_generation: int,
        pair_checkpoint: Mapping[str, Any],
        preclose_session_digest: str,
        postclose_session_digest: str,
        postclose_session_snapshot: Mapping[str, Any],
        uncertainty: Mapping[str, Any],
        successor_epoch_id: str,
        successor_owner_id: str,
        successor_route: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Atomically append a close event and its one authorized successor open.

        When a shared CAS store is configured, both events become visible in one
        revision. No competing process can insert a different route between
        closure and successor activation.
        """
        self.refresh()
        active = self.active_epoch
        if active is None or active["epoch_id"] != epoch_id:
            raise ProofActionRouteEpochError("only the active route epoch can be handed off")
        if (
            active["owner_id"] != owner_id
            or active["owner_generation"] != owner_generation
        ):
            raise ProofActionRouteEpochError(
                "route handoff was submitted by a stale owner generation"
            )
        checked_route = _validate_route(route)
        if checked_route != active["route"]:
            raise ProofActionRouteEpochError("handoff route does not match the active route")
        if reason_code not in REASON_CODES:
            raise ProofActionRouteEpochError("unsupported route-close reason code")
        reason = _text(reason, "reason")
        _sha256(preclose_session_digest, "preclose_session_digest")
        _sha256(postclose_session_digest, "postclose_session_digest")
        successor_epoch_id = _text(successor_epoch_id, "successor_epoch_id")
        successor_owner_id = _text(successor_owner_id, "successor_owner_id")
        if successor_epoch_id == epoch_id or any(
            entry["epoch_id"] == successor_epoch_id for entry in self._entries
        ):
            raise ProofActionRouteEpochError("successor epoch ID must be new")
        if any(
            (entry["event_type"] == "opened" and entry["details"]["owner_id"] == successor_owner_id)
            or (entry["event_type"] == "claimed" and entry["details"]["owner_id"] == successor_owner_id)
            for entry in self._entries
        ):
            raise ProofActionRouteEpochError("successor owner ID was already used")
        successor = _validate_route(successor_route)
        if _route_key(successor) == _route_key(checked_route):
            raise ProofActionRouteEpochError("successor must use a fresh route identity tuple")
        if any(_route_key(old) == _route_key(successor) for old in self._all_routes()):
            raise ProofActionRouteEpochError("successor route identity tuple was already used")

        checkpoint = _validate_pair_checkpoint_binding(
            pair_checkpoint,
            route=checked_route,
            preclose_session_digest=preclose_session_digest,
        )
        uncertainty_copy = _validate_uncertainty_projection(uncertainty)
        if uncertainty_copy != _uncertainty_projection(checkpoint):
            raise ProofActionRouteEpochError(
                "uncertainty projection does not describe the preserved pair checkpoint"
            )
        close_details = {
            "owner_generation": active["owner_generation"],
            "owner_id": active["owner_id"],
            "reason_code": reason_code,
            "reason": reason,
            "preclose_session_digest": preclose_session_digest,
            "postclose_session_digest": postclose_session_digest,
            "postclose_session_snapshot": _validate_postclose_session_snapshot(
                postclose_session_snapshot,
                expected_session_digest=postclose_session_digest,
            ),
            "pair_checkpoint": checkpoint,
            "pair_checkpoint_digest": _digest(checkpoint),
            "uncertainty": uncertainty_copy,
            "successor_epoch_id": successor_epoch_id,
            "successor_owner_id": successor_owner_id,
            "successor_route": successor,
        }
        close_draft = (
            "closed", epoch_id, active["epoch_number"], checked_route, close_details
        )
        open_details = {
            "predecessor_close_digest": None,  # replaced after the close event is built below
            "owner_generation": 1,
            "owner_id": successor_owner_id,
        }
        close_event = self._build_event(
            sequence=len(self._entries) + 1,
            previous_event_digest=(
                self._entries[-1]["event_digest"] if self._entries else "0" * 64
            ),
            event_type=close_draft[0],
            epoch_id=close_draft[1],
            epoch_number=close_draft[2],
            route=close_draft[3],
            details=close_draft[4],
        )
        open_details["predecessor_close_digest"] = close_event["event_digest"]
        open_draft = (
            "opened",
            successor_epoch_id,
            len(self._all_routes()) + 1,
            successor,
            open_details,
        )
        close_event, opened_event = self._append_many(
            [close_draft, open_draft],
            actor_id=owner_id,
        )
        return close_event, opened_event

    def assert_active(self, epoch_id: str, route_digest: str, *, owner_id: str, owner_generation: int) -> None:
        active = self.active_epoch
        if (
            active is None
            or active["epoch_id"] != epoch_id
            or active["route_digest"] != route_digest
            or active["owner_id"] != owner_id
            or active["owner_generation"] != owner_generation
        ):
            raise ProofActionRouteEpochError(
                f"route epoch {epoch_id!r} is closed or superseded"
            )
        if self._store is not None:
            authoritative = self._store.load()
            if authoritative is None:
                raise ProofActionRouteEpochError("authoritative route ledger is unavailable")
            current = type(self).from_dict(authoritative).active_epoch
            if (
                current is None
                or current["epoch_id"] != epoch_id
                or current["route_digest"] != route_digest
                or current["owner_id"] != owner_id
                or current["owner_generation"] != owner_generation
            ):
                raise ProofActionRouteEpochError(
                    f"route epoch {epoch_id!r} is superseded in the authoritative store"
                )

    def to_dict(self) -> dict[str, Any]:
        core = {
            "format": LEDGER_FORMAT,
            "entries": self.entries,
        }
        return {**core, "ledger_digest": _digest(core)}

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        store: RouteEpochLedgerStore | None = None,
    ) -> "ProofActionRouteEpochLedger":
        if not isinstance(payload, Mapping):
            raise ProofActionRouteEpochError("route ledger must be an object")
        supplied = _copy(dict(payload))
        if set(supplied) != {"format", "entries", "ledger_digest"}:
            raise ProofActionRouteEpochError("route ledger fields are invalid")
        if supplied["format"] != LEDGER_FORMAT:
            raise ProofActionRouteEpochError("unsupported route ledger format")
        ledger_digest = _sha256(supplied.pop("ledger_digest"), "ledger_digest")
        if _digest(supplied) != ledger_digest:
            raise ProofActionRouteEpochError("route ledger digest mismatch")
        raw_entries = supplied["entries"]
        if not isinstance(raw_entries, list):
            raise ProofActionRouteEpochError("route ledger entries must be an array")

        restored = cls()
        active: dict[str, Any] | None = None
        used_epoch_ids: set[str] = set()
        used_route_keys: set[tuple[str, str, str, str]] = set()
        used_owner_ids: set[str] = set()
        last_close_digest: str | None = None
        for index, raw in enumerate(raw_entries, 1):
            if not isinstance(raw, Mapping):
                raise ProofActionRouteEpochError("route ledger event must be an object")
            event = _copy(dict(raw))
            required = {
                "sequence", "event_type", "epoch_id", "epoch_number", "route",
                "route_digest", "details", "previous_event_digest", "event_digest",
            }
            if set(event) != required:
                raise ProofActionRouteEpochError("route ledger event fields are invalid")
            if type(event["sequence"]) is not int or event["sequence"] != index:
                raise ProofActionRouteEpochError("route ledger sequence is not contiguous")
            if type(event["epoch_number"]) is not int or event["epoch_number"] <= 0:
                raise ProofActionRouteEpochError("route ledger epoch number is invalid")
            _text(event["epoch_id"], "event.epoch_id")
            route = _validate_route(event["route"])
            if event["route_digest"] != _digest(route):
                raise ProofActionRouteEpochError("route ledger route digest mismatch")
            previous = restored._entries[-1]["event_digest"] if restored._entries else "0" * 64
            if event["previous_event_digest"] != previous:
                raise ProofActionRouteEpochError("route ledger event chain predecessor mismatch")
            core = {key: value for key, value in event.items() if key != "event_digest"}
            if _sha256(event["event_digest"], "event_digest") != _digest(core):
                raise ProofActionRouteEpochError("route ledger event digest mismatch")
            details = event["details"]
            if not isinstance(details, Mapping):
                raise ProofActionRouteEpochError("route ledger event details must be an object")

            if event["event_type"] == "opened":
                if set(details) != {"predecessor_close_digest", "owner_generation", "owner_id"}:
                    raise ProofActionRouteEpochError("opened route event details are invalid")
                if active is not None:
                    raise ProofActionRouteEpochError("route ledger opens an epoch before closing its predecessor")
                if event["epoch_id"] in used_epoch_ids or _route_key(route) in used_route_keys:
                    raise ProofActionRouteEpochError("route ledger reuses an epoch or route identity")
                if event["epoch_number"] != len(used_epoch_ids) + 1:
                    raise ProofActionRouteEpochError("route epoch number is not contiguous")
                predecessor = details.get("predecessor_close_digest")
                if predecessor != last_close_digest:
                    raise ProofActionRouteEpochError("route successor predecessor reference is invalid")
                if last_close_digest is not None:
                    previous_close = restored._entries[-1]
                    if (
                        previous_close["event_type"] != "closed"
                        or event["epoch_id"] != previous_close["details"]["successor_epoch_id"]
                        or route != previous_close["details"]["successor_route"]
                        or details.get("owner_id") != previous_close["details"]["successor_owner_id"]
                    ):
                        raise ProofActionRouteEpochError(
                            "route open does not match its close-authorized successor"
                        )
                if type(details.get("owner_generation")) is not int or details["owner_generation"] != 1:
                    raise ProofActionRouteEpochError("new epoch must begin at owner generation one")
                owner = _text(details.get("owner_id"), "opened.owner_id")
                if owner in used_owner_ids:
                    raise ProofActionRouteEpochError("route owner ID was already used")
                used_owner_ids.add(owner)
                used_epoch_ids.add(event["epoch_id"])
                used_route_keys.add(_route_key(route))
                active = event
            elif event["event_type"] == "claimed":
                if set(details) != {"owner_generation", "previous_owner_id", "owner_id"}:
                    raise ProofActionRouteEpochError("claimed route event details are invalid")
                if active is None or active["epoch_id"] != event["epoch_id"]:
                    raise ProofActionRouteEpochError("route claim targets a non-active epoch")
                if event["epoch_number"] != active["epoch_number"] or route != active["route"]:
                    raise ProofActionRouteEpochError("route claim differs from active route")
                if type(details.get("owner_generation")) is not int or details["owner_generation"] != active["details"]["owner_generation"] + 1:
                    raise ProofActionRouteEpochError("route owner generation is not monotonic")
                if details.get("previous_owner_id") != active["details"]["owner_id"]:
                    raise ProofActionRouteEpochError("route claim omits the prior owner")
                new_owner = _text(details.get("owner_id"), "claim.owner_id")
                if new_owner in used_owner_ids:
                    raise ProofActionRouteEpochError("route claim reuses a historical owner ID")
                used_owner_ids.add(new_owner)
                active = event
            elif event["event_type"] == "closed":
                expected_close_fields = {
                    "owner_generation", "owner_id", "reason_code", "reason",
                    "preclose_session_digest", "postclose_session_digest",
                    "postclose_session_snapshot", "pair_checkpoint", "pair_checkpoint_digest", "uncertainty",
                    "successor_epoch_id", "successor_owner_id", "successor_route",
                }
                if set(details) != expected_close_fields:
                    raise ProofActionRouteEpochError("closed route event details are invalid")
                if active is None or active["epoch_id"] != event["epoch_id"]:
                    raise ProofActionRouteEpochError("route ledger closes a non-active epoch")
                if event["epoch_number"] != active["epoch_number"] or route != active["route"]:
                    raise ProofActionRouteEpochError("route ledger close does not match its open event")
                if details.get("owner_generation") != active["details"]["owner_generation"] or details.get("owner_id") != active["details"]["owner_id"]:
                    raise ProofActionRouteEpochError("route close does not match current owner")
                preclose_digest = _sha256(details.get("preclose_session_digest"), "preclose_session_digest")
                postclose_digest = _sha256(details.get("postclose_session_digest"), "postclose_session_digest")
                _validate_postclose_session_snapshot(
                    details.get("postclose_session_snapshot"),
                    expected_session_digest=postclose_digest,
                )
                checkpoint = _validate_pair_checkpoint_binding(
                    details.get("pair_checkpoint"),
                    route=route,
                    preclose_session_digest=preclose_digest,
                )
                checkpoint_digest = _sha256(details.get("pair_checkpoint_digest"), "pair_checkpoint_digest")
                if _digest(checkpoint) != checkpoint_digest:
                    raise ProofActionRouteEpochError("closed route checkpoint digest mismatch")
                uncertainty = _validate_uncertainty_projection(details.get("uncertainty"))
                if uncertainty != _uncertainty_projection(checkpoint):
                    raise ProofActionRouteEpochError(
                        "closed route uncertainty does not match its preserved pair checkpoint"
                    )
                successor = _validate_route(details.get("successor_route"))
                if _route_key(successor) == _route_key(route) or _route_key(successor) in used_route_keys:
                    raise ProofActionRouteEpochError("closed route successor identity was already used")
                successor_epoch = _text(details.get("successor_epoch_id"), "successor_epoch_id")
                if successor_epoch == event["epoch_id"] or successor_epoch in used_epoch_ids:
                    raise ProofActionRouteEpochError("closed route successor epoch ID was already used")
                successor_owner = _text(details.get("successor_owner_id"), "successor_owner_id")
                if successor_owner in used_owner_ids:
                    raise ProofActionRouteEpochError("closed route successor owner ID was already used")
                if _route_key(successor) == _route_key(route):
                    raise ProofActionRouteEpochError("closed route cannot authorize itself as successor")
                _text(details.get("reason"), "close.reason")
                if details.get("reason_code") not in REASON_CODES:
                    raise ProofActionRouteEpochError("route close reason code is invalid")
                active = None
                last_close_digest = event["event_digest"]
            else:
                raise ProofActionRouteEpochError("unknown route ledger event type")
            restored._entries.append(event)
        if restored.to_dict()["ledger_digest"] != ledger_digest:
            raise ProofActionRouteEpochError("restored route ledger digest mismatch")
        if store is not None:
            authoritative = store.load()
            if authoritative is None or authoritative.get("ledger_digest") != ledger_digest:
                raise ProofActionRouteEpochError(
                    "supplied route ledger does not match the authoritative store revision"
                )
            restored._store = store
        return restored


@dataclass(frozen=True)
class ProofActionRouteHandoff:
    closed_epoch: dict[str, Any]
    opened_epoch: dict[str, Any]
    host: ProofActionReliableHost
    worker: ProofActionReliableWorker


def _attach_route_guard(
    host: ProofActionReliableHost,
    worker: ProofActionReliableWorker,
    ledger: ProofActionRouteEpochLedger,
    epoch_id: str,
    owner_id: str,
    owner_generation: int,
) -> None:
    route = _route_document(host, worker)
    route_digest = _digest(route)

    def guard(candidate_epoch_id: str | None) -> None:
        if candidate_epoch_id != epoch_id:
            raise ProofActionRouteEpochError("endpoint route epoch binding was changed")
        ledger.assert_active(epoch_id, route_digest, owner_id=owner_id, owner_generation=owner_generation)

    host._route_epoch_id = epoch_id
    worker._route_epoch_id = epoch_id
    host._route_guard = guard
    worker._route_guard = guard


def open_proof_action_route_epoch(
    host: ProofActionReliableHost,
    worker: ProofActionReliableWorker,
    ledger: ProofActionRouteEpochLedger,
    *,
    epoch_id: str,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Register the initial route epoch and attach operation guards to both endpoints."""
    if not isinstance(ledger, ProofActionRouteEpochLedger):
        raise ProofActionRouteEpochError("ledger must be a ProofActionRouteEpochLedger")
    if getattr(host, "_route_guard", None) is not None or getattr(
        worker, "_route_guard", None
    ) is not None:
        raise ProofActionRouteEpochError("endpoint is already bound to a route epoch")
    route = _route_document(host, worker)
    owner_id = owner_id or f"owner-{uuid.uuid4().hex}"
    event = ledger.open_epoch(epoch_id, route, owner_id=owner_id)
    _attach_route_guard(host, worker, ledger, epoch_id, owner_id, 1)
    return event


def bind_existing_proof_action_route_epoch(
    host: ProofActionReliableHost,
    worker: ProofActionReliableWorker,
    ledger: ProofActionRouteEpochLedger,
    *,
    epoch_id: str,
) -> None:
    """Reattach guards after checkpoint restoration against a separately restored ledger."""
    active = ledger.active_epoch
    route = _route_document(host, worker)
    if (
        active is None
        or active["epoch_id"] != epoch_id
        or active["route"] != route
    ):
        raise ProofActionRouteEpochError("restored endpoints do not match the active route epoch")
    owner_id = f"owner-{uuid.uuid4().hex}"
    claimed = ledger.claim_epoch(epoch_id, owner_id=owner_id)
    _attach_route_guard(host, worker, ledger, epoch_id, owner_id, claimed["details"]["owner_generation"])


def restore_proof_action_route_handoff(
    close_event: Mapping[str, Any],
    ledger: ProofActionRouteEpochLedger,
    proof_ground: Any,
    *,
    restore_transport: Any,
    owner_id: str | None = None,
    cost_model: Any | None = None,
) -> tuple[Transport, ProofActionReliableHost, ProofActionReliableWorker]:
    """Recover the authorized successor after a crash immediately following handoff commit.

    The close event contains both the old transport checkpoint and the validated
    post-close ProofAttentionSession snapshot. This function restores the
    transport/session, verifies that the successor epoch is still the active
    authorized route, then claims it under a fresh owner generation.
    """
    if not isinstance(ledger, ProofActionRouteEpochLedger):
        raise ProofActionRouteEpochError("ledger must be a ProofActionRouteEpochLedger")
    if not callable(restore_transport):
        raise ProofActionRouteEpochError("restore_transport must be callable")
    if not isinstance(close_event, Mapping):
        raise ProofActionRouteEpochError("close event must be an object")
    supplied = _copy(dict(close_event))
    matches = [
        entry for entry in ledger.entries
        if entry["event_digest"] == supplied.get("event_digest")
    ]
    if len(matches) != 1 or matches[0] != supplied or supplied.get("event_type") != "closed":
        raise ProofActionRouteEpochError("close event is not an exact verified ledger record")

    details = supplied["details"]
    successor_epoch_id = _text(details.get("successor_epoch_id"), "successor_epoch_id")
    successor_route = _validate_route(details.get("successor_route"))
    active = ledger.active_epoch
    if (
        active is None
        or active["epoch_id"] != successor_epoch_id
        or active["route"] != successor_route
    ):
        raise ProofActionRouteEpochError(
            "handoff successor is no longer the active route epoch"
        )

    session_snapshot = _validate_postclose_session_snapshot(
        details.get("postclose_session_snapshot"),
        expected_session_digest=details["postclose_session_digest"],
    )
    try:
        session = ProofAttentionSession.from_snapshot(
            session_snapshot,
            proof_ground,
            cost_model=cost_model,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProofActionRouteEpochError(
            f"post-close proof session could not be restored against the supplied ProofGround: {exc}"
        ) from exc
    if session.to_dict()["session_digest"] != details["postclose_session_digest"]:
        raise ProofActionRouteEpochError("restored successor session digest differs from close event")

    pair_checkpoint = details["pair_checkpoint"]
    transport_snapshot = pair_checkpoint.get("transport")
    if not isinstance(transport_snapshot, Mapping):
        raise ProofActionRouteEpochError("closed route lacks its transport checkpoint")
    try:
        transport = restore_transport(_copy(dict(transport_snapshot)))
    except Exception as exc:
        raise ProofActionRouteEpochError(f"handoff transport restoration failed: {exc}") from exc

    policy = ReliabilityPolicy(**successor_route["policy"])
    host = ProofActionReliableHost(
        session,
        proof_ground,
        transport,
        host_id=successor_route["host_id"],
        worker_id=successor_route["worker_id"],
        request_channel=successor_route["request_channel"],
        result_channel=successor_route["result_channel"],
        policy=policy,
    )
    worker = ProofActionReliableWorker(
        transport,
        worker_id=successor_route["worker_id"],
        host_id=successor_route["host_id"],
        request_channel=successor_route["request_channel"],
        result_channel=successor_route["result_channel"],
        policy=policy,
    )
    new_owner_id = owner_id or f"owner-{uuid.uuid4().hex}"
    claimed = ledger.claim_epoch(successor_epoch_id, owner_id=new_owner_id)
    _attach_route_guard(
        host,
        worker,
        ledger,
        successor_epoch_id,
        new_owner_id,
        claimed["details"]["owner_generation"],
    )
    return transport, host, worker


def handoff_proof_action_route_epoch(
    host: ProofActionReliableHost,
    worker: ProofActionReliableWorker,
    ledger: ProofActionRouteEpochLedger,
    *,
    epoch_id: str,
    reason_code: str,
    reason: str,
    successor_epoch_id: str,
    successor_host_id: str,
    successor_worker_id: str,
    successor_request_channel: str,
    successor_result_channel: str,
) -> ProofActionRouteHandoff:
    """Atomically close a route and activate its pre-authorized successor.

    The successor session is prepared from a verified clone before the CAS
    commit. A failed owner check or store revision leaves the caller's live
    session untouched. The close and open events are appended in one ledger
    revision when a shared CAS store is configured.
    """
    active = ledger.active_epoch
    current_route = _route_document(host, worker)
    if active is None or active["epoch_id"] != epoch_id or active["route"] != current_route:
        raise ProofActionRouteEpochError("handoff source is not the active route epoch")
    ledger.assert_active(
        epoch_id,
        active["route_digest"],
        owner_id=active["owner_id"],
        owner_generation=active["owner_generation"],
    )

    try:
        preclose_checkpoint = export_proof_action_checkpoint(host, worker)
    except (ProofActionCheckpointError, ValueError, TypeError) as exc:
        raise ProofActionRouteEpochError(
            f"could not preserve old route checkpoint: {exc}"
        ) from exc
    uncertainty = _uncertainty_projection(preclose_checkpoint)
    preclose_session_document = host.session.to_dict()
    preclose_session_digest = preclose_session_document["session_digest"]

    successor_route = _validate_route({
        "host_id": _text(successor_host_id, "successor_host_id"),
        "worker_id": _text(successor_worker_id, "successor_worker_id"),
        "request_channel": _text(successor_request_channel, "successor_request_channel"),
        "result_channel": _text(successor_result_channel, "successor_result_channel"),
        "policy": _policy_document(host.policy),
    })
    if reason_code not in REASON_CODES:
        raise ProofActionRouteEpochError("unsupported route-close reason code")
    reason = _text(reason, "reason")
    successor_epoch_id = _text(successor_epoch_id, "successor_epoch_id")
    if _route_key(successor_route) in {_route_key(old) for old in ledger._all_routes()}:
        raise ProofActionRouteEpochError("successor route identity tuple was already used")
    if successor_epoch_id == epoch_id or any(
        item["epoch_id"] == successor_epoch_id for item in ledger.entries
    ):
        raise ProofActionRouteEpochError("successor epoch ID must be new")

    try:
        successor_session = ProofAttentionSession.from_snapshot(
            preclose_session_document,
            host.proof_ground,
            cost_model=getattr(host.session, "_cost_model", None),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProofActionRouteEpochError(
            f"could not prepare a verified successor proof session: {exc}"
        ) from exc

    carried_attempt = successor_session.active_attempt
    if carried_attempt is not None and not carried_attempt.terminal:
        if carried_attempt.status != "planned":
            carried_attempt.mark_failure(
                "route_closed",
                host.host_id,
                f"route epoch {epoch_id} closed while action was at stage {carried_attempt.status}: {reason}",
                evidence_ref=f"urn:sha256:{uncertainty['uncertainty_digest']}",
            )
    postclose_session_digest = successor_session.to_dict()["session_digest"]
    successor_owner_id = f"owner-{uuid.uuid4().hex}"

    try:
        close_event, opened_event = ledger.handoff_epoch(
            epoch_id,
            current_route,
            reason_code=reason_code,
            reason=reason,
            owner_id=active["owner_id"],
            owner_generation=active["owner_generation"],
            pair_checkpoint=preclose_checkpoint,
            preclose_session_digest=preclose_session_digest,
            postclose_session_digest=postclose_session_digest,
            postclose_session_snapshot=successor_session.to_dict(),
            uncertainty=uncertainty,
            successor_epoch_id=successor_epoch_id,
            successor_owner_id=successor_owner_id,
            successor_route=successor_route,
        )
    except ProofActionRouteEpochError:
        # The successor copy has not been installed, and the original live
        # session/endpoint objects remain unchanged.
        raise

    # The authority has committed both the close and exact successor open in
    # one append/CAS revision. Retire old local pointers only after that commit.
    host.session = successor_session
    host._clear_active()

    successor_host = ProofActionReliableHost(
        successor_session,
        host.proof_ground,
        host.transport,
        host_id=successor_host_id,
        worker_id=successor_worker_id,
        request_channel=successor_request_channel,
        result_channel=successor_result_channel,
        policy=host.policy,
    )
    successor_worker = ProofActionReliableWorker(
        host.transport,
        worker_id=successor_worker_id,
        host_id=successor_host_id,
        request_channel=successor_request_channel,
        result_channel=successor_result_channel,
        policy=host.policy,
    )
    _attach_route_guard(
        successor_host,
        successor_worker,
        ledger,
        successor_epoch_id,
        successor_owner_id,
        1,
    )
    return ProofActionRouteHandoff(
        closed_epoch=close_event,
        opened_epoch=opened_event,
        host=successor_host,
        worker=successor_worker,
    )

__all__ = [
    "LEDGER_FORMAT",
    "REASON_CODES",
    "RouteEpochLedgerStore",
    "InMemoryRouteEpochLedgerStore",
    "ProofActionRouteEpochError",
    "ProofActionRouteEpochLedger",
    "ProofActionRouteHandoff",
    "open_proof_action_route_epoch",
    "bind_existing_proof_action_route_epoch",
    "restore_proof_action_route_handoff",
    "handoff_proof_action_route_epoch",
]
