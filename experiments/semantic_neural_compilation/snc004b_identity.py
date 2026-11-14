"""SNC-004B: genuinely independent per-job mTLS bootstrap certificate identities.

GitHub artifact exchange is *only* public certificate and endpoint bootstrap.
No private key, semantic authority, model payload, or application receipt
is accepted from a bootstrap artifact. TLS pins the exact peer public cert.

Identity attestations/issuer authorization are separate future gates: the
same-run GitHub artifact channel is the assumed bootstrap trust root here.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import ssl
import subprocess

from persistent_host import canonical, require, sha
from snc004b_live import PORT, SENDER, RECEIVER, addressing, certificate_sha256

ENDPOINT_SCHEMA = "in-formation-space.snc004b.overlay-bootstrap/0.1"
CERT_SCHEMA = "in-formation-space.snc004b.ephemeral-certificate-bootstrap/0.1"
ROLE_NAME = {"client": SENDER, "server": RECEIVER}


def require_run() -> tuple[str, str]:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(run_id.isdigit() and int(run_id) > 0 and
            attempt.isdigit() and int(attempt) > 0,
            "bootstrap requires an identified GitHub Actions run")
    return run_id, attempt


def make_identity(*, directory: Path, role: str) -> dict:
    require(role in ROLE_NAME, "unexpected role")
    run_id, attempt = require_run()
    directory.mkdir(parents=True, exist_ok=True)
    name = ROLE_NAME[role]
    key = directory / (role + "-key.pem")
    cert = directory / (role + "-cert.pem")
    args = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-days", "1", "-sha256",
        "-keyout", str(key), "-out", str(cert),
        "-subj", "/CN=" + name,
        "-addext", "subjectAltName=DNS:" + name,
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,digitalSignature,keyCertSign,cRLSign,keyEncipherment",
        "-addext", "extendedKeyUsage=serverAuth,clientAuth",
    ]
    result = subprocess.run(args, capture_output=True, text=True,
                            timeout=30, check=False)
    require(result.returncode == 0, "ephemeral TLS key generation failed")
    os.chmod(key, 0o600)
    record = {
        "schema": CERT_SCHEMA, "run_id": run_id, "run_attempt": attempt,
        "role": role, "dns": name,
        "certificate_sha256": certificate_sha256(cert),
    }
    (directory / (role + "-bootstrap.json")).write_bytes(canonical(record))
    return record


def inspect_peer(*, cert: Path, record: Path, expected_role: str) -> dict:
    run_id, attempt = require_run()
    require(expected_role in ROLE_NAME, "invalid expected peer")
    value = json.loads(record.read_text(encoding="utf-8"))
    require(type(value) is dict and set(value) == {
        "schema", "run_id", "run_attempt", "role", "dns", "certificate_sha256"
    }, "unexpected certificate bootstrap fields")
    require(value["schema"] == CERT_SCHEMA and
            value["run_id"] == run_id and value["run_attempt"] == attempt and
            value["role"] == expected_role and
            value["dns"] == ROLE_NAME[expected_role] and
            value["certificate_sha256"] == certificate_sha256(cert),
            "peer certificate bootstrap from wrong run or identity")
    decoded = ssl._ssl._test_decode_cert(str(cert))
    san = [val for typ, val in decoded.get("subjectAltName", ())
           if typ == "DNS"]
    require(ROLE_NAME[expected_role] in san, "peer SAN absent")
    return value


def make_endpoint(*, directory: Path, ip: str) -> dict:
    run_id, attempt = require_run()
    address = addressing(ip, overlay=True)
    cert = directory / "server-cert.pem"
    record = directory / "server-bootstrap.json"
    inspect_peer(cert=cert, record=record, expected_role="server")
    endpoint = {
        "schema": ENDPOINT_SCHEMA, "run_id": run_id, "run_attempt": attempt,
        "server_ipv4": address, "port": PORT,
        "server_certificate_sha256": certificate_sha256(cert),
    }
    (directory / "server-endpoint.json").write_bytes(canonical(endpoint))
    return endpoint


def inspect_endpoint(*, directory: Path) -> str:
    run_id, attempt = require_run()
    cert = directory / "server-cert.pem"
    inspect_peer(
        cert=cert, record=directory / "server-bootstrap.json",
        expected_role="server",
    )
    endpoint = json.loads((directory / "server-endpoint.json").read_text())
    require(type(endpoint) is dict and set(endpoint) == {
        "schema", "run_id", "run_attempt", "server_ipv4", "port",
        "server_certificate_sha256",
    }, "inconsistent endpoint fields")
    require(endpoint["schema"] == ENDPOINT_SCHEMA and
            endpoint["run_id"] == run_id and endpoint["run_attempt"] == attempt and
            type(endpoint["port"]) is int and endpoint["port"] == PORT and
            endpoint["server_certificate_sha256"] == certificate_sha256(cert),
            "wrong run or endpoint fingerprint")
    return addressing(endpoint["server_ipv4"], overlay=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--directory", type=Path, required=True)
    prepare.add_argument("--role", choices=sorted(ROLE_NAME), required=True)
    inspect = sub.add_parser("inspect-peer")
    inspect.add_argument("--directory", type=Path, required=True)
    inspect.add_argument("--role", choices=sorted(ROLE_NAME), required=True)
    endpoint = sub.add_parser("publish-endpoint")
    endpoint.add_argument("--directory", type=Path, required=True)
    endpoint.add_argument("--ip", required=True)
    check = sub.add_parser("inspect-endpoint")
    check.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = make_identity(directory=args.directory, role=args.role)
        elif args.command == "inspect-peer":
            result = inspect_peer(
                cert=args.directory / (args.role + "-cert.pem"),
                record=args.directory / (args.role + "-bootstrap.json"),
                expected_role=args.role,
            )
        elif args.command == "publish-endpoint":
            result = make_endpoint(directory=args.directory, ip=args.ip)
        else:
            result = {"ip": inspect_endpoint(directory=args.directory)}
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, RuntimeError, ssl.SSLError) as exc:
        parser.exit(1, "SNC004B_BOOTSTRAP_REJECTED:" + str(exc)[:250] + "\n")


if __name__ == "__main__":
    main()
