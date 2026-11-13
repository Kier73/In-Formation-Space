#!/usr/bin/env python3
"""Decision-time evidence frontier reconstruction (DFR-001).

This finite reference model distinguishes source send order, receiver
admission order, a decision's declared evidence snapshot, and the evidence
a controller declares it used. It does not authenticate actors or prove
that an admitted value affected the decision computation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "in-formation.decision-time-evidence-frontier/0.1"
GENESIS = hashlib.sha256(b"in-formation.decision-time-evidence-frontier/0.1:genesis").hexdigest()


class FrontierError(ValueError):
    """Malformed, inconsistent, or tampered decision-time evidence."""


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise FrontierError(f"value is not finite canonical JSON: {error}") from error


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def seal_event(core: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(core)
    return {**body, "event_digest": digest(body)}


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FrontierError(f"{label} must be an integer >= {minimum}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FrontierError(f"{label} must be non-empty text")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise FrontierError(f"{label} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise FrontierError(f"{label} contains duplicates")
    if value != sorted(value):
        raise FrontierError(f"{label} must be sorted for canonical comparison")
    return list(value)


def validate_stamp(raw: object, label: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != {"actor_id", "lamport", "vector"}:
        raise FrontierError(f"{label} has invalid causal-stamp fields")
    actor = _text(raw["actor_id"], f"{label}.actor_id")
    lamport = _integer(raw["lamport"], f"{label}.lamport", 1)
    vector = raw["vector"]
    if not isinstance(vector, Mapping) or not vector:
        raise FrontierError(f"{label}.vector must be a non-empty object")
    normalized: dict[str, int] = {}
    for key, value in vector.items():
        name = _text(key, f"{label}.vector actor")
        counter = _integer(value, f"{label}.vector[{name}]")
        if counter > lamport:
            raise FrontierError(f"{label} vector counter exceeds Lamport value")
        normalized[name] = counter
    if actor not in normalized or normalized[actor] < 1:
        raise FrontierError(f"{label}.vector must contain a positive own-actor counter")
    return {"actor_id": actor, "lamport": lamport, "vector": normalized}


def relation(left: Mapping[str, Any], right: Mapping[str, Any]) -> str:
    """Vector-clock relation; absent actors have counter zero."""
    a = left["vector"]
    b = right["vector"]
    actors = set(a) | set(b)
    less = any(a.get(actor, 0) < b.get(actor, 0) for actor in actors)
    greater = any(a.get(actor, 0) > b.get(actor, 0) for actor in actors)
    if less and greater:
        return "concurrent"
    if less:
        return "before"
    if greater:
        return "after"
    return "equal"


def _validate_sealed_event(raw: object, label: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise FrontierError(f"{label} must be an object")
    event = dict(raw)
    claimed = event.get("event_digest")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise FrontierError(f"{label} has no SHA-256 event digest")
    core = {key: value for key, value in event.items() if key != "event_digest"}
    if digest(core) != claimed:
        raise FrontierError(f"{label} digest does not match its exact contents")
    _integer(event.get("event_seq"), f"{label}.event_seq", 1)
    _text(event.get("previous_digest"), f"{label}.previous_digest")
    return event


def validate_source_log(raw_events: object, source_actor: str) -> list[dict[str, Any]]:
    if not isinstance(raw_events, list) or not raw_events:
        raise FrontierError("source_events must be a non-empty list")
    expected_fields = {
        "event_seq", "kind", "previous_digest", "message_id",
        "measurement_sequence", "measurement_epoch", "payload",
        "payload_digest", "causal_stamp", "event_digest",
    }
    events: list[dict[str, Any]] = []
    previous = GENESIS
    prior_measurement = 0
    prior_stamp: dict[str, Any] | None = None
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_events, start=1):
        event = _validate_sealed_event(raw, f"source event {index}")
        if set(event) != expected_fields:
            raise FrontierError(f"source event {index} has missing or unexpected fields")
        if event["event_seq"] != index or event["previous_digest"] != previous:
            raise FrontierError("source log must be a contiguous hash chain from genesis")
        if event["kind"] != "send":
            raise FrontierError("source log contains a non-send event")
        message_id = _text(event["message_id"], "message_id")
        if message_id in seen_ids:
            raise FrontierError("source log contains a duplicate message ID")
        seen_ids.add(message_id)
        measurement = _integer(event["measurement_sequence"], "measurement_sequence", 1)
        if measurement <= prior_measurement:
            raise FrontierError("measurement sequence must increase with source send order")
        prior_measurement = measurement
        _integer(event["measurement_epoch"], "measurement_epoch")
        if digest(event["payload"]) != event["payload_digest"]:
            raise FrontierError(f"source payload digest mismatch for {message_id}")
        stamp = validate_stamp(event["causal_stamp"], f"source {message_id} stamp")
        if stamp["actor_id"] != source_actor:
            raise FrontierError("source causal stamp belongs to another actor")
        if prior_stamp is not None and relation(prior_stamp, stamp) != "before":
            raise FrontierError("source-local sends must be strictly causally ordered")
        if stamp["vector"].get(source_actor, 0) != index:
            raise FrontierError("source-local own-actor counter must match send sequence")
        events.append(event)
        previous = event["event_digest"]
        prior_stamp = stamp
    return events


def _prefix_complete(events_by_seq: Mapping[int, Mapping[str, Any]], end_seq: int) -> bool:
    if end_seq == 0:
        return True
    expected_previous = GENESIS
    for seq in range(1, end_seq + 1):
        event = events_by_seq.get(seq)
        if event is None:
            return False
        if event["previous_digest"] != expected_previous:
            raise FrontierError(f"receiver hash-chain mismatch at contiguous event {seq}")
        expected_previous = event["event_digest"]
    return True


def validate_receiver_log(
    raw_events: object,
    *,
    source_events: Sequence[Mapping[str, Any]],
    receiver_actor: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_events, list) or not raw_events:
        raise FrontierError("receiver_events must be a non-empty list")
    source_by_id = {event["message_id"]: event for event in source_events}
    events: list[dict[str, Any]] = []
    by_seq: dict[int, dict[str, Any]] = {}
    by_message: dict[str, dict[str, Any]] = {}
    prior_seq = 0
    expected_common = {"event_seq", "kind", "previous_digest", "causal_stamp", "event_digest"}

    for index, raw in enumerate(raw_events, start=1):
        event = _validate_sealed_event(raw, f"receiver event {index}")
        seq = event["event_seq"]
        if seq <= prior_seq:
            raise FrontierError("receiver events must be ordered by unique increasing event_seq")
        prior_seq = seq
        if seq in by_seq:
            raise FrontierError("receiver event sequence is duplicated")
        kind = event.get("kind")
        if kind == "intake":
            expected = expected_common | {
                "message_id", "source_event_digest", "payload_digest", "source_causal_stamp",
            }
        elif kind == "decision":
            expected = expected_common | {
                "decision_id", "frontier_event_seq", "frontier_head_digest",
                "available_message_ids", "used_message_ids",
            }
        else:
            raise FrontierError(f"unsupported receiver event kind {kind!r}")
        if set(event) != expected:
            raise FrontierError(f"receiver event {seq} has missing or unexpected fields")

        stamp = validate_stamp(event["causal_stamp"], f"receiver event {seq} stamp")
        if stamp["actor_id"] != receiver_actor:
            raise FrontierError("receiver causal stamp belongs to another actor")

        if kind == "intake":
            message_id = _text(event["message_id"], "intake.message_id")
            if message_id not in source_by_id:
                raise FrontierError(f"intake references unknown message {message_id}")
            if message_id in by_message:
                raise FrontierError(f"duplicate receiver intake for {message_id}")
            source = source_by_id[message_id]
            source_stamp = validate_stamp(source["causal_stamp"], f"{message_id} source stamp")
            received_source_stamp = validate_stamp(
                event["source_causal_stamp"], f"{message_id} received source stamp"
            )
            if event["source_event_digest"] != source["event_digest"]:
                raise FrontierError(f"intake does not bind exact source event for {message_id}")
            if event["payload_digest"] != source["payload_digest"]:
                raise FrontierError(f"intake payload digest differs for {message_id}")
            if received_source_stamp != source_stamp:
                raise FrontierError(f"intake causal stamp differs from source record for {message_id}")
            if relation(received_source_stamp, stamp) != "before":
                raise FrontierError(f"receiver did not causally merge source message {message_id}")
            by_message[message_id] = event
        else:
            _text(event["decision_id"], "decision_id")
            frontier = _integer(event["frontier_event_seq"], "frontier_event_seq")
            if frontier != seq - 1:
                raise FrontierError("decision frontier must name exactly the preceding receiver event")
            _text(event["frontier_head_digest"], "frontier_head_digest")
            if event["frontier_head_digest"] != event["previous_digest"]:
                raise FrontierError("decision frontier head must equal its immediate predecessor digest")
            available = _string_list(event["available_message_ids"], "available_message_ids")
            used = _string_list(event["used_message_ids"], "used_message_ids")
            if not set(used).issubset(available):
                raise FrontierError("decision uses a message it does not declare available")

        by_seq[seq] = event
        events.append(event)

    # Validate every adjacent link we can actually see. A missing sequence is
    # incomplete evidence, not proof of concurrency and not automatically tampering.
    for left, right in zip(events, events[1:]):
        if right["event_seq"] == left["event_seq"] + 1:
            if right["previous_digest"] != left["event_digest"]:
                raise FrontierError(
                    f"receiver hash-chain mismatch between events {left['event_seq']} and {right['event_seq']}"
                )
            left_stamp = validate_stamp(left["causal_stamp"], "prior receiver stamp")
            right_stamp = validate_stamp(right["causal_stamp"], "next receiver stamp")
            if relation(left_stamp, right_stamp) != "before":
                raise FrontierError("contiguous receiver-local events must be strictly causally ordered")
            if right_stamp["vector"].get(receiver_actor, 0) != left_stamp["vector"].get(receiver_actor, 0) + 1:
                raise FrontierError("receiver-local own-actor counter must advance once per contiguous event")

    if events[0]["event_seq"] == 1 and events[0]["previous_digest"] != GENESIS:
        raise FrontierError("receiver genesis link is invalid")
    return events


def build_fixture(*, omit_receiver_event: int | None = None) -> dict[str, Any]:
    """Build two source sends, receive message 2 first, decide, then receive 1."""
    source_actor = "host-A"
    receiver_actor = "host-B"

    def source_stamp(counter: int) -> dict[str, Any]:
        return {"actor_id": source_actor, "lamport": counter, "vector": {source_actor: counter}}

    def receiver_stamp(lamport: int, source_counter: int, receiver_counter: int) -> dict[str, Any]:
        return {
            "actor_id": receiver_actor,
            "lamport": lamport,
            "vector": {source_actor: source_counter, receiver_actor: receiver_counter},
        }

    source_events: list[dict[str, Any]] = []
    previous = GENESIS
    for seq, message_id, measurement_epoch, signal in (
        (1, "m1", 0, "older-sample"),
        (2, "m2", 1, "newer-sample"),
    ):
        payload = {"signal": signal}
        event = seal_event({
            "event_seq": seq,
            "kind": "send",
            "previous_digest": previous,
            "message_id": message_id,
            "measurement_sequence": seq,
            "measurement_epoch": measurement_epoch,
            "payload": payload,
            "payload_digest": digest(payload),
            "causal_stamp": source_stamp(seq),
        })
        source_events.append(event)
        previous = event["event_digest"]

    source_by_id = {event["message_id"]: event for event in source_events}
    receiver_events: list[dict[str, Any]] = []
    previous = GENESIS

    m2 = source_by_id["m2"]
    intake_m2 = seal_event({
        "event_seq": 1,
        "kind": "intake",
        "previous_digest": previous,
        "message_id": "m2",
        "source_event_digest": m2["event_digest"],
        "payload_digest": m2["payload_digest"],
        "source_causal_stamp": m2["causal_stamp"],
        "causal_stamp": receiver_stamp(3, 2, 1),
    })
    receiver_events.append(intake_m2)
    previous = intake_m2["event_digest"]

    decision_1 = seal_event({
        "event_seq": 2,
        "kind": "decision",
        "previous_digest": previous,
        "decision_id": "D1",
        "frontier_event_seq": 1,
        "frontier_head_digest": previous,
        "available_message_ids": ["m2"],
        "used_message_ids": ["m2"],
        "causal_stamp": receiver_stamp(4, 2, 2),
    })
    receiver_events.append(decision_1)
    previous = decision_1["event_digest"]

    m1 = source_by_id["m1"]
    intake_m1 = seal_event({
        "event_seq": 3,
        "kind": "intake",
        "previous_digest": previous,
        "message_id": "m1",
        "source_event_digest": m1["event_digest"],
        "payload_digest": m1["payload_digest"],
        "source_causal_stamp": m1["causal_stamp"],
        "causal_stamp": receiver_stamp(5, 2, 3),
    })
    receiver_events.append(intake_m1)
    previous = intake_m1["event_digest"]

    decision_2 = seal_event({
        "event_seq": 4,
        "kind": "decision",
        "previous_digest": previous,
        "decision_id": "D2",
        "frontier_event_seq": 3,
        "frontier_head_digest": previous,
        "available_message_ids": ["m1", "m2"],
        "used_message_ids": ["m2"],
        "causal_stamp": receiver_stamp(6, 2, 4),
    })
    receiver_events.append(decision_2)

    if omit_receiver_event is not None:
        receiver_events = [
            event for event in receiver_events if event["event_seq"] != omit_receiver_event
        ]
    return {
        "source_actor": source_actor,
        "receiver_actor": receiver_actor,
        "source_events": source_events,
        "receiver_events": receiver_events,
    }


def build_report(bundle: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, Mapping) or set(bundle) != {
        "source_actor", "receiver_actor", "source_events", "receiver_events",
    }:
        raise FrontierError("bundle fields are incomplete or unexpected")
    source_actor = _text(bundle["source_actor"], "source_actor")
    receiver_actor = _text(bundle["receiver_actor"], "receiver_actor")
    if source_actor == receiver_actor:
        raise FrontierError("source and receiver must be distinct actors")
    source_events = validate_source_log(bundle["source_events"], source_actor)
    receiver_events = validate_receiver_log(
        bundle["receiver_events"],
        source_events=source_events,
        receiver_actor=receiver_actor,
    )

    receiver_by_seq = {event["event_seq"]: event for event in receiver_events}
    receiver_by_message = {
        event["message_id"]: event for event in receiver_events if event["kind"] == "intake"
    }
    assessments: list[dict[str, Any]] = []

    for decision in (event for event in receiver_events if event["kind"] == "decision"):
        decision_stamp = validate_stamp(decision["causal_stamp"], "decision causal stamp")
        frontier_seq = decision["frontier_event_seq"]
        complete = _prefix_complete(receiver_by_seq, frontier_seq)
        prefix_intakes = [
            event for event in receiver_events
            if event["kind"] == "intake" and event["event_seq"] <= frontier_seq
        ]
        reconstructed = sorted(event["message_id"] for event in prefix_intakes) if complete else None
        declared_available = list(decision["available_message_ids"])
        declared_used = list(decision["used_message_ids"])
        if complete and reconstructed != declared_available:
            raise FrontierError(
                f"{decision['decision_id']} declared available set differs from its complete receiver prefix"
            )

        message_assessments: list[dict[str, Any]] = []
        for source in source_events:
            source_stamp = validate_stamp(source["causal_stamp"], "source causal stamp")
            send_relation = relation(source_stamp, decision_stamp)
            intake = receiver_by_message.get(source["message_id"])
            receipt_relation = None
            receipt_seq = None
            if intake is not None:
                intake_stamp = validate_stamp(intake["causal_stamp"], "intake causal stamp")
                receipt_relation = relation(decision_stamp, intake_stamp)
                receipt_seq = intake["event_seq"]

            if not complete:
                availability = "unknown_incomplete_log"
            elif intake is not None and receipt_seq <= frontier_seq:
                availability = "available_at_decision"
            elif intake is not None and receipt_seq > frontier_seq:
                if _prefix_complete(receiver_by_seq, receipt_seq):
                    availability = "arrived_after_decision"
                else:
                    availability = "unknown_incomplete_log"
            else:
                availability = "not_recorded_as_admitted_at_snapshot"

            message_assessments.append({
                "message_id": source["message_id"],
                "measurement_sequence": source["measurement_sequence"],
                "source_send_to_decision": send_relation,
                "decision_to_receiver_intake": receipt_relation,
                "receiver_intake_event_seq": receipt_seq,
                "availability": availability,
                "controller_declared_used": source["message_id"] in declared_used,
            })

        assessments.append({
            "decision_id": decision["decision_id"],
            "event_seq": decision["event_seq"],
            "frontier_event_seq": frontier_seq,
            "frontier_head_digest": decision["frontier_head_digest"],
            "frontier_status": "complete" if complete else "unknown_incomplete_log",
            "declared_available_message_ids": declared_available,
            "reconstructed_available_message_ids": reconstructed,
            "controller_declared_used_message_ids": declared_used,
            "messages": message_assessments,
        })

    core = {
        "schema": SCHEMA,
        "source_actor": source_actor,
        "receiver_actor": receiver_actor,
        "source_events": copy.deepcopy(source_events),
        "receiver_events": copy.deepcopy(receiver_events),
        "decision_assessments": assessments,
        "clock_policy": {
            "wall_clock_used": False,
            "global_total_order": None,
            "combined_cross_host_elapsed_ns": None,
        },
        "interpretation": (
            "Availability is reconstructed from a complete receiver-log prefix. "
            "Causal precedence of a source send does not by itself establish receiver admission. "
            "Controller-declared use is retained as a claim, not proof of computational use."
        ),
    }
    return {**core, "report_digest": digest(core)}


def validate_report(report: object) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise FrontierError("report must be an object")
    required = {
        "schema", "source_actor", "receiver_actor", "source_events",
        "receiver_events", "decision_assessments", "clock_policy",
        "interpretation", "report_digest",
    }
    if set(report) != required or report.get("schema") != SCHEMA:
        raise FrontierError("report fields or schema identifier are invalid")
    core = {key: value for key, value in report.items() if key != "report_digest"}
    if report["report_digest"] != digest(core):
        raise FrontierError("report digest does not match its contents")
    rebuilt = build_report({
        "source_actor": report["source_actor"],
        "receiver_actor": report["receiver_actor"],
        "source_events": report["source_events"],
        "receiver_events": report["receiver_events"],
    })
    if rebuilt != dict(report):
        raise FrontierError("report differs from independent reconstruction from retained event logs")
    return rebuilt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drop-receiver-event", type=int, default=None,
                        help="omit one receiver event to demonstrate an unknown decision frontier")
    parser.add_argument("--compact", action="store_true", help="print compact JSON")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    bundle = build_fixture(omit_receiver_event=args.drop_receiver_event)
    report = build_report(bundle)
    validate_report(report)
    encoded = json.dumps(
        report, sort_keys=True,
        separators=(",", ":") if args.compact else None,
        ensure_ascii=False, allow_nan=False,
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
