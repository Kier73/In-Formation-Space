"""Adapter from evidence-gated observation records to authority lineage.

The adapter checks the shape and cross-record identity of supplied evidence.
It does not fetch evidence references, authenticate sources, or decide whether
the authority outcome is correct. Those remain independent verification steps.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from authority_lineage import (
    create_ledger,
    decision_frontier,
    digest,
    issue_decision,
    propose_revision,
    validate_ledger,
)


class ObservationEvidenceError(ValueError):
    """Supplied observation/evidence records violate the bridge contract."""


class DuplicateObservationEvidenceError(ObservationEvidenceError):
    """The proposed late evidence is an exact replay, not a new observation."""


class SourceEquivocationError(ObservationEvidenceError):
    """A source identity is reused for the event with a different payload digest."""


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservationEvidenceError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ObservationEvidenceError(f"{label} must be a lowercase SHA-256 digest")
    if any(char not in "0123456789abcdef" for char in value):
        raise ObservationEvidenceError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _event_key(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"kind", "logical_time"}:
        raise ObservationEvidenceError("evidence event must contain kind and logical_time")
    kind = _nonempty(value.get("kind"), "event.kind")
    logical_time = value.get("logical_time")
    if isinstance(logical_time, bool) or not isinstance(logical_time, int) or logical_time < 0:
        raise ObservationEvidenceError("event.logical_time must be a non-negative integer")
    return {"kind": kind, "logical_time": logical_time}


def _normalize_evidence_record(
    record: Mapping[str, Any],
    *,
    expected_event: Mapping[str, Any] | None = None,
    expected_attempt_id: str | None = None,
    expected_observation_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise TypeError("evidence record must be a mapping")
    event = _event_key(record.get("event"))
    if expected_event is not None and event != dict(expected_event):
        raise ObservationEvidenceError("evidence record belongs to a different logical event")
    attempt_id = _nonempty(record.get("attempt_id"), "evidence.attempt_id")
    observation_id = _nonempty(record.get("observation_id"), "evidence.observation_id")
    if expected_attempt_id is not None and attempt_id != expected_attempt_id:
        raise ObservationEvidenceError("evidence record belongs to a different attempt")
    if expected_observation_id is not None and observation_id != expected_observation_id:
        raise ObservationEvidenceError("evidence record belongs to a different observation")
    source = _nonempty(record.get("source"), "evidence.source")
    channel = _nonempty(record.get("channel"), "evidence.channel")
    sequence = record.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ObservationEvidenceError("evidence.sequence must be a positive integer")
    payload_digest = _sha256(record.get("payload_digest"), "evidence.payload_digest")
    return {
        "attempt_id": attempt_id,
        "observation_id": observation_id,
        "event": event,
        "source": source,
        "channel": channel,
        "sequence": sequence,
        "payload_digest": payload_digest,
    }


def _record_ref(record: Mapping[str, Any]) -> str:
    return (
        "evidence-record://"
        + record["attempt_id"]
        + "/"
        + record["observation_id"]
        + "/"
        + record["source"]
        + "/"
        + record["payload_digest"]
    )


def _evidence_set_digest(records: Sequence[Mapping[str, Any]]) -> str:
    canonical_records = sorted(
        (
            {
                "event": item["event"],
                "observation_id": item["observation_id"],
                "source": item["source"],
                "channel": item["channel"],
                "sequence": item["sequence"],
                "payload_digest": item["payload_digest"],
            }
            for item in records
        ),
        key=lambda item: (
            item["source"], item["channel"], item["sequence"], item["payload_digest"]
        ),
    )
    return digest(canonical_records)


def issue_initial_decision_from_attempt(
    ledger: Mapping[str, Any],
    attempt: Mapping[str, Any],
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    policy_digest: str,
    issued_by: str,
    rationale: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Create an initial authority decision from a finalized attempt and its evidence.

    Evidence source identities and event coordinates must match the attempt's
    declared evidence partition exactly. The attempt's status determines
    whether the decision may name a representative, but does not authenticate
    the attempt or its supplied policy.
    """
    validate_ledger(ledger)
    if not isinstance(attempt, Mapping):
        raise TypeError("attempt must be a mapping")
    attempt_id = _nonempty(attempt.get("attempt_id"), "attempt.attempt_id")
    observation_id = _nonempty(attempt.get("observation_id"), "attempt.observation_id")
    status = attempt.get("final_status")
    if status not in {"AUTHORIZED", "CONFLICT", "REFUSED"}:
        raise ObservationEvidenceError("attempt.final_status is not a finalized authority status")
    expected_sources = attempt.get("evidence_received_sources")
    if not isinstance(expected_sources, list) or not all(
        isinstance(source, str) and source for source in expected_sources
    ):
        raise ObservationEvidenceError("attempt.evidence_received_sources must be a source list")
    if expected_sources != sorted(set(expected_sources)):
        raise ObservationEvidenceError("attempt evidence source list must be sorted and unique")
    if not isinstance(evidence_records, (list, tuple)):
        raise TypeError("evidence_records must be a sequence")
    normalized = [
        _normalize_evidence_record(
            record,
            expected_attempt_id=attempt_id,
            expected_observation_id=observation_id,
        )
        for record in evidence_records
    ]
    if not normalized:
        raise ObservationEvidenceError("a finalized attempt must retain at least one evidence record")
    if len({item["source"] for item in normalized}) != len(normalized):
        raise ObservationEvidenceError("attempt evidence has more than one record for a source")
    actual_sources = sorted(item["source"] for item in normalized)
    if actual_sources != expected_sources:
        raise ObservationEvidenceError("evidence ledger sources differ from the attempt partition")
    if attempt.get("evidence_received_count") != len(normalized):
        raise ObservationEvidenceError("attempt evidence count differs from retained evidence records")
    event_keys = {json.dumps(item["event"], sort_keys=True) for item in normalized}
    if len(event_keys) != 1:
        raise ObservationEvidenceError("evidence ledger contains multiple logical events")
    event = normalized[0]["event"]
    partition = attempt.get("evidence_partition")
    if not isinstance(partition, Mapping):
        raise ObservationEvidenceError("attempt lacks its reconstructed evidence partition")
    if partition.get("observed_sources") != expected_sources:
        raise ObservationEvidenceError("attempt evidence partition has inconsistent source identities")

    representative_ref = None
    representative_source = attempt.get("representative_source")
    if status == "AUTHORIZED":
        if not isinstance(representative_source, str) or representative_source not in expected_sources:
            raise ObservationEvidenceError("authorized attempt lacks a representative in its evidence set")
        representative = next(item for item in normalized if item["source"] == representative_source)
        representative_ref = _record_ref(representative)
    elif representative_source is not None:
        raise ObservationEvidenceError("non-authorized attempt must not select a representative")

    evidence_digest = _evidence_set_digest(normalized)
    updated, decision_id = issue_decision(
        ledger,
        event_key=event,
        status=status,
        evidence_set_digest=evidence_digest,
        policy_digest=_sha256(policy_digest, "policy_digest"),
        issued_by=issued_by,
        rationale=rationale,
        representative_ref=representative_ref,
    )
    receipt = {
        "attempt_id": attempt_id,
        "observation_id": observation_id,
        "event_key": event,
        "decision_id": decision_id,
        "decision_status": status,
        "evidence_sources": actual_sources,
        "evidence_record_count": len(normalized),
        "evidence_set_digest": evidence_digest,
        "representative_source": representative_source,
        "representative_ref": representative_ref,
    }
    receipt["receipt_digest"] = digest(receipt)
    return updated, decision_id, receipt


