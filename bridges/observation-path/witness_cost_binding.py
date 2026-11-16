"""Evidence-constrained proposal of costs for finite distinguishing observations.

Bridge the repository's operation-span profiler to the finite observation
navigator. Source spans are reconstructed by operation_spans before the adapter
chooses any costs. This is an *opt-in estimate*, never operational authority,
and the source content hashes do not authenticate the recording observer.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from operation_spans import validate_operation_cost_profiles

SCHEMA = "in-formation.observation-witness-cost-proposal/0.1"
SCOPE = "single-clock-actor-segment-successful-synchronous-calls-p95"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _bindings(entries: Sequence[tuple[str, str]], label: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(entries, (list, tuple)):
        raise ValueError(f"{label} must be a sequence of (label, operation_id) pairs")
    result: list[tuple[str, str]] = []
    labels: set[str] = set()
    for item in entries:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"{label} entries must be pairs")
        name = _nonempty(item[0], f"{label}.label")
        operation_id = _nonempty(item[1], f"{label}.operation_id")
        if name in labels:
            raise ValueError(f"duplicate {label} label: {name}")
        labels.add(name)
        result.append((name, operation_id))
    return tuple(result)


def propose_witness_cost_policy(
    profile_report: Mapping[str, Any],
    span_documents: list[Mapping[str, Any]],
    *,
    action_bindings: Sequence[tuple[str, str]],
    test_bindings: Sequence[tuple[str, str]],
    clock_actor_id: str,
    clock_segment_id: str,
    minimum_samples: int = 5,
    explicit_planning_opt_in: bool = False,
) -> dict[str, Any]:
    """Offer selected p95 nanosecond estimates only with explicit opt-in.

    Each named action/test is bound to one measured operation_id. The profile
    must be reconstructed from its *original supplied spans*; a profile digest
    alone cannot substantiate a measurement. Every selected operation must
    have enough measured successful samples and no failed or regressed spans
    in the selected actor/segment. Nothing is inferred for missing operations.

    Multiple selected operations share one clock actor and segment: independent
    hosts' recorded durations are not collapsed into a shared clock.
    """
    if explicit_planning_opt_in is not True:
        raise ValueError("empirical cost-based planning requires explicit opt-in")
    if type(minimum_samples) is not int or minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive plain integer")
    actor = _nonempty(clock_actor_id, "clock_actor_id")
    segment = _nonempty(clock_segment_id, "clock_segment_id")
    actions = _bindings(action_bindings, "action_bindings")
    tests = _bindings(test_bindings, "test_bindings")
    if not actions and not tests:
        raise ValueError("at least one action or test binding is required")

    # Validate source evidence before using any derived number as a cost.
    rebuilt = validate_operation_cost_profiles(profile_report, span_documents)
    profiles = {
        (p["operation_id"], p["clock_actor_id"], p["clock_segment_id"], p["outcome"]): p
        for p in rebuilt["profiles"]
    }

    def resolve(bindings: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
        selected = []
        for name, op in bindings:
            profile = profiles.get((op, actor, segment, "succeeded"))
            failed = profiles.get((op, actor, segment, "raised"))
            if failed is not None and failed["span_count"]:
                raise ValueError(f"operation {op!r} has raised-call evidence in selected context")
            if profile is None:
                raise ValueError(f"operation {op!r} has no successful measured profile in selected context")
            if profile["readiness"] != "descriptive_only":
                raise ValueError(f"operation {op!r} has insufficient profiler readiness")
            if profile["measured_sample_count"] < minimum_samples:
                raise ValueError(f"operation {op!r} has too few measured samples")
            if profile["clock_regressed_count"]:
                raise ValueError(f"operation {op!r} contains regressed-clock evidence")
            p95 = profile["p95_ns"]
            if type(p95) is not int or p95 < 0:
                raise ValueError(f"operation {op!r} has no integral p95 measurement")
            selected.append({
                "label": name,
                "operation_id": op,
                "cost_ns": p95,
                "measured_sample_count": profile["measured_sample_count"],
            })
        return selected

    core = {
        "schema": SCHEMA,
        "scope": SCOPE,
        "cost_unit": "synchronous-monotonic-elapsed-ns",
        "cost_statistic": "empirical-nearest-rank-p95",
        "clock_actor_id": actor,
        "clock_segment_id": segment,
        "minimum_samples": minimum_samples,
        "action_costs": resolve(actions),
        "test_costs": resolve(tests),
        "source_profile_digest": rebuilt["profile_digest"],
        "source_span_digests": list(rebuilt["source_span_digests"]),
        "status": "untrusted-operator-opt-in-proposal-only",
    }
    return {**core, "proposal_digest": _digest(core)}


def reconstruct_witness_cost_policy(
    proposal: Mapping[str, Any],
    profile_report: Mapping[str, Any],
    span_documents: list[Mapping[str, Any]],
    *,
    explicit_planning_opt_in: bool = False,
) -> dict[str, Any]:
    """Independently require exact equality with source-reconstructed proposal."""
    if not isinstance(proposal, Mapping):
        raise TypeError("proposed witness cost policy must be a mapping")
    if not isinstance(proposal.get("action_costs"), list) or not isinstance(proposal.get("test_costs"), list):
        raise ValueError("proposed action and test costs must be ordered arrays")
    def pairs(field: str) -> list[tuple[str, str]]:
        return [(item["label"], item["operation_id"]) for item in proposal[field]]
    rebuilt = propose_witness_cost_policy(
        profile_report, span_documents,
        action_bindings=pairs("action_costs"),
        test_bindings=pairs("test_costs"),
        clock_actor_id=proposal.get("clock_actor_id"),
        clock_segment_id=proposal.get("clock_segment_id"),
        minimum_samples=proposal.get("minimum_samples"),
        explicit_planning_opt_in=explicit_planning_opt_in,
    )
    if dict(proposal) != rebuilt:
        raise ValueError("cost proposal differs from exact reconstruction of source evidence")
    return rebuilt


def plan_with_empirical_costs(
    navigator: object,
    left: object,
    right: object,
    proposal: Mapping[str, Any],
    profile_report: Mapping[str, Any],
    span_documents: list[Mapping[str, Any]],
    *,
    explicit_planning_opt_in: bool = False,
) -> object:
    """Compute a plan without executing any action or admitting observations."""
    policy = reconstruct_witness_cost_policy(
        proposal, profile_report, span_documents,
        explicit_planning_opt_in=explicit_planning_opt_in,
    )
    if tuple(navigator.actions) != tuple(item["label"] for item in policy["action_costs"]):
        raise ValueError("navigator action order differs from source-bound cost policy")
    if tuple(navigator.tests) != tuple(item["label"] for item in policy["test_costs"]):
        raise ValueError("navigator test order differs from source-bound cost policy")
    return navigator.plan_min_cost(
        left, right,
        action_costs=tuple(item["cost_ns"] for item in policy["action_costs"]),
        test_costs=tuple(item["cost_ns"] for item in policy["test_costs"]),
    )
