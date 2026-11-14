"""RE-010 hosted CI: separately generated origin receipts and real E-CPU clocks.

This module uses the pinned E-CPU runtime via PYTHONPATH. CI roles are distinct
jobs, not certified independent physical fault domains. Causal concurrency is
lack of vector-clock dependency, not physical simultaneity. HMAC keys are CI
fixtures, not trusted sensor keys in real hardware.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping, Sequence

from mailcpu.temporal import (
    CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile,
)
from coverage_reconstruction import CoverageError, sha
from common_mode_counter import produce_source
from ecpu_coverage_hosts import controller as make_controller, _causal, _check as check_controller
from ecpu_common_mode_hosts import (
    HOST_SCHEMA as RE009_HOST_SCHEMA, _verify_source_host, observer_host,
    verify as verify_re009,
)
from event_origin_commitment import (
    DEFAULT_CLAIMS, ORIGIN, ORIGIN_FIELDS, OriginError, SCHEMA,
    _body, make_origin, origin_key, registration, triangulate,
    verify_origin, verify_signed,
)
from coverage_reconstruction import _sign

HOST_SCHEMA = "in-formation.response-re010-hosted/0.1"
BIND_FIELDS = frozenset((
    "schema", "kind", "challenge", "actor", "key_id", "controller_digest",
    "event_digest", "stamp", "epoch",
))


def source_from_controller(ctrl: Mapping[str, Any], reg: Mapping[str, Any]) -> dict[str, Any]:
    """Source S signs counters WITHOUT owning C's independent causal context."""
    check_controller(ctrl, "controller")
    if ctrl["challenge"] != reg["challenge"]:
        raise OriginError("controller and source enrollment mismatch")
    source = produce_source(reg, controller_digest=ctrl["digest"])
    doc = {"schema": RE009_HOST_SCHEMA, "controller": ctrl, "source": source}
    return {**doc, "digest": sha(doc)}


def origin_host(ctrl: Mapping[str, Any], reg: Mapping[str, Any],
                claims: Sequence[tuple[int,str]] = DEFAULT_CLAIMS) -> dict[str, Any]:
    """Origin O receives only the controller, never source counts or A/B logs."""
    check_controller(ctrl, "controller")
    if ctrl["challenge"] != reg["challenge"]:
        raise OriginError("origin controller challenge mismatch")
    ctx = TemporalContext(ORIGIN, TemporalProfile(frozenset(
        {ClockDomain.CAUSAL, ClockDomain.MONOTONIC})),
        vector={"C":0,"A":0,"B":0,"O":0})
    ctx.receive_causal_stamp(CausalStamp.from_dict(ctrl["frame"]["causal"]))
    origin = make_origin(reg, claims, controller_digest=ctrl["digest"])
    bindings=[]
    for event in origin["receipts"]:
        ctx.emit_causal_stamp()
        frame=ctx.observe().to_dict()
        signed=_sign({**_body(reg,"binding",ctrl["digest"]),
            "epoch":event["epoch"],"event_digest":event["digest"],
            "stamp":frame["causal"]},origin_key(reg))
        bindings.append({"receipt":signed,"frame":frame})
    ctx.emit_causal_stamp()
    seal_frame=ctx.observe().to_dict()
    doc={"schema":HOST_SCHEMA,"role":ORIGIN,"challenge":reg["challenge"],
         "origin":origin,"bindings":bindings,"seal_frame":seal_frame,
         "physical_event_attestation":False}
    return {**doc,"digest":sha(doc)}


