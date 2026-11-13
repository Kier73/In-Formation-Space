"""Owner subprocess that seals one root through cloned mTLS authority credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import ssl
import sys
import time
from typing import Any, Mapping

from mailcpu import (
    DistributedRecoveryLineageCoordinator,
    RecoveryLineageAuthority,
    RecoveryLineagePeerClient,
    RecoveryStateManifest,
    SeedCommitMembership,
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(dict(value)) + b"\n")


def certificate_sha256(path: Path) -> str:
    der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
    return hashlib.sha256(der).hexdigest()


def wait_for_gate(path: Path, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("clone owner did not receive the common start gate")
        time.sleep(0.005)


def run(args: argparse.Namespace) -> dict[str, Any]:
    membership = SeedCommitMembership.from_snapshot(
        json.loads(args.membership.read_text(encoding="utf-8"))
    )
    endpoints = json.loads(args.endpoints.read_text(encoding="utf-8"))
    if set(endpoints) != {"B", "C"}:
        raise ValueError("owner requires exactly the B and C authority endpoints")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    state_payload = canonical_bytes(
        {
            "format": "in-formation.duplicated-mtls-authority-state/0.1",
            "machine_id": membership.system_id,
            "cluster_id": args.cluster_id,
            "state_label": args.state_label,
        }
    )
    state_path = args.out_dir / "state.bin"
    state_path.write_bytes(state_payload)

    manifest = RecoveryStateManifest(
        machine_id=membership.system_id,
        incarnation=membership.incarnation,
        owner_id=membership.owner_id,
        owner_term=membership.owner_term,
        membership_digest=membership.digest,
        generation=1,
        predecessor_digest=membership.genesis_state_digest,
        state_digest=hashlib.sha256(state_payload).hexdigest(),
        capture_cut="after_response_publish",
    )

    owner_journal = args.out_dir / "authorities" / "A.jsonl"
    owner_authority = RecoveryLineageAuthority(
        membership,
        membership.owner_id,
        owner_journal,
    )

    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=str(args.client_ca),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        certfile=str(args.owner_certificate),
        keyfile=str(args.owner_private_key),
    )
    if context.verify_mode is not ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError("owner TLS context must verify server chain and DNS identity")

    wait_for_gate(args.start_gate)
    peers: dict[str, RecoveryLineagePeerClient] = {}
    try:
        for member_id in ("B", "C"):
            endpoint = endpoints[member_id]
            peers[member_id] = RecoveryLineagePeerClient.connect_mutual_tls(
                membership,
                member_id,
                str(endpoint["host"]),
                int(endpoint["port"]),
                context,
                server_hostname=str(endpoint["dns_name"]),
                timeout=4.0,
                handshake_timeout=4.0,
            )

        coordinator = DistributedRecoveryLineageCoordinator(
            membership,
            {membership.owner_id: owner_authority, **peers},
        )
        proof = coordinator.seal(manifest)
        high_water = coordinator.high_water()
        verified = coordinator.verify_state(manifest)
        if high_water != (manifest.generation, manifest.digest):
            raise RuntimeError("distributed owner did not recover the expected quorum high-water")
        if verified.snapshot() != proof.snapshot():
            raise RuntimeError("distributed owner did not verify its exact sealed proof")
        if tuple(sorted(vote.member_id for vote in proof.certificate.votes)) != ("A", "B", "C"):
            raise RuntimeError("expected all three cloned authority identities in the prepare certificate")
        if tuple(sorted(decision.member_id for decision in proof.decisions)) != ("A", "B", "C"):
            raise RuntimeError("expected all three cloned authority identities in durable commit decisions")

        report = {
            "format": "in-formation.duplicated-mtls-authority-owner-result/0.1",
            "cluster_id": args.cluster_id,
            "owner_process_id": os.getpid(),
            "membership": membership.snapshot(),
            "membership_digest": membership.digest,
            "manifest": manifest.snapshot(),
            "manifest_digest": manifest.digest,
            "proof": proof.snapshot(),
            "proof_digest": hashlib.sha256(canonical_bytes(proof.snapshot())).hexdigest(),
            "state_payload": {
                "file_name": "state.bin",
                "size_bytes": len(state_payload),
                "sha256": hashlib.sha256(state_payload).hexdigest(),
            },
            "owner_identity": {
                "member_id": membership.owner_id,
                "expected_peer_dns": args.owner_dns,
                "certificate_der_sha256": certificate_sha256(args.owner_certificate),
                "private_key_file_sha256": hashlib.sha256(args.owner_private_key.read_bytes()).hexdigest(),
            },
            "remote_authorities": [
                {
                    "member_id": member_id,
                    "endpoint": str(endpoints[member_id]["host"]),
                    "port": int(endpoints[member_id]["port"]),
                    "server_dns_name": str(endpoints[member_id]["dns_name"]),
                    "process_id": int(endpoints[member_id]["process_id"]),
                    "certificate_der_sha256": str(endpoints[member_id]["certificate_der_sha256"]),
                }
                for member_id in ("B", "C")
            ],
            "local_high_water": {
                "generation": high_water[0],
                "root_digest": high_water[1],
            },
            "prepare_members": sorted(vote.member_id for vote in proof.certificate.votes),
            "commit_members": sorted(decision.member_id for decision in proof.decisions),
            "distributed_proof_verified": True,
        }
        write_json(args.out_dir / "owner-result.json", report)
        return report
    finally:
        for peer in peers.values():
            peer.close()


def parser() -> argparse.ArgumentParser:
    selected = argparse.ArgumentParser(description=__doc__)
    selected.add_argument("--cluster-id", choices=("left", "right"), required=True)
    selected.add_argument("--state-label", required=True)
    selected.add_argument("--membership", type=Path, required=True)
    selected.add_argument("--endpoints", type=Path, required=True)
    selected.add_argument("--owner-certificate", type=Path, required=True)
    selected.add_argument("--owner-private-key", type=Path, required=True)
    selected.add_argument("--client-ca", type=Path, required=True)
    selected.add_argument("--owner-dns", required=True)
    selected.add_argument("--start-gate", type=Path, required=True)
    selected.add_argument("--out-dir", type=Path, required=True)
    return selected


if __name__ == "__main__":
    run(parser().parse_args())
