from __future__ import annotations

import copy
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mailcpu.reliability import ReliabilityPolicy, ReliableChannel
from mailcpu.socket_transport import SocketTransport
from mailcpu.temporal import ClockDomain, TemporalContext, TemporalProfile

import direct_mtls_operation_path as direct


def runner_env(
    role: str,
    runner_name: str,
    runner_os: str = "Linux",
    workflow_path: str | None = None,
) -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": direct.REPOSITORY,
        "GITHUB_JOB": role,
        "GITHUB_WORKFLOW_REF": (
            f"{direct.REPOSITORY}/{workflow_path or direct.WORKFLOW_PATH}@{direct.SOURCE_REF}"
        ),
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_REF": direct.SOURCE_REF,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_NUMBER": "42",
        "RUNNER_NAME": runner_name,
        "RUNNER_OS": runner_os,
        "RUNNER_ARCH": "X64",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }


class DirectMTLSOperationPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client = direct.generate_identity(
            "client_host",
            self.root / "client",
            runner_env("client_host", "client-vm"),
        )
        self.server = direct.generate_identity(
            "server_host",
            self.root / "server",
            runner_env("server_host", "server-vm", "Windows"),
        )
        self.verifier_env = runner_env("verifier_host", "verifier-vm", "macOS")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_ihp006_workflow_identity_is_allowlisted_but_other_workflows_are_rejected(self) -> None:
        env = runner_env(
            "server_host", "server-vm", workflow_path=direct.TAILSCALE_WORKFLOW_PATH
        )
        host = direct.host_metadata("server_host", env)
        self.assertEqual(host["workflow_ref"], (
            f"{direct.REPOSITORY}/{direct.TAILSCALE_WORKFLOW_PATH}@{direct.SOURCE_REF}"
        ))
        direct._validate_host_metadata(host, "server_host")

        env["GITHUB_WORKFLOW_REF"] = (
            f"{direct.REPOSITORY}/.github/workflows/unapproved.yml@{direct.SOURCE_REF}"
        )
        with self.assertRaisesRegex(direct.DirectMTLSError, "allowlist"):
            direct.host_metadata("server_host", env)

    def test_tailscale_overlay_address_is_restricted_to_the_cgnat_ipv4_range(self) -> None:
        self.assertEqual(
            direct._validate_tailscale_ipv4("100.73.20.11"), "100.73.20.11"
        )
        for invalid in ("203.0.113.4", "100.128.0.1", "2001:db8::1", "not-an-ip"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(direct.DirectMTLSError, "Tailscale overlay address"):
                    direct._validate_tailscale_ipv4(invalid)

    def test_ihp006_prepare_server_cannot_fall_back_to_public_ip(self) -> None:
        env = runner_env(
            "server_host", "server-vm", workflow_path=direct.TAILSCALE_WORKFLOW_PATH
        )
        host = direct.host_metadata("server_host", env)
        with patch.object(direct, "host_metadata", return_value=host):
            with self.assertRaisesRegex(direct.DirectMTLSError, "public-IP fallback is disabled"):
                direct.prepare_server(self.root / "no-bootstrap")

    def test_ephemeral_certificates_are_role_and_run_bound(self) -> None:
        self.assertNotEqual(
            self.client["certificate_sha256"],
            self.server["certificate_sha256"],
        )
        self.assertEqual(self.client["dns_identity"], "ihp002-client-123456789.internal")
        self.assertEqual(self.server["dns_identity"], "ihp002-server-123456789.internal")
        self.assertEqual(
            direct.certificate_sha256(self.client["certificate_path"]),
            self.client["certificate_sha256"],
        )
        self.assertEqual(
            direct.certificate_sha256(self.server["certificate_path"]),
            self.server["certificate_sha256"],
        )
        self.assertEqual(self.client["private_key_path"].stat().st_mode & 0o777, 0o600)

        predicate_path = self.root / "client-cert.predicate.json"
        predicate = direct.write_certificate_predicate(
            self.client["certificate_path"],
            predicate_path,
            "client_host",
            runner_env("client_host", "client-vm"),
        )
        direct._validate_certificate_predicate(
            predicate,
            self.client["certificate_path"],
            "client_host",
            "123456789",
            "1",
        )
        forged = copy.deepcopy(predicate)
        forged["dns_identity"] = "other-host.internal"
        with self.assertRaisesRegex(direct.DirectMTLSError, "DNS identity"):
            direct._validate_certificate_predicate(
                forged,
                self.client["certificate_path"],
                "client_host",
                "123456789",
                "1",
            )

    def test_ed25519_signed_document_binds_exact_canonical_core(self) -> None:
        signed = direct._signed_document(
            {"schema": "test", "value": 7, "sequence": 1},
            self.client["private_key_path"],
        )
        core = direct._verify_signed_document(signed, self.client["certificate_path"])
        self.assertEqual(core["value"], 7)
        altered = copy.deepcopy(signed)
        altered["core"]["value"] = 8
        with self.assertRaisesRegex(direct.DirectMTLSError, "digest"):
            direct._verify_signed_document(altered, self.client["certificate_path"])

    def test_signed_endpoint_advertisement_is_bound_to_server_certificate(self) -> None:
        client_host = self.client["host"]
        server_host = self.server["host"]
        core = {
            "schema": direct.ENDPOINT_SCHEMA,
            "path_id": "run-123456789-ihp002-direct-mtls",
            "run_id": "123456789",
            "run_attempt": "1",
            "server_host": server_host,
            "host": "203.0.113.8",
            "port": direct.LISTEN_PORT,
            "dns_identity": self.server["dns_identity"],
            "server_cert_sha256": self.server["certificate_sha256"],
            "client_actor_id": client_host["actor_id"],
            "client_cert_sha256": self.client["certificate_sha256"],
        }
        signed = direct._signed_document(core, self.server["private_key_path"])
        verified = direct._verify_endpoint_advertisement(signed, self.server["certificate_path"])
        self.assertEqual(verified["host"], "203.0.113.8")
        altered = copy.deepcopy(signed)
        altered["core"]["host"] = "203.0.113.9"
        with self.assertRaisesRegex(direct.DirectMTLSError, "digest"):
            direct._verify_endpoint_advertisement(altered, self.server["certificate_path"])

    def test_ihp006_endpoint_verifier_rejects_a_public_server_address(self) -> None:
        identity = direct.generate_identity(
            "server_host",
            self.root / "server-ihp006",
            runner_env(
                "server_host", "server-vm", workflow_path=direct.TAILSCALE_WORKFLOW_PATH
            ),
        )
        core = {
            "schema": direct.ENDPOINT_SCHEMA,
            "path_id": "run-123456789-ihp002-direct-mtls",
            "run_id": "123456789",
            "run_attempt": "1",
            "server_host": identity["host"],
            "host": "203.0.113.8",
            "port": direct.LISTEN_PORT,
            "dns_identity": identity["dns_identity"],
            "server_cert_sha256": identity["certificate_sha256"],
            "client_actor_id": self.client["host"]["actor_id"],
            "client_cert_sha256": self.client["certificate_sha256"],
        }
        signed = direct._signed_document(core, identity["private_key_path"])
        with self.assertRaisesRegex(direct.DirectMTLSError, "100.64.0.0/10"):
            direct._verify_endpoint_advertisement(signed, identity["certificate_path"])

        core["host"] = "100.73.20.22"
        signed = direct._signed_document(core, identity["private_key_path"])
        verified = direct._verify_endpoint_advertisement(signed, identity["certificate_path"])
        self.assertEqual(verified["host"], "100.73.20.22")

    def test_client_endpoint_commitment_uses_signed_envelope_not_just_core(self) -> None:
        core = {
            "schema": direct.ENDPOINT_SCHEMA,
            "path_id": "run-123456789-ihp002-direct-mtls",
            "run_id": "123456789",
            "run_attempt": "1",
            "server_host": self.server["host"],
            "host": "203.0.113.8",
            "port": direct.LISTEN_PORT,
            "dns_identity": self.server["dns_identity"],
            "server_cert_sha256": self.server["certificate_sha256"],
            "client_actor_id": self.client["host"]["actor_id"],
            "client_cert_sha256": self.client["certificate_sha256"],
        }
        signed = direct._signed_document(core, self.server["private_key_path"])
        path = self.root / "server-endpoint.json"
        direct.write_json(path, signed)
        verified_core, commitment = direct._load_signed_endpoint(
            path,
            self.server["certificate_path"],
        )
        self.assertEqual(verified_core, core)
        self.assertEqual(commitment, direct.digest_object(signed))
        self.assertNotEqual(commitment, direct.digest_object(core))


    def test_mutual_tls_socket_transport_and_reliable_channel_cross_real_tcp_socket(self) -> None:
        listener = SocketTransport.listen("127.0.0.1", 0)
        server_context = direct._server_context(
            self.server["certificate_path"],
            self.server["private_key_path"],
            self.client["certificate_path"],
        )
        client_context = direct._client_context(
            self.client["certificate_path"],
            self.client["private_key_path"],
            self.server["certificate_path"],
        )
        result: dict[str, object] = {}
        errors: list[BaseException] = []

        def accept() -> None:
            try:
                result["transport"] = direct.accept_mutual_tls(
                    listener,
                    "server-host",
                    "client-host",
                    server_context,
                    expected_peer_dns=self.client["dns_identity"],
                )
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=accept, daemon=True)
        thread.start()
        client_transport = None
        server_transport = None
        try:
            client_transport = direct.connect_mutual_tls(
                "127.0.0.1",
                listener.getsockname()[1],
                "client-host",
                "server-host",
                client_context,
                server_hostname=self.server["dns_identity"],
            )
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            server_transport = result["transport"]
            self.assertIsInstance(server_transport, SocketTransport)
            self.assertEqual(
                direct._peer_certificate_sha256(client_transport),
                self.server["certificate_sha256"],
            )
            self.assertEqual(
                direct._peer_certificate_sha256(server_transport),
                self.client["certificate_sha256"],
            )

            policy = ReliabilityPolicy(lease_ticks=2, max_attempts=4, window_size=4)
            sender = ReliableChannel(
                client_transport,
                "client-host",
                "server-host",
                direct.DATA_CHANNEL,
                policy,
            )
            receiver = ReliableChannel(
                server_transport,
                "server-host",
                "server-host",
                direct.DATA_CHANNEL,
                policy,
                peer="client-host",
            )
            self.assertEqual(sender.send({"operation": "direct-mtls", "sequence": 1}), 1)
            deadline = time.monotonic() + 3
            delivered = None
            while time.monotonic() < deadline:
                delivered = receiver.receive()
                if delivered is not None:
                    break
                time.sleep(0.005)
            self.assertEqual(delivered, (1, {"operation": "direct-mtls", "sequence": 1}))
            direct._wait_for_ack(sender, (1,), timeout_seconds=3)
            self.assertEqual(sender.pending_sequences(), ())
        finally:
            if client_transport is not None and not client_transport.closed:
                client_transport.close()
            if server_transport is not None and not server_transport.closed:
                server_transport.close()
            listener.close()
            thread.join(timeout=1)

    def test_signed_handoff_envelope_reconstructs_against_pinned_client_certificate(self) -> None:
        host = self.client["host"]
        context = TemporalContext(
            host["actor_id"],
            TemporalProfile(frozenset({ClockDomain.MONOTONIC, ClockDomain.CAUSAL})),
            segment=0,
        )
        recorder = direct._recorder(host, context)
        attempt = "run-123456789-attempt-1"
        recorder.measure(
            attempt_id=attempt,
            span_id="client-operation",
            operation_id="client.prepare",
            operation=lambda: direct._local_work("payload"),
            context={"role": "client_host"},
        )
        span = recorder.spans[-1]
        context.emit_causal_stamp()
        frame = context.observe().to_dict()
        payload = direct.build_handoff_payload(
            path_id="run-123456789-ihp002-direct-mtls",
            attempt_id=attempt,
            predecessor_span_digest=span["span_digest"],
            sender_completion_frame=frame,
        )
        core = {
            "schema": direct.HANDOFF_SCHEMA,
            "path_id": "run-123456789-ihp002-direct-mtls",
            "attempt_id": attempt,
            "channel_id": direct.DATA_CHANNEL,
            "message_sequence": 1,
            "sender_host": host,
            "sender_cert_sha256": self.client["certificate_sha256"],
            "operation_span": span,
            "sender_completion_frame": frame,
            "handoff_payload": payload,
        }
        signed = direct._signed_document(core, self.client["private_key_path"])
        checked = direct._verify_handoff_envelope(
            signed,
            self.client["certificate_path"],
            expected_sequence=1,
        )
        self.assertEqual(checked["handoff_payload"], payload)
        forged = copy.deepcopy(signed)
        forged["core"]["message_sequence"] = 2
        with self.assertRaisesRegex(direct.DirectMTLSError, "digest"):
            direct._verify_handoff_envelope(
                forged,
                self.client["certificate_path"],
                expected_sequence=1,
            )

    def test_direct_reconstruction_report_binds_both_host_signatures_and_tls_certificates(self) -> None:
        client_host = self.client["host"]
        server_host = self.server["host"]
        attempt = "run-123456789-attempt-1"
        path_id = "run-123456789-ihp002-direct-mtls"
        channel_id = direct.DATA_CHANNEL

        client_context = TemporalContext(
            client_host["actor_id"],
            TemporalProfile(frozenset({ClockDomain.MONOTONIC, ClockDomain.CAUSAL})),
            segment=0,
        )
        client_recorder = direct._recorder(client_host, client_context)
        client_recorder.measure(
            attempt_id=attempt,
            span_id="client-operation",
            operation_id="client.prepare",
            operation=lambda: direct._local_work("client"),
            context={"role": "client_host"},
        )
        predecessor = client_recorder.spans[-1]
        client_context.emit_causal_stamp()
        sender_frame = client_context.observe().to_dict()
        payload = direct.build_handoff_payload(
            path_id=path_id,
            attempt_id=attempt,
            predecessor_span_digest=predecessor["span_digest"],
            sender_completion_frame=sender_frame,
        )
        envelope_core = {
            "schema": direct.HANDOFF_SCHEMA,
            "path_id": path_id,
            "attempt_id": attempt,
            "channel_id": channel_id,
            "message_sequence": 1,
            "sender_host": client_host,
            "sender_cert_sha256": self.client["certificate_sha256"],
            "operation_span": predecessor,
            "sender_completion_frame": sender_frame,
            "handoff_payload": payload,
        }
        signed_envelope = direct._signed_document(envelope_core, self.client["private_key_path"])

        server_context = TemporalContext(
            server_host["actor_id"],
            TemporalProfile(frozenset({ClockDomain.MONOTONIC, ClockDomain.CAUSAL})),
            segment=0,
        )
        server_context.receive_causal_stamp(
            direct.CausalStamp.from_dict(sender_frame["causal"])
        )
        receiver_start = server_context.observe().to_dict()
        server_recorder = direct._recorder(server_host, server_context)
        server_recorder.measure(
            attempt_id=attempt,
            span_id="server-operation",
            operation_id="server.continue",
            operation=lambda: direct._local_work("server"),
            context={"role": "server_host"},
        )
        successor = server_recorder.spans[-1]
        witness = direct.build_causal_handoff_witness(
            payload=payload,
            successor_span_digest=successor["span_digest"],
            channel_id=channel_id,
            message_sequence=1,
            received_sequence=1,
            receiver_start_frame=receiver_start,
        )
        receipt_core = {
            "schema": direct.RECEIPT_SCHEMA,
            "path_id": path_id,
            "attempt_id": attempt,
            "channel_id": channel_id,
            "message_sequence": 1,
            "sender_actor_id": client_host["actor_id"],
            "receiver_actor_id": server_host["actor_id"],
            "sender_cert_sha256": self.client["certificate_sha256"],
            "receiver_cert_sha256": self.server["certificate_sha256"],
            "sender_envelope_digest": signed_envelope["signed_digest"],
            "predecessor_span_digest": predecessor["span_digest"],
            "successor_span_digest": successor["span_digest"],
            "sender_completion_frame": sender_frame,
            "receiver_start_frame": receiver_start,
            "receiver_operation_span": successor,
            "handoff_witness": witness,
        }
        signed_receipt = direct._signed_document(receipt_core, self.server["private_key_path"])
        endpoint_core = {
            "schema": direct.ENDPOINT_SCHEMA,
            "path_id": path_id,
            "run_id": "123456789",
            "run_attempt": "1",
            "server_host": server_host,
            "host": "203.0.113.8",
            "port": direct.LISTEN_PORT,
            "dns_identity": self.server["dns_identity"],
            "server_cert_sha256": self.server["certificate_sha256"],
            "client_actor_id": client_host["actor_id"],
            "client_cert_sha256": self.client["certificate_sha256"],
        }
        endpoint = direct._signed_document(endpoint_core, self.server["private_key_path"])
        endpoint_digest = direct.digest_object(endpoint)
        client_record = direct._make_record(
            role="client_host",
            host=client_host,
            status="direct_mtls_verified",
            certificate_sha256_value=self.client["certificate_sha256"],
            operation_span=predecessor,
            temporal_frame=sender_frame,
            endpoint_digest=endpoint_digest,
            handoff_envelope=signed_envelope,
            receiver_receipt=signed_receipt,
            peer_certificate_sha256=self.server["certificate_sha256"],
        )
        server_record = direct._make_record(
            role="server_host",
            host=server_host,
            status="direct_mtls_verified",
            certificate_sha256_value=self.server["certificate_sha256"],
            operation_span=successor,
            temporal_frame=receiver_start,
            endpoint_digest=endpoint_digest,
            received_envelope=signed_envelope,
            receiver_receipt=signed_receipt,
            peer_certificate_sha256=self.client["certificate_sha256"],
        )
        verifier_host = direct.host_metadata("verifier_host", self.verifier_env)
        placeholder = {"verified": True, "subject_sha256": "0" * 64}
        report = direct.build_report(
            client_record,
            server_record,
            self.client["certificate_path"],
            self.server["certificate_path"],
            endpoint,
            placeholder,
            placeholder,
            placeholder,
            placeholder,
            verifier_host,
        )
        self.assertEqual(report["status"], "direct_mtls_verified")
        self.assertEqual(report["causal_reconstruction"]["edge_count"], 1)
        self.assertIsNone(report["duration"]["combined_cross_host_elapsed_ns"])
        self.assertEqual(
            report["causal_reconstruction"]["topological_order"],
            [predecessor["span_digest"], successor["span_digest"]],
        )

        changed = copy.deepcopy(client_record)
        changed["peer_certificate_sha256"] = "f" * 64
        core = {key: value for key, value in changed.items() if key != "record_digest"}
        changed["record_digest"] = direct.digest_object(core)
        with self.assertRaisesRegex(direct.DirectMTLSError, "TLS peer fingerprints"):
            direct.build_report(
                changed,
                server_record,
                self.client["certificate_path"],
                self.server["certificate_path"],
                endpoint,
                placeholder,
                placeholder,
                placeholder,
                placeholder,
                verifier_host,
            )

    def test_artifact_attestation_command_pins_workflow_and_hosted_runner_policy(self) -> None:
        command = direct._attestation_command(
            self.client["certificate_path"],
            direct.CERT_PREDICATE_TYPE,
            "gh",
        )
        self.assertIn("--repo", command)
        self.assertIn(direct.REPOSITORY, command)
        self.assertIn("--signer-workflow", command)
        self.assertIn(direct.SIGNER_WORKFLOW, command)
        self.assertIn("--source-ref", command)
        self.assertIn(direct.SOURCE_REF, command)
        self.assertIn("--deny-self-hosted-runners", command)


if __name__ == "__main__":
    unittest.main()
