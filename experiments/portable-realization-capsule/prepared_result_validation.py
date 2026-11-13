"""Mutually authenticated remote validation for prepared PSC continuations.

The validator receives only a portable envelope and prepared result. It has no
E-CPU claim store or authority handle: its sole operation is independent
verification and publication of a content-bound validation receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from mailcpu import ReliabilityPolicy, ReliableChannel, SocketTransport
from mailcpu.mtls_transport import accept_mutual_tls, connect_mutual_tls


REQUEST_CHANNEL = "ifs.psc.remote-validator.request.v1"
RESPONSE_CHANNEL = "ifs.psc.remote-validator.response.v1"
REQUEST_SCHEMA = "ifs.psc.remote-validator.request.v1"
RESPONSE_SCHEMA = "ifs.psc.remote-validator.response.v1"
VALIDATION_RECEIPT_SCHEMA = "ifs.psc.remote-validator-receipt.v1"

_MAX_REQUEST_BYTES = 96 * 1024 * 1024
_MAX_FRAME_BYTES = 192 * 1024 * 1024
_SERVICE_POLL_SECONDS = 0.002
_SERVICE_REQUEST_TIMEOUT_SECONDS = 30.0
_SERVICE_RESPONSE_ACK_TIMEOUT_SECONDS = 10.0


class PreparedResultValidationError(RuntimeError):
    """Remote validation, authenticated-peer admission, or receipt binding failed."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PreparedResultValidationError(
            "remote validation material is outside canonical finite JSON"
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
    ):
        raise PreparedResultValidationError(f"{field} must be non-empty trimmed text")
    return value


def _require_digest(value: Any, field: str) -> str:
    selected = _require_text(value, field)
    if (
        len(selected) != 64
        or any(character not in "0123456789abcdef" for character in selected)
    ):
        raise PreparedResultValidationError(f"{field} must be a lowercase SHA-256 digest")
    return selected


def _exact_fields(value: Any, expected: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PreparedResultValidationError(f"{field} fields do not match the exact schema")
    return value


def verifier_implementation_fingerprint(script_directory: Path | None = None) -> str:
    """Bind the independent Node verifier and its shared capsule receiver by their exact bytes."""
    root = script_directory or Path(__file__).resolve().parent
    prepared_script = root / "verify_prepared_result.mjs"
    capsule_script = root / "verify_capsule.mjs"
    if not prepared_script.is_file() or not capsule_script.is_file():
        raise PreparedResultValidationError("validator implementation files are missing")
    return _digest(
        {
            "schema": "ifs.psc.remote-validator-implementation.v1",
            "verify_prepared_result_sha256": _bytes_digest(prepared_script.read_bytes()),
            "verify_capsule_sha256": _bytes_digest(capsule_script.read_bytes()),
        }
    )


@dataclass(frozen=True)
class PreparedResultValidatorEndpoint:
    """Pinned remote verifier endpoint and the worker credentials used for mutual TLS."""

    validator_peer_id: str
    host: str
    port: int
    server_dns_identity: str
    server_certificate_sha256: str
    worker_peer_id: str
    worker_host_id: str
    worker_implementation_fingerprint: str
    worker_certificate_path: Path
    worker_private_key_path: Path
    trusted_server_ca_path: Path
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _require_text(self.validator_peer_id, "validator_peer_id")
        _require_text(self.host, "validator host")
        _require_text(self.server_dns_identity, "validator DNS identity")
        _require_digest(self.server_certificate_sha256, "validator certificate digest")
        _require_text(self.worker_peer_id, "worker_peer_id")
        _require_text(self.worker_host_id, "worker_host_id")
        _require_digest(
            self.worker_implementation_fingerprint,
            "worker_implementation_fingerprint",
        )
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise PreparedResultValidationError("validator port must be within 1..65535")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
        ):
            raise PreparedResultValidationError("validator timeout must be positive")
        for value, name in (
            (self.worker_certificate_path, "worker certificate"),
            (self.worker_private_key_path, "worker private key"),
            (self.trusted_server_ca_path, "validator CA bundle"),
        ):
            if not isinstance(value, Path) or not value.is_file():
                raise PreparedResultValidationError(f"{name} path must refer to an existing file")


