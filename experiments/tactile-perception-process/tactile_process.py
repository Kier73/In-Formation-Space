"""TPP-001: exact synthetic action/response translations across declared ports.

No physical devices are measured or controlled. All quantities use Fraction;
model conservation is checked per transition, not inferred from a checksum.
"""
from __future__ import annotations

from collections import deque
from fractions import Fraction
from hashlib import sha256
import json
import re

ROUTES = {
    "electrical": {"effort": 12, "flow_divisor": 3, "sensor_gain": 7, "sensor_offset": 3},
    "hydraulic": {"effort": 8, "flow_divisor": 2, "sensor_gain": 11, "sensor_offset": -5},
    "resistive": {"effort": 15, "flow_divisor": 3, "sensor_gain": 13, "sensor_offset": 1},
    "inertial": {"effort": 18, "flow_divisor": 3, "sensor_gain": 17, "sensor_offset": -2},
}
SCHEMA = "in-formation-space.tactile-perception-process.tpp-001.v1"
_ACTION = re.compile(rb"^(drive|idle):([0-9]+)/(1|[1-9][0-9]*)$")


def ratio(value):
    """Canonical rational serialization, rejecting float approximations."""
    if not isinstance(value, Fraction):
        raise TypeError("ratios must be Fractions")
    return f"{value.numerator}/{value.denominator}"


def action_wire(kind, amount=Fraction(0), encoding="text"):
    if kind not in ("drive", "idle") or not isinstance(amount, Fraction):
        raise ValueError("invalid action")
    if not 0 <= amount <= 1 or (kind == "idle" and amount):
        raise ValueError("action amount outside declared contract")
    if encoding == "text":
        return f"{kind}:{ratio(amount)}".encode("ascii")
    if encoding == "json":
        return json.dumps({"kind": kind, "n": amount.numerator, "d": amount.denominator},
                          sort_keys=True, separators=(",", ":")).encode("ascii")
    raise ValueError("unknown wire encoding")


