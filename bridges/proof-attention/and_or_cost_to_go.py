"""Experimental additive AND/OR cost-to-go analysis for proof Grounds.

This is a comparison planner, not a replacement for structural proof attention.
It estimates a conditional continuation tree from a VGI ProofGround while
keeping candidate and elaborated transitions, AND bundles, OR alternatives,
and verified-kernel receipts distinct.

Candidate tactic costs come from EmpiricalProbeCostModel provenance. Previously
elaborated transitions have zero *remaining* tactic cost because that operation
has already occurred. The returned sum is a planning proxy, not a percentile
of end-to-end proof completion.
"""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Any

from proof_attention import build_proof_attention_plan


class AndOrCostToGoError(ValueError):
    """Invalid proof graph or insufficient empirical cost evidence."""


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
        raise AndOrCostToGoError(
            "cost-to-go data must be finite canonical JSON"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise AndOrCostToGoError(f"{label} must be non-empty text")
    return value


def _sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AndOrCostToGoError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_cost_record(method_id: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise AndOrCostToGoError(
            f"cost provenance for {method_id!r} must be an object"
        )
    record = dict(raw)
    required = {
        "method_id",
        "operation_id",
        "clock_actor_id",
        "clock_segment_id",
        "outcome",
        "statistic",
        "cost_value_ns",
        "cost_exact",
        "measured_sample_count",
        "minimum_samples",
        "profile_digest",
        "model_digest",
        "source_span_digests",
    }
    if not required.issubset(record):
        raise AndOrCostToGoError(
            f"cost provenance for {method_id!r} is incomplete"
        )
    if record["method_id"] != method_id:
        raise AndOrCostToGoError(
            f"cost provenance method mismatch for {method_id!r}"
        )
    for field in ("operation_id", "clock_actor_id", "clock_segment_id"):
        _text(record[field], f"{method_id}.{field}")
    if record["outcome"] != "succeeded":
        raise AndOrCostToGoError(
            f"{method_id}: only successful operation samples may price a candidate"
        )
    if record["statistic"] not in ("p90_ns", "p95_ns"):
        raise AndOrCostToGoError(
            f"{method_id}: statistic must be p90_ns or p95_ns"
        )

    value = record["cost_value_ns"]
    samples = record["measured_sample_count"]
    minimum = record["minimum_samples"]
    if type(value) is not int or value <= 0:
        raise AndOrCostToGoError(
            f"{method_id}: measured cost must be a positive integer nanosecond value"
        )
    if (
        type(samples) is not int
        or type(minimum) is not int
        or minimum <= 0
        or samples < minimum
    ):
        raise AndOrCostToGoError(
            f"{method_id}: measured sample count is below the required threshold"
        )
    if record["cost_exact"] != {"numerator": value, "denominator": 1}:
        raise AndOrCostToGoError(
            f"{method_id}: exact cost must preserve its integer nanosecond value"
        )
    _sha256(record["profile_digest"], f"{method_id}.profile_digest")
    _sha256(record["model_digest"], f"{method_id}.model_digest")
    source_digests = record["source_span_digests"]
    if (
        not isinstance(source_digests, (list, tuple))
        or len(source_digests) != samples
    ):
        raise AndOrCostToGoError(
            f"{method_id}: source-span digests must match the measured sample count"
        )
    for index, digest in enumerate(source_digests):
        _sha256(digest, f"{method_id}.source_span_digests[{index}]")
    record["source_span_digests"] = list(source_digests)
    return record


def _transition_record(edge: Any, known_ids: set[str]) -> dict[str, Any]:
    source_id = _text(getattr(edge, "source_id", None), "transition source_id")
    tactic = _text(getattr(edge, "tactic", None), "transition tactic")
    transition_id = _text(
        getattr(edge, "transition_id", None), "transition transition_id"
    )
    status = getattr(edge, "attempt_status", None)
    if status not in ("candidate", "elaborated", "timeout", "rejected"):
        raise AndOrCostToGoError(
            f"transition {transition_id!r} has unsupported attempt status"
        )
    raw_children = getattr(edge, "subgoal_ids", None)
    if not isinstance(raw_children, Sequence) or isinstance(
        raw_children, (str, bytes)
    ):
        raise AndOrCostToGoError(
            f"transition {transition_id!r} subgoal_ids must be a sequence"
        )
    children = tuple(
        _text(item, f"transition {transition_id}.subgoal_id")
        for item in raw_children
    )
    if len(set(children)) != len(children):
        raise AndOrCostToGoError(
            f"transition {transition_id!r} repeats a subgoal"
        )
    if source_id not in known_ids or any(item not in known_ids for item in children):
        raise AndOrCostToGoError(
            f"transition {transition_id!r} references an undeclared obligation"
        )
    evidence_ref = getattr(edge, "evidence_ref", "")
    if not isinstance(evidence_ref, str):
        raise AndOrCostToGoError(
            f"transition {transition_id!r} evidence_ref must be text"
        )
    return {
        "transition_id": transition_id,
        "source_id": source_id,
        "tactic": tactic,
        "subgoal_ids": children,
        "attempt_status": status,
        "evidence_ref": evidence_ref,
    }


def build_and_or_cost_to_go(
    proof_ground: Any,
    root_obligation_ids: Sequence[str],
    *,
    cost_model: Any | None = None,
) -> dict[str, Any]:
    """Build independent conditional cost-to-go plans for explicit root goals.

    The recurrence minimizes a lexicographic tuple:
      1. sum of measured candidate-operation percentile values;
      2. number of candidate tactic actions;
      3. number of selected hyper-transitions;
      4. stable transition identifier.

    Each hyper-transition is one OR alternative; its complete subgoal bundle
    is an AND requirement. Candidate edges carry measured costs. Elaborated
    edges carry zero remaining tactic cost but still require their children.
    Only a separately verified kernel receipt makes an obligation terminal.

    Candidate children remain conditional in the output. Their proposed
    continuation is an estimate, not an assertion that a tactic will elaborate
    to those children. Repeated obligation occurrences are costed per
    occurrence rather than globally shared.
    """
    if not hasattr(proof_ground, "obligation_ids") or not hasattr(
        proof_ground, "transitions"
    ) or not callable(getattr(proof_ground, "kernel_status", None)):
        raise AndOrCostToGoError(
            "proof_ground must expose VGI ProofGround interfaces"
        )
    if not isinstance(root_obligation_ids, Sequence) or isinstance(
        root_obligation_ids, (str, bytes)
    ):
        raise AndOrCostToGoError(
            "root_obligation_ids must be a non-empty sequence"
        )
    roots = tuple(
        _text(item, "root obligation id") for item in root_obligation_ids
    )
    if not roots:
        raise AndOrCostToGoError("at least one active root obligation is required")
    if len(set(roots)) != len(roots):
        raise AndOrCostToGoError("active root obligations must be unique")

    obligation_ids = tuple(
        _text(item, "proof Ground obligation id")
        for item in proof_ground.obligation_ids
    )
    known_ids = set(obligation_ids)
    if len(known_ids) != len(obligation_ids):
        raise AndOrCostToGoError(
            "proof Ground contains duplicate obligation identifiers"
        )
    unknown_roots = sorted(set(roots) - known_ids)
    if unknown_roots:
        raise AndOrCostToGoError(
            f"unknown active root obligation(s): {unknown_roots}"
        )

    # Reuse the existing planner's complete Ground validation and digest
    # semantics. Its ranking is kept as a separate structural baseline.
    structural_plan = build_proof_attention_plan(proof_ground, roots)
    statuses: dict[str, str] = {}
    for obligation_id in obligation_ids:
        status = proof_ground.kernel_status(obligation_id)
        if status not in ("unverified", "kernel_accepted", "kernel_rejected"):
            raise AndOrCostToGoError(
                f"unsupported kernel status {status!r}"
            )
        statuses[obligation_id] = status

    transitions: dict[str, dict[str, Any]] = {}
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_edge in proof_ground.transitions:
        edge = _transition_record(raw_edge, known_ids)
        transition_id = edge["transition_id"]
        if transition_id in transitions:
            raise AndOrCostToGoError(
                f"duplicate transition identifier: {transition_id}"
            )
        transitions[transition_id] = edge
        outgoing[edge["source_id"]].append(edge)
    for edges in outgoing.values():
        edges.sort(key=lambda item: item["transition_id"])

    # Find every obligation that can occur in a continuation from an active
    # root. Candidate descendants are included but remain marked conditional.
    relevant_nodes: set[str] = set()
    relevant_transition_ids: set[str] = set()
    queue = deque(roots)
    while queue:
        source_id = queue.popleft()
        if source_id in relevant_nodes:
            continue
        relevant_nodes.add(source_id)
        if statuses[source_id] == "kernel_accepted":
            continue
        for edge in outgoing.get(source_id, ()):
            if edge["attempt_status"] not in ("candidate", "elaborated"):
                continue
            relevant_transition_ids.add(edge["transition_id"])
            queue.extend(edge["subgoal_ids"])

    candidate_methods = sorted({
        transitions[transition_id]["tactic"]
        for transition_id in relevant_transition_ids
        if transitions[transition_id]["attempt_status"] == "candidate"
    })
    cost_records: dict[str, dict[str, Any]] = {}
    if candidate_methods and cost_model is None:
        raise AndOrCostToGoError(
            "an empirical cost model is required for every reachable candidate tactic"
        )
    for method_id in candidate_methods:
        try:
            raw_record = cost_model.provenance_for(method_id)
        except (KeyError, TypeError, ValueError) as exc:
            raise AndOrCostToGoError(
                f"{method_id}: no valid empirical cost provenance is available"
            ) from exc
        cost_records[method_id] = _validate_cost_record(method_id, raw_record)

    domains = {
        (
            item["clock_actor_id"],
            item["clock_segment_id"],
            item["statistic"],
            item["profile_digest"],
            item["model_digest"],
        )
        for item in cost_records.values()
    }
    if len(domains) > 1:
        raise AndOrCostToGoError(
            "all candidate tactic costs must share one clock domain, percentile, profile and model"
        )

    # Compute a least finite derivation. Every selected hyperedge contributes
    # one structural step, including zero-remaining-cost elaborated edges.
    # This tie-break prevents a zero-cost elaborated cycle from being preferred
    # over an equally priced finite continuation.
    scores: dict[str, tuple[int, int, int] | None] = {
        obligation_id: (
            (0, 0, 0)
            if statuses[obligation_id] == "kernel_accepted"
            else None
        )
        for obligation_id in obligation_ids
    }
    selected: dict[str, str] = {}
    edge_costs = {
        transition_id: (
            cost_records[edge["tactic"]]["cost_value_ns"]
            if edge["attempt_status"] == "candidate"
            else 0
        )
        for transition_id, edge in transitions.items()
        if transition_id in relevant_transition_ids
    }

    converged = False
    # A minimum finite derivation never needs a repeated obligation along one
    # path: removing a cycle cannot increase latency and strictly reduces the
    # selected-edge count. n+1 synchronous rounds therefore suffice.
    for _round in range(len(obligation_ids) + 1):
        next_scores = dict(scores)
        next_selected = dict(selected)
        for source_id in sorted(relevant_nodes):
            if statuses[source_id] == "kernel_accepted":
                continue
            for edge in outgoing.get(source_id, ()):
                transition_id = edge["transition_id"]
                if transition_id not in relevant_transition_ids:
                    continue
                child_scores = [scores[item] for item in edge["subgoal_ids"]]
                if any(item is None for item in child_scores):
                    continue
                child_values = [item for item in child_scores if item is not None]
                is_candidate = edge["attempt_status"] == "candidate"
                proposal = (
                    edge_costs[transition_id] + sum(item[0] for item in child_values),
                    int(is_candidate) + sum(item[1] for item in child_values),
                    1 + sum(item[2] for item in child_values),
                )
                current = next_scores[source_id]
                current_id = next_selected.get(source_id)
                if current is None or (
                    proposal,
                    transition_id,
                ) < (current, current_id or "\uffff"):
                    next_scores[source_id] = proposal
                    next_selected[source_id] = transition_id
        changed = next_scores != scores or next_selected != selected
        scores, selected = next_scores, next_selected
        if not changed:
            converged = True
            break
    if not converged:
        raise AndOrCostToGoError(
            "finite cost-to-go relaxation did not converge within the obligation bound"
        )

    # The confirmed frontier follows only already-elaborated hyper-transitions.
    # Candidate subgoals do not become currently actionable by being planned.
    confirmed_frontier: set[str] = set()
    queue = deque(roots)
    while queue:
        source_id = queue.popleft()
        if source_id in confirmed_frontier:
            continue
        confirmed_frontier.add(source_id)
        if statuses[source_id] == "kernel_accepted":
            continue
        for edge in outgoing.get(source_id, ()):
            if edge["attempt_status"] == "elaborated":
                queue.extend(edge["subgoal_ids"])

    def render_node(
        obligation_id: str,
        path: frozenset[str],
        *,
        is_root: bool = False,
    ) -> dict[str, Any]:
        status = statuses[obligation_id]
        activation = (
            "active_intention"
            if is_root
            else (
                "confirmed_frontier"
                if obligation_id in confirmed_frontier
                else "conditional_on_candidate_elaboration"
            )
        )
        common = {
            "obligation_id": obligation_id,
            "kernel_status": status,
            "activation": activation,
            "requires_verified_kernel_receipt": status != "kernel_accepted",
        }
        if status == "kernel_accepted":
            return {
                **common,
                "route_status": "kernel_accepted",
                "summed_component_cost_ns": 0,
                "candidate_action_count": 0,
                "selected_transition": None,
                "children": [],
            }
        score = scores[obligation_id]
        transition_id = selected.get(obligation_id)
        if score is None or transition_id is None:
            return {
                **common,
                "route_status": "no_finite_route",
                "summed_component_cost_ns": None,
                "candidate_action_count": None,
                "selected_transition": None,
                "children": [],
            }
        if obligation_id in path:
            raise AndOrCostToGoError(
                "selected continuation unexpectedly contains a cycle"
            )
        edge = transitions[transition_id]
        is_candidate = edge["attempt_status"] == "candidate"
        provenance = cost_records.get(edge["tactic"]) if is_candidate else None
        children = [
            render_node(
                child_id,
                path | {obligation_id},
            )
            for child_id in edge["subgoal_ids"]
        ]
        return {
            **common,
            "route_status": "finite_conditional_continuation",
            "summed_component_cost_ns": score[0],
            "candidate_action_count": score[1],
            "selected_transition": {
                "transition_id": transition_id,
                "tactic": edge["tactic"],
                "attempt_status": edge["attempt_status"],
                "incremental_cost_ns": edge_costs[transition_id],
                "cost_basis": (
                    provenance["statistic"] if provenance is not None
                    else "already_elaborated_sunk_cost"
                ),
                "cost_provenance": provenance,
                "subgoal_ids": list(edge["subgoal_ids"]),
            },
            "children": children,
        }

    def current_next_actions(
        obligation_id: str,
        path: frozenset[str],
    ) -> list[str]:
        if obligation_id not in confirmed_frontier:
            return []
        if obligation_id in path or statuses[obligation_id] == "kernel_accepted":
            return []
        transition_id = selected.get(obligation_id)
        if transition_id is None:
            return []
        edge = transitions[transition_id]
        if edge["attempt_status"] == "candidate":
            return [transition_id]
        found: list[str] = []
        for child_id in edge["subgoal_ids"]:
            found.extend(
                current_next_actions(child_id, path | {obligation_id})
            )
        return found

    root_results = []
    next_actions_by_root: dict[str, list[str]] = {}
    for root_id in roots:
        score = scores[root_id]
        plan_tree = render_node(root_id, frozenset(), is_root=True)
        next_actions = current_next_actions(root_id, frozenset())
        next_actions_by_root[root_id] = next_actions
        root_results.append({
            "root_obligation_id": root_id,
            "kernel_status": statuses[root_id],
            "estimate_status": (
                "kernel_accepted"
                if statuses[root_id] == "kernel_accepted"
                else (
                    "finite_route_found" if score is not None
                    else "no_finite_route"
                )
            ),
            "summed_component_cost_ns": (
                0 if statuses[root_id] == "kernel_accepted"
                else (score[0] if score is not None else None)
            ),
            "candidate_action_count": (
                0 if statuses[root_id] == "kernel_accepted"
                else (score[1] if score is not None else None)
            ),
            "selected_transition_id": selected.get(root_id),
            "next_action_transition_ids": next_actions,
            "requires_verified_kernel_receipt": (
                statuses[root_id] != "kernel_accepted"
            ),
            "plan": plan_tree,
        })

    if cost_records:
        first_record = next(iter(cost_records.values()))
        cost_comparison = {
            "status": "comparable",
            "statistic": first_record["statistic"],
            "clock_domain": {
                "actor_id": first_record["clock_actor_id"],
                "segment_id": first_record["clock_segment_id"],
            },
            "profile_digest": first_record["profile_digest"],
            "model_digest": first_record["model_digest"],
            "candidate_method_ids": candidate_methods,
        }
    else:
        cost_comparison = {
            "status": "not_required",
            "statistic": None,
            "clock_domain": None,
            "profile_digest": None,
            "model_digest": None,
            "candidate_method_ids": [],
        }

    core = {
        "format": "in-formation.proof-and-or-cost-to-go/0.1",
        "proof_ground_digest": structural_plan["proof_ground_digest"],
        "structural_attention_plan_digest": structural_plan["plan_digest"],
        "active_root_obligation_ids": list(roots),
        "confirmed_frontier_obligation_ids": sorted(confirmed_frontier),
        "considered_obligation_ids": sorted(relevant_nodes),
        "cost_comparison": cost_comparison,
        "roots": root_results,
        "structural_frontier_action_order": [
            item["transition_id"]
            for item in structural_plan["candidate_actions"]
        ],
        "next_action_transition_ids_by_root": next_actions_by_root,
        "policy_effect": "analysis_only",
        "interpretation_limits": [
            "The latency total is a sum of component p90 or p95 values, not that percentile of end-to-end completion time.",
            "Candidate subgoal bundles are conditional proposals until the corresponding tactic is observed as elaborated.",
            "An empty subgoal bundle does not establish kernel acceptance; a separate verified receipt is still required for each unaccepted obligation.",
            "Kernel-rejected obligations are not accepted terminals and may retain alternative candidate tactics.",
            "Repeated obligation occurrences are costed independently; this tree estimate does not optimize cross-branch proof reuse.",
            "Candidate costs describe the caller-bound synchronous operation and do not independently isolate CPU, transport, admission, provenance, or kernel-check time.",
            "Timeout and rejected tactic attempts remain historical evidence and are not treated as executable routes.",
            "The result estimates conditional execution effort only; it provides no tactic success probability, proof, or execution authorization.",
        ],
    }
    return {**core, "plan_digest": _digest(core)}


__all__ = ["AndOrCostToGoError", "build_and_or_cost_to_go"]
