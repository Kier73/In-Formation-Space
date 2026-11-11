"""Adaptive attention policies for sequential, outcome-dependent observation.

Unlike static observation packets, a policy chooses the next observation after
seeing the previous outcome. For a finite hypothesis set and deterministic
candidate observations, memoized subset dynamic programming finds the policy
with minimum expected additive observation cost under an explicit prior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Hashable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class AdaptiveObservation:
    name: str
    cost: float
    observe: Callable[[Hashable], Hashable]


@dataclass(frozen=True)
class PolicyNode:
    hypotheses: Tuple[Hashable, ...]
    query_result: Optional[bool]
    observation_name: Optional[str]
    branches: Tuple[Tuple[Hashable, "PolicyNode"], ...]
    expected_additional_cost: float
    worst_case_additional_cost: float


@dataclass(frozen=True)
class AdaptiveAttentionPlan:
    complete: bool
    expected_cost: Optional[float]
    worst_case_cost: Optional[float]
    policy: Optional[PolicyNode]
    selected_observations: Tuple[str, ...]
    unresolved_pairs: Tuple[Tuple[Hashable, Hashable], ...]
    solver: str


def _selected_names(root: PolicyNode) -> Tuple[str, ...]:
    ordered = []
    seen = set()

    def visit(node: PolicyNode) -> None:
        if node.observation_name is None:
            return
        if node.observation_name not in seen:
            seen.add(node.observation_name)
            ordered.append(node.observation_name)
        for _, child in node.branches:
            visit(child)

    visit(root)
    return tuple(ordered)


def select_adaptive_policy(
    hypotheses: Sequence[Hashable],
    query: Callable[[Hashable], bool],
    observations: Sequence[AdaptiveObservation],
    weights: Optional[Mapping[Hashable, float]] = None,
    max_hypotheses: int = 18,
) -> AdaptiveAttentionPlan:
    """Build a minimum expected-cost policy that resolves query truth.

    Candidate observation functions are assumed deterministic and non-
    intervening. Once an observation is taken, its outcome is known and the
    next observation may differ by branch.

    The objective is expected total cost under the supplied positive prior
    weights (uniform if omitted). The policy also reports worst-case path cost.
    If some true/false hypothesis pair produces identical outcomes for every
    available observation, no complete policy exists and that pair is exposed.
    """
    if not hypotheses:
        raise ValueError("hypotheses must contain at least one state")
    if isinstance(max_hypotheses, bool) or not isinstance(max_hypotheses, int) or max_hypotheses < 1:
        raise ValueError("max_hypotheses must be a positive integer")
    states = list(hypotheses)
    if len(states) > max_hypotheses:
        raise ValueError(
            f"exact adaptive search is limited to {max_hypotheses} hypotheses; got {len(states)}"
        )
    try:
        state_set = set(states)
    except TypeError as exc:
        raise TypeError("every hypothesis must be hashable") from exc
    if len(state_set) != len(states):
        raise ValueError("hypotheses must be unique")
    if not callable(query):
        raise TypeError("query must be callable")

    query_values = {}
    for state in states:
        value = query(state)
        if not isinstance(value, bool):
            raise TypeError("query must return bool for every hypothesis")
        query_values[state] = value

    if weights is None:
        raw_weights = {state: 1.0 for state in states}
    else:
        if set(weights) != state_set:
            raise ValueError("weights must contain exactly one entry for every hypothesis")
        raw_weights = {}
        for state in states:
            if isinstance(weights[state], bool):
                raise ValueError("hypothesis weights must be finite and positive")
            try:
                value = float(weights[state])
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("hypothesis weights must be finite and positive") from exc
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("hypothesis weights must be finite and positive")
            raw_weights[state] = value

    max_weight = max(raw_weights.values())
    scaled_weights = {state: raw_weights[state] / max_weight for state in states}
    total_weight = math.fsum(scaled_weights.values())

    candidates = list(observations)
    names = set()
    costs = []
    for candidate in candidates:
        if not isinstance(candidate.name, str) or not candidate.name.strip():
            raise ValueError("observation names must be non-empty strings")
        if candidate.name in names:
            raise ValueError(f"duplicate observation name: {candidate.name}")
        names.add(candidate.name)
        if isinstance(candidate.cost, bool):
            raise ValueError(f"observation cost must be finite and positive: {candidate.name}")
        try:
            cost = float(candidate.cost)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"observation cost must be finite and positive: {candidate.name}") from exc
        if not math.isfinite(cost) or cost <= 0.0:
            raise ValueError(f"observation cost must be finite and positive: {candidate.name}")
        if not callable(candidate.observe):
            raise TypeError(f"observation must be callable: {candidate.name}")
        costs.append(cost)

    true_states = [state for state in states if query_values[state]]
    false_states = [state for state in states if not query_values[state]]

    if not true_states or not false_states:
        result = bool(true_states)
        terminal = PolicyNode(
            hypotheses=tuple(states),
            query_result=result,
            observation_name=None,
            branches=(),
            expected_additional_cost=0.0,
            worst_case_additional_cost=0.0,
        )
        return AdaptiveAttentionPlan(
            complete=True,
            expected_cost=0.0,
            worst_case_cost=0.0,
            policy=terminal,
            selected_observations=(),
            unresolved_pairs=(),
            solver="exact-subset-dp-trivial",
        )

    # Evaluate each observation once for each hypothesis. The resulting matrix
    # is the finite experiment model over which the policy is optimized.
    observed_values = []
    for candidate in candidates:
        row = {}
        for state in states:
            value = candidate.observe(state)
            try:
                hash(value)
            except TypeError as exc:
                raise TypeError(f"observation {candidate.name} returned an unhashable value") from exc
            row[state] = value
        observed_values.append(row)

    unresolved_pairs = tuple(
        (true_state, false_state)
        for true_state in true_states
        for false_state in false_states
        if all(
            row[true_state] == row[false_state]
            for row in observed_values
        )
    )
    if unresolved_pairs:
        return AdaptiveAttentionPlan(
            complete=False,
            expected_cost=None,
            worst_case_cost=None,
            policy=None,
            selected_observations=(),
            unresolved_pairs=unresolved_pairs,
            solver="unresolvable-under-candidate-observations",
        )

    state_index = {state: index for index, state in enumerate(states)}
    full_mask = (1 << len(states)) - 1

    @lru_cache(maxsize=None)
    def solve(mask: int) -> Optional[PolicyNode]:
        members = [states[index] for index in range(len(states)) if mask & (1 << index)]
        member_results = {query_values[state] for state in members}
        if len(member_results) == 1:
            result = next(iter(member_results))
            return PolicyNode(
                hypotheses=tuple(members),
                query_result=result,
                observation_name=None,
                branches=(),
                expected_additional_cost=0.0,
                worst_case_additional_cost=0.0,
            )

        best_node = None
        best_cost = float("inf")

        for candidate_index, candidate in enumerate(candidates):
            groups = {}
            for state in members:
                outcome = observed_values[candidate_index][state]
                groups.setdefault(outcome, 0)
                groups[outcome] |= 1 << state_index[state]

            # An observation constant on this subset cannot advance the query.
            if len(groups) <= 1:
                continue

            child_nodes = []
            branch_probabilities = []
            feasible = True
            subset_weight = math.fsum(scaled_weights[state] for state in members)

            for outcome, child_mask in groups.items():
                child = solve(child_mask)
                if child is None:
                    feasible = False
                    break
                child_nodes.append((outcome, child))
                child_states = [
                    states[index]
                    for index in range(len(states))
                    if child_mask & (1 << index)
                ]
                branch_weight = math.fsum(scaled_weights[state] for state in child_states)
                branch_probabilities.append(branch_weight / subset_weight)

            if not feasible:
                continue

            cost = costs[candidate_index]
            expected = cost + math.fsum(
                probability * child.expected_additional_cost
                for probability, (_, child) in zip(branch_probabilities, child_nodes)
            )
            worst = cost + max(child.worst_case_additional_cost for _, child in child_nodes)
            if not math.isfinite(expected) or not math.isfinite(worst):
                raise ValueError("policy cost overflowed finite float range")

            if expected < best_cost:
                best_cost = expected
                best_node = PolicyNode(
                    hypotheses=tuple(members),
                    query_result=None,
                    observation_name=candidate.name,
                    branches=tuple(child_nodes),
                    expected_additional_cost=expected,
                    worst_case_additional_cost=worst,
                )

        return best_node

    root = solve(full_mask)
    if root is None:
        # The pairwise pre-check implies a complete decision tree should exist.
        # This is a defensive guard against implementation or representation bugs.
        return AdaptiveAttentionPlan(
            complete=False,
            expected_cost=None,
            worst_case_cost=None,
            policy=None,
            selected_observations=(),
            unresolved_pairs=(),
            solver="no-complete-policy-found",
        )

    return AdaptiveAttentionPlan(
        complete=True,
        expected_cost=root.expected_additional_cost,
        worst_case_cost=root.worst_case_additional_cost,
        policy=root,
        selected_observations=_selected_names(root),
        unresolved_pairs=(),
        solver="exact-adaptive-subset-dp",
    )
