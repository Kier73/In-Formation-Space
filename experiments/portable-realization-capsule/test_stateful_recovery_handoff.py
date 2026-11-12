from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from mailcpu.recovery_lineage import RecoveryLineageAuthority, RecoveryLineageCoordinator
from mailcpu.seed_commit_quorum import SeedCommitMembership
from mailcpu.transferable_execution_claim import (
    ExecutionClaimStatus,
    TransferableExecutionClaimError,
    TransferableExecutionClaimStore,
)

from stateful_recovery_handoff import (
    SCHEMA,
    StatefulRuntimeRehomeError,
    StatefulRuntimeRecoveryEnvelope,
    issue_stateful_recovery_envelope,
    reassign_after_source_loss,
    resume_on_recovery_host,
)


GENESIS = "0" * 64
IMPL_SOURCE = hashlib.sha256(b"source-implementation").hexdigest()
IMPL_B = hashlib.sha256(b"recovery-host-b-implementation").hexdigest()
IMPL_C = hashlib.sha256(b"recovery-host-c-implementation").hexdigest()
FAILURE_SOURCE = hashlib.sha256(b"source-host-lost").hexdigest()
FAILURE_B = hashlib.sha256(b"recovery-host-b-lost-before-resume").hexdigest()


def _store(root: Path):
    membership = SeedCommitMembership(
        "ifs-stateful-runtime-recovery",
        1,
        ("authority-a", "authority-b", "authority-c"),
        "authority-a",
        1,
        GENESIS,
    )
    authorities = {
        member: RecoveryLineageAuthority(membership, member, root / "authorities" / f"{member}.log")
        for member in membership.member_ids
    }
    coordinator = RecoveryLineageCoordinator(membership, authorities)
    store = TransferableExecutionClaimStore(root / "claims", coordinator)
    return store, coordinator


