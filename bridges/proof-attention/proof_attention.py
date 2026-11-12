"""Intention-scoped attention planning for VGI AND/OR proof Grounds.

This module schedules candidate tactic inspections. It does not run tactics,
construct proof terms, or establish kernel acceptance.
"""
from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


class ProofAttentionError(ValueError):
    """Invalid proof-attention request or incompatible cost evidence."""


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
        raise ProofAttentionError("proof-attention data must be finite canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    """Convert immutable mappings/tuples from VGI into canonical JSON values."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProofAttentionError(f"{label} must be non-empty text")
    return value


def _cost_record(method_id: str, record: Any) -> dict[str, Any]:
    """Validate the public provenance record returned by EmpiricalProbeCostModel."""
    if not isinstance(record, Mapping):
        raise ProofAttentionError(f"cost provenance for {method_id!r} must be an object")
    required = {
        "method_id", "operation_id", "clock_actor_id", "clock_segment_id",
        "statistic", "cost_value_ns", "cost_exact", "measured_sample_count",
        "minimum_samples", "profile_digest", "model_digest", "source_span_digests",
    }
    if not required.issubset(record):
        raise ProofAttentionError(f"cost provenance for {method_id!r} is incomplete")
    if record["method_id"] != method_id:
        raise ProofAttentionError(f"cost provenance method mismatch for {method_id!r}")
    for field in ("operation_id", "clock_actor_id", "clock_segment_id"):
        _text(record[field], f"cost provenance {field}")
    if record["statistic"] not in ("p90_ns", "p95_ns"):
        raise ProofAttentionError("cost provenance must use p90_ns or p95_ns")
    value = record["cost_value_ns"]
    samples = record["measured_sample_count"]
    minimum = record["minimum_samples"]
    if type(value) is not int or value <= 0:
        raise ProofAttentionError("empirical tactic cost must be a positive integer nanosecond value")
    if type(samples) is not int or type(minimum) is not int or minimum <= 0 or samples < minimum:
        raise ProofAttentionError("empirical tactic cost does not meet its sample threshold")
    if record["cost_exact"] != {"numerator": value, "denominator": 1}:
        raise ProofAttentionError("empirical tactic cost must retain its exact integer value")
    for field in ("profile_digest", "model_digest"):
        digest = record[field]
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ProofAttentionError(f"cost provenance {field} must be a lowercase SHA-256 digest")
    source_digests = record["source_span_digests"]
    if (
        not isinstance(source_digests, (list, tuple))
        or len(source_digests) != samples
        or any(
            not isinstance(item, str)
            or len(item) != 64
            or any(ch not in "0123456789abcdef" for ch in item)
            for item in source_digests
        )
    ):
        raise ProofAttentionError("cost provenance source spans do not match its measured sample count")
    return dict(record)


def build_proof_attention_plan(
    proof_ground: Any,
    root_obligation_ids: Sequence[str],
    *,
    cost_model: Any | None = None,
) -> dict[str, Any]:
    """Build a deterministic, intention-scoped plan over a VGI ProofGround.

    Only elaborated hyper-transitions expand the currently observed
    obligation frontier. Their subgoals are traversed as an AND bundle; distinct
    hyper-transitions remain OR alternatives. Candidate transitions are
    returned as actions but their proposed subgoals are not traversed until a
    later trace records elaboration. Timeout/rejected attempts remain visible as
    history and are never silently retried.

    root_obligation_ids are explicit active intentions. Optional cost_model may
    be an EmpiricalProbeCostModel; all candidate tactic labels must have
    comparable measured costs before any latency-based ordering is applied.
    Missing costs are never treated as zero.
    """
    if not hasattr(proof_ground, "obligation_ids") or not hasattr(proof_ground, "transitions"):
        raise ProofAttentionError("proof_ground must expose VGI ProofGround interfaces")
    if not isinstance(root_obligation_ids, Sequence) or isinstance(root_obligation_ids, (str, bytes)):
        raise ProofAttentionError("root_obligation_ids must be a non-empty sequence")
    roots = tuple(_text(item, "root obligation id") for item in root_obligation_ids)
    if not roots:
        raise ProofAttentionError("at least one active root obligation is required")
    if len(set(roots)) != len(roots):
        raise ProofAttentionError("active root obligations must be unique")

    obligation_ids = tuple(proof_ground.obligation_ids)
    known_ids = set(obligation_ids)
    if len(known_ids) != len(obligation_ids):
        raise ProofAttentionError("proof Ground contains duplicate obligation identifiers")
    unknown_roots = sorted(set(roots) - known_ids)
    if unknown_roots:
        raise ProofAttentionError(f"unknown active root obligation(s): {unknown_roots}")

    statuses: dict[str, str] = {}
    for obligation_id in obligation_ids:
        status = proof_ground.kernel_status(obligation_id)
        if status not in ("unverified", "kernel_accepted", "kernel_rejected"):
            raise ProofAttentionError(f"unsupported kernel status {status!r}")
        statuses[obligation_id] = status

    source_edges: dict[str, list[Any]] = defaultdict(list)
    transition_ids: set[str] = set()
    transition_views: list[dict[str, Any]] = []
    for edge in proof_ground.transitions:
        source_id = _text(edge.source_id, "transition source id")
        tactic = _text(edge.tactic, "transition tactic")
        transition_id = _text(edge.transition_id, "transition id")
        status = _text(edge.attempt_status, "transition attempt status")
        subgoals = tuple(edge.subgoal_ids)
        if source_id not in known_ids or any(item not in known_ids for item in subgoals):
            raise ProofAttentionError("proof transition references an undeclared obligation")
        if transition_id in transition_ids:
            raise ProofAttentionError(f"duplicate proof transition id: {transition_id}")
        transition_ids.add(transition_id)
        if status not in ("candidate", "elaborated", "timeout", "rejected"):
            raise ProofAttentionError(f"unsupported proof attempt status: {status}")
        source_edges[source_id].append(edge)
        transition_views.append({
            "transition_id": transition_id,
            "source_id": source_id,
            "tactic": tactic,
            "subgoal_ids": list(subgoals),
            "attempt_status": status,
            "evidence_ref": getattr(edge, "evidence_ref", ""),
        })

    # Traverse confirmed elaborations only. Each edge is an AND bundle, while
    # distinct elaborated edges are OR alternatives. Per-root BFS handles cycles.
    roots_for: dict[str, set[str]] = defaultdict(set)
    distance: dict[str, int] = {}
    for root_id in roots:
        per_root_distance = {root_id: 0}
        pending = deque([root_id])
        while pending:
            source_id = pending.popleft()
            current_distance = per_root_distance[source_id]
            roots_for[source_id].add(root_id)
            distance[source_id] = min(distance.get(source_id, current_distance), current_distance)
            if statuses[source_id] == "kernel_accepted":
                continue
            for edge in source_edges.get(source_id, ()):
                if edge.attempt_status != "elaborated":
                    continue
                for child_id in edge.subgoal_ids:
                    candidate_distance = current_distance + 1
                    previous = per_root_distance.get(child_id)
                    if previous is None or candidate_distance < previous:
                        per_root_distance[child_id] = candidate_distance
                        pending.append(child_id)

    reachable = set(roots_for)
    frontier: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for obligation_id in sorted(reachable):
        outgoing = source_edges.get(obligation_id, ())
        candidate_edges = [edge for edge in outgoing if edge.attempt_status == "candidate"]
        elaborated_edges = [edge for edge in outgoing if edge.attempt_status == "elaborated"]
        failed_edges = [edge for edge in outgoing if edge.attempt_status in ("timeout", "rejected")]
        kernel_status = statuses[obligation_id]

        if kernel_status == "kernel_accepted":
            frontier_status = "kernel_accepted"
        elif candidate_edges:
            frontier_status = "candidate_available"
        elif elaborated_edges:
            frontier_status = "expanded_no_candidate"
        elif failed_edges:
            frontier_status = "failed_attempts_only"
        else:
            frontier_status = "no_tactic_recorded"
        frontier.append({
            "obligation_id": obligation_id,
            "kernel_status": kernel_status,
            "frontier_status": frontier_status,
            "minimum_elaboration_distance": distance[obligation_id],
            "intent_root_ids": sorted(roots_for[obligation_id]),
            "intent_root_count": len(roots_for[obligation_id]),
            "candidate_transition_ids": sorted(edge.transition_id for edge in candidate_edges),
            "elaborated_alternative_count": len(elaborated_edges),
            "failed_attempt_count": len(failed_edges),
        })

        if kernel_status == "kernel_accepted":
            continue
        active_alternative_count = len(candidate_edges) + len(elaborated_edges)
        for edge in candidate_edges:
            bundle = []
            accepted_count = 0
            rejected_count = 0
            unverified_count = 0
            for child_id in edge.subgoal_ids:
                child_status = statuses[child_id]
                accepted = child_status == "kernel_accepted"
                accepted_count += int(accepted)
                rejected_count += int(child_status == "kernel_rejected")
                unverified_count += int(child_status == "unverified")
                bundle.append({
                    "obligation_id": child_id,
                    "kernel_status": child_status,
                    "kernel_accepted": accepted,
                })
            if not bundle:
                bundle_status = "empty_bundle_still_requires_parent_kernel_receipt"
            elif accepted_count == len(bundle):
                bundle_status = "all_children_accepted_parent_still_unverified"
            else:
                bundle_status = "and_bundle_contains_unaccepted_children"
            actions.append({
                "transition_id": edge.transition_id,
                "source_obligation_id": obligation_id,
                "tactic": edge.tactic,
                "attempt_status": edge.attempt_status,
                "evidence_ref": getattr(edge, "evidence_ref", ""),
                "intent_root_ids": sorted(roots_for[obligation_id]),
                "intent_root_count": len(roots_for[obligation_id]),
                "minimum_elaboration_distance": distance[obligation_id],
                "or_alternative_count_at_source": active_alternative_count,
                "and_bundle_width": len(bundle),
                "and_bundle": bundle,
                "accepted_subgoal_count": accepted_count,
                "unverified_subgoal_count": unverified_count,
                "kernel_rejected_subgoal_count": rejected_count,
                "bundle_status": bundle_status,
                "requires_parent_kernel_receipt": True,
                "cost_provenance": None,
            })

    # Use measured costs only when every actionable tactic has sufficient
    # successful samples in the same clock domain and percentile.
    cost_status = "not_supplied" if cost_model is None else "no_candidate_actions"
    missing_methods: list[str] = []
    cost_records: dict[str, dict[str, Any]] = {}
    if cost_model is not None and actions:
        for method_id in sorted({item["tactic"] for item in actions}):
            try:
                raw_record = cost_model.provenance_for(method_id)
            except ValueError:
                missing_methods.append(method_id)
                continue
            cost_records[method_id] = _cost_record(method_id, raw_record)
        if missing_methods:
            cost_status = "incomplete_bindings"
        else:
            domains = {
                (record["clock_actor_id"], record["clock_segment_id"], record["statistic"])
                for record in cost_records.values()
            }
            if len(domains) != 1:
                raise ProofAttentionError("candidate tactic costs do not share one clock domain and percentile")
            cost_status = "comparable"
            for action in actions:
                action["cost_provenance"] = cost_records[action["tactic"]]

    use_costs = cost_status == "comparable"
    if use_costs:
        actions.sort(key=lambda item: (
            -item["intent_root_count"],
            item["minimum_elaboration_distance"],
            item["cost_provenance"]["cost_value_ns"],
            item["transition_id"],
        ))
    else:
        actions.sort(key=lambda item: (
            -item["intent_root_count"],
            item["minimum_elaboration_distance"],
            item["transition_id"],
        ))
    for rank, action in enumerate(actions, start=1):
        action["attention_rank"] = rank

    frontier.sort(key=lambda item: (
        -item["intent_root_count"],
        item["minimum_elaboration_distance"],
        item["obligation_id"],
    ))
    receipt_views = []
    for receipt in getattr(proof_ground, "receipts", ()):
        receipt_views.append({
            field: getattr(receipt, field)
            for field in (
                "obligation_id", "proof_term_fingerprint", "environment_fingerprint",
                "checker_id", "checker_version", "result", "receipt_ref",
            )
        })
    graph_core = {
        "environment": proof_ground.environment.to_dict(),
        "obligations": [
            {"obligation_id": item, "kernel_status": statuses[item]}
            for item in sorted(obligation_ids)
        ],
        "transitions": sorted(transition_views, key=lambda item: item["transition_id"]),
        "verified_kernel_receipts": sorted(receipt_views, key=lambda item: item["obligation_id"]),
        "observed_untrusted_kernel_claims": _plain(
            getattr(proof_ground, "observed_kernel_claims", ())
        ),
    }
    core = {
        "format": "in-formation.proof-attention-plan/0.1",
        "proof_ground_digest": _digest(graph_core),
        "active_root_obligation_ids": sorted(roots),
        "frontier": frontier,
        "candidate_actions": actions,
        "cost_comparison": {
            "status": cost_status,
            "ranking_applied": use_costs,
            "missing_methods": sorted(missing_methods),
            "clock_domain": (
                {
                    "actor_id": next(iter(cost_records.values()))["clock_actor_id"],
                    "segment_id": next(iter(cost_records.values()))["clock_segment_id"],
                    "statistic": next(iter(cost_records.values()))["statistic"],
                }
                if use_costs else None
            ),
        },
        "summary": {
            "active_root_count": len(roots),
            "reachable_obligation_count": len(reachable),
            "candidate_action_count": len(actions),
            "actionable_obligation_count": len({item["source_obligation_id"] for item in actions}),
            "kernel_accepted_reachable_count": sum(statuses[item] == "kernel_accepted" for item in reachable),
            "kernel_rejected_reachable_count": sum(statuses[item] == "kernel_rejected" for item in reachable),
            "unverified_reachable_count": sum(statuses[item] == "unverified" for item in reachable),
            "blocked_frontier_count": sum(item["frontier_status"] in ("failed_attempts_only", "no_tactic_recorded") for item in frontier),
        },
        "interpretation": {
            "ranking_kind": "structural_intention_triage",
            "cost_effect": "candidate_ordering_only" if use_costs else "none",
            "success_probability": None,
            "kernel_authority": "external_verified_receipt_required",
        },
    }
    return {**core, "plan_digest": _digest(core)}


__all__ = ["ProofAttentionError", "build_proof_attention_plan"]
