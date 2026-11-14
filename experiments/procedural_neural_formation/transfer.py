"""PNF-002 experiment harness; receiver receives parameter data only via E-CPU."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import uuid

from mailcpu import ReliabilityPolicy, ReliableChannel
from mailcpu.mtls_transport import connect_mutual_tls

from .capsule import canonical, sha
from .formation import FormationError
from .receiver import CHUNK, FRAME, SENDER, RECEIVER, SOURCE_DNS, RECEIVER_DNS, REQUEST, RESPONSE, implementation_digest


def certificates(directory: Path) -> dict:
    """Ephemeral test CA with two distinct SAN identities; keys never enter reports."""
    openssl = shutil.which("openssl")
    if openssl is None and Path(r"C:\Program Files\Git\mingw64\bin\openssl.exe").is_file():
        openssl = r"C:\Program Files\Git\mingw64\bin\openssl.exe"
    if openssl is None:
        raise RuntimeError("OpenSSL executable required for the mTLS experiment")
    def run(*args):
        result = subprocess.run([openssl, *args], cwd=directory, capture_output=True, text=True, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise RuntimeError("test certificate generation failed: " + result.stderr)
    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem",
        "-days", "1", "-subj", "/CN=PNF-Test-CA", "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    files = {"ca": str(directory / "ca.pem")}
    for role, dns in (("source", SOURCE_DNS), ("receiver", RECEIVER_DNS)):
        run("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", role + ".key",
            "-out", role + ".csr", "-subj", "/CN=" + dns)
        (directory / (role + ".ext")).write_text("subjectAltName=DNS:" + dns + "\n"
            "basicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth,clientAuth\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n", encoding="ascii")
        run("x509", "-req", "-in", role + ".csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-out", role + ".pem", "-days", "1", "-extfile", role + ".ext")
        files[role + "_certificate"] = str(directory / (role + ".pem"))
        files[role + "_key"] = str(directory / (role + ".key"))
        files[role + "_pin"] = sha(ssl.PEM_cert_to_DER_cert((directory / (role + ".pem")).read_text()))
    return files


def transfer_pair(raw: bytes, policy: dict, *, expected_receiver_pin: str | None = None,
                  native_execution: bool = False, grant_compute: bool = True) -> dict:
    """Start a fresh interpreter, authenticate it, transfer chunks, validate its receipt."""
    with tempfile.TemporaryDirectory(prefix="pnf-receiver-") as temporary:
        directory = Path(temporary)
        certs = certificates(directory)
        request_id = uuid.uuid4().hex
        config = {"policy": policy, "request_id": request_id, "certificate": certs["receiver_certificate"],
                  "private_key": certs["receiver_key"], "ca": certs["ca"], "source_certificate_sha256": certs["source_pin"],
                  "native_execution": native_execution, "grant_compute": grant_compute}
        config_path, ready_path = directory / "policy.json", directory / "ready.json"
        config_path.write_bytes(canonical(config))
        process = subprocess.Popen([sys.executable, "-m", "experiments.procedural_neural_formation.receiver",
            "--config", str(config_path), "--ready", str(ready_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        transport = None
        try:
            deadline = time.monotonic() + 15
            ready = None
            while ready is None and time.monotonic() < deadline:
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=2)
                    raise RuntimeError(f"receiver exited before readiness: {stdout} {stderr}")
                if ready_path.exists():
                    try:
                        ready = json.loads(ready_path.read_bytes())
                    except json.JSONDecodeError:
                        pass
                if ready is None:
                    time.sleep(0.01)
            if ready is None or ready["pid"] != process.pid or process.pid == os.getpid():
                raise RuntimeError("separate receiver did not become ready")
            expected_impl = implementation_digest(native_execution)
            if ready["implementation_digest"] != expected_impl:
                raise FormationError("receiver implementation mismatch")
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=certs["ca"])
            context.load_cert_chain(certs["source_certificate"], certs["source_key"])
            transport = connect_mutual_tls("127.0.0.1", ready["port"], SENDER, RECEIVER, context,
                server_hostname=RECEIVER_DNS, max_frame_size=FRAME, send_timeout=10)
            peer_pin = sha(transport.socket.getpeercert(binary_form=True))
            if peer_pin != (expected_receiver_pin or certs["receiver_pin"]):
                raise FormationError("receiver certificate pin mismatch")
            reliability = ReliabilityPolicy(window_size=1, lease_ticks=1000, max_attempts=3)
            outgoing = ReliableChannel(transport, SENDER, RECEIVER, REQUEST, reliability, peer=RECEIVER)
            incoming = ReliableChannel(transport, SENDER, SENDER, RESPONSE, reliability, peer=RECEIVER)
            count = 0
            for start in range(0, len(raw), CHUNK):
                outgoing.send({"request_id": request_id, "kind": "chunk", "index": count,
                               "data": base64.b64encode(raw[start:start + CHUNK]).decode("ascii")})
                deadline = time.monotonic() + 15
                while outgoing.pending_sequences() and time.monotonic() < deadline:
                    outgoing.process_ack()
                    time.sleep(0.001)
                if outgoing.pending_sequences():
                    raise TimeoutError("receiver did not acknowledge staged chunk")
                count += 1
            outgoing.send({"request_id": request_id, "kind": "verify"})
            deadline = time.monotonic() + 120
            packet = None
            while packet is None and time.monotonic() < deadline:
                outgoing.process_ack()
                packet = incoming.receive()
                if packet is None:
                    time.sleep(0.002)
            if packet is None:
                raise TimeoutError("receiver did not return a verification result")
            sequence, response = packet
            if (sequence != 1 or response.get("request_id") != request_id or
                response.get("capsule_sha256") != policy["capsule_sha256"] or
                response.get("receiver_pid") != process.pid or response.get("implementation_digest") != expected_impl or
                response.get("source_certificate_sha256") != certs["source_pin"] or response.get("chunks") != count):
                raise FormationError("receiver response identity mismatch")
            report = response.get("report")
            if not isinstance(report, dict) or report.get("status") not in ("verified", "rejected"):
                raise FormationError("invalid receiver result status")
            if report["status"] == "verified" and any(report.get(k) != v for k, v in policy.items()):
                raise FormationError("receiver result does not bind the configured model pair")
            if report["status"] == "verified" and native_execution:
                native = report.get("native_execution", {})
                if (native.get("status") != ("executed" if grant_compute else "denied")
                        or any(native.get(k) != v for k, v in policy.items())
                        or native.get("cut_model_digest") != policy["generated_digest"]):
                    raise FormationError("receiver native result does not bind local execution policy")
            stdout, stderr = process.communicate(timeout=20)
            if process.returncode != 0:
                raise RuntimeError(f"receiver process failed: {stdout} {stderr}")
            return {"request_id": request_id, "sender_pid": os.getpid(), "receiver_pid": process.pid,
                    "receiver_certificate_sha256": peer_pin, "source_certificate_sha256": certs["source_pin"],
                    "capsule_bytes": len(raw), "chunk_count": count, "chunk_limit": CHUNK,
                    "maximum_transport_frame_bytes": FRAME, "transport": "E-CPU ReliableChannel over mutual TLS",
                    "same_physical_host": True, "receiver": response,
                    "shared_parameter_file_used": False, "durable_recovery_claimed": False}
        finally:
            if transport is not None:
                transport.close()
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
