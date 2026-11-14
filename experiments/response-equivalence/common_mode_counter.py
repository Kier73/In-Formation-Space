"""RE-009: source-counter discrepancy, not proof of common-mode physical loss.

Extends RE-008's independently sealed observer logs. A role-enrolled synthetic
source claims cumulative event counts at boundaries 0/4/8. Its signed counter
is another report, never an oracle for physical events. The verifier reports
both the count disagreement and the premises required to interpret it.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
from typing import Any, Mapping, Sequence

from coverage_reconstruction import (
    ACTORS, EPOCHS, CoverageError, _admit_deliveries, _base, _key,
    _sign, _verify, delayed_delivery, enrollment, produce_log,
    reconstruct as reconstruct_coverage, sha, verify_log,
)

SCHEMA = "in-formation.response-re009-source/0.1"
BOUNDS = (0, 4, 8)
SOURCE_FIELDS = frozenset(("schema", "kind", "challenge", "actor", "key_id",
                           "boundary", "cumulative", "parent", "controller_digest"))
ACK_FIELDS = frozenset(("schema", "kind", "challenge", "actor", "key_id",
                        "source_head", "observer_seal", "capture_count"))


class CounterError(CoverageError):
    """Invalid source claim, observer acknowledgement, or count comparison."""


def register(*, deterministic: bool = False) -> dict[str, Any]:
    reg = enrollment(deterministic=deterministic)
    reg["keys"]["S"] = ("ef" * 32 if deterministic else secrets.token_hex(32))
    reg["key_ids"]["S"] = hashlib.sha256(bytes.fromhex(reg["keys"]["S"])).hexdigest()
    return reg


def _source_key(reg: Mapping[str, Any]) -> bytes:
    try:
        value = reg["keys"]["S"]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("invalid key length")
        result = bytes.fromhex(value)
        if hashlib.sha256(result).hexdigest() != reg["key_ids"]["S"]:
            raise ValueError("key identity mismatch")
    except (TypeError, ValueError, KeyError) as exc:
        raise CounterError("source enrollment key invalid") from exc
    return result


def _source_body(reg: Mapping[str, Any], boundary: int, cumulative: int,
                 parent: str | None, controller_digest: str | None) -> dict[str, Any]:
    return {"schema": SCHEMA, "kind": "counter", "challenge": reg["challenge"],
            "actor": "S", "key_id": reg["key_ids"]["S"],
            "boundary": boundary, "cumulative": cumulative, "parent": parent,
            "controller_digest": controller_digest}


def produce_source(reg: Mapping[str, Any], counts: Sequence[int] = (0, 2, 4),
                   *, controller_digest: str | None = None) -> dict[str, Any]:
    if not isinstance(counts, (tuple, list)) or len(counts) != len(BOUNDS) or any(
        type(c) is not int or c < 0 for c in counts
    ) or counts[0] != 0 or any(
        not (0 <= b - a <= end - start) for a, b, start, end in
        zip(counts, counts[1:], BOUNDS, BOUNDS[1:])
    ):
        raise CounterError("source counts violate declared one-event-per-epoch fixture")
    if controller_digest is not None and (not isinstance(controller_digest, str) or
                                          len(controller_digest) != 64):
        raise CounterError("controller digest malformed")
    key = _source_key(reg)
    parent = None
    receipts = []
    for boundary, count in zip(BOUNDS, counts):
        item = _sign(_source_body(reg, boundary, count, parent, controller_digest), key)
        receipts.append(item)
        parent = item["digest"]
    return {"receipts": receipts, "head": parent,
            "controller_digest": controller_digest}


def verify_source(source: Mapping[str, Any], reg: Mapping[str, Any],
                  *, controller_digest: str | None = None) -> tuple[int, ...]:
    if not isinstance(source, dict) or set(source) != {"receipts", "head", "controller_digest"}:
        raise CounterError("source log envelope malformed")
    if source["controller_digest"] != controller_digest:
        raise CounterError("source counter not bound to declared controller")
    receipts = source["receipts"]
    if not isinstance(receipts, list) or len(receipts) != len(BOUNDS):
        raise CounterError("source boundary receipt missing or duplicated")
    previous = None
    counts: list[int] = []
    for expected_boundary, item in zip(BOUNDS, receipts):
        if not isinstance(item, dict) or set(item) != SOURCE_FIELDS | {"mac", "digest"}:
            raise CounterError("source receipt malformed")
        if any((item.get(field) != val) for field, val in (("schema", SCHEMA),
                ("kind", "counter"), ("challenge", reg.get("challenge")),
                ("actor", "S"), ("key_id", reg.get("key_ids", {}).get("S")),
                ("boundary", expected_boundary), ("parent", previous),
                ("controller_digest", controller_digest))):
            raise CounterError("source boundary identity or chain mismatch")
        body = {k: v for k, v in item.items() if k not in ("mac", "digest")}
        mac = hmac.new(_source_key(reg), json.dumps(body, sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False).encode("utf-8"), hashlib.sha256).hexdigest()
        if not isinstance(item.get("mac"), str) or not hmac.compare_digest(item["mac"], mac):
            raise CounterError("source HMAC invalid")
        if item["digest"] != sha({**body, "mac": item["mac"]}):
            raise CounterError("source digest invalid")
        count = item["cumulative"]
        if type(count) is not int or count < 0:
            raise CounterError("source count invalid")
        counts.append(count)
        previous = item["digest"]
    if source["head"] != previous or counts[0] != 0 or any(
        not (0 <= b - a <= end - start) for a, b, start, end in
        zip(counts, counts[1:], BOUNDS, BOUNDS[1:])
    ):
        raise CounterError("source claimed counter range invalid")
    return tuple(counts)


def acknowledge(actor: str, log: Mapping[str, Any], source: Mapping[str, Any],
                reg: Mapping[str, Any]) -> dict[str, Any]:
    if actor not in ACTORS:
        raise CounterError("unknown acknowledging observer")
    # The observer acknowledges exact source bytes. It does not possess S's key:
    # source authentication is performed later by the independent verifier.
    if (not isinstance(source, Mapping) or not isinstance(source.get("head"), str) or len(source["head"]) != 64 or
        not isinstance(source.get("receipts"), list) or len(source["receipts"]) != len(BOUNDS) or
        any(not isinstance(x, Mapping) or x.get("challenge") != reg["challenge"] for x in source["receipts"])):
        raise CounterError("invalid source for acknowledgement")
    vr = verify_log(actor, log, reg)
    if vr["status"] != "complete":
        raise CounterError("cannot acknowledge incomplete sealed log")
    return _sign({**_base(reg, actor, "ack"),
                  "source_head": source["head"],
                  "observer_seal": log["seal"]["digest"],
                  "capture_count": len(EPOCHS)}, _key(reg, actor))


def verify_acknowledgements(logs: Mapping[str, Any], source: Mapping[str, Any],
                            acknowledgements: Mapping[str, Any], reg: Mapping[str, Any]) -> None:
    if not isinstance(acknowledgements, Mapping) or set(acknowledgements) != set(ACTORS):
        raise CounterError("missing independent observer acknowledgement")
    for actor in ACTORS:
        rec = acknowledgements[actor]
        _verify(rec, reg, actor, "ack", ACK_FIELDS)
        if (rec["source_head"] != source["head"] or
            rec["observer_seal"] != logs[actor]["seal"]["digest"] or
            type(rec["capture_count"]) is not int or rec["capture_count"] != len(EPOCHS)):
            raise CounterError("observer acknowledgement detached from source or seal")


def reconstruct(source: Mapping[str, Any], logs: Mapping[str, Any],
                acknowledgements: Mapping[str, Any], reg: Mapping[str, Any],
                deliveries: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Source-vs-observer disagreement is evidence of disagreement, not causation.

    No count is emitted for a corrupt/incomplete archive or conflicting readouts.
    An agreed count does not establish that source and observers saw everything.
    """
    counts = verify_source(source, reg)
    if not isinstance(logs, Mapping) or set(logs) != set(ACTORS):
        raise CounterError("both observer logs required")
    verified = {a: verify_log(a, logs[a], reg) for a in ACTORS}
    if any(x["status"] != "complete" for x in verified.values()):
        return {"schema": SCHEMA, "status": "unresolved_archive_continuity",
                "source_claimed_total": counts[-1], "observed_total": None,
                "source_observer_discrepancy": None, "windows": None,
                "missing_archived_records": {a: verified[a]["missing"] for a in ACTORS},
                **_limits()}
    verify_acknowledgements(logs, source, acknowledgements, reg)
    coverage = reconstruct_coverage(logs, reg, deliveries)
    if coverage["status"] == "conflicted":
        return {"schema": SCHEMA, "status": "unresolved_conflicting_observers",
                "source_claimed_total": counts[-1], "observed_total": None,
                "source_observer_discrepancy": None, "windows": None,
                "conflict_epochs": coverage["conflict_epochs"], **_limits()}
    effective = _admit_deliveries(logs, verified, reg, deliveries)
    observed: dict[int, str] = {}
    for epoch in EPOCHS:
        readings = [effective.get((actor, epoch), (
                     verified[actor]["records"][epoch]["outcome"],
                     verified[actor]["records"][epoch]["event"])) for actor in ACTORS]
        present = [fingerprint for status, fingerprint in readings if status == "present"]
        if present:
            if len(set(present)) != 1:
                raise CounterError("conflicting event fingerprints")
            observed[epoch] = present[0]
    if len(set(observed.values())) != len(observed):
        raise CounterError("same event fingerprint reused across capture epochs")
    windows = []
    for start, end, before, after in zip(BOUNDS, BOUNDS[1:], counts, counts[1:]):
        seen = sum(start <= epoch < end for epoch in observed)
        asserted = after - before
        windows.append({"start": start, "end_exclusive": end,
                        "source_claimed_events": asserted,
                        "observer_reported_distinct_events": seen,
                        "source_minus_observers": asserted - seen})
    discrepancy = counts[-1] - len(observed)
    return {"schema": SCHEMA,
            "status": "source_observer_disagreement" if discrepancy or any(
                w["source_minus_observers"] for w in windows) else "source_observer_counts_agree",
            "source_claimed_total": counts[-1], "observed_total": len(observed),
            "source_observer_discrepancy": discrepancy,
            "windows": windows, "observed_epochs": sorted(observed),
            "observer_blind_declared_epochs": coverage["blind_epochs"],
            "verified_observer_acknowledgements": list(ACTORS),
            **_limits()}


