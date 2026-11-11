"""Cost-aware observation selection for resolving a Boolean query.

The input states are hypotheses still compatible with current evidence. A
Boolean query partitions them into true and false classes. A candidate
observation separates a cross-class pair when its predicted observation
differs under those two hypotheses.

To resolve the query without identifying the full hidden state, the selected
observation packet must separate every true/false hypothesis pair. This is a
weighted set-cover problem over the cross-boundary pairs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Hashable, Sequence, Tuple


@dataclass(frozen=True)
class QueryObservation:
    name: str
    cost: float
    observe: Callable[[Hashable], Hashable]


@dataclass(frozen=True)
class QueryAttentionPlan:
    true_hypothesis_count: int
    false_hypothesis_count: int
    cross_boundary_pair_count: int
    selected_names: Tuple[str, ...]
    total_cost: float
    separated_pair_count: int
    unresolved_pairs: Tuple[Tuple[Hashable, Hashable], ...]
    complete: bool
    exact: bool
    solver: str


def select_query_packet(
    hypotheses: Sequence[Hashable],
    query: Callable[[Hashable], bool],
    observations: Sequence[QueryObservation],
    max_exact_pairs: int = 20,
) -> QueryAttentionPlan:
    """Select a minimum-cost packet sufficient to resolve query truth.

    Every possible true-hypothesis / false-hypothesis pair must be separated
    by at least one selected observation. Differences between two hypotheses
    on the same side of the query do not matter.

    Exact bitmask DP is used when the number of cross-boundary pairs is within
    max_exact_pairs. Larger pair sets use a deterministic greedy approximation,
    labelled non-exact. Pairs that no available observation can distinguish
    are returned explicitly.
    """
    if not hypotheses:
        raise ValueError("hypotheses must contain at least one state")
    if isinstance(max_exact_pairs, bool) or not isinstance(max_exact_pairs, int) or max_exact_pairs < 1:
        raise ValueError("max_exact_pairs must be a positive integer")

    states = list(hypotheses)
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

    true_states = [state for state in states if query_values[state]]
    false_states = [state for state in states if not query_values[state]]
    pairs = [(true_state, false_state) for true_state in true_states for false_state in false_states]

    if not pairs:
        return QueryAttentionPlan(
            true_hypothesis_count=len(true_states),
            false_hypothesis_count=len(false_states),
            cross_boundary_pair_count=0,
            selected_names=(),
            total_cost=0.0,
            separated_pair_count=0,
            unresolved_pairs=(),
            complete=True,
            exact=True,
            solver="exact-trivial",
        )

    candidates = list(observations)
    names = set()
    validated = []
    for candidate in candidates:
        if not isinstance(candidate.name, str) or not candidate.name.strip():
            raise ValueError("observation names must be non-empty strings")
        if candidate.name in names:
            raise ValueError(f"duplicate observation name: {candidate.name}")
        names.add(candidate.name)
        if isinstance(candidate.cost, bool):
            raise ValueError(f"observation cost must be a finite positive number: {candidate.name}")
        try:
            cost = float(candidate.cost)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"observation cost must be a finite positive number: {candidate.name}") from exc
        if not math.isfinite(cost) or cost <= 0.0:
            raise ValueError(f"observation cost must be finite and positive: {candidate.name}")
        if not callable(candidate.observe):
            raise TypeError(f"observation must be callable: {candidate.name}")

        observed = {}
        for state in states:
            value = candidate.observe(state)
            try:
                hash(value)
            except TypeError as exc:
                raise TypeError(f"observation {candidate.name} returned an unhashable value") from exc
            observed[state] = value

        mask = 0
        for index, (true_state, false_state) in enumerate(pairs):
            if observed[true_state] != observed[false_state]:
                mask |= 1 << index
        if mask:
            validated.append((candidate.name, cost, mask))

    union_mask = 0
    for _, _, mask in validated:
        union_mask |= mask

    unresolved = tuple(
        pair for index, pair in enumerate(pairs)
        if not (union_mask & (1 << index))
    )
    coverable_indices = [
        index for index in range(len(pairs))
        if union_mask & (1 << index)
    ]
    compressed_candidates = []
    for name, cost, mask in validated:
        compressed_mask = 0
        for new_index, old_index in enumerate(coverable_indices):
            if mask & (1 << old_index):
                compressed_mask |= 1 << new_index
        if compressed_mask:
            compressed_candidates.append((name, cost, compressed_mask))

    compressed_full = (1 << len(coverable_indices)) - 1
    exact = len(coverable_indices) <= max_exact_pairs

    if exact:
        dp = {0: (0.0, ())}
        for candidate_index, (_, cost, mask) in enumerate(compressed_candidates):
            next_dp = dict(dp)
            for old_mask, (old_cost, chosen) in dp.items():
                new_mask = old_mask | mask
                new_cost = old_cost + cost
                if not math.isfinite(new_cost):
                    raise ValueError("combined observation cost overflowed finite float range")
                new_chosen = chosen + (candidate_index,)
                existing = next_dp.get(new_mask)
                if existing is None:
                    next_dp[new_mask] = (new_cost, new_chosen)
                else:
                    old_best_cost, old_best_chosen = existing
                    if new_cost < old_best_cost or (
                        new_cost == old_best_cost and new_chosen < old_best_chosen
                    ):
                        next_dp[new_mask] = (new_cost, new_chosen)
            dp = next_dp
        total_cost, chosen_indices = dp[compressed_full]
        selected = [compressed_candidates[index][0] for index in chosen_indices]
        solver = "exact-cross-pair-dp"
    else:
        uncovered = compressed_full
        selected = []
        total_cost = 0.0
        remaining = list(compressed_candidates)
        while uncovered:
            best_choice = None
            best_ratio = -1.0
            for index, (name, cost, mask) in enumerate(remaining):
                newly_covered = uncovered & mask
                gain = newly_covered.bit_count()
                if gain == 0:
                    continue
                ratio = gain / cost
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_choice = (index, name, cost, newly_covered)
            if best_choice is None:
                break
            index, name, cost, newly_covered = best_choice
            selected.append(name)
            total_cost += cost
            if not math.isfinite(total_cost):
                raise ValueError("combined greedy cost overflowed finite float range")
            uncovered &= ~newly_covered
            remaining.pop(index)
        solver = "greedy-cross-pair-cover"

    chosen_names = set(selected)
    covered = 0
    for name, _, mask in validated:
        if name in chosen_names:
            covered |= mask
    separated_count = covered.bit_count()

    return QueryAttentionPlan(
        true_hypothesis_count=len(true_states),
        false_hypothesis_count=len(false_states),
        cross_boundary_pair_count=len(pairs),
        selected_names=tuple(selected),
        total_cost=total_cost,
        separated_pair_count=separated_count,
        unresolved_pairs=unresolved,
        complete=(not unresolved and separated_count == len(pairs)),
        exact=exact,
        solver=solver,
    )
