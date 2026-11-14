"""PON-002: observer-owned signed root and navigable multi-delivery operation orbit.

Every route is a *read-only byte source*. Public providers are restricted to
the user's own immutable GitHub commit, through GitHub raw or jsDelivr CDN.
They are different delivery operators, NOT independently established origins.
The observer realizes only pure, bounded CAG-001 arithmetic after verifying
a signature, exact root SHA, packet bytes and dependency closure.

Signing keys are generated outside this module and the recipient must pin the
public key through a separately trusted channel; a published public key alone
is not independent authority or revocation evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from passive_orbit import (
    ROOT_PIN, PUBLIC_PATH, SOURCE_REPOSITORY, HASH, Fetcher, PassiveRejected,
    canonical, checked_manifest, checked_packet, digest, require,
)
from convergent_fabric import Replica, ConvergenceError

CAP_SCHEMA = "in-formation.pon002-root-capability/0.1"
REPORT_SCHEMA = "in-formation.pon002-orbit-navigation/0.1"
SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
ID = re.compile(r"[a-z][a-z0-9_-]{0,23}\Z")
MAX_OBJECTS = 16
MAX_REQUESTS = 54
MAX_ROUTES = 3
MAX_DURATION_S = 3600
SOURCE = "github.com/Kier73/In-Formation-Space"
GITHUB_BASE = "https://raw.githubusercontent.com/Kier73/In-Formation-Space/"
JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/Kier73/In-Formation-Space@"


def public_key_bytes(private: Ed25519PrivateKey) -> bytes:
    return private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def grant_root(*, signer: Ed25519PrivateKey, manifest_sha: str,
               epoch: int, valid_from: int, valid_until: int) -> dict:
    """Produce a short-lived research capability, NOT source provenance."""
    require(type(manifest_sha) is str and HASH.fullmatch(manifest_sha) is not None,
            "root identity missing")
    require(type(epoch) is int and 0 <= epoch <= 10**9, "invalid epoch")
    require(type(valid_from) is int and type(valid_until) is int and
            0 < valid_from <= valid_until and
            valid_until - valid_from <= MAX_DURATION_S,
            "capability lifetime cannot exceed an hour")
    key = public_key_bytes(signer)
    core = {
        "schema": CAP_SCHEMA, "root_sha256": manifest_sha,
        "issuer_public_key_sha256": digest(key),
        "epoch": epoch, "valid_from": valid_from, "valid_until": valid_until,
        "scope": "read-only/pure-cag001",
    }
    return {**core, "signature_hex": signer.sign(canonical(core)).hex()}


def check_grant(*, grant: object, pinned_key: bytes, root_pin: str,
                minimum_epoch: int, now: int) -> dict:
    """Receiver pins issuer key, root, epoch floor and current clock itself."""
    require(type(grant) is dict and set(grant) == {
        "schema", "root_sha256", "issuer_public_key_sha256",
        "epoch", "valid_from", "valid_until", "scope", "signature_hex",
    }, "capability schema mismatch")
    require(type(pinned_key) is bytes and len(pinned_key) == 32,
            "external pinned issuer public key required")
    require(type(root_pin) is str and HASH.fullmatch(root_pin) is not None,
            "external pinned root required")
    require(type(minimum_epoch) is int and minimum_epoch >= 0 and
            type(now) is int and now > 0,
            "receiver anti-rollback policy and time required")
    require(grant["schema"] == CAP_SCHEMA and
            grant["scope"] == "read-only/pure-cag001" and
            grant["root_sha256"] == root_pin and
            grant["issuer_public_key_sha256"] == digest(pinned_key),
            "capability violates receiver-owned source/issuer pin")
    require(type(grant["epoch"]) is int and
            grant["epoch"] >= minimum_epoch and
            type(grant["valid_from"]) is int and
            type(grant["valid_until"]) is int and
            0 < grant["valid_from"] <= now <= grant["valid_until"] and
            grant["valid_until"] - grant["valid_from"] <= MAX_DURATION_S,
            "expired, not-yet-active or rolled-back capability")
    sig = grant["signature_hex"]
    require(type(sig) is str and len(sig) == 128 and
            re.fullmatch(r"[0-9a-f]{128}", sig) is not None,
            "noncanonical signature")
    core = {k: v for k, v in grant.items() if k != "signature_hex"}
    try:
        Ed25519PublicKey.from_public_bytes(pinned_key).verify(bytes.fromhex(sig),
                                                             canonical(core))
    except (InvalidSignature, ValueError) as exc:
        raise PassiveRejected("invalid Ed25519 root capability signature") from exc
    return dict(core)


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    kind: str
    revision: str | None = None

    def __post_init__(self) -> None:
        require(type(self.name) is str and ID.fullmatch(self.name) is not None,
                "invalid provider label")
        require(self.kind in ("github", "jsdelivr", "temporary"), "unknown provider")
        parsed = urlsplit(self.base_url)
        require(not parsed.username and not parsed.password and
                not parsed.query and not parsed.fragment and
                parsed.path.endswith("/") and parsed.port != 0,
                "unsafe provider URL")
        if self.kind == "temporary":
            require(parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and
                    parsed.port is not None and parsed.path == "/" and
                    self.revision is None,
                    "temporary provider must be explicit read-only loopback")
            return
        require(type(self.revision) is str and SHA.fullmatch(self.revision) is not None,
                "public provider must use full immutable Git commit")
        expected = (
            GITHUB_BASE + self.revision + PUBLIC_PATH
            if self.kind == "github" else
            JSDELIVR_BASE + self.revision + PUBLIC_PATH
        )
        require(self.base_url == expected and parsed.scheme == "https" and
                parsed.hostname == ("raw.githubusercontent.com" if self.kind == "github"
                                    else "cdn.jsdelivr.net") and parsed.port is None,
                "public provider path does not match allowlisted immutable source")

    @property
    def operator(self) -> str:
        return {"github": "GitHub", "jsdelivr": "jsDelivr", "temporary": "Local opt-in"}[self.kind]

    @property
    def source_origin(self) -> str:
        return SOURCE if self.kind in ("github", "jsdelivr") else "local-expiring-fixture"


def providers_for_commit(commit: str, *, preference: tuple[str, str] =
                         ("github", "jsdelivr")) -> list[Provider]:
    require(type(commit) is str and SHA.fullmatch(commit) is not None,
            "immutable full Git commit required")
    require(set(preference) == {"github", "jsdelivr"} and len(preference) == 2,
            "unknown public provider preference")
    providers = {
        "github": Provider("github", GITHUB_BASE + commit + PUBLIC_PATH,
                           "github", commit),
        "jsdelivr": Provider("jsdelivr", JSDELIVR_BASE + commit + PUBLIC_PATH,
                             "jsdelivr", commit),
    }
    return [providers[p] for p in preference]


def reconstruct(*, routes: list[Provider], grant: dict,
                pinned_key: bytes, root_pin: str = ROOT_PIN,
                minimum_epoch: int, now: int,
                fetcher: Any | None = None) -> dict:
    """Navigate dependency closure, not the entire declared object inventory."""
    check_grant(grant=grant, pinned_key=pinned_key,
                root_pin=root_pin, minimum_epoch=minimum_epoch, now=now)
    require(type(routes) is list and 1 <= len(routes) <= MAX_ROUTES and
            all(type(r) is Provider for r in routes) and
            len({r.name for r in routes}) == len(routes), "unsafe route selection")
    public_revisions = {r.revision for r in routes if r.kind != "temporary"}
    require(len(public_revisions) <= 1, "cannot mix sources at different Git revisions")
    backend = fetcher or Fetcher()
    events: list[dict] = []
    score = {r.name: 0 for r in routes}  # failure count, not asserted latency consensus
    observed: dict[str, dict] = {}
    packet_bytes: dict[str, bytes] = {}
    attempts = 0
    packet_map: dict[str, dict] = {}
    missing: list[str] = []
    active: set[str] = set()
    used: set[str] = set()
    replica = Replica()

    def obtain(label: str, path: str, expected_hash: str,
               object_id: str | None) -> bytes | None:
        nonlocal attempts
        for route in sorted(routes, key=lambda r: (score[r.name], routes.index(r))):
            require(attempts < MAX_REQUESTS, "network request budget exhausted")
            attempts += 1
            raw, status, elapsed = backend.read(
                route, path, limit=12_000 if object_id is None else 4096)
            if raw is not None:
                try:
                    if object_id is None:
                        checked_manifest(raw, expected_hash)
                    else:
                        checked_packet(raw, identity=object_id, address=expected_hash)
                    status = "verified"
                except PassiveRejected:
                    status = "rejected_integrity_or_semantics"
            events.append({
                "object": label, "provider": route.name,
                "operator": route.operator, "source_origin": route.source_origin,
                "status": status, "elapsed_ns_local": elapsed,
                "content_sha256_expected": expected_hash,
            })
            if status == "verified":
                observed[label] = {
                    "provider": route.name, "operator": route.operator,
                    "source_origin": route.source_origin,
                }
                return raw
            score[route.name] += 1
        return None

    root_raw = obtain("root", "manifest.json", root_pin, None)
    if root_raw is None:
        return {
            "schema": REPORT_SCHEMA, "status": "unresolved",
            "reason": "signed_root_unavailable_or_rejected",
            "target": None, "value": None, "events": events,
            "missing": ["root"], "verified_objects": 0,
            "root_sha256": root_pin, "provider_source_origins":
                sorted({r.source_origin for r in routes if r.kind != "temporary"}),
            "passive_hosts_executed_arithmetic": False,
            "external_effects_authorized": False,
        }
    manifest = checked_manifest(root_raw, root_pin)
    require(len(manifest["objects"]) <= MAX_OBJECTS,
            "orbit dependency/address budget exceeded")
    refs = {p["semantic_id"]: p["object_sha256"] for p in manifest["objects"]}

    def walk(sid: str) -> None:
        if sid in active:
            return  # CAG-001 reconstruction will classify the dependency cycle
        if sid in used:
            return
        used.add(sid)
        expected = refs.get(sid)
        if expected is None:
            missing.append(sid)
            return
        raw = obtain(sid, "objects/" + expected + ".json", expected, sid)
        if raw is None:
            missing.append(sid)
            return
        packet = checked_packet(raw, identity=sid, address=expected)
        packet_map[sid] = packet
        packet_bytes[sid] = raw
        replica.ingest(packet, route=observed[sid]["provider"])
        active.add(sid)
        try:
            for parent in packet["parents"]:
                walk(parent)
        finally:
            active.remove(sid)

    walk(manifest["target"])
    computed = replica.evaluate(manifest["target"])
    is_ready = computed["status"] == "locally_reconstructed_pure_result"
    core = {
        "schema": REPORT_SCHEMA,
        "status": "verified_reconstruction" if is_ready else "unresolved",
        "evaluation_status": computed["status"],
        "target": manifest["target"],
        "value": computed["value"] if is_ready else None,
        "result_digest": computed.get("result_digest") if is_ready else None,
        "lineage": computed.get("lineage", []) if is_ready else [],
        "root_sha256": root_pin, "grant_epoch": grant["epoch"],
        "issuer_public_key_sha256": digest(pinned_key),
        "missing": sorted(set(missing)),
        "reachable_closure_ids": sorted(packet_map),
        "verified_objects": len(packet_map),
        "total_manifest_objects": len(refs),
        "delivery_by_object": observed,
        "events": events,
        "provider_source_origins": sorted({r.source_origin for r in routes if
                                           r.kind != "temporary"}),
        "delivery_operators": sorted({r.operator for r in routes if
                                      r.kind != "temporary"}),
        "public_git_commit": next(iter(public_revisions)) if public_revisions else None,
        "passive_hosts_executed_arithmetic": False,
        "externally_authenticated_issuer": False,
        "external_effects_authorized": False,
    }
    core["evidence_digest"] = digest(canonical(core))
    return core


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--provider", choices=("github", "jsdelivr"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    # This ephemeral fixture signer demonstrates verification and tamper
    # resistance, NOT independent source author identity.
    signer = Ed25519PrivateKey.generate()
    now = int(time.time())
    grant = grant_root(signer=signer, manifest_sha=ROOT_PIN, epoch=1,
                       valid_from=now - 15, valid_until=now + 900)
    # The provider jobs deliberately use exactly one real HTTPS operator each.
    # An unavailable provider must fail that job; automatic silent substitution
    # would destroy evidence of independent delivery path availability.
    route = [p for p in providers_for_commit(args.commit) if p.kind == args.provider]
    pub = public_key_bytes(signer)
    result = reconstruct(
        routes=route, grant=grant, pinned_key=pub,
        minimum_epoch=1, now=now,
    )
    envelope = {
        "schema": "in-formation.pon002-provider-report/0.1",
        "provider": args.provider, "public_git_commit": args.commit,
        "issuer_public_key_hex": pub.hex(), "capability": grant,
        "receiver_min_epoch": 1, "observed_at_unix": now,
        "orbit": result,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(canonical(envelope) + b"\n")
    print(json.dumps({
        "status": result["status"], "value": result["value"],
        "requested_provider": args.provider,
        "root_retrieved_from": result.get("delivery_by_object", {}).get("root", {}),
        "result_digest": result.get("result_digest"),
        "verification": result.get("evidence_digest"),
    }, sort_keys=True))
    if result["status"] != "verified_reconstruction":
        parser.exit(1, "PON002: incomplete signed semantic orbit\n")


if __name__ == "__main__":
    main()
