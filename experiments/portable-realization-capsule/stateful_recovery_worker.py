"""Receiver-side SRH-003 worker with a digest-bound durable response outbox."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

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

from stateful_recovery_handoff import (
    StatefulRuntimeRecoveryEnvelope,
    resume_on_recovery_host,
)


REQUEST_CHANNEL = "ifs.psc.stateful-recovery.request.v1"
RESPONSE_CHANNEL = "ifs.psc.stateful-recovery.response.v1"
OUTBOX_SCHEMA = "ifs.psc.stateful-recovery-worker-outbox.v1"
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
        result = resume_on_recovery_host(
            store,
            envelope,
            owner_peer_id=owner_peer_id,
            owner_host_id=owner_host_id,
            implementation_fingerprint=implementation_fingerprint,
            next_resume_controls=next_resume_controls,
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
    if len(arguments) != 13:
        raise ValueError(
            "worker requires membership, owner journal, claims, B host/port, C host/port, "
            "outbox, owner peer/host, implementation digest, next controls, and crash mode"
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
        crash_mode,
    ) = arguments

    membership = SeedCommitMembership.from_snapshot(
        json.loads(Path(membership_path).read_text(encoding="utf-8"))
    )
    next_resume_controls = json.loads(next_controls_json)
    if not isinstance(next_resume_controls, Mapping):
        raise ValueError("next resume controls must be a JSON object")

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
            }
            return

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
            next_resume_controls=next_resume_controls,
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
