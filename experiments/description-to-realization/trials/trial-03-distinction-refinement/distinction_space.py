"""Finite partition refinement as a test for genuinely new distinctions.

A distinction is redundant relative to existing observations when it is
constant inside every existing observational equivalence class. Otherwise
it refines at least one class. Conditional entropy quantifies the added
information under the supplied state weights; split_pair_count measures
newly separated pairs without depending on a probability distribution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Hashable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class RefinementResult:
    name: str
    previous_block_count: int
    refined_block_count: int
    split_pair_count: int
    conditional_entropy_bits: float
    redundant: bool


class DistinctionSpace:
    """Maintain equivalence classes induced by recorded state observations."""

    def __init__(
        self,
        states: Sequence[Hashable],
        weights: Optional[Mapping[Hashable, float]] = None,
    ) -> None:
        if not states:
            raise ValueError("states must contain at least one state")
        state_list = list(states)
        try:
            state_set = set(state_list)
        except TypeError as exc:
            raise TypeError("every state must be hashable") from exc
        if len(state_set) != len(state_list):
            raise ValueError("states must be unique")

        if weights is None:
            normalized_weights = {state: 1.0 for state in state_list}
        else:
            if set(weights) != state_set:
                raise ValueError("weights must contain exactly one entry for every state")
            normalized_weights = {}
            for state in state_list:
                value = float(weights[state])
                if not math.isfinite(value) or value <= 0.0:
                    raise ValueError("all state weights must be finite and positive")
                normalized_weights[state] = value

        self._states: Tuple[Hashable, ...] = tuple(state_list)
        self._weights: Dict[Hashable, float] = normalized_weights
        self._observations: Dict[str, Dict[Hashable, Hashable]] = {}

    @property
    def states(self) -> Tuple[Hashable, ...]:
        return self._states

    @property
    def distinction_names(self) -> Tuple[str, ...]:
        return tuple(self._observations)

    def _signature(self, state: Hashable) -> Tuple[Hashable, ...]:
        return tuple(values[state] for values in self._observations.values())

    def partition(self) -> Tuple[Tuple[Hashable, ...], ...]:
        """Return current observational equivalence classes in stable input order."""
        blocks: Dict[Tuple[Hashable, ...], List[Hashable]] = {}
        for state in self._states:
            blocks.setdefault(self._signature(state), []).append(state)
        return tuple(tuple(block) for block in blocks.values())

    def signatures(self) -> Dict[Hashable, Tuple[Hashable, ...]]:
        """Return the current observation signature of each state."""
        return {state: self._signature(state) for state in self._states}

    def add_distinction(
        self, name: str, observation: Callable[[Hashable], Hashable]
    ) -> RefinementResult:
        """Add one observation and measure how it refines current equivalence classes."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("distinction name must be a non-empty string")
        if name in self._observations:
            raise ValueError(f"distinction already exists: {name}")
        if not callable(observation):
            raise TypeError("observation must be callable")

        observed: Dict[Hashable, Hashable] = {}
        for state in self._states:
            value = observation(state)
            try:
                hash(value)
            except TypeError as exc:
                raise TypeError(f"observation for state {state!r} must be hashable") from exc
            observed[state] = value

        previous_blocks = self.partition()
        prior_count = len(previous_blocks)
        total_weight = sum(self._weights.values())
        split_pair_count = 0
        conditional_entropy = 0.0

        for block in previous_blocks:
            child_weights: Dict[Hashable, float] = {}
            block_pair_count = len(block) * (len(block) - 1) // 2
            for state in block:
                value = observed[state]
                child_weights[value] = child_weights.get(value, 0.0) + self._weights[state]

            child_pair_count = 0
            for child_weight in child_weights.values():
                # Pair counts depend on state cardinalities, not probability weights.
                child_pair_count += 0  # populated in the cardinality pass below

            child_counts: Dict[Hashable, int] = {}
            for state in block:
                value = observed[state]
                child_counts[value] = child_counts.get(value, 0) + 1
            child_pair_count = sum(
                count * (count - 1) // 2 for count in child_counts.values()
            )
            split_pair_count += block_pair_count - child_pair_count

            block_weight = sum(self._weights[state] for state in block)
            if block_weight > 0.0:
                local_entropy = 0.0
                for child_weight in child_weights.values():
                    probability = child_weight / block_weight
                    local_entropy -= probability * math.log2(probability)
                conditional_entropy += (block_weight / total_weight) * local_entropy

        # Store only after every observation and metric has been computed successfully.
        self._observations[name] = observed
        refined_count = len(self.partition())
        redundant = split_pair_count == 0

        # Floating-point noise should not turn a mathematically-zero entropy into
        # a tiny positive report for a redundant feature.
        if redundant:
            conditional_entropy = 0.0

        return RefinementResult(
            name=name,
            previous_block_count=prior_count,
            refined_block_count=refined_count,
            split_pair_count=split_pair_count,
            conditional_entropy_bits=conditional_entropy,
            redundant=redundant,
        )

    def conditional_entropy_bits(self, name: str) -> float:
        """Measure a stored distinction's entropy conditioned on all earlier ones.

        This is the incremental conditional entropy at insertion time. It is
        therefore recorded in the RefinementResult returned by add_distinction.
        """
        if name not in self._observations:
            raise KeyError(name)
        raise NotImplementedError(
            "Use the RefinementResult returned when the distinction was added."
        )
