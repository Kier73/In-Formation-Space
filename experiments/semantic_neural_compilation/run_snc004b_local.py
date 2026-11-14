"""SNC-004B: actual E-CPU mTLS loopback protocol and negative policy probe.

This is a same-physical-host integration gate. It does not establish that
a Tailscale peer is reachable; the overlay mode is a separate manual CI job.
"""
from __future__ import annotations

import json
from pathlib import Path
import os
from unittest.mock import patch
import re
import subprocess
import sys
import tempfile
import time

from federated_auditor import audit
from federated_pipeline import produce, policy_from_local_source
from snc004b_identity import make_identity, inspect_peer, make_endpoint, inspect_endpoint
from independent_certificate_checker import hash_bytes
from persistent_host import POLICY_SCHEMA, canonical
from run_semantic_transit import test_certificates

HERE = Path(__file__).resolve().parent
CLI = HERE / "snc004b_live.py"


def session(
    folder: Path, certificates: dict[str, Path], *,
    capsule: Path, policy: Path, database: Path, name: str, expected_success: bool,
) -> dict:
    server_report = folder / (name + "-server.json")
    client_report = folder / (name + "-client.json")
    server_cmd = [
        sys.executable, str(CLI), "serve",
        "--bind", "127.0.0.1", "--port", "0",
        "--database", str(database), "--policy", str(policy),
        "--cert", str(certificates["server_cert"]),
        "--key", str(certificates["server_key"]),
        "--peer-cert", str(certificates["client_cert"]),
        "--output", str(server_report),
    ]
    if "ca" in certificates:
        server_cmd.extend(["--trust-root", str(certificates["ca"])])
    process = subprocess.Popen(server_cmd, text=True, bufsize=1,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        line = process.stdout.readline().strip()
        found = re.fullmatch(r"LISTEN_PORT=([1-9][0-9]*)", line)
        if not found:
            raise RuntimeError("local mTLS server did not start: " + line)
        client_cmd = [
            sys.executable, str(CLI), "send",
            "--connect", "127.0.0.1", "--port", found.group(1),
            "--capsule", str(capsule), "--model", "clamp",
            "--coordinate", "3/4", "--request-id", "live1",
            "--cert", str(certificates["client_cert"]),
            "--key", str(certificates["client_key"]),
            "--peer-cert", str(certificates["server_cert"]),
            "--output", str(client_report),
        ]
        if "ca" in certificates:
            client_cmd.extend(["--trust-root", str(certificates["ca"])])
        sender = subprocess.run(client_cmd, capture_output=True,
                                text=True, timeout=55, check=False)
        out, err = process.communicate(timeout=55)
        if process.returncode:
            raise RuntimeError("server failure: " + err[-1000:])
        if not client_report.is_file():
            raise RuntimeError("client application decision absent: " + sender.stderr[-1000:])
        client = json.loads(client_report.read_text())
        if client["response"]["accepted"] != expected_success:
            raise RuntimeError("unexpected receiver policy decision: " + sender.stderr[-800:])
        if expected_success:
            if sender.returncode:
                raise RuntimeError("client failed authenticated positive transfer: " +
                                   sender.stderr[-800:])
            if not server_report.exists():
                raise RuntimeError("server verified report missing")
            server = json.loads(server_report.read_text())
            if server["result"] != client["response"]["result"] or \
                    server["nonce"] != client["nonce"] or \
                    client["peer_certificate_sha256"] != server["local_certificate_sha256"] or \
                    server["peer_certificate_sha256"] != client["local_certificate_sha256"] or \
                    server["received_frame_count"] != client["sent_frame_count"]:
                raise RuntimeError("bidirectional proof/peer transcript mismatch")
            return {"client": client, "server": server}
        if sender.returncode == 0 or server_report.exists():
            raise RuntimeError("denied request was mislabeled accepted")
        return {"client": client, "server": None}
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def run(destination: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="snc004b-live-local-") as tmp:
        root = Path(tmp)
        certs = test_certificates(root)
        source_root = root / "producer"
        produce(source_root)
        capsule = source_root / "portable-model.json"
        receiver_root = root / "receiver"
        receiver_root.mkdir()
        receiver_policy = receiver_root / "receiver-policy.json"
        policy_from_local_source(receiver_policy, "clamp_0_1", "clamp")
        success = session(
            root, certs, capsule=capsule, policy=receiver_policy,
            database=receiver_root / "models.sqlite3", name="accepted",
            expected_success=True,
        )
        # The manual overlay uses independently generated self-signed,
        # exact-peer-pinned identities, unlike this first shared-CA test.
        # Verify that actual handshake mode on loopback as well.
        with patch.dict(os.environ, {
            "GITHUB_RUN_ID": os.environ.get("GITHUB_RUN_ID", "12345"),
            "GITHUB_RUN_ATTEMPT": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        }):
            make_identity(directory=root / "identity-server", role="server")
            make_identity(directory=root / "identity-client", role="client")
            inspect_peer(
                cert=root / "identity-client/client-cert.pem",
                record=root / "identity-client/client-bootstrap.json",
                expected_role="client",
            )
            make_endpoint(directory=root / "identity-server", ip="100.64.10.20")
            if inspect_endpoint(directory=root / "identity-server") != "100.64.10.20":
                raise RuntimeError("self-signed server endpoint not pinned")
        independent_certs = {
            "client_cert": root / "identity-client/client-cert.pem",
            "client_key": root / "identity-client/client-key.pem",
            "server_cert": root / "identity-server/server-cert.pem",
            "server_key": root / "identity-server/server-key.pem",
        }
        self_signed = session(
            root, independent_certs, capsule=capsule,
            policy=receiver_policy,
            database=receiver_root / "models-self-signed.sqlite3",
            name="independent-self-signed", expected_success=True,
        )
        audited = audit(
            body=capsule.read_bytes(),
            receiver_report=canonical(success["server"]["result"]),
            expected_source=json.loads((HERE / "examples.json").read_text())["clamp_0_1"],
            expected_model="clamp", expected_coordinate="3/4",
            expected_request_id="live1",
        )
        denied_policy = root / "denied-policy.json"
        denied_policy.write_bytes(canonical({
            "schema": POLICY_SCHEMA,
            "models": {"clamp": hash_bytes(
                json.loads((HERE / "examples.json").read_text())["identity"])},
        }))
        refusal = session(
            root, certs, capsule=capsule, policy=denied_policy,
            database=root / "denied.sqlite3", name="refused",
            expected_success=False,
        )
        result = {
            "schema": "in-formation-space.snc004b.local-live-evidence/0.1",
            "status": "authenticated-local-transfer-and-policy-denial-verified",
            "topology": "separate sender and receiver Python processes, same physical host",
            "real_transport": "MailCPU mTLS SocketTransport with E-CPU ReliableChannel",
            "accepted": {
                "capsule_application_bytes": success["client"]["bytes_sent_application"],
                "frame_count": success["client"]["sent_frame_count"],
                "tls_version": success["client"]["tls_version"],
                "network_sha256": audited["network_sha256"],
                "independent_outputs": audited["independent_outputs"],
                "receiver_import_verification_ns":
                    success["server"]["result"]["import"]["independent_certificate_verification_ns"],
                "receiver_observation_sha256":
                    success["server"]["result"]["observation"]["receipt_sha256"],
            },
            "independent_per_host_self_signed_test": {
                "tls_version": self_signed["client"]["tls_version"],
                "peer_pin_checked": self_signed["client"]["peer_certificate_sha256"] ==
                    self_signed["server"]["local_certificate_sha256"],
                "observation_output": self_signed["server"]["result"]["observation"]["receipt"]["outputs"],
                "no_shared_test_ca": True,
            },
            "denied": {
                "accepted": refusal["client"]["response"]["accepted"],
                "reason": refusal["client"]["response"]["reason"],
                "durable_success_report_created": False,
            },
            "physical_host_count": 1,
            "cross_host_overlay_verified": False,
            "external_execution_authorized": False,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical(result))
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
