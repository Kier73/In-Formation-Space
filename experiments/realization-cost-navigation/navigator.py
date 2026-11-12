"""Multi-objective navigation across verified compiler realizations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

COST_DIMENSIONS = (
    "dense_parameter_count",
    "dense_multiply_slots",
    "hidden_relu_units",
    "depth",
)


def _integer_metric(candidate: Mapping[str, Any], key: str) -> int:
    value = candidate.get(key)
    if type(value) is not int or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Return whether left is no worse in every declared cost and better in one."""
    left_values = tuple(_integer_metric(left, key) for key in COST_DIMENSIONS)
    right_values = tuple(_integer_metric(right, key) for key in COST_DIMENSIONS)
    return all(a <= b for a, b in zip(left_values, right_values)) and any(
        a < b for a, b in zip(left_values, right_values)
    )


def pareto_frontier(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Retain all nondominated routes without collapsing unlike costs into one score."""
    copied = [dict(candidate) for candidate in candidates]
    for candidate in copied:
        if not isinstance(candidate.get("compiler"), str) or not candidate["compiler"]:
            raise ValueError("every route must have a nonempty compiler name")
        for key in COST_DIMENSIONS:
            _integer_metric(candidate, key)
    return [
        candidate
        for candidate in copied
        if not any(
            other is not candidate and dominates(other, candidate)
            for other in copied
        )
    ]


def navigate(
    candidates: Sequence[Mapping[str, Any]],
    *,
    objective: str = "pareto",
    max_dense_parameter_slots: int | None = None,
    max_dense_multiply_slots: int | None = None,
) -> dict[str, Any]:
    """Filter by hard resource limits, then preserve or resolve the Pareto choices.

    Objectives are independent queries: pareto, storage, or dense_compute.
    A single-objective query uses lexicographic tie-breaking only within that
    declared objective; ties remain a set. No weighted aggregate is created.
    """
    if objective not in {"pareto", "storage", "dense_compute"}:
        raise ValueError("objective must be pareto, storage, or dense_compute")
    for label, value in (
        ("max_dense_parameter_slots", max_dense_parameter_slots),
        ("max_dense_multiply_slots", max_dense_multiply_slots),
    ):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{label} must be a non-negative integer or None")

    available = [dict(candidate) for candidate in candidates]
    for candidate in available:
        if not isinstance(candidate.get("compiler"), str) or not candidate["compiler"]:
            raise ValueError("every route must have a nonempty compiler name")
        for key in COST_DIMENSIONS:
            _integer_metric(candidate, key)

    feasible = [
        candidate
        for candidate in available
        if (
            max_dense_parameter_slots is None
            or candidate["dense_parameter_count"] <= max_dense_parameter_slots
        )
        and (
            max_dense_multiply_slots is None
            or candidate["dense_multiply_slots"] <= max_dense_multiply_slots
        )
    ]
    frontier = pareto_frontier(feasible)
    selected = list(frontier)

    if frontier and objective == "storage":
        best = min(item["dense_parameter_count"] for item in frontier)
        selected = [
            item for item in frontier if item["dense_parameter_count"] == best
        ]
    elif frontier and objective == "dense_compute":
        best = min(item["dense_multiply_slots"] for item in frontier)
        selected = [
            item for item in frontier if item["dense_multiply_slots"] == best
        ]

    return {
        "status": "feasible" if feasible else "infeasible",
        "objective": objective,
        "budget": {
            "max_dense_parameter_slots": max_dense_parameter_slots,
            "max_dense_multiply_slots": max_dense_multiply_slots,
        },
        "available_routes": sorted(item["compiler"] for item in available),
        "feasible_routes": sorted(item["compiler"] for item in feasible),
        "pareto_routes": sorted(item["compiler"] for item in frontier),
        "selected_routes": sorted(item["compiler"] for item in selected),
        "cost_dimensions": list(COST_DIMENSIONS),
        "aggregation": "none; hard constraints plus explicit independent objective",
    }
