"""PON-001: navigate verified immutable computation descriptions on passive hosts.

A route provides *bytes*, not computation. The observer pins a manifest root,
verifies every packet by its exact content digest, then independently
reconstructs finite pure arithmetic using CAG-001. Public routes are restricted
to this repo's raw.githubusercontent.com object subtree; temporary routes are
restricted to loopback test hosts. No arbitrary URL fetching, redirects, remote
execution, or uncontrolled third-party storage is provided.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, quote
from urllib.request import build_opener, HTTPRedirectHandler, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "convergent-ground-fabric"))
from convergent_fabric import Replica, validate, ConvergenceError, canonical as cag_canonical

SCHEMA = "in-formation.pon001.route-manifest/0.1"
REPORT_SCHEMA = "in-formation.pon001.navigation-evidence/0.1"
HERE = Path(__file__).resolve().parent
ROOT_PIN = "1345e9576fba37322a92cdf9e48c525c806ba210b389ac9a411ec1923484f229"
HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST = 12_000
MAX_PACKET = 4096
MAX_REQUESTS = 32
MAX_OBJECTS = 32
PUBLIC_PATH = "/experiments/passive-orbit-cache/public/"
SOURCE_REPOSITORY = "/Kier73/In-Formation-Space/"


class PassiveRejected(ValueError):
    """Untrusted passive storage or source authorization could not be verified."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise PassiveRejected(reason)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def checked_manifest(raw: bytes, expected: str) -> dict:
    require(type(raw) is bytes and 0 < len(raw) <= MAX_MANIFEST,
            "manifest exceeds byte budget")
    require(type(expected) is str and HASH.fullmatch(expected) is not None,
            "receiver must pin exact manifest identity")
    require(digest(raw) == expected, "untrusted manifest digest mismatch")
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PassiveRejected("unparseable manifest") from exc
    require(type(doc) is dict and canonical(doc) == raw and
            set(doc) == {"schema", "target", "objects"} and
            doc["schema"] == SCHEMA, "noncanonical manifest or unexpected fields")
    objs = doc["objects"]
    require(type(objs) is list and 1 <= len(objs) <= MAX_OBJECTS,
            "invalid object count")
    seen = set()
    for obj in objs:
        require(type(obj) is dict and
                set(obj) == {"semantic_id", "object_sha256"}, "invalid object reference")
        sid = obj["semantic_id"]
        h = obj["object_sha256"]
        require(type(sid) is str and re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", sid) and
                type(h) is str and HASH.fullmatch(h) is not None and
                sid not in seen, "duplicate/invalid semantic reference")
        seen.add(sid)
    require(doc["target"] in seen, "target must be pinned")
    return doc


def checked_packet(raw: bytes, *, identity: str, address: str) -> dict:
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PACKET,
            "object exceeds packet bound")
    require(type(address) is str and HASH.fullmatch(address) is not None and
            digest(raw) == address, "content address mismatch")
    try:
        obj = json.loads(raw)
        require(type(obj) is dict and canonical(obj) == raw,
                "object is not canonical")
        packet = validate(obj)
    except (UnicodeDecodeError, json.JSONDecodeError, ConvergenceError) as exc:
        raise PassiveRejected("invalid CAG-001 packet on passive host") from exc
    require(packet["semantic_id"] == identity,
            "semantic identity differs from pinned reference")
    return packet


@dataclass(frozen=True)
class Route:
    name: str
    base_url: str
    kind: str

    def __post_init__(self) -> None:
        require(type(self.name) is str and
                re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", self.name) is not None,
                "invalid route label")
        require(self.kind in ("public", "temporary"),
                "route must identify public or temporary substrate")
        parsed = urlsplit(self.base_url)
        require(not parsed.username and not parsed.password and
                not parsed.query and not parsed.fragment and
                parsed.path.endswith("/"), "unsafe/ambiguous route URL")
        if self.kind == "public":
            require(parsed.scheme == "https" and
                    parsed.hostname == "raw.githubusercontent.com" and
                    parsed.port is None and
                    parsed.path.startswith(SOURCE_REPOSITORY) and
                    parsed.path.endswith(PUBLIC_PATH),
                    "public substrate must be immutable/repository-owned raw objects")
            # Requires a full SHA, never a branch or mutable ref.
            middle = parsed.path[len(SOURCE_REPOSITORY):-len(PUBLIC_PATH)]
            require(HASH.fullmatch(middle) is not None, "public revision must be immutable SHA")
        else:
            require(parsed.scheme == "http" and
                    parsed.hostname == "127.0.0.1" and
                    type(parsed.port) is int and 0 < parsed.port < 65536 and
                    parsed.path == "/", "temporary test route must be explicit loopback")
        require(not parsed.params if hasattr(parsed, "params") else True,
                "unexpected route URL parameters")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise PassiveRejected("passive host redirect prohibited")


class Fetcher:
    def __init__(self, timeout: float = 5.0):
        self._opener = build_opener(NoRedirect)
        self.timeout = timeout
        self.requests = 0

    def read(self, route: Route, path: str, *, limit: int) -> tuple[bytes | None, str, int]:
        require(self.requests < MAX_REQUESTS, "bounded request budget exhausted")
        require(re.fullmatch(r"(manifest.json|objects/[0-9a-f]{64}\.json)", path)
                is not None, "unbounded path/subresource selection")
        self.requests += 1
        target = route.base_url + path
        request = Request(target, headers={
            "User-Agent": "In-Formation-Space-PON001/0.1; bounded passive read",
            "Cache-Control": "no-cache",
        }, method="GET")
        started = time.perf_counter_ns()
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                require(response.status == 200, "unexpected HTTP response")
                payload = response.read(limit + 1)
                require(len(payload) <= limit, "passive host exceeded byte budget")
                return payload, "retrieved", time.perf_counter_ns() - started
        except HTTPError as exc:
            status = f"http_{exc.code}"
            return None, status, time.perf_counter_ns() - started
        except (URLError, TimeoutError, OSError) as exc:
            return None, "unavailable", time.perf_counter_ns() - started


