"""Append-only hypothesis expansion ledger for model-mismatch learning.

An observation outside a policy's predicted branches is evidence that the
current model may be incomplete. It is not automatically a new hypothesis or
proof of a particular explanation.

This ledger records candidate hypotheses with their originating observation
path and interpretation, keeps them in a proposed state, and only adds them
to a new active hypothesis-set revision after an explicit validation receipt.
Previous revisions are retained unchanged.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


_VALIDATION_RESULTS = {"supported", "rejected", "inconclusive"}


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest_hypotheses(hypotheses: Sequence["HypothesisDefinition"]) -> str:
    document = [
        {"hypothesis_id": item.hypothesis_id, "description": item.description}
        for item in sorted(hypotheses, key=lambda item: item.hypothesis_id)
    ]
    raw = _canonical_json(document).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class HypothesisDefinition:
    hypothesis_id: str
    description: str

    def __post_init__(self) -> None:
        _nonempty(self.hypothesis_id, "hypothesis_id")
        _nonempty(self.description, "description")


@dataclass(frozen=True)
class HypothesisCandidate:
    hypothesis_id: str
    description: str
    source_attempt_id: str
    encounter_ref: str
    interpretation_ref: str
    proposal_method: str
    source_payload_digest: Optional[str] = None
    source_canonicalization: Optional[str] = None
    validation_result: Optional[str] = None
    validation_ref: Optional[str] = None
    validator: Optional[str] = None


@dataclass(frozen=True)
class HypothesisSetRevision:
    revision_id: str
    parent_revision_id: Optional[str]
    hypotheses: Tuple[HypothesisDefinition, ...]
    hypothesis_set_digest: str


@dataclass(frozen=True)
class RevisionEvent:
    event_id: str
    event_type: str
    actor: str
    details_json: str

    @property
    def details(self) -> Dict[str, Any]:
        return json.loads(self.details_json)


class HypothesisRevisionLedger:
    """Maintain immutable hypothesis-set revisions and append-only evidence events."""

    def __init__(
        self,
        initial_hypotheses: Sequence[HypothesisDefinition],
        *,
        initial_revision_id: str = "revision-0001",
        author: str = "ledger",
    ) -> None:
        _nonempty(initial_revision_id, "initial_revision_id")
        _nonempty(author, "author")
        initial = tuple(initial_hypotheses)
        if not initial:
            raise ValueError("initial_hypotheses must contain at least one hypothesis")
        if any(not isinstance(item, HypothesisDefinition) for item in initial):
            raise TypeError("initial_hypotheses must contain HypothesisDefinition values")
        ids = [item.hypothesis_id for item in initial]
        if len(set(ids)) != len(ids):
            raise ValueError("initial hypothesis IDs must be unique")

        revision = HypothesisSetRevision(
            revision_id=initial_revision_id,
            parent_revision_id=None,
            hypotheses=initial,
            hypothesis_set_digest=_digest_hypotheses(initial),
        )
        self._revisions: List[HypothesisSetRevision] = [revision]
        self._current = revision
        self._candidates: Dict[str, HypothesisCandidate] = {}
        self._events: List[RevisionEvent] = []
        self._next_event_number = 1
        self._append_event(
            "revision_created",
            author,
            {
                "revision_id": revision.revision_id,
                "parent_revision_id": None,
                "hypothesis_ids": list(ids),
                "hypothesis_set_digest": revision.hypothesis_set_digest,
            },
        )

    @property
    def current_revision(self) -> HypothesisSetRevision:
        return self._current

    @property
    def revisions(self) -> Tuple[HypothesisSetRevision, ...]:
        return tuple(self._revisions)

    @property
    def candidates(self) -> Tuple[HypothesisCandidate, ...]:
        return tuple(self._candidates.values())

    @property
    def events(self) -> Tuple[RevisionEvent, ...]:
        return tuple(self._events)

    def _append_event(
        self, event_type: str, actor: str, details: Mapping[str, Any]
    ) -> RevisionEvent:
        event = RevisionEvent(
            event_id=f"event-{self._next_event_number:06d}",
            event_type=event_type,
            actor=_nonempty(actor, "actor"),
            details_json=_canonical_json(dict(details)),
        )
        self._events.append(event)
        self._next_event_number += 1
        return event

    def propose(
        self,
        hypothesis_id: str,
        description: str,
        *,
        source_attempt_id: str,
        encounter_ref: str,
        interpretation_ref: str,
        proposal_method: str,
        proposer: str,
        source_payload_digest: Optional[str] = None,
        source_canonicalization: Optional[str] = None,
    ) -> HypothesisCandidate:
        """Record a candidate; it remains proposed and does not enter the active set."""
        hypothesis_id = _nonempty(hypothesis_id, "hypothesis_id")
        description = _nonempty(description, "description")
        source_attempt_id = _nonempty(source_attempt_id, "source_attempt_id")
        encounter_ref = _nonempty(encounter_ref, "encounter_ref")
        interpretation_ref = _nonempty(interpretation_ref, "interpretation_ref")
        proposal_method = _nonempty(proposal_method, "proposal_method")
        proposer = _nonempty(proposer, "proposer")
        if source_payload_digest is not None:
            source_payload_digest = _nonempty(source_payload_digest, "source_payload_digest")
        if source_canonicalization is not None:
            source_canonicalization = _nonempty(source_canonicalization, "source_canonicalization")

        active_ids = {item.hypothesis_id for item in self._current.hypotheses}
        if hypothesis_id in active_ids or hypothesis_id in self._candidates:
            raise ValueError(f"hypothesis ID already exists: {hypothesis_id}")

        candidate = HypothesisCandidate(
            hypothesis_id=hypothesis_id,
            description=description,
            source_attempt_id=source_attempt_id,
            encounter_ref=encounter_ref,
            interpretation_ref=interpretation_ref,
            proposal_method=proposal_method,
            source_payload_digest=source_payload_digest,
            source_canonicalization=source_canonicalization,
        )
        self._candidates[hypothesis_id] = candidate
        self._append_event(
            "hypothesis_proposed",
            proposer,
            {
                "hypothesis_id": hypothesis_id,
                "description": description,
                "source_attempt_id": source_attempt_id,
                "encounter_ref": encounter_ref,
                "interpretation_ref": interpretation_ref,
                "proposal_method": proposal_method,
                "source_payload_digest": source_payload_digest,
                "source_canonicalization": source_canonicalization,
                "status": "proposed",
                "based_on_revision": self._current.revision_id,
                "based_on_hypothesis_set_digest": self._current.hypothesis_set_digest,
            },
        )
        return candidate

    def propose_from_unresolved_attempt(
        self,
        attempt: Mapping[str, Any],
        hypothesis_id: str,
        description: str,
        *,
        proposal_method: str,
        proposer: str,
    ) -> HypothesisCandidate:
        """Create a proposal directly from an unresolved model-mismatch attempt.

        The attempt must contain returned, interpreted, and unresolved events;
        its terminal reason must be the coordinator's unpredicted-branch reason.
        Ordinary rejection, timeout, dispatch failure, and interpreter failure
        are not accepted as model-mismatch evidence.
        """
        if not isinstance(attempt, Mapping):
            raise TypeError("attempt must be an observation-path mapping")
        attempt_id = _nonempty(attempt.get("attempt_id"), "attempt.attempt_id")
        if attempt.get("status") != "unresolved":
            raise ValueError("source attempt must terminate as unresolved")

        events = attempt.get("events")
        if not isinstance(events, (list, tuple)) or any(not isinstance(event, Mapping) for event in events):
            raise ValueError("source attempt must contain a sequence of event mappings")
        stages = [event.get("stage") for event in events]
        required_stages = ("dispatched", "admitted", "returned", "interpreted", "unresolved")
        positions = []
        for stage in required_stages:
            try:
                positions.append(stages.index(stage))
            except ValueError as exc:
                raise ValueError(f"model-mismatch source is missing required stage: {stage}") from exc
        if positions != sorted(positions):
            raise ValueError("model-mismatch evidence stages must appear in lifecycle order")

        returned = events[positions[2]]
        interpreted = events[positions[3]]
        unresolved = events[positions[4]]
        returned_details = returned.get("details")
        unresolved_details = unresolved.get("details")
        if not isinstance(returned_details, Mapping) or not isinstance(unresolved_details, Mapping):
            raise ValueError("returned and unresolved events must contain details objects")
        reason = unresolved_details.get("reason")
        if reason != "interpreted observation value was not predicted by the policy":
            raise ValueError("source attempt is unresolved for a reason other than policy model mismatch")

        encounter_ref = _nonempty(returned.get("evidence_ref"), "returned.evidence_ref")
        interpretation_ref = _nonempty(interpreted.get("evidence_ref"), "interpreted.evidence_ref")
        payload_digest = _nonempty(returned_details.get("payload_digest"), "returned.payload_digest")
        canonicalization = _nonempty(returned_details.get("canonicalization"), "returned.canonicalization")

        return self.propose(
            hypothesis_id,
            description,
            source_attempt_id=attempt_id,
            encounter_ref=encounter_ref,
            interpretation_ref=interpretation_ref,
            proposal_method=proposal_method,
            proposer=proposer,
            source_payload_digest=payload_digest,
            source_canonicalization=canonicalization,
        )

    def validate_candidate(
        self,
        hypothesis_id: str,
        result: str,
        *,
        validation_ref: str,
        validator: str,
    ) -> HypothesisCandidate:
        """Record an explicit validation outcome; no outcome is inferred from proposal."""
        hypothesis_id = _nonempty(hypothesis_id, "hypothesis_id")
        validation_ref = _nonempty(validation_ref, "validation_ref")
        validator = _nonempty(validator, "validator")
        if not isinstance(result, str) or result not in _VALIDATION_RESULTS:
            raise ValueError(f"result must be one of {sorted(_VALIDATION_RESULTS)}")
        candidate = self._candidates.get(hypothesis_id)
        if candidate is None:
            raise KeyError(hypothesis_id)
        if candidate.validation_result is not None:
            raise ValueError(f"candidate already has a validation result: {hypothesis_id}")

        updated = HypothesisCandidate(
            hypothesis_id=candidate.hypothesis_id,
            description=candidate.description,
            source_attempt_id=candidate.source_attempt_id,
            encounter_ref=candidate.encounter_ref,
            interpretation_ref=candidate.interpretation_ref,
            proposal_method=candidate.proposal_method,
            source_payload_digest=candidate.source_payload_digest,
            source_canonicalization=candidate.source_canonicalization,
            validation_result=result,
            validation_ref=validation_ref,
            validator=validator,
        )
        self._candidates[hypothesis_id] = updated
        self._append_event(
            "hypothesis_validated",
            validator,
            {
                "hypothesis_id": hypothesis_id,
                "result": result,
                "validation_ref": validation_ref,
                "source_attempt_id": candidate.source_attempt_id,
                "encounter_ref": candidate.encounter_ref,
            },
        )
        return updated

    def activate_supported(
        self,
        *,
        revision_id: str,
        actor: str,
    ) -> HypothesisSetRevision:
        """Create a new revision containing prior hypotheses plus supported candidates."""
        revision_id = _nonempty(revision_id, "revision_id")
        actor = _nonempty(actor, "actor")
        if any(item.revision_id == revision_id for item in self._revisions):
            raise ValueError(f"revision ID already exists: {revision_id}")

        active_ids = {item.hypothesis_id for item in self._current.hypotheses}
        supported = [
            candidate
            for candidate in self._candidates.values()
            if candidate.validation_result == "supported"
            and candidate.hypothesis_id not in active_ids
        ]
        if not supported:
            raise ValueError("no validated supported hypotheses are available to activate")

        new_hypotheses = list(self._current.hypotheses)
        new_hypotheses.extend(
            HypothesisDefinition(candidate.hypothesis_id, candidate.description)
            for candidate in supported
        )
        new_revision = HypothesisSetRevision(
            revision_id=revision_id,
            parent_revision_id=self._current.revision_id,
            hypotheses=tuple(new_hypotheses),
            hypothesis_set_digest=_digest_hypotheses(new_hypotheses),
        )
        self._revisions.append(new_revision)
        self._current = new_revision
        self._append_event(
            "revision_activated",
            actor,
            {
                "revision_id": new_revision.revision_id,
                "parent_revision_id": new_revision.parent_revision_id,
                "added_hypothesis_ids": [candidate.hypothesis_id for candidate in supported],
                "retained_parent_hypothesis_ids": [
                    item.hypothesis_id for item in new_revision.hypotheses
                    if item.hypothesis_id not in {candidate.hypothesis_id for candidate in supported}
                ],
                "hypothesis_set_digest": new_revision.hypothesis_set_digest,
            },
        )
        return new_revision

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_revision_id": self._current.revision_id,
            "revisions": [
                {
                    "revision_id": item.revision_id,
                    "parent_revision_id": item.parent_revision_id,
                    "hypotheses": [
                        {"hypothesis_id": h.hypothesis_id, "description": h.description}
                        for h in item.hypotheses
                    ],
                    "hypothesis_set_digest": item.hypothesis_set_digest,
                }
                for item in self._revisions
            ],
            "candidates": [
                {
                    "hypothesis_id": candidate.hypothesis_id,
                    "description": candidate.description,
                    "source_attempt_id": candidate.source_attempt_id,
                    "encounter_ref": candidate.encounter_ref,
                    "interpretation_ref": candidate.interpretation_ref,
                    "proposal_method": candidate.proposal_method,
                    "source_payload_digest": candidate.source_payload_digest,
                    "source_canonicalization": candidate.source_canonicalization,
                    "validation_result": candidate.validation_result,
                    "validation_ref": candidate.validation_ref,
                    "validator": candidate.validator,
                }
                for candidate in self._candidates.values()
            ],
            "events": [
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "actor": event.actor,
                    "details": event.details,
                }
                for event in self._events
            ],
        }
