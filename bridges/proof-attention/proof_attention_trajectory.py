"""Persist proof-attention sessions through E-CPU's trajectory and journal formats.

The trajectory is an ordered projection of proof-action attempt events. Restore
reconstructs the original session snapshot and delegates its semantic checks
to ProofAttentionSession.from_snapshot against a freshly imported VGI Ground.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mailcpu.journal import EventJournal
from mailcpu.trajectory import TrajectoryError, TrajectoryReader, TrajectoryWriter

from proof_action_execution import ProofAttentionSession


MANIFEST_SCHEMA = "in-formation.proof-attention-trajectory-manifest/0.1"
FRAME_SCHEMA = "in-formation.proof-attention-trajectory-frame/0.1"
ZERO_RECEIPT = "0" * 64


class ProofAttentionTrajectoryError(ValueError):
    """Invalid proof-attention trajectory, manifest, journal projection, or restore."""


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
        raise ProofAttentionTrajectoryError(
            "trajectory document must be finite canonical JSON"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ProofAttentionTrajectoryError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive_int(value: Any, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ProofAttentionTrajectoryError(f"{label} must be a {qualifier} integer")
    return value


def _journal_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": event["attempt_id"],
        "attempt_event_sequence": event["sequence"],
        "actor": event["actor"],
        "evidence_ref": event["evidence_ref"],
        "details": event["details"],
        "previous_event_digest": event["previous_event_digest"],
        "attempt_event_digest": event["event_digest"],
    }


def _event_journal_head(events: list[Mapping[str, Any]]) -> str:
    journal = EventJournal()
    for event in events:
        journal.append(event["stage"], _journal_payload(event))
    if not journal.verify():
        raise ProofAttentionTrajectoryError("EventJournal projection failed verification")
    records = journal.records()
    return records[-1].digest if records else ZERO_RECEIPT


def _atomic_write_json(path: str | Path, document: Mapping[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        document,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=str(destination.parent),
            text=True,
        )
        temporary_path = Path(raw_path)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _snapshot_from_session(session_or_snapshot: Any) -> dict[str, Any]:
    if callable(getattr(session_or_snapshot, "to_dict", None)):
        snapshot = session_or_snapshot.to_dict()
    else:
        snapshot = session_or_snapshot
    if not isinstance(snapshot, Mapping):
        raise ProofAttentionTrajectoryError("session must expose a JSON snapshot")
    return _copy(dict(snapshot))


def export_proof_attention_trajectory(
    session_or_snapshot: Any,
    proof_ground: Any,
    data_path: str | Path,
    index_path: str | Path,
    manifest_path: str | Path,
    *,
    stride: int = 64,
    cost_model: Any | None = None,
) -> dict[str, Any]:
    """Persist a verified proof-attention session as indexed events and a manifest.

    Logical time is the one-based append order within this session snapshot. It
    is a local event coordinate, not elapsed time or a cross-process clock.
    """
    if type(stride) is not int or stride <= 0:
        raise ProofAttentionTrajectoryError("stride must be a positive integer")
    supplied_snapshot = _snapshot_from_session(session_or_snapshot)
    try:
        verified_session = ProofAttentionSession.from_snapshot(
            supplied_snapshot,
            proof_ground,
            cost_model=cost_model,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProofAttentionTrajectoryError(
            f"session snapshot does not match the supplied ProofGround: {exc}"
        ) from exc
    snapshot = verified_session.to_dict()

    attempts = snapshot["attempts"]
    attempt_headers = []
    flat_events: list[dict[str, Any]] = []
    event_owners: list[tuple[int, str]] = []
    for attempt_index, attempt in enumerate(attempts, start=1):
        attempt_headers.append({
            key: value for key, value in attempt.items() if key != "events"
        })
        for event in attempt["events"]:
            flat_events.append(_copy(event))
            event_owners.append((attempt_index, attempt["attempt_id"]))

    receipt_head = ZERO_RECEIPT
    observed_receipts: list[str] = []
    try:
        with TrajectoryWriter(data_path, index_path, stride=stride) as writer:
            for event_index, (event, (attempt_index, attempt_id)) in enumerate(
                zip(flat_events, event_owners),
                start=1,
            ):
                payload = {
                    "schema": FRAME_SCHEMA,
                    "session_snapshot_digest": snapshot["session_digest"],
                    "session_event_sequence": event_index,
                    "attempt_sequence": attempt_index,
                    "attempt_id": attempt_id,
                    "attempt_event_sequence": event["sequence"],
                    "attempt_event_digest": event["event_digest"],
                    "session_event": event,
                }
                frame = writer.append(event_index, payload)
                receipt_head = frame.receipt.hex()
    except (TrajectoryError, OSError, TypeError, ValueError) as exc:
        raise ProofAttentionTrajectoryError("could not write proof-attention trajectory") from exc

    try:
        with TrajectoryReader(data_path, index_path) as reader:
            verified_count = reader.verify()
            replayed_count = reader.replay(
                lambda frame: observed_receipts.append(frame.receipt.hex())
            )
    except (TrajectoryError, OSError) as exc:
        raise ProofAttentionTrajectoryError(
            "newly written proof-attention trajectory failed receipt verification"
        ) from exc

    if (
        verified_count != len(flat_events)
        or replayed_count != len(flat_events)
        or (observed_receipts[-1] if observed_receipts else ZERO_RECEIPT) != receipt_head
    ):
        raise ProofAttentionTrajectoryError(
            "trajectory frame count or receipt head differs from the session event stream"
        )

    journal_head = _event_journal_head(flat_events)
    session_core = {
        key: value
        for key, value in snapshot.items()
        if key not in ("attempts", "session_digest")
    }
    session_section = {
        "session_core": session_core,
        "attempt_headers": attempt_headers,
        "attempt_count": len(attempt_headers),
        "event_count": len(flat_events),
        "session_digest": snapshot["session_digest"],
    }
    trajectory_section = {
        "event_count": len(flat_events),
        "stride": stride,
        "receipt_head": receipt_head,
        "journal_head_digest": journal_head,
        "first_logical_time": 1 if flat_events else None,
        "last_logical_time": len(flat_events) if flat_events else None,
    }
    manifest_core = {
        "schema": MANIFEST_SCHEMA,
        "session": session_section,
        "trajectory": trajectory_section,
    }
    manifest = {**manifest_core, "manifest_digest": _digest(manifest_core)}
    _atomic_write_json(manifest_path, manifest)
    return _copy(manifest)


def restore_proof_attention_trajectory(
    manifest_path: str | Path,
    data_path: str | Path,
    index_path: str | Path,
    proof_ground: Any,
    *,
    cost_model: Any | None = None,
) -> ProofAttentionSession:
    """Reconstruct and restore a session after checking trajectory and journal views."""
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofAttentionTrajectoryError("proof-attention trajectory manifest is unreadable") from exc

    required = {"schema", "session", "trajectory", "manifest_digest"}
    if not isinstance(manifest, Mapping) or set(manifest) != required:
        raise ProofAttentionTrajectoryError("proof-attention trajectory manifest fields are invalid")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ProofAttentionTrajectoryError("unsupported proof-attention trajectory schema")
    manifest_core = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if _sha256(manifest["manifest_digest"], "manifest_digest") != _digest(manifest_core):
        raise ProofAttentionTrajectoryError("proof-attention trajectory manifest digest mismatch")

    session_section = manifest["session"]
    trajectory = manifest["trajectory"]
    if not isinstance(session_section, Mapping) or not isinstance(trajectory, Mapping):
        raise ProofAttentionTrajectoryError("manifest session or trajectory section is invalid")
    if set(session_section) != {
        "session_core", "attempt_headers", "attempt_count", "event_count", "session_digest"
    }:
        raise ProofAttentionTrajectoryError("manifest session fields are invalid")
    if set(trajectory) != {
        "event_count", "stride", "receipt_head", "journal_head_digest",
        "first_logical_time", "last_logical_time",
    }:
        raise ProofAttentionTrajectoryError("manifest trajectory fields are invalid")

    session_core = session_section["session_core"]
    headers = session_section["attempt_headers"]
    if not isinstance(session_core, Mapping) or not isinstance(headers, list):
        raise ProofAttentionTrajectoryError("manifest session core or attempt headers are invalid")
    expected_attempt_count = _positive_int(
        session_section["attempt_count"], "attempt_count", allow_zero=True
    )
    expected_event_count = _positive_int(
        session_section["event_count"], "event_count", allow_zero=True
    )
    _sha256(session_section["session_digest"], "session_digest")
    if len(headers) != expected_attempt_count:
        raise ProofAttentionTrajectoryError("manifest attempt count is inconsistent")
    trajectory_event_count = _positive_int(
        trajectory["event_count"], "trajectory.event_count", allow_zero=True
    )
    if trajectory_event_count != expected_event_count:
        raise ProofAttentionTrajectoryError("manifest session and trajectory event counts disagree")
    stride = _positive_int(trajectory["stride"], "trajectory.stride")
    receipt_head_expected = _sha256(trajectory["receipt_head"], "trajectory.receipt_head")
    journal_head_expected = _sha256(
        trajectory["journal_head_digest"], "trajectory.journal_head_digest"
    )
    expected_first = 1 if expected_event_count else None
    expected_last = expected_event_count if expected_event_count else None
    if (
        trajectory["first_logical_time"] != expected_first
        or trajectory["last_logical_time"] != expected_last
    ):
        raise ProofAttentionTrajectoryError("manifest logical-time range is inconsistent")

    header_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, raw_header in enumerate(headers, start=1):
        if not isinstance(raw_header, Mapping):
            raise ProofAttentionTrajectoryError("attempt header must be an object")
        header = _copy(dict(raw_header))
        attempt_id = header.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id or attempt_id in header_by_id:
            raise ProofAttentionTrajectoryError("attempt headers must have unique IDs")
        header_by_id[attempt_id] = (index, header)

    events_by_attempt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    flat_events: list[dict[str, Any]] = []
    observed_receipts: list[str] = []
    last_attempt_sequence = [0]
    try:
        with TrajectoryReader(data_path, index_path) as reader:
            if reader.stride != stride:
                raise ProofAttentionTrajectoryError("trajectory index stride does not match manifest")
            verified_count = reader.verify()

            def collect(frame) -> None:
                payload = frame.payload
                if (
                    not isinstance(payload, Mapping)
                    or set(payload) != {
                        "schema", "session_snapshot_digest", "session_event_sequence",
                        "attempt_sequence", "attempt_id", "attempt_event_sequence",
                        "attempt_event_digest", "session_event",
                    }
                    or payload["schema"] != FRAME_SCHEMA
                ):
                    raise ProofAttentionTrajectoryError(
                        "trajectory frame fields or schema are invalid"
                    )
                event = payload["session_event"]
                if not isinstance(event, Mapping):
                    raise ProofAttentionTrajectoryError("trajectory frame event is invalid")
                event_copy = _copy(dict(event))
                global_sequence = frame.sequence + 1
                if (
                    payload["session_snapshot_digest"] != session_section["session_digest"]
                    or type(payload["session_event_sequence"]) is not int
                    or payload["session_event_sequence"] != global_sequence
                    or frame.logical_time != global_sequence
                    or type(payload["attempt_sequence"]) is not int
                    or payload["attempt_id"] not in header_by_id
                    or payload["attempt_sequence"] != header_by_id[payload["attempt_id"]][0]
                    or event_copy.get("attempt_id") != payload["attempt_id"]
                    or type(payload["attempt_event_sequence"]) is not int
                    or type(event_copy.get("sequence")) is not int
                    or event_copy.get("sequence") != payload["attempt_event_sequence"]
                    or event_copy.get("event_digest") != payload["attempt_event_digest"]
                ):
                    raise ProofAttentionTrajectoryError(
                        f"trajectory frame {frame.sequence} does not match its session event"
                    )
                attempt_sequence = payload["attempt_sequence"]
                if attempt_sequence < last_attempt_sequence[0]:
                    raise ProofAttentionTrajectoryError(
                        "trajectory frames interleave attempt event groups"
                    )
                last_attempt_sequence[0] = attempt_sequence
                attempt_id = payload["attempt_id"]
                events_by_attempt[attempt_id].append(event_copy)
                flat_events.append(event_copy)
                observed_receipts.append(frame.receipt.hex())

            replayed_count = reader.replay(collect)
    except ProofAttentionTrajectoryError:
        raise
    except (TrajectoryError, OSError, KeyError, TypeError, ValueError) as exc:
        raise ProofAttentionTrajectoryError(
            "proof-attention trajectory receipt or frame verification failed"
        ) from exc

    if (
        verified_count != expected_event_count
        or replayed_count != expected_event_count
        or len(flat_events) != expected_event_count
    ):
        raise ProofAttentionTrajectoryError("trajectory event count does not match manifest")
    receipt_head = observed_receipts[-1] if observed_receipts else ZERO_RECEIPT
    if receipt_head != receipt_head_expected:
        raise ProofAttentionTrajectoryError("trajectory receipt head does not match manifest")

    reconstructed_attempts = []
    for attempt_id, (attempt_sequence, header) in header_by_id.items():
        attempt_events = events_by_attempt.get(attempt_id, [])
        if not attempt_events:
            raise ProofAttentionTrajectoryError(f"attempt {attempt_id} has no trajectory events")
        sequences = [event.get("sequence") for event in attempt_events]
        if sequences != list(range(1, len(attempt_events) + 1)):
            raise ProofAttentionTrajectoryError(f"attempt {attempt_id} event sequence is incomplete")
        reconstructed_attempts.append({**header, "events": attempt_events})

    if len(reconstructed_attempts) != expected_attempt_count:
        raise ProofAttentionTrajectoryError("reconstructed attempt count differs from manifest")
    journal_head = _event_journal_head(flat_events)
    if journal_head != journal_head_expected:
        raise ProofAttentionTrajectoryError("EventJournal projection head does not match manifest")

    snapshot_core = {
        **_copy(dict(session_core)),
        "attempts": reconstructed_attempts,
    }
    source_session_digest = _sha256(session_section["session_digest"], "session_digest")
    if _digest(snapshot_core) != source_session_digest:
        raise ProofAttentionTrajectoryError(
            "reconstructed session snapshot digest differs from source session"
        )
    snapshot = {**snapshot_core, "session_digest": source_session_digest}
    try:
        return ProofAttentionSession.from_snapshot(
            snapshot,
            proof_ground,
            cost_model=cost_model,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProofAttentionTrajectoryError(
            f"restored session does not match supplied ProofGround: {exc}"
        ) from exc


__all__ = [
    "MANIFEST_SCHEMA",
    "FRAME_SCHEMA",
    "ProofAttentionTrajectoryError",
    "export_proof_attention_trajectory",
    "restore_proof_attention_trajectory",
]
