"""SNC-004B third runner: independently reconstruct live mTLS session evidence.

An accepted mathematical result and a matching two-party transcript do not
grant execution effects, issuer trust, or physical-machine attestation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from federated_auditor import audit
from persistent_host import canonical, require, sha
from snc004b_identity import inspect_endpoint, inspect_peer, certificate_sha256
from snc004b_live import CLIENT_REPORT, SERVER_REPORT, RESPONSE_SCHEMA, addressing


class AuditRejected(ValueError):
    pass


def check(ok: bool, why: str) -> None:
    if not ok:
        raise AuditRejected(why)


def third_audit(*, capsule: Path, client_path: Path,
                server_path: Path, client_bootstrap: Path,
                server_bootstrap: Path, expected_source: object,
                expected_model: str = "clamp",
                expected_coordinate: str = "3/4",
                expected_request_id: str = "snc004b-observation") -> dict:
    client = json.loads(client_path.read_bytes())
    server = json.loads(server_path.read_bytes())
    check(type(client) is dict and client.get("schema") == CLIENT_REPORT
          and client.get("mode") == "overlay", "invalid client overlay record")
    check(type(server) is dict and server.get("schema") == SERVER_REPORT
          and server.get("mode") == "overlay", "invalid server overlay record")
    sender_cert = client_bootstrap / "client-cert.pem"
    receiver_cert = server_bootstrap / "server-cert.pem"
    inspect_peer(cert=sender_cert,
                 record=client_bootstrap / "client-bootstrap.json",
                 expected_role="client")
    advertised_server = inspect_endpoint(directory=server_bootstrap)

    check(client["local_certificate_sha256"] ==
          certificate_sha256(sender_cert) ==
          server["peer_certificate_sha256"], "client TLS public certificate mismatch")
    check(server["local_certificate_sha256"] ==
          certificate_sha256(receiver_cert) ==
          client["peer_certificate_sha256"], "server TLS public certificate mismatch")
    try:
        client_local = addressing(client["local_socket_ipv4"], overlay=True)
        client_remote = addressing(client["peer_socket_ipv4"], overlay=True)
        server_local = addressing(server["local_socket_ipv4"], overlay=True)
        server_remote = addressing(server["peer_socket_ipv4"], overlay=True)
    except (KeyError, ValueError) as exc:
        raise AuditRejected("missing or non-overlay socket endpoints") from exc
    check(client_remote == server_local == advertised_server and
          client_local == server_remote and client_local != server_local,
          "reciprocal peer TCP addresses do not match advertised Tailscale path")
    check(client["tls_version"] in ("TLSv1.2", "TLSv1.3") and
          server["tls_version"] in ("TLSv1.2", "TLSv1.3"),
          "mutual TLS was not negotiated")
    check(client["nonce"] == server["nonce"] and
          len(client["nonce"]) == 32, "session challenge mismatch")
    body = capsule.read_bytes()
    check(0 < len(body) <= 128 * 1024 and
          client["document_sha256"] == server["document_sha256"] == sha(body) and
          client["bytes_sent_application"] == server["bytes_received_application"] ==
          len(body) and
          client["sent_frame_count"] == server["received_frame_count"],
          "transcript body or frame count mismatch")
    response = client["response"]
    check(type(response) is dict and
          response.get("schema") == RESPONSE_SCHEMA and
          response.get("accepted") is True and
          response.get("nonce") == client["nonce"] and
          response.get("document_sha256") == sha(body) and
          response.get("request_id") == expected_request_id and
          response.get("result") == server["result"],
          "recipient response differs from independent server report")
    check(server["report_durable_before_final_ack"] is True and
          client["external_execution_authorized"] is False and
          server["external_execution_authorized"] is False,
          "application durability / external authorization mismatch")

    mathematical = audit(
        body=body, receiver_report=canonical(server["result"]),
        expected_source=expected_source,
        expected_model=expected_model,
        expected_coordinate=expected_coordinate,
        expected_request_id=expected_request_id,
    )
    return {
        "schema": "in-formation-space.snc004b.third-host-live-audit/0.1",
        "status": "matched-overlay-mtls-and-mathematical-reconstruction",
        "model_sha256": mathematical["network_sha256"],
        "source_sha256": mathematical["semantic_sha256"],
        "document_sha256": sha(body),
        "observation_outputs": mathematical["independent_outputs"],
        "sender_and_receiver_certificate_fingerprints_match_bootstrap": True,
        "client_server_nonce_matches": True,
        "both_hosts_report_overlay_mode": True,
        "reciprocal_overlay_socket_addresses_match": True,
        "client_socket_ipv4": client_local,
        "server_socket_ipv4": server_local,
        "distinct_hosted_runner_jobs": True,
        "distinct_physical_hosts_attested": False,
        "external_source_issuer_verified": False,
        "third_party_effect_authorized": False,
        "bootstrap": "same-run GitHub artifacts, not external issuer signing",
        "live_network": "E-CPU ReliableChannel over TLS and Tailscale if hosts' records are truthful",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("capsule", "client-report", "server-report",
                 "client-bootstrap", "server-bootstrap", "examples", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        examples = json.loads(args.examples.read_bytes())
        report = third_audit(
            capsule=args.capsule, client_path=args.client_report,
            server_path=args.server_report,
            client_bootstrap=args.client_bootstrap,
            server_bootstrap=args.server_bootstrap,
            expected_source=examples["clamp_0_1"],
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, "SNC004B_AUDIT_REJECTED:" + str(exc)[:350] + "\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(report))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
