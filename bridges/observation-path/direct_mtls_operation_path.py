#!/usr/bin/env python3
"""Direct E-CPU mTLS operation path between independently hosted runners.

The workflow exchanges only public certificates and a signed listener
advertisement through Actions artifacts. The semantic operation and its
ReliableChannel ACK/receipt travel on the direct SocketTransport session.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from distributed_operation_path import (
    build_causal_handoff_witness,
    build_handoff_payload,
    validate_causal_handoff_witness,
)
from operation_spans import OperationSpanRecorder, validate_operation_span
from temporal_provenance import validate_temporal_frame

from mailcpu.mtls_transport import accept_mutual_tls, connect_mutual_tls
from mailcpu.reliability import ReliabilityPolicy, ReliableChannel
from mailcpu.socket_transport import SocketTransport
from mailcpu.temporal import (
    CausalStamp,
    ClockDomain,
    TemporalContext,
    TemporalProfile,
)

REPOSITORY = "Kier73/In-Formation-Space"
WORKFLOW_PATH = ".github/workflows/direct-mtls-operation-path.yml"
TAILSCALE_WORKFLOW_PATH = ".github/workflows/tailscale-mtls-operation-path.yml"
ALLOWED_WORKFLOW_PATHS = frozenset({WORKFLOW_PATH, TAILSCALE_WORKFLOW_PATH})
SIGNER_WORKFLOW = f"{REPOSITORY}/{WORKFLOW_PATH}"
SOURCE_REF = "refs/heads/main"
CERT_PREDICATE_TYPE = (
    "https://kier73.github.io/in-formation-space/direct-mtls-host-certificate/v1"
)
RECORD_PREDICATE_TYPE = (
    "https://kier73.github.io/in-formation-space/direct-mtls-host-operation-record/v1"
)
REPORT_PREDICATE_TYPE = (
    "https://kier73.github.io/in-formation-space/direct-mtls-reconstruction-report/v1"
)
CERT_PREDICATE_SCHEMA = "in-formation.direct-mtls-host-certificate-predicate/0.1"
RECORD_PREDICATE_SCHEMA = "in-formation.direct-mtls-host-record-predicate/0.1"
REPORT_PREDICATE_SCHEMA = "in-formation.direct-mtls-report-predicate/0.1"
CERTIFICATE_SCHEMA = "in-formation.direct-mtls-host-certificate/0.1"
ENDPOINT_SCHEMA = "in-formation.direct-mtls-endpoint-advertisement/0.1"
HANDOFF_SCHEMA = "in-formation.direct-mtls-handoff-envelope/0.1"
RECEIPT_SCHEMA = "in-formation.direct-mtls-receiver-receipt/0.1"
RECORD_SCHEMA = "in-formation.direct-mtls-host-record/0.1"
REPORT_SCHEMA = "in-formation.direct-mtls-reconstruction-report/0.1"
DATA_CHANNEL = "ihp002/direct-operation/v1"
RECEIPT_CHANNEL = "ihp002/receiver-receipt/v1"
LISTEN_PORT = 41763
GH_MIN_VERSION = (2, 103, 3)


class DirectMTLSError(ValueError):
    """A direct-mTLS bootstrap, transport, signature, or reconstruction check failed."""


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DirectMTLSError(f"value is not canonical finite JSON: {error}") from error


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_object(value: object) -> str:
    return digest_bytes(canonical(value))


def file_digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value: object, *, durable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical(value) + b"\n"
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        if durable:
            os.fsync(stream.fileno())


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DirectMTLSError(f"cannot read evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise DirectMTLSError(f"evidence {path} must be a JSON object")
    return value


def _env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not isinstance(value, str) or not value.strip():
        raise DirectMTLSError(f"required runner environment field {name} is missing")
    return value.strip()


def _workflow_path(workflow_ref: str) -> str:
    """Return an explicitly allowed workflow path from a main-branch workflow ref."""
    prefix = f"{REPOSITORY}/"
    suffix = f"@{SOURCE_REF}"
    if not isinstance(workflow_ref, str) or not workflow_ref.startswith(prefix) or not workflow_ref.endswith(suffix):
        raise DirectMTLSError("runner workflow identity is not pinned to the repository main branch")
    path = workflow_ref[len(prefix):-len(suffix)]
    if path not in ALLOWED_WORKFLOW_PATHS:
        raise DirectMTLSError("runner workflow path is not in the direct-mTLS allowlist")
    return path


def _signer_workflow_from_environment() -> str:
    workflow_ref = _env(os.environ, "GITHUB_WORKFLOW_REF")
    return f"{REPOSITORY}/{_workflow_path(workflow_ref)}"


def host_metadata(role: str, env: Mapping[str, str] | None = None) -> dict[str, str]:
    selected = os.environ if env is None else env
    if role not in {"client_host", "server_host", "verifier_host"}:
        raise DirectMTLSError("unsupported direct-mTLS host role")
    fields = {
        "role": role,
        "repository": _env(selected, "GITHUB_REPOSITORY"),
        "run_id": _env(selected, "GITHUB_RUN_ID"),
        "run_attempt": _env(selected, "GITHUB_RUN_ATTEMPT"),
        "run_number": _env(selected, "GITHUB_RUN_NUMBER"),
        "workflow_ref": _env(selected, "GITHUB_WORKFLOW_REF"),
        "workflow_sha": _env(selected, "GITHUB_WORKFLOW_SHA"),
        "git_ref": _env(selected, "GITHUB_REF"),
        "git_sha": _env(selected, "GITHUB_SHA"),
        "job": _env(selected, "GITHUB_JOB"),
        "runner_name": _env(selected, "RUNNER_NAME"),
        "runner_os": _env(selected, "RUNNER_OS"),
        "runner_arch": _env(selected, "RUNNER_ARCH"),
        "runner_environment": _env(selected, "RUNNER_ENVIRONMENT"),
    }
    if fields["repository"] != REPOSITORY:
        raise DirectMTLSError("runner repository does not match the pinned repository")
    _workflow_path(fields["workflow_ref"])
    if fields["git_ref"] != SOURCE_REF:
        raise DirectMTLSError("direct-mTLS evidence must be produced from refs/heads/main")
    if fields["runner_environment"] != "github-hosted":
        raise DirectMTLSError("direct-mTLS experiment requires GitHub-hosted runners")
    if fields["job"] != role:
        raise DirectMTLSError(f"expected job {role!r}, received {fields['job']!r}")
    fields["actor_id"] = (
        f"{fields['repository']}#run-{fields['run_id']}.attempt-{fields['run_attempt']}."
        f"{role}.{fields['runner_name']}"
    )
    fields["clock_segment_id"] = "0"
    return fields


def _validate_host_metadata(value: object, role: str) -> dict[str, str]:
    expected = {
        "role", "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha", "job",
        "runner_name", "runner_os", "runner_arch", "runner_environment",
        "actor_id", "clock_segment_id",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise DirectMTLSError(f"{role} host metadata fields are incomplete or unexpected")
    if any(not isinstance(value[key], str) or not value[key] for key in expected):
        raise DirectMTLSError(f"{role} host metadata values must be non-empty strings")
    if value["role"] != role or value["job"] != role:
        raise DirectMTLSError(f"host metadata does not identify the {role} job")
    if value["repository"] != REPOSITORY:
        raise DirectMTLSError("host metadata repository identity is not pinned")
    _workflow_path(value["workflow_ref"])
    if value["git_ref"] != SOURCE_REF or value["runner_environment"] != "github-hosted":
        raise DirectMTLSError("host metadata ref or runner environment is not permitted")
    return dict(value)


def _identity_name(role: str, run_id: str) -> str:
    label = "client" if role == "client_host" else "server"
    return f"ihp002-{label}-{run_id}.internal"


def generate_identity(role: str, directory: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    host = host_metadata(role, env)
    directory.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, _identity_name(role, host["run_id"]))
    ])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(_identity_name(role, host["run_id"]))]),
            critical=True,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(key, algorithm=None)
    )
    cert_path = directory / f"{'client' if role == 'client_host' else 'server'}-cert.pem"
    key_path = directory / f"{'client' if role == 'client_host' else 'server'}-key.pem"
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    os.chmod(key_path, 0o600)
    return {
        "host": host,
        "certificate_path": cert_path,
        "private_key_path": key_path,
        "certificate_pem": cert_pem.decode("ascii"),
        "certificate_sha256": digest_bytes(certificate.public_bytes(serialization.Encoding.DER)),
        "dns_identity": _identity_name(role, host["run_id"]),
    }


def _load_certificate(path: Path) -> x509.Certificate:
    try:
        return x509.load_pem_x509_certificate(path.read_bytes())
    except (OSError, ValueError) as error:
        raise DirectMTLSError(f"certificate cannot be loaded: {path}") from error


def certificate_sha256(path: Path) -> str:
    return digest_bytes(_load_certificate(path).public_bytes(serialization.Encoding.DER))


def _signed_document(core: Mapping[str, Any], private_key_path: Path) -> dict[str, Any]:
    try:
        key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    except (OSError, ValueError) as error:
        raise DirectMTLSError("signing private key cannot be loaded") from error
    if not isinstance(key, Ed25519PrivateKey):
        raise DirectMTLSError("receipt signer must be an Ed25519 private key")
    signature = key.sign(canonical(dict(core)))
    return {
        "core": dict(core),
        "signature": base64.b64encode(signature).decode("ascii"),
        "signed_digest": digest_object(core),
    }


def _verify_signed_document(
    signed: Mapping[str, Any],
    certificate_path: Path,
    *,
    expected_digest: str | None = None,
) -> dict[str, Any]:
    if not isinstance(signed, Mapping) or set(signed) != {"core", "signature", "signed_digest"}:
        raise DirectMTLSError("signed document fields are incomplete or unexpected")
    core = signed["core"]
    if not isinstance(core, Mapping) or signed["signed_digest"] != digest_object(core):
        raise DirectMTLSError("signed document digest does not match its core")
    if expected_digest is not None and signed["signed_digest"] != expected_digest:
        raise DirectMTLSError("signed document digest differs from expected commitment")
    try:
        signature = base64.b64decode(str(signed["signature"]), validate=True)
        public_key = _load_certificate(certificate_path).public_key()
        if not hasattr(public_key, "verify"):
            raise DirectMTLSError("pinned certificate has no verification key")
        public_key.verify(signature, canonical(dict(core)))
    except DirectMTLSError:
        raise
    except Exception as error:
        raise DirectMTLSError("Ed25519 signature verification failed") from error
    return dict(core)


def write_certificate_predicate(
    certificate_path: Path,
    output_path: Path,
    role: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    host = host_metadata(role, env)
    certificate = _load_certificate(certificate_path)
    dns = _identity_name(role, host["run_id"])
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    if dns not in san.get_values_for_type(x509.DNSName):
        raise DirectMTLSError("certificate DNS SAN differs from its role/run identity")
    predicate = {
        "schema": CERT_PREDICATE_SCHEMA,
        "role": role,
        "host": host,
        "certificate_sha256": certificate_sha256(certificate_path),
        "dns_identity": dns,
    }
    write_json(output_path, predicate)
    return predicate


def _gh_version(gh: str) -> tuple[int, int, int]:
    result = subprocess.run([gh, "--version"], check=True, capture_output=True, text=True)
    import re
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match:
        raise DirectMTLSError("cannot parse GitHub CLI version")
    return tuple(int(part) for part in match.groups())


def _attestation_command(
    path: Path,
    predicate_type: str,
    gh: str,
    *,
    signer_workflow: str = SIGNER_WORKFLOW,
) -> list[str]:
    return [
        gh, "attestation", "verify", str(path),
        "--repo", REPOSITORY,
        "--predicate-type", predicate_type,
        "--signer-workflow", signer_workflow,
        "--source-ref", SOURCE_REF,
        "--deny-self-hosted-runners",
        "--format", "json",
    ]


def _find_verified_statement(results: Any, artifact_digest: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(results, list):
        raise DirectMTLSError("GitHub CLI attestation output must be a JSON array")
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        verification = item.get("verificationResult")
        if not isinstance(verification, Mapping):
            continue
        statement = verification.get("statement")
        if not isinstance(statement, Mapping):
            continue
        subject_match = any(
            isinstance(subject, Mapping)
            and isinstance(subject.get("digest"), Mapping)
            and subject["digest"].get("sha256") == artifact_digest
            for subject in statement.get("subject", [])
        )
        if subject_match:
            matched.append((dict(statement), dict(verification)))
    if not matched:
        raise DirectMTLSError("no valid attestation subject matches the exact artifact bytes")
    for statement, _ in matched:
        if not isinstance(statement.get("predicate"), Mapping):
            raise DirectMTLSError("verified attestation has no predicate object")
    return matched[0]


def verify_artifact_attestation(
    artifact_path: Path,
    predicate_type: str,
    *,
    expected_predicate: Mapping[str, Any] | None = None,
    gh: str = "gh",
) -> dict[str, Any]:
    if _gh_version(gh) < GH_MIN_VERSION:
        raise DirectMTLSError("GitHub CLI 2.103.3 or newer is required for signer-workflow verification")
    artifact_digest = file_digest(artifact_path)
    signer_workflow = _signer_workflow_from_environment()
    try:
        completed = subprocess.run(
            _attestation_command(
                artifact_path, predicate_type, gh, signer_workflow=signer_workflow
            ),
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        results = json.loads(completed.stdout)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() if error.stderr else str(error)
        raise DirectMTLSError(f"GitHub attestation verification failed: {detail}") from error
    except json.JSONDecodeError as error:
        raise DirectMTLSError("GitHub CLI did not return valid attestation JSON") from error
    statement, verified = _find_verified_statement(results, artifact_digest)
    if statement.get("predicateType") != predicate_type:
        raise DirectMTLSError("attestation predicate type is not the pinned type")
    predicate = statement.get("predicate")
    if expected_predicate is not None and dict(predicate) != dict(expected_predicate):
        raise DirectMTLSError("signed attestation predicate differs from the expected evidence")
    signature = verified.get("signature")
    certificate_present = (
        isinstance(signature, Mapping)
        and isinstance(signature.get("certificate"), Mapping)
    )
    if not certificate_present:
        raise DirectMTLSError("verified attestation has no signing certificate")
    return {
        "verified": True,
        "subject_sha256": artifact_digest,
        "predicate_type": predicate_type,
        "signer_workflow": signer_workflow,
        "source_ref": SOURCE_REF,
        "self_hosted_runners_denied": True,
        "predicate": dict(predicate),
        "verified_timestamp_count": len(verified.get("verifiedTimestamps", [])),
    }


def _poll_download_artifact(
    artifact_name: str,
    destination: Path,
    *,
    timeout_seconds: float,
    gh: str = "gh",
) -> Path:
    run_id = _env(os.environ, "GITHUB_RUN_ID")
    repository = _env(os.environ, "GITHUB_REPOSITORY")
    deadline = time.monotonic() + timeout_seconds
    last_error = "artifact has not appeared yet"
    while time.monotonic() < deadline:
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                gh, "run", "download", run_id,
                "--repo", repository,
                "--name", artifact_name,
                "--dir", str(destination),
            ],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            check=False,
        )
        if completed.returncode == 0:
            files = [item for item in destination.rglob("*") if item.is_file()]
            if files:
                return destination
        last_error = (completed.stderr or completed.stdout or "artifact download returned no files").strip()
        time.sleep(2.0)
    raise DirectMTLSError(f"timed out waiting for artifact {artifact_name!r}: {last_error[-1000:]}")


def _require_run_match(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    for field in ("repository", "run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_ref", "git_sha"):
        if left.get(field) != right.get(field):
            raise DirectMTLSError(f"host records differ in shared run field {field}")
    if left.get("actor_id") == right.get("actor_id") or left.get("role") == right.get("role"):
        raise DirectMTLSError("direct operation requires distinct host actors and roles")


def _validate_certificate_predicate(
    predicate: Mapping[str, Any],
    certificate_path: Path,
    role: str,
    expected_run_id: str,
    expected_attempt: str,
) -> dict[str, Any]:
    if set(predicate) != {"schema", "role", "host", "certificate_sha256", "dns_identity"}:
        raise DirectMTLSError("certificate predicate fields are incomplete or unexpected")
    if predicate.get("schema") != CERT_PREDICATE_SCHEMA or predicate.get("role") != role:
        raise DirectMTLSError("certificate predicate schema or role is invalid")
    host = _validate_host_metadata(predicate.get("host"), role)
    if host["run_id"] != expected_run_id or host["run_attempt"] != expected_attempt:
        raise DirectMTLSError("certificate belongs to another workflow run or attempt")
    if predicate.get("certificate_sha256") != certificate_sha256(certificate_path):
        raise DirectMTLSError("certificate predicate digest does not match its exact certificate")
    if predicate.get("dns_identity") != _identity_name(role, expected_run_id):
        raise DirectMTLSError("certificate predicate DNS identity is not the role/run identity")
    return dict(predicate)


def _validate_record_predicate(
    predicate: Mapping[str, Any],
    record_path: Path,
    record: Mapping[str, Any],
    role: str,
) -> dict[str, Any]:
    expected_fields = {
        "schema", "role", "host", "record_sha256",
        "record_digest", "certificate_sha256", "status", "path_id",
    }
    if set(predicate) != expected_fields:
        raise DirectMTLSError("host record predicate fields are incomplete or unexpected")
    if predicate.get("schema") != RECORD_PREDICATE_SCHEMA or predicate.get("role") != role:
        raise DirectMTLSError("host record predicate schema or role is invalid")
    host = _validate_host_metadata(predicate.get("host"), role)
    if host != record.get("host"):
        raise DirectMTLSError("record predicate host differs from the record host")
    if predicate.get("record_sha256") != file_digest(record_path):
        raise DirectMTLSError("record predicate does not bind the exact record bytes")
    if predicate.get("record_digest") != record.get("record_digest"):
        raise DirectMTLSError("record predicate digest differs from the reconstructed record")
    if predicate.get("certificate_sha256") != record.get("certificate_sha256"):
        raise DirectMTLSError("record predicate certificate fingerprint differs from the record")
    if predicate.get("status") != record.get("status"):
        raise DirectMTLSError("record predicate status differs from the record")
    expected_path = f"run-{host['run_id']}-ihp002-direct-mtls"
    if predicate.get("path_id") != expected_path:
        raise DirectMTLSError("record predicate path ID is not bound to the current run")
    return dict(predicate)


def _context(host: Mapping[str, Any]) -> TemporalContext:
    return TemporalContext(
        str(host["actor_id"]),
        TemporalProfile(frozenset({ClockDomain.MONOTONIC, ClockDomain.CAUSAL})),
        segment=0,
    )


def _recorder(host: Mapping[str, Any], context: TemporalContext) -> OperationSpanRecorder:
    return OperationSpanRecorder(
        clock_actor_id=str(host["actor_id"]),
        clock_segment_id="0",
        clock_ns=lambda: context.monotonic_reading().elapsed_ns,
    )


def _local_work(label: str) -> str:
    value = label.encode("utf-8")
    for counter in range(384):
        value = hashlib.sha256(value + counter.to_bytes(4, "big")).digest()
    return value.hex()


def _server_context(cert_path: Path, key_path: Path, peer_cert_path: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert_path), str(key_path))
    context.load_verify_locations(cafile=str(peer_cert_path))
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _client_context(cert_path: Path, key_path: Path, peer_cert_path: Path) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(peer_cert_path))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert_path), str(key_path))
    return context


def _peer_certificate_sha256(transport: SocketTransport) -> str:
    if not isinstance(transport.socket, ssl.SSLSocket):
        raise DirectMTLSError("E-CPU SocketTransport is not backed by an authenticated TLS socket")
    certificate = transport.socket.getpeercert(binary_form=True)
    if not certificate:
        raise DirectMTLSError("TLS session exposes no peer certificate")
    return digest_bytes(certificate)


def _verify_handoff_envelope(
    signed: Mapping[str, Any],
    client_cert_path: Path,
    expected_sequence: int,
) -> dict[str, Any]:
    core = _verify_signed_document(signed, client_cert_path)
    expected_fields = {
        "schema", "path_id", "attempt_id", "channel_id", "message_sequence",
        "sender_host", "sender_cert_sha256", "operation_span",
        "sender_completion_frame", "handoff_payload",
    }
    if set(core) != expected_fields or core["schema"] != HANDOFF_SCHEMA:
        raise DirectMTLSError("signed handoff envelope fields or schema are invalid")
    sender_host = _validate_host_metadata(core["sender_host"], "client_host")
    span = validate_operation_span(core["operation_span"])
    frame = validate_temporal_frame(core["sender_completion_frame"])
    if span["clock_actor_id"] != sender_host["actor_id"] or span["attempt_id"] != core["attempt_id"]:
        raise DirectMTLSError("sender operation span identity does not match its host/attempt")
    if frame["actor_id"] != sender_host["actor_id"] or frame["monotonic"] is None:
        raise DirectMTLSError("sender completion frame identity or monotonic coordinate is invalid")
    if frame["monotonic"]["elapsed_ns"] < span["monotonic_end_ns"]:
        raise DirectMTLSError("sender completion frame predates its operation span")
    payload = build_handoff_payload(
        path_id=str(core["path_id"]),
        attempt_id=str(core["attempt_id"]),
        predecessor_span_digest=span["span_digest"],
        sender_completion_frame=frame,
    )
    if payload != core["handoff_payload"]:
        raise DirectMTLSError("signed handoff payload cannot be independently reconstructed")
    if core["channel_id"] != DATA_CHANNEL or core["message_sequence"] != expected_sequence:
        raise DirectMTLSError("handoff channel or sequence differs from the actual ReliableChannel delivery")
    if core["sender_cert_sha256"] != certificate_sha256(client_cert_path):
        raise DirectMTLSError("sender certificate fingerprint differs from its attested certificate")
    if core["path_id"] != f"run-{sender_host['run_id']}-ihp002-direct-mtls":
        raise DirectMTLSError("handoff path ID does not match the current run")
    return dict(core)


def _load_signed_endpoint(
    endpoint_path: Path,
    server_cert_path: Path,
) -> tuple[dict[str, Any], str]:
    signed_endpoint = read_json(endpoint_path)
    core = _verify_endpoint_advertisement(signed_endpoint, server_cert_path)
    return core, digest_object(signed_endpoint)


def _verify_endpoint_advertisement(
    endpoint: Mapping[str, Any],
    server_cert_path: Path,
) -> dict[str, Any]:
    core = _verify_signed_document(endpoint, server_cert_path)
    expected = {
        "schema", "path_id", "run_id", "run_attempt", "server_host",
        "host", "port", "dns_identity", "server_cert_sha256",
        "client_actor_id", "client_cert_sha256",
    }
    if set(core) != expected or core["schema"] != ENDPOINT_SCHEMA:
        raise DirectMTLSError("server endpoint advertisement fields or schema are invalid")
    host = _validate_host_metadata(core["server_host"], "server_host")
    if _workflow_path(host["workflow_ref"]) == TAILSCALE_WORKFLOW_PATH:
        _validate_tailscale_ipv4(core.get("host"))
    if (
        core["run_id"] != host["run_id"]
        or core["run_attempt"] != host["run_attempt"]
        or core["path_id"] != f"run-{host['run_id']}-ihp002-direct-mtls"
        or core["server_cert_sha256"] != certificate_sha256(server_cert_path)
        or core["dns_identity"] != _identity_name("server_host", host["run_id"])
        or not isinstance(core["host"], str)
        or not core["host"]
        or not isinstance(core["port"], int)
        or isinstance(core["port"], bool)
        or not 1 <= core["port"] <= 65535
    ):
        raise DirectMTLSError("server endpoint advertisement does not match its signer")
    return dict(core)


def _validate_tailscale_ipv4(value: object) -> str:
    """Validate and normalize an endpoint inside Tailscale's CGNAT IPv4 range."""
    if not isinstance(value, str) or not value:
        raise DirectMTLSError("Tailscale overlay address must be a non-empty IPv4 string")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise DirectMTLSError("Tailscale overlay address is not a valid IP address") from error
    if address.version != 4 or address not in ipaddress.ip_network("100.64.0.0/10"):
        raise DirectMTLSError("Tailscale overlay address must be inside 100.64.0.0/10")
    return str(address)


