"""Lossless temporal-coordinate v2 codec over Canonical Metadata v1.

Temporal integers are canonical decimal strings and binary64 values are
big-endian IEEE-754 bit strings. The codec never writes large integers or
floating-point values as JSON numbers.
"""
from __future__ import annotations

import math
import re
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from formats.canonical_metadata_v1 import canonical_bytes

NUMERIC_FORMAT = "in-formation.temporal-numeric"
NUMERIC_SCHEMA = "in-formation.temporal-numeric/2.0"
NUMERIC_PROFILE = NUMERIC_SCHEMA
INTEGER_ENCODING = "canonical-decimal-string"
BINARY64_ENCODING = "ieee754-binary64-be-hex"
FRAME_FORMAT = "in-formation.temporal-frame"
FRAME_SCHEMA = "in-formation.temporal-frame/0.2"
SPAN_FORMAT = "in-formation.operation-span"
SPAN_SCHEMA = "in-formation.operation-span/0.2"

_DECIMAL = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
_BINARY64 = re.compile(r"^[0-9a-f]{16}$")


class TemporalCoordinateError(ValueError):
    """A temporal numeric value or v2 wire object is invalid."""


def _exact(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TemporalCoordinateError(f"{label} must contain exactly {sorted(fields)}")
    return value


def _integer(value: Any, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TemporalCoordinateError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise TemporalCoordinateError(f"{label} must be >= {minimum}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise TemporalCoordinateError(f"{label} must be non-empty text without NUL")
    return value


def _envelope(kind: str, encoding: str, value: str) -> dict[str, str]:
    return {
        "format": NUMERIC_FORMAT,
        "schema": NUMERIC_SCHEMA,
        "kind": kind,
        "encoding": encoding,
        "value": value,
    }


def encode_integer(value: int) -> dict[str, str]:
    """Encode an arbitrary-width integer without passing through JSON number."""
    return _envelope("integer", INTEGER_ENCODING, str(_integer(value, "integer value")))


def decode_integer(
    envelope: Any,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Decode one exact canonical decimal integer envelope."""
    raw = _exact(envelope, {"format", "schema", "kind", "encoding", "value"}, "integer envelope")
    if raw["format"] != NUMERIC_FORMAT or raw["schema"] != NUMERIC_SCHEMA:
        raise TemporalCoordinateError("integer envelope format or schema mismatch")
    if raw["kind"] != "integer" or raw["encoding"] != INTEGER_ENCODING:
        raise TemporalCoordinateError("integer envelope kind or encoding mismatch")
    token = raw["value"]
    if not isinstance(token, str) or not token.isascii() or not _DECIMAL.fullmatch(token):
        raise TemporalCoordinateError("integer value is not canonical base-10 text")
    value = int(token, 10)
    if minimum is not None and value < minimum:
        raise TemporalCoordinateError(f"integer value must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise TemporalCoordinateError(f"integer value must be <= {maximum}")
    return value


def encode_binary64(value: float) -> dict[str, str]:
    """Encode a finite IEEE-754 binary64 value by its exact 64-bit pattern."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemporalCoordinateError("binary64 value must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise TemporalCoordinateError("binary64 value must be finite")
    bits = struct.pack(">d", number).hex()
    return _envelope("binary64", BINARY64_ENCODING, bits)


def decode_binary64(envelope: Any) -> float:
    """Decode exact finite binary64 bits; negative zero and subnormals are preserved."""
    raw = _exact(envelope, {"format", "schema", "kind", "encoding", "value"}, "binary64 envelope")
    if raw["format"] != NUMERIC_FORMAT or raw["schema"] != NUMERIC_SCHEMA:
        raise TemporalCoordinateError("binary64 envelope format or schema mismatch")
    if raw["kind"] != "binary64" or raw["encoding"] != BINARY64_ENCODING:
        raise TemporalCoordinateError("binary64 envelope kind or encoding mismatch")
    token = raw["value"]
    if not isinstance(token, str) or not _BINARY64.fullmatch(token):
        raise TemporalCoordinateError("binary64 value must be 16 lowercase hexadecimal digits")
    value = struct.unpack(">d", bytes.fromhex(token))[0]
    if not math.isfinite(value):
        raise TemporalCoordinateError("binary64 value must be finite")
    return value


def _encode_optional_int(value: Any, label: str, minimum: int = 0) -> dict[str, str] | None:
    if value is None:
        return None
    return encode_integer(_integer(value, label, minimum))


def _encode_optional_float(value: Any, label: str) -> dict[str, str] | None:
    if value is None:
        return None
    try:
        return encode_binary64(value)
    except TemporalCoordinateError as exc:
        raise TemporalCoordinateError(f"{label}: {exc}") from exc


def _check_phase(values: Sequence[float], label: str = "chronon_phase") -> None:
    if len(values) != 2 or not all(math.isfinite(v) for v in values):
        raise TemporalCoordinateError(f"{label} must contain two finite binary64 values")
    if not math.isclose(math.hypot(values[0], values[1]), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise TemporalCoordinateError(f"{label} must lie on the unit circle")


def encode_temporal_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Encode an E-CPU TemporalFrame.to_dict() projection as frame v0.2."""
    fields = {
        "actor_id", "monotonic", "wall", "causal", "scheduler",
        "event_lambda", "chronon_phase", "chemical_tau",
    }
    source = _exact(frame, fields, "temporal frame")
    actor = _text(source["actor_id"], "frame.actor_id")
    wire: dict[str, Any] = {
        "format": FRAME_FORMAT,
        "schema": FRAME_SCHEMA,
        "numeric_profile": NUMERIC_PROFILE,
        "actor_id": actor,
    }

    mono = source["monotonic"]
    if mono is None:
        wire["monotonic"] = None
    else:
        mono = _exact(mono, {"actor_id", "segment", "elapsed_ns"}, "frame.monotonic")
        mono_actor = _text(mono["actor_id"], "monotonic.actor_id")
        if mono_actor != actor:
            raise TemporalCoordinateError("monotonic actor does not match frame actor")
        wire["monotonic"] = {
            "actor_id": mono_actor,
            "segment": encode_integer(_integer(mono["segment"], "monotonic.segment", 0)),
            "elapsed_ns": encode_integer(_integer(mono["elapsed_ns"], "monotonic.elapsed_ns", 0)),
        }

    wall = source["wall"]
    if wall is None:
        wire["wall"] = None
    else:
        wall = _exact(wall, {"actor_id", "utc_ns", "sample_index"}, "frame.wall")
        wall_actor = _text(wall["actor_id"], "wall.actor_id")
        if wall_actor != actor:
            raise TemporalCoordinateError("wall actor does not match frame actor")
        wire["wall"] = {
            "actor_id": wall_actor,
            "utc_ns": encode_integer(_integer(wall["utc_ns"], "wall.utc_ns")),
            "sample_index": encode_integer(_integer(wall["sample_index"], "wall.sample_index", 0)),
        }

    causal = source["causal"]
    if causal is None:
        wire["causal"] = None
    else:
        causal = _exact(causal, {"actor_id", "lamport", "vector"}, "frame.causal")
        causal_actor = _text(causal["actor_id"], "causal.actor_id")
        if causal_actor != actor:
            raise TemporalCoordinateError("causal actor does not match frame actor")
        lamport = _integer(causal["lamport"], "causal.lamport", 0)
        vector = causal["vector"]
        if not isinstance(vector, Mapping) or not vector:
            raise TemporalCoordinateError("causal vector must be a non-empty mapping")
        entries: list[dict[str, Any]] = []
        for vector_actor in sorted(vector, key=lambda item: _text(item, "causal vector actor").encode("utf-8")):
            counter = _integer(vector[vector_actor], f"causal.vector[{vector_actor}]", 0)
            if counter > lamport:
                raise TemporalCoordinateError("causal vector counter exceeds Lamport scalar")
            entries.append({"actor_id": vector_actor, "counter": encode_integer(counter)})
        if causal_actor not in vector:
            raise TemporalCoordinateError("causal vector must include its own actor")
        wire["causal"] = {
            "actor_id": causal_actor,
            "lamport": encode_integer(lamport),
            "vector": entries,
        }

    scheduler = source["scheduler"]
    if scheduler is None:
        wire["scheduler"] = None
    else:
        scheduler = _exact(scheduler, {"scheduler_id", "tick"}, "frame.scheduler")
        wire["scheduler"] = {
            "scheduler_id": _text(scheduler["scheduler_id"], "scheduler.scheduler_id"),
            "tick": encode_integer(_integer(scheduler["tick"], "scheduler.tick", 0)),
        }

    event_lambda = source["event_lambda"]
    wire["event_lambda"] = _encode_optional_int(event_lambda, "event_lambda", 0)

    phase = source["chronon_phase"]
    if phase is None:
        wire["chronon_phase"] = None
    else:
        if not isinstance(phase, (list, tuple)) or len(phase) != 2:
            raise TemporalCoordinateError("chronon_phase must be a real/imaginary pair")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in phase):
            raise TemporalCoordinateError("chronon_phase components must be numeric, not Boolean")
        phase_values = [float(phase[0]), float(phase[1])]
        _check_phase(phase_values)
        wire["chronon_phase"] = [encode_binary64(phase_values[0]), encode_binary64(phase_values[1])]

    tau = source["chemical_tau"]
    if tau is None:
        wire["chemical_tau"] = None
    else:
        if isinstance(tau, bool) or not isinstance(tau, (int, float)):
            raise TemporalCoordinateError("chemical_tau must be numeric, not Boolean")
        tau_float = float(tau)
        if not math.isfinite(tau_float) or tau_float < 0.0:
            raise TemporalCoordinateError("chemical_tau must be finite and non-negative")
        wire["chemical_tau"] = encode_binary64(tau_float)

    canonical_bytes(wire)
    return wire


def decode_temporal_frame(wire_frame: Mapping[str, Any]) -> dict[str, Any]:
    """Decode frame v0.2 to the lossless Python TemporalFrame.to_dict() projection."""
    fields = {
        "format", "schema", "numeric_profile", "actor_id", "monotonic", "wall",
        "causal", "scheduler", "event_lambda", "chronon_phase", "chemical_tau",
    }
    wire = _exact(wire_frame, fields, "temporal frame v0.2")
    if wire["format"] != FRAME_FORMAT or wire["schema"] != FRAME_SCHEMA or wire["numeric_profile"] != NUMERIC_PROFILE:
        raise TemporalCoordinateError("temporal frame format, schema, or numeric profile mismatch")
    actor = _text(wire["actor_id"], "frame.actor_id")
    result: dict[str, Any] = {"actor_id": actor}

    mono = wire["monotonic"]
    if mono is None:
        result["monotonic"] = None
    else:
        mono = _exact(mono, {"actor_id", "segment", "elapsed_ns"}, "frame.monotonic")
        if mono["actor_id"] != actor:
            raise TemporalCoordinateError("monotonic actor does not match frame actor")
        result["monotonic"] = {
            "actor_id": actor,
            "segment": decode_integer(mono["segment"], minimum=0),
            "elapsed_ns": decode_integer(mono["elapsed_ns"], minimum=0),
        }

    wall = wire["wall"]
    if wall is None:
        result["wall"] = None
    else:
        wall = _exact(wall, {"actor_id", "utc_ns", "sample_index"}, "frame.wall")
        if wall["actor_id"] != actor:
            raise TemporalCoordinateError("wall actor does not match frame actor")
        result["wall"] = {
            "actor_id": actor,
            "utc_ns": decode_integer(wall["utc_ns"]),
            "sample_index": decode_integer(wall["sample_index"], minimum=0),
        }

    causal = wire["causal"]
    if causal is None:
        result["causal"] = None
    else:
        causal = _exact(causal, {"actor_id", "lamport", "vector"}, "frame.causal")
        if causal["actor_id"] != actor:
            raise TemporalCoordinateError("causal actor does not match frame actor")
        lamport = decode_integer(causal["lamport"], minimum=0)
        entries = causal["vector"]
        if not isinstance(entries, list) or not entries:
            raise TemporalCoordinateError("causal vector must be a non-empty array")
        vector: dict[str, int] = {}
        prior = None
        for entry in entries:
            entry = _exact(entry, {"actor_id", "counter"}, "causal vector entry")
            vector_actor = _text(entry["actor_id"], "causal vector actor")
            encoded_actor = vector_actor.encode("utf-8")
            if prior is not None and encoded_actor <= prior:
                raise TemporalCoordinateError("causal vector actors must be unique and UTF-8 sorted")
            prior = encoded_actor
            counter = decode_integer(entry["counter"], minimum=0)
            if counter > lamport:
                raise TemporalCoordinateError("causal vector counter exceeds Lamport scalar")
            vector[vector_actor] = counter
        if actor not in vector:
            raise TemporalCoordinateError("causal vector must include its own actor")
        result["causal"] = {"actor_id": actor, "lamport": lamport, "vector": vector}

    scheduler = wire["scheduler"]
    if scheduler is None:
        result["scheduler"] = None
    else:
        scheduler = _exact(scheduler, {"scheduler_id", "tick"}, "frame.scheduler")
        result["scheduler"] = {
            "scheduler_id": _text(scheduler["scheduler_id"], "scheduler.scheduler_id"),
            "tick": decode_integer(scheduler["tick"], minimum=0),
        }

    result["event_lambda"] = None if wire["event_lambda"] is None else decode_integer(wire["event_lambda"], minimum=0)

    phase = wire["chronon_phase"]
    if phase is None:
        result["chronon_phase"] = None
    else:
        if not isinstance(phase, list) or len(phase) != 2:
            raise TemporalCoordinateError("chronon_phase must contain two numeric envelopes")
        phase_values = [decode_binary64(phase[0]), decode_binary64(phase[1])]
        _check_phase(phase_values)
        result["chronon_phase"] = phase_values

    tau = wire["chemical_tau"]
    if tau is None:
        result["chemical_tau"] = None
    else:
        tau_value = decode_binary64(tau)
        if tau_value < 0.0:
            raise TemporalCoordinateError("chemical_tau must be non-negative")
        result["chemical_tau"] = tau_value

    canonical_bytes(dict(wire))
    return result


def encode_operation_span_v2(span: Mapping[str, Any]) -> dict[str, Any]:
    """Project an operation-span v0.1 mapping to span v0.2 and rebind its digest."""
    fields = {
        "format", "schema", "attempt_id", "span_id", "operation_id", "clock_actor_id",
        "clock_segment_id", "monotonic_start_ns", "monotonic_end_ns", "elapsed_ns",
        "clock_status", "outcome", "exception_type", "context", "measurement_scope", "span_digest",
    }
    raw = _exact(span, fields, "operation span")
    if raw["format"] != SPAN_FORMAT or raw["schema"] not in {"in-formation.operation-span/0.1", SPAN_SCHEMA}:
        raise TemporalCoordinateError("operation span format or source schema mismatch")
    if not isinstance(raw["context"], Mapping):
        raise TemporalCoordinateError("operation span context must be an object")
    start = _integer(raw["monotonic_start_ns"], "monotonic_start_ns", 0)
    end = _integer(raw["monotonic_end_ns"], "monotonic_end_ns", 0)
    elapsed = None if raw["elapsed_ns"] is None else _integer(raw["elapsed_ns"], "elapsed_ns", 0)
    if raw["clock_status"] == "measured":
        if end < start or elapsed != end - start:
            raise TemporalCoordinateError("measured span endpoints and elapsed value disagree")
    elif raw["clock_status"] == "regressed":
        if elapsed is not None:
            raise TemporalCoordinateError("regressed span elapsed value must be null")
    else:
        raise TemporalCoordinateError("unsupported span clock status")

    result = dict(raw)
    result["schema"] = SPAN_SCHEMA
    result["monotonic_start_ns"] = encode_integer(start)
    result["monotonic_end_ns"] = encode_integer(end)
    result["elapsed_ns"] = None if elapsed is None else encode_integer(elapsed)
    core = {key: value for key, value in result.items() if key != "span_digest"}
    canonical_bytes(core)
    from formats.canonical_metadata_v1 import canonical_digest
    result["span_digest"] = canonical_digest(core)
    return result


def decode_operation_span_v2(span: Mapping[str, Any]) -> dict[str, Any]:
    """Verify span v0.2 digest, then return an exact logical integer projection."""
    fields = {
        "format", "schema", "attempt_id", "span_id", "operation_id", "clock_actor_id",
        "clock_segment_id", "monotonic_start_ns", "monotonic_end_ns", "elapsed_ns",
        "clock_status", "outcome", "exception_type", "context", "measurement_scope", "span_digest",
    }
    raw = _exact(span, fields, "operation span v0.2")
    if raw["format"] != SPAN_FORMAT or raw["schema"] != SPAN_SCHEMA:
        raise TemporalCoordinateError("operation span v2 format or schema mismatch")
    from formats.canonical_metadata_v1 import canonical_digest
    core = {key: value for key, value in raw.items() if key != "span_digest"}
    if canonical_digest(core) != raw["span_digest"]:
        raise TemporalCoordinateError("operation span v2 digest mismatch")
    start = decode_integer(raw["monotonic_start_ns"], minimum=0)
    end = decode_integer(raw["monotonic_end_ns"], minimum=0)
    elapsed = None if raw["elapsed_ns"] is None else decode_integer(raw["elapsed_ns"], minimum=0)
    if raw["clock_status"] == "measured":
        if end < start or elapsed != end - start:
            raise TemporalCoordinateError("measured span endpoints and elapsed value disagree")
    elif raw["clock_status"] == "regressed":
        if elapsed is not None:
            raise TemporalCoordinateError("regressed span elapsed value must be null")
    else:
        raise TemporalCoordinateError("unsupported span clock status")
    result = dict(raw)
    result["schema"] = SPAN_SCHEMA
    result["monotonic_start_ns"] = start
    result["monotonic_end_ns"] = end
    result["elapsed_ns"] = elapsed
    return result
