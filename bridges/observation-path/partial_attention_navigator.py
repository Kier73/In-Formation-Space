"""Replan partial attention after each evidence-gated Ground revision.

This coordinator sits between VGI's probe ranker and the existing
PartialProbeExecution / ObservationPath bridge. It never dispatches transport,
authorizes evidence, or mutates a Ground in place. The host executes the
selected attempt through the ordinary observation path (and may pass that
same path to ECPUGatedObservationAdapter); the navigator only advances after
the required gates and an interpreted result are present.

Candidate generation is deliberately injected. Scenario sets are explicit
counterfactual assumptions, not predictions invented by this coordinator.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
from typing import Any, Callable, Mapping, Optional, Sequence

from partial_probe_execution import (
    GroundRevision,
    PartialProbeExecution,
    PartialProbeExecutionError,
)


class PartialAttentionNavigationError(ValueError):
    """Invalid navigation state, candidate set, or incomplete evidence path."""


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PartialAttentionNavigationError(f"{label} must be non-empty text")
    return value


def _fraction(value: object, label: str) -> Optional[dict[str, int]]:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise PartialAttentionNavigationError(f"{label} must be an exact rational")
    try:
        rational = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise PartialAttentionNavigationError(f"{label} must be an exact rational") from exc
    return {"numerator": rational.numerator, "denominator": rational.denominator}


def _outcome_record(outcome: object) -> dict[str, Any]:
    target = _nonempty(getattr(outcome, "target", None), "outcome.target")
    raw_output = getattr(outcome, "output", None)
    if not isinstance(raw_output, (tuple, list)):
        raise PartialAttentionNavigationError("outcome.output must be a sequence")
    output = []
    for index, value in enumerate(raw_output):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7:
            raise PartialAttentionNavigationError(
                f"outcome.output[{index}] must be an integer in Z/8Z"
            )
        output.append(value)
    return {"target": target, "output": output}


def _score_record(score: object, rank: int) -> dict[str, Any]:
    probe = getattr(score, "probe", None)
    state = _nonempty(getattr(probe, "state", None), "score.probe.state")
    action = _nonempty(getattr(probe, "action", None), "score.probe.action")
    cost = _fraction(getattr(probe, "cost", None), "score.probe.cost")
    scenarios = []
    for index, scenario_score in enumerate(getattr(score, "scenario_scores", ())):
        scenarios.append({
            "outcome": _outcome_record(getattr(scenario_score, "outcome", None)),
            "weight": _fraction(
                getattr(scenario_score, "weight", None),
                f"scenario_scores[{index}].weight",
            ),
            "unresolved_before": getattr(scenario_score, "unresolved_before", None),
            "unresolved_after": getattr(scenario_score, "unresolved_after", None),
            "resolved_pairs": getattr(scenario_score, "resolved_pairs", None),
            "new_distinguishing_witnesses": getattr(
                scenario_score, "new_distinguishing_witnesses", None
            ),
        })
    return {
        "rank": rank,
        "state": state,
        "action": action,
        "label": getattr(probe, "label", ""),
        "cost": cost,
        "estimation_kind": _nonempty(
            getattr(score, "estimation_kind", None), "score.estimation_kind"
        ),
        "affected_pairs": getattr(score, "affected_pairs", None),
        "minimum_resolved_pairs": getattr(score, "minimum_resolved_pairs", None),
        "maximum_resolved_pairs": getattr(score, "maximum_resolved_pairs", None),
        "expected_resolved_pairs": _fraction(
            getattr(score, "expected_resolved_pairs", None),
            "score.expected_resolved_pairs",
        ),
        "expected_gain_per_cost": _fraction(
            getattr(score, "expected_gain_per_cost", None),
            "score.expected_gain_per_cost",
        ),
        "scenario_scores": scenarios,
    }


@dataclass(frozen=True)
class PartialAttentionSelection:
    """One selected probe plus the complete ranked alternatives at its Ground."""

    cycle_index: int
    prior_ground_fingerprint: str
    ranking: tuple[dict[str, Any], ...]
    execution: PartialProbeExecution

    @property
    def selected_score(self) -> object:
        return self.execution.score

    @property
    def selected_cell(self) -> tuple[str, str]:
        return self.execution.state, self.execution.action


@dataclass(frozen=True)
class AttentionStepResult:
    """A completed cycle; a mismatch is never represented as a Ground revision."""

    status: str
    cycle_index: int
    attempt_id: str
    prior_ground_fingerprint: str
    current_ground_fingerprint: str
    selected_cell: tuple[str, str]
    scenario_match: Optional[bool]
    ground_revision: Optional[GroundRevision] = None
    hypothesis_candidate: Optional[object] = None
    interpretation: Optional[Mapping[str, Any]] = None


class PartialAttentionNavigator:
    """Select, observe, revise, and re-rank one partial transition at a time.

    probe_factory(system, observer, cycle_index) must return explicit VGI
    TransitionProbe candidates for the current Ground. ranker is normally
    VGI's rank_partial_probes callable from its pinned checkout.

    Each attempt owns one ObservationPath. The host must execute that path
    through dispatch, admission, raw return, and the configured authorization /
    application / sender-ACK gates before complete_active is accepted.
    The same attempt.path is directly compatible with the existing E-CPU
    gated adapter; no second path or parallel authority mechanism is created.
    """

    def __init__(
        self,
        system: object,
        observer: object,
        probe_factory: Callable[[object, object, int], Sequence[object]],
        ranker: Callable[[object, object, Sequence[object], int], Sequence[object]],
        horizon: int,
        *,
        attempt_id_prefix: str,
        query_label: str,
        vgi_revision: str,
        application_required: bool = False,
        sender_ack_required: bool = False,
    ) -> None:
        self._validate_ground(system)
        if not callable(probe_factory):
            raise PartialAttentionNavigationError("probe_factory must be callable")
        if not callable(ranker):
            raise TypeError("ranker must be callable")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 0:
            raise PartialAttentionNavigationError("horizon must be a non-negative integer")
        self._attempt_prefix = _nonempty(attempt_id_prefix, "attempt_id_prefix")
        self._query_label = _nonempty(query_label, "query_label")
        self._vgi_revision = _nonempty(vgi_revision, "vgi_revision")
        if not isinstance(application_required, bool):
            raise PartialAttentionNavigationError("application_required must be boolean")
        if not isinstance(sender_ack_required, bool):
            raise PartialAttentionNavigationError("sender_ack_required must be boolean")
        if sender_ack_required and not application_required:
            raise PartialAttentionNavigationError(
                "sender_ack_required implies application_required"
            )

        # A Ground revision is a state change, so this coordinator always
        # requires the explicit authority gate. Application and sender ACK are
        # additional, independently selectable gates.
        self._system = system
        self._observer = observer
        self._probe_factory = probe_factory
        self._ranker = ranker
        self._horizon = horizon
        self._application_required = application_required
        self._sender_ack_required = sender_ack_required
        self._cycle_index = 0
        self._status = "ready"
        self._active: Optional[PartialAttentionSelection] = None
        self._history: list[dict[str, Any]] = []

    @staticmethod
    def _validate_ground(system: object) -> None:
        required = ("states", "actions", "channels", "status", "to_dict", "fingerprint")
        if any(not hasattr(system, field) for field in required):
            raise PartialAttentionNavigationError("system does not expose the VGI Ground interface")
        if not callable(system.status) or not callable(system.to_dict):
            raise PartialAttentionNavigationError("Ground status and to_dict must be callable")
        _nonempty(system.fingerprint, "system.fingerprint")

    @property
    def system(self) -> object:
        """The current immutable Ground value."""
        return self._system

    @property
    def status(self) -> str:
        return self._status

    @property
    def cycle_index(self) -> int:
        return self._cycle_index

    @property
    def active_selection(self) -> Optional[PartialAttentionSelection]:
        return self._active

    @property
    def history(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(json.dumps(item)) for item in self._history)

    def preview(self) -> tuple[object, ...]:
        """Rank candidates for the current Ground without opening an attempt."""
        if self._status != "ready":
            raise PartialAttentionNavigationError(
                f"cannot rank candidates while navigator is {self._status}"
            )
        raw = self._probe_factory(self._system, self._observer, self._cycle_index)
        if raw is None:
            raise PartialAttentionNavigationError("probe_factory returned None")
        if isinstance(raw, (str, bytes)):
            raise PartialAttentionNavigationError("probe_factory must return probe objects")
        try:
            probes = tuple(raw)
        except TypeError as exc:
            raise PartialAttentionNavigationError(
                "probe_factory must return an iterable of probe objects"
            ) from exc
        if not probes:
            return ()
        names = []
        for index, probe in enumerate(probes):
            state = _nonempty(getattr(probe, "state", None), f"probes[{index}].state")
            action = _nonempty(getattr(probe, "action", None), f"probes[{index}].action")
            names.append((state, action))
        if len(set(names)) != len(names):
            raise PartialAttentionNavigationError(
                "probe_factory returned more than one proposal for the same Ground cell"
            )
        ranked = self._ranker(self._system, self._observer, probes, self._horizon)
        if not isinstance(ranked, (tuple, list)):
            raise PartialAttentionNavigationError("ranker must return a ranked sequence")
        if len(ranked) != len(probes):
            raise PartialAttentionNavigationError("ranker changed the candidate count")
        ranked_cells = []
        for index, score in enumerate(ranked):
            probe = getattr(score, "probe", None)
            cell = (
                _nonempty(getattr(probe, "state", None), f"ranked[{index}].probe.state"),
                _nonempty(getattr(probe, "action", None), f"ranked[{index}].probe.action"),
            )
            ranked_cells.append(cell)
        if len(set(ranked_cells)) != len(ranked_cells) or set(ranked_cells) != set(names):
            raise PartialAttentionNavigationError(
                "ranker must return each supplied Ground cell exactly once"
            )
        return tuple(ranked)

    def begin_next(self) -> Optional[PartialAttentionSelection]:
        """Select the highest-ranked probe and create its evidence-path intent.

        Returns None and moves to exhausted when the current Ground has no
        candidate probes. No dispatch or observation is implied by this call.
        """
        if self._status != "ready":
            raise PartialAttentionNavigationError(
                f"cannot begin a probe while navigator is {self._status}"
            )
        ranked = self.preview()
        if not ranked:
            self._status = "exhausted"
            return None

        selected = ranked[0]
        attempt_id = f"{self._attempt_prefix}:{self._cycle_index:04d}"
        execution = PartialProbeExecution(
            self._system,
            self._observer,
            selected,
            self._horizon,
            attempt_id=attempt_id,
            query_label=self._query_label,
            vgi_revision=self._vgi_revision,
            authority_required=True,
            application_required=self._application_required,
            sender_ack_required=self._sender_ack_required,
        )
        selection = PartialAttentionSelection(
            cycle_index=self._cycle_index,
            prior_ground_fingerprint=self._system.fingerprint,
            ranking=tuple(
                _score_record(score, index + 1)
                for index, score in enumerate(ranked)
            ),
            execution=execution,
        )
        self._active = selection
        self._status = "active"
        return selection

    def _required_final_gate(self, execution: PartialProbeExecution) -> str:
        if execution.path.intent.sender_ack_required:
            return "sender_acknowledged"
        if execution.path.intent.application_required:
            return "applied"
        return "evidence_authorized"

    def complete_active(
        self,
        outcome: object,
        *,
        actor: str,
        interpretation_ref: str,
        method: str = "vgi-partial-probe-navigation-v1",
        hypothesis_proposal: Optional[Mapping[str, Any]] = None,
    ) -> AttentionStepResult:
        """Interpret an actual return and advance only through a valid path.

        On a scenario match, a new immutable Ground is built and becomes the
        source for the next ranking cycle. On a mismatch, Ground stays exactly
        as it was; an optional ledger proposal is created only when the caller
        supplies all explicit candidate details.
        """
        if self._status != "active" or self._active is None:
            raise PartialAttentionNavigationError("there is no active probe to complete")
        selection = self._active
        execution = selection.execution
        required_gate = self._required_final_gate(execution)
        if execution.path.status != required_gate:
            raise PartialAttentionNavigationError(
                f"probe requires lifecycle stage {required_gate!r} before interpretation; "
                f"current stage is {execution.path.status!r}"
            )

        if self._system.fingerprint != execution.prior_fingerprint:
            raise PartialAttentionNavigationError(
                "active probe is stale relative to the current Ground fingerprint"
            )

        try:
            interpretation = execution.interpret(
                outcome,
                actor=actor,
                interpretation_ref=interpretation_ref,
                method=method,
            )
        except PartialProbeExecutionError:
            raise
        except ValueError:
            raise

        candidate = None
        revision = None
        status = interpretation["status"]
        prior_fingerprint = selection.prior_ground_fingerprint
        if status == "unmodeled_outcome":
            if hypothesis_proposal is not None:
                if not isinstance(hypothesis_proposal, Mapping):
                    raise PartialAttentionNavigationError(
                        "hypothesis_proposal must be a mapping"
                    )
                ledger = hypothesis_proposal.get("ledger")
                hypothesis_id = _nonempty(
                    hypothesis_proposal.get("hypothesis_id"),
                    "hypothesis_proposal.hypothesis_id",
                )
                description = _nonempty(
                    hypothesis_proposal.get("description"),
                    "hypothesis_proposal.description",
                )
                candidate = execution.propose_hypothesis_revision(
                    ledger,
                    hypothesis_id,
                    description,
                    proposal_method=hypothesis_proposal.get(
                        "proposal_method", "vgi-partial-probe-navigation-v1"
                    ),
                    proposer=hypothesis_proposal.get(
                        "proposer", "partial-attention-navigator"
                    ),
                )
                status = "model_mismatch_proposed"
            else:
                status = "model_mismatch"
        else:
            revision = execution.build_ground_revision(self._system)
            self._system = revision.system
            status = "ground_revised"

        self._history.append({
            "cycle_index": selection.cycle_index,
            "attempt_id": execution.path.intent.attempt_id,
            "prior_ground_fingerprint": prior_fingerprint,
            "current_ground_fingerprint": self._system.fingerprint,
            "selected_cell": {
                "state": selection.selected_cell[0],
                "action": selection.selected_cell[1],
            },
            "ranking": list(selection.ranking),
            "plan_digest": execution.plan_digest,
            "scenario_digest": execution.scenario_digest,
            "interpretation": dict(interpretation),
            "path": execution.path.to_dict(),
            "ground_revision": None if revision is None else {
                "prior_fingerprint": revision.prior_fingerprint,
                "new_fingerprint": revision.new_fingerprint,
                "prior_cell_status": revision.prior_cell_status,
                "revised_cell_status": revision.revised_cell_status,
                "evidence_refs": list(revision.evidence_refs),
            },
            "hypothesis_candidate": None if candidate is None else {
                "hypothesis_id": candidate.hypothesis_id,
                "source_attempt_id": candidate.source_attempt_id,
                "encounter_ref": candidate.encounter_ref,
                "interpretation_ref": candidate.interpretation_ref,
                "validation_result": candidate.validation_result,
            },
        })
        result = AttentionStepResult(
            status=status,
            cycle_index=selection.cycle_index,
            attempt_id=execution.path.intent.attempt_id,
            prior_ground_fingerprint=prior_fingerprint,
            current_ground_fingerprint=self._system.fingerprint,
            selected_cell=selection.selected_cell,
            scenario_match=bool(interpretation["scenario_match"]),
            ground_revision=revision,
            hypothesis_candidate=candidate,
            interpretation=dict(interpretation),
        )
        self._cycle_index += 1
        self._active = None
        self._status = "ready" if status == "ground_revised" else "model_mismatch"
        return result

    def resume_after_mismatch(
        self,
        *,
        probe_factory: Callable[[object, object, int], Sequence[object]],
    ) -> None:
        """Resume only with an explicitly replaced candidate source after model drift."""
        if self._status != "model_mismatch":
            raise PartialAttentionNavigationError(
                f"cannot resume after mismatch while navigator is {self._status}"
            )
        if not callable(probe_factory):
            raise TypeError("probe_factory must be callable")
        self._probe_factory = probe_factory
        self._status = "ready"

    def close(self) -> None:
        """Close a ready or exhausted navigator; an active attempt must first be preserved."""
        if self._status == "active":
            raise PartialAttentionNavigationError(
                "cannot close while a probe attempt is active"
            )
        self._status = "closed"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe continuity record, not the Ground's full contents."""
        return {
            "format": "in-formation.partial-attention-navigation/0.1",
            "status": self._status,
            "cycle_index": self._cycle_index,
            "current_ground_fingerprint": self._system.fingerprint,
            "vgi_revision": self._vgi_revision,
            "horizon": self._horizon,
            "application_required": self._application_required,
            "sender_ack_required": self._sender_ack_required,
            "active_attempt": None if self._active is None else {
                "attempt_id": self._active.execution.path.intent.attempt_id,
                "prior_ground_fingerprint": self._active.prior_ground_fingerprint,
                "selected_cell": {
                    "state": self._active.selected_cell[0],
                    "action": self._active.selected_cell[1],
                },
                "plan_digest": self._active.execution.plan_digest,
                "scenario_digest": self._active.execution.scenario_digest,
                "path": self._active.execution.path.to_dict(),
            },
            "history": list(self._history),
        }


__all__ = [
    "PartialAttentionNavigationError",
    "PartialAttentionSelection",
    "AttentionStepResult",
    "PartialAttentionNavigator",
]
