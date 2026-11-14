"""PON-003: bounded HTTP origin retrieval and receiver-owned orbit reconstruction.

Two independently signed publication *claims* are validated before any GET.
A route returns untrusted bytes, never a mathematical result. The observing
host independently verifies the fixed root and all necessary CAG-001 packets.
Physical origin independence requires external provisioning and observation:
two HTTP server processes alone do not prove separate storage infrastructures.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "convergent-ground-fabric"))
from convergent_fabric import Replica, ConvergenceError

from passive_orbit import (
    ROOT_PIN, PassiveRejected, NoRedirect, HASH, canonical,
    checked_manifest, checked_packet, digest, require
)
from pon003_origin import verify_publication, check_raw_cid, NAMES, raw_cid

REPORT_SCHEMA = "in-formation.pon003.surviving-origin-navigation/0.1"
REQUEST_LIMIT = 20
TIMEOUT_S = 3.0
MAX_ORIGINS = 2


@dataclass(frozen=True)
class Origin:
    kind: str
    base_url: str
    public: bool = False

    def __post_init__(self) -> None:
        require(self.kind in NAMES and type(self.public) is bool,
                "unrecognized origin type")
        parsed = urlsplit(self.base_url)
        require(not parsed.username and not parsed.password and
                not parsed.query and not parsed.fragment and
                parsed.path == "/" and self.base_url.endswith("/") and
                parsed.port != 0, "origin must use exact configured URL")
        if self.public:
            if self.kind == "r2":
                require(parsed.scheme == "https" and
                        re.fullmatch(r"[a-zA-Z0-9-]+\.r2\.dev",
                                     parsed.hostname or "") is not None and
                        parsed.port is None,
                        "public bucket must be operator-owned R2 public development URL")
            else:
                require(parsed.scheme == "https" and
                        parsed.hostname == "ipfs.io" and
                        parsed.port is None,
                        "public IPFS gateway restricted to ipfs.io")
        else:
            require(parsed.scheme == "http" and
                    parsed.hostname == "127.0.0.1" and
                    parsed.port is not None and 1 <= parsed.port <= 65535,
                    "test origins must bind exact loopback IPv4")

    @property
    def origin_id(self) -> str:
        return NAMES[self.kind]

    def object_url(self, entry: dict) -> str:
        check_raw_cid(entry["raw_cid"], entry["sha256"])
        if self.kind == "r2":
            return self.base_url + entry["path"]
        return self.base_url + "ipfs/" + entry["raw_cid"] + "?format=raw"


class Fetcher:
    def __init__(self, *, timeout: float = TIMEOUT_S) -> None:
        require(0 < timeout <= 10, "bounded HTTP timeout required")
        self.opener = build_opener(NoRedirect)
        self.timeout = timeout
        self.count = 0

    def read(self, origin: Origin, entry: dict, *, max_bytes: int
             ) -> tuple[bytes | None, str, int]:
        require(self.count < REQUEST_LIMIT, "HTTP read budget exhausted")
        require(max_bytes in (4096, 12_000), "unexpected read budget")
        self.count += 1
        request = Request(
            origin.object_url(entry),
            headers={
                "User-Agent": "In-Formation-Space-PON003/0.1",
                "Accept": "application/vnd.ipld.raw" if origin.kind == "ipfs"
                          else "application/octet-stream",
            }, method="GET"
        )
        began = time.perf_counter_ns()
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                require(response.status == 200, "unexpected HTTP success code")
                if origin.kind == "ipfs":
                    require(response.headers.get("Content-Type", "").split(";")[0].strip() ==
                            "application/vnd.ipld.raw",
                            "IPFS gateway did not serve verifiable raw block")
                raw = response.read(max_bytes + 1)
                require(len(raw) <= max_bytes, "response exceeded byte bound")
                return raw, "retrieved", time.perf_counter_ns() - began
        except HTTPError as exc:
            return None, "http_" + str(exc.code), time.perf_counter_ns() - began
        except (URLError, TimeoutError, OSError) as exc:
            return None, "unavailable", time.perf_counter_ns() - began


def reconstruct(*, origins: list[Origin], receipts: dict[str, dict],
                pinned_keys: dict[str, bytes], epoch_floor: dict[str, int],
                now: int, root_pin: str = ROOT_PIN, fetcher: Any = None) -> dict:
    """Require independent pinned signers. Outage never bypasses the root pin."""
    require(type(origins) is list and len(origins) == 2 and
            all(type(o) is Origin for o in origins) and
            {o.kind for o in origins} == {"r2", "ipfs"},
            "one distinct bucket and blockstore origin each required")
    require(type(receipts) is dict and type(pinned_keys) is dict and
            type(epoch_floor) is dict and
            set(receipts) == set(pinned_keys) == set(epoch_floor) ==
            {"r2", "ipfs"},
            "two independently receiver-pinned origin identities required")
    require(pinned_keys["r2"] != pinned_keys["ipfs"],
            "two origin identities cannot share one signing key")
    verified = {
        kind: verify_publication(
            receipt=receipts[kind], trusted_public_key=pinned_keys[kind],
            expected_kind=kind, root_pin=root_pin,
            floor=epoch_floor[kind], now=now)
        for kind in ("r2", "ipfs")
    }
    require(verified["r2"] == verified["ipfs"],
            "origin claims do not commit to identical object inventory")

    events: list[dict] = []
    selected: dict[str, str] = {}
    io = fetcher if fetcher is not None else Fetcher()
    by_sid = verified["r2"]
    failures = {o.kind: 0 for o in origins}

    def obtain(sid: str, packet: bool) -> bytes | None:
        require(sid in by_sid, "unbound semantic identity")
        entry = by_sid[sid]
        for origin in sorted(origins, key=lambda o:
                             (failures[o.kind], origins.index(o))):
            raw, status, elapsed = io.read(
                origin, entry, max_bytes=4096 if packet else 12_000)
            if raw is not None:
                try:
                    require(digest(raw) == entry["sha256"],
                            "retrieved content differs from origin commitment")
                    if packet:
                        checked_packet(raw, identity=sid, address=entry["sha256"])
                    else:
                        checked_manifest(raw, root_pin)
                    status = "verified"
                except (PassiveRejected, ConvergenceError, ValueError):
                    status = "rejected_integrity_or_semantics"
            events.append({
                "semantic_id": sid, "origin": origin.kind,
                "status": status, "elapsed_ns_local": elapsed,
                "expected_sha256": entry["sha256"],
                "raw_cid": entry["raw_cid"],
                "mode": "public" if origin.public else "local_test",
            })
            if status == "verified":
                selected[sid] = origin.kind
                return raw
            failures[origin.kind] += 1
        return None

    root = obtain("root", False)
    if root is None:
        return {
            "schema": REPORT_SCHEMA,
            "status": "unresolved", "target": None, "value": None,
            "reason": "all_origins_missing_or_invalid_root",
            "missing": ["root"], "events": events,
            "selected_origins": selected, "result_digest": None,
            "verified_object_count": 0,
            "origin_policy_pins_verified": True,
            "passive_origins_executed_code": False,
            "external_effects_authorized": False,
        }
    manifest = checked_manifest(root, root_pin)
    committed = {s["semantic_id"]: s["sha256"] for s in by_sid.values()}
    expected = {"root": root_pin}
    expected.update({i["semantic_id"]: i["object_sha256"]
                     for i in manifest["objects"]})
    require(committed == expected, "published inventory does not match pinned root")
    missing: list[str] = []
    loaded: set[str] = set()
    active: set[str] = set()
    replica = Replica()

    def visit(sid: str) -> None:
        if sid in loaded or sid in active:
            return
        loaded.add(sid)
        if sid not in by_sid:
            missing.append(sid)
            return
        raw = obtain(sid, True)
        if raw is None:
            missing.append(sid)
            return
        item = checked_packet(raw, identity=sid, address=by_sid[sid]["sha256"])
        replica.ingest(item, route=selected[sid])
        active.add(sid)
        try:
            for parent in item["parents"]:
                visit(parent)
        finally:
            active.remove(sid)

    visit(manifest["target"])
    evaluation = replica.evaluate(manifest["target"])
    complete = evaluation["status"] == "locally_reconstructed_pure_result"
    core = {
        "schema": REPORT_SCHEMA,
        "status": "verified_reconstruction" if complete else "unresolved",
        "evaluation_status": evaluation["status"],
        "root_sha256": root_pin, "target": manifest["target"],
        "value": evaluation.get("value") if complete else None,
        "result_digest": evaluation.get("result_digest") if complete else None,
        "lineage": evaluation.get("lineage", []) if complete else [],
        "missing": sorted(set(missing)),
        "verified_object_count": len(selected) - 1,
        "selected_origins": selected,
        "events": events,
        "receipt_sha256_by_origin": {
            k: digest(canonical(receipts[k])) for k in ("r2", "ipfs")
        },
        "publisher_public_key_sha256_by_origin": {
            k: digest(pinned_keys[k]) for k in ("r2", "ipfs")
        },
        "epoch_floor": epoch_floor,
        "all_sources_same_public_repo_fixture": True,
        "separate_origin_publication_keys": True,
        "origin_policy_pins_verified": True,
        "origins_are_public": all(o.public for o in origins),
        "physical_origin_independence_attested": False,
        "source_issuer_independently_authenticated": False,
        "passive_origins_executed_code": False,
        "external_effects_authorized": False,
    }
    core["evidence_sha256"] = digest(canonical(core))
    return core


def main() -> None:
    parser = __import__("argparse").ArgumentParser(description=__doc__)
    parser.add_argument("--r2-base", required=True)
    parser.add_argument("--ipfs-base", required=True)
    parser.add_argument("--r2-receipt", type=Path, required=True)
    parser.add_argument("--ipfs-receipt", type=Path, required=True)
    parser.add_argument("--r2-public-key", type=Path, required=True)
    parser.add_argument("--ipfs-public-key", type=Path, required=True)
    parser.add_argument("--mode", choices=("local", "public"), required=True)
    parser.add_argument("--priority", choices=("r2", "ipfs"), default="r2")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # A real deployment must separately authenticate the pinned keys
    # and their administrative provenance, never merely trust a fetched key.
    receipts = {
        k: json.loads(getattr(args, k + "_receipt").read_bytes())
        for k in ("r2", "ipfs")
    }
    pins = {
        k: bytes.fromhex(getattr(args, k + "_public_key").read_text().strip())
        for k in ("r2", "ipfs")
    }
    sites = [Origin("r2", args.r2_base, args.mode == "public"),
             Origin("ipfs", args.ipfs_base, args.mode == "public")]
    if args.priority == "ipfs":
        sites.reverse()
    report = reconstruct(
        origins=sites,
        receipts=receipts, pinned_keys=pins,
        epoch_floor={"r2": 1, "ipfs": 1},
        now=int(time.time())
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report) + b"\n")
    print(json.dumps({
        "status": report["status"], "value": report["value"],
        "source_by_object": report["selected_origins"],
        "result_digest": report["result_digest"],
    }, sort_keys=True))
    if report["status"] != "verified_reconstruction":
        parser.exit(1, "PON003: no verified realization available\n")


if __name__ == "__main__":
    main()
