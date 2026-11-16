"""Exact least-cost separating experiment on a validated finite Ground model.

A separating *action word* actively changes the hypothetical model state;
no observation is claimed to have been executed. Costs are nonnegative
integer units, specified by the caller (not measured or inferred).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Hashable, Sequence

from distinguishing_navigation import DistinguishingWitness, FiniteDistinctionNavigator


@dataclass(frozen=True)
class CostedWitness:
    witness: DistinguishingWitness
    total_cost: int | None
    action_cost: int | None
    test_cost: int | None
    cost_scope: str = "caller-supplied-nonnegative-integer-actions-and-terminal-tests"


class CostedDistinctionNavigator(FiniteDistinctionNavigator):
    """Select a minimum-cost distinguishing action word and one final test.

    Minimize (total action + terminal observation cost, action count,
    lexicographic action indices, test index). There is no cost of checking
    intermediate states: no such observation is required by the contract.
    A zero-cost action may occur, but hop-count tie-breaking prevents
    zero-cost cycles from creating ambiguous or infinite witnesses.
    """

    @staticmethod
    def _validate_costs(costs: Sequence[int], length: int, label: str) -> tuple[int, ...]:
        try:
            costs = tuple(costs)
        except TypeError as exc:
            raise ValueError(f"{label} must be a finite ordered sequence") from exc
        if len(costs) != length:
            raise ValueError(f"{label} count must match the declared contract")
        if any(type(cost) is not int or cost < 0 for cost in costs):
            raise ValueError(f"{label} must contain nonnegative plain integers")
        return costs

    def plan_min_cost(
        self,
        left: Hashable,
        right: Hashable,
        *,
        action_costs: Sequence[int],
        test_costs: Sequence[int],
    ) -> CostedWitness:
        """Compute a complete finite-model least-cost witness for this cost policy.

        All declared pairs and edges are considered. A predecessor Dijkstra
        search starts at every pair with a differing output test. A pair not
        reached is equivalent for all finite action words under the supplied
        deterministic model and the supplied observation tests, regardless
        of their costs.
        """
        action_costs = self._validate_costs(action_costs, len(self.actions), "action_costs")
        test_costs = self._validate_costs(test_costs, len(self.tests), "test_costs")
        try:
            i, j = self._index[left], self._index[right]
        except (KeyError, TypeError) as exc:
            raise ValueError("query states must belong to the declared universe") from exc
        start = self._pair(i, j)
        if start is None:
            return CostedWitness(
                DistinguishingWitness("equivalent", (), None, self.states[i], self.states[j], None, None),
                None, None, None,
            )

        n = len(self.states)
        predecessors: dict[tuple[int, int], list[tuple[tuple[int, int], int]]] = {}
        best: dict[tuple[int, int], tuple[int, int]] = {}
        terminal_test: dict[tuple[int, int], int] = {}
        heap: list[tuple[int, int, int, int]] = []
        for x in range(n):
            for y in range(x + 1, n):
                pair = (x, y)
                predecessors[pair] = []
                candidates = (
                    t for t in range(len(self.tests))
                    if self._outputs[x][t] != self._outputs[y][t]
                )
                terminal = min(candidates, key=lambda t: (test_costs[t], t), default=None)
                if terminal is not None:
                    best[pair] = (test_costs[terminal], 0)
                    terminal_test[pair] = terminal
                    heapq.heappush(heap, (test_costs[terminal], 0, x, y))
        for x in range(n):
            for y in range(x + 1, n):
                pair = (x, y)
                for a in range(len(self.actions)):
                    successor = self._pair(self._steps[(x, a)], self._steps[(y, a)])
                    if successor is not None:
                        predecessors[successor].append((pair, a))

        while heap:
            cost, hops, x, y = heapq.heappop(heap)
            pair = (x, y)
            if best[pair] != (cost, hops):
                continue
            for predecessor, action in predecessors[pair]:
                candidate = (cost + action_costs[action], hops + 1)
                if predecessor not in best or candidate < best[predecessor]:
                    best[predecessor] = candidate
                    heapq.heappush(heap, (*candidate, *predecessor))

        if start not in best:
            return CostedWitness(
                DistinguishingWitness("equivalent", (), None, self.states[i], self.states[j], None, None),
                None, None, None,
            )

        minimum_cost, remaining = best[start]
        chosen: list[Hashable] = []
        cumulative_action_cost = 0
        while remaining:
            for a, action in enumerate(self.actions):
                ni, nj = self._steps[(i, a)], self._steps[(j, a)]
                successor = self._pair(ni, nj)
                if successor is not None and best.get(successor) == (
                    best[self._pair(i, j)][0] - action_costs[a], remaining - 1
                ):
                    chosen.append(action)
                    cumulative_action_cost += action_costs[a]
                    i, j = ni, nj
                    remaining -= 1
                    break
            else:
                raise AssertionError("minimum-cost witness has no descending edge")
        final = self._pair(i, j)
        assert final is not None and final in terminal_test
        test_idx = terminal_test[final]
        assert cumulative_action_cost + test_costs[test_idx] == minimum_cost
        witness = DistinguishingWitness(
            "distinguished", tuple(chosen), self.tests[test_idx],
            self.states[i], self.states[j],
            self._outputs[i][test_idx], self._outputs[j][test_idx],
        )
        return CostedWitness(witness, minimum_cost, cumulative_action_cost, test_costs[test_idx])
