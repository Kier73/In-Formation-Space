"""Portable stateful checkpoints bound to exact realization capsules.

PSC-001 stores the live-state/time projection and replay lineage, while each
model revision is bound to a separate PRC realization capsule. Dense weights
are not duplicated in the checkpoint: a receiver reconstructs the runtime by
replaying the typed program events and validates each realization capsule.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from mailcpu.stateful_transition import (
    StatefulTransitionRuntime,
    StatefulTransitionError,
)
from mailcpu.transition_space import FiniteTransitionProgram

from portable_realization import (
    PortableRealizationError,
    _canonical,
    decode_capsule,
)

MAGIC = b"IFSPCK01"
VERSION = 1
PREFIX = struct.Struct("<8sHI")
SCHEMA = "in-formation-space.portable-stateful-checkpoint.v1"
GENESIS_DOMAIN = "mailcpu.stateful-transition-runtime.genesis.v1"
COMPILER_ID = "mailcpu.transition_space.compile_live_compositional_transition_program"


class PortableStatefulCheckpointError(ValueError):
    """A portable state, realization binding, or event replay is inconsistent."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _sha256(_canonical(value))


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise PortableStatefulCheckpointError(f"{field} must be an integer >= {minimum}")
    return value


def _require_digest(value: Any, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PortableStatefulCheckpointError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _bit(value: Any, field: str) -> int:
    if type(value) is not int or value not in (0, 1):
        raise PortableStatefulCheckpointError(f"{field} must be a strict Boolean bit")
    return value


def _program_revisions(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    programs = [snapshot["initial_program"]]
    for event in snapshot["events"]:
        if event.get("kind") == "revision":
            programs.append(event["target_program"])
    return programs


def _expected_model_digests(runtime: StatefulTransitionRuntime) -> list[str]:
    full = runtime.snapshot()
    initial_program = FiniteTransitionProgram.from_dict(full["initial_program"])
    initial_model = StatefulTransitionRuntime(
        initial_program,
        full["initial_state"],
        state_input_names=full["state_input_names"],
    )
    digests = [initial_model.model_digest]
    for event in full["events"]:
        if event.get("kind") == "revision":
            digests.append(event["target_model_digest"])
    return digests


def _validated_realizations(
    snapshot: Mapping[str, Any],
    realization_capsules: Sequence[bytes],
) -> list[dict[str, Any]]:
    programs = _program_revisions(snapshot)
    expected_model_digests: list[str] = []
    initial_program = FiniteTransitionProgram.from_dict(programs[0])
    initial_runtime = StatefulTransitionRuntime(
        initial_program,
        snapshot["initial_state"],
        state_input_names=snapshot["state_input_names"],
    )
    expected_model_digests.append(initial_runtime.model_digest)
    for event in snapshot["events"]:
        if event.get("kind") == "revision":
            expected_model_digests.append(event["target_model_digest"])

    if len(realization_capsules) != len(programs):
        raise PortableStatefulCheckpointError(
            "one realization capsule is required for every runtime revision"
        )
    records: list[dict[str, Any]] = []
    for revision, (program_payload, expected_model_digest, capsule) in enumerate(
        zip(programs, expected_model_digests, realization_capsules)
    ):
        if not isinstance(capsule, bytes) or not capsule:
            raise PortableStatefulCheckpointError("realization capsules must be non-empty bytes")
        try:
            header, _ = decode_capsule(capsule)
        except PortableRealizationError as exc:
            raise PortableStatefulCheckpointError(
                f"realization capsule {revision} failed integrity validation"
            ) from exc
        program = FiniteTransitionProgram.from_dict(program_payload)
        if (
            header["codec"]["name"] != "hybrid_binary"
            or header["source"]["program_digest"] != program.digest
            or header["realization"]["dense_model_digest"] != expected_model_digest
            or header["source"]["ground_digest"] != program.digest
            or header["interface"]["input_names"] != list(program.input_names)
            or header["interface"]["output_names"] != list(program.output_names)
        ):
            raise PortableStatefulCheckpointError(
                f"realization capsule {revision} is not bound to its runtime program/model"
            )
        records.append(
            {
                "revision": revision,
                "program_digest": program.digest,
                "model_digest": expected_model_digest,
                "capsule_sha256": _sha256(capsule),
                "capsule_base64": base64.b64encode(capsule).decode("ascii"),
            }
        )

    if records[-1]["model_digest"] != snapshot["current_model"]["digest"]:
        raise PortableStatefulCheckpointError(
            "active realization capsule does not match the current runtime model"
        )
    return records


def _runtime_projection(
    runtime: StatefulTransitionRuntime,
) -> dict[str, Any]:
    snapshot = runtime.snapshot()
    # Keep the portable control/state lineage free of compiler-specific float
    # weights. The exact active realization is carried by its bound PRC capsule.
    return {
        "schema": snapshot["schema"],
        "compiler_id": snapshot["compiler_id"],
        "initial_state": snapshot["initial_state"],
        "state_input_names": snapshot["state_input_names"],
        "initial_program": snapshot["initial_program"],
        "current_program": snapshot["current_program"],
        "current_model_digest": snapshot["current_model"]["digest"],
        "state": snapshot["state"],
        "tick": snapshot["tick"],
        "revision": snapshot["revision"],
        "events": snapshot["events"],
        "genesis_digest": snapshot["genesis_digest"],
        "chain_head_digest": snapshot["chain_head_digest"],
    }


def encode_checkpoint(
    runtime: StatefulTransitionRuntime,
    realization_capsules: Sequence[bytes],
    resume_controls: Mapping[str, int],
) -> bytes:
    """Encode a compact runtime lineage bound to one capsule per model revision."""
    if not isinstance(runtime, StatefulTransitionRuntime):
        raise PortableStatefulCheckpointError("runtime must be a StatefulTransitionRuntime")
    try:
        StatefulTransitionRuntime.from_snapshot(runtime.snapshot())
    except (StatefulTransitionError, ValueError, TypeError) as exc:
        raise PortableStatefulCheckpointError("runtime failed its own snapshot replay") from exc

    snapshot = runtime.snapshot()
    runtime_projection = _runtime_projection(runtime)
    realization_records = _validated_realizations(snapshot, realization_capsules)

    current_control_names = tuple(
        name for name in runtime.program.input_names
        if name not in set(runtime.state_input_names)
    )
    if not isinstance(resume_controls, Mapping) or set(resume_controls) != set(current_control_names):
        raise PortableStatefulCheckpointError("resume controls do not match the active program")
    controls = {
        name: _bit(resume_controls[name], f"resume control {name}")
        for name in current_control_names
    }

    core = {
        "schema": SCHEMA,
        "version": VERSION,
        "runtime": runtime_projection,
        "realizations": realization_records,
        "resume_controls": controls,
    }
    try:
        header = {**core, "checkpoint_sha256": _digest(core)}
        header_bytes = _canonical(header)
    except PortableRealizationError as exc:
        raise PortableStatefulCheckpointError("checkpoint metadata is not canonical") from exc
    return PREFIX.pack(MAGIC, VERSION, len(header_bytes)) + header_bytes


def decode_checkpoint(checkpoint: bytes) -> dict[str, Any]:
    """Validate PSC framing, canonical JSON, and the checkpoint identity digest."""
    if not isinstance(checkpoint, bytes) or len(checkpoint) < PREFIX.size:
        raise PortableStatefulCheckpointError("checkpoint is truncated")
    magic, version, header_length = PREFIX.unpack_from(checkpoint, 0)
    if magic != MAGIC:
        raise PortableStatefulCheckpointError("checkpoint magic does not match")
    if version != VERSION:
        raise PortableStatefulCheckpointError("unsupported checkpoint framing version")
    end = PREFIX.size + header_length
    if header_length <= 0 or end != len(checkpoint):
        raise PortableStatefulCheckpointError("checkpoint header length does not match file size")
    try:
        header = json.loads(checkpoint[PREFIX.size:end].decode("utf-8"))
        canonical_header = _canonical(header)
    except (UnicodeDecodeError, json.JSONDecodeError, PortableRealizationError) as exc:
        raise PortableStatefulCheckpointError("checkpoint header is not canonical JSON") from exc
    if canonical_header != checkpoint[PREFIX.size:end]:
        raise PortableStatefulCheckpointError("checkpoint header is not canonical")
    if not isinstance(header, dict):
        raise PortableStatefulCheckpointError("checkpoint header must be an object")
    supplied = header.pop("checkpoint_sha256", None)
    if supplied != _digest(header):
        raise PortableStatefulCheckpointError("checkpoint SHA-256 mismatch")
    header["checkpoint_sha256"] = supplied
    return header


def restore_runtime(checkpoint: bytes) -> StatefulTransitionRuntime:
    """Restore a runtime by rebuilding each revision and replaying every event."""
    header = decode_checkpoint(checkpoint)
    if (
        header.get("schema") != SCHEMA
        or _require_int(header.get("version"), "checkpoint.version") != VERSION
        or set(header) != {
            "schema", "version", "runtime", "realizations", "resume_controls",
            "checkpoint_sha256",
        }
    ):
        raise PortableStatefulCheckpointError("checkpoint fields/schema do not match PSC v1")

    projection = header["runtime"]
    required = {
        "schema", "compiler_id", "initial_state", "state_input_names",
        "initial_program", "current_program", "current_model_digest", "state",
        "tick", "revision", "events", "genesis_digest", "chain_head_digest",
    }
    if not isinstance(projection, Mapping) or set(projection) != required:
        raise PortableStatefulCheckpointError("runtime projection fields do not match PSC v1")
    if projection["schema"] != "mailcpu.stateful-transition-runtime.v1":
        raise PortableStatefulCheckpointError("unsupported stateful runtime schema")
    if projection["compiler_id"] != COMPILER_ID:
        raise PortableStatefulCheckpointError("unsupported stateful runtime compiler")
    _require_digest(projection["current_model_digest"], "runtime.current_model_digest")

    realization_records = header["realizations"]
    if not isinstance(realization_records, list) or len(realization_records) != projection["revision"] + 1:
        raise PortableStatefulCheckpointError("checkpoint realization revision count is invalid")
    capsules: list[bytes] = []
    for revision, record in enumerate(realization_records):
        if not isinstance(record, Mapping) or set(record) != {
            "revision", "program_digest", "model_digest", "capsule_sha256", "capsule_base64"
        }:
            raise PortableStatefulCheckpointError("realization record fields are invalid")
        if _require_int(record["revision"], "realization.revision") != revision:
            raise PortableStatefulCheckpointError("realization revisions are not contiguous")
        _require_digest(record["program_digest"], "realization.program_digest")
        _require_digest(record["model_digest"], "realization.model_digest")
        _require_digest(record["capsule_sha256"], "realization.capsule_sha256")
        try:
            capsule = base64.b64decode(record["capsule_base64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise PortableStatefulCheckpointError("realization capsule base64 is invalid") from exc
        if base64.b64encode(capsule).decode("ascii") != record["capsule_base64"]:
            raise PortableStatefulCheckpointError("realization capsule base64 is not canonical")
        if _sha256(capsule) != record["capsule_sha256"]:
            raise PortableStatefulCheckpointError("realization capsule digest mismatch")
        capsules.append(capsule)

    snapshot_for_runtime = {
        key: value for key, value in projection.items()
        if key != "current_model_digest"
    }
    initial_program = FiniteTransitionProgram.from_dict(snapshot_for_runtime["initial_program"])
    runtime = StatefulTransitionRuntime(
        initial_program,
        snapshot_for_runtime["initial_state"],
        state_input_names=snapshot_for_runtime["state_input_names"],
    )
    if runtime.model_digest != realization_records[0]["model_digest"]:
        raise PortableStatefulCheckpointError("initial model digest differs from its capsule binding")
    if runtime.program_digest != realization_records[0]["program_digest"]:
        raise PortableStatefulCheckpointError("initial program digest differs from its capsule binding")

    if not isinstance(snapshot_for_runtime["events"], list):
        raise PortableStatefulCheckpointError("runtime events must be an ordered array")
    revision_index = 0
    for stored_event in snapshot_for_runtime["events"]:
        if not isinstance(stored_event, Mapping):
            raise PortableStatefulCheckpointError("runtime event must be an object")
        try:
            if stored_event.get("kind") == "step":
                generated = runtime.step(stored_event.get("controls", {}))
                generated_event = runtime.events[-1]
            elif stored_event.get("kind") == "revision":
                target = FiniteTransitionProgram.from_dict(stored_event["target_program"])
                generated_event = runtime.revise(target)
                revision_index += 1
                if revision_index >= len(realization_records):
                    raise PortableStatefulCheckpointError("event revision has no realization capsule")
                record = realization_records[revision_index]
                if (
                    target.digest != record["program_digest"]
                    or generated_event["target_model_digest"] != record["model_digest"]
                ):
                    raise PortableStatefulCheckpointError("revision event differs from its capsule binding")
            else:
                raise PortableStatefulCheckpointError("runtime event kind is unsupported")
        except (StatefulTransitionError, KeyError, TypeError, ValueError) as exc:
            raise PortableStatefulCheckpointError("runtime event replay failed") from exc
        if _canonical(generated_event) != _canonical(dict(stored_event)):
            raise PortableStatefulCheckpointError("runtime event differs from its replay")

    if (
        runtime.program.digest != FiniteTransitionProgram.from_dict(
            snapshot_for_runtime["current_program"]
        ).digest
        or runtime.model_digest != projection["current_model_digest"]
        or list(runtime.state) != snapshot_for_runtime["state"]
        or runtime.tick != _require_int(snapshot_for_runtime["tick"], "runtime.tick")
        or runtime.revision != _require_int(snapshot_for_runtime["revision"], "runtime.revision")
        or runtime.chain_head_digest != snapshot_for_runtime["chain_head_digest"]
    ):
        raise PortableStatefulCheckpointError("runtime terminal state or lineage differs from replay")

    current_record = realization_records[-1]
    if (
        current_record["model_digest"] != runtime.model_digest
        or current_record["program_digest"] != runtime.program.digest
    ):
        raise PortableStatefulCheckpointError("active realization capsule does not match restored runtime")
    current_control_names = tuple(
        name for name in runtime.program.input_names
        if name not in set(runtime.state_input_names)
    )
    controls = header["resume_controls"]
    if not isinstance(controls, Mapping) or set(controls) != set(current_control_names):
        raise PortableStatefulCheckpointError("resume controls do not match active runtime")
    for name in current_control_names:
        _bit(controls[name], f"resume control {name}")
    return runtime