def decode_action(wire, encoding):
    """Interpret bytes through one declared, unambiguous receiver vocabulary."""
    if not isinstance(wire, bytes) or len(wire) > 160:
        raise ValueError("invalid command bytes")
    if encoding == "text":
        match = _ACTION.fullmatch(wire)
        if match is None:
            raise ValueError("malformed text action")
        kind = match.group(1).decode("ascii")
        amount = Fraction(int(match.group(2)), int(match.group(3)))
    elif encoding == "json":
        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result
        try:
            obj = json.loads(wire.decode("ascii"), object_pairs_hook=no_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed JSON action") from exc
        if not isinstance(obj, dict) or set(obj) != {"kind", "n", "d"}:
            raise ValueError("incorrect JSON fields")
        kind = obj["kind"]
        if type(obj["n"]) is not int or type(obj["d"]) is not int or obj["d"] <= 0:
            raise ValueError("invalid JSON rational")
        amount = Fraction(obj["n"], obj["d"])
    else:
        raise ValueError("unknown wire encoding")
    if kind not in ("drive", "idle") or not 0 <= amount <= 1:
        raise ValueError("unsupported action or amount")
    if kind == "idle" and amount:
        raise ValueError("idle cannot carry drive magnitude")
    if action_wire(kind, amount, encoding) != wire:
        raise ValueError("noncanonical action representation")
    return kind, amount


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def transition(route, position, stored, kind, amount):
    """Deliberately idealized ports with explicit mechanical/thermal/storage balance."""
    if route not in ROUTES:
        raise ValueError("unknown route")
    if kind == "drive":
        step = amount
        energy_in = Fraction(ROUTES[route]["effort"], ROUTES[route]["flow_divisor"]) * amount
        heat = amount if route == "resistive" else Fraction(0)
        delta_storage = 2 * amount if route == "inertial" else Fraction(0)
        new_stored = stored + delta_storage
        effort = Fraction(ROUTES[route]["effort"])
        flow = amount / ROUTES[route]["flow_divisor"]
    else:
        energy_in = heat = effort = flow = Fraction(0)
        step = stored / 4 if route == "inertial" else Fraction(0)
        new_stored = Fraction(0) if route == "inertial" else stored
        delta_storage = new_stored - stored
    mechanical_work = 4 * step  # 4 N times metres, one-second step
    if energy_in != mechanical_work + heat + delta_storage:
        raise AssertionError("model violates declared energy balance")
    if kind == "drive" and energy_in != effort * flow:  # 1 second interval
        raise AssertionError("port power mismatch")
    return position + step, new_stored, (energy_in, mechanical_work, heat, delta_storage, effort, flow)


def emit_report(route, actions, encoding="text"):
    if route not in ROUTES:
        raise ValueError("unknown route")
    if encoding not in ("text", "json"):
        raise ValueError("unknown wire encoding")
    position = stored = Fraction(0)
    previous = "0" * 64
    events = []
    config = ROUTES[route]
    for index, (kind, magnitude) in enumerate(actions):
        wire = action_wire(kind, magnitude, encoding)
        kind, amount = decode_action(wire, encoding)
        position, stored, power = transition(route, position, stored, kind, amount)
        raw = config["sensor_gain"] * position + config["sensor_offset"]
        decoded = (raw - config["sensor_offset"]) / config["sensor_gain"]
        assert decoded == position
        event = {
            "index": index, "input_hex": wire.hex(), "parent_digest": previous,
            "raw_sensor": ratio(raw), "observed_position_m": ratio(decoded),
            "state_stored_j": ratio(stored),
            "energy_in_j": ratio(power[0]), "mechanical_work_j": ratio(power[1]),
            "heat_j": ratio(power[2]), "storage_delta_j": ratio(power[3]),
            "effort": ratio(power[4]), "flow": ratio(power[5]),
        }
        previous = sha256(canonical(event)).hexdigest()
        event["digest"] = previous
        events.append(event)
    return {"schema": SCHEMA, "scope": "synthetic-exact-not-physical-evidence",
            "route": route, "encoding": encoding, "events": events,
            "head_digest": previous}


def observe(report, property_name):
    if property_name == "position":
        return tuple(event["observed_position_m"] for event in report["events"])
    if property_name == "energy":
        return tuple(event["energy_in_j"] for event in report["events"])
    if property_name == "heat":
        return tuple(event["heat_j"] for event in report["events"])
    raise ValueError("unknown observation contract")


def distinguish(route_a, route_b, property_name, alphabet=None, max_depth=3):
    """Bounded shortest distinguishing continuation; exhaustion is not equivalence."""
    if alphabet is None:
        alphabet = (("drive", Fraction(1, 2)), ("idle", Fraction(0)))
    if not 1 <= max_depth <= 8:
        raise ValueError("invalid observation horizon")
    if route_a not in ROUTES or route_b not in ROUTES:
        raise ValueError("unknown route")
    tested = 0
    queue = deque([()])
    while queue:
        sequence = queue.popleft()
        if len(sequence) == max_depth:
            continue
        for action in alphabet:
            future = sequence + (action,)
            left = emit_report(route_a, future)
            right = emit_report(route_b, future)
            tested += 1
            if observe(left, property_name) != observe(right, property_name):
                return {"status": "distinguished", "sequence": [f"{kind}:{ratio(q)}" for kind, q in future],
                        "tested": tested, "left": list(observe(left, property_name)),
                        "right": list(observe(right, property_name))}
            queue.append(future)
    return {"status": "undetermined-within-supplied-horizon", "tested": tested,
            "max_depth": max_depth}


def demonstration():
    actions = (("drive", Fraction(1, 2)), ("idle", Fraction(0)),
               ("drive", Fraction(1, 4)))
    ea = emit_report("electrical", actions, "text")
    hy = emit_report("hydraulic", actions, "json")
    return {
        "schema": SCHEMA,
        "tested": "synthetic exact rational model only",
        "paired_observations": {"electrical": list(observe(ea, "position")),
                                "hydraulic": list(observe(hy, "position"))},
        "raw_electrical": [x["raw_sensor"] for x in ea["events"]],
        "raw_hydraulic": [x["raw_sensor"] for x in hy["events"]],
        "continuation_probes": {
            "electrical_vs_hydraulic_position": distinguish("electrical", "hydraulic", "position"),
            "electrical_vs_inertial_position": distinguish("electrical", "inertial", "position"),
            "electrical_vs_inertial_energy": distinguish("electrical", "inertial", "energy"),
            "electrical_vs_resistive_position": distinguish("electrical", "resistive", "position"),
            "electrical_vs_resistive_energy": distinguish("electrical", "resistive", "energy"),
        },
    }


if __name__ == "__main__":
    print(json.dumps(demonstration(), indent=2, sort_keys=True))