def prepare_client(directory: Path) -> dict[str, Any]:
    identity = generate_identity("client_host", directory)
    predicate = write_certificate_predicate(
        identity["certificate_path"],
        directory / "client-cert.predicate.json",
        "client_host",
    )
    return {
        "certificate_sha256": identity["certificate_sha256"],
        "dns_identity": identity["dns_identity"],
        "predicate": predicate,
    }


def prepare_server(
    directory: Path,
    *,
    gh: str = "gh",
    bootstrap_timeout: float = 180.0,
    advertise_host: str | None = None,
) -> dict[str, Any]:
    host = host_metadata("server_host")
    workflow_path = _workflow_path(host["workflow_ref"])
    if workflow_path == TAILSCALE_WORKFLOW_PATH and advertise_host is None:
        raise DirectMTLSError(
            "IHP-006 requires an explicit Tailscale overlay address; public-IP fallback is disabled"
        )
    peer_directory = directory / "peer-client"
    _poll_download_artifact("ihp002-client-bootstrap", peer_directory, timeout_seconds=bootstrap_timeout, gh=gh)
    client_cert_path = peer_directory / "client-cert.pem"
    client_predicate = read_json(peer_directory / "client-cert.predicate.json")
    client_attestation = verify_artifact_attestation(
        client_cert_path,
        CERT_PREDICATE_TYPE,
        expected_predicate=client_predicate,
        gh=gh,
    )
    _validate_certificate_predicate(
        client_predicate, client_cert_path, "client_host", host["run_id"], host["run_attempt"]
    )
    client_host = _validate_host_metadata(client_predicate.get("host"), "client_host")

    identity = generate_identity("server_host", directory)
    server_cert_path = identity["certificate_path"]
    server_key_path = identity["private_key_path"]
    cert_predicate = write_certificate_predicate(
        server_cert_path, directory / "server-cert.predicate.json", "server_host"
    )
    if advertise_host is not None:
        public_ip = _validate_tailscale_ipv4(advertise_host)
    else:
        try:
            with urllib.request.urlopen("https://api4.ipify.org", timeout=8.0) as response:
                public_ip = response.read(128).decode("ascii").strip()
        except Exception as error:
            raise DirectMTLSError(f"cannot discover runner public IPv4 address: {error}") from error
        if not public_ip or any(character not in "0123456789." for character in public_ip):
            raise DirectMTLSError("public IPv4 discovery returned an invalid address")

    endpoint_core = {
        "schema": ENDPOINT_SCHEMA,
        "path_id": f"run-{host['run_id']}-ihp002-direct-mtls",
        "run_id": host["run_id"],
        "run_attempt": host["run_attempt"],
        "server_host": host,
        "host": public_ip,
        "port": LISTEN_PORT,
        "dns_identity": identity["dns_identity"],
        "server_cert_sha256": identity["certificate_sha256"],
        "client_actor_id": client_host["actor_id"],
        "client_cert_sha256": client_predicate["certificate_sha256"],
    }
    signed_endpoint = _signed_document(endpoint_core, server_key_path)
    write_json(directory / "server-endpoint.json", signed_endpoint)
    return {
        "host": host,
        "client_host": client_host,
        "client_certificate_sha256": client_predicate["certificate_sha256"],
        "client_attestation": client_attestation,
        "server_certificate_sha256": identity["certificate_sha256"],
        "server_dns_identity": identity["dns_identity"],
        "public_ip": public_ip,
        "port": LISTEN_PORT,
        "certificate_predicate": cert_predicate,
    }