def propose_revision_from_new_evidence(
    ledger: Mapping[str, Any],
    *,
    event_key: Mapping[str, Any],
    base_decision_ids: Sequence[str],
    known_evidence_records: Sequence[Mapping[str, Any]],
    new_evidence_records: Sequence[Mapping[str, Any]],
    reason: str,
    proposed_by: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Turn genuinely new source evidence into a review proposal.

    An exact replay from an already represented source is rejected as a
    duplicate. A changed payload from an already represented source raises
    SourceEquivocationError. Neither is mislabeled as an ordinary late source.
    """
    validate_ledger(ledger)
    event = _event_key(event_key)
    if not isinstance(known_evidence_records, (list, tuple)):
        raise TypeError("known_evidence_records must be a sequence")
    if not isinstance(new_evidence_records, (list, tuple)) or not new_evidence_records:
        raise ValueError("new_evidence_records must be a non-empty sequence")
    known = [
        _normalize_evidence_record(item, expected_event=event)
        for item in known_evidence_records
    ]
    new = [
        _normalize_evidence_record(item, expected_event=event)
        for item in new_evidence_records
    ]
    known_by_source: dict[str, dict[str, Any]] = {}
    for item in known:
        previous = known_by_source.get(item["source"])
        if previous is not None:
            if previous["payload_digest"] != item["payload_digest"]:
                raise SourceEquivocationError(
                    f"known evidence already contains contradictory records for {item['source']}"
                )
            raise DuplicateObservationEvidenceError(
                f"known evidence repeats a source record: {item['source']}"
            )
        known_by_source[item["source"]] = item

    frontier = decision_frontier(ledger, event)
    if frontier["status"] != "SINGLE_DECISION":
        raise ObservationEvidenceError(
            "late evidence adapter requires a single current decision frontier; merge competing branches first"
        )
    frontier_ids = sorted(frontier["decision_ids"])
    proposed_bases = sorted(base_decision_ids)
    if frontier_ids != proposed_bases:
        raise ObservationEvidenceError(
            "revision base decision IDs differ from the complete current authority frontier"
        )
    known_digest = _evidence_set_digest(known)
    current_decision = frontier["decisions"][0]
    if known_digest != current_decision["evidence_set_digest"]:
        raise ObservationEvidenceError(
            "known evidence records do not reconstruct the current decision's evidence-set digest"
        )

    batch_by_source: dict[str, dict[str, Any]] = {}
    for item in new:
        previous = batch_by_source.get(item["source"])
        if previous is not None:
            if previous["payload_digest"] == item["payload_digest"]:
                raise DuplicateObservationEvidenceError(
                    f"late evidence repeats the same source payload: {item['source']}"
                )
            raise SourceEquivocationError(
                f"late evidence contains contradictory payloads from {item['source']}"
            )
        batch_by_source[item["source"]] = item
        existing = known_by_source.get(item["source"])
        if existing is not None:
            if existing["payload_digest"] == item["payload_digest"]:
                raise DuplicateObservationEvidenceError(
                    f"late evidence is an exact replay from {item['source']}"
                )
            raise SourceEquivocationError(
                f"source {item['source']} changed its payload for the same event"
            )

    refs = [
        {"ref": _record_ref(item), "sha256": item["payload_digest"]}
        for item in sorted(new, key=lambda item: item["source"])
    ]
    updated, proposal_id = propose_revision(
        ledger,
        event_key=event,
        base_decision_ids=base_decision_ids,
        evidence_refs=refs,
        reason=reason,
        proposed_by=proposed_by,
    )
    receipt_core = {
        "proposal_id": proposal_id,
        "event_key": event,
        "new_sources": sorted(item["source"] for item in new),
        "new_evidence_refs": refs,
        "new_evidence_count": len(new),
        "known_source_count": len(known_by_source),
        "proposal_reason": reason,
        "proposed_by": proposed_by,
    }
    receipt = {**receipt_core, "receipt_digest": digest(receipt_core)}
    return updated, proposal_id, receipt
