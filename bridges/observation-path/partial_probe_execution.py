"""Evidence-gated execution of VGI cell-specific partial-attention proposals.

The planner's scenarios are counterfactual possibilities, not observations.
This module binds a VGI score to one Ground revision and an append-only
ObservationPath. A returned outcome is interpreted against the proposed
scenario set, but it changes no Ground until the normal evidence-authorization
gate (and any declared application/ACK gates) has been recorded.

The runtime deliberately does not import VGI. This keeps the bridge optional
and lets it consume compatible, inspectable VGI objects by their public fields.
The interoperability tests use a separately pinned VGI checkout.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping, Optional

from observation_path import ObservationIntent, ObservationPath


PLAN_FORMAT = "in-formation.vgi-partial-probe-plan/0.1"
HISTORY_KEY = "in_formation_partial_probe_revision_history"


class PartialProbeExecutionError(ValueError):
    """Invalid proposal, lifecycle, interpretation, or Ground revision."""


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PartialProbeExecutionError(f"{label} must be non-empty text")
    return value


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PartialProbeExecutionError(
            f"value must be finite canonical JSON: {exc}"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _exact_fraction(value: object, label: str, *, positive: bool = False) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise PartialProbeExecutionError(
            f"{label} must be an exact integer or Fraction, not a float"
        )
    try:
        result = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise PartialProbeExecutionError(f"{label} must be an exact rational") from exc
    if positive and result <= 0:
        raise PartialProbeExecutionError(f"{label} must be positive")
    return result


def _fraction_record(value: object, label: str, *, positive: bool = False):
    if value is None:
        return None
    rational = _exact_fraction(value, label, positive=positive)
    return {"numerator": rational.numerator, "denominator": rational.denominator}


def _outcome_record(outcome: object, channels: int, label: str) -> dict[str, Any]:
    target = _nonempty(getattr(outcome, "target", None), f"{label}.target")
    raw_output = getattr(outcome, "output", None)
    if not isinstance(raw_output, (tuple, list)):
        raise PartialProbeExecutionError(f"{label}.output must be a sequence")
    output = []
    for index, value in enumerate(raw_output):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7:
            raise PartialProbeExecutionError(
                f"{label}.output[{index}] must be an integer in Z/8Z"
            )
        output.append(value)
    if len(output) != channels:
        raise PartialProbeExecutionError(
            f"{label}.output width must equal the Ground channel count ({channels})"
        )
    return {"target": target, "output": output}


def _event(path: ObservationPath, stage: str):
    matches = [item for item in path.events if item.stage == stage]
    if len(matches) != 1:
        raise PartialProbeExecutionError(
            f"expected exactly one {stage!r} lifecycle event; found {len(matches)}"
        )
    return matches[0]


@dataclass(frozen=True)
class GroundRevision:
    """A new immutable VGI Ground plus the exact evidence that produced it."""

    system: object
    prior_fingerprint: str
    new_fingerprint: str
    cell_state: str
    cell_action: str
    prior_cell_status: str
    revised_cell_status: str
    evidence_refs: tuple[str, ...]
    plan_digest: str
    observed_outcome_digest: str


class PartialProbeExecution:
    """Bind one VGI partial probe score to the existing evidence-path ledger.

    The score is the result of VGI score_partial_probe. The bridge consumes its
    public fields but never executes a probe or treats its scenarios as
    evidence. External adapters report real dispatch, admission, return,
    authority, application, and ACK events through the exposed path.
    """

    def __init__(
        self,
        system: object,
        observer: object,
        score: object,
        horizon: int,
        *,
        attempt_id: str,
        query_label: str,
        vgi_revision: str,
        plan_ref: Optional[str] = None,
        authority_required: bool = True,
        application_required: bool = False,
        sender_ack_required: bool = False,
    ) -> None:
        _nonempty(attempt_id, "attempt_id")
        _nonempty(query_label, "query_label")
        revision = _nonempty(vgi_revision, "vgi_revision")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 0:
            raise PartialProbeExecutionError("horizon must be a non-negative integer")
        if not isinstance(authority_required, bool):
            raise PartialProbeExecutionError("authority_required must be boolean")
        if not isinstance(application_required, bool):
            raise PartialProbeExecutionError("application_required must be boolean")
        if not isinstance(sender_ack_required, bool):
            raise PartialProbeExecutionError("sender_ack_required must be boolean")
        if application_required and not authority_required:
            raise PartialProbeExecutionError(
                "application_required implies authority_required"
            )
        if sender_ack_required and not application_required:
            raise PartialProbeExecutionError(
                "sender_ack_required implies application_required"
            )
        if plan_ref is not None:
            _nonempty(plan_ref, "plan_ref")

        required = ("states", "actions", "channels", "status", "to_dict", "fingerprint")
        if any(not hasattr(system, name) for name in required):
            raise PartialProbeExecutionError("system does not expose the VGI Ground interface")
        if not callable(system.status) or not callable(system.to_dict):
            raise PartialProbeExecutionError("system status and to_dict must be callable")
        if not hasattr(observer, "actions") or not hasattr(observer, "channels"):
            raise PartialProbeExecutionError("observer must expose actions and channels")

        probe = getattr(score, "probe", None)
        state = _nonempty(getattr(probe, "state", None), "score.probe.state")
        action = _nonempty(getattr(probe, "action", None), "score.probe.action")
        scenarios = getattr(probe, "scenarios", None)
        if not isinstance(scenarios, (tuple, list)) or not scenarios:
            raise PartialProbeExecutionError("probe must contain at least one scenario")
        if state not in system.states or action not in system.actions:
            raise PartialProbeExecutionError("probe cell is outside the Ground schema")
        if action not in observer.actions:
            raise PartialProbeExecutionError("probe action is not visible to the observer")

        prior_status = system.status(state, action)
        if prior_status not in ("unknown", "ambiguous"):
            raise PartialProbeExecutionError(
                f"probe cell must be unknown or ambiguous, not {prior_status!r}"
            )

        cost = _exact_fraction(getattr(probe, "cost", None), "probe.cost", positive=True)
        scenario_records = []
        seen_outcomes = set()
        total_weight = Fraction(0)
        any_weight = False
        all_weight = True
        for index, scenario in enumerate(scenarios):
            record = _outcome_record(
                getattr(scenario, "outcome", None),
                len(system.channels),
                f"scenario[{index}].outcome",
            )
            if record["target"] not in system.states:
                raise PartialProbeExecutionError(
                    f"scenario[{index}] targets a state outside the Ground"
                )
            outcome_key = _canonical(record)
            if outcome_key in seen_outcomes:
                raise PartialProbeExecutionError("probe scenarios must have distinct outcomes")
            seen_outcomes.add(outcome_key)
            raw_weight = getattr(scenario, "weight", None)
            if raw_weight is None:
                all_weight = False
            else:
                any_weight = True
                weight = _exact_fraction(raw_weight, f"scenario[{index}].weight", positive=True)
                total_weight += weight
            scenario_records.append({
                "outcome": record,
                "weight": _fraction_record(raw_weight, f"scenario[{index}].weight"),
            })
        if any_weight and not all_weight:
            raise PartialProbeExecutionError(
                "scenario weights must be supplied for every scenario or none"
            )
        if all_weight and total_weight != 1:
            raise PartialProbeExecutionError("exact scenario weights must sum to one")

        ground_payload = system.to_dict()
        if not isinstance(ground_payload, Mapping):
            raise PartialProbeExecutionError("Ground to_dict() must return a mapping")
        original_fingerprint = _nonempty(system.fingerprint, "system.fingerprint")
        source_cell = None
        for item in ground_payload.get("observations", []):
            if item.get("source") == state and item.get("action") == action:
                source_cell = item
                break

        def metric(name):
            value = getattr(score, name, None)
            if value is None:
                return None
            if name in ("minimum_resolved_pairs", "maximum_resolved_pairs", "affected_pairs"):
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise PartialProbeExecutionError(
                        f"score.{name} must be a non-negative integer"
                    )
                return value
            return _fraction_record(value, f"score.{name}")

        scenario_score_records = []
        raw_scenario_scores = getattr(score, "scenario_scores", ())
        if not isinstance(raw_scenario_scores, (tuple, list)) or len(raw_scenario_scores) != len(scenario_records):
            raise PartialProbeExecutionError(
                "score.scenario_scores must align one-for-one with proposed scenarios"
            )
        for index, item in enumerate(raw_scenario_scores):
            observed_scenario = _outcome_record(
                getattr(item, "outcome", None),
                len(system.channels),
                f"score.scenario_scores[{index}].outcome",
            )
            if observed_scenario != scenario_records[index]["outcome"]:
                raise PartialProbeExecutionError(
                    "scenario score outcome does not match the proposed scenario at the same index"
                )
            raw_weight = getattr(item, "weight", None)
            if _fraction_record(raw_weight, f"score.scenario_scores[{index}].weight") != scenario_records[index]["weight"]:
                raise PartialProbeExecutionError(
                    "scenario score weight does not match the proposed scenario"
                )
            counts = {}
            for field_name in (
                "unresolved_before", "unresolved_after",
                "resolved_pairs", "new_distinguishing_witnesses",
            ):
                value = getattr(item, field_name, None)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise PartialProbeExecutionError(
                        f"score.scenario_scores[{index}].{field_name} must be a non-negative integer"
                    )
                counts[field_name] = value
            scenario_score_records.append({
                "outcome": observed_scenario,
                "weight": scenario_records[index]["weight"],
                **counts,
            })

        estimation_kind = _nonempty(
            getattr(score, "estimation_kind", None), "score.estimation_kind"
        )
        plan = {
            "format": PLAN_FORMAT,
            "source": {
                "repository": "Kier73/Virtual-Ground-Interpreter",
                "revision": revision,
                "planner": "vgi.partial_attention.score_partial_probe",
            },
            "ground": {
                "fingerprint": original_fingerprint,
                "cell_status": prior_status,
                "cell_record": source_cell,
            },
            "observer": {
                "actions": list(observer.actions),
                "channels": list(observer.channels),
            },
            "horizon": horizon,
            "probe": {
                "state": state,
                "action": action,
                "cost": {
                    "numerator": cost.numerator,
                    "denominator": cost.denominator,
                },
                "scenarios": scenario_records,
            },
            "score": {
                "estimation_kind": estimation_kind,
                "affected_pairs": metric("affected_pairs"),
                "minimum_resolved_pairs": metric("minimum_resolved_pairs"),
                "maximum_resolved_pairs": metric("maximum_resolved_pairs"),
                "expected_resolved_pairs": metric("expected_resolved_pairs"),
                "expected_gain_per_cost": metric("expected_gain_per_cost"),
                "scenario_scores": scenario_score_records,
            },
        }
        plan_digest = _digest(plan)
        scenario_digest = _digest({
            "ground_fingerprint": original_fingerprint,
            "state": state,
            "action": action,
            "scenarios": scenario_records,
        })
        resolved_plan_ref = plan_ref or f"urn:sha256:{plan_digest}"

        self.system = system
        self.observer = observer
        self.score = score
        self.horizon = horizon
        self.vgi_revision = revision
        self.state = state
        self.action = action
        self.cost = cost
        self.scenarios = tuple(scenario_records)
        self.prior_status = prior_status
        self.prior_fingerprint = original_fingerprint
        self.plan_digest = plan_digest
        self.scenario_digest = scenario_digest
        self.plan_ref = resolved_plan_ref
        self._plan_json = _canonical(plan)
        self._interpretation: Optional[dict[str, Any]] = None
        self._revision_built = False
        self.path = ObservationPath(ObservationIntent(
            attempt_id=attempt_id,
            candidate_name=f"vgi-cell:{state}:{action}",
            query=query_label,
            hypothesis_set_digest=original_fingerprint,
            estimated_cost=float(cost),
            plan_ref=resolved_plan_ref,
            authority_required=authority_required,
            application_required=application_required,
            sender_ack_required=sender_ack_required,
        ))

    @property
    def status(self) -> str:
        return self.path.status

    @property
    def plan(self) -> dict[str, Any]:
        """Return a fresh copy of the digest-bound proposal."""
        return json.loads(self._plan_json)

    def mark_dispatched(self, actor: str, evidence_ref: str, **kwargs):
        return self.path.append("dispatched", actor, evidence_ref=evidence_ref, **kwargs)

    def mark_admitted(self, actor: str, evidence_ref: str, **kwargs):
        return self.path.append("admitted", actor, evidence_ref=evidence_ref, **kwargs)

    def record_return(
        self,
        actor: str,
        *,
        evidence_ref: str,
        encounter_id: str,
        payload_digest: str,
        canonicalization: str,
        **kwargs,
    ):
        """Record an admitted raw return; interpretation remains a later stage."""
        return self.path.append(
            "returned",
            actor,
            evidence_ref=evidence_ref,
            details={
                "encounter_id": encounter_id,
                "payload_digest": payload_digest,
                "canonicalization": canonicalization,
                "plan_digest": self.plan_digest,
                "scenario_digest": self.scenario_digest,
            },
            **kwargs,
        )

    def record_unadmitted_return(
        self,
        actor: str,
        *,
        evidence_ref: str,
        encounter_id: str,
        payload_digest: str,
        canonicalization: str,
        **kwargs,
    ):
        """Preserve an unadmitted return as a terminal path, never a Ground update."""
        return self.path.append(
            "returned_unadmitted",
            actor,
            evidence_ref=evidence_ref,
            details={
                "encounter_id": encounter_id,
                "payload_digest": payload_digest,
                "canonicalization": canonicalization,
                "plan_digest": self.plan_digest,
                "scenario_digest": self.scenario_digest,
            },
            **kwargs,
        )

    def interpret(
        self,
        outcome: object,
        *,
        actor: str,
        interpretation_ref: str,
        method: str = "exact-vgi-transition-outcome-match",
        **kwargs,
    ) -> dict[str, Any]:
        """Compare a real interpreted return with scenarios; never mutate Ground."""
        if self._interpretation is not None:
            raise PartialProbeExecutionError("this attempt already has an interpretation")
        actor = _nonempty(actor, "actor")
        interpretation_ref = _nonempty(interpretation_ref, "interpretation_ref")
        method = _nonempty(method, "method")
        if self.path.status not in (
            "returned", "evidence_authorized", "applied", "sender_acknowledged"
        ):
            raise PartialProbeExecutionError(
                f"cannot interpret an attempt at lifecycle stage {self.path.status!r}"
            )

        actual = _outcome_record(outcome, len(self.system.channels), "observed_outcome")
        if actual["target"] not in self.system.states:
            raise PartialProbeExecutionError("observed outcome target is outside the Ground")
        actual_digest = _digest(actual)
        matches = [
            index for index, scenario in enumerate(self.scenarios)
            if scenario["outcome"] == actual
        ]
        matched_index = matches[0] if matches else None
        interpretation = {
            "outcome": actual,
            "outcome_digest": actual_digest,
            "scenario_match": matched_index is not None,
            "matched_scenario_index": matched_index,
            "plan_digest": self.plan_digest,
            "scenario_digest": self.scenario_digest,
        }
        self.path.append(
            "interpreted",
            actor,
            evidence_ref=interpretation_ref,
            details={
                "method": method,
                "plan_digest": self.plan_digest,
                "scenario_digest": self.scenario_digest,
                **interpretation,
            },
            **kwargs,
        )
        self._interpretation = interpretation
        if matched_index is None:
            self.path.append(
                "unresolved",
                actor,
                evidence_ref=interpretation_ref,
                details={
                    "reason": "observed_outcome_outside_proposed_scenario_set",
                    "plan_digest": self.plan_digest,
                    "scenario_digest": self.scenario_digest,
                    "outcome_digest": actual_digest,
                },
            )
            return {**interpretation, "status": "unmodeled_outcome"}
        return {**interpretation, "status": "scenario_matched_not_yet_adjudicated"}

    def propose_hypothesis_revision(
        self,
        ledger: object,
        hypothesis_id: str,
        description: str,
        *,
        proposal_method: str = "vgi-partial-probe-mismatch-v1",
        proposer: str = "vgi-partial-probe-bridge",
    ):
        """Pass a genuine out-of-scenario return to the append-only revision ledger.

        This only creates a proposed candidate. It does not validate or activate
        a hypothesis and does not revise the VGI Ground. The mismatch must be
        this attempt's own terminal unresolved result, with a dispatched,
        admitted, returned, and interpreted path.
        """
        if self.path.status != "unresolved":
            raise PartialProbeExecutionError(
                "hypothesis proposals require this attempt to terminate unresolved"
            )
        if self._interpretation is None or self._interpretation["scenario_match"]:
            raise PartialProbeExecutionError(
                "only an interpreted outcome outside the proposal scenarios can seed a hypothesis"
            )
        unresolved = _event(self.path, "unresolved")
        if unresolved.details.get("reason") != "observed_outcome_outside_proposed_scenario_set":
            raise PartialProbeExecutionError(
                "unresolved reason is not a VGI partial-probe scenario mismatch"
            )
        for stage in ("dispatched", "admitted", "returned", "interpreted"):
            _event(self.path, stage)

        returned = _event(self.path, "returned")
        interpreted = _event(self.path, "interpreted")
        returned_details = returned.details
        interpreted_details = interpreted.details
        for label, details in (
            ("returned", returned_details),
            ("interpreted", interpreted_details),
            ("unresolved", unresolved.details),
        ):
            if details.get("plan_digest") != self.plan_digest:
                raise PartialProbeExecutionError(
                    f"{label} event is not bound to this probe plan"
                )
            if details.get("scenario_digest") != self.scenario_digest:
                raise PartialProbeExecutionError(
                    f"{label} event is not bound to this scenario set"
                )
        if interpreted_details.get("scenario_match") is not False:
            raise PartialProbeExecutionError(
                "interpreted event must explicitly record a scenario mismatch"
            )
        if interpreted_details.get("outcome_digest") != self._interpretation["outcome_digest"]:
            raise PartialProbeExecutionError(
                "interpreted event outcome digest does not match the recorded mismatch"
            )
        if unresolved.details.get("outcome_digest") != self._interpretation["outcome_digest"]:
            raise PartialProbeExecutionError(
                "unresolved event outcome digest does not match the recorded mismatch"
            )
        encounter_ref = _nonempty(returned.evidence_ref, "returned.evidence_ref")
        encounter_id = _nonempty(
            returned_details.get("encounter_id"), "returned.encounter_id"
        )
        payload_digest = _nonempty(
            returned_details.get("payload_digest"), "returned.payload_digest"
        )
        canonicalization = _nonempty(
            returned_details.get("canonicalization"), "returned.canonicalization"
        )
        interpretation_ref = _nonempty(
            interpreted.evidence_ref, "interpreted.evidence_ref"
        )
        propose = getattr(ledger, "propose", None)
        if not callable(propose):
            raise PartialProbeExecutionError(
                "ledger must expose the append-only propose() interface"
            )
        return propose(
            hypothesis_id,
            description,
            source_attempt_id=self.path.intent.attempt_id,
            encounter_ref=encounter_ref,
            interpretation_ref=interpretation_ref,
            proposal_method=_nonempty(proposal_method, "proposal_method"),
            proposer=_nonempty(proposer, "proposer"),
            source_encounter_id=encounter_id,
            source_payload_digest=payload_digest,
            source_canonicalization=canonicalization,
        )

    def build_ground_revision(self, current_system: object) -> GroundRevision:
        """Apply an authorized actual outcome to a new Ground value.

        Unknown cells become known from the admitted observation. Ambiguous
        cells remain ambiguous: prior alternatives are retained and the actual
        outcome is added only when it was not already present. One new observed
        return increments support_count exactly once.
        """
        if self._revision_built:
            raise PartialProbeExecutionError("a Ground revision was already built for this attempt")
        if self._interpretation is None or not self._interpretation["scenario_match"]:
            raise PartialProbeExecutionError("a matched interpreted outcome is required")
        if self.path.status != "interpreted":
            raise PartialProbeExecutionError(
                "only a matched, non-terminal interpreted path may revise the Ground"
            )
        if not self.path.intent.authority_required:
            raise PartialProbeExecutionError(
                "Ground revision requires an explicit evidence-authorization gate"
            )
        if current_system.fingerprint != self.prior_fingerprint:
            raise PartialProbeExecutionError(
                "stale proposal: current Ground fingerprint differs from the planned Ground"
            )
        authorized = _event(self.path, "evidence_authorized")
        if authorized.details.get("decision_status") != "AUTHORIZED":
            raise PartialProbeExecutionError("Ground revision requires AUTHORIZED evidence")
        returned = _event(self.path, "returned")
        interpreted = _event(self.path, "interpreted")
        if interpreted.evidence_ref is None or returned.evidence_ref is None:
            raise PartialProbeExecutionError(
                "return and interpretation evidence references are required"
            )

        payload = current_system.to_dict()
        observations = [dict(item) for item in payload["observations"]]
        cell_index = next((
            index for index, item in enumerate(observations)
            if item["source"] == self.state and item["action"] == self.action
        ), None)
        old_record = None if cell_index is None else observations[cell_index]
        old_outcomes = [] if old_record is None else list(old_record["outcomes"])
        actual = self._interpretation["outcome"]
        if old_record is None:
            revised_outcomes = [actual]
            old_support = 0
            old_evidence = []
        else:
            revised_outcomes = list(old_outcomes)
            old_support = old_record["support_count"]
            old_evidence = list(old_record.get("evidence", []))
            if actual not in revised_outcomes:
                revised_outcomes.append(actual)

        evidence_refs = []
        for event in self.path.events:
            if event.evidence_ref and event.evidence_ref not in evidence_refs:
                evidence_refs.append(event.evidence_ref)
        combined_evidence = list(old_evidence)
        for reference in evidence_refs:
            if reference not in combined_evidence:
                combined_evidence.append(reference)

        revised_record = {
            "source": self.state,
            "action": self.action,
            "outcomes": revised_outcomes,
            "support_count": old_support + 1,
            "evidence": combined_evidence,
        }
        if cell_index is None:
            observations.append(revised_record)
        else:
            observations[cell_index] = revised_record

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise PartialProbeExecutionError("Ground metadata must be a mapping")
        metadata = dict(metadata)
        history = metadata.get(HISTORY_KEY, [])
        if not isinstance(history, list):
            raise PartialProbeExecutionError(
                f"Ground metadata {HISTORY_KEY!r} must be an append-only list"
            )
        history = list(history)
        history.append({
            "attempt_id": self.path.intent.attempt_id,
            "prior_fingerprint": self.prior_fingerprint,
            "new_observation_cell": {"state": self.state, "action": self.action},
            "observed_outcome": actual,
            "observed_outcome_digest": self._interpretation["outcome_digest"],
            "plan_digest": self.plan_digest,
            "scenario_digest": self.scenario_digest,
            "vgi_revision": self.vgi_revision,
            "evidence_refs": evidence_refs,
            "prior_cell_status": self.prior_status,
            "revised_cell_status": "known" if len(revised_outcomes) == 1 else "ambiguous",
        })
        metadata[HISTORY_KEY] = history
        payload["observations"] = observations
        payload["metadata"] = metadata

        factory = getattr(type(current_system), "from_dict", None)
        if not callable(factory):
            raise PartialProbeExecutionError("Ground type must expose from_dict()")
        revised_system = factory(payload)
        revised_status = revised_system.status(self.state, self.action)
        if self.prior_status == "ambiguous" and revised_status != "ambiguous":
            raise PartialProbeExecutionError(
                "ambiguous Ground cell was incorrectly collapsed during revision"
            )
        if self.prior_status == "unknown" and revised_status != "known":
            raise PartialProbeExecutionError(
                "unknown Ground cell did not become a single observed transition"
            )

        self._revision_built = True
        return GroundRevision(
            system=revised_system,
            prior_fingerprint=self.prior_fingerprint,
            new_fingerprint=revised_system.fingerprint,
            cell_state=self.state,
            cell_action=self.action,
            prior_cell_status=self.prior_status,
            revised_cell_status=revised_status,
            evidence_refs=tuple(evidence_refs),
            plan_digest=self.plan_digest,
            observed_outcome_digest=self._interpretation["outcome_digest"],
        )


__all__ = [
    "PLAN_FORMAT",
    "HISTORY_KEY",
    "PartialProbeExecutionError",
    "GroundRevision",
    "PartialProbeExecution",
]
