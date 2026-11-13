from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tailscale_overlay_probe as overlay


def runner_env(role: str, runner: str, system: str = "Linux") -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": overlay.REPOSITORY,
        "GITHUB_JOB": role,
        "GITHUB_RUN_ID": "789012345",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_NUMBER": "88",
        "GITHUB_WORKFLOW_REF": f"{overlay.REPOSITORY}/{overlay.WORKFLOW_PATH}@{overlay.SOURCE_REF}",
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_REF": overlay.SOURCE_REF,
        "GITHUB_SHA": "a" * 40,
        "RUNNER_NAME": runner,
        "RUNNER_OS": system,
        "RUNNER_ARCH": "X64",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }


class TailscaleOverlayProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client_env = runner_env("client_host", "client-vm")
        self.server_env = runner_env("server_host", "server-vm", "Windows")
        self.verifier_env = runner_env("verifier_host", "verifier-vm", "macOS")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def address(self, role: str, env: dict[str, str], ip: str | None):
        output = self.root / role
        with patch.object(overlay, "_tailscale_ip", return_value=ip or "100.64.0.10"):
            return overlay.create_address(role, output, enabled=ip is not None, env=env), output

    def record(self, address: dict, role: str, *, route: str, status: str, peer: dict | None, peer_attestation: dict | None = None):
        core = {
            "schema": overlay.RECORD_SCHEMA,
            "role": role,
            "host": address["host"],
            "status": status,
            "overlay_provider": "tailscale",
            "overlay_tag": overlay.TAG,
            "overlay_ipv4": address["overlay_ipv4"],
            "address_digest": address["address_digest"],
            "peer_address_digest": None if peer is None else overlay.digest_bytes(overlay.canonical(peer) + b"\n"),
            "peer_role": "server_host" if role == "client_host" else "client_host",
            "peer_overlay_ipv4": None if peer is None else peer["overlay_ipv4"],
            "peer_address_attestation": peer_attestation,
            "route_type": route,
            "ping_count": 0 if route == "not_attempted" else overlay.PING_COUNT,
            "ping_exit_code": None if route == "not_attempted" else (0 if status == "route_observed" else 1),
            "ping_output": "",
            "diagnostic": "fixture",
        }
        return {**core, "record_digest": overlay.digest_object(core)}

    def test_tailscale_route_classification_distinguishes_direct_derp_peer_relay_and_unreachable(self) -> None:
        self.assertEqual(
            overlay.classify_route("pong from node (100.64.0.2) via 198.51.100.5:41641 in 20ms", 0),
            "direct",
        )
        self.assertEqual(
            overlay.classify_route("pong from node (100.64.0.2) via DERP(nyc) in 90ms", 0),
            "derp_relay",
        )
        self.assertEqual(
            overlay.classify_route("pong from node (100.64.0.2) via peer-relay(device-a) in 40ms", 0),
            "peer_relay",
        )
        self.assertEqual(overlay.classify_route("no response from peer", 1), "unreachable")
        self.assertEqual(
            overlay.classify_route(
                "pong via DERP(nyc)\npong via 198.51.100.5:41641",
                0,
            ),
            "direct",
        )

    def test_address_document_is_role_run_tag_and_ip_bound(self) -> None:
        with patch.object(overlay, "_tailscale_ip", return_value="100.73.20.11"):
            address = overlay.create_address(
                "client_host", self.root / "client", enabled=True, env=self.client_env
            )
        self.assertEqual(address["status"], "ready")
        self.assertEqual(address["overlay_ipv4"], "100.73.20.11")
        self.assertEqual(address["overlay_tag"], "tag:ihp003-ci")
        self.assertEqual(
            address["address_digest"],
            overlay.digest_object({k: v for k, v in address.items() if k != "address_digest"}),
        )
        validated = overlay._validate_address(
            address, expected_role="client_host",
            expected_run_id="789012345", expected_attempt="1",
        )
        self.assertEqual(validated["host"]["actor_id"], address["host"]["actor_id"])

        forged = copy.deepcopy(address)
        forged["overlay_ipv4"] = "203.0.113.99"
        with self.assertRaisesRegex(overlay.OverlayProbeError, "digest"):
            overlay._validate_address(
                forged, expected_role="client_host",
                expected_run_id="789012345", expected_attempt="1",
            )

    def test_missing_tailnet_configuration_is_explicit_and_never_claims_a_route(self) -> None:
        address = overlay.create_address(
            "client_host", self.root / "client-missing", enabled=False, env=self.client_env
        )
        self.assertEqual(address["status"], "credentials_missing")
        self.assertIsNone(address["overlay_ipv4"])
        self.assertEqual(address["overlay_tag"], "tag:ihp003-ci")

    def test_report_reconstructs_direct_peer_route_from_two_distinct_host_records(self) -> None:
        client_address, _ = self.address("client_host", self.client_env, "100.64.0.11")
        server_address, _ = self.address("server_host", self.server_env, "100.64.0.22")
        attestation = {"verified": True, "subject_sha256": "a" * 64}
        client_record = self.record(
            client_address, "client_host", route="direct", status="route_observed",
            peer=server_address, peer_attestation=attestation,
        )
        server_record = self.record(
            server_address, "server_host", route="direct", status="route_observed",
            peer=client_address, peer_attestation=attestation,
        )
        verifier = overlay.host_metadata("verifier_host", self.verifier_env)
        report = overlay.build_report(
            client_record, server_record,
            attestation, attestation, attestation, attestation, verifier,
        )
        self.assertEqual(report["status"], "direct_peer_to_peer")
        self.assertEqual(report["client"]["route_type"], "direct")
        self.assertEqual(report["server"]["route_type"], "direct")
        self.assertFalse(report["path_semantics"]["application_payload_sent"])

    def test_report_distinguishes_relayed_overlay_from_direct_path(self) -> None:
        client_address, _ = self.address("client_host", self.client_env, "100.64.0.11")
        server_address, _ = self.address("server_host", self.server_env, "100.64.0.22")
        attestation = {"verified": True, "subject_sha256": "b" * 64}
        client_record = self.record(
            client_address, "client_host", route="derp_relay", status="route_observed",
            peer=server_address, peer_attestation=attestation,
        )
        server_record = self.record(
            server_address, "server_host", route="direct", status="route_observed",
            peer=client_address, peer_attestation=attestation,
        )
        report = overlay.build_report(
            client_record, server_record,
            attestation, attestation, attestation, attestation,
            overlay.host_metadata("verifier_host", self.verifier_env),
        )
        self.assertEqual(report["status"], "overlay_reachable_with_relay_or_asymmetry")

    def test_report_has_no_route_when_credentials_are_missing(self) -> None:
        client_address, _ = self.address("client_host", self.client_env, None)
        server_address, _ = self.address("server_host", self.server_env, None)
        client_record = self.record(
            client_address, "client_host", route="not_attempted", status="credentials_missing", peer=None
        )
        server_record = self.record(
            server_address, "server_host", route="not_attempted", status="credentials_missing", peer=None
        )
        attestation = {"verified": True, "subject_sha256": "c" * 64}
        report = overlay.build_report(
            client_record, server_record,
            attestation, attestation, attestation, attestation,
            overlay.host_metadata("verifier_host", self.verifier_env),
        )
        self.assertEqual(report["status"], "overlay_credentials_missing")

    def test_route_observed_record_without_peer_address_commitment_is_rejected(self) -> None:
        client_address, _ = self.address("client_host", self.client_env, "100.64.0.11")
        record = self.record(
            client_address, "client_host", route="direct", status="route_observed", peer=None
        )
        with self.assertRaisesRegex(overlay.OverlayProbeError, "both peer address commitments"):
            overlay._validate_record(
                record, "client_host",
                expected_run_id="789012345", expected_attempt="1",
            )

    def test_host_workflow_identity_is_pinned_to_main_and_expected_role(self) -> None:
        with self.assertRaisesRegex(overlay.OverlayProbeError, "workflow identity"):
            bad = dict(self.client_env)
            bad["GITHUB_WORKFLOW_REF"] = "someone/else/workflow.yml@refs/heads/main"
            overlay.host_metadata("client_host", bad)
        with self.assertRaisesRegex(overlay.OverlayProbeError, "expected job"):
            overlay.host_metadata("client_host", runner_env("server_host", "wrong-role"))


if __name__ == "__main__":
    unittest.main()
