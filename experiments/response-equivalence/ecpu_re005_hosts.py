"""RE-005 GitHub-hosted roles using the actual pinned E-CPU TemporalContext.

Run with PYTHONPATH=external/E-CPU:experiments/response-equivalence.
Roles A/C are independent causal actors; B merges both only after artifact handoff.
Signing key enrolment is a CI test fixture, NOT physical source attestation.
"""
from __future__ import annotations

import json
import sys

from mailcpu.temporal import CausalRelation, CausalStamp, ClockDomain, TemporalContext, TemporalProfile
from independent_event_causation import (
    EvidenceError, enroll, infer, make_receiver, make_source, make_witness,
    verify_source, verify_receiver, verify_witness_bundle,
)

ROSTER = {"A": 0, "B": 0, "C": 0}


def context(actor: str) -> TemporalContext:
    return TemporalContext(actor, TemporalProfile(frozenset({ClockDomain.CAUSAL})), vector=ROSTER)


def stamp_factory(ctx: TemporalContext):
    def produce() -> dict:
        ctx.emit_causal_stamp()
        frame = ctx.observe()  # actual typed E-CPU TemporalFrame, not a stand-in vector implementation
        assert frame.causal is not None
        return frame.causal.to_dict()
    return produce


def source() -> dict:
    return make_source(stamp_factory(context("A")))


def witness(enrollment: dict, *, permitted: bool = True) -> dict:
    return make_witness(stamp_factory(context("C")), enrollment["key_hex"],
                        enrollment["key_id"], permitted=permitted)


def receiver(a: dict, c: dict, *, truth: str = "common_cause_marker") -> dict:
    # No witness authentication key supplied to B: it only links public evidence.
    verify_source(a)
    if c.get("role") != "C" or len(c.get("records", [])) != 3:
        raise EvidenceError("invalid witness handoff")
    ctx = context("B")
    ctx.receive_causal_stamp(CausalStamp.from_dict(a["records"][-1]["causal"]))
    ctx.receive_causal_stamp(CausalStamp.from_dict(c["records"][-1]["causal"]))
    return make_receiver(truth, stamp_factory(ctx), a, c)


def _stamps(records: list[dict], actor: str) -> list[CausalStamp]:
    result = []
    for rec in records:
        stamp = CausalStamp.from_dict(rec["causal"])
        if stamp.actor_id != actor:
            raise EvidenceError("temporal actor identity mismatch")
        result.append(stamp)
    if len(result) != 3:
        raise EvidenceError("missing actor causal frame")
    if any(x.relation(y) != CausalRelation.BEFORE for x, y in zip(result, result[1:])):
        raise EvidenceError("actor-local causal advancement invalid")
    # No arbitrary jumps or outside dependencies are accepted in the fixture.
    for i, stamp in enumerate(result):
        vec = stamp.vector_map()
        if actor in ("A", "C"):
            expect = {"A": i + 1 if actor == "A" else 0,
                      "B": 0,
                      "C": i + 1 if actor == "C" else 0}
            if vec != expect:
                raise EvidenceError("independent actor vector mismatch")
    return result


def verify(a: dict, c: dict, b: dict, registration: dict,
           *, controlled_exclusion_assured: bool = False) -> dict:
    result = infer(a, c, b, registration["key_hex"], registration["key_id"],
                   controlled_exclusion_assured=controlled_exclusion_assured)
    a_stamps = _stamps(a["records"], "A")
    c_stamps = _stamps(c["records"], "C")
    b_stamps = _stamps(b["records"], "B")
    # A and C are not allowed to smuggle artificial cross-actor dependency.
    if a_stamps[-1].relation(c_stamps[-1]) != CausalRelation.CONCURRENT:
        raise EvidenceError("source and witness not independently concurrent")
    if (a_stamps[-1].relation(b_stamps[0]) != CausalRelation.BEFORE
            or c_stamps[-1].relation(b_stamps[0]) != CausalRelation.BEFORE):
        raise EvidenceError("receiver lacks both causal handoffs")
    for k, frame in enumerate(b_stamps):
        vec = frame.vector_map()
        if vec.get("A") != 3 or vec.get("C") != 3 or vec.get("B") != k + 3:
            raise EvidenceError("receiver vector does not bind exact dual handoff")
    return {"experiment": "RE-005",
            "causal_relation": {"A2_C2": "concurrent", "A2_B0": "before", "C2_B0": "before", "B0_B1": "before", "B1_B2": "before"},
            "identification": result,
            "hosted_runtime": "real E-CPU TemporalContext/CausalStamp",
            "independent_public_verifier": True,
            "witness_authentication": "HMAC under workflow-issued ephemeral shared key",
            "physical_identity_attested": False,
            "physical_causation_proved": False,
            "combined_cross_host_elapsed": None}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("use --enroll|--source|--witness|--receiver|--verify")
    op = sys.argv[1]
    payload = {} if op in ("--enroll", "--source") else json.load(sys.stdin)
    if op == "--enroll":
        result = enroll()
    elif op == "--source":
        result = source()
    elif op == "--witness":
        result = witness(payload["enrollment"], permitted=payload.get("permitted", True))
    elif op == "--receiver":
        result = receiver(payload["source"], payload["witness"], truth=payload.get("truth", "common_cause_marker"))
    elif op == "--verify":
        result = verify(payload["source"], payload["witness"], payload["receiver"],
                        payload["enrollment"], controlled_exclusion_assured=payload.get("controlled_exclusion_assured", False))
    else:
        raise SystemExit("unknown operation")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
