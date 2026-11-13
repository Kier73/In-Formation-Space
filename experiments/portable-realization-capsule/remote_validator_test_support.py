from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import sys
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


VALIDATOR_PEER_ID = "validator-peer-01"
VALIDATOR_DNS = "validator-node.mailcpu.test"
WORKER_PEER_ID = "peer-recovery-worker"
WORKER_DNS = "recovery-worker.mailcpu.test"


def _openssl(directory: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["openssl", *arguments],
        cwd=directory,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(f"OpenSSL failed: {result.stderr}")


def make_validator_certificates(directory: Path) -> dict[str, Path]:
    """Create a test CA and SAN-separated validator/worker identities."""
    directory.mkdir(parents=True, exist_ok=True)
    ca_key = directory / "ca.key"
    ca_certificate = directory / "ca.pem"
    _openssl(
        directory,
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(ca_key), "-out", str(ca_certificate),
        "-days", "3", "-sha256", "-subj", "/CN=IFS Remote Validator Test CA",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
    )
    files: dict[str, Path] = {"ca": ca_certificate}
    identities = (
        ("validator", VALIDATOR_DNS),
        ("worker", WORKER_DNS),
    )
    for role, dns_name in identities:
        key = directory / f"{role}.key"
        request = directory / f"{role}.csr"
        certificate = directory / f"{role}.pem"
        extensions = directory / f"{role}.ext"
        _openssl(
            directory,
            "req", "-new", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(request),
            "-subj", f"/CN={dns_name}",
        )
        extensions.write_text(
            "\n".join(
                (
                    f"subjectAltName=DNS:{dns_name}",
                    "extendedKeyUsage=clientAuth,serverAuth",
                    "basicConstraints=critical,CA:FALSE",
                    "keyUsage=critical,digitalSignature,keyEncipherment",
                )
            ) + "\n",
            encoding="utf-8",
        )
        _openssl(
            directory,
            "x509", "-req", "-in", str(request),
            "-CA", str(ca_certificate), "-CAkey", str(ca_key),
            "-CAcreateserial", "-out", str(certificate),
            "-days", "3", "-sha256", "-extfile", str(extensions),
        )
        files[f"{role}_key"] = key
        files[f"{role}_cert"] = certificate

    attestation_private = Ed25519PrivateKey.generate()
    attestation_private_path = directory / "validator-attestation-private.pem"
    attestation_public_path = directory / "validator-attestation-public.pem"
    attestation_private_path.write_bytes(
        attestation_private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    attestation_public_path.write_bytes(
        attestation_private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    files["attestation_private_key"] = attestation_private_path
    files["attestation_public_key"] = attestation_public_path
    return files


def start_validator_service(
    repository_root: Path,
    service_directory: Path,
    certificates: dict[str, Path],
    *,
    worker_peer_id: str = WORKER_PEER_ID,
    worker_host_id: str = "logical-host-recovery-worker",
    worker_implementation_fingerprint: str | None = None,
) -> tuple[subprocess.Popen[str], dict[str, Any]]:
    """Launch the validator in a separate Python interpreter with mutual TLS."""
    service_directory.mkdir(parents=True, exist_ok=True)
    script = (
        repository_root
        / "experiments"
        / "portable-realization-capsule"
        / "prepared_result_validation.py"
    )
    ecpu_root = repository_root / "external" / "E-CPU"
    vgi_root = repository_root / "external" / "Virtual-Ground-Interpreter" / "virtual_ground_interpreter"
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    entries = [
        str(repository_root / "experiments" / "portable-realization-capsule"),
        str(ecpu_root),
        str(vgi_root),
    ]
    if existing:
        entries.append(existing)
    environment["PYTHONPATH"] = os.pathsep.join(entries)
    selected_implementation = worker_implementation_fingerprint or hashlib.sha256(
        b"recovery-worker-implementation"
    ).hexdigest()
    process = subprocess.Popen(
        [
            sys.executable,
            str(script),
            "--host", "127.0.0.1",
            "--port", "0",
            "--validator-peer-id", VALIDATOR_PEER_ID,
            "--validator-dns-identity", VALIDATOR_DNS,
            "--expected-worker-peer-id", worker_peer_id,
            "--expected-worker-dns-identity", WORKER_DNS,
            "--expected-worker-host-id", worker_host_id,
            "--expected-worker-implementation-fingerprint", selected_implementation,
            "--certificate", str(certificates["validator_cert"]),
            "--private-key", str(certificates["validator_key"]),
            "--client-ca", str(certificates["ca"]),
            "--attestation-private-key", str(certificates["attestation_private_key"]),
        ],
        cwd=repository_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    ready_line = process.stdout.readline()
    if not ready_line:
        if process.poll() is None:
            process.kill()
        stdout, stderr = process.communicate(timeout=5)
        raise AssertionError(
            f"remote validator did not start: rc={process.returncode}, "
            f"stdout={stdout!r}, stderr={stderr!r}"
        )
    ready = json.loads(ready_line)
    assert ready["ready"] is True
    assert ready["validator_peer_id"] == VALIDATOR_PEER_ID
    assert ready["validator_dns_identity"] == VALIDATOR_DNS
    assert ready["expected_worker_host_id"] == worker_host_id
    assert ready["expected_worker_implementation_fingerprint"] == selected_implementation
    assert ready["pid"] == process.pid
    expected_der = ssl.PEM_cert_to_DER_cert(
        certificates["validator_cert"].read_text(encoding="ascii")
    )
    assert hashlib.sha256(expected_der).hexdigest() == ready["server_certificate_sha256"]
    public_key = serialization.load_pem_public_key(certificates["attestation_public_key"].read_bytes())
    public_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert hashlib.sha256(public_der).hexdigest() == ready["attestation_key_id"]
    return process, ready


def stop_validator_service(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=5)
