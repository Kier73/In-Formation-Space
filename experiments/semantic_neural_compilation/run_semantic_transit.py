"""SNC-002: two distinct local processes exchange source meaning or neural parameters.

This is an empirical same-host comparison, not a claim of independent physical
machines or global network communication. The receiver owns the source pin.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from tempfile import TemporaryDirectory

from compiler import compile_semantics
from independent_certificate_checker import hash_bytes
from semantic_transit import SCHEMA, canonical

HERE = Path(__file__).resolve().parent
WIRE_CLI = HERE / "semantic_transit.py"
MAX_T = 65


def command(folder: Path, *args: str) -> None:
    result = subprocess.run(
        ["openssl", *args], cwd=folder, text=True,
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "ephemeral test-only PKI generation failed: " + result.stderr[-600:])


def test_certificates(folder: Path) -> dict[str, Path]:
    ca, ca_key = folder / "ca.pem", folder / "ca.key"
    command(folder, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(ca_key), "-out", str(ca), "-days", "1",
            "-sha256", "-subj", "/CN=SNC002 Ephemeral Test CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    result = {"ca": ca}
    for role, dns in (("server", "snc002-recipient"),
                      ("client", "snc002-origin")):
        key, csr, cert, ext = (
            folder / (role + ".key"), folder / (role + ".csr"),
            folder / (role + ".pem"), folder / (role + ".ext"),
        )
        ext.write_text(
            f"subjectAltName=DNS:{dns}\n"
            "extendedKeyUsage=serverAuth,clientAuth\n"
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n",
            encoding="utf-8",
        )
        command(folder, "req", "-new", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(csr), "-subj", f"/CN={dns}")
        command(folder, "x509", "-req", "-in", str(csr),
                "-CA", str(ca), "-CAkey", str(ca_key), "-CAcreateserial",
                "-out", str(cert), "-days", "1", "-sha256", "-extfile", str(ext))
        result[role + "_key"], result[role + "_cert"] = key, cert
    return result


def zigzag(count: int = 32) -> list[dict[str, object]]:
    """Exact continuous stress atlas, with independently determined boundaries."""
    assert 1 <= count <= 48
    out = []
    left = "-inf"
    slope, offset = 1, 0
    for t in range(1, count + 1):
        out.append({
            "left": left, "right": str(t),
            "affines": [[str(slope), str(offset)]],
        })
        next_slope = -slope
        offset += (slope - next_slope) * t
        slope = next_slope
        left = str(t)
    out.append({
        "left": left, "right": "+inf",
        "affines": [[str(slope), str(offset)]],
    })
    return out


def one_transfer(
    folder: Path, files: dict[str, Path], *, name: str, kind: str,
    body: bytes, expected_sha: str,
) -> dict[str, object]:
    payload_path = folder / f"{name}-{kind}.payload.json"
    receiver_path = folder / f"{name}-{kind}.receiver.json"
    payload_path.write_bytes(body)
    server_cmd = [
        sys.executable, str(WIRE_CLI), "serve",
        "--bind", "127.0.0.1", "--port", "0",
        "--ca", str(files["ca"]),
        "--cert", str(files["server_cert"]),
        "--key", str(files["server_key"]),
        "--expected-semantic-sha256", expected_sha,
        "--report", str(receiver_path),
    ]
    start = time.perf_counter_ns()
    server = subprocess.Popen(
        server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    try:
        first = server.stdout.readline().strip()
        found = re.fullmatch(r"LISTEN_PORT=([1-9][0-9]*)", first)
        if not found:
            raise RuntimeError(
                f"mTLS receiver failed to listen for {name}/{kind}: "
                + first + " " + (server.stderr.read(300) if server.poll() is not None else ""))
        port = int(found.group(1))
        sender_cmd = [
            sys.executable, str(WIRE_CLI), "send",
            "--host", "127.0.0.1", "--port", str(port),
            "--kind", kind, "--payload", str(payload_path),
            "--ca", str(files["ca"]), "--cert", str(files["client_cert"]),
            "--key", str(files["client_key"]),
        ]
        sent = subprocess.run(
            sender_cmd, text=True, capture_output=True,
            check=False, timeout=MAX_T,
        )
        server_output, server_error = server.communicate(timeout=MAX_T)
        elapsed = time.perf_counter_ns() - start
        if sent.returncode:
            raise RuntimeError(
                f"sender failed for {name}/{kind}: " + sent.stderr[-1200:])
        if server.returncode:
            raise RuntimeError(
                f"receiver failed for {name}/{kind}: " + server_error[-1200:])
        if not receiver_path.is_file():
            raise RuntimeError("no independent receiving proof report produced")
        if "SNC002_RECEIVER_VERIFIED:" not in server_output:
            raise RuntimeError("receiver success marker absent")
        send_report = json.loads(sent.stdout)
        receive_report = json.loads(receiver_path.read_text())
        decision = receive_report["semantic_verification"]
        if decision["status"] != "exact-all-real-semantic-equivalence-verified":
            raise RuntimeError("receiver returned a non-equivalent realization")
        if decision["source_semantic_sha256"] != expected_sha:
            raise RuntimeError("receiver admitted incorrect semantic identity")
        if send_report["application_bytes"] != receive_report["application_bytes"]:
            raise RuntimeError("application-byte measurements disagree")
        if send_report["frames_acked"] != receive_report["frame_count"]:
            raise RuntimeError("reliable frame count disagrees")
        if receive_report["tls_version"] not in ("TLSv1.2", "TLSv1.3"):
            raise RuntimeError("no authenticated TLS protocol reported")
        return {
            "application_bytes": send_report["application_bytes"],
            "frames_acked": send_report["frames_acked"],
            "sender_ack_duration_ns_sender_local": send_report["sender_ack_duration_ns"],
            "receive_duration_ns_receiver_local": receive_report["receive_duration_ns_receiver_local"],
            "construction_ns_receiver_local": decision["construction_ns_receiver_local"],
            "verification_ns_receiver_local": decision["independent_verification_ns_receiver_local"],
            "same_host_process_roundtrip_ns": elapsed,
            "source_semantic_sha256": decision["source_semantic_sha256"],
            "generated_network_sha256": decision["generated_network_sha256"],
            "tls_version": receive_report["tls_version"],
            "peer_certificate_sha256": receive_report["peer_certificate_sha256"],
        }
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate(timeout=5)


def run(*, output: Path) -> dict[str, object]:
    examples = json.loads((HERE / "examples.json").read_text())
    selected = {
        "clamp_0_1": examples["clamp_0_1"],
        "triangular_bump": examples["triangular_bump"],
        "vector_x_abs": examples["vector_x_abs"],
        "zigzag_32": zigzag(),
    }
    with TemporaryDirectory(prefix="snc002-mtls-test-fixtures-") as tmp:
        folder = Path(tmp)
        files = test_certificates(folder)
        results = {}
        for name, atlas in selected.items():
            expected_sha = hash_bytes(atlas)
            source_payload = canonical({
                "schema": SCHEMA, "kind": "semantic", "semantic_atlas": atlas,
            })
            # Baseline carries the explicit generated coefficients and a
            # portable activation-cell certificate. This is an intentionally
            # verified parameter baseline, not a raw-weights-only comparison.
            constructed = compile_semantics(atlas)
            parameter_payload = canonical({
                "schema": SCHEMA, "kind": "parameters",
                "generated_certificate": constructed["generated_certificate"],
            })
            semantic = one_transfer(
                folder, files, name=name, kind="semantic",
                body=source_payload, expected_sha=expected_sha,
            )
            parameters = one_transfer(
                folder, files, name=name, kind="parameters",
                body=parameter_payload, expected_sha=expected_sha,
            )
            if semantic["source_semantic_sha256"] != parameters["source_semantic_sha256"]:
                raise RuntimeError("different observed semantics across strategies")
            if semantic["generated_network_sha256"] != parameters["generated_network_sha256"]:
                raise RuntimeError("different generated coefficient identity across strategies")
            results[name] = {
                "semantic": semantic, "parameters_with_certificate": parameters,
                "semantic_to_parameter_byte_ratio":
                    semantic["application_bytes"] / parameters["application_bytes"],
                "generated_model_equivalent_and_identical": True,
            }
    report = {
        "schema": "in-formation-space.snc002.mtls-comparison-report/0.1",
        "status": "all-receiver-verified",
        "cases": results,
        "transport": "E-CPU SocketTransport + ReliableChannel + mutual TLS",
        "pki": "ephemeral test-only local CA and SAN identities",
        "receiver_source_pins": "coordinator-owned exact atlas digests; not supplied by wire",
        "hosts": "separate sender and receiver Python processes on one Linux host",
        "timing": "same-host process wall-clock; sender and receiver monotonic durations are local",
        "baseline": "complete parameter-bearing COE certificate vs semantic atlas alone",
        "numeric_hardware_execution": False,
        "external_source_authenticated": False,
        "ground_admitted": False,
        "independent_machine_transfer": False,
        "note": "wire byte ratios are not TLS packet byte ratios or a universal compression claim",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(output=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
