"""CGS-010 — restore CGS-008 Ground authority through E-CPU's REAL mTLS quorum.

Reuses the pinned E-CPU DistributedRecoveryLineageCoordinator and
RecoveryLineageAuthorityService. No new quorum, vote logic, or transport.

An owner/receiver process may die completely. Its successor has provisioned
trust bootstrap, owner identity/journal, authenticated endpoints, and a
separately persisted content-addressed archive, but NO candidate checkpoint.
It discovers the quorum high-water root and reconstructs only those bytes.
No recovered historical observation authorizes current execution.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any

from mailcpu import (
    DistributedRecoveryLineageCoordinator,
    RecoveryLineageAuthority,
    RecoveryLineagePeerClient,
    RecoveryStateManifest,
    SeedCommitMembership,
)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ecpu_quorum_bridge as existing  # noqa: E402
import verify_authority as independent  # noqa: E402

MEMBERS = ("A", "B", "C")
OWNER_DNS = "owner-a.mailcpu.test"
DNS = {"B": "member-b.mailcpu.test", "C": "member-c.mailcpu.test"}
SCHEMA = "ifs.cgs010-reconstructed-receiver/0.1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("CGS-010 refused: " + message)


def membership_for(trust: dict[str, Any]) -> SeedCommitMembership:
    """Owner/authority identities are pinned to the exact CGS-008 trust root."""
    h = independent.digest(trust)
    return SeedCommitMembership(
        "cgs010-" + h[:32], 1, MEMBERS, "A", 1,
        existing.sha(("IFS-CGS010-GENESIS:" + h).encode("ascii")),
    )


def read_trust(path: Path) -> dict:
    """External provisioned trust is not read from a candidate checkpoint."""
    obj = json.loads(path.read_text(encoding="utf8"))
    require(type(obj) is dict and obj.get("schema") == "ifs.cgs008-trust/0.1",
            "provisioned trust does not have the expected schema")
    return obj


def open_distributed(membership: SeedCommitMembership, owner_journal: Path,
                     tls_dir: Path, endpoints_file: Path
                     ) -> DistributedRecoveryLineageCoordinator:
    """mTLS authenticated real E-CPU service connections, never mock peers."""
    endpoints = json.loads(endpoints_file.read_text(encoding="utf8"))
    require(type(endpoints) is dict and set(endpoints) == set(DNS),
            "expected exactly the configured remote authorities B and C")
    ctx = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH, cafile=str(tls_dir / "ca.pem"))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(tls_dir / "A.pem"), str(tls_dir / "A.key"))
    peers: dict[str, RecoveryLineagePeerClient] = {}
    try:
        for member, dns in DNS.items():
            ep = endpoints[member]
            require(type(ep) is dict and set(ep) == {"host", "port", "dns"} and
                    ep["dns"] == dns and ep["host"] == "127.0.0.1" and
                    type(ep["port"]) is int and 0 < ep["port"] <= 65535,
                    "authority endpoint configuration is not pinned")
            peers[member] = RecoveryLineagePeerClient.connect_mutual_tls(
                membership, member, ep["host"], ep["port"], ctx,
                server_hostname=dns, timeout=2.0, handshake_timeout=2.0,
            )
        owner = RecoveryLineageAuthority(membership, "A", owner_journal)
        return DistributedRecoveryLineageCoordinator(
            membership, {"A": owner, **peers})
    except Exception:
        for p in peers.values():
            p.close()
        raise


def stored_path(archive: Path, kind: str, digest: str) -> Path:
    require(kind in ("sources", "objects", "manifests") and
            type(digest) is str and len(digest) == 64 and
            all(c in "0123456789abcdef" for c in digest),
            "content address invalid")
    return archive / kind / (digest + ".json")


def persist_candidate(archive: Path, bundle: dict, manifest: RecoveryStateManifest,
                      raw: bytes) -> None:
    """Stage bytes and fsync before E-CPU quorum issues its proof."""
    source = existing.canonical(bundle)
    source_digest = existing.sha(source)
    require(source_digest == json.loads(raw)["source_bundle_digest"],
            "signed source not bound to candidate")
    existing.atomic_create(stored_path(archive, "sources", source_digest), source)
    existing.atomic_create(stored_path(archive, "objects", manifest.state_digest), raw)
    existing.atomic_create(stored_path(archive, "manifests", manifest.digest),
                           existing.canonical(manifest.snapshot()))


def seal_two(bundle_path: Path, archive: Path, trust_file: Path,
             owner_journal: Path, tls_dir: Path, endpoints_file: Path, *,
             ready_file: Path | None = None, hold_for_hard_kill: bool = False) -> dict:
    """One live owner process commits both original signed CGS-008 generations."""
    trust = read_trust(trust_file)
    bundle = existing.load_bundle(bundle_path)
    require(bundle["trust"] == trust, "source trust does not match provisioned bootstrap")
    membership = membership_for(trust)
    coordinator = open_distributed(
        membership, owner_journal, tls_dir, endpoints_file)
    result = []
    try:
        for generation in (1, 2):
            previous_generation, previous_root = coordinator.high_water()
            require(previous_generation == generation - 1,
                    "authority high-water is not the expected predecessor")
            candidate = existing.state_document(bundle, generation)
            raw = existing.canonical(candidate)
            manifest = existing.manifest_for(
                membership, generation, previous_root, raw)
            persist_candidate(archive, bundle, manifest, raw)
            proof = coordinator.seal(manifest)
            require(coordinator.verify_state(manifest).proposal.digest ==
                    proof.proposal.digest, "committed root not readable from quorum")
            result.append({
                "generation": generation,
                "manifest_root": manifest.digest,
                "decision_members": sorted(d.member_id for d in proof.decisions),
                "state_digest": manifest.state_digest,
            })
        report = {"sealed": result, "checkpoint_files_on_owner": 0,
                  "quorum_protocol": "mailcpu.DistributedRecoveryLineageCoordinator"}
        if ready_file is not None:
            existing.atomic_create(ready_file, existing.canonical(report))
        if hold_for_hard_kill:
            require(ready_file is not None, "hard-kill test requires durable readiness")
            print(json.dumps(report, sort_keys=True), flush=True)
            # Preserve authenticated E-CPU streams so SIGKILL severs them.
            while True:
                time.sleep(0.2)
        return report
    finally:
        coordinator.close()


def recover_from_quorum(archive: Path, trust_file: Path,
                        owner_journal: Path, tls_dir: Path,
                        endpoints_file: Path, *,
                        candidate_hint: str | None = None) -> dict:
    """Replacement receives no checkpoint; quorum root selects exact archive data."""
    trust = read_trust(trust_file)
    membership = membership_for(trust)
    coordinator = open_distributed(
        membership, owner_journal, tls_dir, endpoints_file)
    try:
        proof = coordinator.latest_proof()  # >= 2 matching durable commit decisions
        require(proof is not None, "no quorum-sealed state can be recovered")
        generation = proof.proposal.slot
        root = proof.proposal.result_state_digest
        require(candidate_hint is None or candidate_hint == root,
                "valid but superseded candidate is not the quorum high-water")
        # The authoritative root was obtained before reading any archived state.
        manifest_bytes = stored_path(
            archive, "manifests", root).read_bytes()
        manifest_snapshot = json.loads(manifest_bytes)
        require(manifest_bytes == existing.canonical(manifest_snapshot),
                "manifest archive is not canonical")
        manifest = RecoveryStateManifest.from_snapshot(manifest_snapshot)
        require(manifest.digest == root and manifest.generation == generation,
                "archive manifest disagrees with quorum root")
        state_bytes = stored_path(
            archive, "objects", manifest.state_digest).read_bytes()
        manifest.verify_payload(state_bytes)
        verified = coordinator.verify_state(manifest)
        require(verified.proposal.digest == proof.proposal.digest,
                "quorum high-water changed during recovery")
        body = json.loads(state_bytes)
        require(state_bytes == existing.canonical(body),
                "state archive is not canonical")
        require(body.get("generation") == generation and
                body.get("schema") == existing.SCHEMA and
                body.get("current_execution_authorized") is False,
                "archived state cannot grant authority to act")
        src_digest = body.get("source_bundle_digest")
        source_bytes = stored_path(archive, "sources", src_digest).read_bytes()
        require(existing.sha(source_bytes) == src_digest,
                "source content-address mismatch")
        source = json.loads(source_bytes)
        require(source_bytes == existing.canonical(source),
                "source archive not canonical")
        independent.verify_bundle(source)  # real Ed25519 recheck in new process
        require(source["trust"] == trust and
                body == existing.state_document(source, generation),
                "archived receiver state violates the signed Ground evidence")
        cp = body["checkpoint"]["body"]
        require(cp["policy_version"] == generation and
                cp["counter"] == generation and
                cp["last_receipt"] != existing.sha(b""),
                "restored policy/counter/receipt inconsistent")
        return {
            "schema": SCHEMA,
            "status": "historical-state-recovered-under-remote-quorum",
            "generation": generation,
            "manifest_root": root,
            "state_digest": manifest.state_digest,
            "receiver_counter": cp["counter"],
            "policy_version": cp["policy_version"],
            "receipt_digest": cp["last_receipt"],
            "source_ed25519_verified": True,
            "state_selected_from_quorum_not_local_checkpoint": True,
            "requires_fresh_challenge": True,
            "current_execution_authorized": False,
            "scope": "real loopback mTLS authority processes; independent journals; one machine",
        }
    finally:
        coordinator.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("seal-two", "recover"))
    p.add_argument("--bundle", type=Path)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--trust", type=Path, required=True)
    p.add_argument("--owner-journal", type=Path, required=True)
    p.add_argument("--tls-dir", type=Path, required=True)
    p.add_argument("--endpoints", type=Path, required=True)
    p.add_argument("--candidate-hint")
    p.add_argument("--ready-file", type=Path)
    p.add_argument("--hard-kill-ready", action="store_true")
    args = p.parse_args()
    if args.command == "seal-two":
        require(args.bundle is not None, "initial owner needs the public signed source")
        report = seal_two(
            args.bundle, args.archive, args.trust, args.owner_journal,
            args.tls_dir, args.endpoints,
            ready_file=args.ready_file, hold_for_hard_kill=args.hard_kill_ready)
        print(json.dumps(report, sort_keys=True), flush=True)
    else:
        require(args.bundle is None, "replacement must NOT receive prior source bundle")
        report = recover_from_quorum(
            args.archive, args.trust, args.owner_journal,
            args.tls_dir, args.endpoints, candidate_hint=args.candidate_hint)
        print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
