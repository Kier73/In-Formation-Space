from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import pytest
import sys
import time
from pathlib import Path

from mailcpu import (
    RecoveryLineageAuthority,
    RecoveryLineageCoordinator,
    ReliabilityPolicy,
    ReliableChannel,
    SeedCommitMembership,
    SocketTransport,
    TransferableExecutionClaimStore,
)

from stateful_recovery_handoff import (
    StatefulRuntimeRecoveryEnvelope,
    issue_stateful_recovery_envelope,
    reassign_after_source_loss,
)
from remote_validator_test_support import (
    make_validator_certificates,
    start_validator_service,
    stop_validator_service,
)


GENESIS = hashlib.sha256(b"ifs-srh-003-worker-transport-genesis").hexdigest()
SOURCE_IMPL = hashlib.sha256(b"source-worker-implementation").hexdigest()
RECOVERY_IMPL = hashlib.sha256(b"recovery-worker-implementation").hexdigest()
SOURCE_FAILURE = hashlib.sha256(b"source-worker-unavailable").hexdigest()
REQUEST_CHANNEL = "ifs.psc.stateful-recovery.request.v1"
RESPONSE_CHANNEL = "ifs.psc.stateful-recovery.response.v1"


def _membership() -> SeedCommitMembership:
    return SeedCommitMembership(
        "ifs-stateful-runtime-worker-transport",
        1,
        ("authority-a", "authority-b", "authority-c"),
        "authority-a",
        1,
        GENESIS,
    )


