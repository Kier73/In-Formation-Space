"""Connect an adaptive attention policy to append-only observation attempts.

This coordinator does not execute transport or sensor operations. An external
adapter reports dispatch, receiver admission, raw-return provenance, and the
interpreter's result through explicit methods.

The policy is a prediction model. An observed value that matches no predicted
branch closes the attempt as unresolved model drift; the coordinator never
chooses a nearest branch or converts missing evidence into a negative result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Hashable, List, Mapping, Optional, Sequence

from observation_path import ObservationIntent, ObservationPath


@dataclass(frozen=True)
class PolicyExecutionResult:
    status: str
    query_result: Optional[bool]
    attempts: tuple


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


class AdaptivePolicyExecution:
    """Bridge a supplied policy tree to evidence-gated request attempts.

    The plan and its nodes are consumed by their attributes:
    complete, policy, query_result, observation_name, hypotheses, branches.
    This avoids binding the bridge to one planner implementation.

    Observations are supplied as objects with name and cost attributes. The
    coordinator records intent and evidence references only. A transport
    adapter must call the stage methods after its real operation has occurred.
    """

    def __init__(
        self,
        plan: object,
        observations: Sequence[object],
        *,
        attempt_id_prefix: str,
        query_label: str,
        hypothesis_digest: Callable[[Sequence[Hashable]], str],
        plan_ref: Optional[str] = None,
        evidence_authority_required: bool = False,
        receiver_application_required: bool = False,
        sender_acknowledgement_required: bool = False,
    ) -> None:
        _nonempty(attempt_id_prefix, "attempt_id_prefix")
        _nonempty(query_label, "query_label")
        if plan_ref is not None:
            _nonempty(plan_ref, "plan_ref")
        if not callable(hypothesis_digest):
            raise TypeError("hypothesis_digest must be callable")
        if not isinstance(evidence_authority_required, bool):
            raise ValueError("evidence_authority_required must be boolean")
        if not isinstance(receiver_application_required, bool):
            raise ValueError("receiver_application_required must be boolean")
        if not isinstance(sender_acknowledgement_required, bool):
            raise ValueError("sender_acknowledgement_required must be boolean")
        if receiver_application_required and not evidence_authority_required:
            raise ValueError("receiver_application_required implies evidence_authority_required")
        if sender_acknowledgement_required and not receiver_application_required:
            raise ValueError("sender_acknowledgement_required implies receiver_application_required")
        if not getattr(plan, "complete", False):
            raise ValueError("cannot execute an incomplete adaptive policy plan")
        root = getattr(plan, "policy", None)
        if root is None:
            raise ValueError("complete plan must contain a policy root")

        by_name: Dict[str, object] = {}
        for candidate in observations:
            name = getattr(candidate, "name", None)
            _nonempty(name, "observation.name")
            if name in by_name:
                raise ValueError(f"duplicate observation candidate: {name}")
            cost_value = getattr(candidate, "cost", None)
            if isinstance(cost_value, bool):
                raise ValueError(f"observation cost must be finite and positive: {name}")
            try:
                cost = float(cost_value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"observation cost must be finite and positive: {name}") from exc
            if not math.isfinite(cost) or cost <= 0.0:
                raise ValueError(f"observation cost must be finite and positive: {name}")
            by_name[name] = candidate

        self._node = root
        self._observations = by_name
        self._attempt_prefix = attempt_id_prefix
        self._query_label = query_label
        self._hypothesis_digest = hypothesis_digest
        self._plan_ref = plan_ref
        self._evidence_authority_required = evidence_authority_required
        self._receiver_application_required = receiver_application_required
        self._sender_acknowledgement_required = sender_acknowledgement_required
        self._attempt_index = 0
        self._path: Optional[ObservationPath] = None
        self._attempts: List[ObservationPath] = []
        self._status = "ready"
        self._query_result: Optional[bool] = None

        initial_result = getattr(root, "query_result", None)
        if initial_result is not None:
            if not isinstance(initial_result, bool):
                raise TypeError("policy root query_result must be boolean or None")
            self._query_result = initial_result
            self._status = "resolved"

    @property
    def status(self) -> str:
        return self._status

    @property
    def query_result(self) -> Optional[bool]:
        return self._query_result

    @property
    def current_observation_name(self) -> Optional[str]:
        return getattr(self._node, "observation_name", None) if self._status == "ready" else None

    @property
    def attempts(self) -> tuple:
        return tuple(self._attempts)

    def _current_path(self) -> ObservationPath:
        if self._path is None:
            raise ValueError("no active observation attempt; call begin_attempt first")
        return self._path

    def _digest(self, hypotheses: Sequence[Hashable]) -> str:
        return _nonempty(self._hypothesis_digest(tuple(hypotheses)), "hypothesis digest")

    def begin_attempt(self) -> ObservationPath:
        """Create the next planned request from the current policy node."""
        if self._status != "ready":
            raise ValueError(f"cannot begin attempt while execution is {self._status}")
        observation_name = getattr(self._node, "observation_name", None)
        if observation_name is None:
            raise ValueError("non-terminal policy node has no observation name")
        candidate = self._observations.get(observation_name)
        if candidate is None:
            raise ValueError(f"policy references an unavailable observation: {observation_name}")

        attempt_id = f"{self._attempt_prefix}:{self._attempt_index:04d}"
        intent = ObservationIntent(
            attempt_id=attempt_id,
            candidate_name=observation_name,
            query=self._query_label,
            hypothesis_set_digest=self._digest(getattr(self._node, "hypotheses")),
            estimated_cost=float(candidate.cost),
            plan_ref=self._plan_ref,
            authority_required=self._evidence_authority_required,
            application_required=self._receiver_application_required,
            sender_ack_required=self._sender_acknowledgement_required,
        )
        self._path = ObservationPath(intent)
        self._attempts.append(self._path)
        self._status = "planned"
        return self._path

    def mark_dispatched(
        self,
        actor: str,
        evidence_ref: str,
        *,
        clock_value: Optional[str] = None,
        clock_domain: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        path = self._current_path()
        if self._status != "planned":
            raise ValueError(f"cannot dispatch while execution is {self._status}")
        path.append(
            "dispatched", actor, evidence_ref=evidence_ref,
            clock_value=clock_value, clock_domain=clock_domain, details=details,
        )
        self._status = "dispatched"

    def mark_admitted(
        self,
        actor: str,
        evidence_ref: str,
        *,
        clock_value: Optional[str] = None,
        clock_domain: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        path = self._current_path()
        if self._status != "dispatched":
            raise ValueError(f"cannot admit while execution is {self._status}")
        path.append(
            "admitted", actor, evidence_ref=evidence_ref,
            clock_value=clock_value, clock_domain=clock_domain, details=details,
        )
        self._status = "admitted"

    def record_return(
        self,
        actor: str,
        *,
        evidence_ref: str,
        encounter_id: str,
        payload_digest: str,
        canonicalization: str,
        clock_value: Optional[str] = None,
        clock_domain: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Record a raw return reference; the payload itself is not interpreted."""
        path = self._current_path()
        if self._status != "admitted":
            raise ValueError(f"cannot record a return while execution is {self._status}")
        return_details = dict(details or {})
        return_details.update({
            "encounter_id": encounter_id,
            "payload_digest": payload_digest,
            "canonicalization": canonicalization,
        })
        path.append(
            "returned", actor, evidence_ref=evidence_ref,
            clock_value=clock_value, clock_domain=clock_domain,
            details=return_details,
        )
        self._status = "returned"

    def record_unadmitted_return(
        self,
        actor: str,
        *,
        evidence_ref: str,
        encounter_id: str,
        payload_digest: str,
        canonicalization: str,
        clock_value: Optional[str] = None,
        clock_domain: Optional[str] = None,
    ) -> PolicyExecutionResult:
        """Preserve a return that arrived without receiver admission."""
        path = self._current_path()
        if self._status != "dispatched":
            raise ValueError(f"cannot record an unadmitted return while execution is {self._status}")
        path.append(
            "returned_unadmitted",
            actor,
            evidence_ref=evidence_ref,
            clock_value=clock_value,
            clock_domain=clock_domain,
            details={
                "encounter_id": encounter_id,
                "payload_digest": payload_digest,
                "canonicalization": canonicalization,
            },
        )
        self._status = "returned_unadmitted"
        return self.result()



    def mark_evidence_authorized(
        self,
        actor: str,
        evidence_ref: str,
        *,
        policy_digest: str,
        decision_digest: str,
        quorum: int,
        strict: bool,
        observed_sources: Sequence[str],
        representative_source: str,
        dissenting_sources: Sequence[str] = (),
        missing_sources: Sequence[str] = (),
    ) -> None:
        """Record explicit consensus/authority after a raw return is preserved."""
        path = self._current_path()
        if self._status != "returned":
            raise ValueError(f"cannot authorize evidence while execution is {self._status}")
        path.append(
            "evidence_authorized",
            actor,
            evidence_ref=evidence_ref,
            details={
                "decision_status": "AUTHORIZED",
                "policy_digest": policy_digest,
                "decision_digest": decision_digest,
                "quorum": quorum,
                "strict": strict,
                "observed_sources": list(observed_sources),
                "dissenting_sources": list(dissenting_sources),
                "missing_sources": list(missing_sources),
                "representative_source": representative_source,
            },
        )
        self._status = "evidence_authorized"

    def mark_evidence_refused(
        self,
        actor: str,
        evidence_ref: str,
        *,
        decision_status: str,
        policy_digest: str,
        decision_digest: str,
        quorum: int,
        strict: bool,
        observed_sources: Sequence[str],
        dissenting_sources: Sequence[str] = (),
        missing_sources: Sequence[str] = (),
        reason: str,
    ) -> PolicyExecutionResult:
        """Record a finalized conflict/refusal without interpreting the payload."""
        path = self._current_path()
        if self._status != "returned":
            raise ValueError(f"cannot refuse evidence while execution is {self._status}")
        path.append(
            "evidence_refused",
            actor,
            evidence_ref=evidence_ref,
            details={
                "decision_status": decision_status,
                "policy_digest": policy_digest,
                "decision_digest": decision_digest,
                "quorum": quorum,
                "strict": strict,
                "observed_sources": list(observed_sources),
                "dissenting_sources": list(dissenting_sources),
                "missing_sources": list(missing_sources),
                "reason": reason,
            },
        )
        self._status = "evidence_refused"
        return self.result()

    def mark_applied(
        self,
        actor: str,
        evidence_ref: str,
        *,
        application_id: str,
        target_id: str,
        projection_digest: str,
        register_prefix: str,
    ) -> None:
        """Record an externally completed receiver-side application receipt."""
        path = self._current_path()
        if self._status != "evidence_authorized":
            raise ValueError(f"cannot record receiver application while execution is {self._status}")
        path.append(
            "applied",
            actor,
            evidence_ref=evidence_ref,
            details={
                "application_id": application_id,
                "target_id": target_id,
                "projection_digest": projection_digest,
                "register_prefix": register_prefix,
            },
        )
        self._status = "applied"

    def stop_application_failed(self, actor: str, reason: str) -> PolicyExecutionResult:
        path = self._current_path()
        if self._status not in {"evidence_authorized", "applied"}:
            raise ValueError(f"cannot record application failure while execution is {self._status}")
        path.append("application_failed", actor, details={"reason": reason})
        self._status = "application_failed"
        return self.result()

    def mark_sender_acknowledged(
        self,
        actor: str,
        evidence_ref: str,
        *,
        event_kind: str,
        logical_time: int,
        sources: Sequence[str],
        acknowledged_sequences: Sequence[Mapping[str, Any]],
        expected_event_sequences: Sequence[Mapping[str, Any]],
        missing_event_sequences: Sequence[Mapping[str, Any]],
        ack_digest: str,
        complete: bool,
    ) -> None:
        """Record sender-side processing only after the adapter verifies removed pending sequences."""
        path = self._current_path()
        if not self._sender_acknowledgement_required:
            raise ValueError("sender acknowledgement is not required by this policy execution")
        if self._status not in {"applied", "sender_ack_progress"}:
            raise ValueError(f"cannot acknowledge sender delivery while execution is {self._status}")
        if not isinstance(complete, bool):
            raise ValueError("complete must be boolean")
        stage = "sender_acknowledged" if complete else "sender_ack_progress"
        path.append(
            stage,
            actor,
            evidence_ref=evidence_ref,
            details={
                "event_kind": event_kind,
                "logical_time": logical_time,
                "sources": list(sources),
                "acknowledged_sequences": [dict(item) for item in acknowledged_sequences],
                "expected_event_sequences": [dict(item) for item in expected_event_sequences],
                "missing_event_sequences": [dict(item) for item in missing_event_sequences],
                "ack_digest": ack_digest,
            },
        )
        self._status = stage

    def interpret(
        self,
        interpreted_value: Hashable,
        *,
        actor: str,
        method: str,
        evidence_ref: str,
    ) -> PolicyExecutionResult:
        """Interpret the return and advance, resolve, or stop on model mismatch."""
        path = self._current_path()
        required_stage = (
            "sender_acknowledged" if self._sender_acknowledgement_required
            else "applied" if self._receiver_application_required
            else "evidence_authorized"
            if self._evidence_authority_required or self._status == "evidence_authorized"
            else "returned"
        )
        if self._status != required_stage:
            raise ValueError(f"cannot interpret before required stage {required_stage}; current status is {self._status}")
        try:
            hash(interpreted_value)
        except TypeError as exc:
            raise TypeError("interpreted_value must be hashable") from exc

        path.append(
            "interpreted",
            actor,
            evidence_ref=evidence_ref,
            details={"method": method, "interpreted_value": interpreted_value},
        )

        selected_child = None
        for outcome, child in getattr(self._node, "branches"):
            if outcome == interpreted_value:
                selected_child = child
                break

        if selected_child is None:
            path.append(
                "unresolved",
                actor,
                evidence_ref=evidence_ref,
                details={
                    "reason": "interpreted observation value was not predicted by the policy",
                    "interpreted_value": interpreted_value,
                },
            )
            self._status = "unresolved_model_mismatch"
            return self.result()

        child_result = getattr(selected_child, "query_result", None)
        if child_result is not None:
            if not isinstance(child_result, bool):
                raise TypeError("terminal policy query_result must be boolean or None")
            digest = self._digest(getattr(selected_child, "hypotheses"))
            path.append(
                "query_determined",
                "verifier",
                evidence_ref=evidence_ref,
                details={
                    "query_result": child_result,
                    "hypothesis_set_digest": digest,
                    "basis": evidence_ref,
                },
            )
            self._node = selected_child
            self._query_result = child_result
            self._status = "resolved"
            return self.result()

        next_name = getattr(selected_child, "observation_name", None)
        if next_name not in self._observations:
            path.append(
                "unresolved",
                actor,
                evidence_ref=evidence_ref,
                details={"reason": f"policy references unavailable next observation: {next_name!r}"},
            )
            self._status = "unresolved_missing_candidate"
            return self.result()

        self._attempt_index += 1
        next_attempt_id = f"{self._attempt_prefix}:{self._attempt_index:04d}"
        digest = self._digest(getattr(selected_child, "hypotheses"))
        path.append(
            "continued",
            "policy-controller",
            evidence_ref=evidence_ref,
            details={
                "next_attempt_id": next_attempt_id,
                "next_candidate_name": next_name,
                "hypothesis_set_digest": digest,
            },
        )
        self._node = selected_child
        self._path = None
        self._status = "ready"
        return self.result()

    def stop_dispatch_failed(self, actor: str, reason: str) -> PolicyExecutionResult:
        path = self._current_path()
        if self._status != "planned":
            raise ValueError(f"cannot record dispatch failure while execution is {self._status}")
        path.append("dispatch_failed", actor, details={"reason": reason})
        self._status = "dispatch_failed"
        return self.result()

    def stop_no_result(self, actor: str, reason: str) -> PolicyExecutionResult:
        path = self._current_path()
        if self._status != "admitted":
            raise ValueError(f"cannot record no-result while execution is {self._status}")
        path.append("no_result", actor, details={"reason": reason})
        self._status = "no_result"
        return self.result()

    def stop_interpretation_failed(self, actor: str, reason: str) -> PolicyExecutionResult:
        path = self._current_path()
        required_stage = (
            "sender_acknowledged" if self._sender_acknowledgement_required
            else "applied" if self._receiver_application_required
            else "evidence_authorized"
            if self._evidence_authority_required or self._status == "evidence_authorized"
            else "returned"
        )
        if self._status != required_stage:
            raise ValueError(f"cannot record interpretation failure before required stage {required_stage}; current status is {self._status}")
        path.append("interpretation_failed", actor, details={"reason": reason})
        self._status = "interpretation_failed"
        return self.result()

    def stop_rejected(self, actor: str, reason: str) -> PolicyExecutionResult:
        path = self._current_path()
        if self._status != "dispatched":
            raise ValueError(f"cannot record rejection while execution is {self._status}")
        path.append("rejected", actor, details={"reason": reason})
        self._status = "rejected"
        return self.result()

    def result(self) -> PolicyExecutionResult:
        return PolicyExecutionResult(
            status=self._status,
            query_result=self._query_result,
            attempts=tuple(path.to_dict() for path in self._attempts),
        )
