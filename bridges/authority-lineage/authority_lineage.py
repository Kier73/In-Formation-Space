"""Append-only lineage for finalized authority decisions.

A late observation does not mutate a prior decision. It becomes a proposal.
A reviewed proposal may authorize a new decision that explicitly supersedes
one or more prior decisions. Competing accepted revisions remain visible as
multiple frontier branches until a later decision explicitly merges them.

Digests provide deterministic integrity checks, not signer authentication.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

FORMAT = "in-formation.authority-lineage-ledger"
SCHEMA = "in-formation.authority-lineage-ledger/0.1"
ZERO_DIGEST = "0" * 64
DECISION_STATUSES = {"AUTHORIZED", "CONFLICT", "REFUSED"}
PROPOSAL_OUTCOMES = {"ACCEPTED", "REJECTED", "INCONCLUSIVE", "STALE"}
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX_256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _event_key(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("event_key must be a mapping")
    kind = _nonempty(value.get("kind"), "event_key.kind")
    logical_time = value.get("logical_time")
    if isinstance(logical_time, bool) or not isinstance(logical_time, int) or logical_time < 0:
        raise ValueError("event_key.logical_time must be a non-negative integer")
    if set(value) != {"kind", "logical_time"}:
        raise ValueError("event_key must contain exactly kind and logical_time")
    return {"kind": kind, "logical_time": logical_time}


def _event_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("kind") == right.get("kind")
        and left.get("logical_time") == right.get("logical_time")
    )


def _entries_of_type(ledger: Mapping[str, Any], entry_type: str) -> list[dict[str, Any]]:
    return [
        entry for entry in ledger["entries"]
        if entry["entry_type"] == entry_type
    ]


def _decision_records(ledger: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [entry["payload"] for entry in _entries_of_type(ledger, "decision_issued")]


def _frontier_ids(
    decisions: Sequence[Mapping[str, Any]],
    event_key: Mapping[str, Any],
) -> list[str]:
    selected = [
        decision for decision in decisions
        if _event_equal(decision["event_key"], event_key)
    ]
    superseded = {
        parent_id
        for decision in selected
        for parent_id in decision["supersedes_decision_ids"]
    }
    return sorted(
        decision["decision_id"]
        for decision in selected
        if decision["decision_id"] not in superseded
    )


def _ledger_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    return digest([entry["entry_digest"] for entry in entries])


def _append_entry(
    ledger: Mapping[str, Any],
    entry_type: str,
    actor: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    validate_ledger(ledger)
    new_ledger = copy.deepcopy(dict(ledger))
    entries = list(new_ledger["entries"])
    previous = entries[-1]["entry_digest"] if entries else ZERO_DIGEST
    core = {
        "sequence": len(entries) + 1,
        "entry_type": _nonempty(entry_type, "entry_type"),
        "actor": _nonempty(actor, "actor"),
        "previous_digest": previous,
        "payload": copy.deepcopy(dict(payload)),
    }
    entry = {**core, "entry_digest": digest(core)}
    entries.append(entry)
    new_ledger["entries"] = entries
    new_ledger["ledger_digest"] = _ledger_digest(entries)
    validate_ledger(new_ledger)
    return new_ledger


def create_ledger(ledger_id: str, *, created_by: str) -> dict[str, Any]:
    ledger_id = _nonempty(ledger_id, "ledger_id")
    created_by = _nonempty(created_by, "created_by")
    core = {
        "sequence": 1,
        "entry_type": "ledger_created",
        "actor": created_by,
        "previous_digest": ZERO_DIGEST,
        "payload": {"ledger_id": ledger_id},
    }
    entry = {**core, "entry_digest": digest(core)}
    ledger = {
        "format": FORMAT,
        "schema": SCHEMA,
        "ledger_id": ledger_id,
        "entries": [entry],
        "ledger_digest": digest([entry["entry_digest"]]),
    }
    validate_ledger(ledger)
    return ledger


def current_frontier(
    ledger: Mapping[str, Any],
    event_key: Mapping[str, Any],
) -> dict[str, Any]:
    validate_ledger(ledger)
    event = _event_key(event_key)
    decisions = _decision_records(ledger)
    decision_ids = _frontier_ids(decisions, event)
    if not decision_ids:
        status = "NO_DECISION"
    elif len(decision_ids) == 1:
        status = "SINGLE_DECISION"
    else:
        status = "AMBIGUOUS_FRONTIER"
    return {
        "event_key": event,
        "status": status,
        "decision_ids": decision_ids,
    }


def decision_history(
    ledger: Mapping[str, Any],
    event_key: Mapping[str, Any],
) -> list[dict[str, Any]]:
    validate_ledger(ledger)
    event = _event_key(event_key)
    return [
        copy.deepcopy(decision)
        for decision in _decision_records(ledger)
        if _event_equal(decision["event_key"], event)
    ]


def propose_revision(
    ledger: Mapping[str, Any],
    *,
    event_key: Mapping[str, Any],
    base_decision_ids: Sequence[str],
    evidence_refs: Sequence[Mapping[str, str]],
    reason: str,
    proposed_by: str,
) -> tuple[dict[str, Any], str]:
    """Append a proposal; it does not change the current authority frontier."""
    validate_ledger(ledger)
    event = _event_key(event_key)
    actor = _nonempty(proposed_by, "proposed_by")
    reason = _nonempty(reason, "reason")
    if not isinstance(base_decision_ids, (list, tuple)) or not base_decision_ids:
        raise ValueError("revision proposal must name at least one base decision")
    bases = sorted(_nonempty(value, "base_decision_id") for value in base_decision_ids)
    if len(set(bases)) != len(bases):
        raise ValueError("base decision IDs must be unique")
    frontier = current_frontier(ledger, event)["decision_ids"]
    if bases != frontier:
        raise ValueError("proposal must name the complete current authority frontier")
    if not isinstance(evidence_refs, (list, tuple)) or not evidence_refs:
        raise ValueError("revision proposal must retain at least one evidence reference")
    normalized_refs = []
    seen_refs = set()
    for index, item in enumerate(evidence_refs):
        if not isinstance(item, Mapping):
            raise TypeError(f"evidence_refs[{index}] must be a mapping")
        ref = _nonempty(item.get("ref"), f"evidence_refs[{index}].ref")
        ref_digest = _sha256(item.get("sha256"), f"evidence_refs[{index}].sha256")
        if ref in seen_refs:
            raise ValueError("evidence references must be unique")
        seen_refs.add(ref)
        normalized_refs.append({"ref": ref, "sha256": ref_digest})

    proposal_number = len(_entries_of_type(ledger, "revision_proposed")) + 1
    proposal_id = f"proposal-{proposal_number:06d}"
    payload = {
        "proposal_id": proposal_id,
        "event_key": event,
        "base_decision_ids": bases,
        "evidence_refs": normalized_refs,
        "reason": reason,
        "status_at_creation": "PROPOSED",
    }
    return _append_entry(
        ledger, "revision_proposed", actor, payload
    ), proposal_id


def resolve_proposal(
    ledger: Mapping[str, Any],
    proposal_id: str,
    *,
    outcome: str,
    rationale: str,
    resolved_by: str,
) -> dict[str, Any]:
    """Append an explicit review outcome; a stale proposal cannot be accepted."""
    validate_ledger(ledger)
    proposal_id = _nonempty(proposal_id, "proposal_id")
    if outcome not in PROPOSAL_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(PROPOSAL_OUTCOMES)}")
    proposal_entries = [
        entry for entry in _entries_of_type(ledger, "revision_proposed")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    if not proposal_entries:
        raise KeyError(proposal_id)
    prior_resolutions = [
        entry for entry in _entries_of_type(ledger, "proposal_resolved")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    if prior_resolutions:
        raise ValueError("proposal already has an immutable resolution")
    proposal = proposal_entries[0]["payload"]
    frontier = current_frontier(ledger, proposal["event_key"])["decision_ids"]
    is_stale = frontier != proposal["base_decision_ids"]
    if outcome == "ACCEPTED" and is_stale:
        raise ValueError("stale proposal cannot be accepted against a changed authority frontier")
    if outcome == "STALE" and not is_stale:
        raise ValueError("proposal is not stale relative to the current authority frontier")
    certificate_entries = [
        entry for entry in _entries_of_type(ledger, "proposal_review_certified")
        if entry["payload"]["proposal_id"] == proposal_id
    ]
    if len(certificate_entries) > 1:
        raise ValueError("proposal has more than one immutable review certificate")
    certificate_digest = None
    if certificate_entries:
        certificate_payload = certificate_entries[0]["payload"]
        certificate = certificate_payload["certificate"]
        expected_outcome = (
            "STALE" if is_stale else certificate["evaluation"]["outcome"]
        )
        if outcome != expected_outcome:
            raise ValueError(
                "resolution outcome differs from the recorded review certificate"
            )
        certificate_digest = certificate_payload["certificate_digest"]

    payload = {
        "proposal_id": proposal_id,
        "outcome": outcome,
        "rationale": _nonempty(rationale, "rationale"),
        "base_decision_ids": list(proposal["base_decision_ids"]),
        "frontier_at_resolution": frontier,
    }
    if certificate_digest is not None:
        payload["review_certificate_digest"] = certificate_digest
    return _append_entry(
        ledger, "proposal_resolved", _nonempty(resolved_by, "resolved_by"), payload
    )


def issue_decision(
    ledger: Mapping[str, Any],
    *,
    event_key: Mapping[str, Any],
    status: str,
    evidence_set_digest: str,
    policy_digest: str,
    issued_by: str,
    rationale: str,
    representative_ref: str | None = None,
    proposal_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Append a decision; revisions must be backed by a previously accepted proposal."""
    validate_ledger(ledger)
    event = _event_key(event_key)
    if status not in DECISION_STATUSES:
        raise ValueError(f"status must be one of {sorted(DECISION_STATUSES)}")
    evidence_digest = _sha256(evidence_set_digest, "evidence_set_digest")
    policy_digest_value = _sha256(policy_digest, "policy_digest")
    issuer = _nonempty(issued_by, "issued_by")
    rationale = _nonempty(rationale, "rationale")
    if status == "AUTHORIZED":
        representative = _nonempty(representative_ref, "representative_ref")
    else:
        if representative_ref is not None:
            raise ValueError("non-authorized decisions must not select a representative")
        representative = None

    all_decisions = _decision_records(ledger)
    event_decisions = [
        decision for decision in all_decisions
        if _event_equal(decision["event_key"], event)
    ]
    if proposal_id is None:
        if event_decisions:
            raise ValueError("a later decision requires an accepted revision proposal")
        bases: list[str] = []
        generation = 0
    else:
        proposal_id = _nonempty(proposal_id, "proposal_id")
        proposal_entries = [
            entry for entry in _entries_of_type(ledger, "revision_proposed")
            if entry["payload"]["proposal_id"] == proposal_id
        ]
        if not proposal_entries:
            raise KeyError(proposal_id)
        proposal = proposal_entries[0]["payload"]
        if not _event_equal(proposal["event_key"], event):
            raise ValueError("revision proposal event does not match decision event")
        resolutions = [
            entry["payload"] for entry in _entries_of_type(ledger, "proposal_resolved")
            if entry["payload"]["proposal_id"] == proposal_id
        ]
        if not resolutions or resolutions[0]["outcome"] != "ACCEPTED":
            raise ValueError("a revised decision requires an explicitly accepted proposal")
        issued_for_proposal = [
            decision for decision in all_decisions
            if decision["proposal_id"] == proposal_id
        ]
        if issued_for_proposal:
            raise ValueError("an accepted proposal can authorize only one decision")
        bases = list(proposal["base_decision_ids"])
        if not bases or any(
            not any(decision["decision_id"] == base for decision in event_decisions)
            for base in bases
        ):
            raise ValueError("revision bases are not existing decisions for this event")
        generation = 1 + max(
            decision["generation"]
            for decision in event_decisions
            if decision["decision_id"] in bases
        )

    decision_number = len(_entries_of_type(ledger, "decision_issued")) + 1
    decision_id = f"decision-{decision_number:06d}"
    core = {
        "decision_id": decision_id,
        "event_key": event,
        "generation": generation,
        "supersedes_decision_ids": sorted(bases),
        "proposal_id": proposal_id,
        "status": status,
        "evidence_set_digest": evidence_digest,
        "policy_digest": policy_digest_value,
        "representative_ref": representative,
        "rationale": rationale,
        "issued_by": issuer,
    }
    decision = {**core, "decision_digest": digest(core)}
    new_ledger = _append_entry(
        ledger, "decision_issued", issuer, decision
    )
    return new_ledger, decision_id


