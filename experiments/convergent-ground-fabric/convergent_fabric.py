#!/usr/bin/env python3
"""CAG-001: bounded, transport-agnostic causal anti-entropy for pure operations.

Packets are untrusted descriptions. Local evaluation proves only the bounded
deterministic result of those descriptions; it does not authenticate authors,
authorize external effects, or establish a physical network route.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "in-formation.cag001-operation/0.1"
BUNDLE_SCHEMA = "in-formation.cag001-source-bundle/0.1"
ROUTE_SCHEMA = "in-formation.cag001-route-bundle/0.1"
REPORT_SCHEMA = "in-formation.cag001-convergence-report/0.1"
ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
MAX_VALUE = 1_000_000_000
MAX_PACKET = 4096
ROUTE_PLAN = {
    "blue": ("final", "right", "seed", "right"),
    "amber": ("merge", "left", "seed"),
}
TARGET = "final"


class ConvergenceError(ValueError):
    """Invalid, misleading, or unadmitted description."""


def ensure(ok: bool, reason: str) -> None:
    if not ok:
        raise ConvergenceError(reason)


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(obj) + b"\n")


def read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ensure(isinstance(data, dict), "expected a JSON object")
    return data


def bounded_int(value: Any, label: str) -> int:
    ensure(type(value) is int and abs(value) <= MAX_VALUE, f"{label} is not a bounded integer")
    return value


def packet(semantic_id: str, kind: str, parents: list[str], argument: int | None) -> dict[str, Any]:
    core = {"schema": SCHEMA, "semantic_id": semantic_id, "kind": kind,
            "parents": parents, "argument": argument}
    return {**core, "digest": sha(core)}


def validate(item: Mapping[str, Any]) -> dict[str, Any]:
    ensure(isinstance(item, Mapping), "packet must be a mapping")
    ensure(set(item) == {"schema", "semantic_id", "kind", "parents", "argument", "digest"},
           "unexpected or missing packet fields")
    ensure(item["schema"] == SCHEMA, "packet schema mismatch")
    sid = item["semantic_id"]
    ensure(isinstance(sid, str) and ID.fullmatch(sid) is not None, "invalid semantic identity")
    kind = item["kind"]
    parents = item["parents"]
    ensure(kind in ("constant", "add", "multiply", "sum"), "unrecognized computation kind")
    ensure(isinstance(parents, list) and all(isinstance(p, str) and ID.fullmatch(p)
           for p in parents) and len(parents) == len(set(parents))
           and sid not in parents and len(parents) <= 12,
           "invalid parent list")
    if kind == "constant":
        ensure(len(parents) == 0, "constant cannot have dependencies")
    elif kind in ("add", "multiply"):
        ensure(len(parents) == 1, "unary transform requires one dependency")
    else:
        ensure(2 <= len(parents), "sum requires two or more explicit dependencies")
    if kind == "sum":
        ensure(item["argument"] is None, "sum has no external operand")
    else:
        bounded_int(item["argument"], "argument")
    core = {k: v for k, v in item.items() if k != "digest"}
    ensure(len(canonical(item)) <= MAX_PACKET, "packet exceeds bound")
    ensure(isinstance(item["digest"], str) and item["digest"] == sha(core),
           "packet digest mismatch")
    return dict(item)


def fixture() -> list[dict[str, Any]]:
    return [
        packet("seed", "constant", [], 3),
        packet("left", "add", ["seed"], 4),
        packet("right", "multiply", ["seed"], 5),
        packet("merge", "sum", ["left", "right"], None),
        packet("final", "multiply", ["merge"], 2),
    ]


class Replica:
    """Grow-only union of packet *variants*, never first-arrival-wins."""

    def __init__(self) -> None:
        self.packets: dict[str, dict[str, Any]] = {}
        self.variants: dict[str, set[str]] = {}
        self.routes: dict[str, set[str]] = {}

    def ingest(self, item: Mapping[str, Any], *, route: str) -> bool:
        doc = validate(item)
        ensure(isinstance(route, str) and ID.fullmatch(route) is not None,
               "invalid observational route")
        h = doc["digest"]
        fresh = h not in self.packets
        self.packets[h] = doc
        self.variants.setdefault(doc["semantic_id"], set()).add(h)
        self.routes.setdefault(h, set()).add(route)
        return fresh

    def inventory(self) -> tuple[str, ...]:
        return tuple(sorted(self.packets))

    def missing_from(self, known: set[str]) -> tuple[dict[str, Any], ...]:
        return tuple(self.packets[h] for h in self.inventory() if h not in known)

    def reconcile_from(self, peer: "Replica", *, route: str) -> int:
        missing = peer.missing_from(set(self.inventory()))
        for item in missing:
            self.ingest(item, route=route)
        return len(missing)

    def evaluate(self, target: str) -> dict[str, Any]:
        ensure(ID.fullmatch(target) is not None, "invalid target identity")
        cache: dict[str, tuple[int, set[str]]] = {}
        active: set[str] = set()

        def calculate(sid: str) -> tuple[int, set[str]]:
            variants = self.variants.get(sid, set())
            if not variants:
                raise ConvergenceError(f"unknown_dependency:{sid}")
            if len(variants) > 1:
                raise ConvergenceError(f"conflicting_identity:{sid}")
            if sid in active:
                raise ConvergenceError(f"dependency_cycle:{sid}")
            if sid in cache:
                return cache[sid]
            active.add(sid)
            item = self.packets[next(iter(variants))]
            try:
                parents = [calculate(p) for p in item["parents"]]
                lineage = {item["digest"]}
                for _, dep_lineage in parents:
                    lineage.update(dep_lineage)
                if item["kind"] == "constant":
                    value = item["argument"]
                elif item["kind"] == "add":
                    value = parents[0][0] + item["argument"]
                elif item["kind"] == "multiply":
                    value = parents[0][0] * item["argument"]
                else:
                    value = sum(result for result, _ in parents)
                bounded_int(value, "realized result")
                cache[sid] = value, lineage
                return cache[sid]
            finally:
                active.remove(sid)

        try:
            value, used = calculate(target)
        except ConvergenceError as error:
            code = str(error).split(":", 1)[0]
            ensure(code in {"unknown_dependency", "conflicting_identity",
                            "dependency_cycle", "invalid_result"}, "unexpected evaluation error")
            return {"status": code, "target": target, "value": None,
                    "result_digest": None, "detail": str(error)}
        core = {"status": "locally_reconstructed_pure_result", "target": target,
                "value": value, "lineage": sorted(used)}
        return {**core, "result_digest": sha(core)}


def source_bundle() -> dict[str, Any]:
    docs = fixture()
    core = {"schema": BUNDLE_SCHEMA, "target": TARGET, "packets": docs}
    return {**core, "bundle_digest": sha(core)}


def check_source(source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    ensure(set(source) == {"schema", "target", "packets", "bundle_digest"}
           and source["schema"] == BUNDLE_SCHEMA, "unexpected source-bundle schema")
    docs = source["packets"]
    ensure(isinstance(docs, list) and 1 <= len(docs) <= 50,
           "invalid source-bundle size")
    all_items = [validate(p) for p in docs]
    ensure(source["bundle_digest"] == sha({k: v for k, v in source.items()
                                         if k != "bundle_digest"}), "source-bundle digest mismatch")
    ids = [p["semantic_id"] for p in all_items]
    ensure(len(set(ids)) == len(ids) and source["target"] in ids, "source IDs are not unique")
    return {p["semantic_id"]: p for p in all_items}


def route_bundle(source: Mapping[str, Any], route: str) -> dict[str, Any]:
    ensure(route in ROUTE_PLAN, "unrecognized route")
    doc = check_source(source)
    core = {"schema": ROUTE_SCHEMA, "route": route, "source_bundle_digest": source["bundle_digest"],
            "packets": [doc[sid] for sid in ROUTE_PLAN[route]]}
    return {**core, "bundle_digest": sha(core)}


def check_route(route_doc: Mapping[str, Any], source: Mapping[str, Any],
                expected_route: str) -> list[dict[str, Any]]:
    ensure(set(route_doc) == {"schema", "route", "source_bundle_digest", "packets", "bundle_digest"}
           and route_doc["schema"] == ROUTE_SCHEMA and route_doc["route"] == expected_route
           and expected_route in ROUTE_PLAN, "route-bundle contract mismatch")
    ensure(route_doc["source_bundle_digest"] == source["bundle_digest"],
           "route bound to different source")
    ensure(route_doc["bundle_digest"] == sha({k: v for k, v in route_doc.items()
                                            if k != "bundle_digest"}), "route digest mismatch")
    docs = route_doc["packets"]
    ensure(isinstance(docs, list) and len(docs) == len(ROUTE_PLAN[expected_route]),
           "route packet count changed")
    source_ids = check_source(source)
    ensure([p.get("semantic_id") for p in docs] == list(ROUTE_PLAN[expected_route]),
           "route packet identities changed")
    ensure(all(validate(p) == source_ids[p["semantic_id"]] for p in docs),
           "route has modified source packets")
    return [dict(p) for p in docs]


def verify(source: Mapping[str, Any], blue: Mapping[str, Any],
           amber: Mapping[str, Any]) -> dict[str, Any]:
    original = check_source(source)
    # Independent reference interpretation: does not rely on either route's claimed result.
    reference = Replica()
    for item in original.values():
        reference.ingest(item, route="reference")
    expected = reference.evaluate(source["target"])
    ensure(expected["status"] == "locally_reconstructed_pure_result", "source program unresolved")

    routes = {"blue": check_route(blue, source, "blue"),
              "amber": check_route(amber, source, "amber")}
    receivers = []
    for order in (("blue", "amber"), ("amber", "blue")):
        replica = Replica()
        partials = []
        for name in order:
            for item in routes[name]:
                replica.ingest(item, route=name)
            partials.append(replica.evaluate(source["target"])["status"])
        result = replica.evaluate(source["target"])
        ensure(result == expected, "multi-route delivery altered deterministic result")
        receivers.append({"route_order": list(order), "partial_statuses": partials,
                          "final": result, "distinct_packets": len(replica.inventory()),
                          "route_observations": {
                              h: sorted(rs) for h, rs in sorted(replica.routes.items())
                          }})
    core = {
        "schema": REPORT_SCHEMA,
        "status": "multi_route_eventual_convergence",
        "source_digest": source["bundle_digest"],
        "route_digests": {name: payload["bundle_digest"]
                          for name, payload in (("blue", blue), ("amber", amber))},
        "expected": expected,
        "receivers": receivers,
        "semantic_delivery_route": "GitHub Actions artifacts in hosted CI; deterministic local fixture outside CI",
        "limitations": [
            "Routes are simulated by separate artifact-producing GitHub jobs; no direct host connection or physical network independence is established.",
            "SHA-256 content identity does not authenticate an issuer or authorize a state-changing action.",
            "Only finite deterministic pure arithmetic is reconstructed, never external side effects.",
            "At least one missing dependency remains unresolved; convergence requires eventual delivery of all necessary records.",
            "Conflicting semantic IDs remain conflicted and must not be resolved by arrival order.",
            "Transport acknowledgements, artifact upload, and local recomputation are distinct evidence layers.",
        ],
    }
    return {**core, "report_digest": sha(core)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("source")
    a.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("relay")
    b.add_argument("--source", type=Path, required=True)
    b.add_argument("--route", choices=sorted(ROUTE_PLAN), required=True)
    b.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("verify")
    for name in ("source", "blue", "amber"):
        c.add_argument("--" + name, type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "source":
            result = source_bundle()
        elif args.command == "relay":
            result = route_bundle(read(args.source), args.route)
        else:
            result = verify(read(args.source), read(args.blue), read(args.amber))
        write(args.out, result)
        print(json.dumps({"command": args.command, "status": result.get("status", "written"),
                          "digest": sha(result)}, sort_keys=True))
    except (ConvergenceError, ValueError, KeyError, TypeError) as exc:
        p.exit(1, f"CAG-001 rejected: {exc}\n")


if __name__ == "__main__":
    main()
