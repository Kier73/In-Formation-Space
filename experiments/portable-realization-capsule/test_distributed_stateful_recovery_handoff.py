from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from mailcpu import (
    DistributedRecoveryLineageCoordinator,
    RecoveryLineageAuthority,
    RecoveryLineagePeerClient,
    SeedCommitMembership,
    TransferableExecutionClaimStore,
)

from stateful_recovery_handoff import (
    issue_stateful_recovery_envelope,
    reassign_after_source_loss,
    resume_on_recovery_host,
)


GENESIS = hashlib.sha256(b"ifs-srh-002-distributed-authority-genesis").hexdigest()
SOURCE_IMPL = hashlib.sha256(b"source-worker-implementation").hexdigest()
RECOVERY_IMPL = hashlib.sha256(b"recovery-worker-implementation").hexdigest()
SOURCE_FAILURE = hashlib.sha256(b"source-host-unavailable-evidence").hexdigest()


def _membership() -> SeedCommitMembership:
    return SeedCommitMembership(
        "ifs-stateful-runtime-recovery-distributed",
        1,
        ("authority-a", "authority-b", "authority-c"),
        "authority-a",
        1,
        GENESIS,
    )


def _start_remote_authority(
    root: Path,
    membership: SeedCommitMembership,
    member_id: str,
) -> tuple[subprocess.Popen[str], RecoveryLineagePeerClient]:
    """Start one separate authority interpreter with a durable, member-local journal."""
    root.mkdir(parents=True, exist_ok=True)
    membership_path = root / "membership.json"
    membership_path.write_text(
        json.dumps(membership.snapshot(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    repository_root = Path(__file__).resolve().parents[2]
    ecpu_root = repository_root / "external" / "E-CPU"
    worker = ecpu_root / "tests" / "helpers" / "recovery_lineage_authority_worker.py"
    journal = root / f"{member_id}.jsonl"
    marker = root / f"{member_id}.marker"
    process = subprocess.Popen(
        [
            sys.executable,
            str(worker),
            member_id,
            str(membership_path),
            str(journal),
            "-",
            str(marker),
        ],
        cwd=ecpu_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    ready_line = process.stdout.readline()
    if not ready_line:
        stdout, stderr = process.communicate(timeout=5)
        raise AssertionError(
            f"authority {member_id} did not start: rc={process.returncode}, "
            f"stdout={stdout!r}, stderr={stderr!r}"
        )
    ready = json.loads(ready_line)
    assert ready["member_id"] == member_id
    assert ready["pid"] == process.pid
    peer = RecoveryLineagePeerClient.connect(
        membership,
        member_id,
        "127.0.0.1",
        int(ready["port"]),
        timeout=2.0,
    )
    return process, peer


def _stop_remote_authority(
    process: subprocess.Popen[str] | None,
    peer: RecoveryLineagePeerClient | None,
) -> None:
    if peer is not None:
        peer.close()
    if process is not None:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def _psc_fixture():
    """Reuse the existing PSC-001 state/time/model-revision fixture."""
    fixture_path = Path(__file__).with_name("test_portable_stateful_checkpoint.py")
    spec = importlib.util.spec_from_file_location("psc001_distributed_authority_fixture", fixture_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_runtime_and_capsules()


def _issue(store: TransferableExecutionClaimStore):
    runtime, capsules = _psc_fixture()
    return issue_stateful_recovery_envelope(
        store,
        session_id="distributed-counter-session",
        runtime=runtime,
        realization_capsules=capsules,
        resume_controls={"advance": 1, "reset": 0},
        owner_peer_id="peer-source",
        owner_host_id="logical-host-source",
        implementation_fingerprint=SOURCE_IMPL,
    )


def _distributed_store(root: Path, membership: SeedCommitMembership, peer_b, peer_c):
    owner = RecoveryLineageAuthority(
        membership,
        membership.owner_id,
        root / "authority-a.jsonl",
    )
    coordinator = DistributedRecoveryLineageCoordinator(
        membership,
        {
            membership.owner_id: owner,
            "authority-b": peer_b,
            "authority-c": peer_c,
        },
    )
    store = TransferableExecutionClaimStore(root / "claims", coordinator)
    return store, coordinator


def test_psc_rehome_uses_remote_quorum_authorities_and_recovers_their_journals(tmp_path: Path) -> None:
    """A PSC continuation remains admitted after remote authority processes are restarted."""
    membership = _membership()
    authority_root = tmp_path / "remote-authorities"
    process_b: subprocess.Popen[str] | None = None
    process_c: subprocess.Popen[str] | None = None
    peer_b: RecoveryLineagePeerClient | None = None
    peer_c: RecoveryLineagePeerClient | None = None
    coordinator: DistributedRecoveryLineageCoordinator | None = None

    try:
        process_b, peer_b = _start_remote_authority(authority_root, membership, "authority-b")
        process_c, peer_c = _start_remote_authority(authority_root, membership, "authority-c")
        store, coordinator = _distributed_store(authority_root, membership, peer_b, peer_c)

        source = _issue(store)
        assert coordinator.high_water()[0] == 1

        moved = reassign_after_source_loss(
            store,
            source,
            target_peer_id="peer-recovery",
            target_host_id="logical-host-recovery",
            target_implementation_fingerprint=RECOVERY_IMPL,
            failure_evidence_digest=SOURCE_FAILURE,
        )
        assert moved.ticket.claim.current_assignment.epoch == 2
        assert coordinator.high_water()[0] == 2

        resumed = resume_on_recovery_host(
            store,
            moved,
            owner_peer_id="peer-recovery",
            owner_host_id="logical-host-recovery",
            implementation_fingerprint=RECOVERY_IMPL,
            next_resume_controls={"advance": 0, "reset": 0},
        )
        assert resumed.receipt["state_before"] == [1, 0]
        assert resumed.receipt["state_after"] == [1, 1]
        assert resumed.receipt["tick_before"] == 3
        assert resumed.receipt["tick_after"] == 4
        assert resumed.completed_ticket.claim.result_digest == resumed.next_envelope.checkpoint_sha256
        assert coordinator.high_water()[0] == 4

        coordinator_high_water = coordinator.high_water()
        # Stop the owner-side remote streams and hard-kill both authority
        # processes. Their durable member journals remain the only source of
        # remote decision state after this point.
        coordinator.close()
        coordinator = None
        _stop_remote_authority(process_b, None)
        _stop_remote_authority(process_c, None)
        process_b = process_c = None
        peer_b = peer_c = None

        # Reopen each authority as a fresh interpreter under the same member
        # identity and journal path, then construct a fresh distributed owner.
        process_b, peer_b = _start_remote_authority(authority_root, membership, "authority-b")
        process_c, peer_c = _start_remote_authority(authority_root, membership, "authority-c")
        restored_store, restored_coordinator = _distributed_store(
            authority_root,
            membership,
            peer_b,
            peer_c,
        )
        assert restored_coordinator.high_water() == coordinator_high_water
        restored_completed = restored_store.get(source.claim_id)
        assert restored_completed.claim.status.value == "completed"
        assert restored_completed.claim.result_digest == resumed.next_envelope.checkpoint_sha256
        restored_completed.verify_current(restored_coordinator)

        restored_successor = restored_store.get(resumed.next_envelope.claim_id)
        restored_successor.verify_for_target(
            restored_coordinator,
            parent_request_digest=restored_successor.claim.parent_request_digest,
            child_request_digest=restored_successor.claim.child_request_digest,
            address_digest=restored_successor.claim.address_digest,
            operator_spec=restored_successor.claim.operator_spec,
            computational_ground_fingerprint=restored_successor.claim.computational_ground_fingerprint,
            owner_peer_id="peer-recovery",
            owner_host_id="logical-host-recovery",
            implementation_fingerprint=RECOVERY_IMPL,
        )
        restored_coordinator.close()
    finally:
        if coordinator is not None:
            coordinator.close()
            peer_b = peer_c = None
        _stop_remote_authority(process_b, peer_b)
        _stop_remote_authority(process_c, peer_c)
