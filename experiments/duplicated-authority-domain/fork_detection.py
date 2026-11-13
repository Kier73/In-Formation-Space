"""Detect conflicting quorum heads produced by isolated copies of one membership.

This is an adversarial clone experiment, not a consensus implementation. Each
producer creates three local E-CPU recovery-lineage journals using the same
fixed membership and genesis, then seals a different generation-one state.
A third observer reopens all six journals and verifies both local quorums.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from mailcpu.recovery_lineage import (
    RecoveryLineageAuthority,
    RecoveryLineageCoordinator,
    RecoveryLineageError,
    RecoveryLineageProof,
    RecoveryStateManifest,
)
from mailcpu.seed_commit_quorum import SeedCommitMembership

BUNDLE_FORMAT = "in-formation.duplicated-authority-domain-bundle/0.1"
REPORT_FORMAT = "in-formation.duplicated-authority-domain-observation/0.1"
GENESIS = hashlib.sha256(b"ifs-duplicated-authority-domain-genesis-v1").hexdigest()
MEMBER_IDS = ("authority-a", "authority-b", "authority-c")
SYSTEM_ID = "ifs-fork-detection-machine"
OWNER_ID = "authority-a"
OWNER_TERM = 1


class ForkDetectionError(ValueError):
    """A cluster bundle is malformed, unauthenticated, or fails journal reconstruction."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ForkDetectionError("evidence is outside the canonical JSON value domain") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(dict(value)) + b"\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForkDetectionError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ForkDetectionError(f"JSON evidence {path} must contain an object")
    return value


def configured_membership() -> SeedCommitMembership:
    return SeedCommitMembership(
        SYSTEM_ID,
        1,
        MEMBER_IDS,
        OWNER_ID,
        OWNER_TERM,
        GENESIS,
    )


def producer_identity() -> dict[str, Any]:
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY", "local-test"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local-test"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "run_number": os.environ.get("GITHUB_RUN_NUMBER", "0"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", "local-test"),
        "workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA", "local-test"),
        "git_sha": os.environ.get("GITHUB_SHA", "local-test"),
        "job": os.environ.get("GITHUB_JOB", "local-test"),
        "runner_name": os.environ.get("RUNNER_NAME", "local-test"),
        "runner_environment": os.environ.get("RUNNER_ENVIRONMENT", "local-test"),
    }