def validate_ledger(ledger: Mapping[str, Any]) -> None:
    """Rebuild the entire append-only hash chain and all lineage constraints."""
    if not isinstance(ledger, Mapping):
        raise TypeError("ledger must be a mapping")
    if ledger.get("format") != FORMAT or ledger.get("schema") != SCHEMA:
        raise ValueError("unsupported authority-lineage ledger format or schema")
    _nonempty(ledger.get("ledger_id"), "ledger_id")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("authority-lineage ledger must contain an append-only entry list")
    if set(ledger) != {"format", "schema", "ledger_id", "entries", "ledger_digest"}:
        raise ValueError("ledger has missing or unrecognized top-level fields")

    proposals: dict[str, dict[str, Any]] = {}
    resolutions: dict[str, dict[str, Any]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    decision_proposals: set[str] = set()
    review_certificates: dict[str, dict[str, Any]] = {}
    previous = ZERO_DIGEST

    def frontier_at(event: Mapping[str, Any]) -> list[str]:
        return _frontier_ids(list(decisions.values()), event)

    for expected_sequence, entry in enumerate(entries, start=1):
        if not isinstance(entry, Mapping):
            raise TypeError("ledger entries must be mappings")
        expected_fields = {
            "sequence", "entry_type", "actor", "previous_digest", "payload", "entry_digest"
        }
        if set(entry) != expected_fields:
            raise ValueError("ledger entry has missing or unrecognized fields")
        if entry["sequence"] != expected_sequence:
            raise ValueError("ledger sequence is not contiguous")
        _nonempty(entry["entry_type"], "entry_type")
        _nonempty(entry["actor"], "actor")
        if entry["previous_digest"] != previous:
            raise ValueError("ledger previous_digest does not match prior entry")
        if not isinstance(entry["payload"], Mapping):
            raise TypeError("ledger entry payload must be a mapping")
        entry_core = {
            key: entry[key]
            for key in ("sequence", "entry_type", "actor", "previous_digest", "payload")
        }
        calculated_entry_digest = digest(entry_core)
        if entry["entry_digest"] != calculated_entry_digest:
            raise ValueError("ledger entry digest mismatch")
        previous = calculated_entry_digest
        entry_type = entry["entry_type"]
        payload = entry["payload"]

        if expected_sequence == 1:
            if entry_type != "ledger_created":
                raise ValueError("first authority-lineage entry must create the ledger")
            if dict(payload) != {"ledger_id": ledger["ledger_id"]}:
                raise ValueError("ledger_created payload does not match ledger identity")
            continue
        if entry_type == "ledger_created":
            raise ValueError("authority-lineage ledger cannot be created more than once")

        if entry_type == "revision_proposed":
            proposal_id = _nonempty(payload.get("proposal_id"), "proposal_id")
            if proposal_id in proposals:
                raise ValueError("duplicate revision proposal ID")
            event = _event_key(payload.get("event_key"))
            bases = payload.get("base_decision_ids")
            if not isinstance(bases, list) or not bases:
                raise ValueError("revision proposal must name base decisions")
            if bases != sorted(set(bases)):
                raise ValueError("proposal base decision IDs must be unique and sorted")
            if bases != frontier_at(event):
                raise ValueError("proposal must be anchored to the complete current frontier")
            evidence_refs = payload.get("evidence_refs")
            if not isinstance(evidence_refs, list) or not evidence_refs:
                raise ValueError("revision proposal must retain evidence references")
            refs_seen = set()
            for item in evidence_refs:
                if not isinstance(item, Mapping) or set(item) != {"ref", "sha256"}:
                    raise ValueError("proposal evidence reference has invalid shape")
                ref = _nonempty(item["ref"], "evidence reference")
                _sha256(item["sha256"], "evidence reference digest")
                if ref in refs_seen:
                    raise ValueError("duplicate proposal evidence reference")
                refs_seen.add(ref)
            _nonempty(payload.get("reason"), "proposal reason")
            if payload.get("status_at_creation") != "PROPOSED":
                raise ValueError("new revision proposals must begin as PROPOSED")
            proposals[proposal_id] = dict(payload)
        elif entry_type == "proposal_review_certified":
            proposal_id = _nonempty(payload.get("proposal_id"), "proposal_id")
            if proposal_id not in proposals:
                raise ValueError("review certificate precedes its revision proposal")
            if proposal_id in review_certificates:
                raise ValueError("proposal has more than one immutable review certificate")
            if proposal_id in resolutions:
                raise ValueError("review certificate cannot follow proposal resolution")
            expected_payload_fields = {
                "proposal_id", "event_key", "certificate_id",
                "certificate_digest", "certificate",
            }
            if set(payload) != expected_payload_fields:
                raise ValueError("review certificate ledger entry has invalid fields")
            proposal = proposals[proposal_id]
            certificate = payload.get("certificate")
            if not isinstance(certificate, Mapping):
                raise TypeError("review certificate payload must be a mapping")
            if certificate.get("format") != "in-formation.authority-review-certificate":
                raise ValueError("unsupported review certificate format")
            if certificate.get("schema") != "in-formation.authority-review-certificate/0.1":
                raise ValueError("unsupported review certificate schema")
            certificate_id = _nonempty(payload.get("certificate_id"), "certificate_id")
            if certificate_id != f"review-certificate:{proposal_id}":
                raise ValueError("review certificate ID does not bind its proposal")
            if certificate.get("certificate_id") != certificate_id:
                raise ValueError("ledger and certificate IDs differ")
            certificate_digest = _sha256(
                payload.get("certificate_digest"), "review certificate digest"
            )
            certificate_core = {
                key: value for key, value in certificate.items()
                if key != "certificate_digest"
            }
            if certificate.get("certificate_digest") != certificate_digest:
                raise ValueError("embedded certificate digest differs from ledger entry")
            if digest(certificate_core) != certificate_digest:
                raise ValueError("embedded review certificate digest mismatch")
            if certificate.get("ledger_id") != ledger["ledger_id"]:
                raise ValueError("review certificate belongs to another ledger")
            if certificate.get("proposal_id") != proposal_id:
                raise ValueError("review certificate belongs to another proposal")
            if certificate.get("proposal_digest") != digest(proposal):
                raise ValueError("review certificate proposal digest mismatch")
            event = _event_key(payload.get("event_key"))
            if not _event_equal(event, proposal["event_key"]):
                raise ValueError("review certificate entry event differs from its proposal")
            if not _event_equal(certificate.get("event_key", {}), event):
                raise ValueError("embedded review certificate event differs from its proposal")
            if certificate.get("base_decision_ids") != proposal["base_decision_ids"]:
                raise ValueError("review certificate base decisions differ from proposal")
            if frontier_at(event) != proposal["base_decision_ids"]:
                raise ValueError("review certificate was recorded against a stale frontier")
            base_digests = certificate.get("base_decision_digests")
            expected_base_digests = {
                decision_id: decisions[decision_id]["decision_digest"]
                for decision_id in proposal["base_decision_ids"]
                if decision_id in decisions
            }
            if base_digests != expected_base_digests:
                raise ValueError("review certificate base decision digests mismatch")
            policy_snapshot = certificate.get("policy_snapshot")
            if not isinstance(policy_snapshot, Mapping):
                raise TypeError("review certificate policy snapshot must be a mapping")
            _sha256(certificate.get("policy_digest"), "review certificate policy digest")
            if certificate["policy_digest"] != digest(policy_snapshot):
                raise ValueError("review certificate policy digest mismatch")
            evaluation = certificate.get("evaluation")
            if not isinstance(evaluation, Mapping) or evaluation.get("outcome") not in {
                "ACCEPTED", "REJECTED", "INCONCLUSIVE"
            }:
                raise ValueError("review certificate has an invalid evaluation outcome")
            review_certificates[proposal_id] = {
                "certificate_digest": certificate_digest,
                "certificate": dict(certificate),
            }
        elif entry_type == "proposal_resolved":
            proposal_id = _nonempty(payload.get("proposal_id"), "proposal_id")
            if proposal_id not in proposals:
                raise ValueError("proposal resolution precedes proposal")
            if proposal_id in resolutions:
                raise ValueError("proposal has more than one immutable resolution")
            outcome = payload.get("outcome")
            if outcome not in PROPOSAL_OUTCOMES:
                raise ValueError("proposal resolution has unknown outcome")
            proposal = proposals[proposal_id]
            if payload.get("base_decision_ids") != proposal["base_decision_ids"]:
                raise ValueError("proposal resolution changed its base decision set")
            frontier = frontier_at(proposal["event_key"])
            if payload.get("frontier_at_resolution") != frontier:
                raise ValueError("proposal resolution frontier receipt is inconsistent")
            stale = frontier != proposal["base_decision_ids"]
            if outcome == "ACCEPTED" and stale:
                raise ValueError("stale revision proposal cannot be accepted")
            if outcome == "STALE" and not stale:
                raise ValueError("STALE outcome requires a changed authority frontier")
            certificate_record = review_certificates.get(proposal_id)
            if certificate_record is None:
                if "review_certificate_digest" in payload:
                    raise ValueError("resolution references an unrecorded review certificate")
            else:
                certificate = certificate_record["certificate"]
                expected_outcome = (
                    "STALE" if stale else certificate["evaluation"]["outcome"]
                )
                if outcome != expected_outcome:
                    raise ValueError("proposal resolution differs from its review certificate")
                if payload.get("review_certificate_digest") != certificate_record["certificate_digest"]:
                    raise ValueError("proposal resolution review certificate digest mismatch")
            _nonempty(payload.get("rationale"), "proposal resolution rationale")
            resolutions[proposal_id] = dict(payload)
        elif entry_type == "decision_issued":
            decision_id = _nonempty(payload.get("decision_id"), "decision_id")
            if decision_id in decisions:
                raise ValueError("duplicate authority decision ID")
            event = _event_key(payload.get("event_key"))
            status = payload.get("status")
            if status not in DECISION_STATUSES:
                raise ValueError("decision has unknown authority status")
            if status == "AUTHORIZED":
                _nonempty(payload.get("representative_ref"), "authorized representative_ref")
            elif payload.get("representative_ref") is not None:
                raise ValueError("non-authorized decision cannot contain a representative")
            _sha256(payload.get("evidence_set_digest"), "evidence_set_digest")
            _sha256(payload.get("policy_digest"), "policy_digest")
            _nonempty(payload.get("rationale"), "decision rationale")
            _nonempty(payload.get("issued_by"), "decision issued_by")
            bases = payload.get("supersedes_decision_ids")
            if not isinstance(bases, list) or bases != sorted(set(bases)):
                raise ValueError("decision supersedes list must be unique and sorted")
            if payload.get("proposal_id") is None:
                if bases or any(
                    _event_equal(existing["event_key"], event)
                    for existing in decisions.values()
                ):
                    raise ValueError("only the first decision may have no revision proposal")
                expected_generation = 0
            else:
                proposal_id = _nonempty(payload["proposal_id"], "proposal_id")
                if proposal_id not in proposals:
                    raise ValueError("decision references unknown revision proposal")
                if proposal_id not in resolutions or resolutions[proposal_id]["outcome"] != "ACCEPTED":
                    raise ValueError("decision requires an accepted revision proposal")
                if proposal_id in decision_proposals:
                    raise ValueError("accepted proposal already issued a decision")
                proposal = proposals[proposal_id]
                if not _event_equal(proposal["event_key"], event):
                    raise ValueError("decision event differs from its accepted proposal")
                if bases != proposal["base_decision_ids"]:
                    raise ValueError("decision does not supersede the proposal's exact base set")
                if not bases or any(base not in decisions for base in bases):
                    raise ValueError("decision supersedes an unknown base decision")
                if any(not _event_equal(decisions[base]["event_key"], event) for base in bases):
                    raise ValueError("decision supersedes a decision from another event")
                expected_generation = 1 + max(decisions[base]["generation"] for base in bases)
                decision_proposals.add(proposal_id)
            if payload.get("generation") != expected_generation:
                raise ValueError("decision generation does not match its supersession ancestry")
            decision_core = {
                key: value for key, value in payload.items()
                if key != "decision_digest"
            }
            if payload.get("decision_digest") != digest(decision_core):
                raise ValueError("authority decision digest mismatch")
            decisions[decision_id] = dict(payload)
        else:
            raise ValueError(f"unknown authority-lineage entry type: {entry_type}")

    if ledger.get("ledger_digest") != _ledger_digest(entries):
        raise ValueError("ledger digest does not match entry chain")


def _frontier_decisions(
    ledger: Mapping[str, Any], event_key: Mapping[str, Any]
) -> list[dict[str, Any]]:
    validate_ledger(ledger)
    event = _event_key(event_key)
    decisions = _decision_records(ledger)
    frontier = set(_frontier_ids(decisions, event))
    return [
        copy.deepcopy(decision)
        for decision in decisions
        if decision["decision_id"] in frontier
        and _event_equal(decision["event_key"], event)
    ]


def decision_frontier(
    ledger: Mapping[str, Any],
    event_key: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the un-superseded branch tips; multiple tips are intentionally ambiguous."""
    frontier = _frontier_decisions(ledger, event_key)
    ids = [item["decision_id"] for item in frontier]
    return {
        "event_key": _event_key(event_key),
        "status": (
            "NO_DECISION" if not ids
            else "SINGLE_DECISION" if len(ids) == 1
            else "AMBIGUOUS_FRONTIER"
        ),
        "decision_ids": ids,
        "decisions": frontier,
    }


def event_entries(
    ledger: Mapping[str, Any],
    event_key: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return proposals, their resolutions, and decisions for one event in append order."""
    validate_ledger(ledger)
    event = _event_key(event_key)
    proposal_events = {
        entry["payload"]["proposal_id"]: entry["payload"]["event_key"]
        for entry in _entries_of_type(ledger, "revision_proposed")
    }
    selected = []
    for entry in ledger["entries"]:
        payload = entry["payload"]
        payload_event = payload.get("event_key")
        if entry["entry_type"] == "proposal_resolved":
            payload_event = proposal_events[payload["proposal_id"]]
        if isinstance(payload_event, Mapping) and _event_equal(payload_event, event):
            selected.append(copy.deepcopy(dict(entry)))
    return selected