def verify_hosted_origin(ctrl: Mapping[str, Any], hosted: Mapping[str, Any],
                         reg: Mapping[str, Any], a_doc: Mapping[str,Any] | None = None,
                         b_doc: Mapping[str,Any] | None = None) -> dict[str, Any]:
    check_controller(ctrl,"controller")
    if not isinstance(hosted,dict) or set(hosted)!={
            "schema","role","challenge","origin","bindings","seal_frame",
            "physical_event_attestation","digest"}:
        raise OriginError("origin hosted envelope invalid")
    if (hosted["schema"]!=HOST_SCHEMA or hosted["role"]!=ORIGIN or
        hosted["challenge"]!=reg["challenge"] or
        hosted["challenge"]!=ctrl["challenge"] or
        hosted["physical_event_attestation"] is not False):
        raise OriginError("origin hosted identity or unsupported physical claim")
    if hosted["digest"]!=sha({k:v for k,v in hosted.items() if k!="digest"}):
        raise OriginError("origin hosted envelope digest invalid")
    accepted=verify_origin(hosted["origin"],reg,controller_digest=ctrl["digest"])
    bindings=hosted["bindings"]
    if not isinstance(bindings,list) or len(bindings)!=len(accepted):
        raise OriginError("origin event frame bindings missing")
    c=_causal(ctrl["frame"],"C")
    previous=c
    for event,binding in zip(hosted["origin"]["receipts"],bindings):
        if not isinstance(binding,dict) or set(binding)!={"receipt","frame"}:
            raise OriginError("origin event binding envelope malformed")
        receipt=binding["receipt"]
        verify_signed(receipt,reg,"binding",BIND_FIELDS,ctrl["digest"])
        stamp=_causal(binding["frame"],ORIGIN)
        if (receipt["epoch"]!=event["epoch"] or
            receipt["event_digest"]!=event["digest"] or
            receipt["stamp"]!=stamp.to_dict()):
            raise OriginError("origin signed event/stamp binding invalid")
        if previous.relation(stamp)!=CausalRelation.BEFORE:
            raise OriginError("origin event causal progression invalid")
        previous=stamp
    seal_stamp=_causal(hosted["seal_frame"],ORIGIN)
    if previous.relation(seal_stamp)!=CausalRelation.BEFORE:
        raise OriginError("origin seal not causally after event captures")
    if a_doc is not None and b_doc is not None:
        for actor, host in (("A",a_doc),("B",b_doc)):
            first=_causal(host["witness"]["bindings"][0]["frame"],actor)
            if c.relation(first)!=CausalRelation.BEFORE or \
               seal_stamp.relation(first)!=CausalRelation.CONCURRENT:
                raise OriginError("origin and observer causal independence contract violated")
    return {"origin_causal_sequence_valid":True,
            "controller_before_origin":"before",
            "origin_concurrent_A_and_B": "concurrent" if a_doc is not None else "not_checked",
            "cross_host_elapsed": None,
            "physical_origin_identity_attested":False}


def verify(source_doc: Mapping[str, Any], a_doc: Mapping[str, Any],
           b_doc: Mapping[str, Any], origin_doc: Mapping[str, Any],
           reg: Mapping[str, Any]) -> dict[str, Any]:
    _verify_source_host(source_doc,reg)
    # Exercise RE-009's actual pinned E-CPU source/observer causal comparison.
    prior=verify_re009(source_doc,a_doc,b_doc,reg)
    causal=verify_hosted_origin(source_doc["controller"],origin_doc,reg,a_doc,b_doc)
    a,b=a_doc["witness"],b_doc["witness"]
    triangle=triangulate(source_doc["source"],{"A":a["log"],"B":b["log"]},
          {"A":a_doc["ack"],"B":b_doc["ack"]},origin_doc["origin"],reg,
          (a["delivery"],),controller_digest=source_doc["controller"]["digest"])
    if triangle["status"]!="origin_corrob_source_claim_not_observer_readout" or \
       triangle["origin_only_epochs"]!=[3] or \
       prior["counter_reconstruction"]["source_observer_discrepancy"]!=1:
        raise OriginError("hosted four/three/three claim predicate not satisfied")
    return {"schema":HOST_SCHEMA,"status":"scoped_origin_counter_triangle_verified",
            "triangulation":triangle,"origin_causal_evidence":causal,
            "observer_causal_evidence":prior["causal_relation"],
            "physical_event_attested":False,"physical_common_mode_loss_proved":False,
            "independent_fault_domains_proved":False,"cross_host_elapsed":None}


def cli() -> None:
    mode=sys.argv[1] if len(sys.argv)==2 else ""
    inp=json.load(sys.stdin)
    if mode=="--controller":
        result=make_controller(inp["challenge"])
    elif mode=="--source":
        result=source_from_controller(inp["controller"],inp["registration"])
    elif mode in ("--A","--B"):
        result=observer_host(mode[-1],inp["source"],inp["registration"])
    elif mode=="--origin":
        result=origin_host(inp["controller"],inp["registration"])
    elif mode=="--verifier":
        result=verify(inp["source"],inp["A"],inp["B"],inp["origin"],inp["registration"])
    else:
        raise SystemExit("usage: --controller | --source | --A | --B | --origin | --verifier")
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    cli()