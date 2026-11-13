"""RE-008: signed observer log coverage, repair and observer-relative blind slots.

Synthetic finite epoch fixture. HMAC binds bytes to CI-enrolled keys, not to a
physical sensor. An attested epoch range is NOT proof of complete physical time
or detection of every external event. Reconstruct only declared-epoch coverage.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Mapping, Sequence

SCHEMA = "in-formation.response-re008/0.1"
ACTORS = ("A", "B")
EPOCHS = tuple(range(8))
EVENTS = {1: "p", 4: "q", 6: "r"}
OUTCOMES = frozenset(("present", "absent", "dropout", "pending"))


class CoverageError(ValueError):
    """Evidence is malformed, unauthenticated, or contradictory."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def enrollment(*, deterministic: bool = False) -> dict[str, Any]:
    keys = ({a: ("ab" if a == "A" else "cd") * 32 for a in ACTORS}
            if deterministic else {a: secrets.token_hex(32) for a in ACTORS})
    return {"challenge": "re008-test-challenge-012345" if deterministic else secrets.token_hex(24),
            "keys": keys, "key_ids": {a: hashlib.sha256(bytes.fromhex(keys[a])).hexdigest()
                                   for a in ACTORS}}


def _key(reg: Mapping[str, Any], actor: str) -> bytes:
    if actor not in ACTORS or not isinstance(reg, Mapping):
        raise CoverageError("unknown signing actor")
    try:
        key = bytes.fromhex(reg["keys"][actor]); keyid = reg["key_ids"][actor]
    except (KeyError, TypeError, ValueError) as exc:
        raise CoverageError("missing signing key") from exc
    if len(key) != 32 or hashlib.sha256(key).hexdigest() != keyid:
        raise CoverageError("enrollment key mismatch")
    return key


def _sign(payload: dict[str, Any], key: bytes) -> dict[str, Any]:
    mac = hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()
    body = {**payload, "mac": mac}
    return {**body, "digest": sha(body)}


def _verify(item: Mapping[str, Any], reg: Mapping[str, Any], actor: str, kind: str,
            fields: frozenset[str]) -> None:
    if not isinstance(item, dict) or set(item) != fields | {"mac", "digest"}:
        raise CoverageError("invalid signed record fields")
    if item.get("schema") != SCHEMA or item.get("challenge") != reg.get("challenge") or \
       item.get("actor") != actor or item.get("kind") != kind or \
       item.get("key_id") != reg.get("key_ids", {}).get(actor):
        raise CoverageError("record identity/enrollment mismatch")
    body = {k: v for k, v in item.items() if k not in ("mac", "digest")}
    expected = hmac.new(_key(reg, actor), canonical(body), hashlib.sha256).hexdigest()
    if not isinstance(item["mac"], str) or not hmac.compare_digest(item["mac"], expected):
        raise CoverageError("role HMAC invalid")
    if item["digest"] != sha({**body, "mac": item["mac"]}):
        raise CoverageError("record digest invalid")


SLOT_FIELDS = frozenset(("schema", "kind", "challenge", "actor", "key_id",
                         "epoch", "outcome", "event", "parent"))
SEAL_FIELDS = frozenset(("schema", "kind", "challenge", "actor", "key_id",
                         "start", "end", "count", "head"))
DELIVERY_FIELDS = frozenset(("schema", "kind", "challenge", "actor", "key_id",
                             "capture_epoch", "capture_digest", "delivery_tick",
                             "outcome", "event"))


def _base(reg: Mapping[str, Any], actor: str, kind: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "kind": kind, "challenge": reg["challenge"],
            "actor": actor, "key_id": reg["key_ids"][actor]}


def _event(epoch: int, outcome: str) -> str | None:
    if outcome == "present":
        if epoch not in EVENTS:
            raise CoverageError("no declared synthetic event in epoch")
        return sha({"epoch": epoch, "mark": EVENTS[epoch]})
    return None


def produce_log(actor: str, reg: Mapping[str, Any],
                overrides: Mapping[int, str] | None = None) -> dict[str, Any]:
    """Create a sealed, append-only synthetic log; producer keeps full archive."""
    key = _key(reg, actor)
    overrides = overrides or {}
    if any(type(epoch) is not int or epoch not in EPOCHS or status not in OUTCOMES
           for epoch, status in overrides.items()):
        raise CoverageError("invalid planned outcome")
    parent = None
    records = []
    for epoch in EPOCHS:
        outcome = overrides.get(epoch, "present" if epoch in EVENTS else "absent")
        item = _sign({**_base(reg, actor, "slot"), "epoch": epoch,
                      "outcome": outcome, "event": _event(epoch, outcome),
                      "parent": parent}, key)
        records.append(item)
        parent = item["digest"]
    seal = _sign({**_base(reg, actor, "seal"), "start": EPOCHS[0],
                  "end": EPOCHS[-1], "count": len(EPOCHS), "head": parent}, key)
    return {"records": records, "seal": seal}