def navigate(routes: list[Route], *, root_pin: str = ROOT_PIN,
             fetcher: Fetcher | None = None) -> dict[str, object]:
    """A receiver-owned manifest root drives retrieval. Remote bytes cannot add URLs."""
    require(type(routes) is list and 1 <= len(routes) <= 3 and
            len(set(r.name for r in routes)) == len(routes),
            "duplicate or excessive passive routes")
    io = fetcher or Fetcher()
    attempts: list[dict] = []
    recovered: list[str] = []
    observations: dict[str, str] = {}
    replica = Replica()

    def recover(path: str, expected: str, identity: str | None,
                budget: int) -> bytes | None:
        for route in routes:
            raw, status, elapsed = io.read(route, path, limit=budget)
            if raw is not None:
                try:
                    if identity is None:
                        checked_manifest(raw, expected)
                    else:
                        checked_packet(raw, identity=identity, address=expected)
                    status = "verified"
                except PassiveRejected:
                    status = "rejected_integrity_or_semantics"
            attempts.append({
                "object": identity or "root", "route": route.name,
                "status": status, "route_kind": route.kind,
                "elapsed_ns_local": elapsed,
            })
            if status == "verified":
                observations[identity or "root"] = route.name
                return raw
        return None

    root = recover("manifest.json", root_pin, None, MAX_MANIFEST)
    if root is None:
        return {
            "schema": REPORT_SCHEMA, "status": "root_unavailable_or_unverified",
            "target": None, "value": None, "missing": ["root"],
            "verified_object_count": 0, "attempts": attempts,
            "local_arithmetic_performed": False,
            "external_execution_authorized": False,
        }
    manifest = checked_manifest(root, root_pin)
    missing = []
    for ref in manifest["objects"]:
        sid = ref["semantic_id"]
        addr = ref["object_sha256"]
        raw = recover("objects/" + addr + ".json", addr, sid, MAX_PACKET)
        if raw is None:
            missing.append(sid)
            continue
        replica.ingest(checked_packet(raw, identity=sid, address=addr),
                       route=observations[sid])
        recovered.append(sid)
    evaluation = replica.evaluate(manifest["target"])
    complete = evaluation["status"] == "locally_reconstructed_pure_result"
    return {
        "schema": REPORT_SCHEMA,
        "status": evaluation["status"] if complete else "unresolved",
        "target": manifest["target"],
        "value": evaluation["value"] if complete else None,
        "lineage": evaluation.get("lineage", []),
        "reconstruction_digest": evaluation.get("result_digest"),
        "receiver_root_pin": root_pin,
        "missing": missing,
        "verified_object_count": len(recovered),
        "source_by_semantic_id": observations,
        "attempts": attempts,
        "local_arithmetic_performed": complete,
        "external_execution_authorized": False,
        "passive_host_executed_operations": False,
        "evaluation_status": evaluation["status"],
        "transported_state": "immutable CAG-001 descriptions, not executable code",
    }


class PassiveHandler(BaseHTTPRequestHandler):
    """Explicitly opt-in, finite read-only local temporary host."""
    def do_GET(self) -> None:
        host = self.server
        if time.monotonic() >= host.expires:
            self.send_error(410)
            return
        if not re.fullmatch(r"/(manifest\.json|objects/[0-9a-f]{64}\.json)", self.path):
            self.send_error(404)
            return
        file = host.root / self.path.lstrip("/")
        if not file.is_file() or file.is_symlink():
            self.send_error(404)
            return
        raw = file.read_bytes()
        if len(raw) > MAX_MANIFEST:
            self.send_error(413)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        self.send_error(405)

    def log_message(self, fmt, *args) -> None:
        pass


def listen(root: Path, *, ttl_seconds: float, port: int = 0) -> ThreadingHTTPServer:
    require(root.is_dir() and not root.is_symlink(), "temporary directory absent or symlinked")
    require(type(ttl_seconds) in (float, int) and 0 < ttl_seconds <= 60,
            "temporary host finite lease is mandatory")
    srv = ThreadingHTTPServer(("127.0.0.1", port), PassiveHandler)
    srv.root = root
    srv.expires = time.monotonic() + ttl_seconds
    srv.daemon_threads = True
    return srv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--directory", type=Path, required=True)
    server.add_argument("--ttl", type=float, default=3.0)
    runner = sub.add_parser("navigate")
    runner.add_argument("--public-sha", required=True)
    runner.add_argument("--temporary", default="")
    runner.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "serve":
        srv = listen(args.directory, ttl_seconds=args.ttl)
        print("LISTEN_PORT=" + str(srv.server_port), flush=True)
        try:
            srv.serve_forever()
        finally:
            srv.server_close()
    else:
        routes = []
        if args.temporary:
            routes.append(Route("ephemeral", args.temporary, "temporary"))
        routes.append(Route("public", "https://raw.githubusercontent.com"
                            + SOURCE_REPOSITORY + args.public_sha + PUBLIC_PATH,
                            "public"))
        result = navigate(routes)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical(result) + b"\n")
        print(json.dumps({
            "status": result["status"], "value": result.get("value"),
            "verified_object_count": result["verified_object_count"],
            "source_by_semantic_id": result.get("source_by_semantic_id"),
        }, sort_keys=True))
        if result["status"] != "locally_reconstructed_pure_result":
            parser.exit(1, "PON001: incomplete/unverified passive information orbit\n")


if __name__ == "__main__":
    main()
