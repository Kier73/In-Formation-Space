"""Deterministic review certificates bound to append-only authority proposals.

Certificates preserve the exact proposal/base/policy/vote computation and can
be recorded in the authority-lineage ledger. Reviewer references are labels,
not authenticated identities; hashes provide integrity, not signatures.
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from authority_lineage import (
    _append_entry,
    _event_equal,
    _nonempty,
    _sha256,
    current_frontier,
    digest,
    resolve_proposal,
    validate_ledger,
)

_POLICY_DIR = Path(__file__).resolve().parents[2] / "experiments" / "authority-adjudication-space"
if str(_POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(_POLICY_DIR))

from review_policy_space import (  # noqa: E402
    POLICIES,
    PROPOSER,
    REVIEWERS,
    REVIEW_STATES,
    evaluate_review_policy,
)

FORMAT = "in-formation.authority-review-certificate"
SCHEMA = "in-formation.authority-review-certificate/0.1"
EVALUATOR = "in-formation.authority-review-evaluator/0.1"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_VOTE_STATES = {"APPROVE", "REJECT", "ABSTAIN"}
_CERTIFICATE_FIELDS = {
    "format",
    "schema",
    "certificate_id",
    "ledger_id",
    "proposal_id",
    "proposal_digest",
    "event_key",
    "base_decision_ids",
    "base_decision_digests",
    "policy_snapshot",
    "policy_digest",
    "reviewer_seats",
    "proposer_seat",
    "evaluator",
    "votes",
    "evaluation",
    "certificate_digest",
}
_VOTE_FIELDS = {
    "seat",
    "reviewer_ref",
    "vote",
    "rationale",
    "review_ref",
    "review_sha256",
}


class ReviewCertificateError(ValueError):
    """A review certificate is malformed, unbound, or inconsistent."""


def _proposal_entry(ledger: Mapping[str, Any], proposal_id: str) -> dict[str, Any]:
    matches = [
        entry for entry in ledger["entries"]
        if entry["entry_type"] == "revision_proposed"
        and entry["payload"]["proposal_id"] == proposal_id
    ]
    if not matches:
        raise KeyError(proposal_id)
    if len(matches) != 1:
        raise ReviewCertificateError("proposal identifier is not unique")
    return matches[0]


def _certificate_entries(ledger: Mapping[str, Any], proposal_id: str) -> list[dict[str, Any]]:
    return [
        entry for entry in ledger["entries"]
        if entry["entry_type"] == "proposal_review_certified"
        and entry["payload"]["proposal_id"] == proposal_id
    ]


def _resolution_entries(ledger: Mapping[str, Any], proposal_id: str) -> list[dict[str, Any]]:
    return [
        entry for entry in ledger["entries"]
        if entry["entry_type"] == "proposal_resolved"
        and entry["payload"]["proposal_id"] == proposal_id
    ]


def _policy_snapshot(policy_name: str) -> dict[str, Any]:
    if policy_name not in POLICIES:
        raise ReviewCertificateError(f"unknown review policy: {policy_name}")
    return {
        "policy_id": policy_name,
        "definition": copy.deepcopy(POLICIES[policy_name]),
        "reviewer_seats": list(REVIEWERS),
        "proposer_seat": PROPOSER,
        "evaluator": EVALUATOR,
    }


def _normalize_votes(
    proposal_actor: str,
    votes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(votes, (list, tuple)):
        raise TypeError("votes must be a sequence")
    normalized = []
    seen_seats: set[str] = set()
    seen_reviewers: set[str] = set()
    seen_artifacts: set[str] = set()
    for index, vote in enumerate(votes):
        if not isinstance(vote, Mapping) or set(vote) != _VOTE_FIELDS:
            raise ReviewCertificateError(f"votes[{index}] has missing or unrecognized fields")
        seat = _nonempty(vote.get("seat"), f"votes[{index}].seat")
        if seat not in REVIEWERS:
            raise ReviewCertificateError(f"votes[{index}] names an unknown reviewer seat")
        if seat in seen_seats:
            raise ReviewCertificateError(f"reviewer seat {seat} supplied more than one vote")
        reviewer_ref = _nonempty(vote.get("reviewer_ref"), f"votes[{index}].reviewer_ref")
        if reviewer_ref in seen_reviewers:
            raise ReviewCertificateError("reviewer references must be distinct across seats")
        if seat == PROPOSER and reviewer_ref != proposal_actor:
            raise ReviewCertificateError("proposer-seat reviewer_ref must match the proposal actor")
        if seat != PROPOSER and reviewer_ref == proposal_actor:
            raise ReviewCertificateError("independent reviewer seat cannot reuse the proposer reference")
        stance = vote.get("vote")
        if stance not in _VOTE_STATES:
            raise ReviewCertificateError("vote must be APPROVE, REJECT, or ABSTAIN")
        rationale = _nonempty(vote.get("rationale"), f"votes[{index}].rationale")
        review_ref = _nonempty(vote.get("review_ref"), f"votes[{index}].review_ref")
        if review_ref in seen_artifacts:
            raise ReviewCertificateError("review artifact references must be unique")
        review_sha256 = _sha256(vote.get("review_sha256"), f"votes[{index}].review_sha256")
        normalized.append({
            "seat": seat,
            "reviewer_ref": reviewer_ref,
            "vote": stance,
            "rationale": rationale,
            "review_ref": review_ref,
            "review_sha256": review_sha256,
        })
        seen_seats.add(seat)
        seen_reviewers.add(reviewer_ref)
        seen_artifacts.add(review_ref)
    return sorted(normalized, key=lambda item: REVIEWERS.index(item["seat"]))


def _evaluation_from_votes(votes: Sequence[Mapping[str, Any]], policy_id: str) -> dict[str, Any]:
    states = {seat: "ABSENT" for seat in REVIEWERS}
    for item in votes:
        states[item["seat"]] = item["vote"]
    pattern = [states[seat] for seat in REVIEWERS]
    evaluation = evaluate_review_policy(policy_id, pattern)
    return {
        "outcome": evaluation["outcome"],
        "reason": evaluation["reason"],
        "eligible_reviewers": evaluation["eligible_reviewers"],
        "present_eligible_reviewers": evaluation["present_eligible_reviewers"],
        "approval_count": evaluation["approval_count"],
        "rejection_count": evaluation["rejection_count"],
        "abstention_count": evaluation["abstention_count"],
        "proposer_vote_counted": evaluation["proposer_vote_counted"],
        "conflicting_thresholds": evaluation["conflicting_thresholds"],
        "seat_pattern": pattern,
    }


def build_review_certificate(
    ledger: Mapping[str, Any],
    proposal_id: str,
    *,
    policy_name: str,
    votes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic certificate for one unresolved proposal.

    The current authority frontier must still equal the proposal's base.
    Missing seats are represented as ABSENT in the evaluator's seat pattern;
    they are not fabricated as reviewer receipts.
    """
    validate_ledger(ledger)
    proposal_id = _nonempty(proposal_id, "proposal_id")
    proposal_entry = _proposal_entry(ledger, proposal_id)
    proposal = proposal_entry["payload"]
    if _resolution_entries(ledger, proposal_id):
        raise ReviewCertificateError("cannot certify a proposal that is already resolved")
    if _certificate_entries(ledger, proposal_id):
        raise ReviewCertificateError("proposal already has a review certificate")
    frontier = current_frontier(ledger, proposal["event_key"])["decision_ids"]
    if frontier != proposal["base_decision_ids"]:
        raise ReviewCertificateError("proposal is stale; its cited authority frontier has changed")

    policy_snapshot = _policy_snapshot(policy_name)
    normalized_votes = _normalize_votes(proposal_entry["actor"], votes)
    decision_map = {
        entry["payload"]["decision_id"]: entry["payload"]
        for entry in ledger["entries"]
        if entry["entry_type"] == "decision_issued"
    }
    base_decision_digests = {
        decision_id: decision_map[decision_id]["decision_digest"]
        for decision_id in proposal["base_decision_ids"]
    }
    policy_digest = digest(policy_snapshot)
    core = {
        "format": FORMAT,
        "schema": SCHEMA,
        "certificate_id": f"review-certificate:{proposal_id}",
        "ledger_id": ledger["ledger_id"],
        "proposal_id": proposal_id,
        "proposal_digest": digest(proposal),
        "event_key": copy.deepcopy(proposal["event_key"]),
        "base_decision_ids": list(proposal["base_decision_ids"]),
        "base_decision_digests": base_decision_digests,
        "policy_snapshot": policy_snapshot,
        "policy_digest": policy_digest,
        "reviewer_seats": list(REVIEWERS),
        "proposer_seat": PROPOSER,
        "evaluator": EVALUATOR,
        "votes": normalized_votes,
        "evaluation": _evaluation_from_votes(normalized_votes, policy_name),
    }
    return {**core, "certificate_digest": digest(core)}


