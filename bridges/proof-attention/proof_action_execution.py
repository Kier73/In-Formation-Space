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
    "planned": {"dispatched", "dispatch_failed", "route_closed"},
    "dispatched": {"admitted", "execution_rejected", "returned_unadmitted", "delivery_unconfirmed", "route_closed"},
    "admitted": {"returned", "no_result", "route_closed"},
    "returned": {"interpreted", "interpretation_failed", "route_closed"},
    "interpreted": {"continued", "query_determined", "unresolved"},
}
_TERMINAL = {
    "dispatch_failed",
    "execution_rejected",
    "route_closed",
    "delivery_unconfirmed",
    "returned_unadmitted",
    "no_result",
    "interpretation_failed",
    "query_determined",
    "unresolved",
}
_FAILURE_STAGES = {
    "dispatch_failed", "execution_rejected", "delivery_unconfirmed", "no_result", "interpretation_failed", "route_closed"
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

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "ProofActionAttempt":
        """Restore one attempt after verifying its snapshot and event hash chain."""
        if not isinstance(record, Mapping):
            raise ProofActionExecutionError("proof-action attempt snapshot must be an object")
        supplied = _copy(dict(record))
        required = {
            "format", "attempt_id", "query_label", "plan_digest",
            "proof_ground_digest", "action", "status", "terminal",
            "events", "attempt_digest",
        }
        if set(supplied) != required:
            raise ProofActionExecutionError("proof-action attempt snapshot fields are invalid")
        if supplied["format"] != "in-formation.proof-action-attempt/0.1":
            raise ProofActionExecutionError("unsupported proof-action attempt snapshot format")
        digest = supplied.pop("attempt_digest")
        if _sha256(digest, "attempt_digest") != _digest(supplied):
            raise ProofActionExecutionError("proof-action attempt snapshot digest mismatch")

        attempt_id = _text(supplied["attempt_id"], "attempt_id")
        query_label = _text(supplied["query_label"], "query_label")
        plan_digest = _sha256(supplied["plan_digest"], "plan_digest")
        ground_digest = _sha256(supplied["proof_ground_digest"], "proof_ground_digest")
        action = supplied["action"]
        if not isinstance(action, Mapping):
            raise ProofActionExecutionError("proof-action attempt action must be an object")
        action = _copy(dict(action))
        _text(action.get("transition_id"), "action.transition_id")
        _text(action.get("source_obligation_id"), "action.source_obligation_id")
        _text(action.get("tactic"), "action.tactic")

        events = supplied["events"]
        if not isinstance(events, list) or not events:
            raise ProofActionExecutionError("proof-action attempt requires an event sequence")
        prior_digest = "0" * 64
        prior_stage = None
        for index, event in enumerate(events, start=1):
            if not isinstance(event, Mapping):
                raise ProofActionExecutionError("proof-action event must be an object")
            event = dict(event)
            expected_fields = {
                "sequence", "attempt_id", "stage", "actor", "evidence_ref",
                "details", "previous_event_digest", "event_digest",
            }
            if set(event) != expected_fields:
                raise ProofActionExecutionError("proof-action event fields are invalid")
            if type(event["sequence"]) is not int or event["sequence"] != index:
                raise ProofActionExecutionError("proof-action event sequence is not contiguous")
            if event["attempt_id"] != attempt_id:
                raise ProofActionExecutionError("proof-action event belongs to another attempt")
            stage = _text(event["stage"], "event.stage")
            if (prior_stage is None and stage != "planned") or (
                prior_stage is not None and stage not in _ALLOWED_NEXT.get(prior_stage, set())
            ):
                raise ProofActionExecutionError("proof-action event lifecycle is invalid")
            _text(event["actor"], "event.actor")
            if event["evidence_ref"] is not None:
                _text(event["evidence_ref"], "event.evidence_ref")
            if not isinstance(event["details"], Mapping):
                raise ProofActionExecutionError("proof-action event details must be an object")
            if event["previous_event_digest"] != prior_digest:
                raise ProofActionExecutionError("proof-action event chain predecessor mismatch")
            event_core = {key: value for key, value in event.items() if key != "event_digest"}
            observed_digest = _sha256(event["event_digest"], "event.event_digest")
            if observed_digest != _digest(event_core):
                raise ProofActionExecutionError("proof-action event digest mismatch")
            prior_digest = observed_digest
            prior_stage = stage

        if supplied["status"] != prior_stage:
            raise ProofActionExecutionError("proof-action attempt status disagrees with its event tail")
        if type(supplied["terminal"]) is not bool or supplied["terminal"] != (prior_stage in _TERMINAL):
            raise ProofActionExecutionError("proof-action attempt terminal flag is inconsistent")
        first = events[0]
        first_details = first["details"]
        if (
            first_details.get("plan_digest") != plan_digest
            or first_details.get("proof_ground_digest") != ground_digest
            or first_details.get("transition_id") != action["transition_id"]
            or first_details.get("source_obligation_id") != action["source_obligation_id"]
            or first_details.get("tactic") != action["tactic"]
        ):
            raise ProofActionExecutionError("proof-action planned event does not match its action snapshot")

        instance = cls.__new__(cls)
        instance.attempt_id = attempt_id
        instance.action = action
        instance.plan_digest = plan_digest
        instance.proof_ground_digest = ground_digest
        instance.query_label = query_label
        instance._events = _copy(events)
        return instance

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

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        proof_ground: Any,
        *,
        cost_model: Any | None = None,
    ) -> "ProofAttentionSession":
        """Restore against a freshly imported Ground and verify the full handoff snapshot.

        This restores orchestration state only. It does not authenticate prior
        workers, returned Encounters, or upstream kernel receipts.
        """
        if not isinstance(snapshot, Mapping):
            raise ProofActionExecutionError("proof-attention session snapshot must be an object")
        supplied = _copy(dict(snapshot))
        required = {
            "format", "attempt_id_prefix", "query_label", "active_root_obligation_ids",
            "status", "current_proof_ground_digest", "current_plan_digest",
            "current_plan", "attempted_transition_ids", "attempts", "session_digest",
        }
        if set(supplied) != required:
            raise ProofActionExecutionError("proof-attention session snapshot fields are invalid")
        if supplied["format"] != "in-formation.proof-attention-session/0.1":
            raise ProofActionExecutionError("unsupported proof-attention session snapshot format")
        session_digest = _sha256(supplied.pop("session_digest"), "session_digest")
        if session_digest != _digest(supplied):
            raise ProofActionExecutionError("proof-attention session snapshot digest mismatch")

        roots = supplied["active_root_obligation_ids"]
        if not isinstance(roots, list) or not roots or any(
            not isinstance(item, str) or not item for item in roots
        ):
            raise ProofActionExecutionError("session snapshot requires explicit root obligation IDs")
        if roots != sorted(set(roots)):
            raise ProofActionExecutionError("session snapshot root obligation IDs must be sorted and unique")
        status = supplied["status"]
        if status not in ("ready", "active", "complete", "exhausted"):
            raise ProofActionExecutionError("session snapshot status is invalid")

        restored = cls(
            proof_ground,
            tuple(roots),
            attempt_id_prefix=supplied["attempt_id_prefix"],
            query_label=supplied["query_label"],
            cost_model=cost_model,
        )
        current_plan = supplied["current_plan"]
        if not isinstance(current_plan, Mapping) or _copy(dict(current_plan)) != restored.plan:
            raise ProofActionExecutionError("supplied ProofGround does not reproduce the session's current plan")
        if (
            supplied["current_plan_digest"] != restored._plan["plan_digest"]
            or supplied["current_proof_ground_digest"] != restored._plan["proof_ground_digest"]
        ):
            raise ProofActionExecutionError("session snapshot plan fingerprints do not match supplied ProofGround")

        raw_attempts = supplied["attempts"]
        if not isinstance(raw_attempts, list):
            raise ProofActionExecutionError("session snapshot attempts must be an array")
        attempts = [ProofActionAttempt.from_dict(item) for item in raw_attempts]
        attempt_ids = [item.attempt_id for item in attempts]
        transition_ids = [item.action["transition_id"] for item in attempts]
        if len(set(attempt_ids)) != len(attempt_ids):
            raise ProofActionExecutionError("session snapshot contains duplicate attempt IDs")
        if len(set(transition_ids)) != len(transition_ids):
            raise ProofActionExecutionError("session snapshot repeats an attempted transition ID")
        expected_attempt_ids = [
            f"{supplied['attempt_id_prefix']}:{index:06d}"
            for index in range(1, len(attempts) + 1)
        ]
        if attempt_ids != expected_attempt_ids:
            raise ProofActionExecutionError("session snapshot attempt sequence is not contiguous")
        if any(item.query_label != supplied["query_label"] for item in attempts):
            raise ProofActionExecutionError("session snapshot mixes query labels")
        attempted = supplied["attempted_transition_ids"]
        if not isinstance(attempted, list) or attempted != sorted(transition_ids):
            raise ProofActionExecutionError("session snapshot attempted transition index is inconsistent")

        if status == "ready" and attempts:
            raise ProofActionExecutionError("ready session snapshot cannot contain attempts")
        if status == "active" and not attempts:
            raise ProofActionExecutionError("active session snapshot must contain an active attempt")
        if status == "active" and attempts[-1].status in ("continued", "query_determined", "unresolved"):
            raise ProofActionExecutionError("active session snapshot ends in a closed attempt")
        if status == "active" and attempts[-1].status != "interpreted":
            active_transition_id = attempts[-1].action["transition_id"]
            if not any(
                action["transition_id"] == active_transition_id
                for action in restored._plan["candidate_actions"]
            ):
                raise ProofActionExecutionError("active attempt is not present in the current candidate frontier")
        roots_accepted = all(
            proof_ground.kernel_status(root) == "kernel_accepted" for root in roots
        )
        if status == "complete" and not roots_accepted:
            raise ProofActionExecutionError("complete session snapshot lacks accepted receipts for every root")
        if status == "exhausted":
            remaining = [
                action for action in restored._plan["candidate_actions"]
                if action["transition_id"] not in set(transition_ids)
            ]
            if roots_accepted or remaining:
                raise ProofActionExecutionError("exhausted session snapshot contradicts current proof frontier")

        restored._attempts = attempts
        restored._attempted_transition_ids = set(transition_ids)
        restored._next_sequence = len(attempts) + 1
        restored._status = status
        restored._active = attempts[-1] if status == "active" else None
        return restored

    def to_dict(self) -> dict[str, Any]:
        core = {
            "format": "in-formation.proof-attention-session/0.1",
            "attempt_id_prefix": self._attempt_prefix,
            "query_label": self._query_label,
            "active_root_obligation_ids": sorted(self._roots),
            "status": self._status,
            "current_proof_ground_digest": self._plan["proof_ground_digest"],
            "current_plan_digest": self._plan["plan_digest"],
            "current_plan": self.plan,
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
