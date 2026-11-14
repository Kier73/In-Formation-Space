"""Shortest observable distinctions in a supplied finite deterministic Ground.

Observation equivalence is relative to the *declared* states, actions and tests.
No action is executed on an external host; transitions are model descriptions.
Unknown/invalid/incomplete models fail closed rather than yielding equivalence.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Hashable, Sequence


@dataclass(frozen=True)
class DistinguishingWitness:
    status: str  # "distinguished" or "equivalent"
    actions: tuple[Hashable, ...]
    distinguishing_test: object | None
    left_final: Hashable
    right_final: Hashable
    left_observation: object | None
    right_observation: object | None
    scope: str = "complete-finite-deterministic-declared-observations"


class FiniteDistinctionNavigator:
    """Precompute minimal distinguishing continuations by reverse pair reachability.

    For every unordered pair of distinct states, compute outgoing pair transitions
    under each declared action. Seed all pairs already distinguished by a test,
    then propagate their shortest distance backward. A pair not reached by that
    reverse search cannot reach a differing observable in this complete finite
    model: its observation streams agree under *every* finite action sequence.

    Given a distinguished pair, choose the first action (in supplied order)
    reducing distance by one until the first differing observation. This yields
    a shortest witness and a deterministic action-order tie break.
    """

    def __init__(
        self,
        states: Sequence[Hashable],
        actions: Sequence[Hashable],
        tests: Sequence[object],
        observation_fn: Callable[[Hashable, object], object],
        transition_fn: Callable[[Hashable, Hashable], Hashable],
        *,
        max_pairs: int = 50_000,
    ) -> None:
        self.states = tuple(states)
        self.actions = tuple(actions)
        self.tests = tuple(tests)
        if not self.states:
            raise ValueError("at least one state is required")
        if isinstance(max_pairs, bool) or not isinstance(max_pairs, int) or max_pairs < 0:
            raise ValueError("max_pairs must be a non-negative integer")
        if not callable(observation_fn) or not callable(transition_fn):
            raise TypeError("observation_fn and transition_fn must be callable")
        try:
            self._index = {state: i for i, state in enumerate(self.states)}
            unique_actions = set(self.actions)
        except TypeError as exc:
            raise TypeError("states and actions must be hashable") from exc
        if len(self._index) != len(self.states) or len(unique_actions) != len(self.actions):
            raise ValueError("states and actions must each be unique")

        n = len(self.states)
        self.checked_state_pairs = n * (n - 1) // 2
        if self.checked_state_pairs > max_pairs:
            raise ValueError("finite pair budget exceeded; equivalence not established")

        # Evaluate the entire declared model before making any equivalence claim.
        self._outputs = tuple(
            tuple(observation_fn(state, test) for test in self.tests)
            for state in self.states
        )
        steps: dict[tuple[int, int], int] = {}
        for i, state in enumerate(self.states):
            for a, action in enumerate(self.actions):
                try:
                    destination = transition_fn(state, action)
                except Exception as exc:
                    raise ValueError(f"action {action!r} undefined for {state!r}") from exc
                try:
                    j = self._index[destination]
                except TypeError as exc:
                    raise TypeError("transition successor must be a hashable state") from exc
                except KeyError as exc:
                    raise ValueError("transition left the supplied finite state universe") from exc
                steps[(i, a)] = j
        self._steps = steps
        self.checked_transitions = len(steps)

        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        previous: dict[tuple[int, int], list[tuple[int, int]]] = {p: [] for p in pairs}
        difference: dict[tuple[int, int], int] = {}
        for pair in pairs:
            left, right = pair
            for t in range(len(self.tests)):
                if self._outputs[left][t] != self._outputs[right][t]:
                    difference[pair] = t
                    break
            for a in range(len(self.actions)):
                successor = self._pair(steps[(left, a)], steps[(right, a)])
                if successor is not None:
                    previous[successor].append(pair)

        # The entire finite pair graph is explored once, not separately per query.
        distance = {pair: 0 for pair in difference}
        pending = deque(difference)
        while pending:
            pair = pending.popleft()
            for predecessor in previous[pair]:
                if predecessor not in distance:
                    distance[predecessor] = distance[pair] + 1
                    pending.append(predecessor)
        self._distance = distance
        self._difference = difference

    @staticmethod
    def _pair(i: int, j: int) -> tuple[int, int] | None:
        if i == j:
            return None
        return (i, j) if i < j else (j, i)

    def compare(self, left: Hashable, right: Hashable) -> DistinguishingWitness:
        """Return a shortest test-bearing trace, or exact finite-model equivalence."""
        try:
            i, j = self._index[left], self._index[right]
        except (KeyError, TypeError) as exc:
            raise ValueError("query states must belong to the declared universe") from exc
        pair = self._pair(i, j)
        if pair is None or pair not in self._distance:
            return DistinguishingWitness(
                "equivalent", (), None, self.states[i], self.states[j], None, None
            )
        remaining = self._distance[pair]
        chosen: list[Hashable] = []
        while remaining:
            for a, action in enumerate(self.actions):
                next_i, next_j = self._steps[(i, a)], self._steps[(j, a)]
                successor = self._pair(next_i, next_j)
                if successor is not None and self._distance.get(successor) == remaining - 1:
                    chosen.append(action)
                    i, j = next_i, next_j
                    remaining -= 1
                    break
            else:
                raise AssertionError("precomputed witness distance has no descending edge")
        final_pair = self._pair(i, j)
        assert final_pair is not None
        test_index = self._difference[final_pair]
        return DistinguishingWitness(
            "distinguished",
            tuple(chosen),
            self.tests[test_index],
            self.states[i],
            self.states[j],
            self._outputs[i][test_index],
            self._outputs[j][test_index],
        )
