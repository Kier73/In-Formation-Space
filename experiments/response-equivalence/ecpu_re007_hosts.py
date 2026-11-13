"""RE-007 scoped, synthetic two-job E-CPU causal fixture (runtime import required).

GitHub-hosted job identity and CI-shared HMAC key possession are not proof of
physical sensor identity, completeness or causation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import secrets
import sys
from typing import Any, Mapping

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from partial_observation import (
    LAWS, ObservationError, SCHEMA, State, apply_probe, digest, issue_pending,
    make_request, response, result_receipt, verify_receipt,
)


def enrollment() -> dict[str, str]:
    key = secrets.token_hex(32)
    return {"challenge": secrets.token_hex(24), "sensor_key": key,
            "sensor_key_id": hashlib.sha256(bytes.fromhex(key)).hexdigest()}


def _profile(actor: str) -> TemporalContext:
    return TemporalContext(actor,
        TemporalProfile(frozenset({ClockDomain.CAUSAL, ClockDomain.MONOTONIC, ClockDomain.WALL})),
        vector={"C": 0, "S": 0})


def _wrapped(document: dict[str, Any]) -> dict[str, Any]:
    return {**document, "digest": digest(document)}


def _check_record(data: Mapping[str, Any], expected: str) -> None:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("role") != expected:
        raise ObservationError("wrong schema/role")
    if not isinstance(data.get("digest"), str) or data["digest"] != digest({k: v for k, v in data.items() if k != "digest"}):
        raise ObservationError("record digest mismatch (not an authentication signature)")


def controller(challenge: str) -> dict[str, Any]:
    if not isinstance(challenge, str) or len(challenge) < 16:
        raise ObservationError("invalid enrollment challenge")
    ctx = _profile("C")
    ctx.emit_causal_stamp()
    frame = ctx.observe().to_dict()
    request = make_request(challenge, "re007-early", "resonance", 0)
    return _wrapped({"schema": SCHEMA, "role": "controller",
                     "challenge": challenge, "request": request, "frame": frame})


def sensor(controller_data: Mapping[str, Any], enrollment_data: Mapping[str, Any],
           *, truth: str = "transient") -> dict[str, Any]:
    _check_record(controller_data, "controller")
    if truth not in LAWS:
        raise ObservationError("unknown synthetic world")
    key = _enrolled_key(enrollment_data)
    if controller_data["challenge"] != enrollment_data["challenge"]:
        raise ObservationError("enrollment challenge changed")
    ctx = _profile("S")
    received = CausalStamp.from_dict(controller_data["frame"]["causal"])
    ctx.receive_causal_stamp(received)
    state = State()
    request_early = controller_data["request"]
    pending_early, value_early = issue_pending(request_early, state=state, law=truth)
    capture_early = ctx.observe().to_dict()
    # The first response remains pending while an acknowledged intervention occurs.
    state = apply_probe(state, "prime")
    ctx.emit_causal_stamp()
    prime_frame = ctx.observe().to_dict()
    ctx.emit_causal_stamp()
    late_frame = ctx.observe().to_dict()
    early_receipt = result_receipt(pending_early, value=value_early, status="returned",
                                  delivered_revision=state.revision, sensor_key=key,
                                  sensor_stamp=late_frame["causal"])
    # Take a fresh observation after the state-changing probe.
    request_later = make_request(controller_data["challenge"], "re007-post-prime", "resonance", 1)
    ctx.emit_causal_stamp()
    capture_later = ctx.observe().to_dict()
    pending_later, value_later = issue_pending(request_later, state=state, law=truth)
    ctx.emit_causal_stamp()
    delivery_later = ctx.observe().to_dict()
    later_receipt = result_receipt(pending_later, value=value_later, status="returned",
                                  delivered_revision=state.revision, sensor_key=key,
                                  sensor_stamp=delivery_later["causal"])
    return _wrapped({"schema": SCHEMA, "role": "sensor",
                     "challenge": controller_data["challenge"],
                     "early": {"pending": pending_early, "capture_frame": capture_early,
                               "receipt": early_receipt, "delivery_frame": late_frame},
                     "prime_frame": prime_frame,
                     "later": {"pending": pending_later, "capture_frame": capture_later,
                               "receipt": later_receipt, "delivery_frame": delivery_later},
                     "private_physical_sensor_attestation": False})


def _enrolled_key(registration: Mapping[str, Any]) -> bytes:
    if not isinstance(registration, dict) or set(registration) != {"challenge", "sensor_key", "sensor_key_id"}:
        raise ObservationError("invalid enrollment fields")
    try:
        key = bytes.fromhex(registration["sensor_key"])
    except (ValueError, TypeError, KeyError) as e:
        raise ObservationError("invalid enrollment key") from e
    if len(key) != 32 or hashlib.sha256(key).hexdigest() != registration["sensor_key_id"]:
        raise ObservationError("enrollment key id mismatch")
    if not isinstance(registration["challenge"], str) or len(registration["challenge"]) < 16:
        raise ObservationError("invalid enrollment challenge")
    return key


def _stamp(frame: Mapping[str, Any], actor: str) -> CausalStamp:
    if not isinstance(frame, dict) or frame.get("actor_id") != actor or not isinstance(frame.get("causal"), dict):
        raise ObservationError("temporal frame wrong actor or missing causal field")
    stamp = CausalStamp.from_dict(frame["causal"])
    if stamp.actor_id != actor:
        raise ObservationError("causal actor binding mismatched")
    return stamp


def verify(controller_data: Mapping[str, Any], sensor_data: Mapping[str, Any],
           enrollment_data: Mapping[str, Any]) -> dict[str, Any]:
    """Independent verifier gets public records and fixture enrollment key only."""
    _check_record(controller_data, "controller")
    _check_record(sensor_data, "sensor")
    key = _enrolled_key(enrollment_data)
    if not (controller_data["challenge"] == sensor_data["challenge"] == enrollment_data["challenge"]):
        raise ObservationError("source/witness enrollment challenge mismatch")
    original = controller_data["request"]
    if original != make_request(controller_data["challenge"], "re007-early", "resonance", 0):
        raise ObservationError("unexpected initial request contract")
    early, later = sensor_data["early"], sensor_data["later"]
    if early["pending"].get("request") != original:
        raise ObservationError("early capture request is not controller request")
    second_request = make_request(controller_data["challenge"], "re007-post-prime", "resonance", 1)
    if later["pending"].get("request") != second_request:
        raise ObservationError("post-prime capture request invalid")
    early_admitted = verify_receipt(original, early["pending"], early["receipt"], sensor_key=key)
    late_admitted = verify_receipt(second_request, later["pending"], later["receipt"],
                                  sensor_key=key, already_accepted=frozenset({original["request_id"]}))
    if early["receipt"]["sensor_stamp"] != early["delivery_frame"]["causal"] or \
            later["receipt"]["sensor_stamp"] != later["delivery_frame"]["causal"]:
        raise ObservationError("signed sensor frame mismatch")
    if early_admitted["capture_revision"] != 0 or early_admitted["delivery_revision"] != 1 or \
            late_admitted["capture_revision"] != 1 or late_admitted["delivery_revision"] != 1:
        raise ObservationError("intervention-aware capture/delivery revision invalid")
    frames = (controller_data["frame"], early["capture_frame"], sensor_data["prime_frame"],
              early["delivery_frame"], later["capture_frame"], later["delivery_frame"])
    stamps = [_stamp(f, "C" if i == 0 else "S") for i, f in enumerate(frames)]
    if any(left.relation(right) != CausalRelation.BEFORE
           for left, right in zip(stamps, stamps[1:])):
        raise ObservationError("E-CPU vector clocks do not establish required causal chain")
    readings = (early_admitted["admitted_measurement"], late_admitted["admitted_measurement"])
    survivors = list(LAWS)
    for idx, measured in enumerate(readings):
        if measured is None:
            continue
        survivors = [law for law in survivors if response(law, State(primed=bool(idx), revision=idx),
                                                        "resonance") == measured]
    return {"schema": SCHEMA, "status": "identified_within_declared_finite_model" if len(survivors) == 1 else "unresolved",
            "survivors": survivors, "readings": list(readings),
            "delayed_reply_interpreted_at_capture_revision": 0,
            "causal_order": ["C0<S_capture0", "S_capture0<S_prime", "S_prime<S_delivery0",
                             "S_delivery0<S_capture1", "S_capture1<S_delivery1"],
            "cross_host_elapsed": None, "sensor_authentication": "CI_enrolled_HMAC_key_possession_only",
            "physical_sensor_identity_proved": False,
            "absence_of_unobserved_disturbances_proved": False,
            "physical_causation_proved": False}


def demo() -> dict[str, Any]:
    reg = enrollment()
    ctrl = controller(reg["challenge"])
    sensed = sensor(ctrl, reg)
    return verify(ctrl, sensed, reg)


def cli() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else None
    if mode == "--enroll":
        result = enrollment()
    elif mode == "--controller":
        obj = json.load(sys.stdin)
        result = controller(obj["challenge"])
    elif mode == "--sensor":
        obj = json.load(sys.stdin)
        result = sensor(obj["controller"], obj["enrollment"], truth=obj.get("truth", "transient"))
    elif mode == "--verifier":
        obj = json.load(sys.stdin)
        result = verify(obj["controller"], obj["sensor"], obj["enrollment"])
    else:
        raise SystemExit("usage: ecpu_re007_hosts.py --enroll|--controller|--sensor|--verifier")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    cli()
