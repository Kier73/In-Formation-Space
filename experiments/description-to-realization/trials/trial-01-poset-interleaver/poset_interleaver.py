"""Poset Causal Interleaver.

Models multi-stream partially ordered event systems, detects cycles with
witness extraction, computes exact topological linear extension counts, and
verifies candidate event traces.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple


class PosetCycleError(ValueError):
    """Raised when causal constraints contain a directed cycle."""

    def __init__(self, message: str, cycle: List[str]):
        super().__init__(message)
        self.cycle = cycle


class PosetInterleaver:
    """Represents a finite partially ordered set (poset) of events."""

    def __init__(self) -> None:
        self._events: Set[str] = set()
        self._successors: Dict[str, Set[str]] = defaultdict(set)
        self._predecessors: Dict[str, Set[str]] = defaultdict(set)
        # Preserve edge insertion order for deterministic O(V + E) trace blame.
        self._edge_order: List[Tuple[str, str]] = []

    @property
    def events(self) -> Set[str]:
        """Return a defensive copy of all registered events."""
        return set(self._events)

    @property
    def edge_count(self) -> int:
        """Total number of directed causal precedence edges."""
        return sum(len(succs) for succs in self._successors.values())

    def add_event(self, event_id: str) -> None:
        """Register an event in the poset."""
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Event ID must be a non-empty string.")
        self._events.add(event_id)

    def add_chain(self, sequence: Sequence[str]) -> None:
        """Add a sequence of events forming a totally ordered chain: e1 < e2 < ... < en."""
        events_list = list(sequence)
        for e in events_list:
            self.add_event(e)
        for i in range(len(events_list) - 1):
            self.add_edge(events_list[i], events_list[i + 1])

    def add_edge(self, u: str, v: str) -> None:
        """Add a precedence constraint u < v (u must happen before v)."""
        self.add_event(u)
        self.add_event(v)
        if u == v:
            raise PosetCycleError(f"Self-loop cycle on event '{u}'.", [u, u])
        if v not in self._successors.get(u, set()):
            self._successors[u].add(v)
            self._predecessors[v].add(u)
            self._edge_order.append((u, v))

    def find_cycle(self) -> Optional[List[str]]:
        """Detect if the constraint graph has a cycle.

        Returns:
            A cycle path [e1, e2, ..., ek, e1] if a cycle exists, else None.
        """
        # 0 = unvisited, 1 = visiting (in recursion stack), 2 = visited
        visited: Dict[str, int] = {e: 0 for e in self._events}
        parent: Dict[str, str] = {}

        for start_node in sorted(self._events):
            if visited[start_node] != 0:
                continue

            # Iterative DFS using explicit call stack to extract clean cycles
            stack: List[Tuple[str, Iterator[str]]] = [(start_node, iter(sorted(self._successors.get(start_node, ()))))]
            visited[start_node] = 1

            while stack:
                curr, it = stack[-1]
                try:
                    nxt = next(it)
                    if visited[nxt] == 1:
                        # Found back-edge! Reconstruct cycle from curr back to nxt
                        cycle = [nxt]
                        node = curr
                        while node != nxt:
                            cycle.append(node)
                            node = parent.get(node, nxt)
                        cycle.append(nxt)
                        cycle.reverse()
                        return cycle
                    elif visited[nxt] == 0:
                        visited[nxt] = 1
                        parent[nxt] = curr
                        stack.append((nxt, iter(sorted(self._successors.get(nxt, ())))))
                except StopIteration:
                    visited[curr] = 2
                    stack.pop()

        return None

    def is_acyclic(self) -> bool:
        """Check if the poset is a valid Directed Acyclic Graph (DAG)."""
        return self.find_cycle() is None

    def verify_trace(self, sequence: Sequence[str]) -> Tuple[bool, Optional[str], Optional[Tuple[str, str]]]:
        """Verify whether a total sequence is a valid linear extension of the poset.

        Returns:
            (is_valid, error_reason, violated_edge)
        """
        seq = list(sequence)
        if len(seq) != len(self._events):
            return False, f"Sequence length ({len(seq)}) does not match poset event count ({len(self._events)}).", None

        seq_set = set(seq)
        if len(seq_set) != len(seq):
            return False, "Sequence contains duplicate events.", None

        if seq_set != self._events:
            missing = self._events - seq_set
            extra = seq_set - self._events
            return False, f"Event set mismatch. Missing: {missing}, Extra: {extra}.", None

        # Build position lookup in O(V)
        pos = {e: idx for idx, e in enumerate(seq)}

        # Check all edges in O(E)
        # Edge insertion order is stable for a given construction trace.
        # This keeps verification O(V + E) without sorting at query time.
        for u, v in self._edge_order:
            u_pos = pos[u]
            v_pos = pos[v]
            if u_pos >= v_pos:
                    return (
                        False,
                        f"Precedence violation: '{u}' (pos {u_pos}) must precede '{v}' (pos {v_pos}).",
                        (u, v),
                    )

        return True, None, None

    def count_linear_extensions(self) -> int:
        """Compute the exact number of linear extensions (topological sorts).

        Uses dynamic programming over down-sets (subposet ideals).
        The DP scans up to n events per reachable down-set: O(n * |J(P)| + |E|)
        time and O(|J(P)|) auxiliary memory. In an antichain, |J(P)| = 2**n.
        """
        cycle = self.find_cycle()
        if cycle is not None:
            raise PosetCycleError("Cannot count linear extensions of a cyclic graph.", cycle)

        if not self._events:
            # There is exactly one linear extension of the empty poset: [].
            return 1

        event_list = sorted(self._events)
        n = len(event_list)
        idx_map = {e: i for i, e in enumerate(event_list)}

        # Bitmask representation of predecessors
        pred_masks = [0] * n
        for v in event_list:
            v_idx = idx_map[v]
            mask = 0
            for u in self._predecessors.get(v, ()):
                mask |= 1 << idx_map[u]
            pred_masks[v_idx] = mask

        # dp[mask] = number of linear extensions of the subset represented by mask
        dp: Dict[int, int] = {0: 1}
        full_mask = (1 << n) - 1

        # Use BFS queue over valid down-set masks
        queue = deque([0])
        seen_masks: Set[int] = {0}

        while queue:
            mask = queue.popleft()
            ways = dp[mask]

            if mask == full_mask:
                continue

            for i in range(n):
                if not (mask & (1 << i)):
                    # Event i can be appended if all its predecessors are already in mask
                    if (mask & pred_masks[i]) == pred_masks[i]:
                        nxt_mask = mask | (1 << i)
                        if nxt_mask not in dp:
                            dp[nxt_mask] = ways
                            if nxt_mask not in seen_masks:
                                seen_masks.add(nxt_mask)
                                queue.append(nxt_mask)
                        else:
                            dp[nxt_mask] += ways

        return dp.get(full_mask, 0)

    def generate_linear_extensions(self, limit: Optional[int] = None) -> Iterator[List[str]]:
        """Yield valid topological linear extensions up to `limit`."""
        cycle = self.find_cycle()
        if cycle is not None:
            raise PosetCycleError("Cannot generate linear extensions of a cyclic graph.", cycle)

        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative or None.")

        in_deg = {e: len(self._predecessors.get(e, ())) for e in self._events}
        current_path: List[str] = []
        count = 0

        def backtrack(available: Set[str]) -> Iterator[List[str]]:
            nonlocal count
            if limit is not None and count >= limit:
                return

            if len(current_path) == len(self._events):
                count += 1
                yield list(current_path)
                return

            for u in sorted(available):
                if limit is not None and count >= limit:
                    break

                current_path.append(u)
                next_avail = set(available)
                next_avail.remove(u)

                # Decrement in-degree of successors
                unlocked: List[str] = []
                for v in sorted(self._successors.get(u, ())):
                    in_deg[v] -= 1
                    if in_deg[v] == 0:
                        unlocked.append(v)
                        next_avail.add(v)

                yield from backtrack(next_avail)

                # Revert
                for v in sorted(self._successors.get(u, ())):
                    in_deg[v] += 1
                current_path.pop()

        start_available = {e for e, deg in in_deg.items() if deg == 0}
        yield from backtrack(start_available)