def validate_review_certificate(
    ledger: Mapping[str, Any],
    certificate: Mapping[str, Any],
    *,
    allow_recorded: bool = False,
) -> None:
    """Independently reconstruct the certificate's binding and policy result."""
    validate_ledger(ledger)
    if not isinstance(certificate, Mapping) or set(certificate) != _CERTIFICATE_FIELDS:
        raise ReviewCertificateError("certificate has missing or unrecognized fields")
    cert = dict(certificate)
    if cert["format"] != FORMAT or cert["schema"] != SCHEMA:
        raise ReviewCertificateError("unsupported review certificate format or schema")
    certificate_id = _nonempty(cert["certificate_id"], "certificate_id")
    proposal_id = _nonempty(cert["proposal_id"], "proposal_id")
    if certificate_id != f"review-certificate:{proposal_id}":
        raise ReviewCertificateError("certificate_id does not bind the proposal")
    if cert["ledger_id"] != ledger["ledger_id"]:
        raise ReviewCertificateError("certificate belongs to a different ledger")
    proposal_entry = _proposal_entry(ledger, proposal_id)
    proposal = proposal_entry["payload"]
    if cert["proposal_digest"] != digest(proposal):
        raise ReviewCertificateError("certificate proposal digest does not match the ledger")
    if cert["event_key"] != proposal["event_key"]:
        raise ReviewCertificateError("certificate event key differs from its proposal")
    if cert["base_decision_ids"] != proposal["base_decision_ids"]:
        raise ReviewCertificateError("certificate base decisions differ from its proposal")

    decision_map = {
        entry["payload"]["decision_id"]: entry["payload"]
        for entry in ledger["entries"]
        if entry["entry_type"] == "decision_issued"
    }
    expected_base_digests = {
        decision_id: decision_map[decision_id]["decision_digest"]
        for decision_id in proposal["base_decision_ids"]
    }
    if cert["base_decision_digests"] != expected_base_digests:
        raise ReviewCertificateError("certificate base decision digests do not match the ledger")

    policy_id = cert["policy_snapshot"].get("policy_id") if isinstance(cert["policy_snapshot"], Mapping) else None
    expected_snapshot = _policy_snapshot(policy_id) if isinstance(policy_id, str) else None
    if cert["policy_snapshot"] != expected_snapshot:
        raise ReviewCertificateError("certificate policy snapshot is not a recognized policy definition")
    if cert["policy_digest"] != digest(expected_snapshot):
        raise ReviewCertificateError("certificate policy digest mismatch")
    if cert["reviewer_seats"] != list(REVIEWERS) or cert["proposer_seat"] != PROPOSER:
        raise ReviewCertificateError("certificate reviewer roster does not match the evaluator profile")
    if cert["evaluator"] != EVALUATOR:
        raise ReviewCertificateError("certificate names an unsupported evaluator contract")

    normalized_votes = _normalize_votes(proposal_entry["actor"], cert["votes"])
    if cert["votes"] != normalized_votes:
        raise ReviewCertificateError("certificate votes are not normalized in seat order")
    expected_evaluation = _evaluation_from_votes(normalized_votes, policy_id)
    if cert["evaluation"] != expected_evaluation:
        raise ReviewCertificateError("certificate outcome does not reconstruct from its votes")

    supplied_digest = cert["certificate_digest"]
    _sha256(supplied_digest, "certificate_digest")
    digest_core = {key: value for key, value in cert.items() if key != "certificate_digest"}
    if supplied_digest != digest(digest_core):
        raise ReviewCertificateError("review certificate digest mismatch")

    existing = _certificate_entries(ledger, proposal_id)
    if allow_recorded:
        if len(existing) != 1:
            raise ReviewCertificateError("recorded review certificate is missing or duplicated")
        payload = existing[0]["payload"]
        if payload["certificate_digest"] != supplied_digest or payload["certificate"] != cert:
            raise ReviewCertificateError("ledger review certificate differs from the supplied certificate")
    elif existing:
        raise ReviewCertificateError("proposal already has a recorded review certificate")
    elif _resolution_entries(ledger, proposal_id):
        raise ReviewCertificateError("cannot record a certificate after proposal resolution")


