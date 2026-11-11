"""Cost-aware selection of observations that distinguish a target state.

Given the current observational equivalence class of a target, each candidate
observation separates some alternatives from the target. Selecting a minimum-
cost set whose union separates all alternatives is weighted set cover.

Small ambiguity sets are solved exactly by bitmask dynamic programming.
Larger sets use a deterministic greedy approximation and are labelled as such.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Hashable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ObservationCandidate:
    name: str
    cost: float
    observe: Callable[[Hashable], Hashable]


@dataclass(frozen=True)
class AttentionPlan:
    target: Hashable
    ambiguity_before: int
    selected_names: Tuple[str, ...]
    total_cost: float
    separated_states: Tuple[Hashable, ...]
    unseparable_states: Tuple[Hashable, ...]
    complete: bool
    exact: bool
    solver: str


def select_attention_packet(
    states: Sequence[Hashable],
    target: Hashable,
    candidates: Sequence[ObservationCandidate],
    current_signatures: Optional[Mapping[Hashable, Hashable]] = None,
    max_exact_alternatives: int = 20,
) -> AttentionPlan:
    """Select observations that isolate target from its current equivalence class.

    current_signatures maps each state to its signature under observations
    already available. Equal signatures mean observationally indistinguishable.
    If omitted, every state begins in one equivalence class.

    The selected packet is minimum-cost when exact=True. For larger ambiguity
    sets, exact=False and a deterministic greedy set-cover approximation is
    returned. A state no candidate can distinguish from target is reported in
    unseparable_states; no algorithm can isolate target from that state using
    the supplied candidate family.
    """
    if not states:
        raise ValueError("states must contain at least one state")
    if max_exact_alternatives < 1:
        raise ValueError("max_exact_alternatives must be positive")

    state_list = list(states)
    try:
        state_set = set(state_list)
    except TypeError as exc:
        raise TypeError("every state must be hashable") from exc
    if len(state_set) != len(state_list):
        raise ValueError("states must be unique")
    if target not in state_set:
        raise ValueError("target must be present in states")

    if current_signatures is None:
        signatures = {state: () for state in state_list}
    else:
        if set(current_signatures) != state_set:
            raise ValueError("current_signatures must contain exactly one entry for every state")
        signatures = dict(current_signatures)
        for state, signature in signatures.items():
            try:
                hash(signature)
            except TypeError as exc:
                raise TypeError(f"current signature for {state!r} must be hashable") from exc

    target_signature = signatures[target]
    alternatives = [
        state for state in state_list
        if state != target and signatures[state] == target_signature
    ]
    ambiguity_before = len(alternatives)
    if not alternatives:
        return AttentionPlan(
            target=target,
            ambiguity_before=0,
            selected_names=(),
            total_cost=0.0,
            separated_states=(),
            unseparable_states=(),
            complete=True,
            exact=True,
            solver="exact-trivial",
        )

    candidate_list = list(candidates)
    seen_names = set()
    validated = []
    for candidate in candidate_list:
        if not isinstance(candidate.name, str) or not candidate.name.strip():
            raise ValueError("candidate names must be non-empty strings")
        if candidate.name in seen_names:
            raise ValueError(f"duplicate candidate name: {candidate.name}")
        seen_names.add(candidate.name)
        if not math.isfinite(float(candidate.cost)) or float(candidate.cost) <= 0.0:
            raise ValueError(f"candidate cost must be finite and positive: {candidate.name}")
        if not callable(candidate.observe):
            raise TypeError(f"candidate observation must be callable: {candidate.name}")

        target_value = candidate.observe(target)
        try:
            hash(target_value)
        except TypeError as exc:
            raise TypeError(f"candidate {candidate.name} returned an unhashable value") from exc

        mask = 0
        for index, state in enumerate(alternatives):
            observed = candidate.observe(state)
            try:
                hash(observed)
            except TypeError as exc:
                raise TypeError(f"candidate {candidate.name} returned an unhashable value") from exc
            if observed != target_value:
                mask |= 1 << index
        validated.append((candidate.name, float(candidate.cost), mask))

    union_mask = 0
    for _, _, mask in validated:
        union_mask |= mask

    full_mask = (1 << ambiguity_before) - 1
    unseparable = tuple(
        state for index, state in enumerate(alternatives)
        if not (union_mask & (1 << index))
    )
    coverable_indices = [
        index for index in range(ambiguity_before)
        if union_mask & (1 << index)
    ]
    coverable_states = tuple(alternatives[index] for index in coverable_indices)

    # Compress to only alternatives that at least one candidate can separate.
    compressed_candidates = []
    for name, cost, mask in validated:
        compressed_mask = 0
        for new_index, old_index in enumerate(coverable_indices):
            if mask & (1 << old_index):
                compressed_mask |= 1 << new_index
        if compressed_mask:
            compressed_candidates.append((name, cost, compressed_mask))

    compressed_full = (1 << len(coverable_indices)) - 1
    exact = len(coverable_indices) <= max_exact_alternatives

    if exact:
        # dp[mask] = (cost, candidate-index tuple). Updating from a snapshot
        # makes this a 0/1 set-cover dynamic program: a candidate is selected
        # at most once.
        dp = {0: (0.0, ())}
        for candidate_index, (_, cost, mask) in enumerate(compressed_candidates):
            next_dp = dict(dp)
            for old_mask, (old_cost, chosen) in dp.items():
                new_mask = old_mask | mask
                new_cost = old_cost + cost
                new_chosen = chosen + (candidate_index,)
                existing = next_dp.get(new_mask)
                if existing is None:
                    next_dp[new_mask] = (new_cost, new_chosen)
                else:
                    old_best_cost, old_best_chosen = existing
                    cheaper = new_cost < old_best_cost and not math.isclose(
                        new_cost, old_best_cost, rel_tol=1e-12, abs_tol=1e-12
                    )
                    tied_but_earlier = math.isclose(
                        new_cost, old_best_cost, rel_tol=1e-12, abs_tol=1e-12
                    ) and new_chosen < old_best_chosen
                    if cheaper or tied_but_earlier:
                        next_dp[new_mask] = (new_cost, new_chosen)
            dp = next_dp

        best_cost, best_indices = dp[compressed_full]
        selected = [compressed_candidates[index][0] for index in best_indices]
        solver_name = "exact-bitmask-dp"
    else:
        uncovered = compressed_full
        selected = []
        best_cost = 0.0
        remaining = list(compressed_candidates)
        while uncovered:
            best_choice = None
            best_ratio = -1.0
            for index, (name, cost, mask) in enumerate(remaining):
                gain_mask = uncovered & mask
                gain = gain_mask.bit_count()
                if gain == 0:
                    continue
                ratio = gain / cost
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_choice = (index, name, cost, gain_mask)
            if best_choice is None:
                break
            index, name, cost, gain_mask = best_choice
            selected.append(name)
            best_cost += cost
            uncovered &= ~gain_mask
            remaining.pop(index)
        solver_name = "greedy-set-cover"

    selected_set = set(selected)
    covered_original = 0
    for name, _, mask in validated:
        if name in selected_set:
            covered_original |= mask
    separated = tuple(
        state for index, state in enumerate(alternatives)
        if covered_original & (1 << index)
    )

    return AttentionPlan(
        target=target,
        ambiguity_before=ambiguity_before,
        selected_names=tuple(selected),
        total_cost=best_cost,
        separated_states=separated,
        unseparable_states=unseparable,
        complete=(len(unseparable) == 0 and len(separated) == ambiguity_before),
        exact=exact,
        solver=solver_name,
    )