def _manifest_for(
    membership: SeedCommitMembership,
    *,
    cluster_id: str,
    state_payload: bytes,
) -> RecoveryStateManifest:
    return RecoveryStateManifest(
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


def produce_cluster(
    out_dir: Path,
    *,
    cluster_id: str,
    state_label: str,
) -> dict[str, Any]:
    """Create one complete, locally valid authority set under the shared fixed membership."""
    if cluster_id not in {"left", "right"}:
        raise ForkDetectionError("cluster_id must be left or right")
    if not isinstance(state_label, str) or not state_label:
        raise ForkDetectionError("state_label must be non-empty text")
    out_dir.mkdir(parents=True, exist_ok=True)
    journal_dir = out_dir / "authorities"
    journal_dir.mkdir(parents=True, exist_ok=True)

    membership = configured_membership()
    state_payload = canonical_bytes(
        {
            "format": "in-formation.duplicated-authority-domain-state/0.1",
            "state_label": state_label,
            "machine_id": membership.system_id,
        }
    )
    (out_dir / "state.bin").write_bytes(state_payload)
    manifest = _manifest_for(
        membership,
        cluster_id=cluster_id,
        state_payload=state_payload,
    )

    authorities = {
        member_id: RecoveryLineageAuthority(
            membership,
            member_id,
            journal_dir / f"{member_id}.jsonl",
        )
        for member_id in membership.member_ids
    }
    coordinator = RecoveryLineageCoordinator(membership, authorities)
    proof = coordinator.seal(manifest)
    if coordinator.high_water() != (manifest.generation, manifest.digest):
        raise ForkDetectionError("producer cluster did not recover its committed high-water")
    if coordinator.verify_state(manifest).snapshot() != proof.snapshot():
        raise ForkDetectionError("producer cluster did not verify its own exact state proof")

    journal_evidence = []
    for member_id in membership.member_ids:
        authority = authorities[member_id]
        journal_path = journal_dir / f"{member_id}.jsonl"
        snapshot = authority.ledger.snapshot()
        if not authority.verify():
            raise ForkDetectionError(f"producer journal {member_id} failed independent replay")
        journal_evidence.append(
            {
                "member_id": member_id,
                "file_name": f"{member_id}.jsonl",
                "size_bytes": journal_path.stat().st_size,
                "sha256": file_digest(journal_path),
                "ledger_snapshot": snapshot,
            }
        )

    core = {
        "format": BUNDLE_FORMAT,
        "cluster_id": cluster_id,
        "membership": membership.snapshot(),
        "membership_digest": membership.digest,
        "manifest": manifest.snapshot(),
        "manifest_digest": manifest.digest,
        "proof": proof.snapshot(),
        "proof_digest": digest(proof.snapshot()),
        "state_payload": {
            "file_name": "state.bin",
            "size_bytes": len(state_payload),
            "sha256": hashlib.sha256(state_payload).hexdigest(),
        },
        "journal_evidence": journal_evidence,
        "producer_identity": producer_identity(),
        "local_verification": {
            "journal_replay_verified": True,
            "local_high_water": {
                "generation": manifest.generation,
                "root_digest": manifest.digest,
            },
            "local_proof_verified": True,
        },
    }
    bundle = {**core, "bundle_digest": digest(core)}
    write_json(out_dir / "bundle.json", bundle)
    return bundle


def _verify_one_cluster(bundle_dir: Path) -> dict[str, Any]:
    bundle = read_json(bundle_dir / "bundle.json")
    if bundle.get("format") != BUNDLE_FORMAT:
        raise ForkDetectionError("cluster bundle format is unsupported")
    if bundle.get("cluster_id") not in {"left", "right"}:
        raise ForkDetectionError("cluster bundle identity is invalid")
    supplied_digest = bundle.get("bundle_digest")
    core = {key: value for key, value in bundle.items() if key != "bundle_digest"}
    if not isinstance(supplied_digest, str) or digest(core) != supplied_digest:
        raise ForkDetectionError("cluster bundle digest mismatch")

    try:
        membership = SeedCommitMembership.from_snapshot(bundle["membership"])
        manifest = RecoveryStateManifest.from_snapshot(bundle["manifest"])
        proof = RecoveryLineageProof.from_snapshot(bundle["proof"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ForkDetectionError(f"cluster protocol documents failed reconstruction: {exc}") from exc

    expected_bundle_fields = {
        "format", "cluster_id", "membership", "membership_digest", "manifest",
        "manifest_digest", "proof", "proof_digest", "state_payload",
        "journal_evidence", "producer_identity", "local_verification",
        "bundle_digest",
    }
    if set(bundle) != expected_bundle_fields:
        raise ForkDetectionError("cluster bundle fields are invalid")
    proposal = proof.proposal
    if (
        membership.digest != bundle.get("membership_digest")
        or manifest.digest != bundle.get("manifest_digest")
        or digest(proof.snapshot()) != bundle.get("proof_digest")
        or proposal.membership_digest != membership.digest
        or proposal.system_id != membership.system_id
        or proposal.incarnation != membership.incarnation
        or proposal.owner_id != membership.owner_id
        or proposal.owner_term != membership.owner_term
        or proposal.slot != manifest.generation
        or proposal.predecessor_state_digest != manifest.predecessor_digest
        or proposal.request_fingerprint != manifest.request_fingerprint
        or proposal.result_state_digest != manifest.digest
        or proof.certificate.membership_digest != membership.digest
        or proof.certificate.proposal_digest != proposal.digest
    ):
        raise ForkDetectionError("cluster bundle membership, manifest, or proof binding mismatch")

    state_meta = bundle.get("state_payload")
    if not isinstance(state_meta, Mapping) or set(state_meta) != {
        "file_name", "size_bytes", "sha256"
    }:
        raise ForkDetectionError("cluster state-payload descriptor is malformed")
    if state_meta["file_name"] != "state.bin":
        raise ForkDetectionError("cluster state-payload file name is invalid")
    state_path = bundle_dir / "state.bin"
    if not state_path.is_file():
        raise ForkDetectionError("cluster state payload is missing")
    state_bytes = state_path.read_bytes()
    if (
        len(state_bytes) != state_meta["size_bytes"]
        or hashlib.sha256(state_bytes).hexdigest() != state_meta["sha256"]
    ):
        raise ForkDetectionError("cluster state payload digest or size mismatch")
    manifest.verify_payload(state_bytes)

    raw_journals = bundle.get("journal_evidence")
    if not isinstance(raw_journals, list) or len(raw_journals) != len(membership.member_ids):
        raise ForkDetectionError("cluster journal evidence set is incomplete")
    by_member = {}
    for row in raw_journals:
        if not isinstance(row, Mapping) or set(row) != {
            "member_id", "file_name", "size_bytes", "sha256", "ledger_snapshot"
        }:
            raise ForkDetectionError("cluster journal evidence row is malformed")
        member_id = row["member_id"]
        if member_id not in membership.member_ids or member_id in by_member:
            raise ForkDetectionError("cluster journal evidence has an unknown or duplicate member")
        if row["file_name"] != f"{member_id}.jsonl":
            raise ForkDetectionError("cluster journal file name is not bound to its member")
        by_member[member_id] = row
    if set(by_member) != set(membership.member_ids):
        raise ForkDetectionError("cluster journal evidence does not cover fixed membership")

    authorities = {}
    journal_reports = []
    for member_id in membership.member_ids:
        row = by_member[member_id]
        journal_path = bundle_dir / "authorities" / f"{member_id}.jsonl"
        if not journal_path.is_file():
            raise ForkDetectionError(f"cluster journal {member_id} is missing")
        actual_size = journal_path.stat().st_size
        actual_hash = file_digest(journal_path)
        if actual_size != row["size_bytes"] or actual_hash != row["sha256"]:
            raise ForkDetectionError(f"cluster journal {member_id} bytes differ from its manifest")
        authority = RecoveryLineageAuthority(membership, member_id, journal_path)
        if not authority.verify():
            raise ForkDetectionError(f"cluster journal {member_id} failed hash-chain replay")
        snapshot = authority.ledger.snapshot()
        if snapshot != row["ledger_snapshot"]:
            raise ForkDetectionError(f"cluster journal {member_id} snapshot differs from its evidence row")
        authorities[member_id] = authority
        journal_reports.append(
            {
                "member_id": member_id,
                "journal_sha256": actual_hash,
                "journal_size_bytes": actual_size,
                "journal_head": snapshot["head_hex"],
                "journal_sequence": snapshot["sequence"],
                "committed_state": snapshot["committed_state"],
                "replay_verified": True,
            }
        )

    coordinator = RecoveryLineageCoordinator(membership, authorities)
    local_proof = coordinator.latest_proof()
    if local_proof is None or local_proof.snapshot() != proof.snapshot():
        raise ForkDetectionError("cluster journals do not reproduce the bundled quorum proof")
    if coordinator.high_water() != (manifest.generation, manifest.digest):
        raise ForkDetectionError("cluster journals do not reproduce the manifest high-water")
    if coordinator.verify_state(manifest).snapshot() != proof.snapshot():
        raise ForkDetectionError("cluster manifest is not the exact locally admitted state")

    return {
        "cluster_id": bundle["cluster_id"],
        "bundle_digest": supplied_digest,
        "membership": membership,
        "manifest": manifest,
        "proof": proof,
        "membership_digest": membership.digest,
        "generation": manifest.generation,
        "predecessor_digest": manifest.predecessor_digest,
        "root_digest": manifest.digest,
        "state_digest": manifest.state_digest,
        "proposal_digest": proof.proposal.digest,
        "prepare_members": sorted(vote.member_id for vote in proof.certificate.votes),
        "commit_members": sorted(decision.member_id for decision in proof.decisions),
        "producer_identity": bundle["producer_identity"],
        "journal_reports": journal_reports,
        "local_quorum_reconstructed": True,
        "cross_manifest_rejected": None,
        "_coordinator": coordinator,
    }


def observe_two_clusters(
    left_dir: Path,
    right_dir: Path,
    *,
    producer_attestations_verified: bool = False,
) -> dict[str, Any]:
    left = _verify_one_cluster(left_dir)
    right = _verify_one_cluster(right_dir)

    shared_configuration = (
        left["membership_digest"] == right["membership_digest"]
        and left["membership"].snapshot() == right["membership"].snapshot()
    )
    same_predecessor = (
        left["generation"] == right["generation"]
        and left["predecessor_digest"] == right["predecessor_digest"]
    )
    divergent_root = (
        shared_configuration
        and same_predecessor
        and left["root_digest"] != right["root_digest"]
    )
    left_rejects_right = False
    right_rejects_left = False
    left_error = None
    right_error = None
    if shared_configuration and same_predecessor and divergent_root:
        try:
            left["_coordinator"].verify_state(right["manifest"])
        except RecoveryLineageError as exc:
            left_error = str(exc)
            left_rejects_right = "conflicts with committed high-water generation" in left_error
        try:
            right["_coordinator"].verify_state(left["manifest"])
        except RecoveryLineageError as exc:
            right_error = str(exc)
            right_rejects_left = "conflicts with committed high-water generation" in right_error

    left_job = left["producer_identity"].get("job")
    right_job = right["producer_identity"].get("job")
    workflow_run_match = (
        left["producer_identity"].get("repository") == right["producer_identity"].get("repository")
        and left["producer_identity"].get("run_id") == right["producer_identity"].get("run_id")
        and left["producer_identity"].get("run_id") != "local-test"
    )
    distinct_jobs = (
        isinstance(left_job, str)
        and isinstance(right_job, str)
        and left_job != right_job
        and left_job in {"authority_cluster_left", "authority_cluster_right"}
        and right_job in {"authority_cluster_left", "authority_cluster_right"}
    )
    if shared_configuration and same_predecessor and divergent_root:
        classification = "cloned_membership_split_brain"
        adjudication = "refuse_automatic_winner"
    elif shared_configuration and same_predecessor and not divergent_root:
        classification = "matching_duplicate_authority_views"
        adjudication = "no_fork_observed"
    else:
        classification = "incomparable_authority_views"
        adjudication = "refuse_automatic_winner"

    return {
        "format": REPORT_FORMAT,
        "classification": classification,
        "adjudication": adjudication,
        "membership_digest": left["membership_digest"] if shared_configuration else None,
        "shared_fixed_membership": shared_configuration,
        "same_generation_and_predecessor": same_predecessor,
        "generation": left["generation"] if same_predecessor else None,
        "predecessor_digest": left["predecessor_digest"] if same_predecessor else None,
        "conflicting_roots": divergent_root,
        "left_rejects_right_manifest": left_rejects_right,
        "right_rejects_left_manifest": right_rejects_left,
        "each_cluster_reconstructed_its_own_quorum": (
            left["local_quorum_reconstructed"] and right["local_quorum_reconstructed"]
        ),
        "producer_attestations_verified_by_github": producer_attestations_verified,
        "producer_jobs_distinct": distinct_jobs,
        "same_github_workflow_run": workflow_run_match,
        "physical_fault_domain_separation_established": False,
        "winner": None if classification != "matching_duplicate_authority_views" else "not_applicable",
        "clusters": [
            {
                "cluster_id": left["cluster_id"],
                "bundle_digest": left["bundle_digest"],
                "root_digest": left["root_digest"],
                "state_digest": left["state_digest"],
                "proposal_digest": left["proposal_digest"],
                "prepare_members": left["prepare_members"],
                "commit_members": left["commit_members"],
                "producer_identity": left["producer_identity"],
                "journal_reports": left["journal_reports"],
                "local_quorum_reconstructed": left["local_quorum_reconstructed"],
            },
            {
                "cluster_id": right["cluster_id"],
                "bundle_digest": right["bundle_digest"],
                "root_digest": right["root_digest"],
                "state_digest": right["state_digest"],
                "proposal_digest": right["proposal_digest"],
                "prepare_members": right["prepare_members"],
                "commit_members": right["commit_members"],
                "producer_identity": right["producer_identity"],
                "journal_reports": right["journal_reports"],
                "local_quorum_reconstructed": right["local_quorum_reconstructed"],
            },
        ],
        "not_established": [
            "which cluster is the legitimate continuation; both were locally valid under the duplicated membership and genesis",
            "that the six journals are held on six physical machines; each producer job creates its three-member cluster on one runner",
            "physical server, region, storage-controller, or administrative fault-domain separation between GitHub-hosted jobs",
            "Byzantine consensus or security against an attacker that can clone all member identities and journal state",
            "membership reconfiguration, owner election, or an external monotonic trust anchor",
            "production E-CPU ReliableChannel or mutual-TLS transport between authority members; this experiment uses the local fixed-membership coordinator",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    produce = sub.add_parser("produce")
    produce.add_argument("--cluster-id", required=True, choices=("left", "right"))
    produce.add_argument("--state-label", required=True)
    produce.add_argument("--out-dir", type=Path, required=True)
    observe = sub.add_parser("observe")
    observe.add_argument("--left-dir", type=Path, required=True)
    observe.add_argument("--right-dir", type=Path, required=True)
    observe.add_argument("--output", type=Path, required=True)
    observe.add_argument("--producer-attestations-verified", action="store_true")
    args = parser.parse_args()
    if args.command == "produce":
        produce_cluster(args.out_dir, cluster_id=args.cluster_id, state_label=args.state_label)
    else:
        report = observe_two_clusters(
            args.left_dir,
            args.right_dir,
            producer_attestations_verified=args.producer_attestations_verified,
        )
        write_json(args.output, report)


if __name__ == "__main__":
    main()
