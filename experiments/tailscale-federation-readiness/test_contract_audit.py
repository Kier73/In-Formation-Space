"""Regression tests for the fail-closed offline Tailscale federation contract."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_audit as audit


class FederationContractTests(unittest.TestCase):
    def document(self, experiment: str) -> dict:
        return yaml.safe_load((audit.ROOT / audit.CONTRACTS[experiment]["workflow"]).read_text(encoding="utf-8"))

    @staticmethod
    def join_step(doc: dict, role: str) -> dict:
        return next(step for step in doc["jobs"][role]["steps"]
                    if str(step.get("uses", "")).startswith("tailscale/github-action@"))

    @staticmethod
    def gate_step(doc: dict, role: str) -> dict:
        return next(step for step in doc["jobs"][role]["steps"]
                    if str(step.get("name", "")).startswith("Require the dedicated"))

    def test_both_shipped_workflows_pass_without_reading_credentials(self) -> None:
        result = audit.inspect_repository()
        self.assertEqual(result["status"], "source_contracts_verified")
        self.assertEqual({entry["experiment"] for entry in result["experiments"]},
                         {"IHP-006", "MOR-002"})
        for item in result["experiments"]:
            self.assertEqual(item["live_federation"], "not_assessed")
            self.assertEqual(item["listener"], "tcp:41763")
            self.assertEqual(len(item["workflow_sha256"]), 64)

    def test_wrong_tailnet_tag_fails_closed(self) -> None:
        doc = self.document("IHP-006")
        self.join_step(doc, "client_host")["with"]["tags"] = "tag:unrestricted-ci"
        with self.assertRaisesRegex(audit.ContractError, "tailnet tag"):
            audit.inspect_workflow(doc, "IHP-006")

    def test_reusing_other_experiments_identity_is_rejected(self) -> None:
        doc = self.document("MOR-002")
        self.join_step(doc, "server_host")["with"]["oauth-client-id"] = "secrets.IHP006_TS_OAUTH_CLIENT_ID"
        with self.assertRaisesRegex(audit.ContractError, "dedicated client ID"):
            audit.inspect_workflow(doc, "MOR-002")

    def test_credential_gate_cannot_be_removed(self) -> None:
        doc = self.document("IHP-006")
        self.gate_step(doc, "server_host")["run"] = "echo skipping credential verification"
        with self.assertRaisesRegex(audit.ContractError, "empty-credential rejection"):
            audit.inspect_workflow(doc, "IHP-006")

    def test_live_peer_cannot_run_from_untrusted_branch(self) -> None:
        doc = self.document("MOR-002")
        doc["jobs"]["client_host"]["if"] = "github.ref == 'refs/heads/develop'"
        with self.assertRaisesRegex(audit.ContractError, "restricted to main"):
            audit.inspect_workflow(doc, "MOR-002")

    def test_mor002_live_peer_requires_explicit_dispatch(self) -> None:
        doc = self.document("MOR-002")
        doc["jobs"]["client_host"]["if"] = "needs.tests.result == 'success' && github.ref == 'refs/heads/main'"
        with self.assertRaisesRegex(audit.ContractError, "manual dispatch"):
            audit.inspect_workflow(doc, "MOR-002")

    def test_mor002_independent_observer_requires_dispatch(self) -> None:
        doc = self.document("MOR-002")
        doc["jobs"]["observer_host"]["if"] = "needs.tests.result == 'success' && github.ref == 'refs/heads/main'"
        with self.assertRaisesRegex(audit.ContractError, "manual dispatch"):
            audit.inspect_workflow(doc, "MOR-002")

    def test_authkey_fallback_is_forbidden(self) -> None:
        doc = self.document("MOR-002")
        self.join_step(doc, "client_host")["with"]["authkey"] = "secrets.SHARED_TAILSCALE_KEY"
        with self.assertRaisesRegex(audit.ContractError, "fallback is forbidden"):
            audit.inspect_workflow(doc, "MOR-002")

    def test_action_must_be_immutable(self) -> None:
        doc = self.document("IHP-006")
        self.join_step(doc, "server_host")["uses"] = "tailscale/github-action@v4"
        with self.assertRaisesRegex(audit.ContractError, "pinned Tailscale action"):
            audit.inspect_workflow(doc, "IHP-006")

    def test_ephemeral_server_must_bind_only_to_overlay(self) -> None:
        doc = self.document("IHP-006")
        for step in doc["jobs"]["server_host"]["steps"]:
            if "direct_mtls_operation_path.py serve" in str(step.get("run", "")):
                step["run"] = step["run"].replace("--bind-host", "--not-an-overlay-bind")
        with self.assertRaisesRegex(audit.ContractError, "advertise and bind"):
            audit.inspect_workflow(doc, "IHP-006")

    def test_independent_verifier_must_not_join_tailnet(self) -> None:
        doc = self.document("MOR-002")
        doc["jobs"]["verifier_host"]["steps"].append({
            "name": "Unexpected Tailscale join",
            "uses": "tailscale/github-action@v4",
        })
        with self.assertRaisesRegex(audit.ContractError, "off-tailnet"):
            audit.inspect_workflow(doc, "MOR-002")

    def test_missing_oidc_permission_is_rejected(self) -> None:
        doc = self.document("IHP-006")
        doc["jobs"]["client_host"]["permissions"]["id-token"] = "read"
        with self.assertRaisesRegex(audit.ContractError, "id-token: write"):
            audit.inspect_workflow(doc, "IHP-006")


if __name__ == "__main__":
    unittest.main()
