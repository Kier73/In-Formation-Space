"""Independent reconstruction of TPP-001 public synthetic transcripts.

This module deliberately does not import the producer. A passing check shows
agreement with the declared equations, not a trusted physical measurement.
"""
from __future__ import annotations

from fractions import Fraction as Q
from hashlib import sha256
import json
import re

_V = {
    "electrical": (12, 3, 7, 3),
    "hydraulic": (8, 2, 11, -5),
    "resistive": (15, 3, 13, 1),
    "inertial": (18, 3, 17, -2),
}
_EXPECTED_SCHEMA = "in-formation-space.tactile-perception-process.tpp-001.v1"
_TEXT = re.compile(r"(drive|idle):([0-9]+)/(1|[1-9][0-9]*)\Z")


def _fraction(s):
    if not isinstance(s, str) or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)/[1-9][0-9]*", s):
        raise ValueError("non-rational field")
    value = Q(s)
    if s != f"{value.numerator}/{value.denominator}":
        raise ValueError("noncanonical fraction")
    return value


def _wire(wire, encoding):
    if encoding == "text":
        match = _TEXT.fullmatch(wire.decode("ascii"))
        if not match:
            raise ValueError("bad text instruction")
        kind = match.group(1)
        q = Q(int(match.group(2)), int(match.group(3)))
        canonical = f"{kind}:{q.numerator}/{q.denominator}".encode("ascii")
    elif encoding == "json":
        # Parsing is intentionally independent of producer's parser.
        pairs = json.loads(wire.decode("ascii"), object_pairs_hook=list)
        if not isinstance(pairs, list) or sorted(k for k, _ in pairs) != ["d", "kind", "n"]:
            raise ValueError("bad json instruction")
        fields = dict(pairs)
        if type(fields["n"]) is not int or type(fields["d"]) is not int or fields["d"] <= 0:
            raise ValueError("invalid JSON numerator/denominator")
        kind = fields["kind"]
        q = Q(fields["n"], fields["d"])
        canonical = json.dumps({"d": q.denominator, "kind": kind, "n": q.numerator},
                               sort_keys=True, separators=(",", ":")).encode("ascii")
    else:
        raise ValueError("unknown encoding")
    if wire != canonical or kind not in ("drive", "idle") or not 0 <= q <= 1:
        raise ValueError("noncanonical or unsupported instruction")
    if kind == "idle" and q:
        raise ValueError("nonzero idle")
    return kind, q


def verify(report):
    """Refuse malformed, forged or equation-inconsistent public transcripts."""
    if not isinstance(report, dict) or set(report) != {"schema", "scope", "route", "encoding", "events", "head_digest"}:
        raise ValueError("unexpected report shape")
    if report["schema"] != _EXPECTED_SCHEMA or report["scope"] != "synthetic-exact-not-physical-evidence":
        raise ValueError("scope/schema mismatch")
    route = report["route"]
    if route not in _V or report["encoding"] not in ("text", "json") or not isinstance(report["events"], list):
        raise ValueError("unknown route or invalid events")
    effort, divisor, gain, offset = _V[route]
    position = stored = Q(0)
    parent = "0" * 64
    fields = {"index", "input_hex", "parent_digest", "raw_sensor", "observed_position_m",
              "state_stored_j", "energy_in_j", "mechanical_work_j", "heat_j",
              "storage_delta_j", "effort", "flow", "digest"}
    for index, record in enumerate(report["events"]):
        if not isinstance(record, dict) or set(record) != fields or record["index"] != index or record["parent_digest"] != parent:
            raise ValueError("event structure or ancestry failed")
        try:
            wire = bytes.fromhex(record["input_hex"])
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid wire evidence") from exc
        if len(wire) > 160 or wire.hex() != record["input_hex"]:
            raise ValueError("noncanonical input bytes")
        kind, amount = _wire(wire, report["encoding"])
        if kind == "drive":
            movement = amount
            incoming = Q(effort, divisor) * amount
            heat = amount if route == "resistive" else Q(0)
            next_stored = stored + 2 * amount if route == "inertial" else stored
            upstream_effort, upstream_flow = Q(effort), amount / divisor
        else:
            movement = stored / 4 if route == "inertial" else Q(0)
            incoming = heat = upstream_effort = upstream_flow = Q(0)
            next_stored = Q(0) if route == "inertial" else stored
        next_position = position + movement
        work = 4 * movement
        delta = next_stored - stored
        if incoming != work + heat + delta:
            raise ValueError("independent energy accounting failed")
        expected = {
            "raw_sensor": gain * next_position + offset,
            "observed_position_m": next_position,
            "state_stored_j": next_stored, "energy_in_j": incoming,
            "mechanical_work_j": work, "heat_j": heat,
            "storage_delta_j": delta, "effort": upstream_effort, "flow": upstream_flow,
        }
        for label, target in expected.items():
            if _fraction(record[label]) != target:
                raise ValueError(f"model or sensor mismatch: {label}")
        event_bytes = json.dumps({k: v for k, v in record.items() if k != "digest"},
                                 sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        parent = sha256(event_bytes).hexdigest()
        if record["digest"] != parent:
            raise ValueError("event digest mismatch")
        position, stored = next_position, next_stored
    if report["head_digest"] != parent:
        raise ValueError("transcript head mismatch")
    return {"verified": True, "events": len(report["events"]),
            "position_m": f"{position.numerator}/{position.denominator}",
            "stored_j": f"{stored.numerator}/{stored.denominator}",
            "scope": "synthetic-model-consistency-only"}
