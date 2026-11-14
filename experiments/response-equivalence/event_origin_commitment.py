"""RE-010: separately enrolled event-origin claims versus source/observer reports.

CI HMAC verifies which enrolled role *claimed* a finite event, not that an event
occurred in the physical world. The origin manifest is generated independently
of source counter and observer logs, but all fixtures share a declared model.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Mapping, Sequence

from coverage_reconstruction import (
    ACTORS, EPOCHS, CoverageError, _admit_deliveries, _key, _sign,
    _verify, delayed_delivery, produce_log, sha, verify_log,
)
from common_mode_counter import (
    BOUNDS, CounterError, acknowledge, produce_source,
    reconstruct as reconstruct_counter, register, verify_source,
)

SCHEMA = "in-formation.response-re010-origin/0.1"
ORIGIN = "O"
ORIGIN_FIELDS = frozenset((
    "schema", "kind", "challenge", "actor", "key_id", "controller_digest",
    "epoch", "event_id", "mark", "fingerprint", "parent",
))
SEAL_FIELDS = frozenset((
    "schema", "kind", "challenge", "actor", "key_id", "controller_digest",
    "start", "end", "count", "head", "declared_scope",
))
DEFAULT_CLAIMS = ((1, "p"), (3, "hidden-event"), (4, "q"), (6, "r"))
OBSERVED_CLAIMS = ((1, "p"), (4, "q"), (6, "r"))


class OriginError(CounterError):
    """An origin claim is malformed, altered, replayed, or not enrolled."""


def registration(*, deterministic: bool = False) -> dict[str, Any]:
    """Role-scoped test enrollment. Signing keys are NOT physical root trust."""
    reg = register(deterministic=deterministic)
    key = "56" * 32 if deterministic else secrets.token_hex(32)
    reg["keys"][ORIGIN] = key
    reg["key_ids"][ORIGIN] = hashlib.sha256(bytes.fromhex(key)).hexdigest()
    return reg


def origin_key(reg: Mapping[str, Any]) -> bytes:
    try:
        value = reg["keys"][ORIGIN]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("wrong length")
        key = bytes.fromhex(value)
        if len(key) != 32 or reg["key_ids"][ORIGIN] != hashlib.sha256(key).hexdigest():
            raise ValueError("key id mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        raise OriginError("origin enrollment key invalid") from exc
    return key


def _body(reg: Mapping[str, Any], kind: str, controller_digest: str | None) -> dict[str, Any]:
    return {"schema": SCHEMA, "kind": kind, "challenge": reg["challenge"],
            "actor": ORIGIN, "key_id": reg["key_ids"][ORIGIN],
            "controller_digest": controller_digest}


def _check_controller_digest(value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or len(value) != 64 or
                              any(ch not in "0123456789abcdef" for ch in value)):
        raise OriginError("controller digest invalid")


def verify_signed(rec: Any, reg: Mapping[str, Any], kind: str,
                  fields: frozenset[str], controller_digest: str | None) -> None:
    if not isinstance(rec, dict) or set(rec) != fields | {"mac", "digest"}:
        raise OriginError("origin record fields invalid")
    expected_identity = _body(reg, kind, controller_digest)
    if any(rec.get(k) != v for k, v in expected_identity.items()):
        raise OriginError("origin record identity/session/controller mismatch")
    body = {k: v for k, v in rec.items() if k not in ("mac", "digest")}
    expected = hmac.new(origin_key(reg), json.dumps(body, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(),
        hashlib.sha256).hexdigest()
    if not isinstance(rec["mac"], str) or not hmac.compare_digest(expected, rec["mac"]):
        raise OriginError("origin HMAC invalid")
    if rec["digest"] != sha({**body, "mac": rec["mac"]}):
        raise OriginError("origin digest invalid")


def make_origin(reg: Mapping[str, Any], claims: Sequence[tuple[int, str]] = DEFAULT_CLAIMS,
                *, controller_digest: str | None = None) -> dict[str, Any]:
    """Construct from origin event declarations ONLY, never source/observer data."""
    _check_controller_digest(controller_digest)
    if not isinstance(claims, (tuple, list)):
        raise OriginError("origin claims must be an ordered finite sequence")
    key = origin_key(reg)
    parent = None
    receipts = []
    previous = -1
    for epoch, mark in claims:
        if type(epoch) is not int or epoch not in EPOCHS or epoch <= previous or \
           not isinstance(mark, str) or not mark or len(mark) > 100:
            raise OriginError("invalid, duplicated, unordered origin event")
        previous = epoch
        item = _sign({**_body(reg, "event", controller_digest),
                "epoch": epoch, "event_id": f"origin-{epoch}", "mark": mark,
                "fingerprint": sha({"epoch": epoch, "mark": mark}),
                "parent": parent}, key)
        receipts.append(item)
        parent = item["digest"]
    seal = _sign({**_body(reg, "seal", controller_digest),
        "start": EPOCHS[0], "end": EPOCHS[-1], "count": len(receipts),
        "head": parent, "declared_scope": "finite-eight-epochs-one-event-max"}, key)
    return {"receipts": receipts, "seal": seal}


def verify_origin(manifest: Mapping[str, Any], reg: Mapping[str, Any],
                  *, controller_digest: str | None = None) -> dict[int, dict[str, Any]]:
    """Check integrity, identity and finite-range claimed origin completeness."""
    _check_controller_digest(controller_digest)
    if not isinstance(manifest, dict) or set(manifest) != {"receipts", "seal"}:
        raise OriginError("origin envelope invalid or missing")
    receipts = manifest["receipts"]
    if not isinstance(receipts, list) or len(receipts) > len(EPOCHS):
        raise OriginError("origin receipts invalid")
    previous = None
    last_epoch = -1
    accepted = {}
    for rec in receipts:
        verify_signed(rec, reg, "event", ORIGIN_FIELDS, controller_digest)
        epoch = rec["epoch"]
        if type(epoch) is not int or epoch not in EPOCHS or epoch <= last_epoch or \
           rec["event_id"] != f"origin-{epoch}" or \
           not isinstance(rec["mark"], str) or not (0 < len(rec["mark"]) <= 100) or \
           rec["parent"] != previous or \
           rec["fingerprint"] != sha({"epoch":epoch,"mark":rec["mark"]}):
            raise OriginError("origin claim identity, chain or fingerprint invalid")
        accepted[epoch] = rec
        last_epoch, previous = epoch, rec["digest"]
    seal = manifest["seal"]
    verify_signed(seal, reg, "seal", SEAL_FIELDS, controller_digest)
    if (seal["start"], seal["end"], seal["count"], seal["head"], seal["declared_scope"]) != (
            EPOCHS[0], EPOCHS[-1], len(receipts), previous,
            "finite-eight-epochs-one-event-max"):
        raise OriginError("origin seal cannot establish claimed finite window")
    return accepted


def detect_origin_fork(manifests: Sequence[Mapping[str, Any]], reg: Mapping[str, Any],
                       *, controller_digest: str | None = None) -> dict[str, Any]:
    """Detect two distinct signed histories only if BOTH were retained."""
    if len(manifests) < 2:
        return {"status": "insufficient_views", "equivocation_proved": False}
    for m in manifests:
        verify_origin(m, reg, controller_digest=controller_digest)
    heads = {m["seal"]["digest"] for m in manifests}
    return {"status": "conflicting_signed_origins" if len(heads) > 1 else "identical_origin",
            "equivocation_proved": len(heads) > 1}


def _observed_claims(logs: Mapping[str, Any], reg: Mapping[str, Any],
                     deliveries: Sequence[Mapping[str, Any]]) -> dict[int, str] | None:
    verified = {actor: verify_log(actor, logs[actor], reg) for actor in ACTORS}
    if any(v["status"] != "complete" for v in verified.values()):
        return None
    effective = _admit_deliveries(logs, verified, reg, deliveries)
    observed = {}
    for epoch in EPOCHS:
        statuses = [effective.get((actor, epoch), (verified[actor]["records"][epoch]["outcome"],
                   verified[actor]["records"][epoch]["event"])) for actor in ACTORS]
        fingerprints = {fingerprint for status,fingerprint in statuses if status=="present"}
        if len(fingerprints) > 1:
            raise OriginError("observer event identities conflict")
        if fingerprints:
            observed[epoch] = next(iter(fingerprints))
    return observed


def triangulate(source: Mapping[str, Any], logs: Mapping[str, Any],
                acknowledgements: Mapping[str, Any], manifest: Mapping[str, Any] | None,
                reg: Mapping[str, Any], deliveries: Sequence[Mapping[str, Any]] = (),
                *, controller_digest: str | None = None) -> dict[str, Any]:
    """Report agreement and conditional reconciliation, never physical truth."""
    source_report = reconstruct_counter(source, logs, acknowledgements, reg,
                                        deliveries, controller_digest=controller_digest)
    base = {"schema": SCHEMA, "source_observer": source_report,
            "physical_occurrence_verified": False,
            "origin_sensor_independence_verified": False,
            "origin_completeness_verified": False,
            "physical_common_mode_loss_proved": False,
            "global_event_completeness_proved": False,
            "cross_host_elapsed": None}
    if source_report["status"].startswith("unresolved_"):
        return {**base, "status": "unresolved_observer_evidence", "origin_vs_observers": None}
    if manifest is None:
        return {**base, "status": "origin_evidence_unavailable", "origin_vs_observers": None}
    origins = verify_origin(manifest, reg, controller_digest=controller_digest)
    observed = _observed_claims(logs, reg, deliveries)
    if observed is None:
        return {**base, "status": "unresolved_observer_evidence", "origin_vs_observers": None}
    mismatch = sorted(e for e in (set(origins)&set(observed)) if
                      origins[e]["fingerprint"] != observed[e])
    only_origin = sorted(set(origins)-set(observed))
    only_observers = sorted(set(observed)-set(origins))
    counts = verify_source(source, reg, controller_digest=controller_digest)
    windows = []
    for start,end,before,after in zip(BOUNDS,BOUNDS[1:],counts,counts[1:]):
        origins_in = sum(start <= e < end for e in origins)
        obs_in = sum(start <= e < end for e in observed)
        src_in = after-before
        windows.append({"start":start, "end_exclusive":end,
                        "source_claimed":src_in, "origin_claimed":origins_in,
                        "observer_reported":obs_in, "source_minus_origin":src_in-origins_in})
    origin_counts_match_source = all(w["source_minus_origin"]==0 for w in windows)
    identities_match = not mismatch and not only_observers
    origin_matches_observers = identities_match and not only_origin
    if mismatch:
        status = "origin_observer_event_identity_conflict"
    elif origin_counts_match_source and only_origin and not only_observers:
        status = "origin_corrob_source_claim_not_observer_readout"
    elif origin_matches_observers and not origin_counts_match_source:
        status = "origin_corrob_observer_claim_not_source_count"
    elif origin_counts_match_source and origin_matches_observers:
        status = "all_declared_claims_agree"
    else:
        status = "unresolved_three_way_disagreement"
    return {**base,"status":status,"origin_reported_total":len(origins),
            "observer_reported_total":len(observed),
            "source_reported_total":counts[-1],
            "origin_only_epochs":only_origin, "observer_only_epochs":only_observers,
            "identity_conflict_epochs":mismatch,
            "source_origin_windows":windows,
            "conditional_on_origin_truthfulness_and_completeness": (
                "candidate observer omission" if status=="origin_corrob_source_claim_not_observer_readout"
                else "candidate source overcount" if status=="origin_corrob_observer_claim_not_source_count"
                else "no discrepancy within declared scope" if status=="all_declared_claims_agree"
                else "unresolved")}


def fixture(*, claimed_origin: Sequence[tuple[int,str]]=DEFAULT_CLAIMS,
            source_counts: Sequence[int]=(0,2,4),
            deterministic: bool=True) -> tuple[dict[str, Any], ...]:
    reg = registration(deterministic=deterministic)
    source = produce_source(reg, source_counts)
    logs = {"A": produce_log("A", reg, {2:"dropout",5:"dropout",6:"pending"}),
            "B": produce_log("B", reg, {1:"dropout",4:"dropout"})}
    ack = {a: acknowledge(a, logs[a], source, reg) for a in ACTORS}
    deliveries = [delayed_delivery("A", reg, logs["A"]["records"][6])]
    manifest = make_origin(reg, claimed_origin)
    return source, logs, ack, manifest, reg, deliveries


def demonstration() -> dict[str, Any]:
    s,l,a,o,r,d=fixture()
    missed=triangulate(s,l,a,o,r,d)
    s2,l2,a2,o2,r2,d2=fixture(claimed_origin=OBSERVED_CLAIMS)
    overcount=triangulate(s2,l2,a2,o2,r2,d2)
    equal_evidence=make_origin(r,DEFAULT_CLAIMS)==make_origin(r,DEFAULT_CLAIMS)
    return {"experiment":"RE-010", "origin_claims_four":missed,
            "origin_claims_three":overcount,
            "latent_worlds_with_identical_public_evidence": [
                 "real_undetected_event_epoch_3", "origin_role_fabricated_event_epoch_3"],
            "same_signed_evidence_under_both_latent_worlds":equal_evidence,
            "physical_world_distinguished_by_records":False}

if __name__ == "__main__":
    print(json.dumps(demonstration(),indent=2,sort_keys=True))