def _psc_fixture():
    fixture_path = Path(__file__).with_name("test_portable_stateful_checkpoint.py")
    spec = importlib.util.spec_from_file_location("psc001_worker_transport_fixture", fixture_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_runtime_and_capsules()


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _start_authority_process(
    root: Path,
    membership: SeedCommitMembership,
    member_id: str,
) -> tuple[subprocess.Popen[str], int]:
    root.mkdir(parents=True, exist_ok=True)
    membership_path = root / "membership.json"
    membership_path.write_text(
        json.dumps(membership.snapshot(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    repository_root = Path(__file__).resolve().parents[2]
    ecpu_root = repository_root / "external" / "E-CPU"
    worker = ecpu_root / "tests" / "helpers" / "recovery_lineage_authority_worker.py"
    process = subprocess.Popen(
        [
            sys.executable,
            str(worker),
            member_id,
            str(membership_path),
            str(root / f"{member_id}.jsonl"),
            "-",
            str(root / f"{member_id}.marker"),
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
    return process, int(ready["port"])


def _start_worker(
    repository_root: Path,
    arguments: list[str],
) -> tuple[subprocess.Popen[str], int]:
    worker = repository_root / "experiments" / "portable-realization-capsule" / "stateful_recovery_worker.py"
    ecpu_root = repository_root / "external" / "E-CPU"
    vgi_root = repository_root / "external" / "Virtual-Ground-Interpreter" / "virtual_ground_interpreter"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    search = [
        str(repository_root / "experiments" / "portable-realization-capsule"),
        str(ecpu_root),
        str(vgi_root),
    ]
    if existing:
        search.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(search)
    process = subprocess.Popen(
        [sys.executable, str(worker), *arguments],
        cwd=repository_root,
        env=env,
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
            f"recovery worker did not start: rc={process.returncode}, "
            f"stdout={stdout!r}, stderr={stderr!r}"
        )
    ready = json.loads(ready_line)
    assert ready["ready"] is True
    assert ready["pid"] == process.pid
    return process, int(ready["port"])


def _stop(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=5)


@pytest.mark.parametrize(
    ("crash_mode", "expected_exit", "expect_cached_outbox", "expect_completed_claim_recovery", "replacement_controls"),
    (
        ("after-outbox-fsync", 91, True, False, {"advance": 1, "reset": 0}),
        ("after-prepared-fsync", 94, False, False, {"advance": 1, "reset": 0}),
        ("after-claim-complete", 92, False, True, {"advance": 1, "reset": 0}),
        ("after-successor-claim", 93, False, True, {"advance": 1, "reset": 0}),
    ),
)
def test_checkpoint_crosses_reliable_channel_and_recovers_after_worker_kill(
    tmp_path: Path,
    crash_mode: str,
    expected_exit: int,
    expect_cached_outbox: bool,
    expect_completed_claim_recovery: bool,
    replacement_controls: dict[str, int],
) -> None:
    membership = _membership()
    authority_root = tmp_path / "authorities"
    authority_root.mkdir()
    membership_path = authority_root / "membership.json"
    membership_path.write_text(
        json.dumps(membership.snapshot(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    authority_paths = {
        member: authority_root / f"{member}.jsonl"
        for member in membership.member_ids
    }
    authorities = {
        member: RecoveryLineageAuthority(membership, member, authority_paths[member])
        for member in membership.member_ids
    }
    source_coordinator = RecoveryLineageCoordinator(membership, authorities)
    claim_directory = tmp_path / "claims"
    source_store = TransferableExecutionClaimStore(claim_directory, source_coordinator)

    runtime, capsules = _psc_fixture()
    source = issue_stateful_recovery_envelope(
        source_store,
        session_id="worker-transport-counter",
        runtime=runtime,
        realization_capsules=capsules,
        resume_controls={"advance": 1, "reset": 0},
        owner_peer_id="peer-source",
        owner_host_id="logical-host-source",
        implementation_fingerprint=SOURCE_IMPL,
    )
    assigned = reassign_after_source_loss(
        source_store,
        source,
        target_peer_id="peer-recovery-worker",
        target_host_id="logical-host-recovery-worker",
        target_implementation_fingerprint=RECOVERY_IMPL,
        failure_evidence_digest=SOURCE_FAILURE,
    )
    assert source_coordinator.high_water()[0] == 2

    # Start independent authority services against the already committed
    # durable journals. They are contacted by the recovery worker, not by the
    # source process, during the actual PSC continuation.
    process_b: subprocess.Popen[str] | None = None
    process_c: subprocess.Popen[str] | None = None
    first_worker: subprocess.Popen[str] | None = None
    retry_worker: subprocess.Popen[str] | None = None
    first_transport: SocketTransport | None = None
    retry_transport: SocketTransport | None = None
    validator_process: subprocess.Popen[str] | None = None

    try:
        repository_root = Path(__file__).resolve().parents[2]
        validator_certificates = make_validator_certificates(tmp_path / "validator-tls")
        validator_process, validator_ready = start_validator_service(
            repository_root,
            tmp_path / "validator-service",
            validator_certificates,
        )
        process_b, port_b = _start_authority_process(authority_root, membership, "authority-b")
        process_c, port_c = _start_authority_process(authority_root, membership, "authority-c")

        outbox_directory = tmp_path / "worker-outbox"
        outbox_path = outbox_directory / f"{assigned.claim_id}.json"
        prepared_path = outbox_directory / f"{assigned.claim_id}.prepared.json"
        common_arguments = [
            str(membership_path),
            str(authority_paths["authority-a"]),
            str(claim_directory),
            "127.0.0.1",
            str(port_b),
            "127.0.0.1",
            str(port_c),
            str(outbox_directory),
            "peer-recovery-worker",
            "logical-host-recovery-worker",
            RECOVERY_IMPL,
            json.dumps({"advance": 0, "reset": 0}, sort_keys=True, separators=(",", ":")),
            validator_ready["validator_peer_id"],
            validator_ready["host"],
            str(validator_ready["port"]),
            validator_ready["validator_dns_identity"],
            validator_ready["server_certificate_sha256"],
            str(validator_certificates["worker_cert"]),
            str(validator_certificates["worker_key"]),
            str(validator_certificates["ca"]),
            str(validator_certificates["attestation_public_key"]),
        ]

        first_worker, first_port = _start_worker(
            repository_root,
            common_arguments + [crash_mode],
        )
        first_transport = SocketTransport.connect(
            "127.0.0.1",
            first_port,
            "source",
            "recovery-worker",
        )
        policy = ReliabilityPolicy(lease_ticks=1, max_attempts=5, window_size=8)
        request_sender = ReliableChannel(
            first_transport,
            "source",
            "recovery-worker",
            REQUEST_CHANNEL,
            policy,
        )
        response_receiver = ReliableChannel(
            first_transport,
            "source",
            "source",
            RESPONSE_CHANNEL,
            policy,
            peer="recovery-worker",
        )
        assert request_sender.send(assigned.to_dict()) == 1
        request_snapshot = request_sender.snapshot()
        response_snapshot = response_receiver.snapshot()

        # Exercise one of three cuts: after the outbox fsync, after quorum
        # completion but before successor creation, or after successor
        # creation but before the first outbox write.
        first_worker.wait(timeout=20)
        first_stdout, first_stderr = first_worker.communicate(timeout=5)
        assert first_worker.returncode == expected_exit, (
            f"worker exit mismatch: expected={expected_exit}, "
            f"actual={first_worker.returncode}, stdout={first_stdout!r}, stderr={first_stderr!r}"
        )
        assert outbox_path.is_file() is expect_cached_outbox
        assert prepared_path.is_file()
        assert request_sender.pending_sequences() == (1,)
        first_transport.close()
        first_transport = None

        # The authority peer processes may have observed the worker's abrupt
        # disconnect. Restart them from their durable journals so the second
        # worker is admitted against a fresh process set at the committed
        # quorum high-water.
        _stop(process_b)
        _stop(process_c)
        process_b, port_b = _start_authority_process(authority_root, membership, "authority-b")
        process_c, port_c = _start_authority_process(authority_root, membership, "authority-c")
        replacement_arguments = list(common_arguments)
        replacement_arguments[4] = str(port_b)
        replacement_arguments[6] = str(port_c)
        # The prepared checkpoint carries the next-step controls. A replacement
        # with a different local default must recover the exact staged result.
        replacement_arguments[11] = json.dumps(
            replacement_controls,
            sort_keys=True,
            separators=(",", ":"),
        )

        # A replacement worker binds a fresh TCP stream. The requester restores
        # its exact pending reliable frame and retransmits sequence 1. If the
        # outbox exists it is replayed; otherwise the prepared checkpoint is
        # deterministically checked against the same input before claim commit
        # or successor/outbox reconstruction. The replacement's CLI controls
        # intentionally differ from the staged output checkpoint.
        retry_worker, retry_port = _start_worker(
            repository_root,
            replacement_arguments + ["none"],
        )
        retry_transport = SocketTransport.connect(
            "127.0.0.1",
            retry_port,
            "source",
            "recovery-worker",
        )
        restored_request = ReliableChannel.from_snapshot(request_snapshot, retry_transport)
        restored_response = ReliableChannel.from_snapshot(response_snapshot, retry_transport)
        assert restored_request.pending_sequences() == (1,)
        assert restored_request.retransmit(1) is True

        response_packet = None
        acknowledged: list[int] = []
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and response_packet is None:
            acknowledged.extend(restored_request.process_ack())
            received = restored_response.receive()
            if received is not None:
                response_packet = received
                break
            if retry_worker.poll() is not None:
                stdout, stderr = retry_worker.communicate(timeout=5)
                raise AssertionError(
                    f"replacement worker exited before response: rc={retry_worker.returncode}, "
                    f"stdout={stdout!r}, stderr={stderr!r}"
                )
            time.sleep(0.002)
        assert response_packet is not None, "replacement worker did not return the durable response"
        assert response_packet[0] == 1
        response = response_packet[1]
        assert response["schema"] == "ifs.psc.stateful-recovery-worker-response.v1"
        assert response["replayed_from_durable_outbox"] is expect_cached_outbox
        assert response["recovered_from_completed_claim"] is expect_completed_claim_recovery
        assert response["result"]["recovered_from_completed_claim"] is expect_completed_claim_recovery
        assert response["result"]["receipt"]["state_before"] == [1, 0]
        assert response["result"]["receipt"]["state_after"] == [1, 1]
        assert response["result"]["receipt"]["tick_before"] == 3
        assert response["result"]["receipt"]["tick_after"] == 4
        ack_deadline = time.monotonic() + 5.0
        while restored_request.pending_sequences() and time.monotonic() < ack_deadline:
            acknowledged.extend(restored_request.process_ack())
            time.sleep(0.001)
        assert restored_request.pending_sequences() == ()
        assert tuple(acknowledged) == (1,)

        retry_worker.wait(timeout=15)
        assert retry_worker.returncode == 0
        retry_transport.close()
        retry_transport = None

        record = json.loads(outbox_path.read_text(encoding="utf-8"))
        record_core = {key: value for key, value in record.items() if key != "result_sha256"}
        assert record["result_sha256"] == hashlib.sha256(_canonical(record_core)).hexdigest()
        assert record["input_claim_id"] == assigned.claim_id
        assert record["input_envelope_sha256"] == assigned.envelope_sha256
        assert record["request_sequence"] == 1
        prepared_record = json.loads(prepared_path.read_text(encoding="utf-8"))
        prepared_core = {
            key: value for key, value in prepared_record.items()
            if key != "prepared_sha256"
        }
        assert prepared_record["prepared_sha256"] == hashlib.sha256(
            _canonical(prepared_core)
        ).hexdigest()
        independent = prepared_record["independent_verification"]
        remote_receipt = prepared_record["remote_validator_receipt"]
        assert independent is not None
        assert remote_receipt is not None
        assert remote_receipt["validator_peer_id"] == validator_ready["validator_peer_id"]
        assert remote_receipt["validator_dns_identity"] == validator_ready["validator_dns_identity"]
        assert remote_receipt["validator_certificate_sha256"] == validator_ready["server_certificate_sha256"]
        assert remote_receipt["worker_peer_id"] == "peer-recovery-worker"
        assert remote_receipt["worker_host_id"] == "logical-host-recovery-worker"
        assert remote_receipt["worker_implementation_fingerprint"] == RECOVERY_IMPL
        assert remote_receipt["verifier_implementation_fingerprint"] == validator_ready[
            "verifier_implementation_fingerprint"
        ]
        assert remote_receipt["validation"] == independent
        assert remote_receipt["validation_digest"] == independent["verification_digest"]
        remote_core = {
            key: value for key, value in remote_receipt.items()
            if key != "remote_validator_receipt_digest"
        }
        remote_digest = hashlib.sha256(_canonical(remote_core)).hexdigest()
        assert remote_receipt["remote_validator_receipt_digest"] == remote_digest
        assert remote_digest == response["result"]["receipt"]["independent_verification_digest"]
        receipt = dict(response["result"]["receipt"])
        receipt_digest = receipt.pop("receipt_sha256")
        assert receipt_digest == response["result"]["receipt_sha256"]
        assert hashlib.sha256(_canonical(receipt)).hexdigest() == receipt_digest
        next_envelope = StatefulRuntimeRecoveryEnvelope.from_dict(
            response["result"]["next_envelope"]
        )
        assert next_envelope.checkpoint_sha256 == record["result"]["next_envelope"]["checkpoint_sha256"]
        assert response["result"]["receipt_sha256"] == record["result"]["receipt_sha256"]

        # Re-open all three local authority journals after the remote child
        # processes have completed their durable commits. This independently
        # verifies the claim chain from the source-side store.
        _stop(process_b)
        _stop(process_c)
        process_b = process_c = None
        restored_authorities = {
            member: RecoveryLineageAuthority(membership, member, authority_paths[member])
            for member in membership.member_ids
        }
        restored_coordinator = RecoveryLineageCoordinator(membership, restored_authorities)
        restored_store = TransferableExecutionClaimStore(claim_directory, restored_coordinator)
        assert restored_coordinator.high_water()[0] == 4

        completed = restored_store.get(source.claim_id)
        assert completed.claim.status.value == "completed"
        assert completed.claim.result_digest == next_envelope.checkpoint_sha256
        assert completed.claim.child_receipt_digest == response["result"]["receipt_sha256"]
        completed.verify_current(restored_coordinator)

        successor = restored_store.get(next_envelope.claim_id)
        successor.verify_for_target(
            restored_coordinator,
            parent_request_digest=successor.claim.parent_request_digest,
            child_request_digest=successor.claim.child_request_digest,
            address_digest=successor.claim.address_digest,
            operator_spec=successor.claim.operator_spec,
            computational_ground_fingerprint=successor.claim.computational_ground_fingerprint,
            owner_peer_id="peer-recovery-worker",
            owner_host_id="logical-host-recovery-worker",
            implementation_fingerprint=RECOVERY_IMPL,
        )
    finally:
        if first_transport is not None:
            first_transport.close()
        if retry_transport is not None:
            retry_transport.close()
        _stop(first_worker)
        _stop(retry_worker)
        _stop(process_b)
        _stop(process_c)
        stop_validator_service(validator_process)