def _build_client_context(endpoint: PreparedResultValidatorEndpoint) -> ssl.SSLContext:
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=str(endpoint.trusted_server_ca_path),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        certfile=str(endpoint.worker_certificate_path),
        keyfile=str(endpoint.worker_private_key_path),
    )
    return context


def _validation_request(
    endpoint: PreparedResultValidatorEndpoint,
    envelope: Mapping[str, Any],
    prepared_record: Mapping[str, Any],
) -> dict[str, Any]:
    if len(_canonical(envelope)) + len(_canonical(prepared_record)) > _MAX_REQUEST_BYTES:
        raise PreparedResultValidationError("remote validation request exceeds its finite byte bound")
    # Previous verification receipts are checked by the worker against their
    # stored digests. Keep them out of the content-addressed validator request
    # so a retry is byte-identical to the first validation attempt.
    prepared_projection = dict(prepared_record)
    prepared_projection["independent_verification"] = None
    prepared_projection["remote_validator_receipt"] = None
    prepared_projection_core = {
        key: value for key, value in prepared_projection.items()
        if key != "prepared_sha256"
    }
    prepared_projection["prepared_sha256"] = _digest(prepared_projection_core)
    assignment_epoch = prepared_projection.get("assignment_epoch")
    claim_id = prepared_projection.get("input_claim_id")
    prepared_sha256 = prepared_projection.get("prepared_sha256")
    request_id = _digest(
        {
            "schema": "ifs.psc.remote-validator-request-identity.v1",
            "validator_peer_id": endpoint.validator_peer_id,
            "worker_peer_id": endpoint.worker_peer_id,
            "input_claim_id": claim_id,
            "assignment_epoch": assignment_epoch,
            "prepared_sha256": prepared_sha256,
        }
    )
    core = {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id,
        "validator_peer_id": endpoint.validator_peer_id,
        "worker_peer_id": endpoint.worker_peer_id,
        "envelope": dict(envelope),
        "prepared_record": prepared_projection,
    }
    return {**core, "request_sha256": _digest(core)}


