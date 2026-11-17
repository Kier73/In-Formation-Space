"""CGS-009: reuse E-CPU's real quorum recovery for CGS-008 signed Ground state.

This is deliberately an adapter, not a new quorum, consensus, or checkpoint
algorithm. E-CPU RecoveryStateManifest / RecoveryLineageCoordinator remain
the ONLY high-water authority. The CGS-008 Python Ed25519 verifier remains
the cryptographic source of policy and receiver-checkpoint truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from mailcpu import (
    RecoveryLineageAuthority,
    RecoveryLineageCoordinator,
    RecoveryLineageError,
    RecoveryStateManifest,
    SeedCommitMembership,
)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_authority as cgs8  # noqa: E402

SCHEMA = "ifs.cgs009-ecpu-anchored-receiver-state/0.1"
STAGES = {
    1: "checkpoint_after1",
    2: "checkpoint_after2",
}


def require(predicate: bool, reason: str) -> None:
    if not predicate:
        raise ValueError("CGS-009 refused: " + reason)


def canonical(doc: Any) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_bundle(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    cgs8.verify_bundle(data)  # all Ed25519 root, policy, receiver and observer evidence
    return data


def membership_for(trust: dict) -> SeedCommitMembership:
    """Pin immutable E-CPU machine identity to the signed bootstrap's hash."""
    trust_hash = cgs8.digest(trust)
    return SeedCommitMembership(
        system_id="cgs009-" + trust_hash[:32],
        incarnation=1,
        member_ids=("anchor-A", "anchor-B", "anchor-C"),
        owner_id="anchor-A",
        owner_term=1,
        genesis_state_digest=sha(("IFS-CGS009-GENESIS:" + trust_hash).encode()),
    )


def open_lineage(workspace: Path, membership: SeedCommitMembership,
                 members: tuple[str, ...] = ("anchor-A", "anchor-B", "anchor-C")
                 ) -> RecoveryLineageCoordinator:
    """Reopen each existing E-CPU durable journal; no journal reinitialization."""
    require(len(set(members)) == len(members) and
            all(m in membership.member_ids for m in members),
            "unknown or duplicate authority journal")
    journals = workspace / "authority-journals"
    journals.mkdir(parents=True, exist_ok=True)
    authorities = {
        member: RecoveryLineageAuthority(
            membership, member, journals / (member + ".jsonl")
        ) for member in members
    }
    return RecoveryLineageCoordinator(membership, authorities)


def state_document(bundle: dict, generation: int) -> dict:
    """One exact CGS-008 signed checkpoint and its prefix policy lineage."""
    require(generation in STAGES, "only the two original signed generations exist")
    trust = bundle["trust"]
    checkpoint = bundle[STAGES[generation]]
    root_digests = cgs8.ledger(trust, bundle["policies"][:generation])
    cgs8.checkpoint(trust, checkpoint)
    b = checkpoint["body"]
    require(b["policy_version"] == generation and
            b["policy_digest"] == root_digests[-1] and
            b["counter"] == generation and
            b["ground"] == trust["ground"] and b["realm"] == trust["realm"],
            "checkpoint does not bind the expected policy generation")
    expected_receipt = cgs8.digest({
        "request": bundle["request"+str(generation)]["body"],
        "signatures": [
            {"body": obs["body"], "signatures": obs["signatures"]}
            for obs in bundle["receipts"+str(generation)]
        ],
    })
    require(b["last_receipt"] == expected_receipt,
            "receiver checkpoint did not commit signed receipts")
    return {
        "schema": SCHEMA,
        "generation": generation,
        "realm": trust["realm"],
        "ground": trust["ground"],
        "policy_digest": b["policy_digest"],
        "checkpoint": checkpoint,
        "policies": bundle["policies"][:generation],
        "source_bundle_digest": sha(canonical(bundle)),
        "capture_cut": STAGES[generation],
        "current_execution_authorized": False,
    }


