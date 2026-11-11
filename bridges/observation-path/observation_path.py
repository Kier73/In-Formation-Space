"""Evidence-gated lifecycle for a selected observation request.

The planner, transport, receiver, sensor, interpreter, and verifier are separate
actors. This path ledger prevents a planned or admitted request from being
misrepresented as a returned observation.

Every clock coordinate is kept with its clock-domain label. The ledger never
aligns or compares timestamps across domains. Raw returned data is referenced
through an Encounter Envelope; the ledger records that reference and digest but
does not fetch or authenticate the external artifact itself.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple


_ALLOWED_NEXT = {
    "planned": {"dispatched", "dispatch_failed"},
    "dispatched": {"admitted", "rejected", "dispatch_failed", "returned_unadmitted"},
    "admitted": {"returned", "no_result"},
    "returned": {"interpreted", "interpretation_failed"},
    "interpreted": {"continued", "query_determined", "unresolved"},
}
_TERMINAL = {
    "dispatch_failed",
    "rejected",
    "returned_unadmitted",
    "no_result",
    "interpretation_failed",
    "continued",
    "query_determined",
    "unresolved",
}
_EVIDENCE_REQUIRED = {
    "dispatched",
    "admitted",
    "returned",
    "returned_unadmitted",
    "interpreted",
    "query_determined",
}


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _json_snapshot(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("event details must be a JSON-compatible mapping")
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("event details must contain finite JSON-compatible values") from exc


@dataclass(frozen=True)
class ObservationIntent:
    attempt_id: str
    candidate_name: str
    query: str
    hypothesis_set_digest: str
    estimated_cost: float
    plan_ref: Optional[str] = None

    def __post_init__(self) -> None:
        _nonempty(self.attempt_id, "attempt_id")
        _nonempty(self.candidate_name, "candidate_name")
        _nonempty(self.query, "query")
        _nonempty(self.hypothesis_set_digest, "hypothesis_set_digest")
        if isinstance(self.estimated_cost, bool):
            raise ValueError("estimated_cost must be finite and positive")
        try:
            cost = float(self.estimated_cost)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("estimated_cost must be finite and positive") from exc
        if not math.isfinite(cost) or cost <= 0.0:
            raise ValueError("estimated_cost must be finite and positive")
        if self.plan_ref is not None:
            _nonempty(self.plan_ref, "plan_ref")


@dataclass(frozen=True)
class PathEvent:
    stage: str
    actor: str
    clock_value: Optional[str]
    clock_domain: Optional[str]
    evidence_ref: Optional[str]
    details_json: str

    @property
    def details(self) -> Dict[str, Any]:
        """Return a fresh copy so callers cannot mutate the recorded event."""
        return json.loads(self.details_json)


class ObservationPath:
    """Append-only lifecycle for one selected observation attempt."""

    def __init__(self, intent: ObservationIntent) -> None:
        if not isinstance(intent, ObservationIntent):
            raise TypeError("intent must be an ObservationIntent")
        self.intent = intent
        self._events: List[PathEvent] = [
            PathEvent(
                stage="planned",
                actor="planner",
                clock_value=None,
                clock_domain=None,
                evidence_ref=intent.plan_ref,
                details_json=_json_snapshot({
                    "attempt_id": intent.attempt_id,
                    "candidate_name": intent.candidate_name,
                    "query": intent.query,
                    "hypothesis_set_digest": intent.hypothesis_set_digest,
                    "estimated_cost": float(intent.estimated_cost),
                    "plan_ref": intent.plan_ref,
                }),
            )
        ]

    @property
    def events(self) -> Tuple[PathEvent, ...]:
        return tuple(self._events)

    @property
    def status(self) -> str:
        return self._events[-1].stage

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL

    def append(
        self,
        stage: str,
        actor: str,
        *,
        clock_value: Optional[str] = None,
        clock_domain: Optional[str] = None,
        evidence_ref: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> PathEvent:
        """Append one valid lifecycle event; prior events are never rewritten."""
        _nonempty(stage, "stage")
        _nonempty(actor, "actor")
        current = self.status
        allowed = _ALLOWED_NEXT.get(current, set())
        if stage not in allowed:
            raise ValueError(f"invalid observation-path transition: {current} -> {stage}")

        if clock_value is not None:
            _nonempty(clock_value, "clock_value")
            _nonempty(clock_domain, "clock_domain")
        elif clock_domain is not None:
            _nonempty(clock_domain, "clock_domain")

        if stage in _EVIDENCE_REQUIRED:
            _nonempty(evidence_ref, "evidence_ref")
        elif evidence_ref is not None:
            _nonempty(evidence_ref, "evidence_ref")

        detail_values = dict(details or {})
        if stage in {"returned", "returned_unadmitted"}:
            _nonempty(detail_values.get("encounter_id"), "details.encounter_id")
            _nonempty(detail_values.get("payload_digest"), "details.payload_digest")
            _nonempty(detail_values.get("canonicalization"), "details.canonicalization")
        elif stage == "query_determined":
            if not isinstance(detail_values.get("query_result"), bool):
                raise ValueError("query_determined requires boolean details.query_result")
            _nonempty(detail_values.get("hypothesis_set_digest"), "details.hypothesis_set_digest")
            _nonempty(detail_values.get("basis"), "details.basis")
        elif stage in {"dispatch_failed", "rejected", "no_result", "interpretation_failed", "unresolved"}:
            _nonempty(detail_values.get("reason"), "details.reason")
        elif stage == "interpreted":
            _nonempty(detail_values.get("method"), "details.method")
        elif stage == "continued":
            _nonempty(detail_values.get("next_attempt_id"), "details.next_attempt_id")
            _nonempty(detail_values.get("next_candidate_name"), "details.next_candidate_name")
            _nonempty(detail_values.get("hypothesis_set_digest"), "details.hypothesis_set_digest")

        event = PathEvent(
            stage=stage,
            actor=actor,
            clock_value=clock_value,
            clock_domain=clock_domain,
            evidence_ref=evidence_ref,
            details_json=_json_snapshot(detail_values),
        )
        self._events.append(event)
        return event

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.intent.attempt_id,
            "intent": {
                "candidate_name": self.intent.candidate_name,
                "query": self.intent.query,
                "hypothesis_set_digest": self.intent.hypothesis_set_digest,
                "estimated_cost": float(self.intent.estimated_cost),
                "plan_ref": self.intent.plan_ref,
            },
            "status": self.status,
            "terminal": self.terminal,
            "events": [
                {
                    "stage": event.stage,
                    "actor": event.actor,
                    "clock_value": event.clock_value,
                    "clock_domain": event.clock_domain,
                    "evidence_ref": event.evidence_ref,
                    "details": event.details,
                }
                for event in self._events
            ],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