def record_review_certificate(
    ledger: Mapping[str, Any],
    certificate: Mapping[str, Any],
    *,
    recorded_by: str,
) -> dict[str, Any]:
    """Append the complete certificate before proposal resolution."""
    validate_review_certificate(ledger, certificate)
    payload = {
        "proposal_id": certificate["proposal_id"],
        "event_key": copy.deepcopy(certificate["event_key"]),
        "certificate_id": certificate["certificate_id"],
        "certificate_digest": certificate["certificate_digest"],
        "certificate": copy.deepcopy(dict(certificate)),
    }
    updated = _append_entry(
        ledger,
        "proposal_review_certified",
        _nonempty(recorded_by, "recorded_by"),
        payload,
    )
    validate_review_certificates_in_ledger(updated)
    return updated


def validate_review_certificates_in_ledger(ledger: Mapping[str, Any]) -> None:
    """Validate each embedded certificate against its proposal and vote policy."""
    validate_ledger(ledger)
    for entry in ledger["entries"]:
        if entry["entry_type"] == "proposal_review_certified":
            payload = entry["payload"]
            validate_review_certificate(
                ledger,
                payload["certificate"],
                allow_recorded=True,
            )


def resolve_reviewed_proposal(
    ledger: Mapping[str, Any],
    proposal_id: str,
    *,
    rationale: str,
    resolved_by: str,
) -> dict[str, Any]:
    """Resolve using the recorded certificate; stale certificates resolve STALE."""
    validate_review_certificates_in_ledger(ledger)
    matches = _certificate_entries(ledger, proposal_id)
    if len(matches) != 1:
        raise ReviewCertificateError("proposal must have exactly one recorded review certificate")
    certificate = matches[0]["payload"]["certificate"]
    frontier = current_frontier(ledger, certificate["event_key"])["decision_ids"]
    if frontier != certificate["base_decision_ids"]:
        outcome = "STALE"
    else:
        outcome = certificate["evaluation"]["outcome"]
    return resolve_proposal(
        ledger,
        proposal_id,
        outcome=outcome,
        rationale=rationale,
        resolved_by=resolved_by,
    )
