"""Bind proof-action communication checkpoints to append-only session history.

The continuity bundle is a small portable index over two independently useful
artifacts: the paired host/worker/transport checkpoint and the E-CPU trajectory
manifest+data+index. Restore verifies both views against the same session digest.
The actual trajectory bytes remain external files and retain their own receipt
and EventJournal projection checks.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

from mailcpu.transport import Transport

from proof_action_checkpoint import (
    ProofActionCheckpointError,
    export_proof_action_checkpoint,
    restore_proof_action_checkpoint,
)
from proof_attention_trajectory import (
    MANIFEST_SCHEMA,
    ProofAttentionTrajectoryError,
    restore_proof_attention_trajectory,
)


BUNDLE_FORMAT = "in-formation.proof-action-continuity-bundle/0.1"


class ProofActionContinuityError(ValueError):
    """A paired runtime checkpoint and its append-only history do not agree."""


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
        raise ProofActionContinuityError(
            "continuity bundle values must be finite canonical JSON"
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
        raise ProofActionContinuityError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _nonnegative(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ProofActionContinuityError(f"{label} must be a non-negative integer")
    return value


def _positive(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProofActionContinuityError(f"{label} must be a positive integer")
    return value


def _manifest_binding(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        raise ProofActionContinuityError("trajectory manifest must be an object")
    document = _copy(dict(manifest))
    if set(document) != {"schema", "session", "trajectory", "manifest_digest"}:
        raise ProofActionContinuityError("trajectory manifest fields are invalid")
    if document["schema"] != MANIFEST_SCHEMA:
        raise ProofActionContinuityError("unsupported proof-attention trajectory manifest")
    core = {key: value for key, value in document.items() if key != "manifest_digest"}
    manifest_digest = _sha256(document["manifest_digest"], "manifest_digest")
    if _digest(core) != manifest_digest:
        raise ProofActionContinuityError("trajectory manifest digest mismatch")

    session = document["session"]
    trajectory = document["trajectory"]
    if not isinstance(session, Mapping) or not isinstance(trajectory, Mapping):
        raise ProofActionContinuityError("trajectory manifest sections must be objects")
    if set(session) != {
        "session_core", "attempt_headers", "attempt_count", "event_count", "session_digest"
    }:
        raise ProofActionContinuityError("trajectory session manifest fields are invalid")
    if set(trajectory) != {
        "event_count", "stride", "receipt_head", "journal_head_digest",
        "first_logical_time", "last_logical_time",
    }:
        raise ProofActionContinuityError("trajectory receipt manifest fields are invalid")
    if not isinstance(session["session_core"], Mapping):
        raise ProofActionContinuityError("trajectory session core must be an object")
    if not isinstance(session["attempt_headers"], list):
        raise ProofActionContinuityError("trajectory attempt headers must be an array")

    session_digest = _sha256(session["session_digest"], "session_digest")
    attempt_count = _nonnegative(session["attempt_count"], "attempt_count")
    event_count = _nonnegative(session["event_count"], "event_count")
    trajectory_event_count = _nonnegative(
        trajectory["event_count"], "trajectory.event_count"
    )
    stride = _positive(trajectory["stride"], "trajectory.stride")
    receipt_head = _sha256(trajectory["receipt_head"], "trajectory.receipt_head")
    journal_head = _sha256(
        trajectory["journal_head_digest"], "trajectory.journal_head_digest"
    )
    if (
        attempt_count != len(session["attempt_headers"])
        or event_count != trajectory_event_count
        or trajectory["first_logical_time"] != (1 if event_count else None)
        or trajectory["last_logical_time"] != (event_count if event_count else None)
    ):
        raise ProofActionContinuityError("trajectory event coordinates disagree")

    return {
        "manifest_digest": manifest_digest,
        "session_digest": session_digest,
        "attempt_count": attempt_count,
        "event_count": event_count,
        "stride": stride,
        "receipt_head": receipt_head,
        "journal_head_digest": journal_head,
    }


def _seal(core: dict[str, Any]) -> dict[str, Any]:
    return {**core, "bundle_digest": _digest(core)}


def _open_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, Mapping):
        raise ProofActionContinuityError("continuity bundle must be an object")
    supplied = _copy(dict(bundle))
    if set(supplied) != {"format", "pair_checkpoint", "trajectory_binding", "bundle_digest"}:
        raise ProofActionContinuityError("continuity bundle fields are invalid")
    if supplied["format"] != BUNDLE_FORMAT:
        raise ProofActionContinuityError("unsupported proof-action continuity bundle")
    digest = _sha256(supplied.pop("bundle_digest"), "bundle_digest")
    if _digest(supplied) != digest:
        raise ProofActionContinuityError("continuity bundle digest mismatch")
    return supplied


def export_proof_action_continuity_bundle(
    host: Any,
    worker: Any,
    trajectory_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a paired endpoint checkpoint to the exact session/trajectory cut.

    The trajectory manifest must have been produced from the same current
    ProofAttentionSession. Its binary data and sparse index remain separate
    append-only artifacts; this bundle binds their manifest and receipt heads.
    """
    binding = _manifest_binding(trajectory_manifest)
    try:
        session_document = host.session.to_dict()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProofActionContinuityError("host must expose a serializable proof session") from exc
    if session_document.get("session_digest") != binding["session_digest"]:
        raise ProofActionContinuityError(
            "trajectory manifest does not describe the host's exact session snapshot"
        )
    pair_checkpoint = export_proof_action_checkpoint(host, worker)
    core = {
        "format": BUNDLE_FORMAT,
        "pair_checkpoint": pair_checkpoint,
        "trajectory_binding": binding,
    }
    return _seal(core)


