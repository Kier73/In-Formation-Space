from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from mailcpu.transferable_execution_claim import ExecutionClaimStatus

from prepared_result_validation import (
    PreparedResultValidationError,
    PreparedResultValidatorEndpoint,
    validate_prepared_result_remotely,
)
from stateful_recovery_handoff import resume_on_recovery_host
from stateful_recovery_worker import (
    _canonical,
    _digest,
    _store_independent_verification,
    _store_remote_validator_receipt,
    _write_prepared,
)
from remote_validator_test_support import (
    make_validator_certificates,
    start_validator_service,
    stop_validator_service,
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


def _validator_endpoint(tmp_path: Path, repository_root: Path):
    certificates = make_validator_certificates(tmp_path / "tls")
    process, ready = start_validator_service(
        repository_root,
        tmp_path / "validator-service",
        certificates,
        worker_peer_id="peer-b",
        worker_host_id="logical-host-b",
        worker_implementation_fingerprint=IMPL_B,
    )
    endpoint = PreparedResultValidatorEndpoint(
        validator_peer_id=ready["validator_peer_id"],
        host=ready["host"],
        port=ready["port"],
        server_dns_identity=ready["validator_dns_identity"],
        server_certificate_sha256=ready["server_certificate_sha256"],
        worker_peer_id="peer-b",
        worker_host_id="logical-host-b",
        worker_implementation_fingerprint=IMPL_B,
        worker_certificate_path=certificates["worker_cert"],
        worker_private_key_path=certificates["worker_key"],
        trusted_server_ca_path=certificates["ca"],
    )
    return process, endpoint, ready


def test_remote_validator_receipt_is_bound_into_quorum_completion(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    validator_process, endpoint, ready = _validator_endpoint(tmp_path, repository_root)
    store, coordinator = _store(tmp_path / "claim-store")
    envelope = _reassign_to_b(store, _source_envelope(store))
    prepared_path = tmp_path / "prepared" / f"{envelope.claim_id}.prepared.json"
    selected: dict[str, object] = {}

    def validate_before_commit(output_checkpoint: bytes, receipt_core, receipt_digest: str) -> str:
        _prepare(prepared_path, envelope, output_checkpoint, receipt_core, receipt_digest)
        prepared_record = json.loads(prepared_path.read_text(encoding="utf-8"))
        report = validate_prepared_result_remotely(
            endpoint,
            envelope=envelope.to_dict(),
            prepared_record=prepared_record,
        )
        _store_independent_verification(prepared_path, report["verification"])
        _store_remote_validator_receipt(prepared_path, report["remote_validator_receipt"])
        selected.update(report)
        return report["remote_validator_receipt_digest"]

    try:
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
        assert selected["remote_validator_receipt_digest"] == result.receipt[
            "independent_verification_digest"
        ]
        remote_receipt = record["remote_validator_receipt"]
        assert remote_receipt["validator_peer_id"] == ready["validator_peer_id"]
        assert remote_receipt["validator_dns_identity"] == ready["validator_dns_identity"]
        assert remote_receipt["validator_certificate_sha256"] == ready["server_certificate_sha256"]
        assert remote_receipt["worker_peer_id"] == "peer-b"
        assert remote_receipt["worker_host_id"] == "logical-host-b"
        assert remote_receipt["worker_implementation_fingerprint"] == IMPL_B
        assert remote_receipt["validation"] == record["independent_verification"]
        assert remote_receipt["validation_digest"] == record["independent_verification"]["verification_digest"]
        assert result.completed_ticket.claim.status is ExecutionClaimStatus.COMPLETED
        assert result.completed_ticket.claim.child_receipt_digest == result.receipt_sha256
        assert result.receipt["state_before"] == [1, 0]
        assert result.receipt["state_after"] == [1, 1]
        assert result.receipt["tick_before"] == 3
        assert result.receipt["tick_after"] == 4
        result.completed_ticket.verify_current(coordinator)
    finally:
        stop_validator_service(validator_process)


def test_remote_validator_rejects_tampered_prepared_checkpoint_before_quorum_commit(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    validator_process, endpoint, _ready = _validator_endpoint(tmp_path, repository_root)
    store, _coordinator = _store(tmp_path / "claim-store")
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
        return validate_prepared_result_remotely(
            endpoint,
            envelope=envelope.to_dict(),
            prepared_record=json.loads(prepared_path.read_text(encoding="utf-8")),
        )["remote_validator_receipt_digest"]

    try:
        with pytest.raises(PreparedResultValidationError, match="remote validator rejected"):
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
    finally:
        stop_validator_service(validator_process)


def test_remote_validator_certificate_pin_fails_closed_before_request(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    validator_process, endpoint, _ready = _validator_endpoint(tmp_path, repository_root)
    store, _coordinator = _store(tmp_path / "claim-store")
    envelope = _reassign_to_b(store, _source_envelope(store))
    prepared_path = tmp_path / "prepared" / f"{envelope.claim_id}.prepared.json"
    output = b"this is not used because certificate pinning must fail before sending"
    _prepare(
        prepared_path,
        envelope,
        output,
        {"schema": "invalid"},
        _digest({"schema": "invalid"}),
    )
    forged_endpoint = PreparedResultValidatorEndpoint(
        validator_peer_id=endpoint.validator_peer_id,
        host=endpoint.host,
        port=endpoint.port,
        server_dns_identity=endpoint.server_dns_identity,
        server_certificate_sha256="0" * 64,
        worker_peer_id=endpoint.worker_peer_id,
        worker_host_id=endpoint.worker_host_id,
        worker_implementation_fingerprint=endpoint.worker_implementation_fingerprint,
        worker_certificate_path=endpoint.worker_certificate_path,
        worker_private_key_path=endpoint.worker_private_key_path,
        trusted_server_ca_path=endpoint.trusted_server_ca_path,
    )
    try:
        with pytest.raises(PreparedResultValidationError, match="certificate"):
            validate_prepared_result_remotely(
                forged_endpoint,
                envelope=envelope.to_dict(),
                prepared_record=json.loads(prepared_path.read_text(encoding="utf-8")),
            )
        current = store.get(envelope.claim_id)
        assert current.claim.status is ExecutionClaimStatus.ASSIGNED
    finally:
        stop_validator_service(validator_process)
