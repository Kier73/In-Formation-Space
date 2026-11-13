"""Evidence-gated execution of finite VGI minimax partial-probe policies.

The policy's declared scenarios are counterfactual branches, not observations.
This adapter follows one branch only after an actual outcome traverses the
existing ObservationPath and explicit evidence-authorization gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Any, Callable, Mapping, Optional

from partial_probe_execution import HISTORY_KEY, PartialProbeExecution


EXECUTION_FORMAT = "in-formation.vgi-minimax-observation-execution/0.1"
RECEIPT_FORMAT = "in-formation.vgi-minimax-decision-receipt/0.1"
GENESIS = hashlib.sha256(
    b"in-formation.vgi-minimax-decision-receipt/0.1:genesis"
).hexdigest()
USED_STAGES = {
    "dispatched", "admitted", "returned", "evidence_authorized",
    "applied", "sender_ack_progress", "sender_acknowledged", "interpreted",
}


class MinimaxPolicyExecutionError(ValueError):
    """Invalid policy, execution lifecycle, or reconstructed receipt."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise MinimaxPolicyExecutionError(f"not finite canonical JSON: {exc}") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MinimaxPolicyExecutionError(f"{label} must be non-empty text")
    return value


def _fraction(value: object, label: str) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise MinimaxPolicyExecutionError(f"{label} must be an exact rational")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise MinimaxPolicyExecutionError(f"{label} must be an exact rational") from exc


def _fraction_record(value: object, label: str) -> dict[str, int]:
    exact = _fraction(value, label)
    return {"numerator": exact.numerator, "denominator": exact.denominator}


def _outcome_record(outcome: object) -> dict[str, Any]:
    target = _text(getattr(outcome, "target", None), "outcome.target")
    output = getattr(outcome, "output", None)
    if not isinstance(output, (tuple, list)):
        raise MinimaxPolicyExecutionError("outcome.output must be a sequence")
    if any(isinstance(x, bool) or not isinstance(x, int) or not 0 <= x <= 7 for x in output):
        raise MinimaxPolicyExecutionError("outcome.output values must be integers in Z/8Z")
    return {"target": target, "output": list(output)}


def _probe_record(probe: object) -> dict[str, Any]:
    state = _text(getattr(probe, "state", None), "probe.state")
    action = _text(getattr(probe, "action", None), "probe.action")
    label = getattr(probe, "label", "")
    if not isinstance(label, str):
        raise MinimaxPolicyExecutionError("probe.label must be text")
    scenarios = getattr(probe, "scenarios", None)
    if not isinstance(scenarios, (tuple, list)) or not scenarios:
        raise MinimaxPolicyExecutionError("probe.scenarios must be non-empty")
    records = []
    for item in scenarios:
        weight = getattr(item, "weight", None)
        outcome = _outcome_record(getattr(item, "outcome", None))
        records.append({
            "outcome": outcome,
            "weight": None if weight is None else _fraction_record(weight, "scenario.weight"),
            "weight_role": "metadata_only_not_used_by_worst_case_objective",
        })
    # VGI orders branches by (target, output), not by scenario probability.
    records.sort(key=lambda item: (
        item["outcome"]["target"], tuple(item["outcome"]["output"])
    ))
    return {
        "state": state,
        "action": action,
        "label": label,
        "cost": _fraction_record(getattr(probe, "cost", None), "probe.cost"),
        "scenarios": records,
    }


def _policy_record(value: object) -> dict[str, Any]:
    to_dict = getattr(value, "to_dict", None)
    raw = to_dict() if callable(to_dict) else value
    if not isinstance(raw, Mapping):
        raise MinimaxPolicyExecutionError("policy must expose a JSON-compatible to_dict()")
    record = json.loads(_json(dict(raw)))
    claimed = record.get("policy_digest")
    core = {key: item for key, item in record.items() if key != "policy_digest"}
    if record.get("format") != "VGI-PartialProbePolicy-1" or claimed != _digest(core):
        raise MinimaxPolicyExecutionError("VGI policy format or policy_digest is invalid")
    if not isinstance(record.get("root"), Mapping):
        raise MinimaxPolicyExecutionError("VGI policy has no root node")
    return record