def delayed_delivery(actor: str, reg: Mapping[str, Any], pending: Mapping[str, Any],
                     *, delivery_tick: int = 99) -> dict[str, Any]:
    if pending.get("outcome") != "pending" or pending.get("actor") != actor:
        raise CoverageError("delivery does not refer to pending slot")
    epoch = pending["epoch"]
    if type(delivery_tick) is not int or delivery_tick <= epoch:
        raise CoverageError("delivery must follow captured logical slot")
    final = "present" if epoch in EVENTS else "absent"
    return _sign({**_base(reg, actor, "delivery"), "capture_epoch": epoch,
                  "capture_digest": pending["digest"], "delivery_tick": delivery_tick,
                  "outcome": final, "event": _event(epoch, final)}, _key(reg, actor))


def verify_log(actor: str, log: Mapping[str, Any], reg: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(log, Mapping) or set(log) != {"records", "seal"}:
        raise CoverageError("log must contain records and seal")
    seal = log["seal"]
    if seal is None:
        return {"status": "unsealed", "records": {}, "missing": list(EPOCHS)}
    _verify(seal, reg, actor, "seal", SEAL_FIELDS)
    if (seal["start"], seal["end"], seal["count"]) != (0, 7, len(EPOCHS)):
        raise CoverageError("seal does not cover declared fixed window")
    records = log["records"]
    if not isinstance(records, list):
        raise CoverageError("record collection invalid")
    indexed = {}
    for rec in records:
        _verify(rec, reg, actor, "slot", SLOT_FIELDS)
        epoch = rec["epoch"]
        if type(epoch) is not int or epoch not in EPOCHS:
            raise CoverageError("epoch outside declared range")
        if epoch in indexed:
            raise CoverageError("duplicate/equivocating epoch")
        if rec["outcome"] not in OUTCOMES:
            raise CoverageError("unknown outcome")
        if rec["outcome"] == "present":
            if not isinstance(rec["event"], str) or len(rec["event"]) != 64:
                raise CoverageError("present requires event fingerprint")
        elif rec["event"] is not None:
            raise CoverageError("non-present slot cannot contain event")
        if epoch == 0 and rec["parent"] is not None:
            raise CoverageError("first parent must be null")
        indexed[epoch] = rec
    for epoch in EPOCHS[1:]:
        if epoch in indexed and epoch - 1 in indexed and \
           indexed[epoch]["parent"] != indexed[epoch - 1]["digest"]:
            raise CoverageError("broken append-only hash chain")
    if EPOCHS[-1] in indexed and indexed[EPOCHS[-1]]["digest"] != seal["head"]:
        raise CoverageError("terminal head does not match signed seal")
    missing = [epoch for epoch in EPOCHS if epoch not in indexed]
    return {"status": "complete" if not missing else "missing_archived_records",
            "records": indexed, "missing": missing}


def _admit_deliveries(logs: Mapping[str, Any], verified: Mapping[str, Any],
                      reg: Mapping[str, Any], deliveries: Sequence[Mapping[str, Any]]) -> dict[tuple[str, int], tuple[str, str | None]]:
    admitted: dict[tuple[str, int], tuple[str, str | None]] = {}
    for receipt in deliveries:
        actor = receipt.get("actor") if isinstance(receipt, Mapping) else None
        if actor not in ACTORS:
            raise CoverageError("unknown delivery actor")
        _verify(receipt, reg, actor, "delivery", DELIVERY_FIELDS)
        epoch = receipt["capture_epoch"]
        if type(epoch) is not int or epoch not in verified[actor]["records"]:
            raise CoverageError("delivery for missing capture")
        capture = verified[actor]["records"][epoch]
        if capture["outcome"] != "pending" or capture["digest"] != receipt["capture_digest"]:
            raise CoverageError("delivery not bound to pending capture")
        if type(receipt["delivery_tick"]) is not int or receipt["delivery_tick"] <= epoch:
            raise CoverageError("invalid delivery logical order")
        status = receipt["outcome"]
        if status not in ("present", "absent"):
            raise CoverageError("delivery cannot claim dropout/pending")
        if (status == "present") != (isinstance(receipt["event"], str) and len(receipt["event"]) == 64):
            raise CoverageError("invalid delivery event fingerprint")
        key = actor, epoch
        if key in admitted:
            raise CoverageError("replayed or equivocating delivery")
        admitted[key] = status, receipt["event"]
    return admitted


def reconstruct(logs: Mapping[str, Any], reg: Mapping[str, Any],
                deliveries: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    if not isinstance(logs, Mapping) or set(logs) != set(ACTORS):
        raise CoverageError("both observer logs required")
    verified = {a: verify_log(a, logs[a], reg) for a in ACTORS}
    if any(v["status"] != "complete" for v in verified.values()):
        return {"schema": SCHEMA, "status": "unresolved_log_continuity",
                "archive_gaps": {a: verified[a]["missing"] for a in ACTORS},
                "blind_epoch_bound": None, "full_physical_coverage_proved": False}
    delivery_map = _admit_deliveries(logs, verified, reg, deliveries)
    slots = []
    for epoch in EPOCHS:
        effective = {}
        for actor in ACTORS:
            rec = verified[actor]["records"][epoch]
            effective[actor] = delivery_map.get((actor, epoch), (rec["outcome"], rec["event"]))
        a, b = effective["A"], effective["B"]
        if a[0] == "present" and b[0] == "present":
            outcome = "corroborated_present" if a[1] == b[1] else "conflicting_events"
        elif a[0] == "absent" and b[0] == "absent":
            outcome = "corroborated_absent"
        elif {a[0], b[0]} == {"present", "absent"}:
            outcome = "conflicting_observers"
        elif a[0] == "present" or b[0] == "present":
            outcome = "single_present"
        elif a[0] == "absent" or b[0] == "absent":
            outcome = "single_absent"
        else:
            outcome = "blind"
        slots.append({"epoch": epoch, "status": outcome,
                      "observers": {k: v[0] for k, v in effective.items()}})
    blind = [item["epoch"] for item in slots if item["status"] == "blind"]
    conflicts = [item["epoch"] for item in slots if item["status"].startswith("conflicting")]
    single = [item["epoch"] for item in slots if item["status"].startswith("single")]
    corroborated = [item["epoch"] for item in slots if item["status"].startswith("corroborated")]
    return {"schema": SCHEMA, "status": "conflicted" if conflicts else (
                "observational_gap" if blind else "declared_epochs_observed"),
            "slots": slots, "blind_epochs": blind, "blind_epoch_bound": len(blind),
            "conflict_epochs": conflicts, "single_observer_epochs": single,
            "corroborated_epochs": corroborated,
            "coverage_scope": "declared eight capture epochs under CI-enrolled roles",
            "physical_event_loss_bound": None,
            "full_physical_coverage_proved": False, "physical_sensor_identity_proved": False}


def choose_audit(logs: Mapping[str, Any], reg: Mapping[str, Any],
                 deliveries: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """A suggestion; not an executed observation or authority grant."""
    report = reconstruct(logs, reg, deliveries)
    if report["status"] == "unresolved_log_continuity":
        gaps = [(a, i) for a in ACTORS for i in report["archive_gaps"][a]]
        return {"action": "retrieve_signed_archived_slot", "target": list(gaps[0]) if gaps else None,
                "observation_cost": 1, "intervention_cost": 0, "outcome": "planned_only"}
    if report["conflict_epochs"]:
        return {"action": "independent_disagreement_review", "target": report["conflict_epochs"][0],
                "observation_cost": 3, "intervention_cost": 0, "outcome": "planned_only"}
    pending = [(a, r["epoch"]) for a in ACTORS for r in logs[a]["records"]
               if r["outcome"] == "pending" and
               not any(d.get("actor") == a and d.get("capture_epoch") == r["epoch"] for d in deliveries)]
    if pending:
        return {"action": "request_capture_bound_delivery", "target": list(pending[0]),
                "observation_cost": 1, "intervention_cost": 0, "outcome": "planned_only"}
    if report["blind_epochs"]:
        return {"action": "new_authorized_reobservation", "target": report["blind_epochs"][0],
                "observation_cost": 2, "intervention_cost": 1,
                "outcome": "planned_only_not_retroactive_evidence"}
    return {"action": "none", "target": None, "observation_cost": 0, "intervention_cost": 0,
            "outcome": "scope_saturated_no_physical_completeness_claim"}


def fixture(*, delayed: bool = True) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    reg = enrollment(deterministic=True)
    logs = {"A": produce_log("A", reg, {2: "dropout", 5: "dropout", 6: "pending"}),
            "B": produce_log("B", reg, {1: "dropout", 4: "dropout"})}
    deliveries = ([delayed_delivery("A", reg, logs["A"]["records"][6])]
                  if delayed else [])
    return logs, reg, deliveries


def demonstration() -> dict[str, Any]:
    logs, reg, late = fixture(delayed=False)
    before = reconstruct(logs, reg)
    plan = choose_audit(logs, reg)
    after = reconstruct(logs, reg, [delayed_delivery("A", reg, logs["A"]["records"][6])])
    disrupted = {"A": logs["A"], "B": {**logs["B"], "records": [r for r in logs["B"]["records"] if r["epoch"] != 3]}}
    return {"experiment": "RE-008", "before_delivery": before, "planned_audit": plan,
            "after_delivery": after,
            "lost_archive": reconstruct(disrupted, reg),
            "archive_recovery": reconstruct(logs, reg),
            "claims": {"no_unobserved_physical_events_proved": False,
                       "honest_enrollment_assumption": True,
                       "declared_epoch_count": len(EPOCHS)}}


if __name__ == "__main__":
    print(json.dumps(demonstration(), indent=2, sort_keys=True))