def validate_prepared_result_remotely(
    endpoint: PreparedResultValidatorEndpoint,
    *,
    envelope: Mapping[str, Any],
    prepared_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Send exact bytes and metadata to a pinned mutual-TLS validator and verify its receipt."""
    if not isinstance(endpoint, PreparedResultValidatorEndpoint):
        raise PreparedResultValidationError("remote validation requires a typed endpoint")
    if (
        prepared_record.get("owner_peer_id") != endpoint.worker_peer_id
        or prepared_record.get("owner_host_id") != endpoint.worker_host_id
        or prepared_record.get("implementation_fingerprint")
        != endpoint.worker_implementation_fingerprint
    ):
        raise PreparedResultValidationError(
            "prepared assignment does not match the configured validator worker peer/Host/implementation"
        )
    request = _validation_request(endpoint, envelope, prepared_record)
    context = _build_client_context(endpoint)
    transport = None
    try:
        transport = connect_mutual_tls(
            endpoint.host,
            endpoint.port,
            endpoint.worker_peer_id,
            endpoint.validator_peer_id,
            context,
            server_hostname=endpoint.server_dns_identity,
            timeout=min(endpoint.timeout_seconds, 10.0),
            handshake_timeout=min(endpoint.timeout_seconds, 10.0),
            max_frame_size=_MAX_FRAME_BYTES,
            send_timeout=min(endpoint.timeout_seconds, 10.0),
        )
        peer_der = transport.socket.getpeercert(binary_form=True)
        if not peer_der:
            raise PreparedResultValidationError("TLS validator did not present a peer certificate")
        peer_certificate_sha256 = _bytes_digest(peer_der)
        if peer_certificate_sha256 != endpoint.server_certificate_sha256:
            raise PreparedResultValidationError(
                "authenticated validator certificate does not match the configured certificate pin"
            )

        policy = ReliabilityPolicy(lease_ticks=1, max_attempts=8, window_size=2)
        requests = ReliableChannel(
            transport,
            endpoint.worker_peer_id,
            endpoint.validator_peer_id,
            REQUEST_CHANNEL,
            policy,
            peer=endpoint.validator_peer_id,
        )
        responses = ReliableChannel(
            transport,
            endpoint.worker_peer_id,
            endpoint.worker_peer_id,
            RESPONSE_CHANNEL,
            policy,
            peer=endpoint.validator_peer_id,
        )
        request_sequence = requests.send(request)
        acknowledged: list[int] = []
        deadline = time.monotonic() + endpoint.timeout_seconds
        response_packet = None
        while time.monotonic() < deadline and response_packet is None:
            acknowledged.extend(requests.process_ack())
            response_packet = responses.receive()
            if response_packet is None:
                if transport.closed:
                    raise PreparedResultValidationError("validator closed the authenticated stream before its result")
                time.sleep(_SERVICE_POLL_SECONDS)

        if response_packet is None:
            raise TimeoutError("remote prepared-result validator did not answer before its deadline")
        response_sequence, response = response_packet
        if response_sequence != 1 or not isinstance(response, Mapping):
            raise PreparedResultValidationError("remote validator response sequence or shape is invalid")

        response_fields = {
            "schema",
            "request_id",
            "request_sha256",
            "validator_peer_id",
            "validator_dns_identity",
            "worker_peer_id",
            "worker_host_id",
            "worker_implementation_fingerprint",
            "status",
            "validation_report",
            "verifier_implementation_fingerprint",
            "response_sha256",
            "rejection",
        }
        _exact_fields(response, response_fields, "remote validator response")
        response_core = {key: value for key, value in response.items() if key != "response_sha256"}
        if (
            response["schema"] != RESPONSE_SCHEMA
            or response["request_id"] != request["request_id"]
            or response["request_sha256"] != request["request_sha256"]
            or response["validator_peer_id"] != endpoint.validator_peer_id
            or response["validator_dns_identity"] != endpoint.server_dns_identity
            or response["worker_peer_id"] != endpoint.worker_peer_id
            or response["worker_host_id"] != endpoint.worker_host_id
            or response["worker_implementation_fingerprint"]
            != endpoint.worker_implementation_fingerprint
            or _digest(response_core) != _require_digest(response["response_sha256"], "response_sha256")
        ):
            raise PreparedResultValidationError("remote validator response identity or digest mismatch")
        if response["status"] != "verified":
            rejection = response.get("rejection")
            raise PreparedResultValidationError(
                f"remote validator rejected the prepared result: {rejection or 'unspecified rejection'}"
            )

        report = response["validation_report"]
        if not isinstance(report, Mapping) or report.get("valid") is not True:
            raise PreparedResultValidationError("remote validator did not return a successful verification report")
        if (
            not isinstance(report.get("verification"), Mapping)
            or not isinstance(report.get("verification_digest"), str)
            or _digest({
                key: value for key, value in report["verification"].items()
                if key != "verification_digest"
            }) != report["verification_digest"]
        ):
            raise PreparedResultValidationError("remote validator's independent report digest is invalid")

        local_implementation = verifier_implementation_fingerprint()
        remote_implementation = _require_digest(
            response["verifier_implementation_fingerprint"],
            "verifier_implementation_fingerprint",
        )
        if remote_implementation != local_implementation:
            raise PreparedResultValidationError(
                "remote validator implementation fingerprint differs from the pinned verifier implementation"
            )

        remote_receipt_core = {
            "schema": VALIDATION_RECEIPT_SCHEMA,
            "validator_peer_id": endpoint.validator_peer_id,
            "validator_dns_identity": endpoint.server_dns_identity,
            "validator_certificate_sha256": peer_certificate_sha256,
            "worker_peer_id": endpoint.worker_peer_id,
            "worker_host_id": endpoint.worker_host_id,
            "worker_implementation_fingerprint": endpoint.worker_implementation_fingerprint,
            "request_sha256": request["request_sha256"],
            "response_sha256": response["response_sha256"],
            "verifier_implementation_fingerprint": remote_implementation,
            "validation_digest": report["verification_digest"],
            "validation": dict(report["verification"]),
        }
        remote_receipt_digest = _digest(remote_receipt_core)
        remote_receipt = {
            **remote_receipt_core,
            "remote_validator_receipt_digest": remote_receipt_digest,
        }

        ack_deadline = time.monotonic() + min(endpoint.timeout_seconds, 5.0)
        while requests.pending_sequences() and time.monotonic() < ack_deadline:
            acknowledged.extend(requests.process_ack())
            time.sleep(_SERVICE_POLL_SECONDS)
        if requests.pending_sequences() or request_sequence not in acknowledged:
            raise TimeoutError("remote validation request was not acknowledged")
        return {
            "valid": True,
            "verification": dict(report["verification"]),
            "verification_digest": report["verification_digest"],
            "remote_validator_receipt": remote_receipt,
            "remote_validator_receipt_digest": remote_receipt_digest,
        }
    except (TimeoutError, OSError, ssl.SSLError) as exc:
        raise PreparedResultValidationError(f"remote prepared-result validation transport failed: {exc}") from exc
    finally:
        if transport is not None:
            transport.close()


class PreparedResultValidatorService:
    """A verifier-only service with no E-CPU claim-store or quorum-publication capability."""

    def __init__(
        self,
        *,
        validator_peer_id: str,
        validator_dns_identity: str,
        expected_worker_peer_id: str,
        expected_worker_dns_identity: str,
        expected_worker_host_id: str,
        expected_worker_implementation_fingerprint: str,
        listener: socket.socket,
        tls_context: ssl.SSLContext,
        certificate_path: Path,
        handshake_timeout: float = 5.0,
        poll_interval: float = _SERVICE_POLL_SECONDS,
    ) -> None:
        self.validator_peer_id = _require_text(validator_peer_id, "validator_peer_id")
        self.validator_dns_identity = _require_text(validator_dns_identity, "validator_dns_identity")
        self.expected_worker_peer_id = _require_text(expected_worker_peer_id, "expected_worker_peer_id")
        self.expected_worker_dns_identity = _require_text(
            expected_worker_dns_identity,
            "expected_worker_dns_identity",
        )
        self.expected_worker_host_id = _require_text(
            expected_worker_host_id,
            "expected_worker_host_id",
        )
        self.expected_worker_implementation_fingerprint = _require_digest(
            expected_worker_implementation_fingerprint,
            "expected_worker_implementation_fingerprint",
        )
        if not isinstance(listener, socket.socket):
            raise TypeError("remote validator listener must be a socket.socket")
        if not isinstance(tls_context, ssl.SSLContext):
            raise TypeError("remote validator service requires an SSL server context")
        if not isinstance(certificate_path, Path) or not certificate_path.is_file():
            raise ValueError("remote validator certificate path must identify a PEM certificate")
        if handshake_timeout <= 0 or poll_interval <= 0:
            raise ValueError("remote validator service timing values must be positive")
        self.listener = listener
        self.tls_context = tls_context
        self.certificate_path = certificate_path
        self.handshake_timeout = float(handshake_timeout)
        self.poll_interval = float(poll_interval)
        self._stopped = False
        self.accepted_connections = 0
        self.rejected_connections = 0
        certificate_der = ssl.PEM_cert_to_DER_cert(certificate_path.read_text(encoding="ascii"))
        self.server_certificate_sha256 = _bytes_digest(certificate_der)
        self.verifier_fingerprint = verifier_implementation_fingerprint()

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.listener.getsockname()[:2]
        return str(host), int(port)

    def stop(self) -> None:
        self._stopped = True
        try:
            self.listener.close()
        except OSError:
            pass

    def serve_forever(self) -> None:
        while not self._stopped:
            try:
                transport = accept_mutual_tls(
                    self.listener,
                    self.validator_peer_id,
                    self.expected_worker_peer_id,
                    self.tls_context,
                    expected_peer_dns=self.expected_worker_dns_identity,
                    handshake_timeout=self.handshake_timeout,
                    max_frame_size=_MAX_FRAME_BYTES,
                )
            except Exception:
                if self._stopped:
                    break
                self.rejected_connections += 1
                time.sleep(0.02)
                continue
            self.accepted_connections += 1
            try:
                self._serve_connection(transport)
            except Exception:
                # A dropped/invalid client exchange is isolated to that
                # connection; it must not take down the verifier service.
                self.rejected_connections += 1
            finally:
                transport.close()

    def _serve_connection(self, transport: SocketTransport) -> None:
        policy = ReliabilityPolicy(lease_ticks=1, max_attempts=8, window_size=2)
        incoming = ReliableChannel(
            transport,
            self.validator_peer_id,
            self.validator_peer_id,
            REQUEST_CHANNEL,
            policy,
            peer=self.expected_worker_peer_id,
        )
        outgoing = ReliableChannel(
            transport,
            self.validator_peer_id,
            self.expected_worker_peer_id,
            RESPONSE_CHANNEL,
            policy,
            peer=self.expected_worker_peer_id,
        )
        holder: dict[str, Any] = {}

        def verify_request(sequence: int, payload: Any) -> None:
            try:
                report = self._verify_request(payload)
                holder["response"] = report
            except Exception as exc:
                request_id = payload.get("request_id") if isinstance(payload, Mapping) else ""
                request_sha256 = payload.get("request_sha256") if isinstance(payload, Mapping) else ""
                core = {
                    "schema": RESPONSE_SCHEMA,
                    "request_id": request_id if isinstance(request_id, str) else "",
                    "request_sha256": request_sha256 if isinstance(request_sha256, str) else "",
                    "validator_peer_id": self.validator_peer_id,
                    "validator_dns_identity": self.validator_dns_identity,
                    "worker_peer_id": self.expected_worker_peer_id,
                    "worker_host_id": self.expected_worker_host_id,
                    "worker_implementation_fingerprint": self.expected_worker_implementation_fingerprint,
                    "status": "rejected",
                    "validation_report": None,
                    "verifier_implementation_fingerprint": self.verifier_fingerprint,
                    "rejection": f"{type(exc).__name__}: {exc}",
                }
                holder["response"] = {**core, "response_sha256": _digest(core)}

        deadline = time.monotonic() + _SERVICE_REQUEST_TIMEOUT_SECONDS
        received = None
        while received is None and time.monotonic() < deadline:
            received = incoming.receive(commit=verify_request)
            if received is None:
                time.sleep(self.poll_interval)
        if received is None or "response" not in holder:
            raise PreparedResultValidationError("remote validator request did not complete")
        outgoing.send(holder["response"])
        ack_deadline = time.monotonic() + _SERVICE_RESPONSE_ACK_TIMEOUT_SECONDS
        while outgoing.pending_sequences() and time.monotonic() < ack_deadline:
            outgoing.process_ack()
            time.sleep(self.poll_interval)
        if outgoing.pending_sequences():
            raise TimeoutError("remote validator response was not acknowledged")

    def _verify_request(self, payload: Any) -> dict[str, Any]:
        expected_fields = {
            "schema",
            "request_id",
            "validator_peer_id",
            "worker_peer_id",
            "envelope",
            "prepared_record",
            "request_sha256",
        }
        request = _exact_fields(payload, expected_fields, "remote validation request")
        core = {key: value for key, value in request.items() if key != "request_sha256"}
        request_digest = _require_digest(request["request_sha256"], "request_sha256")
        if (
            request["schema"] != REQUEST_SCHEMA
            or request["validator_peer_id"] != self.validator_peer_id
            or request["worker_peer_id"] != self.expected_worker_peer_id
            or _digest(core) != request_digest
        ):
            raise PreparedResultValidationError("remote validation request identity or digest mismatch")
        prepared = request["prepared_record"]
        if not isinstance(prepared, Mapping):
            raise PreparedResultValidationError("remote validation request is missing its prepared record")
        if (
            prepared.get("owner_peer_id") != self.expected_worker_peer_id
            or prepared.get("owner_host_id") != self.expected_worker_host_id
            or prepared.get("implementation_fingerprint")
            != self.expected_worker_implementation_fingerprint
        ):
            raise PreparedResultValidationError(
                "prepared claim assignment does not match the authenticated worker peer/Host/implementation"
            )
        if not isinstance(prepared, Mapping) or not isinstance(request["envelope"], Mapping):
            raise PreparedResultValidationError("remote validation request is missing its envelope or prepared record")
        if len(_canonical(request)) > _MAX_REQUEST_BYTES:
            raise PreparedResultValidationError("remote validation request exceeds its finite byte bound")
        request_id_expected = _digest(
            {
                "schema": "ifs.psc.remote-validator-request-identity.v1",
                "validator_peer_id": self.validator_peer_id,
                "worker_peer_id": self.expected_worker_peer_id,
                "input_claim_id": prepared.get("input_claim_id"),
                "assignment_epoch": prepared.get("assignment_epoch"),
                "prepared_sha256": prepared.get("prepared_sha256"),
            }
        )
        if request["request_id"] != request_id_expected:
            raise PreparedResultValidationError("remote validation request ID is not content-bound")

        node = shutil.which("node")
        if node is None:
            raise PreparedResultValidationError("remote validator process requires Node.js")
        script = Path(__file__).with_name("verify_prepared_result.mjs")
        if not script.is_file():
            raise PreparedResultValidationError("remote verifier implementation file is missing")
        with tempfile.TemporaryDirectory(prefix="ifs-psc-validator-") as temporary_directory:
            root = Path(temporary_directory)
            envelope_path = root / "envelope.json"
            prepared_path = root / "prepared.json"
            envelope_path.write_bytes(_canonical(request["envelope"]) + b"\n")
            prepared_path.write_bytes(_canonical(prepared) + b"\n")
            completed = subprocess.run(
                [
                    node,
                    str(script),
                    "--envelope",
                    str(envelope_path),
                    "--prepared",
                    str(prepared_path),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "unknown verifier failure"
            raise PreparedResultValidationError(f"independent Node validator rejected the prepared result: {message}")
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise PreparedResultValidationError("independent Node validator returned malformed JSON") from exc
        if (
            not isinstance(report, Mapping)
            or report.get("valid") is not True
            or not isinstance(report.get("verification"), Mapping)
            or report.get("verification_digest") != _digest({
                key: value for key, value in report["verification"].items()
                if key != "verification_digest"
            })
        ):
            raise PreparedResultValidationError("independent Node validator returned an invalid receipt")

        core = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "request_sha256": request_digest,
            "validator_peer_id": self.validator_peer_id,
            "validator_dns_identity": self.validator_dns_identity,
            "worker_peer_id": self.expected_worker_peer_id,
            "worker_host_id": self.expected_worker_host_id,
            "worker_implementation_fingerprint": self.expected_worker_implementation_fingerprint,
            "status": "verified",
            "validation_report": dict(report),
            "verifier_implementation_fingerprint": self.verifier_fingerprint,
            "rejection": None,
        }
        return {**core, "response_sha256": _digest(core)}


def build_service_from_arguments(arguments: list[str]) -> PreparedResultValidatorService:
    parser = argparse.ArgumentParser(description="Run a verifier-only mutual-TLS PSC validation peer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--validator-peer-id", required=True)
    parser.add_argument("--validator-dns-identity", required=True)
    parser.add_argument("--expected-worker-peer-id", required=True)
    parser.add_argument("--expected-worker-dns-identity", required=True)
    parser.add_argument("--expected-worker-host-id", required=True)
    parser.add_argument("--expected-worker-implementation-fingerprint", required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--client-ca", type=Path, required=True)
    selected = parser.parse_args(arguments)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(selected.certificate), str(selected.private_key))
    context.load_verify_locations(cafile=str(selected.client_ca))
    context.verify_mode = ssl.CERT_REQUIRED
    listener = SocketTransport.listen(selected.host, selected.port)
    return PreparedResultValidatorService(
        validator_peer_id=selected.validator_peer_id,
        validator_dns_identity=selected.validator_dns_identity,
        expected_worker_peer_id=selected.expected_worker_peer_id,
        expected_worker_dns_identity=selected.expected_worker_dns_identity,
        expected_worker_host_id=selected.expected_worker_host_id,
        expected_worker_implementation_fingerprint=selected.expected_worker_implementation_fingerprint,
        listener=listener,
        tls_context=context,
        certificate_path=selected.certificate,
    )


if __name__ == "__main__":
    service = build_service_from_arguments(sys.argv[1:])
    host, port = service.address
    print(
        json.dumps(
            {
                "ready": True,
                "validator_peer_id": service.validator_peer_id,
                "validator_dns_identity": service.validator_dns_identity,
                "expected_worker_host_id": service.expected_worker_host_id,
                "expected_worker_implementation_fingerprint": service.expected_worker_implementation_fingerprint,
                "host": host,
                "port": port,
                "pid": os.getpid(),
                "server_certificate_sha256": service.server_certificate_sha256,
                "verifier_implementation_fingerprint": service.verifier_fingerprint,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        service.serve_forever()
    finally:
        service.stop()