def _ground_semantics(system: object) -> str:
    """Compare transitions while excluding provenance and metadata added by realization."""
    payload = system.to_dict()
    required = ("states", "actions", "initial_state", "channels", "observations")
    if not isinstance(payload, Mapping) or any(key not in payload for key in required):
        raise MinimaxPolicyExecutionError("Ground snapshot is missing transition fields")
    observations = []
    for item in payload["observations"]:
        outcomes = sorted(
            (dict(row) for row in item["outcomes"]),
            key=lambda row: _json(row),
        )
        observations.append({
            "source": item["source"], "action": item["action"],
            "outcomes": outcomes, "support_count": item["support_count"],
        })
    observations.sort(key=lambda item: (item["source"], item["action"]))
    return _json({
        "states": list(payload["states"]), "actions": list(payload["actions"]),
        "initial_state": payload["initial_state"], "channels": list(payload["channels"]),
        "observations": observations,
    })


def _ground_refs(snapshot: Mapping[str, Any]) -> list[str]:
    refs: set[str] = set()
    for observation in snapshot.get("observations", []):
        for ref in observation.get("evidence", []):
            refs.add(_text(ref, "Ground evidence reference"))
    metadata = snapshot.get("metadata", {})
    history = metadata.get(HISTORY_KEY, []) if isinstance(metadata, Mapping) else []
    if not isinstance(history, list):
        raise MinimaxPolicyExecutionError("Ground revision history must be a list")
    for revision in history:
        for ref in revision.get("evidence_refs", []):
            refs.add(_text(ref, "Ground revision evidence reference"))
    return sorted(refs)


def _path_refs(path: Mapping[str, Any], *, used_only: bool = False) -> list[str]:
    refs = []
    for event in path.get("events", []):
        ref = event.get("evidence_ref")
        if ref is None or (used_only and event.get("stage") not in USED_STAGES):
            continue
        ref = _text(ref, "path evidence reference")
        if ref not in refs:
            refs.append(ref)
    return refs