def _limits() -> dict[str, Any]:
    return {"source_truthfulness_proved": False,
            "physical_common_mode_loss_proved": False,
            "physical_event_completeness_proved": False,
            "causation_proved": False,
            "cross_host_elapsed": None}


def choose_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    if result["status"] == "unresolved_archive_continuity":
        return {"action": "retrieve_signed_archived_observer_slot", "outcome": "planned_only"}
    if result["status"] == "unresolved_conflicting_observers":
        return {"action": "investigate_observer_conflict", "outcome": "planned_only"}
    if result["status"] == "source_observer_disagreement":
        return {"action": "request_independent_event_origin_evidence",
                "target_window": next((([w["start"], w["end_exclusive"]])
                  for w in result["windows"] if w["source_minus_observers"]), None),
                "outcome": "planned_only_not_historical_measurement"}
    return {"action": "retain_scoped_agreement_only", "outcome": "planned_only"}


def fixture(*, counts: Sequence[int] = (0, 2, 4),
            delayed: bool = True) -> tuple[dict[str, Any], dict[str, Any],
                                            dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    reg = register(deterministic=True)
    source = produce_source(reg, counts)
    logs = {"A": produce_log("A", reg, {2: "dropout", 5: "dropout", 6: "pending"}),
            "B": produce_log("B", reg, {1: "dropout", 4: "dropout"})}
    ack = {a: acknowledge(a, logs[a], source, reg) for a in ACTORS}
    late = [delayed_delivery("A", reg, logs["A"]["records"][6])] if delayed else []
    return source, logs, ack, reg, late


def demonstration() -> dict[str, Any]:
    source, logs, ack, reg, late = fixture()
    claimed_loss = reconstruct(source, logs, ack, reg, late)
    false_counter = produce_source(reg, (0, 1, 3))
    false_ack = {a: acknowledge(a, logs[a], false_counter, reg) for a in ACTORS}
    matching = reconstruct(false_counter, logs, false_ack, reg, late)
    return {"experiment": "RE-009", "source_counter_excess": claimed_loss,
            "source_counter_matches_observers": matching,
            "proposal": choose_audit(claimed_loss),
            "indistinguishable_latent_worlds": [
                "event-at-epoch-3-both-observers-miss-it",
                "no-event-at-epoch-3-source-counter-overstates-events"],
            "physical_truth_selected_from_public_records": False}


if __name__ == "__main__":
    print(json.dumps(demonstration(), indent=2, sort_keys=True))