def atomic_create(path: Path, raw: bytes) -> None:
    """Persist a candidate artifact before quorum sealing; no replacing rivals."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw,
                "different state bytes already occupy this generation")
        return
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # The experiment assumes one active owner; do not overwrite rivals.
        if path.exists():
            require(path.read_bytes() == raw,
                    "concurrent conflicting candidate")
        else:
            os.replace(tmp, path)
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        tmp.unlink(missing_ok=True)


def manifest_for(membership: SeedCommitMembership, generation: int,
                 predecessor: str, raw: bytes) -> RecoveryStateManifest:
    return RecoveryStateManifest(
        machine_id=membership.system_id,
        incarnation=membership.incarnation,
        owner_id=membership.owner_id,
        owner_term=membership.owner_term,
        membership_digest=membership.digest,
        generation=generation,
        predecessor_digest=predecessor,
        state_digest=sha(raw),
        capture_cut="cgs008:" + STAGES[generation],
    )


def seal(workspace: Path, bundle: dict, generation: int,
         members: tuple[str, ...] = ("anchor-A", "anchor-B", "anchor-C")) -> dict:
    """Do not issue proof until E-CPU quorum persists its commit decisions."""
    m = membership_for(bundle["trust"])
    lineage = open_lineage(workspace, m, members)
    previous_generation, previous_root = lineage.high_water()
    require(generation == previous_generation + 1,
            "generation must follow the quorum-supported high-water")
    raw = canonical(state_document(bundle, generation))
    manifest = manifest_for(m, generation, previous_root, raw)
    atomic_create(workspace / ("state-" + str(generation) + ".json"), raw)
    atomic_create(workspace / ("manifest-" + str(generation) + ".json"),
                  canonical(manifest.snapshot()))
    proof = lineage.seal(manifest)
    require(lineage.verify_state(manifest).proposal.digest == proof.proposal.digest,
            "sealed state is not the read-quorum high-water")
    return {"stage": "quorum-sealed", "generation": generation,
            "manifest_digest": manifest.digest,
            "state_digest": manifest.state_digest,
            "decision_members": sorted(d.member_id for d in proof.decisions),
            "state_policy_version": generation,
            "current_execution_authorized": False}


def recover(workspace: Path, bundle: dict, generation: int,
            members: tuple[str, ...] = ("anchor-A", "anchor-B", "anchor-C")) -> dict:
    """Reject stale/forged state before reconstructing any receiver action."""
    require(generation in STAGES, "unknown recovery generation")
    m = membership_for(bundle["trust"])
    lineage = open_lineage(workspace, m, members)
    raw = (workspace / ("state-" + str(generation) + ".json")).read_bytes()
    manifest_raw = (workspace / ("manifest-" + str(generation) + ".json")).read_bytes()
    manifest = RecoveryStateManifest.from_snapshot(json.loads(manifest_raw))
    manifest.verify_payload(raw)
    require(manifest.generation == generation and
            manifest.capture_cut == "cgs008:" + STAGES[generation],
            "manifest is not for requested state")
    # Exact latest E-CPU quorum verification BEFORE semantic interpretation.
    proof = lineage.verify_state(manifest)
    content = json.loads(raw)
    require(raw == canonical(content), "state bytes are not canonical")
    require(content == state_document(bundle, generation),
            "state conflicts with independently verified CGS-008 signature chain")
    require(content["current_execution_authorized"] is False,
            "archived state cannot authorize an effect")
    return {"stage": "recovered-against-live-quorum",
            "generation": proof.proposal.slot,
            "manifest_digest": manifest.digest,
            "state_digest": manifest.state_digest,
            "recovered_checkpoint_counter": content["checkpoint"]["body"]["counter"],
            "recovered_policy_version": content["checkpoint"]["body"]["policy_version"],
            "receipt_digest": content["checkpoint"]["body"]["last_receipt"],
            "current_execution_authorized": False,
            "requires_new_challenge": True}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("seal", "recover", "high-water"))
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--generation", type=int, default=0)
    p.add_argument("--members", nargs="+",
                   default=["anchor-A", "anchor-B", "anchor-C"])
    a = p.parse_args()
    bundle = load_bundle(a.bundle)
    members = tuple(a.members)
    if a.command == "seal":
        result = seal(a.workspace, bundle, a.generation, members)
    elif a.command == "recover":
        result = recover(a.workspace, bundle, a.generation, members)
    else:
        m = membership_for(bundle["trust"])
        gen, root = open_lineage(a.workspace, m, members).high_water()
        result = {"generation": gen, "root": root,
                  "scope": "E-CPU fixed-membership majority-committed state"}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
