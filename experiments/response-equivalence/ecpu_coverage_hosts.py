"""RE-008 synthetic independent-job overlap using real E-CPU temporal stamps.

The model requires mailcpu.temporal at the repository-pinned E-CPU revision.
Two CI runners create separate causal contexts and CI-HMAC coverage receipts.
This is NOT independent physical sensor attestation or exhaustive event sensing.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from coverage_reconstruction import (
    ACTORS, EPOCHS, SCHEMA, CoverageError, SLOT_FIELDS, _base, _key, _sign,
    _verify, delayed_delivery, enrollment, produce_log, reconstruct, sha, verify_log,
)

BIND_FIELDS = frozenset(("schema", "kind", "challenge", "actor", "key_id", "slot_digest", "stamp"))
HOST_SCHEMA = "in-formation.response-re008-hosted/0.1"
OVERRIDES = {"A": {2: "dropout", 5: "dropout", 6: "pending"},
             "B": {1: "dropout", 4: "dropout"}}


def context(actor: str) -> TemporalContext:
    return TemporalContext(actor,
        TemporalProfile(frozenset({ClockDomain.CAUSAL, ClockDomain.MONOTONIC, ClockDomain.WALL})),
        vector={"C": 0, "A": 0, "B": 0})


def _wrapped(doc: dict[str, Any]) -> dict[str, Any]:
    return {**doc, "digest": sha(doc)}


def _check(doc: Any, role: str) -> None:
    if not isinstance(doc, dict) or doc.get("schema") != HOST_SCHEMA or doc.get("role") != role:
        raise CoverageError("invalid hosted role identity")
    if doc.get("digest") != sha({k: v for k, v in doc.items() if k != "digest"}):
        raise CoverageError("hosted envelope hash mismatch (unkeyed)")


def controller(challenge: str) -> dict[str, Any]:
    if not isinstance(challenge, str) or len(challenge) < 20:
        raise CoverageError("invalid session challenge")
    ctx = context("C")
    ctx.emit_causal_stamp()
    return _wrapped({"schema": HOST_SCHEMA, "role": "controller", "challenge": challenge,
                     "epochs": list(EPOCHS), "frame": ctx.observe().to_dict()})


def witness(actor: str, controller_doc: Mapping[str, Any], reg: Mapping[str, Any]) -> dict[str, Any]:
    if actor not in ACTORS:
        raise CoverageError("unknown witness")
    _check(controller_doc, "controller")
    if controller_doc["challenge"] != reg["challenge"] or controller_doc["epochs"] != list(EPOCHS):
        raise CoverageError("controller challenge or epoch declaration mismatch")
    ctx = context(actor)
    ctx.receive_causal_stamp(CausalStamp.from_dict(controller_doc["frame"]["causal"]))
    log = produce_log(actor, reg, OVERRIDES[actor])
    bindings = []
    for slot in log["records"]:
        ctx.emit_causal_stamp()
        frame = ctx.observe().to_dict()
        # Bind the actor's genuine E-CPU stamp to a signed coverage slot.
        receipt = _sign({**_base(reg, actor, "binding"),
                         "slot_digest": slot["digest"], "stamp": frame["causal"]},
                        _key(reg, actor))
        bindings.append({"receipt": receipt, "frame": frame})
    delivery = None
    delivery_frame = None
    if actor == "A":
        delivery = delayed_delivery(actor, reg, log["records"][6], delivery_tick=99)
        ctx.emit_causal_stamp()
        delivery_frame = ctx.observe().to_dict()
    return _wrapped({"schema": HOST_SCHEMA, "role": actor,
                     "challenge": reg["challenge"], "log": log, "bindings": bindings,
                     "delivery": delivery, "delivery_frame": delivery_frame,
                     "physical_sensor_attestation": False})


def _causal(data: Any, actor: str) -> CausalStamp:
    if not isinstance(data, dict) or data.get("actor_id") != actor or not isinstance(data.get("causal"), dict):
        raise CoverageError("typed E-CPU frame invalid or wrong actor")
    stamp = CausalStamp.from_dict(data["causal"])
    if stamp.actor_id != actor:
        raise CoverageError("causal stamp actor mismatch")
    return stamp


def verify(controller_doc: Mapping[str, Any], witness_a: Mapping[str, Any],
           witness_b: Mapping[str, Any], reg: Mapping[str, Any]) -> dict[str, Any]:
    _check(controller_doc, "controller")
    _check(witness_a, "A")
    _check(witness_b, "B")
    if controller_doc["epochs"] != list(EPOCHS) or any(
        r["challenge"] != controller_doc["challenge"] for r in (witness_a, witness_b)
    ) or reg["challenge"] != controller_doc["challenge"]:
        raise CoverageError("challenge/epoch mismatch")
    c = _causal(controller_doc["frame"], "C")
    verified = {}
    stamped = {}
    logs = {}
    for actor, host in (("A", witness_a), ("B", witness_b)):
        if host.get("physical_sensor_attestation") is not False:
            raise CoverageError("unsupported physical sensor claim")
        log = host["log"]
        result = verify_log(actor, log, reg)
        if result["status"] != "complete":
            raise CoverageError("hosted log continuity incomplete")
        bindings = host["bindings"]
        if not isinstance(bindings, list) or len(bindings) != len(EPOCHS):
            raise CoverageError("missing frame bindings")
        stamps = []
        for slot, binding in zip(log["records"], bindings):
            signed = binding["receipt"]
            _verify(signed, reg, actor, "binding", BIND_FIELDS)
            stamp = _causal(binding["frame"], actor)
            if signed["slot_digest"] != slot["digest"] or signed["stamp"] != stamp.to_dict():
                raise CoverageError("signed slot/causal stamp binding invalid")
            stamps.append(stamp)
        if c.relation(stamps[0]) != CausalRelation.BEFORE or any(
            p.relation(n) != CausalRelation.BEFORE for p, n in zip(stamps, stamps[1:])
        ):
            raise CoverageError("E-CPU temporal progression invalid")
        stamped[actor] = stamps
        verified[actor] = result
        logs[actor] = log
    if stamped["A"][0].relation(stamped["B"][0]) != CausalRelation.CONCURRENT:
        raise CoverageError("witnesses unexpectedly ordered; independence contract violated")
    if witness_b["delivery"] is not None or witness_b["delivery_frame"] is not None:
        raise CoverageError("undeclared B followup")
    a_delivery = witness_a["delivery"]
    if a_delivery is None or witness_a["delivery_frame"] is None:
        raise CoverageError("missing delayed capture-bound completion")
    a_after = _causal(witness_a["delivery_frame"], "A")
    if stamped["A"][-1].relation(a_after) != CausalRelation.BEFORE:
        raise CoverageError("delivery not causally after original capture")
    report = reconstruct(logs, reg, (a_delivery,))
    if report["blind_epoch_bound"] != 0 or report["conflict_epochs"]:
        raise CoverageError("expected synthetic overlap coverage not established")
    return {"schema": HOST_SCHEMA, "status": "declared_epoch_coverage_verified",
            "coverage": report, "causal_relation": {
                "controller_before_A": "before", "controller_before_B": "before",
                "A_concurrent_B": "concurrent", "A_capture_before_delivery": "before"},
            "coverage_assumption": "synthetic CI-enrolled reporters for eight declared capture epochs",
            "external_event_loss_bound": None, "cross_host_elapsed": None,
            "physical_sensor_identity_proved": False,
            "physical_event_completeness_proved": False}


def cli() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode == "--enroll":
        result = enrollment()
    elif mode == "--controller":
        inp = json.load(sys.stdin)
        result = controller(inp["challenge"])
    elif mode in ("--A", "--B"):
        inp = json.load(sys.stdin)
        result = witness(mode[-1], inp["controller"], inp["enrollment"])
    elif mode == "--verifier":
        inp = json.load(sys.stdin)
        result = verify(inp["controller"], inp["A"], inp["B"], inp["enrollment"])
    else:
        raise SystemExit("usage: --enroll | --controller | --A | --B | --verifier")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    cli()