def _checkpoint_fixture():
    """Reuse the exact PSC-001 counter and PRC capsule construction, not a second model fixture."""
    path = Path(__file__).with_name("test_portable_stateful_checkpoint.py")
    spec = importlib.util.spec_from_file_location("psc001_shared_test_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_runtime_and_capsules()


def _source_envelope(store):
    runtime, capsules = _checkpoint_fixture()
    envelope = issue_stateful_recovery_envelope(
        store,
        session_id="two-bit-counter-session",
        runtime=runtime,
        realization_capsules=capsules,
        resume_controls={"advance": 1, "reset": 0},
        owner_peer_id="peer-source",
        owner_host_id="logical-host-source",
        implementation_fingerprint=IMPL_SOURCE,
    )
    return envelope


def _reassign_to_b(store, envelope):
    return reassign_after_source_loss(
        store,
        envelope,
        target_peer_id="peer-b",
        target_host_id="logical-host-b",
        target_implementation_fingerprint=IMPL_B,
        failure_evidence_digest=FAILURE_SOURCE,
    )


def test_psc_checkpoint_rehomes_to_new_quorum_owner_and_continues_once(tmp_path: Path) -> None:
    store, coordinator = _store(tmp_path)
    source = _source_envelope(store)

    # The wire envelope survives a JSON-only hop before the source is lost.
    wire = json.loads(json.dumps(source.to_dict()))
    source = StatefulRuntimeRecoveryEnvelope.from_dict(wire)
    assert source.to_dict()["schema"] == SCHEMA

    moved = _reassign_to_b(store, source)
    assert moved.ticket.claim.current_assignment.epoch == 2
    assert moved.ticket.claim.current_assignment.owner_host_id == "logical-host-b"

    # The source's old proof and old epoch cannot publish an accepted state.
    with pytest.raises(TransferableExecutionClaimError, match="not current"):
        source.ticket.verify_current(coordinator)
    with pytest.raises(TransferableExecutionClaimError, match="exact current assignment"):
        store.complete(
            source.claim_id,
            expected_epoch=1,
            owner_peer_id="peer-source",
            owner_host_id="logical-host-source",
            implementation_fingerprint=IMPL_SOURCE,
            result_digest=hashlib.sha256(b"stale-source-output").hexdigest(),
            child_receipt_digest=hashlib.sha256(b"stale-source-receipt").hexdigest(),
        )

    # A different host or implementation cannot consume the new ownership ticket.
    with pytest.raises(TransferableExecutionClaimError, match="exact target workload"):
        moved.ticket.verify_for_target(
            coordinator,
            parent_request_digest=moved.ticket.claim.parent_request_digest,
            child_request_digest=moved.ticket.claim.child_request_digest,
            address_digest=moved.ticket.claim.address_digest,
            operator_spec=moved.ticket.claim.operator_spec,
            computational_ground_fingerprint=moved.ticket.claim.computational_ground_fingerprint,
            owner_peer_id="peer-b",
            owner_host_id="logical-host-b",
            implementation_fingerprint=IMPL_SOURCE,
        )

    result = resume_on_recovery_host(
        store,
        moved,
        owner_peer_id="peer-b",
        owner_host_id="logical-host-b",
        implementation_fingerprint=IMPL_B,
        next_resume_controls={"advance": 0, "reset": 0},
    )

    assert result.completed_ticket.claim.status is ExecutionClaimStatus.COMPLETED
    assert result.completed_ticket.claim.result_digest == result.next_envelope.checkpoint_sha256
    assert result.completed_ticket.claim.child_receipt_digest == result.receipt_sha256
    assert result.receipt["tick_before"] == 3
    assert result.receipt["tick_after"] == 4
    assert result.receipt["state_before"] == [1, 0]
    assert result.receipt["state_after"] == [1, 1]
    assert result.receipt["output_checkpoint_sha256"] == result.next_envelope.checkpoint_sha256
    result.completed_ticket.verify_current(coordinator)

    # The successor checkpoint is itself a new, current claim on the recovery host.
    successor = result.next_envelope
    assert successor.ticket.claim.status is ExecutionClaimStatus.ASSIGNED
    assert successor.ticket.claim.current_assignment.owner_host_id == "logical-host-b"
    assert successor.ticket.claim.current_assignment.state_generation > (
        moved.ticket.claim.current_assignment.state_generation
    )
    successor.ticket.verify_for_target(
        coordinator,
        parent_request_digest=successor.ticket.claim.parent_request_digest,
        child_request_digest=successor.ticket.claim.child_request_digest,
        address_digest=successor.ticket.claim.address_digest,
        operator_spec=successor.ticket.claim.operator_spec,
        computational_ground_fingerprint=successor.ticket.claim.computational_ground_fingerprint,
        owner_peer_id="peer-b",
        owner_host_id="logical-host-b",
        implementation_fingerprint=IMPL_B,
    )

    # Lost completion acknowledgements are safe to retry with the exact same receipt.
    retried = store.complete(
        moved.claim_id,
        expected_epoch=2,
        owner_peer_id="peer-b",
        owner_host_id="logical-host-b",
        implementation_fingerprint=IMPL_B,
        result_digest=successor.ticket.claim.child_request_digest,
        child_receipt_digest=result.receipt_sha256,
    )
    assert retried.claim.status is ExecutionClaimStatus.COMPLETED
    assert retried.claim.result_digest == result.completed_ticket.claim.result_digest


def test_recovery_owner_can_fail_before_resume_and_be_rehomed_again(tmp_path: Path) -> None:
    store, coordinator = _store(tmp_path)
    source = _source_envelope(store)
    host_b = _reassign_to_b(store, source)

    # Simulate a crash after quorum reassignment but before the new host runs.
    # A second recovery assignment advances the same claim's owner epoch.
    host_c = reassign_after_source_loss(
        store,
        host_b,
        target_peer_id="peer-c",
        target_host_id="logical-host-c",
        target_implementation_fingerprint=IMPL_C,
        failure_evidence_digest=FAILURE_B,
    )
    assert host_c.ticket.claim.current_assignment.epoch == 3
    assert host_c.ticket.claim.current_assignment.owner_host_id == "logical-host-c"

    with pytest.raises(TransferableExecutionClaimError, match="not current"):
        host_b.ticket.verify_current(coordinator)
    with pytest.raises(StatefulRuntimeRehomeError, match="could not admit or resume"):
        resume_on_recovery_host(
            store,
            host_b,
            owner_peer_id="peer-b",
            owner_host_id="logical-host-b",
            implementation_fingerprint=IMPL_B,
            next_resume_controls={"advance": 0, "reset": 0},
        )

    resumed = resume_on_recovery_host(
        store,
        host_c,
        owner_peer_id="peer-c",
        owner_host_id="logical-host-c",
        implementation_fingerprint=IMPL_C,
        next_resume_controls={"advance": 0, "reset": 0},
    )
    assert resumed.receipt["tick_after"] == 4
    assert resumed.next_envelope.ticket.claim.current_assignment.owner_host_id == "logical-host-c"


def test_reassignment_retry_is_idempotent_and_forged_envelopes_are_rejected(tmp_path: Path) -> None:
    store, _coordinator = _store(tmp_path)
    source = _source_envelope(store)
    moved = _reassign_to_b(store, source)

    # Exact retry after an acknowledgement loss returns the already-committed assignment.
    retried = _reassign_to_b(store, source)
    assert retried.ticket.digest == moved.ticket.digest

    payload = moved.to_dict()
    forged_checkpoint = dict(payload)
    encoded = forged_checkpoint["checkpoint_base64"]
    forged_checkpoint["checkpoint_base64"] = ("A" if encoded[0] != "A" else "B") + encoded[1:]
    with pytest.raises(StatefulRuntimeRehomeError, match="checkpoint digest|envelope SHA"):
        StatefulRuntimeRecoveryEnvelope.from_dict(forged_checkpoint)

    forged_ticket = moved.to_dict()
    forged_ticket["ticket"]["claim"]["assignments"][-1]["owner_host_id"] = "impostor-host"
    forged_core = {
        key: value for key, value in forged_ticket.items()
        if key != "envelope_sha256"
    }
    forged_ticket["envelope_sha256"] = hashlib.sha256(
        json.dumps(
            forged_core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(StatefulRuntimeRehomeError, match="portable claim ticket is invalid"):
        StatefulRuntimeRecoveryEnvelope.from_dict(forged_ticket)

    with pytest.raises(StatefulRuntimeRehomeError, match="Base64|checkpoint"):
        StatefulRuntimeRecoveryEnvelope.from_dict({
            **payload,
            "checkpoint_base64": "not-base64!",
        })


def test_wrong_target_and_conflicting_completion_are_rejected(tmp_path: Path) -> None:
    store, coordinator = _store(tmp_path)
    moved = _reassign_to_b(store, _source_envelope(store))

    with pytest.raises(TransferableExecutionClaimError, match="exact target workload"):
        moved.ticket.verify_for_target(
            coordinator,
            parent_request_digest=moved.ticket.claim.parent_request_digest,
            child_request_digest=moved.ticket.claim.child_request_digest,
            address_digest=moved.ticket.claim.address_digest,
            operator_spec=moved.ticket.claim.operator_spec,
            computational_ground_fingerprint=moved.ticket.claim.computational_ground_fingerprint,
            owner_peer_id="peer-b",
            owner_host_id="different-host",
            implementation_fingerprint=IMPL_B,
        )

    result = resume_on_recovery_host(
        store,
        moved,
        owner_peer_id="peer-b",
        owner_host_id="logical-host-b",
        implementation_fingerprint=IMPL_B,
        next_resume_controls={"advance": 0, "reset": 0},
    )
    with pytest.raises(TransferableExecutionClaimError, match="conflicting result|conflicting"):
        store.complete(
            moved.claim_id,
            expected_epoch=2,
            owner_peer_id="peer-b",
            owner_host_id="logical-host-b",
            implementation_fingerprint=IMPL_B,
            result_digest=hashlib.sha256(b"different-checkpoint").hexdigest(),
            child_receipt_digest=result.receipt_sha256,
        )
