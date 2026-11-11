"""Derive conservative checkpoint-to-checkpoint latency from a verified temporal binding.

This module does not sample clocks or reconstruct E-CPU semantics. It consumes
the output of validate_temporal_binding() and preserves the independent clock
domains. Monotonic totals are reported only when every adjacent interval is
comparable and measured within one continuous actor/segment chain.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping


_BINDING_SCHEMA = "in-formation.observation-temporal-binding/0.1"
_ANALYSIS_SCHEMA = "in-formation.observation-temporal-analysis/0.1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


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


def _optional_integer(value: object, label: str, *, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer or null")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


def _optional_finite_number(value: object, label: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite numeric data or null")
    return value


def _validate_phase(value: object, label: str) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must be a two-element phase pair or null")
    result = []
    for item in value:
        checked = _optional_finite_number(item, label)
        if checked is None:
            raise ValueError(f"{label} cannot contain null coordinates")
        result.append(float(checked))
    return result


def analyze_temporal_binding(binding_document: Mapping[str, Any]) -> dict[str, Any]:
    """Build a conservative interval report from one self-consistent temporal binding.

    The caller should first use validate_temporal_binding() with E-CPU's
    TemporalPathTrace.from_dict. This function independently checks the
    binding digest and interval/event structure, then derives only values
    already present in the verified E-CPU interval records.
    """
    if not isinstance(binding_document, Mapping):
        raise TypeError("binding_document must be a mapping")

    expected_fields = {
        "schema",
        "attempt_id",
        "observation_path_digest",
        "temporal_trace_ref",
        "temporal_trace_digest",
        "event_bindings",
        "intervals",
        "binding_digest",
    }
    if set(binding_document) != expected_fields:
        raise ValueError("temporal binding fields are incomplete or unexpected")
    if binding_document.get("schema") != _BINDING_SCHEMA:
        raise ValueError("unsupported observation-temporal binding schema")

    attempt_id = _nonempty(binding_document.get("attempt_id"), "attempt_id")
    trace_ref = _nonempty(binding_document.get("temporal_trace_ref"), "temporal_trace_ref")
    path_digest = binding_document.get("observation_path_digest")
    trace_digest = binding_document.get("temporal_trace_digest")
    binding_digest = binding_document.get("binding_digest")
    for label, value in (
        ("observation_path_digest", path_digest),
        ("temporal_trace_digest", trace_digest),
        ("binding_digest", binding_digest),
    ):
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")

    core = {
        key: binding_document[key]
        for key in (
            "schema",
            "attempt_id",
            "observation_path_digest",
            "temporal_trace_ref",
            "temporal_trace_digest",
            "event_bindings",
            "intervals",
        )
    }
    if _digest(core) != binding_digest:
        raise ValueError("temporal binding digest does not match its contents")

    events = binding_document.get("event_bindings")
    intervals = binding_document.get("intervals")
    if not isinstance(events, list) or not events:
        raise ValueError("temporal binding requires a non-empty event_bindings list")
    if not isinstance(intervals, list) or len(intervals) != len(events) - 1:
        raise ValueError("temporal binding requires one interval per adjacent event pair")

    normalized_events = []
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise ValueError("temporal event binding must be a mapping")
        if isinstance(event.get("index"), bool) or not isinstance(event.get("index"), int) or event.get("index") != index:
            raise ValueError("temporal event binding indices must be strict integers, contiguous, and ordered")
        stage = _nonempty(event.get("stage"), f"event_bindings[{index}].stage")
        actor_id = _nonempty(
            event.get("temporal_frame_actor_id"),
            f"event_bindings[{index}].temporal_frame_actor_id",
        )
        for key in ("observation_event_digest", "temporal_frame_digest"):
            value = event.get(key)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise ValueError(f"event_bindings[{index}].{key} must be a lowercase SHA-256 digest")
        normalized_events.append({
            "index": index,
            "stage": stage,
            "temporal_frame_actor_id": actor_id,
            "observation_event_digest": event["observation_event_digest"],
            "temporal_frame_digest": event["temporal_frame_digest"],
        })

    normalized_intervals = []
    monotonic_values = []
    for index, interval in enumerate(intervals):
        if not isinstance(interval, Mapping):
            raise ValueError("temporal interval must be a mapping")
        left = normalized_events[index]["stage"]
        right = normalized_events[index + 1]["stage"]
        if interval.get("from_stage") != left or interval.get("to_stage") != right:
            raise ValueError(f"temporal interval {index} does not connect its adjacent bound events")
        delta = interval.get("delta")
        if not isinstance(delta, Mapping):
            raise ValueError(f"temporal interval {index} lacks a delta mapping")

        start_actor = _nonempty(delta.get("start_actor_id"), f"interval[{index}].start_actor_id")
        end_actor = _nonempty(delta.get("end_actor_id"), f"interval[{index}].end_actor_id")
        mono = _optional_integer(
            delta.get("monotonic_elapsed_ns"),
            f"interval[{index}].monotonic_elapsed_ns",
            minimum=0,
        )
        regressed = delta.get("monotonic_regressed")
        if not isinstance(regressed, bool):
            raise ValueError(f"interval[{index}].monotonic_regressed must be boolean")
        if regressed and mono is not None:
            raise ValueError("a regressed monotonic interval cannot also have an elapsed value")
        if start_actor != normalized_events[index]["temporal_frame_actor_id"]:
            raise ValueError(f"temporal interval {index} start actor does not match its bound frame")
        if end_actor != normalized_events[index + 1]["temporal_frame_actor_id"]:
            raise ValueError(f"temporal interval {index} end actor does not match its bound frame")
        if mono is not None and start_actor != end_actor:
            raise ValueError("monotonic elapsed time cannot compare different temporal frame actors")

        if regressed:
            mono_status = "regressed"
        elif mono is not None:
            mono_status = "measured"
        else:
            mono_status = "not_comparable_or_unobserved"
        monotonic_values.append(mono)

        wall = _optional_integer(delta.get("wall_elapsed_ns"), f"interval[{index}].wall_elapsed_ns")
        scheduler = _optional_integer(delta.get("scheduler_ticks"), f"interval[{index}].scheduler_ticks", minimum=0)
        event_steps = _optional_integer(delta.get("event_steps"), f"interval[{index}].event_steps", minimum=0)
        chemical = _optional_finite_number(delta.get("chemical_tau_delta"), f"interval[{index}].chemical_tau_delta")
        causal = delta.get("causal_relation")
        if causal is not None and not isinstance(causal, str):
            raise ValueError(f"interval[{index}].causal_relation must be text or null")

        normalized_intervals.append({
            "index": index,
            "from_stage": left,
            "to_stage": right,
            "start_actor_id": start_actor,
            "end_actor_id": end_actor,
            "monotonic_status": mono_status,
            "monotonic_elapsed_ns": mono,
            "monotonic_regressed": regressed,
            "wall_elapsed_ns": wall,
            "causal_relation": causal,
            "scheduler_ticks": scheduler,
            "event_steps": event_steps,
            "chemical_tau_delta": chemical,
            "chronon_phase_from": _validate_phase(delta.get("chronon_phase_from"), f"interval[{index}].chronon_phase_from"),
            "chronon_phase_to": _validate_phase(delta.get("chronon_phase_to"), f"interval[{index}].chronon_phase_to"),
        })

    if not intervals:
        total_status = "no_intervals"
        total_elapsed = None
    elif all(value is not None for value in monotonic_values):
        total_status = "complete"
        total_elapsed = sum(monotonic_values)
    else:
        total_status = "incomplete_or_incomparable"
        total_elapsed = None

    report_core = {
        "schema": _ANALYSIS_SCHEMA,
        "attempt_id": attempt_id,
        "observation_path_digest": path_digest,
        "temporal_trace_ref": trace_ref,
        "temporal_trace_digest": trace_digest,
        "binding_digest": binding_digest,
        "event_count": len(events),
        "interval_count": len(intervals),
        "monotonic_total_status": total_status,
        "monotonic_total_elapsed_ns": total_elapsed,
        "intervals": normalized_intervals,
        "measurement_scope": (
            "Elapsed time between adjacent local temporal-frame captures. "
            "It is not an isolated measurement of the operation associated with the transition."
        ),
        "interpretation_limits": [
            "A monotonic interval is comparable only within the same actor and monotonic segment, as verified by the E-CPU trace constructor.",
            "A missing monotonic interval is not zero; it is incomparable or unobserved.",
            "Wall-clock differences are retained separately and may be affected by clock adjustments.",
            "Causal relations describe the supplied typed causal stamps; a local adapter clock does not establish remote causation.",
            "The summary does not authenticate the referenced artifacts or clocks.",
        ],
    }
    return {
        **report_core,
        "analysis_digest": _digest(report_core),
    }


def validate_temporal_analysis(
    report: Mapping[str, Any],
    binding_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild a report from its source binding and require exact equality.

    The report's own digest is checked, but digest equality alone is not
    treated as evidence that the report was correctly derived.
    """
    if not isinstance(report, Mapping):
        raise TypeError("temporal analysis report must be a mapping")
    supplied = dict(report)
    digest = supplied.pop("analysis_digest", None)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("analysis_digest must be a lowercase SHA-256 digest")
    if _digest(supplied) != digest:
        raise ValueError("temporal analysis digest does not match its contents")
    if supplied.get("schema") != _ANALYSIS_SCHEMA:
        raise ValueError("unsupported temporal analysis schema")
    rebuilt = analyze_temporal_binding(binding_document)
    if rebuilt != dict(report):
        raise ValueError("temporal analysis differs from independent reconstruction from its binding")
    return dict(report)
