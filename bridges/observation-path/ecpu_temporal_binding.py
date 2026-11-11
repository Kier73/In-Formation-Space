"""Bind an E-CPU TemporalPathTrace to an ObservationPath without flattening clocks.

This module deliberately does not import E-CPU. The caller supplies its typed
TemporalPathTrace and matching from_dict constructor. E-CPU remains the owner
of clock semantics, clock-domain comparability, interval calculation, and
temporal-trace verification.

A temporal frame actor_id identifies the process that sampled the frame. It
does not automatically identify the remote actor named by an observation-path
event. This lets a receiver-side adapter measure when it recorded a stage
without inventing remote source timestamps.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from observation_path import ObservationPath


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TRACE_SCHEMA = "mailcpu.temporal-path-trace.v1"
_BINDING_SCHEMA = "in-formation.observation-temporal-binding/0.1"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


@dataclass(frozen=True)
class ObservationTemporalBinding:
    """Immutable digest binding between one observation attempt and one E-CPU trace."""

    attempt_id: str
    observation_path_digest: str
    temporal_trace_ref: str
    temporal_trace_digest: str
    event_bindings: tuple[Mapping[str, Any], ...]
    intervals: tuple[Mapping[str, Any], ...]
    binding_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _BINDING_SCHEMA,
            "attempt_id": self.attempt_id,
            "observation_path_digest": self.observation_path_digest,
            "temporal_trace_ref": self.temporal_trace_ref,
            "temporal_trace_digest": self.temporal_trace_digest,
            "event_bindings": [dict(item) for item in self.event_bindings],
            "intervals": [dict(item) for item in self.intervals],
            "binding_digest": self.binding_digest,
        }


def append_missing_temporal_events(
    path: ObservationPath,
    temporal_trace: object,
    frame_factory: Callable[[object], object],
) -> object:
    """Append frames for path events not yet represented in a typed temporal trace.

    frame_factory(path_event) must return a typed E-CPU TemporalFrame. A new
    frame is sampled for each unrepresented event, in observation-path order.
    The frame actor identifies the sampler; it is not inferred from the path
    event's actor field.

    The returned trace is a new immutable E-CPU TemporalPathTrace. The caller
    owns storing it and retaining its digest/reference.
    """
    if not isinstance(path, ObservationPath):
        raise TypeError("path must be an ObservationPath")
    if not callable(frame_factory):
        raise TypeError("frame_factory must be callable")
    if getattr(temporal_trace, "path_id", None) != path.intent.attempt_id:
        raise ValueError("temporal trace path_id must equal observation attempt_id")

    current_events = getattr(temporal_trace, "events", None)
    append = getattr(temporal_trace, "append", None)
    if not isinstance(current_events, (list, tuple)) or not callable(append):
        raise TypeError("temporal_trace must expose immutable events and append()")
    if len(current_events) > len(path.events):
        raise ValueError("temporal trace contains more events than the observation path")

    path_document = path.to_dict()
    path_events = path_document["events"]
    trace = temporal_trace

    for index in range(len(current_events), len(path.events)):
        path_event = path.events[index]
        frame = frame_factory(path_event)
        frame_to_dict = getattr(frame, "to_dict", None)
        if not callable(frame_to_dict):
            raise TypeError("frame_factory must return a typed frame exposing to_dict()")
        frame_document = frame_to_dict()
        if not isinstance(frame_document, Mapping):
            raise ValueError("temporal frame to_dict() must return a mapping")
        trace = trace.append(
            path_event.stage,
            frame,
            _digest(path_events[index]),
        )

    return trace


def create_temporal_binding(
    path: ObservationPath,
    temporal_trace: object,
    *,
    temporal_trace_ref: str,
    restore_trace: Callable[[Mapping[str, Any]], object],
) -> ObservationTemporalBinding:
    """Verify and bind a full E-CPU temporal trace to every path event.

    The E-CPU trace is round-tripped through its own from_dict constructor.
    Every event must match the observation path by index and stage, and its
    evidence_digest must equal the canonical digest of that path event.
    Temporal intervals are copied from E-CPU's verified trace, not recomputed
    or converted by this module.
    """
    if not isinstance(path, ObservationPath):
        raise TypeError("path must be an ObservationPath")
    temporal_trace_ref = _nonempty(temporal_trace_ref, "temporal_trace_ref")
    if not callable(restore_trace):
        raise TypeError("restore_trace must be callable")
    if getattr(temporal_trace, "path_id", None) != path.intent.attempt_id:
        raise ValueError("temporal trace path_id must equal observation attempt_id")

    trace_to_dict = getattr(temporal_trace, "to_dict", None)
    trace_digest = getattr(temporal_trace, "digest", None)
    trace_events = getattr(temporal_trace, "events", None)
    if not callable(trace_to_dict) or not isinstance(trace_digest, str):
        raise TypeError("temporal trace must expose to_dict(), digest, and events")
    if not isinstance(trace_events, (list, tuple)):
        raise TypeError("temporal trace events must be a sequence")

    trace_document = trace_to_dict()
    if not isinstance(trace_document, Mapping):
        raise ValueError("temporal trace document must be a mapping")
    if trace_document.get("schema") != _TRACE_SCHEMA:
        raise ValueError("unsupported E-CPU temporal trace schema")
    if trace_document.get("path_id") != path.intent.attempt_id:
        raise ValueError("serialized temporal trace path_id mismatch")
    if trace_document.get("digest") != trace_digest or not _SHA256.fullmatch(trace_digest):
        raise ValueError("temporal trace digest is missing or inconsistent")

    restored = restore_trace(dict(trace_document))
    if getattr(restored, "digest", None) != trace_digest:
        raise ValueError("E-CPU temporal trace failed digest verification")
    restored_document = restored.to_dict()
    if restored_document != dict(trace_document):
        raise ValueError("E-CPU temporal trace changed during verified restoration")

    path_document = path.to_dict()
    path_events = path_document["events"]
    serialized_events = trace_document.get("events")
    if not isinstance(serialized_events, list):
        raise ValueError("E-CPU temporal trace events must be a list")
    if len(path_events) != len(serialized_events):
        raise ValueError("temporal trace must contain exactly one event per observation-path event")

    event_bindings = []
    for index, (path_event, temporal_event) in enumerate(zip(path_events, serialized_events)):
        if not isinstance(temporal_event, Mapping):
            raise ValueError("temporal trace event must be a mapping")
        if temporal_event.get("stage") != path_event["stage"]:
            raise ValueError(f"temporal stage mismatch at event index {index}")
        expected_path_digest = _digest(path_event)
        if temporal_event.get("evidence_digest") != expected_path_digest:
            raise ValueError(f"temporal event {index} does not bind the corresponding observation event")
        frame = temporal_event.get("frame")
        if not isinstance(frame, Mapping):
            raise ValueError(f"temporal event {index} has no typed frame mapping")
        actor_id = _nonempty(frame.get("actor_id"), f"temporal event {index} frame actor_id")
        event_bindings.append({
            "index": index,
            "stage": path_event["stage"],
            "observation_event_digest": expected_path_digest,
            "temporal_frame_actor_id": actor_id,
            "temporal_frame_digest": _digest(dict(frame)),
        })

    intervals = trace_document.get("intervals")
    if not isinstance(intervals, list) or len(intervals) != max(0, len(path_events) - 1):
        raise ValueError("temporal trace intervals do not correspond to adjacent path events")

    core = {
        "schema": _BINDING_SCHEMA,
        "attempt_id": path.intent.attempt_id,
        "observation_path_digest": _digest(path_document),
        "temporal_trace_ref": temporal_trace_ref,
        "temporal_trace_digest": trace_digest,
        "event_bindings": event_bindings,
        "intervals": intervals,
    }
    binding_digest = _digest(core)
    return ObservationTemporalBinding(
        attempt_id=path.intent.attempt_id,
        observation_path_digest=core["observation_path_digest"],
        temporal_trace_ref=temporal_trace_ref,
        temporal_trace_digest=trace_digest,
        event_bindings=tuple(event_bindings),
        intervals=tuple(intervals),
        binding_digest=binding_digest,
    )


def validate_temporal_binding(
    binding_document: Mapping[str, Any],
    path: ObservationPath,
    temporal_trace: object,
    *,
    restore_trace: Callable[[Mapping[str, Any]], object],
) -> ObservationTemporalBinding:
    """Rebuild a binding and require exact equality with the supplied artifact."""
    if not isinstance(binding_document, Mapping):
        raise TypeError("binding_document must be a mapping")
    ref = _nonempty(binding_document.get("temporal_trace_ref"), "temporal_trace_ref")
    rebuilt = create_temporal_binding(
        path,
        temporal_trace,
        temporal_trace_ref=ref,
        restore_trace=restore_trace,
    )
    if rebuilt.to_dict() != dict(binding_document):
        raise ValueError("observation-temporal binding failed independent reconstruction")
    return rebuilt