def restore_proof_action_continuity_bundle(
    bundle: Mapping[str, Any],
    proof_ground: Any,
    *,
    restore_transport: Callable[[Mapping[str, Any]], Transport],
    trajectory_manifest_path: str | Path,
    trajectory_data_path: str | Path,
    trajectory_index_path: str | Path,
    cost_model: Any | None = None,
) -> tuple[Transport, Any, Any, Any]:
    """Restore pair and trajectory independently, then require identical session history.

    Returns the transport, host, worker and separately restored trajectory session.
    The caller receives both the live endpoint pair and append-only session view;
    neither is silently substituted for the other.
    """
    supplied = _open_bundle(bundle)
    binding = supplied["trajectory_binding"]
    if not isinstance(binding, Mapping):
        raise ProofActionContinuityError("trajectory binding must be an object")
    expected_fields = {
        "manifest_digest", "session_digest", "attempt_count", "event_count",
        "stride", "receipt_head", "journal_head_digest",
    }
    if set(binding) != expected_fields:
        raise ProofActionContinuityError("trajectory binding fields are invalid")
    normalized_binding = {
        "manifest_digest": _sha256(binding["manifest_digest"], "binding.manifest_digest"),
        "session_digest": _sha256(binding["session_digest"], "binding.session_digest"),
        "attempt_count": _nonnegative(binding["attempt_count"], "binding.attempt_count"),
        "event_count": _nonnegative(binding["event_count"], "binding.event_count"),
        "stride": _positive(binding["stride"], "binding.stride"),
        "receipt_head": _sha256(binding["receipt_head"], "binding.receipt_head"),
        "journal_head_digest": _sha256(
            binding["journal_head_digest"], "binding.journal_head_digest"
        ),
    }

    try:
        manifest_document = json.loads(
            Path(trajectory_manifest_path).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofActionContinuityError("bound trajectory manifest is unreadable") from exc
    actual_binding = _manifest_binding(manifest_document)
    if actual_binding != normalized_binding:
        raise ProofActionContinuityError(
            "persisted trajectory manifest does not match the continuity bundle binding"
        )

    try:
        trajectory_session = restore_proof_attention_trajectory(
            trajectory_manifest_path,
            trajectory_data_path,
            trajectory_index_path,
            proof_ground,
            cost_model=cost_model,
        )
    except (ProofAttentionTrajectoryError, OSError, ValueError, TypeError) as exc:
        raise ProofActionContinuityError(f"append-only trajectory restore failed: {exc}") from exc

    trajectory_session_document = trajectory_session.to_dict()
    if trajectory_session_document["session_digest"] != normalized_binding["session_digest"]:
        raise ProofActionContinuityError(
            "restored trajectory history does not reproduce the bound session digest"
        )

    try:
        transport, host, worker = restore_proof_action_checkpoint(
            supplied["pair_checkpoint"],
            proof_ground,
            restore_transport=restore_transport,
            cost_model=cost_model,
        )
    except (ProofActionCheckpointError, OSError, ValueError, TypeError) as exc:
        raise ProofActionContinuityError(f"paired endpoint restore failed: {exc}") from exc

    host_session_document = host.session.to_dict()
    if host_session_document["session_digest"] != normalized_binding["session_digest"]:
        raise ProofActionContinuityError(
            "restored host session does not match the append-only trajectory history"
        )
    if host_session_document != trajectory_session_document:
        raise ProofActionContinuityError(
            "host session and trajectory session differ despite matching digest labels"
        )
    return transport, host, worker, trajectory_session


__all__ = [
    "BUNDLE_FORMAT",
    "ProofActionContinuityError",
    "export_proof_action_continuity_bundle",
    "restore_proof_action_continuity_bundle",
]
