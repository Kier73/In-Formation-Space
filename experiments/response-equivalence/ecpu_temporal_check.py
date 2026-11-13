"""RE-004 hosted integration: real E-CPU TemporalContext and CausalStamp.

This module must be run with PYTHONPATH pointing to pinned Kier73/E-CPU.
A and B can execute in separate GitHub Actions jobs; a third job reconstructs
using only the public producer envelopes, without shared clock subtraction.
GitHub workflow/artifact provenance is distinct from cryptographic source signing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from intervention_or_drift import (
    LAWS, EvidenceError, digest, produce_a, produce_b, reconstruct,
)

HOSTED_SCHEMA = "in-formation.re004-ecpu-temporal/1"
PROFILE = TemporalProfile(frozenset({ClockDomain.MONOTONIC, ClockDomain.CAUSAL}))


def _clock(actor: str) -> TemporalContext:
    return TemporalContext(actor, PROFILE, vector={"A": 0, "B": 0})


def _frame(clock: TemporalContext, record: Mapping[str, Any]) -> dict[str, Any]:
    clock.emit_causal_stamp()
    temporal = clock.observe().to_dict()
    return {"record_digest": record["digest"], "temporal_frame": temporal,
            "binding_digest": digest({"record_digest": record["digest"], "temporal_frame": temporal})}


def produce_source(truth: str) -> dict[str, Any]:
    producer = produce_a(truth)
    ctx = _clock("A")
    bindings = [_frame(ctx, record) for record in producer["records"]]
    return {"public": {"schema": HOSTED_SCHEMA, "actor": "A",
                       "records": producer["records"], "handoff": producer["handoff"],
                       "bindings": bindings},
            "private": {"checkpoint": producer["private_checkpoint"],
                        "nonce": producer["private_nonce"]}}


def produce_receiver(truth: str, source: Mapping[str, Any], private: Mapping[str, Any],
                     *, permitted: bool = True) -> dict[str, Any]:
    if source.get("schema") != HOSTED_SCHEMA or source.get("actor") != "A":
        raise EvidenceError("invalid source envelope")
    if not source.get("bindings") or len(source["bindings"]) != 2:
        raise EvidenceError("missing source causal frames")
    # Receiver uses a *real E-CPU CausalStamp merge* after receiving the
    # source's latest frame. No source-independent event causation is inferred.
    source_stamp = CausalStamp.from_dict(source["bindings"][-1]["temporal_frame"]["causal"])
    ctx = _clock("B")
    ctx.receive_causal_stamp(source_stamp)
    grants = ["environment:read"] if permitted else []
    producer = produce_b(truth, source["handoff"], private["checkpoint"],
                         private["nonce"], ["witness"], grants)
    bindings = [_frame(ctx, rec) for rec in producer["records"]]
    return {"schema": HOSTED_SCHEMA, "actor": "B", "records": producer["records"],
            "acknowledged_handoff": producer["acknowledged_handoff"],
            "bindings": bindings, "permits": grants}


def _check_bindings(envelope: Mapping[str, Any], expected_actor: str) -> list[CausalStamp]:
    if envelope.get("schema") != HOSTED_SCHEMA or envelope.get("actor") != expected_actor:
        raise EvidenceError("invalid temporal envelope")
    records, bindings = envelope.get("records"), envelope.get("bindings")
    if not isinstance(records, list) or not isinstance(bindings, list) or len(bindings) != len(records):
        raise EvidenceError("missing temporal event binding")
    stamps = []
    for rec, evidence in zip(records, bindings):
        if set(evidence) != {"record_digest", "temporal_frame", "binding_digest"}:
            raise EvidenceError("malformed event binding")
        frame = evidence["temporal_frame"]
        if not isinstance(frame, dict) or frame.get("actor_id") != expected_actor:
            raise EvidenceError("wrong temporal actor")
        if evidence["record_digest"] != rec["digest"] or evidence["binding_digest"] != digest({
            "record_digest": rec["digest"], "temporal_frame": frame,
        }):
            raise EvidenceError("record-to-frame commitment broken")
        if any(frame.get(name) is not None for name in
               ("wall", "scheduler", "event_lambda", "chronon_phase", "chemical_tau")):
            raise EvidenceError("undeclared temporal domain")
        monotonic = frame.get("monotonic")
        if not isinstance(monotonic, dict) or monotonic.get("actor_id") != expected_actor:
            raise EvidenceError("wrong monotonic coordinate actor")
        stamp = CausalStamp.from_dict(frame["causal"])
        if stamp.actor_id != expected_actor:
            raise EvidenceError("wrong causal coordinate actor")
        stamps.append(stamp)
    return stamps


def verify(source: Mapping[str, Any], receiver: Mapping[str, Any]) -> dict[str, Any]:
    a_stamps = _check_bindings(source, "A")
    b_stamps = _check_bindings(receiver, "B")
    if len(a_stamps) != 2 or len(b_stamps) != 1:
        raise EvidenceError("wrong experiment event count")
    if a_stamps[0].relation(a_stamps[1]) != CausalRelation.BEFORE:
        raise EvidenceError("source event precedence not established")
    if a_stamps[1].relation(b_stamps[0]) != CausalRelation.BEFORE:
        raise EvidenceError("receiver did not causally follow source")
    if b_stamps[0].vector_map().get("A") != a_stamps[1].vector_map().get("A"):
        raise EvidenceError("incompatible causal handoff")
    if receiver.get("acknowledged_handoff") != source["handoff"]["digest"]:
        raise EvidenceError("receiver acknowledged wrong handoff")
    scope = frozenset(receiver.get("permits", []))
    model = reconstruct(source["records"], receiver["records"], source["handoff"], scope)
    return {"schema": HOSTED_SCHEMA, "causal_relation": {
                "A0_A1": "before", "A1_B0": "before"},
            "model_reconstruction": model,
            "trusted_clock_evidence": "E-CPU typed local and causal frames",
            "origin_authentication": "not established by unkeyed commitments",
            "external_event_source_attribution": None,
            "cross_host_elapsed": None}


def demonstration() -> dict[str, Any]:
    source = produce_source("triggered_external")
    receiver = produce_receiver("triggered_external", source["public"], source["private"])
    return verify(source["public"], receiver)


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--source":
        obj = json.load(sys.stdin)
        print(json.dumps(produce_source(obj["truth"])))
    elif len(sys.argv) == 2 and sys.argv[1] == "--receiver":
        obj = json.load(sys.stdin)
        print(json.dumps(produce_receiver(obj["truth"], obj["source"], obj["private"],
                                          permitted=obj.get("permitted", True))))
    elif len(sys.argv) == 2 and sys.argv[1] == "--verifier":
        obj = json.load(sys.stdin)
        print(json.dumps(verify(obj["source"], obj["receiver"])))
    elif len(sys.argv) == 1:
        print(json.dumps(demonstration(), indent=2, sort_keys=True))
    else:
        raise SystemExit("usage: ecpu_temporal_check.py [--source|--receiver|--verifier]")


if __name__ == "__main__":
    main()