def _groups(path: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for event in path.get("events", []):
        result.setdefault(event["stage"], []).append(event)
    return result


def _validate_path(path: Mapping[str, Any], attempt_id: str, probe_plan_digest: str,
                   scenario_digest: str, matched: bool) -> None:
    if path.get("attempt_id") != attempt_id:
        raise MinimaxPolicyExecutionError("path attempt identity differs")
    intent = path.get("intent")
    if not isinstance(intent, Mapping) or intent.get("authority_required") is not True:
        raise MinimaxPolicyExecutionError("minimax Ground revision requires explicit authority")
    app = intent.get("application_required")
    ack = intent.get("sender_ack_required")
    if not isinstance(app, bool) or not isinstance(ack, bool) or (ack and not app):
        raise MinimaxPolicyExecutionError("path application/ACK requirements are invalid")
    stages = [event.get("stage") for event in path.get("events", [])]
    expected = ["planned", "dispatched", "admitted", "returned", "evidence_authorized"]
    if app:
        expected.append("applied")
    if ack:
        expected.extend(x for x in stages if x == "sender_ack_progress")
        expected.append("sender_acknowledged")
    expected.append("interpreted")
    if not matched:
        expected.append("unresolved")
    if stages != expected or path.get("status") != stages[-1]:
        raise MinimaxPolicyExecutionError(f"invalid observation path stage sequence: {stages!r}")
    grouped = _groups(path)
    returned = grouped["returned"][0]["details"]
    interpreted = grouped["interpreted"][0]["details"]
    if returned.get("plan_digest") != probe_plan_digest or returned.get("scenario_digest") != scenario_digest:
        raise MinimaxPolicyExecutionError("raw return is not bound to this policy and scenario set")
    if interpreted.get("plan_digest") != probe_plan_digest or interpreted.get("scenario_digest") != scenario_digest:
        raise MinimaxPolicyExecutionError("interpretation is not bound to this policy and scenario set")
    payload_digest = _text(returned.get("payload_digest"), "returned.payload_digest")
    if len(payload_digest) != 64 or any(c not in "0123456789abcdef" for c in payload_digest):
        raise MinimaxPolicyExecutionError("returned payload digest must be lowercase SHA-256")
    _text(returned.get("encounter_id"), "returned.encounter_id")
    if interpreted.get("scenario_match") is not matched:
        raise MinimaxPolicyExecutionError("path scenario-match claim is inconsistent")


@dataclass(frozen=True)
class MinimaxStepResult:
    """One step's result and the next selected branch, when one exists."""
    status: str
    cycle_index: int
    attempt_id: str
    scenario_match: Optional[bool]
    prior_ground_fingerprint: str
    current_ground_fingerprint: str
    selected_branch_ground_fingerprint: Optional[str] = None
    next_probe: Optional[Mapping[str, Any]] = None


class MinimaxPartialProbeExecution:
    """Execute a VGI minimax tree using actual evidence-path attempts.

    Inject VGI's score_partial_probe and counterfactual_probe_ground functions.
    The adapter never dispatches a sensor or transport operation itself.
    """

    def __init__(
        self, system: object, observer: object, policy: object, *,
        score_probe: Callable[[object, object, object, int], object],
        counterfactual_ground: Callable[[object, object, object], object],
        attempt_id_prefix: str, query_label: str, vgi_revision: str,
        application_required: bool = False, sender_ack_required: bool = False,
    ) -> None:
        if not callable(score_probe) or not callable(counterfactual_ground):
            raise MinimaxPolicyExecutionError("VGI scorer and counterfactual function are required")
        if sender_ack_required and not application_required:
            raise MinimaxPolicyExecutionError("sender ACK requires receiver application")
        if not isinstance(application_required, bool) or not isinstance(sender_ack_required, bool):
            raise MinimaxPolicyExecutionError("application and ACK requirements must be boolean")
        self._policy_record = _policy_record(policy)
        self._policy_digest = self._policy_record["policy_digest"]
        self._node = getattr(policy, "root", None)
        self._horizon = getattr(policy, "horizon", None)
        if isinstance(self._horizon, bool) or not isinstance(self._horizon, int) or self._horizon < 0:
            raise MinimaxPolicyExecutionError("policy horizon must be a non-negative integer")
        self._initial_fp = _text(getattr(system, "fingerprint", None), "Ground fingerprint")
        if getattr(policy, "system_fingerprint", None) != self._initial_fp:
            raise MinimaxPolicyExecutionError("policy was not planned from the supplied Ground")
        if getattr(self._node, "ground_fingerprint", None) != self._initial_fp:
            raise MinimaxPolicyExecutionError("policy root Ground fingerprint differs")
        planned_observer = getattr(policy, "observer", None)
        if planned_observer is None or any(
            getattr(planned_observer, field, None) != getattr(observer, field, None)
            for field in ("name", "actions", "channels")
        ):
            raise MinimaxPolicyExecutionError("policy observer differs from execution observer")
        self._system = system
        self._planning_system = system
        self._expected_actual_fp = self._initial_fp
        self._observer = observer
        self._score_probe = score_probe
        self._counterfactual_ground = counterfactual_ground
        self._attempt_prefix = _text(attempt_id_prefix, "attempt_id_prefix")
        self._query_label = _text(query_label, "query_label")
        self._vgi_revision = _text(vgi_revision, "vgi_revision")
        self._application_required = application_required
        self._sender_ack_required = sender_ack_required
        self._initial_snapshot = json.loads(_json(system.to_dict()))
        self._initial_ground_refs = _ground_refs(self._initial_snapshot)
        self._cycle = 0
        self._status = "complete" if getattr(self._node, "probe", None) is None else "ready"
        self._active: Optional[PartialProbeExecution] = None
        self._active_probe: Optional[object] = None
        self._active_frontier_refs: list[str] = []
        self._history: list[dict[str, Any]] = []

    @property
    def system(self) -> object:
        return self._system

    @property
    def status(self) -> str:
        return self._status

    @property
    def active_execution(self) -> Optional[PartialProbeExecution]:
        return self._active

    @property
    def plan_digest(self) -> str:
        return self._policy_digest

    @property
    def history(self) -> tuple[dict[str, Any], ...]:
        """Completed attempts in controller order, copied as JSON data."""
        return tuple(json.loads(_json(self._history)))

    def begin_next(self) -> Optional[PartialProbeExecution]:
        """Create the next single-attempt ObservationPath for the selected policy node."""
        if self._status != "ready":
            raise MinimaxPolicyExecutionError(f"execution is {self._status}, not ready")
        if self._system.fingerprint != self._expected_actual_fp:
            raise MinimaxPolicyExecutionError("Ground changed outside this execution")
        if _ground_semantics(self._system) != _ground_semantics(self._planning_system):
            raise MinimaxPolicyExecutionError("actual Ground differs from selected policy branch")
        probe = getattr(self._node, "probe", None)
        if probe is None:
            self._status = "complete"
            return None
        if getattr(self._node, "ground_fingerprint", None) != self._planning_system.fingerprint:
            raise MinimaxPolicyExecutionError("policy node Ground fingerprint differs")
        score = self._score_probe(self._system, self._observer, probe, self._horizon)
        if _probe_record(getattr(score, "probe", None)) != _probe_record(probe):
            raise MinimaxPolicyExecutionError("VGI scorer returned a different probe")
        attempt_id = f"{self._attempt_prefix}:{self._cycle:04d}"
        self._active = PartialProbeExecution(
            self._system, self._observer, score, self._horizon,
            attempt_id=attempt_id, query_label=self._query_label,
            vgi_revision=self._vgi_revision,
            plan_ref=f"vgi-minimax-policy:{self._policy_digest}",
            authority_required=True,
            application_required=self._application_required,
            sender_ack_required=self._sender_ack_required,
        )
        self._active_probe = probe
        self._active_frontier_refs = _ground_refs(self._system.to_dict())
        self._status = "active"
        return self._active

    def _required_gate(self) -> str:
        assert self._active is not None
        intent = self._active.path.intent
        if intent.sender_ack_required:
            return "sender_acknowledged"
        if intent.application_required:
            return "applied"
        return "evidence_authorized"

    def complete_active(self, outcome: object, *, actor: str,
                        interpretation_ref: str,
                        method: str = "vgi-minimax-policy-branch-v1") -> MinimaxStepResult:
        """Follow the exact child branch selected by an admitted actual outcome."""
        if self._status != "active" or self._active is None or self._active_probe is None:
            raise MinimaxPolicyExecutionError("no active minimax probe")
        execution = self._active
        if execution.path.status != self._required_gate():
            raise MinimaxPolicyExecutionError(
                f"required evidence gate is not complete; current stage={execution.path.status}"
            )
        if self._system.fingerprint != execution.prior_fingerprint:
            raise MinimaxPolicyExecutionError("active probe is stale")
        interpretation = execution.interpret(
            outcome, actor=actor, interpretation_ref=interpretation_ref, method=method
        )
        attempt_id = execution.path.intent.attempt_id
        prior_fp = self._system.fingerprint
        path = execution.path.to_dict()
        refs = _path_refs(path)
        used = _path_refs(path, used_only=True)
        decision_base = {
            "decision_id": f"{attempt_id}:branch",
            "attempt_frontier_event_seq": len(path["events"]),
            "available_ground_evidence_refs": list(self._active_frontier_refs),
            "available_attempt_evidence_refs": refs,
            "controller_declared_used_evidence_refs": used,
            "outcome_digest": interpretation["outcome_digest"],
        }

        if not interpretation["scenario_match"]:
            decision = {
                **decision_base, "decision_kind": "model_mismatch",
                "selected_branch_index": None, "selected_branch_outcome": None,
                "selected_child_ground_fingerprint": None, "next_probe": None,
                "terminal_reason": "observed_outcome_outside_declared_scenario_set",
            }
            self._history.append({
                "cycle_index": self._cycle, "attempt_id": attempt_id,
                "prior_ground_fingerprint": prior_fp,
                "policy_node_ground_fingerprint": self._node.ground_fingerprint,
                "frontier_ground_evidence_refs": list(self._active_frontier_refs),
                "selected_probe": _probe_record(self._active_probe),
                "plan_digest": self._policy_digest, "probe_plan_digest": execution.plan_digest,
                "scenario_digest": execution.scenario_digest,
                "path": path, "interpretation": interpretation, "decision": decision,
                "ground_revision": None,
            })
            self._cycle += 1
            self._active = None
            self._active_probe = None
            self._status = "model_mismatch"
            return MinimaxStepResult(
                "model_mismatch", self._cycle - 1, attempt_id, False, prior_fp, self._system.fingerprint
            )

        actual = interpretation["outcome"]
        branches = getattr(self._node, "branches", ())
        matches = [
            (index, item) for index, item in enumerate(branches)
            if _outcome_record(item.outcome) == actual
        ]
        if len(matches) != 1:
            raise MinimaxPolicyExecutionError("actual outcome does not identify exactly one policy branch")
        branch_index, branch = matches[0]
        child = branch.child
        hypothetical = self._counterfactual_ground(self._planning_system, self._active_probe, outcome)
        child_fp = _text(getattr(child, "ground_fingerprint", None), "child Ground fingerprint")
        if getattr(hypothetical, "fingerprint", None) != child_fp:
            raise MinimaxPolicyExecutionError("counterfactual reconstruction differs from VGI child")
        revision = execution.build_ground_revision(self._system)
        if _ground_semantics(revision.system) != _ground_semantics(hypothetical):
            raise MinimaxPolicyExecutionError("actual Ground revision differs from selected policy branch")
        revision_refs = list(revision.evidence_refs)
        updated_refs = _ground_refs(revision.system.to_dict())
        if updated_refs != sorted(set(self._active_frontier_refs) | set(revision_refs)):
            raise MinimaxPolicyExecutionError("Ground evidence frontier differs from observation receipts")
        child_probe = getattr(child, "probe", None)
        decision = {
            **decision_base,
            "decision_kind": "branch_selected" if child_probe is not None else "policy_terminal",
            "selected_branch_index": branch_index,
            "selected_branch_outcome": actual,
            "selected_child_ground_fingerprint": child_fp,
            "next_probe": None if child_probe is None else _probe_record(child_probe),
            "terminal_reason": getattr(child, "terminal_reason", None),
            "selection_basis": "exact_interpreted_outcome_not_scenario_weight",
        }
        ground_revision = {
            "prior_fingerprint": revision.prior_fingerprint,
            "new_fingerprint": revision.new_fingerprint,
            "evidence_refs": revision_refs,
            "plan_digest": revision.plan_digest,
            "observed_outcome_digest": revision.observed_outcome_digest,
            "prior_cell_status": revision.prior_cell_status,
            "revised_cell_status": revision.revised_cell_status,
        }
        self._history.append({
            "cycle_index": self._cycle, "attempt_id": attempt_id,
            "prior_ground_fingerprint": prior_fp,
            "policy_node_ground_fingerprint": self._node.ground_fingerprint,
            "frontier_ground_evidence_refs": list(self._active_frontier_refs),
            "selected_probe": _probe_record(self._active_probe),
            "plan_digest": self._policy_digest, "probe_plan_digest": execution.plan_digest,
            "scenario_digest": execution.scenario_digest,
            "path": path, "interpretation": interpretation, "decision": decision,
            "ground_revision": ground_revision, "updated_ground_evidence_refs": updated_refs,
        })
        self._system = revision.system
        self._expected_actual_fp = revision.new_fingerprint
        self._planning_system = hypothetical
        self._node = child
        self._cycle += 1
        self._active = None
        self._active_probe = None
        self._status = "complete" if child_probe is None else "ready"
        return MinimaxStepResult(
            "policy_terminal" if child_probe is None else "ground_revised",
            self._cycle - 1, attempt_id, True, prior_fp, self._system.fingerprint,
            child_fp, None if child_probe is None else _probe_record(child_probe),
        )

    def finish_terminal_attempt(self) -> MinimaxStepResult:
        """Preserve a failed attempt without converting it into an observation."""
        if self._status != "active" or self._active is None:
            raise MinimaxPolicyExecutionError("no active minimax probe")
        execution = self._active
        terminal = execution.path.status
        allowed = {
            "dispatch_failed", "rejected", "returned_unadmitted", "evidence_refused",
            "no_result", "application_failed", "interpretation_failed",
        }
        if not execution.path.terminal or terminal not in allowed:
            raise MinimaxPolicyExecutionError("attempt is not a terminal non-observation")
        if self._system.fingerprint != execution.prior_fingerprint:
            raise MinimaxPolicyExecutionError("Ground changed during failed attempt")
        attempt_id = execution.path.intent.attempt_id
        self._history.append({
            "cycle_index": self._cycle, "attempt_id": attempt_id,
            "prior_ground_fingerprint": self._system.fingerprint,
            "policy_node_ground_fingerprint": self._node.ground_fingerprint,
            "frontier_ground_evidence_refs": list(self._active_frontier_refs),
            "selected_probe": _probe_record(self._active_probe),
            "plan_digest": self._policy_digest, "probe_plan_digest": execution.plan_digest,
            "scenario_digest": execution.scenario_digest,
            "path": execution.path.to_dict(), "interpretation": None,
            "decision": None, "ground_revision": None, "terminal_status": terminal,
        })
        self._cycle += 1
        self._active = None
        self._active_probe = None
        self._status = "ready"
        return MinimaxStepResult(
            f"attempt_{terminal}", self._cycle - 1, attempt_id, None,
            self._system.fingerprint, self._system.fingerprint,
        )

    def to_dict(self) -> dict[str, Any]:
        """Export execution history and the initial Ground needed for reconstruction."""
        return {
            "format": EXECUTION_FORMAT, "status": self._status,
            "cycle_index": self._cycle, "plan_digest": self._policy_digest,
            "vgi_revision": self._vgi_revision, "horizon": self._horizon,
            "initial_ground_fingerprint": self._initial_fp,
            "current_ground_fingerprint": self._system.fingerprint,
            "initial_ground_snapshot": self._initial_snapshot,
            "history": json.loads(_json(self._history)),
            "active_attempt": None if self._active is None else {
                "attempt_id": self._active.path.intent.attempt_id,
                "path": self._active.path.to_dict(),
                "selected_probe": _probe_record(self._active_probe),
            },
        }


def _rebuild_receipt(execution: Mapping[str, Any], policy: Mapping[str, Any]):
    if execution.get("format") != EXECUTION_FORMAT or execution.get("plan_digest") != policy["policy_digest"]:
        raise MinimaxPolicyExecutionError("execution format or policy binding is invalid")
    if execution.get("active_attempt") is not None:
        raise MinimaxPolicyExecutionError("cannot seal a receipt while an attempt is active")
    initial = execution.get("initial_ground_snapshot")
    if not isinstance(initial, Mapping):
        raise MinimaxPolicyExecutionError("receipt requires the initial Ground snapshot")
    actual_fp = _text(execution.get("initial_ground_fingerprint"), "initial Ground fingerprint")
    if policy.get("system_fingerprint") != actual_fp or policy["root"].get("ground_fingerprint") != actual_fp:
        raise MinimaxPolicyExecutionError("policy root and initial Ground do not match")
    node = policy["root"]
    available_ground_refs = set(_ground_refs(initial))
    history = execution.get("history")
    if not isinstance(history, list):
        raise MinimaxPolicyExecutionError("execution history must be a list")
    event_log: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    previous = GENESIS

    def seal(core: dict[str, Any]) -> dict[str, Any]:
        nonlocal previous
        body = {**core, "previous_digest": previous}
        item = {**body, "event_digest": _digest(body)}
        event_log.append(item)
        previous = item["event_digest"]
        return item

    for index, item in enumerate(history):
        if item.get("cycle_index") != index:
            raise MinimaxPolicyExecutionError("cycle indexes are not contiguous")
        attempt_id = _text(item.get("attempt_id"), "attempt_id")
        if item.get("prior_ground_fingerprint") != actual_fp:
            raise MinimaxPolicyExecutionError("actual Ground fingerprint chain is broken")
        if item.get("policy_node_ground_fingerprint") != node.get("ground_fingerprint"):
            raise MinimaxPolicyExecutionError("history does not match the current policy node")
        if item.get("plan_digest") != policy["policy_digest"]:
            raise MinimaxPolicyExecutionError("history references a different VGI policy")
        frontier = sorted(available_ground_refs)
        if item.get("frontier_ground_evidence_refs") != frontier:
            raise MinimaxPolicyExecutionError("decision-time Ground evidence frontier is invalid")
        if item.get("selected_probe") != node.get("probe"):
            raise MinimaxPolicyExecutionError("selected probe differs from the policy node")
        path = item.get("path")
        if not isinstance(path, Mapping) or not path.get("events"):
            raise MinimaxPolicyExecutionError("history has no retained ObservationPath")
        for local_index, event in enumerate(path["events"], start=1):
            seal({
                "event_seq": len(event_log) + 1, "kind": "observation_path_event",
                "attempt_id": attempt_id, "attempt_event_seq": local_index,
                "event": dict(event),
            })

        decision = item.get("decision")
        interpretation = item.get("interpretation")
        if decision is None:
            terminal = item.get("terminal_status")
            if terminal not in {
                "dispatch_failed", "rejected", "returned_unadmitted", "evidence_refused",
                "no_result", "application_failed", "interpretation_failed",
            } or path.get("status") != terminal or item.get("ground_revision") is not None:
                raise MinimaxPolicyExecutionError("decision-less history is not a valid failed attempt")
            continue

        if not isinstance(decision, Mapping) or not isinstance(interpretation, Mapping):
            raise MinimaxPolicyExecutionError("completed history requires decision and interpretation")
        matched = interpretation.get("scenario_match")
        if not isinstance(matched, bool):
            raise MinimaxPolicyExecutionError("scenario_match must be boolean")
        _validate_path(path, attempt_id, _text(item.get("probe_plan_digest"), "probe_plan_digest"),
                       _text(item.get("scenario_digest"), "scenario_digest"), matched)
        outcome = interpretation.get("outcome")
        if not isinstance(outcome, Mapping) or _digest(outcome) != interpretation.get("outcome_digest"):
            raise MinimaxPolicyExecutionError("interpreted outcome digest is invalid")
        if _groups(path)["interpreted"][0]["details"].get("outcome_digest") != interpretation["outcome_digest"]:
            raise MinimaxPolicyExecutionError("path and history interpretation disagree")

        path_refs = _path_refs(path)
        used_refs = _path_refs(path, used_only=True)
        available_refs = sorted(available_ground_refs | set(path_refs))
        if decision.get("attempt_frontier_event_seq") != len(path["events"]):
            raise MinimaxPolicyExecutionError("decision does not name the complete attempt prefix")
        if decision.get("available_ground_evidence_refs") != frontier:
            raise MinimaxPolicyExecutionError("decision Ground inputs differ from its frontier")
        if decision.get("available_attempt_evidence_refs") != path_refs:
            raise MinimaxPolicyExecutionError("available attempt evidence differs from path")
        if decision.get("controller_declared_used_evidence_refs") != used_refs:
            raise MinimaxPolicyExecutionError("controller-declared evidence use differs from path")
        if not set(used_refs).issubset(available_refs):
            raise MinimaxPolicyExecutionError("decision uses evidence outside its available prefix")
        if decision.get("outcome_digest") != interpretation["outcome_digest"]:
            raise MinimaxPolicyExecutionError("decision and observed outcome digests differ")

        if not matched:
            if decision.get("decision_kind") != "model_mismatch" or item.get("ground_revision") is not None:
                raise MinimaxPolicyExecutionError("out-of-scenario observation cannot revise or branch")
            if decision.get("selected_branch_index") is not None or decision.get("selected_child_ground_fingerprint") is not None:
                raise MinimaxPolicyExecutionError("model mismatch cannot select a policy child")
            if any(branch.get("outcome") == outcome for branch in node.get("branches", [])):
                raise MinimaxPolicyExecutionError("mismatch outcome is actually declared by policy")
            kind = "model_mismatch"
        else:
            branches = node.get("branches")
            selected = [
                (j, branch) for j, branch in enumerate(branches or [])
                if branch.get("outcome") == outcome
            ]
            if len(selected) != 1:
                raise MinimaxPolicyExecutionError("observed outcome does not select exactly one policy branch")
            branch_index, branch = selected[0]
            child = branch.get("policy")
            if not isinstance(child, Mapping):
                raise MinimaxPolicyExecutionError("selected branch has no child policy")
            if decision.get("selected_branch_index") != branch_index:
                raise MinimaxPolicyExecutionError("selected branch index is inconsistent")
            if decision.get("selected_branch_outcome") != outcome:
                raise MinimaxPolicyExecutionError("selected branch outcome differs from observation")
            if decision.get("selected_child_ground_fingerprint") != child.get("ground_fingerprint"):
                raise MinimaxPolicyExecutionError("selected child fingerprint differs from policy")
            if decision.get("next_probe") != child.get("probe"):
                raise MinimaxPolicyExecutionError("next probe differs from policy child")
            kind = "branch_selected" if child.get("probe") is not None else "policy_terminal"
            if decision.get("decision_kind") != kind:
                raise MinimaxPolicyExecutionError("decision kind differs from selected child")
            revision = item.get("ground_revision")
            if not isinstance(revision, Mapping):
                raise MinimaxPolicyExecutionError("matched observation lacks a Ground revision")
            if revision.get("prior_fingerprint") != actual_fp or revision.get("plan_digest") != item.get("probe_plan_digest"):
                raise MinimaxPolicyExecutionError("Ground revision identity or policy binding differs")
            if revision.get("observed_outcome_digest") != interpretation["outcome_digest"]:
                raise MinimaxPolicyExecutionError("Ground revision is not bound to actual outcome")
            if revision.get("evidence_refs") != path_refs:
                raise MinimaxPolicyExecutionError("Ground revision evidence refs differ from path")
            actual_fp = _text(revision.get("new_fingerprint"), "new Ground fingerprint")
            available_ground_refs.update(path_refs)
            if item.get("updated_ground_evidence_refs") != sorted(available_ground_refs):
                raise MinimaxPolicyExecutionError("updated Ground evidence frontier is inconsistent")
            node = child

        if decision.get("decision_kind") != kind:
            raise MinimaxPolicyExecutionError("decision kind failed reconstruction")
        decision_event = seal({
            "event_seq": len(event_log) + 1, "kind": "branch_decision",
            "attempt_id": attempt_id,
            "decision_id": _text(decision.get("decision_id"), "decision_id"),
            "frontier_event_seq": len(event_log),
            "frontier_head_digest": previous,
            "decision_kind": kind, "policy_digest": policy["policy_digest"],
            "available_ground_evidence_refs": frontier,
            "available_evidence_refs": available_refs,
            "controller_declared_used_evidence_refs": used_refs,
            "outcome_digest": interpretation["outcome_digest"],
            "selected_branch_index": decision.get("selected_branch_index"),
            "selected_branch_outcome": decision.get("selected_branch_outcome"),
            "selected_child_ground_fingerprint": decision.get("selected_child_ground_fingerprint"),
            "next_probe": decision.get("next_probe"),
            "terminal_reason": decision.get("terminal_reason"),
            "selection_basis": decision.get("selection_basis"),
        })
        decisions.append(decision_event)

    if execution.get("cycle_index") != len(history):
        raise MinimaxPolicyExecutionError("execution cycle_index differs from history length")
    if execution.get("current_ground_fingerprint") != actual_fp:
        raise MinimaxPolicyExecutionError("final Ground fingerprint differs from reconstructed chain")
    last = history[-1] if history else None
    if last is not None and isinstance(last.get("decision"), Mapping) and last["decision"].get("decision_kind") == "model_mismatch":
        expected_status = "model_mismatch"
    elif node.get("probe") is None:
        expected_status = "complete"
    else:
        expected_status = "ready"
    if execution.get("active_attempt") is None and execution.get("status") != expected_status:
        raise MinimaxPolicyExecutionError("execution status differs from policy position")
    return event_log, decisions


def build_decision_receipt(execution_record: Mapping[str, Any],
                           policy_record: Mapping[str, Any]) -> dict[str, Any]:
    """Create a sealed, independently reconstructable decision-time receipt."""
    execution = json.loads(_json(dict(execution_record)))
    policy = _policy_record(policy_record)
    if execution.get("active_attempt") is not None:
        raise MinimaxPolicyExecutionError("finish or preserve the active attempt before sealing")
    events, decisions = _rebuild_receipt(execution, policy)
    core = {
        "schema": RECEIPT_FORMAT, "policy": policy, "execution": execution,
        "event_log": events, "decisions": decisions,
        "clock_policy": {
            "wall_clock_used": False, "global_total_order": None,
            "cross_host_elapsed_time": None,
            "ordering_scope": "one controller's retained attempt sequence",
        },
        "interpretation": (
            "Availability is reconstructed from the supplied Ground evidence and the "
            "complete current ObservationPath prefix. Controller-declared use is separate "
            "and is not proof that the referenced values caused the computation. The exact "
            "interpreted outcome selects a declared finite policy branch; scenario sets are "
            "not claims of physical exhaustiveness."
        ),
    }
    return {**core, "report_digest": _digest(core)}


def validate_decision_receipt(receipt: object) -> dict[str, Any]:
    """Rebuild policy, path, branch, frontier and hash-chain assertions."""
    if not isinstance(receipt, Mapping):
        raise MinimaxPolicyExecutionError("receipt must be a mapping")
    required = {
        "schema", "policy", "execution", "event_log", "decisions",
        "clock_policy", "interpretation", "report_digest",
    }
    if set(receipt) != required or receipt.get("schema") != RECEIPT_FORMAT:
        raise MinimaxPolicyExecutionError("receipt schema or fields are invalid")
    core = {key: value for key, value in receipt.items() if key != "report_digest"}
    if receipt.get("report_digest") != _digest(core):
        raise MinimaxPolicyExecutionError("receipt report digest is invalid")
    rebuilt = build_decision_receipt(receipt["execution"], receipt["policy"])
    if rebuilt != dict(receipt):
        raise MinimaxPolicyExecutionError("receipt differs from independent reconstruction")
    return rebuilt


__all__ = [
    "EXECUTION_FORMAT", "RECEIPT_FORMAT", "MinimaxPolicyExecutionError",
    "MinimaxStepResult", "MinimaxPartialProbeExecution",
    "build_decision_receipt", "validate_decision_receipt",
]
