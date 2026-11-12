"""Evidence-gated execution lifecycle for VGI proof-attention actions.

The session selects an action from a digest-bound ProofGround plan, records
its dispatch/admission/return lifecycle, then accepts a refreshed ProofGround
only when it contains one result edge correlated to that exact attempt ID.
This bridge does not execute tactics or authenticate external receipts.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Any

from proof_attention import build_proof_attention_plan


class ProofActionExecutionError(ValueError):
    """Invalid proof action, execution lifecycle, or refreshed proof trace."""


_ALLOWED_NEXT = {
    "planned": {"dispatched", "dispatch_failed"},
    "dispatched": {"admitted", "execution_rejected", "returned_unadmitted"},
    "admitted": {"returned", "no_result"},
    "returned": {"interpreted", "interpretation_failed"},
    "interpreted": {"continued", "query_determined", "unresolved"},
}
_TERMINAL = {
    "dispatch_failed",
    "execution_rejected",
    "returned_unadmitted",
    "no_result",
    "interpretation_failed",
    "query_determined",
    "unresolved",
}
_FAILURE_STAGES = {
    "dispatch_failed", "execution_rejected", "no_result", "interpretation_failed"
}
_RESULT_STAGES = {"elaborated", "timeout", "rejected"}


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProofActionExecutionError("proof-action data must be finite canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProofActionExecutionError(f"{label} must be non-empty text")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ProofActionExecutionError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _environment_payload(proof_ground: Any) -> dict[str, Any]:
    environment = getattr(proof_ground, "environment", None)
    if environment is None or not callable(getattr(environment, "to_dict", None)):
        raise ProofActionExecutionError("proof Ground must expose environment.to_dict()")
    payload = environment.to_dict()
    if not isinstance(payload, Mapping):
        raise ProofActionExecutionError("proof Ground environment must serialize to an object")
    return _copy(payload)


class ProofActionAttempt:
    """One append-only action lifecycle, correlated to a single plan candidate."""

    def __init__(
        self,
        *,
        attempt_id: str,
        action: Mapping[str, Any],
        plan_digest: str,
        proof_ground_digest: str,
        query_label: str,
    ) -> None:
        self.attempt_id = _text(attempt_id, "attempt_id")
        self.action = _copy(action)
        self.plan_digest = _sha256(plan_digest, "plan_digest")
        self.proof_ground_digest = _sha256(proof_ground_digest, "proof_ground_digest")
        self.query_label = _text(query_label, "query_label")
        self._events: list[dict[str, Any]] = []
        self._append(
            "planned",
            "proof-attention-planner",
            evidence_ref=f"urn:sha256:{self.plan_digest}",
            details={
                "query_label": self.query_label,
                "plan_digest": self.plan_digest,
                "proof_ground_digest": self.proof_ground_digest,
                "transition_id": self.action["transition_id"],
                "source_obligation_id": self.action["source_obligation_id"],
                "tactic": self.action["tactic"],
                "and_bundle_width": self.action["and_bundle_width"],
            },
        )

    @property
    def status(self) -> str:
        return self._events[-1]["stage"]

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(_copy(event) for event in self._events)

    def _append(
        self,
        stage: str,
        actor: str,
        *,
        evidence_ref: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        actor = _text(actor, "actor")
        if self._events:
            if stage not in _ALLOWED_NEXT.get(self.status, set()):
                raise ProofActionExecutionError(
                    f"invalid proof-action transition: {self.status} -> {stage}"
                )
        elif stage != "planned":
            raise ProofActionExecutionError("a proof-action attempt must begin at planned")
        if stage in {
            "dispatched", "admitted", "returned", "returned_unadmitted",
            "interpreted", "continued", "query_determined",
        }:
            evidence_ref = _text(evidence_ref, "evidence_ref")
        elif evidence_ref is not None:
            evidence_ref = _text(evidence_ref, "evidence_ref")

        values = _copy(dict(details or {}))
        if stage in _FAILURE_STAGES | {"execution_rejected", "returned_unadmitted"}:
            _text(values.get("reason"), "details.reason")
        elif stage == "returned":
            _text(values.get("encounter_id"), "details.encounter_id")
            _sha256(values.get("payload_digest"), "details.payload_digest")
            _text(values.get("canonicalization"), "details.canonicalization")
        elif stage == "interpreted":
            if values.get("attempt_status") not in _RESULT_STAGES:
                raise ProofActionExecutionError(
                    "interpreted event requires elaborated, timeout, or rejected attempt_status"
                )
            _text(values.get("result_transition_id"), "details.result_transition_id")
            _sha256(values.get("updated_proof_ground_digest"), "details.updated_proof_ground_digest")
            _sha256(values.get("updated_plan_digest"), "details.updated_plan_digest")
            _text(values.get("interpretation_ref"), "details.interpretation_ref")
            subgoals = values.get("subgoal_ids")
            if not isinstance(subgoals, (list, tuple)) or any(
                not isinstance(item, str) or not item for item in subgoals
            ):
                raise ProofActionExecutionError("interpreted event requires subgoal_ids")
            if len(set(subgoals)) != len(subgoals):
                raise ProofActionExecutionError("interpreted subgoal_ids must be unique")
        elif stage == "continued":
            _text(values.get("next_attempt_id"), "details.next_attempt_id")
            _text(values.get("next_transition_id"), "details.next_transition_id")
            _sha256(values.get("next_plan_digest"), "details.next_plan_digest")
        elif stage == "query_determined":
            if values.get("query_result") is not True:
                raise ProofActionExecutionError("query_determined requires query_result=true")
            _text(values.get("basis"), "details.basis")
            _sha256(values.get("proof_ground_digest"), "details.proof_ground_digest")
        elif stage == "unresolved":
            _text(values.get("reason"), "details.reason")

        previous = self._events[-1]["event_digest"] if self._events else "0" * 64
        core = {
            "sequence": len(self._events) + 1,
            "attempt_id": self.attempt_id,
            "stage": stage,
            "actor": actor,
            "evidence_ref": evidence_ref,
            "details": values,
            "previous_event_digest": previous,
        }
        event = {**core, "event_digest": _digest(core)}
        self._events.append(event)
        return _copy(event)

    def mark_dispatched(self, actor: str, evidence_ref: str, *, details: Mapping[str, Any] | None = None):
        return self._append("dispatched", actor, evidence_ref=evidence_ref, details=details)

    def mark_admitted(self, actor: str, evidence_ref: str, *, details: Mapping[str, Any] | None = None):
        return self._append("admitted", actor, evidence_ref=evidence_ref, details=details)

    def record_return(
        self,
        actor: str,
        *,
        evidence_ref: str,
        encounter_id: str,
        payload_digest: str,
        canonicalization: str,
        details: Mapping[str, Any] | None = None,
    ):
        values = dict(details or {})
        values.update({
            "encounter_id": encounter_id,
            "payload_digest": payload_digest,
            "canonicalization": canonicalization,
            "attempt_id": self.attempt_id,
            "transition_id": self.action["transition_id"],
        })
        return self._append("returned", actor, evidence_ref=evidence_ref, details=values)

    def record_unadmitted_return(
        self,
        actor: str,
        *,
        evidence_ref: str,
        encounter_id: str,
        payload_digest: str,
        canonicalization: str,
    ):
        return self._append(
            "returned_unadmitted",
            actor,
            evidence_ref=evidence_ref,
            details={
                "reason": "raw result returned without an admission receipt",
                "encounter_id": _text(encounter_id, "encounter_id"),
                "payload_digest": _sha256(payload_digest, "payload_digest"),
                "canonicalization": _text(canonicalization, "canonicalization"),
            },
        )

    def mark_failure(
        self,
        stage: str,
        actor: str,
        reason: str,
        *,
        evidence_ref: str | None = None,
    ):
        if stage not in _FAILURE_STAGES | {"execution_rejected"}:
            raise ProofActionExecutionError(f"unsupported failure stage: {stage}")
        return self._append(
            stage, actor, evidence_ref=evidence_ref,
            details={"reason": _text(reason, "reason")},
        )

    def _record_interpretation(
        self,
        *,
        actor: str,
        interpretation_ref: str,
        result_edge: Any,
        updated_plan: Mapping[str, Any],
        returned_payload_digest: str,
    ) -> dict[str, Any]:
        return self._append(
            "interpreted",
            actor,
            evidence_ref=interpretation_ref,
            details={
                "attempt_status": result_edge.attempt_status,
                "result_transition_id": result_edge.transition_id,
                "result_evidence_ref": result_edge.evidence_ref,
                "subgoal_ids": list(result_edge.subgoal_ids),
                "returned_payload_digest": returned_payload_digest,
                "updated_proof_ground_digest": updated_plan["proof_ground_digest"],
                "updated_plan_digest": updated_plan["plan_digest"],
                "interpretation_ref": interpretation_ref,
            },
        )

    def _finish_continued(self, next_attempt_id: str, next_action: Mapping[str, Any], next_plan: Mapping[str, Any]):
        return self._append(
            "continued",
            "proof-attention-session",
            evidence_ref=f"urn:sha256:{next_plan['plan_digest']}",
            details={
                "next_attempt_id": next_attempt_id,
                "next_transition_id": next_action["transition_id"],
                "next_plan_digest": next_plan["plan_digest"],
            },
        )

    def _finish_query(self, proof_ground_digest: str):
        return self._append(
            "query_determined",
            "proof-attention-session",
            evidence_ref=f"urn:sha256:{proof_ground_digest}",
            details={
                "query_result": True,
                "basis": "every explicit active root has a matched verified kernel-accepted receipt",
                "proof_ground_digest": proof_ground_digest,
            },
        )

    def _finish_unresolved(self, reason: str, proof_ground_digest: str):
        return self._append(
            "unresolved",
            "proof-attention-session",
            evidence_ref=f"urn:sha256:{proof_ground_digest}",
            details={"reason": reason},
        )

    def to_dict(self) -> dict[str, Any]:
        core = {
            "format": "in-formation.proof-action-attempt/0.1",
            "attempt_id": self.attempt_id,
            "query_label": self.query_label,
            "plan_digest": self.plan_digest,
            "proof_ground_digest": self.proof_ground_digest,
            "action": _copy(self.action),
            "status": self.status,
            "terminal": self.terminal,
            "events": self.events,
        }
        return {**core, "attempt_digest": _digest(core)}


class ProofAttentionSession:
    """Select one proof action at a time and replan only from a refreshed VGI Ground."""

    def __init__(
        self,
        proof_ground: Any,
        root_obligation_ids: Sequence[str],
        *,
        attempt_id_prefix: str,
        query_label: str,
        cost_model: Any | None = None,
    ) -> None:
        self._attempt_prefix = _text(attempt_id_prefix, "attempt_id_prefix")
        self._query_label = _text(query_label, "query_label")
        if not isinstance(root_obligation_ids, Sequence) or isinstance(root_obligation_ids, (str, bytes)):
            raise ProofActionExecutionError("root_obligation_ids must be a sequence")
        self._roots = tuple(root_obligation_ids)
        if not self._roots:
            raise ProofActionExecutionError("at least one active root intention is required")
        self._cost_model = cost_model
        self._ground = proof_ground
        self._environment = _environment_payload(proof_ground)
        self._plan = build_proof_attention_plan(
            proof_ground, self._roots, cost_model=cost_model
        )
        self._attempted_transition_ids: set[str] = set()
        self._attempts: list[ProofActionAttempt] = []
        self._active: ProofActionAttempt | None = None
        self._status = "ready"
        self._next_sequence = 1

    @property
    def status(self) -> str:
        return self._status

    @property
    def plan(self) -> dict[str, Any]:
        return _copy(self._plan)

    @property
    def active_attempt(self) -> ProofActionAttempt | None:
        return self._active

    @property
    def attempts(self) -> tuple[ProofActionAttempt, ...]:
        return tuple(self._attempts)

    def _roots_accepted(self) -> bool:
        return all(self._ground.kernel_status(root) == "kernel_accepted" for root in self._roots)

    def _set_terminal_status(self) -> None:
        self._status = "complete" if self._roots_accepted() else "exhausted"

    def begin_next(self) -> ProofActionAttempt | None:
        """Open the highest-ranked unattempted action, or finish the current frontier."""
        if self._status in ("complete", "exhausted"):
            return None
        if self._active is not None and not (
            self._active.terminal or self._active.status == "interpreted"
        ):
            raise ProofActionExecutionError(
                f"one proof action is already active at stage {self._active.status}"
            )

        next_action = next(
            (
                action for action in self._plan["candidate_actions"]
                if action["transition_id"] not in self._attempted_transition_ids
            ),
            None,
        )
        if self._roots_accepted():
            if self._active is not None and self._active.status == "interpreted":
                self._active._finish_query(self._plan["proof_ground_digest"])
            self._status = "complete"
            self._active = None
            return None

        if next_action is None:
            if self._active is not None and self._active.status == "interpreted":
                self._active._finish_unresolved(
                    "no unattempted candidate actions remain on the observed proof frontier",
                    self._plan["proof_ground_digest"],
                )
            self._set_terminal_status()
            self._active = None
            return None

        attempt_id = f"{self._attempt_prefix}:{self._next_sequence:06d}"
        if self._active is not None and self._active.status == "interpreted":
            self._active._finish_continued(attempt_id, next_action, self._plan)

        attempt = ProofActionAttempt(
            attempt_id=attempt_id,
            action=next_action,
            plan_digest=self._plan["plan_digest"],
            proof_ground_digest=self._plan["proof_ground_digest"],
            query_label=self._query_label,
        )
        self._next_sequence += 1
        self._attempted_transition_ids.add(next_action["transition_id"])
        self._attempts.append(attempt)
        self._active = attempt
        self._status = "active"
        return attempt

    def interpret_result(
        self,
        updated_proof_ground: Any,
        *,
        actor: str,
        interpretation_ref: str,
    ) -> dict[str, Any]:
        """Correlate one returned tactic result with a refreshed, structurally valid VGI Ground.

        The refreshed Ground must preserve the prior obligation identities and
        environment, and contain exactly one elaborated/timeout/rejected edge
        for the selected source+tactic whose evidence_ref is this attempt ID.
        """
        attempt = self._active
        if attempt is None or attempt.status != "returned":
            stage = attempt.status if attempt is not None else "no active attempt"
            raise ProofActionExecutionError(
                f"proof result can only be interpreted after return; current stage is {stage}"
            )
        actor = _text(actor, "actor")
        interpretation_ref = _text(interpretation_ref, "interpretation_ref")

        try:
            new_environment = _environment_payload(updated_proof_ground)
            old_ids = set(self._ground.obligation_ids)
            new_ids = set(updated_proof_ground.obligation_ids)
            if new_environment != self._environment:
                raise ProofActionExecutionError("refreshed proof trace changed its environment fingerprint")
            if not old_ids.issubset(new_ids):
                raise ProofActionExecutionError("refreshed proof Ground discarded prior obligation identities")
            source_id = attempt.action["source_obligation_id"]
            if source_id not in new_ids:
                raise ProofActionExecutionError("refreshed proof Ground no longer contains the selected source obligation")
            matches = [
                edge for edge in updated_proof_ground.transitions
                if (
                    edge.source_id == source_id
                    and edge.tactic == attempt.action["tactic"]
                    and edge.evidence_ref == attempt.attempt_id
                    and edge.attempt_status in _RESULT_STAGES
                )
            ]
            if len(matches) != 1:
                raise ProofActionExecutionError(
                    "refreshed proof Ground must contain exactly one result edge correlated to this attempt ID"
                )
            result_edge = matches[0]
            if any(item not in new_ids for item in result_edge.subgoal_ids):
                raise ProofActionExecutionError("result hyper-transition references an undeclared subgoal")
            updated_plan = build_proof_attention_plan(
                updated_proof_ground, self._roots, cost_model=self._cost_model
            )
        except ProofActionExecutionError:
            raise
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            raise ProofActionExecutionError(f"refreshed proof Ground is invalid: {exc}") from exc

        returned_events = [
            event for event in attempt.events if event["stage"] == "returned"
        ]
        if len(returned_events) != 1:
            raise ProofActionExecutionError("active attempt has no unique returned payload receipt")
        returned_payload_digest = returned_events[0]["details"]["payload_digest"]
        event = attempt._record_interpretation(
            actor=actor,
            interpretation_ref=interpretation_ref,
            result_edge=result_edge,
            updated_plan=updated_plan,
            returned_payload_digest=returned_payload_digest,
        )
        self._ground = updated_proof_ground
        self._environment = new_environment
        self._plan = updated_plan
        return {
            "attempt_id": attempt.attempt_id,
            "attempt_status": result_edge.attempt_status,
            "result_transition_id": result_edge.transition_id,
            "subgoal_ids": list(result_edge.subgoal_ids),
            "updated_plan_digest": updated_plan["plan_digest"],
            "event_digest": event["event_digest"],
        }

    def to_dict(self) -> dict[str, Any]:
        core = {
            "format": "in-formation.proof-attention-session/0.1",
            "attempt_id_prefix": self._attempt_prefix,
            "query_label": self._query_label,
            "active_root_obligation_ids": sorted(self._roots),
            "status": self._status,
            "current_proof_ground_digest": self._plan["proof_ground_digest"],
            "current_plan_digest": self._plan["plan_digest"],
            "attempted_transition_ids": sorted(self._attempted_transition_ids),
            "attempts": [attempt.to_dict() for attempt in self._attempts],
        }
        return {**core, "session_digest": _digest(core)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)


__all__ = [
    "ProofActionExecutionError",
    "ProofActionAttempt",
    "ProofAttentionSession",
]
