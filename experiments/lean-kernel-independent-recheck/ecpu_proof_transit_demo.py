#!/usr/bin/env python3
"""Live two-process loopback mTLS E-CPU proof transfer with replay rejection.

The proof receiver in the server process still runs *real* GitHub/Sigstore
attestation checks. The locally generated CA is a TEST FIXTURE, not production
PKI. A different process opens the persisted SQLite ledger for a second run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

import proof_receipt_receiver as receiver
import term_receipt as term

MAIN = Path(__file__).resolve().parent / "ecpu_proof_transit.py"
DURABLE = "independently-accepted-once"
MAX_T = 160


def _run_openssl(cwd: Path, *args: str) -> None:
    p = subprocess.run(["openssl", *args], cwd=cwd, capture_output=True, text=True,
                       timeout=30, check=False)
    if p.returncode:
        raise RuntimeError(f"test-only OpenSSL fixture creation failed: {p.stderr[-400:]}")


def _certs(folder: Path) -> dict[str, Path]:
    ca = folder / "demo-ca.pem"
    ca_key = folder / "demo-ca.key"
    _run_openssl(folder, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                 "-keyout", str(ca_key), "-out", str(ca), "-days", "1",
                 "-sha256", "-subj", "/CN=Proof Transit Test CA",
                 "-addext", "basicConstraints=critical,CA:TRUE",
                 "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    files = {"ca": ca}
    for role, dns in (("server", "proof-recipient"), ("client", "proof-origin")):
        key = folder / (role + ".key")
        csr = folder / (role + ".csr")
        cert = folder / (role + ".pem")
        ext = folder / (role + ".ext")
        ext.write_text(
            f"subjectAltName=DNS:{dns}\nextendedKeyUsage=serverAuth,clientAuth\n"
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n",
            encoding="utf-8",
        )
        _run_openssl(folder, "req", "-new", "-newkey", "rsa:2048", "-nodes",
                     "-keyout", str(key), "-out", str(csr),
                     "-subj", f"/CN={dns}")
        _run_openssl(folder, "x509", "-req", "-in", str(csr),
                     "-CA", str(ca), "-CAkey", str(ca_key), "-CAcreateserial",
                     "-out", str(cert), "-days", "1", "-sha256", "-extfile", str(ext))
        files[role + "_key"] = key
        files[role + "_cert"] = cert
    return files


def _transport_round(
    *, files: dict[str, Path], subjects: dict[str, Path],
    intent: Path, ledger: Path, decision: Path, observation: Path,
    replay_expected: bool,
) -> dict:
    tls = [sys.executable, str(MAIN)]
    server_argv = [
        *tls, "serve",
        "--bind", "127.0.0.1", "--port", "0",
        "--ca", str(files["ca"]),
        "--cert", str(files["server_cert"]),
        "--key", str(files["server_key"]),
        "--intent", str(intent), "--ledger", str(ledger),
        "--output", str(decision), "--transport-report", str(observation),
    ]
    server = subprocess.Popen(
        server_argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    client = None
    try:
        line = server.stdout.readline().strip()
        matched = re.fullmatch(r"LISTEN_PORT=([1-9][0-9]*)", line)
        if matched is None:
            raise RuntimeError(f"authenticated receiver did not start: {line!r}")
        port = int(matched.group(1))
        client_argv = [
            *tls, "send", "--host", "127.0.0.1", "--port", str(port),
            "--ca", str(files["ca"]),
            "--cert", str(files["client_cert"]),
            "--key", str(files["client_key"]),
        ]
        for name in receiver.SUBJECTS:
            client_argv.extend(["--" + name.replace("_", "-"), str(subjects[name])])
        client = subprocess.run(
            client_argv, capture_output=True, text=True, check=False, timeout=MAX_T,
        )
        server_out, server_err = server.communicate(timeout=MAX_T)
        if client.returncode:
            raise RuntimeError(f"reliable TLS client failed: {client.stderr[-900:]}")
        if "MAILCPU_PROOF_FRAMES_ACKED:" not in client.stdout:
            raise RuntimeError("client did not observe complete reliable-channel delivery ACKs")
        if replay_expected:
            if server.returncode == 0 or "replayed receipt" not in server_err:
                raise RuntimeError(
                    f"second receiver unexpectedly admitted or rejected for wrong reason: {server_err[-900:]}"
                )
            return {"outcome": "replay_rejected_after_fresh_process",
                    "transport_acked": True}
        if server.returncode:
            raise RuntimeError(f"proof recipient rejected live transfer: {server_err[-1800:]}")
        if "MAILCPU_PROOF_RECIPIENT_ACCEPTED:" not in server_out:
            raise RuntimeError("recipient did not issue its independently verified decision")
        report = term._read(observation)
        term._bind_digest(report, "mTLS transport observation")
        if report.get("status") != "mutual_tls_reliable_frames_delivered_and_independently_verified":
            raise RuntimeError("invalid mTLS transfer observation")
        if report.get("negotiated_tls_version") not in ("TLSv1.2", "TLSv1.3"):
            raise RuntimeError("missing authenticated TLS protocol evidence")
        accepted = term._read(decision)
        term._bind_digest(accepted, "independent receiver decision")
        if accepted.get("status") != "accepted_once_after_independent_verification":
            raise RuntimeError("received proof is not an independently accepted VGI receipt")
        if accepted["receipt_ref"] != report.get("recipient_proof_receipt_ref"):
            raise RuntimeError("transport and proof receipt observations disagree")
        return {
            "outcome": "proof_independently_accepted",
            "transport_acked": True,
            "tls_version": report["negotiated_tls_version"],
            "frames": report["frame_count"],
            "receipt_ref": accepted["receipt_ref"],
            "recipient_decision_digest": accepted["document_digest"],
        }
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in receiver.SUBJECTS:
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    for name in ("intent", "ledger", "decision", "transport-report", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    subjects = {name: getattr(args, name) for name in receiver.SUBJECTS}
    try:
        with TemporaryDirectory(prefix="ecpu-proof-tls-certs-") as temp:
            certificates = _certs(Path(temp))
            first = _transport_round(
                files=certificates, subjects=subjects, intent=args.intent,
                ledger=args.ledger, decision=args.decision,
                observation=args.transport_report, replay_expected=False,
            )
            second = _transport_round(
                files=certificates, subjects=subjects, intent=args.intent,
                ledger=args.ledger, decision=args.decision,
                observation=args.transport_report, replay_expected=True,
            )
        with sqlite3.connect(args.ledger) as db:
            admitted = db.execute(
                "SELECT COUNT(*) FROM accepted_proof_transfers"
            ).fetchone()[0]
        if admitted != 1:
            raise RuntimeError("second mTLS delivery changed durable proof admission count")
        evidence = {
            "format": "in-formation.ecpu-vgi-proof-transport-live-experiment/0.1",
            "transport": "E-CPU SocketTransport + ReliableChannel over mTLS",
            "tls_ca": "ephemeral local testing-only CA, not a production trust anchor",
            "communication": "two separate Python processes over loopback TCP on one GitHub runner",
            "first": first, "second": second,
            "durable_sqlite_admissions": admitted,
            "issuer_crypto_authority": "GitHub/Sigstore checks performed by receiving process, not mailcpu",
            "scope_warning": "not a second physical computer or internet path; no global replay consensus",
        }
        term._write(args.output, {**evidence, "document_digest": term.digest(evidence)})
        print("ECPU_MTLS_PROOF_TRANSFER_ACCEPTED_AND_REPLAY_REJECTED")
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError,
            receiver.ReceiverReject) as exc:
        parser.exit(1, f"ECPU_PROOF_TRANSFER_DEMO_REJECTED:{exc}\n")


if __name__ == "__main__":
    main()
