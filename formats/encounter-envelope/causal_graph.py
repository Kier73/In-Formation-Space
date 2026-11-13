#!/usr/bin/env python3
"""Causal graph and partial-order analysis for encounter envelopes.

Interprets the `relations` of a collection of encounter envelopes as a causal
partially ordered set (poset), checks for causal cycles, audits timestamp order only within explicitly shared
clock domains, extracts minimal dependency Hasse diagrams (transitive reduction),
and measures temporal underdetermination via topological linear extensions.

Zero third-party dependencies: standard Python only.
"""

from __future__ import annotations

import json
import sys
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

# Import existing envelope parser utilities
try:
    from validate_envelope import parse_iso8601, validate_encounter
except ImportError:
    from .validate_envelope import parse_iso8601, validate_encounter


def parse_envelope_datetime(timestamp_str: str) -> Optional[dt.datetime]:
    """Parse an RFC 3339 timestamp into an offset-aware datetime."""
    if not isinstance(timestamp_str, str) or not parse_iso8601(timestamp_str):
        return None
    normalized = timestamp_str.replace("t", "T", 1)
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


# Standard causal relation kinds and their induced edge directions
# Forward: source precedes target (source -> target)
FORWARD_CAUSAL_KINDS: FrozenSet[str] = frozenset(
    {"precedes", "causes", "triggers", "initiates"}
)

# Backward: target precedes source (target -> source)
BACKWARD_CAUSAL_KINDS: FrozenSet[str] = frozenset(
    {"caused_by", "depends_on", "derived_from", "response_to", "verifies"}
)

# Non-causal relations: informative links that do NOT induce temporal ordering
NON_CAUSAL_KINDS: FrozenSet[str] = frozenset(
    {"references", "annotates", "correlates_with", "see_also", "replaces"}
)


@dataclass(frozen=True)
class TimestampOrderConflict:
    """Diagnostic witness: same-domain wall timestamps oppose causal order."""

    predecessor_id: str
    successor_id: str
    predecessor_time: str
    successor_time: str
    time_skew_seconds: float


# Backwards-compatible name for existing callers.
AnachronismViolation = TimestampOrderConflict


@dataclass(frozen=True)
class CausalGraphReport:
    """Report on causal structure and the scoped timestamp audit."""

    envelope_count: int
    internal_nodes: Tuple[str, ...]
    external_targets: Tuple[str, ...]
    has_cycle: bool
    cycle_witness: Optional[Tuple[str, ...]]
    direct_edges: Tuple[Tuple[str, str], ...]
    hasse_edges: Tuple[Tuple[str, str], ...]
    timestamp_order_conflicts: Tuple[TimestampOrderConflict, ...]
    linear_extension_count: Optional[int]
    sample_topological_order: Optional[Tuple[str, ...]]
    timestamp_pairs_checked: int = 0
    timestamp_pairs_unassessed: int = 0
    timestamp_unassessed_reasons: Tuple[Tuple[str, int], ...] = ()

    @property
    def anachronisms(self) -> Tuple[TimestampOrderConflict, ...]:
        """Deprecated compatibility alias; conflicts are diagnostics, not proof."""
        return self.timestamp_order_conflicts


