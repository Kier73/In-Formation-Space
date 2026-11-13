"""Receiver-side SRH-003 worker with a digest-bound durable response outbox."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from mailcpu import (
    DistributedRecoveryLineageCoordinator,
    RecoveryLineageAuthority,
    RecoveryLineagePeerClient,
    ReliabilityPolicy,
    ReliableChannel,
    SeedCommitMembership,
    SocketTransport,
    TransferableExecutionClaimStore,
)

from portable_stateful_checkpoint import decode_checkpoint
from prepared_result_validation import (
    PreparedResultValidatorEndpoint,
    validate_prepared_result_remotely,
    verify_stored_remote_validator_receipt,
)
from stateful_recovery_handoff import (
    StatefulRuntimeRecoveryEnvelope,
    resume_on_recovery_host,
)


REQUEST_CHANNEL = "ifs.psc.stateful-recovery.request.v1"
RESPONSE_CHANNEL = "ifs.psc.stateful-recovery.response.v1"
OUTBOX_SCHEMA = "ifs.psc.stateful-recovery-worker-outbox.v1"
PREPARED_SCHEMA = "ifs.psc.stateful-recovery-worker-prepared.v4"
_MAX_RECORD_BYTES = 96 * 1024 * 1024


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _record_path(outbox_directory: Path, claim_id: str) -> Path:
    if (
        not isinstance(claim_id, str)
        or len(claim_id) != 64
        or any(character not in "0123456789abcdef" for character in claim_id)
    ):
        raise ValueError("claim_id must be a lowercase SHA-256 identity")
    return outbox_directory / f"{claim_id}.json"


def _read_outbox(
    path: Path,
    *,
    sequence: int,
    envelope: StatefulRuntimeRecoveryEnvelope,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw_bytes = path.read_bytes()
    if not raw_bytes or len(raw_bytes) > _MAX_RECORD_BYTES:
        raise ValueError("durable outbox record is empty or exceeds the 96 MiB bound")
    record = json.loads(raw_bytes.decode("utf-8"))
    fields = {
        "schema",
        "request_sequence",
        "input_claim_id",
        "input_checkpoint_sha256",
        "input_envelope_sha256",
        "result",
        "result_sha256",
    }
    if not isinstance(record, Mapping) or set(record) != fields:
        raise ValueError("durable outbox record fields do not match v1")
    core = {key: record[key] for key in fields if key != "result_sha256"}
    if record["schema"] != OUTBOX_SCHEMA:
        raise ValueError("durable outbox record schema is not supported")
    if _digest(core) != record["result_sha256"]:
        raise ValueError("durable outbox record digest mismatch")
    if (
        record["request_sequence"] != sequence
        or record["input_claim_id"] != envelope.claim_id
        or record["input_checkpoint_sha256"] != envelope.checkpoint_sha256
        or record["input_envelope_sha256"] != envelope.envelope_sha256
    ):
        raise ValueError("durable outbox record does not bind this exact request and checkpoint")
    if not isinstance(record["result"], Mapping):
        raise ValueError("durable outbox result must be a mapping")
    return dict(record)


def _prepared_path(prepared_directory: Path, claim_id: str) -> Path:
    return prepared_directory / f"{claim_id}.prepared.json"


def _read_prepared(
    path: Path,
    *,
    sequence: int,
    envelope: StatefulRuntimeRecoveryEnvelope,
    owner_peer_id: str,
    owner_host_id: str,
    implementation_fingerprint: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw_bytes = path.read_bytes()
    if not raw_bytes or len(raw_bytes) > _MAX_RECORD_BYTES:
        raise ValueError("prepared result is empty or exceeds the 96 MiB bound")
    record = json.loads(raw_bytes.decode("utf-8"))
    fields = {
        "schema",
        "request_sequence",
        "input_claim_id",
        "input_checkpoint_sha256",
        "input_envelope_sha256",
        "assignment_epoch",
        "owner_peer_id",
        "owner_host_id",
        "implementation_fingerprint",
        "output_checkpoint_base64",
        "output_checkpoint_sha256",
        "receipt_core",
        "receipt_sha256",
        "independent_verification",
        "remote_validator_receipt",
        "prepared_sha256",
    }
    if not isinstance(record, Mapping) or set(record) != fields:
        raise ValueError("prepared result fields do not match v3")
    core = {key: record[key] for key in fields if key != "prepared_sha256"}
    if record["schema"] != PREPARED_SCHEMA or _digest(core) != record["prepared_sha256"]:
        raise ValueError("prepared result schema or digest is invalid")
    verification = record["independent_verification"]
    if verification is not None:
        if not isinstance(verification, Mapping) or "verification_digest" not in verification:
            raise ValueError("prepared independent-verification receipt is malformed")
        verification_core = {
            key: value for key, value in verification.items()
            if key != "verification_digest"
        }
        if _digest(verification_core) != verification["verification_digest"]:
            raise ValueError("prepared independent-verification receipt digest mismatch")
    remote_receipt = record["remote_validator_receipt"]
    if remote_receipt is not None:
        if not isinstance(remote_receipt, Mapping) or "remote_validator_receipt_digest" not in remote_receipt:
            raise ValueError("prepared remote-validator receipt is malformed")
        remote_core = {
            key: value for key, value in remote_receipt.items()
            if key != "remote_validator_receipt_digest"
        }
        if _digest(remote_core) != remote_receipt["remote_validator_receipt_digest"]:
            raise ValueError("prepared remote-validator receipt digest mismatch")
        if (
            verification is None
            or remote_receipt.get("validation") != verification
            or remote_receipt.get("validation_digest") != verification.get("verification_digest")
        ):
            raise ValueError("prepared remote-validator receipt is not bound to the independent verification")
    if (
        record["request_sequence"] != sequence
        or record["input_claim_id"] != envelope.claim_id
        or record["input_checkpoint_sha256"] != envelope.checkpoint_sha256
        or record["input_envelope_sha256"] != envelope.envelope_sha256
        or record["assignment_epoch"] != envelope.ticket.claim.current_assignment.epoch
        or record["owner_peer_id"] != owner_peer_id
        or record["owner_host_id"] != owner_host_id
        or record["implementation_fingerprint"] != implementation_fingerprint
    ):
        raise ValueError("prepared result does not bind this exact request, assignment, and target")
    encoded = record["output_checkpoint_base64"]
    if not isinstance(encoded, str) or len(encoded) > ((_MAX_RECORD_BYTES + 2) // 3) * 4:
        raise ValueError("prepared checkpoint Base64 is missing or exceeds its bound")
    output_checkpoint = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(output_checkpoint).hexdigest() != record["output_checkpoint_sha256"]:
        raise ValueError("prepared checkpoint digest mismatch")
    receipt_core = record["receipt_core"]
    if not isinstance(receipt_core, Mapping) or _digest(receipt_core) != record["receipt_sha256"]:
        raise ValueError("prepared receipt digest mismatch")
    if (
        receipt_core.get("input_claim_id") != envelope.claim_id
        or receipt_core.get("input_checkpoint_sha256") != envelope.checkpoint_sha256
        or receipt_core.get("assignment_epoch") != record["assignment_epoch"]
        or receipt_core.get("owner_peer_id") != owner_peer_id
        or receipt_core.get("owner_host_id") != owner_host_id
        or receipt_core.get("implementation_fingerprint") != implementation_fingerprint
        or receipt_core.get("output_checkpoint_sha256") != record["output_checkpoint_sha256"]
    ):
        raise ValueError("prepared receipt is not bound to its checkpoint and target")
    # Decode the actual checkpoint now, so malformed bytes never become the
    # source of next-step controls during recovery.
    decode_checkpoint(output_checkpoint)
    return {**dict(record), "output_checkpoint": output_checkpoint}


def _write_prepared(
    path: Path,
    *,
    sequence: int,
    envelope: StatefulRuntimeRecoveryEnvelope,
    output_checkpoint: bytes,
    receipt_core: Mapping[str, Any],
    receipt_sha256: str,
    owner_peer_id: str,
    owner_host_id: str,
    implementation_fingerprint: str,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    core = {
        "schema": PREPARED_SCHEMA,
        "request_sequence": sequence,
        "input_claim_id": envelope.claim_id,
        "input_checkpoint_sha256": envelope.checkpoint_sha256,
        "input_envelope_sha256": envelope.envelope_sha256,
        "assignment_epoch": envelope.ticket.claim.current_assignment.epoch,
        "owner_peer_id": owner_peer_id,
        "owner_host_id": owner_host_id,
        "implementation_fingerprint": implementation_fingerprint,
        "output_checkpoint_base64": base64.b64encode(output_checkpoint).decode("ascii"),
        "output_checkpoint_sha256": hashlib.sha256(output_checkpoint).hexdigest(),
        "receipt_core": dict(receipt_core),
        "receipt_sha256": receipt_sha256,
        "independent_verification": None,
        "remote_validator_receipt": None,
    }
    if _digest(core["receipt_core"]) != receipt_sha256:
        raise ValueError("worker attempted to persist a prepared result with an invalid receipt digest")
    record = {**core, "prepared_sha256": _digest(core)}
    payload = _canonical(record) + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return record


def _store_independent_verification(
    path: Path,
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    existing = record.get("independent_verification")
    selected = dict(verification)
    if existing is not None and existing != selected:
        raise ValueError("prepared independent-verification receipt changed across recovery")
    record["independent_verification"] = selected
    core = {key: value for key, value in record.items() if key != "prepared_sha256"}
    record["prepared_sha256"] = _digest(core)
    payload = _canonical(record) + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.verification.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return record


def _store_remote_validator_receipt(
    path: Path,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    existing = record.get("remote_validator_receipt")
    selected = dict(receipt)
    if existing is not None and existing != selected:
        raise ValueError("remote-validator receipt changed across recovery")
    record["remote_validator_receipt"] = selected
    core = {key: value for key, value in record.items() if key != "prepared_sha256"}
    record["prepared_sha256"] = _digest(core)
    payload = _canonical(record) + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.remote-verification.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return record


def _verify_prepared_remotely(
    *,
    endpoint: PreparedResultValidatorEndpoint,
    envelope: StatefulRuntimeRecoveryEnvelope,
    prepared_path: Path,
) -> dict[str, Any]:
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    return validate_prepared_result_remotely(
        endpoint,
        envelope=envelope.to_dict(),
        prepared_record=prepared,
    )


def _write_outbox(
    path: Path,
    *,
    sequence: int,
    envelope: StatefulRuntimeRecoveryEnvelope,
    result: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    core = {
        "schema": OUTBOX_SCHEMA,
        "request_sequence": sequence,
        "input_claim_id": envelope.claim_id,
        "input_checkpoint_sha256": envelope.checkpoint_sha256,
        "input_envelope_sha256": envelope.envelope_sha256,
        "result": dict(result),
    }
    record = {**core, "result_sha256": _digest(core)}
    payload = _canonical(record) + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _result_payload(result: Any) -> dict[str, Any]:
    return {
        "completed_ticket": result.completed_ticket.to_dict(),
        "receipt": dict(result.receipt),
        "receipt_sha256": result.receipt_sha256,
        "next_envelope": result.next_envelope.to_dict(),
        "recovered_from_completed_claim": result.recovered_from_completed_claim,
    }


def _resume_once(
    *,
    envelope: StatefulRuntimeRecoveryEnvelope,
    membership: SeedCommitMembership,
    owner_journal_path: Path,
    claim_store_directory: Path,
    authority_b_host: str,
    authority_b_port: int,
    authority_c_host: str,
    authority_c_port: int,
    owner_peer_id: str,
    owner_host_id: str,
    implementation_fingerprint: str,
    next_resume_controls: Mapping[str, int],
    crash_mode: str,
    before_claim_complete: Callable[[bytes, Mapping[str, Any], str], str],
) -> dict[str, Any]:
    peer_b = RecoveryLineagePeerClient.connect(
        membership,
        "authority-b",
        authority_b_host,
        authority_b_port,
        timeout=3.0,
    )
    peer_c = None
    coordinator = None
    try:
        peer_c = RecoveryLineagePeerClient.connect(
            membership,
            "authority-c",
            authority_c_host,
            authority_c_port,
            timeout=3.0,
        )
        owner = RecoveryLineageAuthority(
            membership,
            membership.owner_id,
            owner_journal_path,
        )
        coordinator = DistributedRecoveryLineageCoordinator(
            membership,
            {
                membership.owner_id: owner,
                "authority-b": peer_b,
                "authority-c": peer_c,
            },
        )
        store = TransferableExecutionClaimStore(claim_store_directory, coordinator)
        def crash_after_claim_complete(_ticket: Any) -> None:
            if crash_mode == "after-claim-complete":
                os._exit(92)

        def crash_after_successor_claim(_next_envelope: Any) -> None:
            if crash_mode == "after-successor-claim":
                os._exit(93)

        result = resume_on_recovery_host(
            store,
            envelope,
            owner_peer_id=owner_peer_id,
            owner_host_id=owner_host_id,
            implementation_fingerprint=implementation_fingerprint,
            next_resume_controls=next_resume_controls,
            before_claim_complete=before_claim_complete,
            after_claim_complete=crash_after_claim_complete,
            after_successor_claim=crash_after_successor_claim,
        )
        return _result_payload(result)
    finally:
        if coordinator is not None:
            coordinator.close()
        else:
            peer_b.close()
            if peer_c is not None:
                peer_c.close()


def _run(arguments: list[str]) -> int:
    if len(arguments) != 22:
        raise ValueError(
            "worker requires membership/claim stores, authority B/C endpoints, runtime identity, "
            "next controls, validator peer/host/port/DNS/certificate pin, worker certificate/key, "
            "validator CA bundle, and crash mode"
        )
    (
        membership_path,
        owner_journal_path,
        claim_store_directory,
        authority_b_host,
        authority_b_port,
        authority_c_host,
        authority_c_port,
        outbox_directory,
        owner_peer_id,
        owner_host_id,
        implementation_fingerprint,
        next_controls_json,
        validator_peer_id,
        validator_host,
        validator_port,
        validator_dns_identity,
        validator_certificate_sha256,
        worker_certificate_path,
        worker_private_key_path,
        validator_ca_path,
        validator_attestation_public_key_path,
        crash_mode,
    ) = arguments

    membership = SeedCommitMembership.from_snapshot(
        json.loads(Path(membership_path).read_text(encoding="utf-8"))
    )
    next_resume_controls = json.loads(next_controls_json)
    if not isinstance(next_resume_controls, Mapping):
        raise ValueError("next resume controls must be a JSON object")
    validator_endpoint = PreparedResultValidatorEndpoint(
        validator_peer_id=validator_peer_id,
        host=validator_host,
        port=int(validator_port),
        server_dns_identity=validator_dns_identity,
        server_certificate_sha256=validator_certificate_sha256,
        worker_peer_id=owner_peer_id,
        worker_host_id=owner_host_id,
        worker_implementation_fingerprint=implementation_fingerprint,
        worker_certificate_path=Path(worker_certificate_path),
        worker_private_key_path=Path(worker_private_key_path),
        trusted_server_ca_path=Path(validator_ca_path),
        attestation_public_key_path=Path(validator_attestation_public_key_path),
    )

    listener = SocketTransport.listen("127.0.0.1", 0)
    port = listener.getsockname()[1]
    print(json.dumps({"ready": True, "port": port, "pid": os.getpid()}), flush=True)
    try:
        transport = SocketTransport.accept(
            listener,
            "recovery-worker",
            "source",
        )
    finally:
        listener.close()

    policy = ReliabilityPolicy(lease_ticks=1, max_attempts=5, window_size=8)
    incoming = ReliableChannel(
        transport,
        "recovery-worker",
        "recovery-worker",
        REQUEST_CHANNEL,
        policy,
        peer="source",
    )
    outgoing = ReliableChannel(
        transport,
        "recovery-worker",
        "source",
        RESPONSE_CHANNEL,
        policy,
        peer="source",
    )
    response_holder: dict[str, Any] = {}

    def commit_request(sequence: int, payload: Any) -> None:
        envelope = StatefulRuntimeRecoveryEnvelope.from_dict(payload)
        outbox_path = _record_path(Path(outbox_directory), envelope.claim_id)
        stored = _read_outbox(
            outbox_path,
            sequence=sequence,
            envelope=envelope,
        )
        if stored is not None:
            response_holder["payload"] = {
                "schema": "ifs.psc.stateful-recovery-worker-response.v1",
                "result": stored["result"],
                "replayed_from_durable_outbox": True,
                "recovered_from_completed_claim": stored["result"].get("recovered_from_completed_claim", False),
            }
            return

        prepared_path = _prepared_path(Path(outbox_directory), envelope.claim_id)
        prepared = _read_prepared(
            prepared_path,
            sequence=sequence,
            envelope=envelope,
            owner_peer_id=owner_peer_id,
            owner_host_id=owner_host_id,
            implementation_fingerprint=implementation_fingerprint,
        )
        if prepared is not None and prepared.get("remote_validator_receipt") is not None:
            verify_stored_remote_validator_receipt(
                validator_endpoint,
                prepared["remote_validator_receipt"],
            )
        selected_next_controls = (
            decode_checkpoint(prepared["output_checkpoint"])["resume_controls"]
            if prepared is not None
            else next_resume_controls
        )

        def persist_prepared(
            output_checkpoint: bytes,
            receipt_core: Mapping[str, Any],
            receipt_sha256: str,
        ) -> str:
            if prepared is not None:
                if (
                    prepared["output_checkpoint"] != output_checkpoint
                    or prepared["receipt_core"] != dict(receipt_core)
                    or prepared["receipt_sha256"] != receipt_sha256
                ):
                    raise ValueError(
                        "deterministic replay differs from the durable prepared checkpoint or receipt"
                    )
            else:
                _write_prepared(
                    prepared_path,
                    sequence=sequence,
                    envelope=envelope,
                    output_checkpoint=output_checkpoint,
                    receipt_core=receipt_core,
                    receipt_sha256=receipt_sha256,
                    owner_peer_id=owner_peer_id,
                    owner_host_id=owner_host_id,
                    implementation_fingerprint=implementation_fingerprint,
                )
                if crash_mode == "after-prepared-fsync":
                    # The prepared result exists durably, but independent
                    # receiver validation and quorum completion have not run.
                    os._exit(94)

            persisted_record = json.loads(prepared_path.read_text(encoding="utf-8"))
            persisted_output = base64.b64decode(
                persisted_record["output_checkpoint_base64"],
                validate=True,
            )
            if (
                persisted_output != output_checkpoint
                or persisted_record["receipt_core"] != dict(receipt_core)
                or persisted_record["receipt_sha256"] != receipt_sha256
            ):
                raise ValueError(
                    "prepared file changed after construction and no longer matches the in-memory transition result"
                )
            independent = _verify_prepared_remotely(
                endpoint=validator_endpoint,
                envelope=envelope,
                prepared_path=prepared_path,
            )
            verification = independent["verification"]
            if prepared is None or prepared.get("independent_verification") is None:
                _store_independent_verification(prepared_path, verification)
            elif prepared["independent_verification"] != verification:
                raise ValueError(
                    "remote independent-verification report changed during deterministic recovery"
                )

            remote_receipt = independent["remote_validator_receipt"]
            if prepared is None or prepared.get("remote_validator_receipt") is None:
                _store_remote_validator_receipt(prepared_path, remote_receipt)
            elif prepared["remote_validator_receipt"] != remote_receipt:
                raise ValueError(
                    "authenticated remote-validator receipt changed during deterministic recovery"
                )
            return independent["remote_validator_receipt_digest"]

        result = _resume_once(
            envelope=envelope,
            membership=membership,
            owner_journal_path=Path(owner_journal_path),
            claim_store_directory=Path(claim_store_directory),
            authority_b_host=authority_b_host,
            authority_b_port=int(authority_b_port),
            authority_c_host=authority_c_host,
            authority_c_port=int(authority_c_port),
            owner_peer_id=owner_peer_id,
            owner_host_id=owner_host_id,
            implementation_fingerprint=implementation_fingerprint,
            next_resume_controls=selected_next_controls,
            crash_mode=crash_mode,
            before_claim_complete=persist_prepared,
        )
        _write_outbox(
            outbox_path,
            sequence=sequence,
            envelope=envelope,
            result=result,
        )
        if crash_mode == "after-outbox-fsync":
            # Simulate a hard process cut after the response is durable but
            # before ReliableChannel consumes the request or emits its ACK.
            os._exit(91)
        response_holder["payload"] = {
            "schema": "ifs.psc.stateful-recovery-worker-response.v1",
            "result": result,
            "replayed_from_durable_outbox": False,
            "recovered_from_completed_claim": result.get("recovered_from_completed_claim", False),
        }

    deadline = time.monotonic() + 30.0
    received = None
    while received is None and time.monotonic() < deadline:
        received = incoming.receive(commit=commit_request)
        if received is None:
            time.sleep(0.002)
    if received is None:
        raise TimeoutError("recovery worker did not receive a PSC request before its deadline")
    if "payload" not in response_holder:
        raise RuntimeError("recovery worker committed a request without producing a response")

    outgoing.send(response_holder["payload"])
    ack_deadline = time.monotonic() + 10.0
    while outgoing.pending_sequences() and time.monotonic() < ack_deadline:
        outgoing.process_ack()
        time.sleep(0.002)
    if outgoing.pending_sequences():
        raise TimeoutError("recovery worker response was not acknowledged")
    transport.close()
    print(json.dumps({"completed": True, "sequence": received[0]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_run(sys.argv[1:]))
