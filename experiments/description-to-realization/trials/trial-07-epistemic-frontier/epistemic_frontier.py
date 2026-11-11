"""Trial 07: Epistemic frontier mapping over encounter envelopes.

Loads every encounter envelope in a repository tree, constructs the global
causal DAG via relations, and identifies the epistemic frontier: the antichain
of nodes that no other node causally succeeds.

The frontier equation:

    F(G) = { v in V : not exists w in V, v -< w }

A fully connected forest with no causal relations declared has |F(G)| = |V|
— every node is on the frontier. That is not an error; it means no contributor
has yet asserted any causal dependency between envelopes. The report preserves
that fact rather than inferring links.

Verification ratio over the frontier:

    rho = |{ v in F(G) : payload is inline and integrity is verified }|
          / |F(G)|

A rho = 0 means no frontier node carries a verifiable digest claim.
A rho = 1 means every frontier node's payload was checked and matched.
Values between 0 and 1 mean partial verification — some are on trust.

Zero third-party dependencies: standard Python 3.10+ only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Minimal envelope loader
# ---------------------------------------------------------------------------

ENCOUNTER_FORMAT_PREFIX = "in-formation.encounter"


def _load_envelopes(root: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    """Walk root recursively and return all encounter envelope documents."""
    results = []
    for path in sorted(root.rglob("*.json")):
        if "schema" in path.name.lower():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        if str(doc.get("format", "")).startswith(ENCOUNTER_FORMAT_PREFIX):
            results.append((path, doc))
    return results


# ---------------------------------------------------------------------------
# Digest verification (zero-dependency)
# ---------------------------------------------------------------------------

def _verify_digest(doc: Dict[str, Any]) -> Optional[bool]:
    """Return True if digest verified, False on mismatch, None if not checkable."""
    payload = doc.get("payload")
    integrity = doc.get("integrity")
    if not isinstance(payload, dict) or not isinstance(integrity, dict):
        return None
    if "value" not in payload:
        return None  # reference payloads are not checked here
    algo = integrity.get("algorithm")
    canon = integrity.get("canonicalization")
    stated_digest = integrity.get("digest")
    if not stated_digest:
        return None
    value = payload["value"]
    try:
        if algo == "sha256" and canon == "json-sort-keys-utf8-v1":
            serialized = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            actual = hashlib.sha256(serialized).hexdigest()
            return actual == stated_digest
        elif algo == "sha256" and canon == "utf8-raw-v1":
            if not isinstance(value, str):
                return None
            actual = hashlib.sha256(value.encode("utf-8")).hexdigest()
            return actual == stated_digest
    except (TypeError, ValueError):
        return False
    return None


# ---------------------------------------------------------------------------
# Frontier analysis
# ---------------------------------------------------------------------------

FORWARD_KINDS: FrozenSet[str] = frozenset(
    {"precedes", "causes", "triggers", "initiates"}
)
BACKWARD_KINDS: FrozenSet[str] = frozenset(
    {"caused_by", "depends_on", "derived_from", "response_to", "verifies"}
)


@dataclass
class NodeSummary:
    envelope_id: str
    path: str
    observed_at: Optional[str]
    has_inline_value: bool
    has_reference: bool
    integrity_algo: Optional[str]
    integrity_canon: Optional[str]
    digest_verified: Optional[bool]  # True/False/None
    relation_count: int
    on_frontier: bool


@dataclass
class FrontierReport:
    root: Path
    generated_at: str
    envelope_count: int
    nodes: List[NodeSummary] = field(default_factory=list)
    causal_edge_count: int = 0
    frontier_ids: List[str] = field(default_factory=list)
    external_target_ids: List[str] = field(default_factory=list)
    has_cycle: bool = False
    cycle_witness: Optional[List[str]] = None
    verification_ratio: Optional[float] = None
    verified_count: int = 0
    unverified_count: int = 0
    not_checkable_count: int = 0

    def summary_lines(self) -> List[str]:
        lines = [
            f"Root:              {self.root}",
            f"Generated at:      {self.generated_at}",
            f"Envelopes loaded:  {self.envelope_count}",
            f"Causal edges:      {self.causal_edge_count}",
        ]
        if self.has_cycle:
            lines.append(f"[CYCLE DETECTED]   witness: {' -> '.join(self.cycle_witness or [])}")
        lines += [
            f"Frontier size:     |F(G)| = {len(self.frontier_ids)}  (of {self.envelope_count} nodes)",
            f"External targets:  {len(self.external_target_ids)}",
        ]
        if self.frontier_ids:
            lines.append("Frontier nodes:")
            for fid in self.frontier_ids:
                lines.append(f"  {fid}")
        if self.external_target_ids:
            lines.append("External targets (epistemic boundary):")
            for eid in self.external_target_ids:
                lines.append(f"  {eid}")
        lines += [
            "",
            "Payload verification (frontier nodes):",
            f"  Verified:          {self.verified_count}",
            f"  Mismatch/failed:   {self.unverified_count}",
            f"  Not checkable:     {self.not_checkable_count}",
        ]
        if self.verification_ratio is not None:
            lines.append(f"  rho (ratio):       {self.verification_ratio:.3f}")
        return lines


def _detect_cycle(
    all_nodes: List[str], adj: Dict[str, Set[str]]
) -> Optional[List[str]]:
    """3-color DFS cycle detection; return a witness path or None."""
    color: Dict[str, int] = {n: 0 for n in all_nodes}
    parent: Dict[str, Optional[str]] = {n: None for n in all_nodes}
    result: Optional[List[str]] = None

    def dfs(u: str) -> bool:
        nonlocal result
        color[u] = 1
        for v in sorted(adj.get(u, set())):
            if color[v] == 1:
                path = [v, u]
                curr = u
                while curr != v and parent[curr] is not None:
                    curr = parent[curr]  # type: ignore[assignment]
                    path.append(curr)
                path.reverse()
                result = path
                return True
            if color[v] == 0:
                parent[v] = u
                if dfs(v):
                    return True
        color[u] = 2
        return False

    for n in all_nodes:
        if color[n] == 0:
            if dfs(n):
                return result
    return None


def analyze_frontier(root: Path) -> FrontierReport:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    report = FrontierReport(root=root, generated_at=now, envelope_count=0)

    envelope_docs = _load_envelopes(root)
    report.envelope_count = len(envelope_docs)

    id_to_doc: Dict[str, Dict[str, Any]] = {}
    id_to_path: Dict[str, str] = {}

    for path, doc in envelope_docs:
        eid = doc.get("id", "")
        id_to_doc[eid] = doc
        id_to_path[eid] = str(path.relative_to(root).as_posix())

    all_internal: List[str] = sorted(id_to_doc.keys())
    adj: Dict[str, Set[str]] = {n: set() for n in all_internal}
    external_targets: Set[str] = set()
    edge_count = 0

    for eid, doc in id_to_doc.items():
        rels = doc.get("relations") or []
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            kind = rel.get("kind", "")
            target = rel.get("target", "")
            if not kind or not target:
                continue
            if kind in FORWARD_KINDS:
                # eid -> target (eid causally precedes target)
                if target not in adj:
                    adj[target] = set()
                    external_targets.add(target)
                adj[eid].add(target)
                edge_count += 1
            elif kind in BACKWARD_KINDS:
                # target -> eid (target causally precedes eid)
                if target not in adj:
                    adj[target] = set()
                    external_targets.add(target)
                adj[target].add(eid)
                edge_count += 1

    all_nodes = all_internal + sorted(external_targets)
    report.causal_edge_count = edge_count
    report.external_target_ids = sorted(external_targets)

    # Cycle detection
    cycle_witness = _detect_cycle(all_nodes, adj)
    if cycle_witness:
        report.has_cycle = True
        report.cycle_witness = cycle_witness

    # Compute successors (nodes that are caused BY each node)
    has_successor: Set[str] = set()
    for u, targets in adj.items():
        for v in targets:
            has_successor.add(u)

    # Frontier: internal nodes with no outgoing causal edge (i.e. nothing they precede)
    frontier: List[str] = [n for n in all_internal if n not in has_successor]
    report.frontier_ids = frontier

    # Verification ratio over frontier
    verified = 0
    unverified = 0
    not_checkable = 0
    for fid in frontier:
        doc = id_to_doc.get(fid, {})
        result = _verify_digest(doc)
        if result is True:
            verified += 1
        elif result is False:
            unverified += 1
        else:
            not_checkable += 1

    report.verified_count = verified
    report.unverified_count = unverified
    report.not_checkable_count = not_checkable
    if frontier:
        report.verification_ratio = verified / len(frontier)

    # Build node summaries
    for eid, doc in id_to_doc.items():
        payload = doc.get("payload") or {}
        integ = doc.get("integrity") or {}
        rels = doc.get("relations") or []
        digest_verified = _verify_digest(doc)
        node = NodeSummary(
            envelope_id=eid,
            path=id_to_path.get(eid, "?"),
            observed_at=doc.get("observed_at"),
            has_inline_value="value" in payload if isinstance(payload, dict) else False,
            has_reference="reference" in payload if isinstance(payload, dict) else False,
            integrity_algo=integ.get("algorithm") if isinstance(integ, dict) else None,
            integrity_canon=integ.get("canonicalization") if isinstance(integ, dict) else None,
            digest_verified=digest_verified,
            relation_count=len([r for r in rels if isinstance(r, dict)]),
            on_frontier=eid in frontier,
        )
        report.nodes.append(node)

    return report


def to_encounter_payload(report: FrontierReport) -> Dict[str, Any]:
    """Serialize the report as an encounter envelope payload value."""
    return {
        "root": str(report.root),
        "generated_at": report.generated_at,
        "envelope_count": report.envelope_count,
        "causal_edge_count": report.causal_edge_count,
        "frontier_size": len(report.frontier_ids),
        "has_cycle": report.has_cycle,
        "cycle_witness": report.cycle_witness,
        "external_target_count": len(report.external_target_ids),
        "external_targets": report.external_target_ids,
        "frontier_ids": report.frontier_ids,
        "verification_ratio": report.verification_ratio,
        "verified_count": report.verified_count,
        "unverified_count": report.unverified_count,
        "not_checkable_count": report.not_checkable_count,
        "nodes": [
            {
                "id": n.envelope_id,
                "path": n.path,
                "observed_at": n.observed_at,
                "has_inline_value": n.has_inline_value,
                "has_reference": n.has_reference,
                "integrity_algo": n.integrity_algo,
                "integrity_canon": n.integrity_canon,
                "digest_verified": n.digest_verified,
                "relation_count": n.relation_count,
                "on_frontier": n.on_frontier,
            }
            for n in sorted(report.nodes, key=lambda n: n.envelope_id)
        ],
    }


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    if not root.is_dir():
        print(f"[ERROR] Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    report = analyze_frontier(root)

    for line in report.summary_lines():
        print(line)

    if report.has_cycle:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