def _make_record(
    *,
    role: str,
    host: Mapping[str, Any],
    status: str,
    certificate_sha256_value: str,
    operation_span: Mapping[str, Any] | None = None,
    temporal_frame: Mapping[str, Any] | None = None,
    endpoint_digest: str | None = None,
    handoff_envelope: Mapping[str, Any] | None = None,
    received_envelope: Mapping[str, Any] | None = None,
    receiver_receipt: Mapping[str, Any] | None = None,
    peer_certificate_sha256: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    core = {
        "schema": RECORD_SCHEMA,
        "role": role,
        "status": status,
        "host": dict(host),
        "certificate_sha256": certificate_sha256_value,
        "operation_span": None if operation_span is None else dict(operation_span),
        "temporal_frame": None if temporal_frame is None else dict(temporal_frame),
        "endpoint_digest": endpoint_digest,
        "handoff_envelope": None if handoff_envelope is None else dict(handoff_envelope),
        "received_envelope": None if received_envelope is None else dict(received_envelope),
        "receiver_receipt": None if receiver_receipt is None else dict(receiver_receipt),
        "peer_certificate_sha256": peer_certificate_sha256,
        "error": error,
    }
    return {**core, "record_digest": digest_object(core)}


def _write_record(directory: Path, record: Mapping[str, Any]) -> Path:
    path = directory / f"{record['role']}-record.json"
    write_json(path, record, durable=True)
    return path


def serve(
    directory: Path,
    *,
    accept_timeout: float = 120.0,
    bind_host: str | None = None,
) -> dict[str, Any]:
    host = host_metadata("server_host")
    workflow_path = _workflow_path(host["workflow_ref"])
    if workflow_path == TAILSCALE_WORKFLOW_PATH:
        if bind_host is None:
            raise DirectMTLSError(
                "IHP-006 requires an explicit Tailscale bind address; wildcard binding is disabled"
            )
        listener_host = _validate_tailscale_ipv4(bind_host)
    else:
        if bind_host is not None:
            raise DirectMTLSError("custom bind addresses are reserved for the IHP-006 overlay workflow")
        listener_host = "0.0.0.0"
    client_cert_path = directory / "peer-client" / "client-cert.pem"
    server_cert_path = directory / "server-cert.pem"
    server_key_path = directory / "server-key.pem"
    endpoint = read_json(directory / "server-endpoint.json")
    endpoint_core = _verify_endpoint_advertisement(endpoint, server_cert_path)
    listener = SocketTransport.listen(listener_host, LISTEN_PORT)
    listener.settimeout(accept_timeout)
    transport: SocketTransport | None = None

    try:
        server_tls = _server_context(server_cert_path, server_key_path, client_cert_path)
        transport = accept_mutual_tls(
            listener,
            "server-host",
            "client-host",
            server_tls,
            expected_peer_dns=_identity_name("client_host", host["run_id"]),
            handshake_timeout=8.0,
        )
    except Exception as error:
        record = _make_record(
            role="server_host",
            host=host,
            status="direct_tcp_unavailable",
            certificate_sha256_value=certificate_sha256(server_cert_path),
            endpoint_digest=digest_object(endpoint),
            peer_certificate_sha256=None,
            error=f"{type(error).__name__}: {str(error)[:800]}",
        )
        path = _write_record(directory, record)
        return {"status": record["status"], "record_path": str(path), "error": record["error"]}
    finally:
        listener.close()

    try:
        peer_sha = _peer_certificate_sha256(transport)
        expected_client_sha = certificate_sha256(client_cert_path)
        if peer_sha != expected_client_sha or peer_sha != endpoint_core["client_cert_sha256"]:
            raise DirectMTLSError("TLS peer certificate differs from the attested client bootstrap certificate")

        context = _context(host)
        receiver_channel = ReliableChannel(
            transport,
            "server-host",
            "server-host",
            DATA_CHANNEL,
            ReliabilityPolicy(lease_ticks=2, max_attempts=4, window_size=4),
            peer="client-host",
        )
        committed: dict[str, Any] = {}

        def commit(sequence: int, envelope: Any) -> None:
            if not isinstance(envelope, Mapping):
                raise DirectMTLSError("ReliableChannel payload must be a signed handoff envelope")
            sender_core = _verify_handoff_envelope(envelope, client_cert_path, sequence)
            if sender_core["sender_cert_sha256"] != peer_sha:
                raise DirectMTLSError("signed handoff certificate fingerprint differs from TLS peer")
            sender_host = sender_core["sender_host"]
            if (
                endpoint_core["client_actor_id"] != sender_host["actor_id"]
                or endpoint_core["client_cert_sha256"] != sender_core["sender_cert_sha256"]
            ):
                raise DirectMTLSError("received handoff signer differs from the endpoint's pinned client")
            source_span = validate_operation_span(sender_core["operation_span"])
            sender_frame = validate_temporal_frame(sender_core["sender_completion_frame"])
            source_stamp = CausalStamp.from_dict(sender_frame["causal"])
            context.receive_causal_stamp(source_stamp)
            receiver_start = context.observe().to_dict()

            recorder = _recorder(host, context)
            attempt_id = str(sender_core["attempt_id"])
            recorder.measure(
                attempt_id=attempt_id,
                span_id="server-operation",
                operation_id="ihp002.server.receive-and-transform",
                operation=lambda: _local_work("ihp002-server-operation"),
                context={"role": "server_host", "channel": DATA_CHANNEL},
            )
            successor = recorder.spans[-1]
            witness = build_causal_handoff_witness(
                payload=sender_core["handoff_payload"],
                successor_span_digest=successor["span_digest"],
                channel_id=DATA_CHANNEL,
                message_sequence=sequence,
                received_sequence=sequence,
                receiver_start_frame=receiver_start,
            )
            validate_causal_handoff_witness(
                witness,
                predecessor_span=source_span,
                successor_span=successor,
            )
            receipt_core = {
                "schema": RECEIPT_SCHEMA,
                "path_id": sender_core["path_id"],
                "attempt_id": attempt_id,
                "channel_id": DATA_CHANNEL,
                "message_sequence": sequence,
                "sender_actor_id": sender_host["actor_id"],
                "receiver_actor_id": host["actor_id"],
                "sender_cert_sha256": sender_core["sender_cert_sha256"],
                "receiver_cert_sha256": certificate_sha256(server_cert_path),
                "sender_envelope_digest": envelope["signed_digest"],
                "predecessor_span_digest": source_span["span_digest"],
                "successor_span_digest": successor["span_digest"],
                "sender_completion_frame": sender_frame,
                "receiver_start_frame": receiver_start,
                "receiver_operation_span": successor,
                "handoff_witness": witness,
            }
            signed_receipt = _signed_document(receipt_core, server_key_path)
            record = _make_record(
                role="server_host",
                host=host,
                status="direct_mtls_verified",
                certificate_sha256_value=certificate_sha256(server_cert_path),
                operation_span=successor,
                temporal_frame=receiver_start,
                endpoint_digest=digest_object(endpoint),
                received_envelope=dict(envelope),
                receiver_receipt=signed_receipt,
                peer_certificate_sha256=peer_sha,
            )
            _write_record(directory, record)
            committed.update({
                "receipt": signed_receipt,
                "record": record,
                "source_span": source_span,
                "source_frame": sender_frame,
            })

        deadline = time.monotonic() + accept_timeout
        delivered = None
        while time.monotonic() < deadline:
            delivered = receiver_channel.receive(commit=commit)
            if delivered is not None:
                break
            time.sleep(0.005)
        if delivered is None or "receipt" not in committed:
            raise DirectMTLSError("authenticated TCP session delivered no reliable operation frame")

        receipt_sender = ReliableChannel(
            transport,
            "server-host",
            "client-host",
            RECEIPT_CHANNEL,
            ReliabilityPolicy(lease_ticks=2, max_attempts=4, window_size=4),
        )
        receipt_sequence = receipt_sender.send(committed["receipt"])
        if receipt_sequence != 1:
            raise DirectMTLSError("first signed receipt did not use ReliableChannel sequence one")
        _wait_for_ack(receipt_sender, (receipt_sequence,), timeout_seconds=12.0)

        record = dict(committed["record"])
        record_core = {key: value for key, value in record.items() if key != "record_digest"}
        record_core["status"] = "direct_mtls_verified"
        record_core["error"] = None
        record = {**record_core, "record_digest": digest_object(record_core)}
        path = _write_record(directory, record)
        return {
            "status": "direct_mtls_verified",
            "record_path": str(path),
            "peer_certificate_sha256": peer_sha,
            "message_sequence": delivered[0],
            "receipt_sequence": receipt_sequence,
        }
    except Exception as error:
        record = _make_record(
            role="server_host",
            host=host,
            status="direct_mtls_rejected",
            certificate_sha256_value=certificate_sha256(server_cert_path),
            endpoint_digest=digest_object(endpoint),
            peer_certificate_sha256=_peer_certificate_sha256(transport),
            error=f"{type(error).__name__}: {str(error)[:800]}",
        )
        path = _write_record(directory, record)
        return {"status": record["status"], "record_path": str(path), "error": record["error"]}
    finally:
        if transport is not None and not transport.closed:
            transport.close()


def _wait_for_ack(channel: ReliableChannel, expected: tuple[int, ...], *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    observed: set[int] = set()
    while time.monotonic() < deadline:
        observed.update(channel.process_ack())
        if set(expected).issubset(observed):
            return
        time.sleep(0.005)
    raise DirectMTLSError(f"timed out waiting for ReliableChannel ACKs {expected!r}")


def connect_and_send(
    directory: Path,
    *,
    connect_timeout_seconds: float = 100.0,
    gh: str = "gh",
) -> dict[str, Any]:
    host = host_metadata("client_host")
    server_directory = directory / "peer-server"
    _poll_download_artifact("ihp002-server-bootstrap", server_directory, timeout_seconds=connect_timeout_seconds, gh=gh)
    server_cert_path = server_directory / "server-cert.pem"
    server_predicate = read_json(server_directory / "server-cert.predicate.json")
    verify_artifact_attestation(
        server_cert_path,
        CERT_PREDICATE_TYPE,
        expected_predicate=server_predicate,
        gh=gh,
    )
    _validate_certificate_predicate(
        server_predicate, server_cert_path, "server_host", host["run_id"], host["run_attempt"]
    )
    server_host = _validate_host_metadata(server_predicate.get("host"), "server_host")
    endpoint, endpoint_digest = _load_signed_endpoint(
        server_directory / "server-endpoint.json",
        server_cert_path,
    )
    own_cert_path = directory / "client-cert.pem"
    own_key_path = directory / "client-key.pem"
    own_cert_sha = certificate_sha256(own_cert_path)
    if endpoint["client_actor_id"] != host["actor_id"] or endpoint["client_cert_sha256"] != own_cert_sha:
        raise DirectMTLSError("server endpoint was advertised for another client actor or certificate")

    context = _context(host)
    recorder = _recorder(host, context)
    attempt_id = f"run-{host['run_id']}-attempt-{host['run_attempt']}"
    recorder.measure(
        attempt_id=attempt_id,
        span_id="client-operation",
        operation_id="ihp002.client.prepare",
        operation=lambda: _local_work("ihp002-client-operation"),
        context={"role": "client_host", "channel": DATA_CHANNEL},
    )
    source_span = recorder.spans[-1]
    context.emit_causal_stamp()
    sender_frame = context.observe().to_dict()
    path_id = f"run-{host['run_id']}-ihp002-direct-mtls"
    handoff_payload = build_handoff_payload(
        path_id=path_id,
        attempt_id=attempt_id,
        predecessor_span_digest=source_span["span_digest"],
        sender_completion_frame=sender_frame,
    )
    envelope_core = {
        "schema": HANDOFF_SCHEMA,
        "path_id": path_id,
        "attempt_id": attempt_id,
        "channel_id": DATA_CHANNEL,
        "message_sequence": 1,
        "sender_host": host,
        "sender_cert_sha256": own_cert_sha,
        "operation_span": source_span,
        "sender_completion_frame": sender_frame,
        "handoff_payload": handoff_payload,
    }
    signed_envelope = _signed_document(envelope_core, own_key_path)
    deadline = time.monotonic() + connect_timeout_seconds
    transport: SocketTransport | None = None
    last_error = "connection has not been attempted"
    while time.monotonic() < deadline:
        try:
            transport = connect_mutual_tls(
                str(endpoint["host"]),
                int(endpoint["port"]),
                "client-host",
                "server-host",
                _client_context(own_cert_path, own_key_path, server_cert_path),
                server_hostname=str(endpoint["dns_identity"]),
                timeout=4.0,
                handshake_timeout=4.0,
            )
            break
        except Exception as error:
            last_error = f"{type(error).__name__}: {str(error)[:600]}"
            time.sleep(2.0)

    if transport is None:
        record = _make_record(
            role="client_host",
            host=host,
            status="direct_tcp_unavailable",
            certificate_sha256_value=own_cert_sha,
            operation_span=source_span,
            temporal_frame=sender_frame,
            endpoint_digest=endpoint_digest,
            handoff_envelope=signed_envelope,
            error=last_error,
        )
        path = _write_record(directory, record)
        return {"status": record["status"], "record_path": str(path), "error": last_error}

    try:
        peer_sha = _peer_certificate_sha256(transport)
        if peer_sha != endpoint["server_cert_sha256"] or peer_sha != certificate_sha256(server_cert_path):
            raise DirectMTLSError("TLS server peer does not match the attested server certificate")
        sender_channel = ReliableChannel(
            transport,
            "client-host",
            "server-host",
            DATA_CHANNEL,
            ReliabilityPolicy(lease_ticks=2, max_attempts=4, window_size=4),
        )
        sequence = sender_channel.send(signed_envelope)
        if sequence != 1:
            raise DirectMTLSError("first direct operation did not use ReliableChannel sequence one")
        _wait_for_ack(sender_channel, (sequence,), timeout_seconds=15.0)

        receipt_receiver = ReliableChannel(
            transport,
            "client-host",
            "client-host",
            RECEIPT_CHANNEL,
            ReliabilityPolicy(lease_ticks=2, max_attempts=4, window_size=4),
            peer="server-host",
        )
        deadline = time.monotonic() + 15.0
        delivered = None
        while time.monotonic() < deadline:
            delivered = receipt_receiver.receive()
            if delivered is not None:
                break
            time.sleep(0.005)
        if delivered is None:
            raise DirectMTLSError("server did not return a signed receiver receipt")
        receipt_sequence, signed_receipt = delivered
        if receipt_sequence != 1:
            raise DirectMTLSError("receiver receipt did not use ReliableChannel sequence one")
        receipt_core = _verify_signed_document(signed_receipt, server_cert_path)
        if receipt_core.get("schema") != RECEIPT_SCHEMA:
            raise DirectMTLSError("unsupported receiver receipt schema")
        if (
            receipt_core.get("path_id") != path_id
            or receipt_core.get("attempt_id") != attempt_id
            or receipt_core.get("channel_id") != DATA_CHANNEL
            or receipt_core.get("message_sequence") != sequence
            or receipt_core.get("sender_actor_id") != host["actor_id"]
            or receipt_core.get("receiver_actor_id") != server_host["actor_id"]
            or receipt_core.get("sender_cert_sha256") != own_cert_sha
            or receipt_core.get("receiver_cert_sha256") != peer_sha
            or receipt_core.get("sender_envelope_digest") != signed_envelope["signed_digest"]
            or receipt_core.get("predecessor_span_digest") != source_span["span_digest"]
        ):
            raise DirectMTLSError("signed receiver receipt does not bind this direct handoff")
        witness = receipt_core.get("handoff_witness")
        successor = validate_operation_span(receipt_core.get("receiver_operation_span"))
        validate_causal_handoff_witness(
            witness,
            predecessor_span=source_span,
            successor_span=successor,
        )
        if receipt_core.get("successor_span_digest") != successor["span_digest"]:
            raise DirectMTLSError("receiver receipt successor digest differs from its operation span")
        record = _make_record(
            role="client_host",
            host=host,
            status="direct_mtls_verified",
            certificate_sha256_value=own_cert_sha,
            operation_span=source_span,
            temporal_frame=sender_frame,
            endpoint_digest=endpoint_digest,
            handoff_envelope=signed_envelope,
            receiver_receipt=dict(signed_receipt),
            peer_certificate_sha256=peer_sha,
        )
        path = _write_record(directory, record)
        return {
            "status": "direct_mtls_verified",
            "record_path": str(path),
            "peer_certificate_sha256": peer_sha,
            "message_sequence": sequence,
            "receipt_sequence": receipt_sequence,
        }
    except Exception as error:
        record = _make_record(
            role="client_host",
            host=host,
            status="direct_mtls_rejected",
            certificate_sha256_value=own_cert_sha,
            operation_span=source_span,
            temporal_frame=sender_frame,
            endpoint_digest=endpoint_digest,
            handoff_envelope=signed_envelope,
            peer_certificate_sha256=_peer_certificate_sha256(transport),
            error=f"{type(error).__name__}: {str(error)[:800]}",
        )
        path = _write_record(directory, record)
        return {"status": record["status"], "record_path": str(path), "error": record["error"]}
    finally:
        if not transport.closed:
            transport.close()


def write_record_predicate(record_path: Path, output_path: Path, role: str) -> dict[str, Any]:
    record = read_json(record_path)
    if record.get("schema") != RECORD_SCHEMA or record.get("role") != role:
        raise DirectMTLSError("unsupported host operation record or role")
    core = {key: value for key, value in record.items() if key != "record_digest"}
    if record.get("record_digest") != digest_object(core):
        raise DirectMTLSError("host operation record digest is invalid")
    host = host_metadata(role)
    if dict(record.get("host", {})) != host:
        raise DirectMTLSError("host operation record identity differs from the current runner")
    predicate = {
        "schema": RECORD_PREDICATE_SCHEMA,
        "role": role,
        "host": host,
        "record_sha256": file_digest(record_path),
        "record_digest": record["record_digest"],
        "certificate_sha256": record["certificate_sha256"],
        "status": record["status"],
        "path_id": (
            record["handoff_envelope"]["core"]["path_id"]
            if record.get("handoff_envelope")
            else f"run-{host['run_id']}-ihp002-direct-mtls"
        ),
    }
    write_json(output_path, predicate)
    return predicate


def _validate_record(record: Mapping[str, Any], role: str) -> dict[str, Any]:
    required = {
        "schema", "role", "status", "host", "certificate_sha256",
        "operation_span", "temporal_frame", "endpoint_digest",
        "handoff_envelope", "received_envelope", "receiver_receipt",
        "peer_certificate_sha256", "error", "record_digest",
    }
    if not isinstance(record, Mapping) or set(record) != required:
        raise DirectMTLSError(f"{role} record fields are incomplete or unexpected")
    if record["schema"] != RECORD_SCHEMA or record["role"] != role:
        raise DirectMTLSError(f"{role} record schema or role is invalid")
    core = {key: record[key] for key in required if key != "record_digest"}
    if record["record_digest"] != digest_object(core):
        raise DirectMTLSError(f"{role} record digest does not match")
    host = _validate_host_metadata(record["host"], role)
    if not isinstance(record["certificate_sha256"], str) or len(record["certificate_sha256"]) != 64:
        raise DirectMTLSError(f"{role} certificate digest is invalid")
    if record["status"] not in {"direct_mtls_verified", "direct_tcp_unavailable", "direct_mtls_rejected"}:
        raise DirectMTLSError(f"{role} status is unsupported")
    if record["status"] == "direct_mtls_verified":
        if not isinstance(record["operation_span"], Mapping) or not isinstance(record["temporal_frame"], Mapping):
            raise DirectMTLSError(f"{role} successful record lacks its operation span/frame")
        validate_operation_span(record["operation_span"])
        validate_temporal_frame(record["temporal_frame"])
        if not isinstance(record["peer_certificate_sha256"], str) or len(record["peer_certificate_sha256"]) != 64:
            raise DirectMTLSError(f"{role} successful record lacks a TLS peer certificate fingerprint")
    return dict(record)


def _validate_verifier(verifier: Mapping[str, Any], client: Mapping[str, Any], server: Mapping[str, Any]) -> None:
    if verifier.get("role") != "verifier_host":
        raise DirectMTLSError("report must be produced by the verifier_host job")
    _validate_host_metadata(verifier, "verifier_host")
    client_host = _validate_host_metadata(client["host"], "client_host")
    server_host = _validate_host_metadata(server["host"], "server_host")
    _require_run_match(client_host, server_host)
    _require_run_match(client_host, verifier)


def build_report(
    client_record: Mapping[str, Any],
    server_record: Mapping[str, Any],
    client_cert_path: Path,
    server_cert_path: Path,
    server_endpoint: Mapping[str, Any],
    client_cert_attestation: Mapping[str, Any],
    server_cert_attestation: Mapping[str, Any],
    client_record_attestation: Mapping[str, Any],
    server_record_attestation: Mapping[str, Any],
    verifier_host: Mapping[str, Any],
) -> dict[str, Any]:
    client = _validate_record(client_record, "client_host")
    server = _validate_record(server_record, "server_host")
    _validate_verifier(verifier_host, client, server)
    client_cert_sha = certificate_sha256(client_cert_path)
    server_cert_sha = certificate_sha256(server_cert_path)
    if client["certificate_sha256"] != client_cert_sha or server["certificate_sha256"] != server_cert_sha:
        raise DirectMTLSError("host record certificate fingerprint differs from the attested public certificate")

    client_status = client["status"]
    server_status = server["status"]
    endpoint_core = _verify_endpoint_advertisement(server_endpoint, server_cert_path)
    if (
        endpoint_core["client_actor_id"] != client["host"]["actor_id"]
        or endpoint_core["client_cert_sha256"] != client_cert_sha
        or endpoint_core["server_host"]["actor_id"] != server["host"]["actor_id"]
        or client.get("endpoint_digest") != digest_object(server_endpoint)
        or server.get("endpoint_digest") != digest_object(server_endpoint)
    ):
        raise DirectMTLSError("host records do not bind the same signed endpoint advertisement")
    common = {
        "schema": REPORT_SCHEMA,
        "path_id": f"run-{client['host']['run_id']}-ihp002-direct-mtls",
        "repository": REPOSITORY,
        "run_id": client["host"]["run_id"],
        "run_attempt": client["host"]["run_attempt"],
        "client": {
            "host": client["host"],
            "status": client_status,
            "certificate_sha256": client_cert_sha,
            "record_digest": client["record_digest"],
            "record_attestation": dict(client_record_attestation),
            "certificate_attestation": dict(client_cert_attestation),
        },
        "server": {
            "host": server["host"],
            "status": server_status,
            "certificate_sha256": server_cert_sha,
            "record_digest": server["record_digest"],
            "record_attestation": dict(server_record_attestation),
            "certificate_attestation": dict(server_cert_attestation),
        },
        "verifier": dict(verifier_host),
        "server_endpoint": dict(server_endpoint),
        "direct_transport": {
            "substrate": "E-CPU SocketTransport over mutually authenticated TLS",
            "data_channel": DATA_CHANNEL,
            "receipt_channel": RECEIPT_CHANNEL,
            "bootstrap_transport": "GitHub Actions artifacts; public certificates and endpoint advertisement only",
            "semantic_payload_relayed_by_artifact_store": False,
        },
        "duration": {
            "client_local_elapsed_ns": None,
            "server_local_elapsed_ns": None,
            "combined_cross_host_elapsed_ns": None,
            "status": "not_computed_independent_unaligned_clock_domains",
        },
        "limitations": [
            "The hosted runner worker IDs and physical infrastructure are controlled by GitHub; this experiment does not establish independent cloud-provider trust domains.",
            "A certificate attestation binds the public certificate to the protected workflow identity; the self-signed certificate private key remains local to its participant.",
            "A signed application receipt proves possession of the pinned Ed25519 key, not that a malicious host performed honest computation.",
            "The endpoint advertisement is signed by the server identity; a successful TCP connection is required before a direct transport edge is claimed.",
            "Operation spans measure synchronous callable boundaries, not CPU time.",
            "No combined cross-host duration is inferred from independent monotonic clocks.",
        ],
    }

    if client_status != "direct_mtls_verified" or server_status != "direct_mtls_verified":
        report_core = {
            **common,
            "status": "direct_transport_unavailable",
            "causal_reconstruction": {
                "status": "not_established",
                "reason": "both hosts did not record a completed mutually authenticated ReliableChannel exchange",
                "client_error": client.get("error"),
                "server_error": server.get("error"),
            },
        }
        return {**report_core, "report_digest": digest_object(report_core)}

    handoff = client["handoff_envelope"]
    received_handoff = server["received_envelope"]
    receipt = client["receiver_receipt"]
    server_receipt = server["receiver_receipt"]
    if (
        client["operation_span"] != handoff["core"]["operation_span"]
        or client["temporal_frame"] != handoff["core"]["sender_completion_frame"]
        or server["operation_span"] != server_receipt["core"]["receiver_operation_span"]
        or server["temporal_frame"] != server_receipt["core"]["receiver_start_frame"]
    ):
        raise DirectMTLSError("host records differ from the signed operation or receipt endpoints")
    if handoff != received_handoff or receipt != server_receipt:
        raise DirectMTLSError("client and server records disagree on the signed handoff or receipt")
    handoff_core = _verify_signed_document(handoff, client_cert_path)
    receipt_core = _verify_signed_document(receipt, server_cert_path)
    if handoff_core["sender_cert_sha256"] != client_cert_sha or receipt_core["receiver_cert_sha256"] != server_cert_sha:
        raise DirectMTLSError("signed envelope/receipt certificate bindings do not match the attested certificates")
    if client["peer_certificate_sha256"] != server_cert_sha or server["peer_certificate_sha256"] != client_cert_sha:
        raise DirectMTLSError("TLS peer fingerprints do not match the reciprocal attested certificates")

    predecessor = validate_operation_span(handoff_core["operation_span"])
    successor = validate_operation_span(receipt_core["receiver_operation_span"])
    witness = validate_causal_handoff_witness(
        receipt_core["handoff_witness"],
        predecessor_span=predecessor,
        successor_span=successor,
    )
    if (
        witness["channel_id"] != DATA_CHANNEL
        or witness["message_sequence"] != 1
        or witness["received_sequence"] != 1
        or receipt_core["sender_envelope_digest"] != handoff["signed_digest"]
        or receipt_core["predecessor_span_digest"] != predecessor["span_digest"]
        or receipt_core["successor_span_digest"] != successor["span_digest"]
    ):
        raise DirectMTLSError("receiver receipt does not bind the exact operation handoff and reliable sequence")

    report_core = {
        **common,
        "status": "direct_mtls_verified",
        "causal_reconstruction": {
            "status": "verified_from_direct_peer_authenticated_receipt",
            "edge_count": 1,
            "edge_basis": "E-CPU ReliableChannel delivery, TLS peer certificate pinning, Ed25519 sender envelope and receiver receipt, vector-clock merge",
            "predecessor_span_digest": predecessor["span_digest"],
            "successor_span_digest": successor["span_digest"],
            "handoff_digest": witness["handoff_digest"],
            "sender_actor_id": witness["sender_actor_id"],
            "receiver_actor_id": witness["receiver_actor_id"],
            "sender_vector": witness["sender_completion_frame"]["causal"]["vector"],
            "receiver_vector": witness["receiver_start_frame"]["causal"]["vector"],
            "sender_lamport": witness["sender_completion_frame"]["causal"]["lamport"],
            "receiver_lamport": witness["receiver_start_frame"]["causal"]["lamport"],
            "transport_sequence": witness["message_sequence"],
            "receipt_digest": receipt["signed_digest"],
            "sender_envelope_digest": handoff["signed_digest"],
            "tls_client_certificate_sha256": client_cert_sha,
            "tls_server_certificate_sha256": server_cert_sha,
            "topological_order": [predecessor["span_digest"], successor["span_digest"]],
        },
        "duration": {
            "client_local_elapsed_ns": predecessor["elapsed_ns"],
            "server_local_elapsed_ns": successor["elapsed_ns"],
            "combined_cross_host_elapsed_ns": None,
            "status": "not_computed_independent_unaligned_clock_domains",
        },
    }
    return {**report_core, "report_digest": digest_object(report_core)}


def write_report_predicate(report_path: Path, predicate_path: Path) -> dict[str, Any]:
    report = read_json(report_path)
    if report.get("schema") != REPORT_SCHEMA:
        raise DirectMTLSError("unsupported direct-mTLS report")
    core = {key: value for key, value in report.items() if key != "report_digest"}
    if report.get("report_digest") != digest_object(core):
        raise DirectMTLSError("direct-mTLS report digest is invalid")
    host = host_metadata("verifier_host")
    if report.get("verifier") != host:
        raise DirectMTLSError("report verifier identity differs from the current job")
    predicate = {
        "schema": REPORT_PREDICATE_SCHEMA,
        "repository": host["repository"],
        "run_id": host["run_id"],
        "run_attempt": host["run_attempt"],
        "workflow_ref": host["workflow_ref"],
        "workflow_sha": host["workflow_sha"],
        "git_ref": host["git_ref"],
        "git_sha": host["git_sha"],
        "job": host["job"],
        "runner_name": host["runner_name"],
        "runner_environment": host["runner_environment"],
        "report_sha256": file_digest(report_path),
        "report_digest": report["report_digest"],
        "status": report["status"],
        "path_id": report["path_id"],
    }
    write_json(predicate_path, predicate)
    return predicate


def verify_to_report(
    directory: Path,
    output_path: Path,
    *,
    gh: str = "gh",
) -> dict[str, Any]:
    client_bootstrap = directory / "client-bootstrap"
    server_bootstrap = directory / "server-bootstrap"
    client_result = directory / "client-result"
    server_result = directory / "server-result"
    client_cert = client_bootstrap / "client-cert.pem"
    server_cert = server_bootstrap / "server-cert.pem"
    client_record_path = client_result / "client_host-record.json"
    server_record_path = server_result / "server_host-record.json"
    client_record = read_json(client_record_path)
    server_record = read_json(server_record_path)
    server_endpoint = read_json(server_bootstrap / "server-endpoint.json")
    client_certificate_predicate = read_json(client_bootstrap / "client-cert.predicate.json")
    server_certificate_predicate = read_json(server_bootstrap / "server-cert.predicate.json")
    client_record_predicate = read_json(client_result / "client_host-record.predicate.json")
    server_record_predicate = read_json(server_result / "server_host-record.predicate.json")

    client_cert_attestation = verify_artifact_attestation(
        client_cert, CERT_PREDICATE_TYPE, expected_predicate=client_certificate_predicate, gh=gh
    )
    server_cert_attestation = verify_artifact_attestation(
        server_cert, CERT_PREDICATE_TYPE, expected_predicate=server_certificate_predicate, gh=gh
    )
    client_record_attestation = verify_artifact_attestation(
        client_record_path, RECORD_PREDICATE_TYPE, expected_predicate=client_record_predicate, gh=gh
    )
    server_record_attestation = verify_artifact_attestation(
        server_record_path, RECORD_PREDICATE_TYPE, expected_predicate=server_record_predicate, gh=gh
    )
    current_run = _env(os.environ, "GITHUB_RUN_ID")
    current_attempt = _env(os.environ, "GITHUB_RUN_ATTEMPT")
    _validate_certificate_predicate(client_certificate_predicate, client_cert, "client_host", current_run, current_attempt)
    _validate_certificate_predicate(server_certificate_predicate, server_cert, "server_host", current_run, current_attempt)
    _validate_record_predicate(client_record_predicate, client_record_path, client_record, "client_host")
    _validate_record_predicate(server_record_predicate, server_record_path, server_record, "server_host")
    report = build_report(
        client_record,
        server_record,
        client_cert,
        server_cert,
        server_endpoint,
        client_cert_attestation,
        server_cert_attestation,
        client_record_attestation,
        server_record_attestation,
        host_metadata("verifier_host"),
    )
    write_json(output_path, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    client_parser = commands.add_parser("prepare-client")
    client_parser.add_argument("--directory", type=Path, required=True)

    server_parser = commands.add_parser("prepare-server")
    server_parser.add_argument("--directory", type=Path, required=True)
    server_parser.add_argument("--gh", default="gh")
    server_parser.add_argument("--bootstrap-timeout", type=float, default=180.0)
    server_parser.add_argument(
        "--advertise-host",
        help="explicit Tailscale overlay IPv4 endpoint (required by the IHP-006 workflow)",
    )

    serve_parser = commands.add_parser("serve")
    serve_parser.add_argument("--directory", type=Path, required=True)
    serve_parser.add_argument("--accept-timeout", type=float, default=120.0)
    serve_parser.add_argument(
        "--bind-host",
        help="explicit Tailscale overlay IPv4 listener address (required by IHP-006)",
    )

    connect_parser = commands.add_parser("connect")
    connect_parser.add_argument("--directory", type=Path, required=True)
    connect_parser.add_argument("--connect-timeout", type=float, default=100.0)
    connect_parser.add_argument("--gh", default="gh")

    predicate_parser = commands.add_parser("write-record-predicate")
    predicate_parser.add_argument("--record", type=Path, required=True)
    predicate_parser.add_argument("--role", choices=("client_host", "server_host"), required=True)
    predicate_parser.add_argument("--output", type=Path, required=True)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--directory", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--gh", default="gh")

    report_predicate_parser = commands.add_parser("write-report-predicate")
    report_predicate_parser.add_argument("--report", type=Path, required=True)
    report_predicate_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-client":
            result = prepare_client(args.directory)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "prepare-server":
            result = prepare_server(
                args.directory,
                gh=args.gh,
                bootstrap_timeout=args.bootstrap_timeout,
                advertise_host=args.advertise_host,
            )
            print(json.dumps(result, sort_keys=True))
        elif args.command == "serve":
            result = serve(
                args.directory,
                accept_timeout=args.accept_timeout,
                bind_host=args.bind_host,
            )
            print(json.dumps(result, sort_keys=True))
        elif args.command == "connect":
            result = connect_and_send(args.directory, connect_timeout_seconds=args.connect_timeout, gh=args.gh)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "write-record-predicate":
            result = write_record_predicate(args.record, args.output, args.role)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "verify":
            result = verify_to_report(args.directory, args.output, gh=args.gh)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "write-report-predicate":
            result = write_report_predicate(args.report, args.output)
            print(json.dumps(result, sort_keys=True))
    except (DirectMTLSError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"direct-mtls-operation-path: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
