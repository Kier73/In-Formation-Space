from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from mailcpu.transferable_execution_claim import ExecutionClaimStatus

from stateful_recovery_handoff import resume_on_recovery_host
from stateful_recovery_worker import (
    _canonical,
    _digest,
    _store_independent_verification,
    _verify_prepared_with_node,
    _write_prepared,
)
from test_stateful_recovery_handoff import IMPL_B, _reassign_to_b, _source_envelope, _store


def _prepare(path: Path, envelope, output: bytes, receipt_core, receipt_digest: str) -> None:
    _write_prepared(
        path,
        sequence=1,
        envelope=envelope,
        output_checkpoint=output,
        receipt_core=receipt_core,
        receipt_sha256=receipt_digest,
        owner_peer_id="peer-b",
        owner_host_id="logical-host-b",
        implementation_fingerprint=IMPL_B,
    )


def test_independent_node_receiver_receipt_is_bound_into_quorum_completion(tmp_path: Path) -> None:
    store, coordinator = _store(tmp_path)
    envelope = _reassign_to_b(store, _source_envelope(store))
    prepared_path = tmp_path / "prepared" / f"{envelope.claim_id}.prepared.json"
    selected: dict[str, object] = {}

    def validate_before_commit(output_checkpoint: bytes, receipt_core, receipt_digest: str) -> str:
        _prepare(prepared_path, envelope, output_checkpoint, receipt_core, receipt_digest)
        report = _verify_prepared_with_node(envelope=envelope, prepared_path=prepared_path)
        _store_independent_verification(prepared_path, report["verification"])
        selected.update(report)
        return report["verification_digest"]

    result = resume_on_recovery_host(
        store,
        envelope,
        owner_peer_id="peer-b",
        owner_host_id="logical-host-b",
        implementation_fingerprint=IMPL_B,
        next_resume_controls={"advance": 0, "reset": 0},
        before_claim_complete=validate_before_commit,
    )

    record = json.loads(prepared_path.read_text(encoding="utf-8"))
    assert selected["valid"] is True
    assert selected["verification_digest"] == result.receipt["independent_verification_digest"]
    assert record["independent_verification"] == selected["verification"]
    assert result.completed_ticket.claim.status is ExecutionClaimStatus.COMPLETED
    assert result.completed_ticket.claim.child_receipt_digest == result.receipt_sha256
    assert result.receipt["state_before"] == [1, 0]
    assert result.receipt["state_after"] == [1, 1]
    assert result.receipt["tick_before"] == 3
    assert result.receipt["tick_after"] == 4
    result.completed_ticket.verify_current(coordinator)


def test_independent_receiver_rejects_tampered_prepared_checkpoint_before_quorum_commit(
    tmp_path: Path,
) -> None:
    store, _coordinator = _store(tmp_path)
    envelope = _reassign_to_b(store, _source_envelope(store))
    prepared_path = tmp_path / "prepared" / f"{envelope.claim_id}.prepared.json"

    def reject_before_commit(output_checkpoint: bytes, receipt_core, receipt_digest: str) -> str:
        _prepare(prepared_path, envelope, output_checkpoint, receipt_core, receipt_digest)
        record = json.loads(prepared_path.read_text(encoding="utf-8"))
        forged = bytearray(base64.b64decode(record["output_checkpoint_base64"], validate=True))
        forged[-1] ^= 1
        record["output_checkpoint_base64"] = base64.b64encode(forged).decode("ascii")
        record["output_checkpoint_sha256"] = hashlib.sha256(forged).hexdigest()
        record_core = {key: value for key, value in record.items() if key != "prepared_sha256"}
        record["prepared_sha256"] = _digest(record_core)
        prepared_path.write_bytes(_canonical(record) + b"\n")
        report = _verify_prepared_with_node(envelope=envelope, prepared_path=prepared_path)
        return report["verification_digest"]

    with pytest.raises(RuntimeError, match="independent Node prepared-result verifier rejected"):
        resume_on_recovery_host(
            store,
            envelope,
            owner_peer_id="peer-b",
            owner_host_id="logical-host-b",
            implementation_fingerprint=IMPL_B,
            next_resume_controls={"advance": 0, "reset": 0},
            before_claim_complete=reject_before_commit,
        )

    current = store.get(envelope.claim_id)
    assert current.claim.status is ExecutionClaimStatus.ASSIGNED
    assert current.claim.result_digest is None
    assert current.claim.child_receipt_digest is None