class CausalEncounterGraph:
    """Constructs and analyzes the causal partial order of encounter envelopes."""

    def __init__(self, envelopes: Iterable[Mapping[str, Any]]) -> None:
        self._envelopes: Dict[str, Mapping[str, Any]] = {}
        self._observed_times: Dict[str, dt.datetime] = {}
        self._observed_time_strings: Dict[str, str] = {}
        self._observed_clock_domains: Dict[str, str] = {}
        self._relations: List[Tuple[str, str, str]] = []  # (source, kind, target)
        self._external_targets: Set[str] = set()

        for env in envelopes:
            env_id = env.get("id")
            if not isinstance(env_id, str) or not env_id.strip():
                raise ValueError("each envelope must have a non-empty string id")
            if env_id in self._envelopes:
                raise ValueError(f"duplicate envelope id: {env_id}")
            self._envelopes[env_id] = env

            obs_at = env.get("observed_at")
            if isinstance(obs_at, str):
                parsed = parse_envelope_datetime(obs_at)
                if parsed is not None:
                    self._observed_times[env_id] = parsed
                    self._observed_time_strings[env_id] = obs_at

            # Wall-clock timestamps are comparable only when both records
            # explicitly name the same observed_at clock domain.
            context = env.get("context")
            if isinstance(context, Mapping):
                clock_domain = context.get("observed_at_clock_domain")
                if isinstance(clock_domain, str) and clock_domain.strip():
                    self._observed_clock_domains[env_id] = clock_domain.strip()

        # Process relations
        for env_id, env in self._envelopes.items():
            rels = env.get("relations")
            if isinstance(rels, list):
                for rel in rels:
                    if isinstance(rel, dict):
                        kind = rel.get("kind")
                        target = rel.get("target")
                        if isinstance(kind, str) and isinstance(target, str):
                            self._relations.append((env_id, kind, target))
                            if target not in self._envelopes:
                                self._external_targets.add(target)

    @classmethod
    def from_files(cls, paths: Iterable[Path | str]) -> CausalEncounterGraph:
        """Load and structurally validate encounter envelopes from JSON files."""
        loaded: List[Dict[str, Any]] = []
        for path in paths:
            p = Path(path)
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            # Validate format and structure
            valid, err = validate_encounter(doc)
            if not valid:
                raise ValueError(f"file {p} is not a valid encounter envelope: {err}")
            loaded.append(doc)
        return cls(loaded)

    def analyze(self, max_counting_nodes: int = 16) -> CausalGraphReport:
        """Analyze the causal poset and audit only comparable timestamp pairs."""
        internal_nodes = sorted(self._envelopes.keys())
        all_nodes = sorted(set(internal_nodes).union(self._external_targets))

        # Build directed adjacency list: u -> v means u precedes v causally (u < v)
        adj: Dict[str, Set[str]] = {node: set() for node in all_nodes}

        for source, kind, target in self._relations:
            if kind in FORWARD_CAUSAL_KINDS:
                # source precedes target: source -> target
                adj[source].add(target)
            elif kind in BACKWARD_CAUSAL_KINDS:
                # target precedes source: target -> source
                adj[target].add(source)
            # NON_CAUSAL_KINDS intentionally do not induce causal edges

        # 1. Cycle detection via 3-color DFS
        # 0: unvisited, 1: visiting, 2: visited
        color: Dict[str, int] = {node: 0 for node in all_nodes}
        parent: Dict[str, Optional[str]] = {node: None for node in all_nodes}
        cycle_witness: Optional[List[str]] = None

        def dfs(u: str) -> bool:
            nonlocal cycle_witness
            color[u] = 1
            for v in sorted(adj[u]):
                if color[v] == 1:
                    # Cycle found! Reconstruct cycle path
                    path = [v, u]
                    curr = u
                    while curr != v and parent[curr] is not None:
                        curr = parent[curr]  # type: ignore
                        path.append(curr)
                    path.reverse()
                    cycle_witness = path
                    return True
                elif color[v] == 0:
                    parent[v] = u
                    if dfs(v):
                        return True
            color[u] = 2
            return False

        has_cycle = False
        for node in all_nodes:
            if color[node] == 0:
                if dfs(node):
                    has_cycle = True
                    break

        direct_edges_list = [
            (u, v) for u in all_nodes for v in sorted(adj[u])
        ]

        if has_cycle:
            return CausalGraphReport(
                envelope_count=len(self._envelopes),
                internal_nodes=tuple(internal_nodes),
                external_targets=tuple(sorted(self._external_targets)),
                has_cycle=True,
                cycle_witness=tuple(cycle_witness) if cycle_witness else None,
                direct_edges=tuple(direct_edges_list),
                hasse_edges=(),
                timestamp_order_conflicts=(),
                linear_extension_count=0,
                sample_topological_order=None,
            )

        # 2. Transitive Closure (Warshall's algorithm on DAG)
        tc: Dict[str, Set[str]] = {node: set(adj[node]) for node in all_nodes}
        for k in all_nodes:
            for i in all_nodes:
                if k in tc[i]:
                    tc[i].update(tc[k])

        # 3. Transitive Reduction (Hasse diagram edges)
        # An edge u -> v is in Hasse diagram iff u -> v is in adj and there is no w
        # such that u -> w and w -> v (i.e. length >= 2 path).
        hasse_edges: List[Tuple[str, str]] = []
        for u in all_nodes:
            for v in sorted(adj[u]):
                # Is there an intermediate node w?
                intermediate = False
                for w in all_nodes:
                    if w != u and w != v and (w in tc[u]) and (v in tc[w]):
                        intermediate = True
                        break
                if not intermediate:
                    hasse_edges.append((u, v))

        # 4. Timestamp consistency diagnostic, scoped to an explicitly shared clock.
        # A timestamp from another or unknown domain is not evidence of order.
        timestamp_order_conflicts: List[TimestampOrderConflict] = []
        timestamp_pairs_checked = 0
        unassessed_reasons: Dict[str, int] = {}

        def mark_unassessed(reason: str) -> None:
            unassessed_reasons[reason] = unassessed_reasons.get(reason, 0) + 1

        for u in all_nodes:
            for v in tc[u]:
                time_u = self._observed_times.get(u)
                time_v = self._observed_times.get(v)
                domain_u = self._observed_clock_domains.get(u)
                domain_v = self._observed_clock_domains.get(v)

                if time_u is None or time_v is None:
                    mark_unassessed("missing_observed_at")
                    continue
                if domain_u is None or domain_v is None:
                    mark_unassessed("missing_clock_domain")
                    continue
                if domain_u != domain_v:
                    mark_unassessed("different_clock_domains")
                    continue

                timestamp_pairs_checked += 1
                if time_u > time_v:
                    skew = (time_u - time_v).total_seconds()
                    timestamp_order_conflicts.append(
                        TimestampOrderConflict(
                            predecessor_id=u,
                            successor_id=v,
                            predecessor_time=self._observed_time_strings[u],
                            successor_time=self._observed_time_strings[v],
                            time_skew_seconds=skew,
                        )
                    )

        timestamp_pairs_unassessed = sum(unassessed_reasons.values())
        timestamp_unassessed_reasons = tuple(sorted(unassessed_reasons.items()))

        # 5. Deterministic Topological Sort (Kahn's algorithm)
        in_degree: Dict[str, int] = {node: 0 for node in all_nodes}
        for u in all_nodes:
            for v in adj[u]:
                in_degree[v] += 1

        ready = [node for node in all_nodes if in_degree[node] == 0]
        topo_order: List[str] = []

        while ready:
            # Deterministic: sort alphabetically
            ready.sort()
            curr = ready.pop(0)
            topo_order.append(curr)
            for nxt in sorted(adj[curr]):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    ready.append(nxt)

        # 6. Linear Extensions Count (Down-set DP for small graphs)
        extension_count: Optional[int] = None
        if len(all_nodes) <= max_counting_nodes:
            extension_count = self._count_linear_extensions(all_nodes, tc)

        return CausalGraphReport(
            envelope_count=len(self._envelopes),
            internal_nodes=tuple(internal_nodes),
            external_targets=tuple(sorted(self._external_targets)),
            has_cycle=False,
            cycle_witness=None,
            direct_edges=tuple(direct_edges_list),
            hasse_edges=tuple(hasse_edges),
            timestamp_order_conflicts=tuple(timestamp_order_conflicts),
            linear_extension_count=extension_count,
            sample_topological_order=tuple(topo_order),
            timestamp_pairs_checked=timestamp_pairs_checked,
            timestamp_pairs_unassessed=timestamp_pairs_unassessed,
            timestamp_unassessed_reasons=timestamp_unassessed_reasons,
        )

    def _count_linear_extensions(
        self, nodes: List[str], tc: Dict[str, Set[str]]
    ) -> int:
        """Count linear extensions via DP over down-set order ideals."""
        n = len(nodes)
        node_to_idx = {node: i for i, node in enumerate(nodes)}

        # Precompute predecessors as bitmasks
        # pred_mask[i] is the mask of all strictly preceding nodes
        pred_mask = [0] * n
        for u in nodes:
            u_idx = node_to_idx[u]
            for v in tc[u]:
                v_idx = node_to_idx[v]
                pred_mask[v_idx] |= 1 << u_idx

        # dp[mask] = number of linear extensions of the sub-poset induced by mask
        dp: Dict[int, int] = {0: 1}

        # Iterate masks by increasing popcount
        # To avoid generating 2^n in full memory, process layer by layer
        current_layer: Dict[int, int] = {0: 1}
        full_mask = (1 << n) - 1

        for _ in range(n):
            next_layer: Dict[int, int] = {}
            for mask, count in current_layer.items():
                for i in range(n):
                    if not (mask & (1 << i)):
                        # Can node i be appended? Only if all its predecessors are already in mask
                        if (pred_mask[i] & mask) == pred_mask[i]:
                            new_mask = mask | (1 << i)
                            next_layer[new_mask] = next_layer.get(new_mask, 0) + count
            current_layer = next_layer

        return current_layer.get(full_mask, 0)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python causal_graph.py <envelope.json> [envelope2.json ...]")
        sys.exit(2)

    try:
        graph = CausalEncounterGraph.from_files(sys.argv[1:])
        report = graph.analyze()
    except Exception as exc:
        print(f"[ERROR] Failed to analyze encounter causal graph: {exc}", file=sys.stderr)
        sys.exit(1)

    print("=== ENCOUNTER CAUSAL GRAPH REPORT ===")
    print(f"Envelopes analyzed: {report.envelope_count}")
    print(f"Internal nodes:     {len(report.internal_nodes)}")
    print(f"External targets:   {len(report.external_targets)}")
    if report.external_targets:
        print(f"  External: {', '.join(report.external_targets)}")

    if report.has_cycle:
        print("\n[CAUSAL CONTRADICTION] Directed cycle detected!")
        if report.cycle_witness:
            print(f"Cycle witness: {' -> '.join(report.cycle_witness)}")
        sys.exit(1)

    print(f"\nDirect causal edges: {len(report.direct_edges)}")
    print(f"Hasse reduction (minimal dependencies): {len(report.hasse_edges)} edges")
    for u, v in report.hasse_edges:
        print(f"  {u} -> {v}")

    print(
        f"\nTimestamp audit: {report.timestamp_pairs_checked} same-domain causal pairs checked; "
        f"{report.timestamp_pairs_unassessed} pairs unassessed."
    )
    if report.timestamp_order_conflicts:
        print(
            f"\n[TIMESTAMP ORDER CONFLICTS] {len(report.timestamp_order_conflicts)} "
            "same-domain wall-clock readings oppose the recorded causal order:"
        )
        for conflict in report.timestamp_order_conflicts:
            print(
                f"  {conflict.predecessor_id} (time: {conflict.predecessor_time}) causally precedes "
                f"{conflict.successor_id} (time: {conflict.successor_time}) by "
                f"+{conflict.time_skew_seconds:.3f}s"
            )
    else:
        print("\n[TIMESTAMPS] No same-domain timestamp order conflicts detected.")

    if report.linear_extension_count is not None:
        print(f"\nLinear extensions count: |Omega| = {report.linear_extension_count}")

    if report.sample_topological_order:
        print(f"Canonical topological sort: {' -> '.join(report.sample_topological_order)}")

    sys.exit(0)


if __name__ == "__main__":
    main()
