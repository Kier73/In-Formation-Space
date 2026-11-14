#!/usr/bin/env python3
"""Offline contract audit for dedicated IHP-006 and MOR-002 Tailscale workflows.

This script deliberately has no network or secret access. A passing result is
configuration-source validation, never evidence of a live tailnet connection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION_SHA = "064b10558093f38325e838ddea35486bdc6b1d5c"
CONTRACTS = {
    "IHP-006": {
        "workflow": ".github/workflows/tailscale-mtls-operation-path.yml",
        "tag": "tag:ihp006-mtls-ci",
        "client_id_secret": "IHP006_TS_OAUTH_CLIENT_ID",
        "audience_secret": "IHP006_TS_AUDIENCE",
    },
    "MOR-002": {
        "workflow": ".github/workflows/mor002-tailscale-causal-reconstruction.yml",
        "tag": "tag:mor002-mtls-ci",
        "client_id_secret": "MOR002_TS_OAUTH_CLIENT_ID",
        "audience_secret": "MOR002_TS_AUDIENCE",
    },
}


class ContractError(ValueError):
    """A source-controlled federation requirement is missing or changed."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ContractError(message)


def inspect_workflow(document: dict[str, Any], name: str) -> dict[str, Any]:
    """Assert the static contract for one trusted main-branch workflow."""
    require(name in CONTRACTS, "unknown federation experiment")
    spec = CONTRACTS[name]
    triggers = document.get("on", document.get(True, {}))
    require(isinstance(triggers, dict) and "workflow_dispatch" in triggers,
            f"{name}: explicit main-branch dispatch is required")
    jobs = document.get("jobs", {})
    require(isinstance(jobs, dict), f"{name}: jobs are missing")
    for role in ("client_host", "server_host"):
        job = jobs.get(role)
        require(isinstance(job, dict), f"{name}: missing {role}")
        require("github.ref == 'refs/heads/main'" in str(job.get("if", "")),
                f"{name}/{role}: live execution must be restricted to main")
        if name == "MOR-002":
            require("github.event_name == 'workflow_dispatch'" in str(job.get("if", "")),
                    f"{name}/{role}: live peer execution must require manual dispatch")
        require(job.get("permissions", {}).get("id-token") == "write",
                f"{name}/{role}: Tailscale OIDC requires id-token: write")
        steps = job.get("steps", [])
        require(isinstance(steps, list), f"{name}/{role}: malformed steps")
        actions = [step for step in steps if str(step.get("uses", "")).startswith("tailscale/github-action@")]
        require(len(actions) == 1, f"{name}/{role}: require exactly one Tailscale join")
        action = actions[0]
        require(action["uses"] == "tailscale/github-action@" + ACTION_SHA,
                f"{name}/{role}: pinned Tailscale action changed")
        settings = action.get("with", {})
        require(isinstance(settings, dict), f"{name}/{role}: missing Tailscale inputs")
        require(settings.get("tags") == spec["tag"], f"{name}/{role}: unexpected tailnet tag")
        require("secrets." + spec["client_id_secret"] in str(settings.get("oauth-client-id", "")),
                f"{name}/{role}: wrong dedicated client ID")
        require("secrets." + spec["audience_secret"] in str(settings.get("audience", "")),
                f"{name}/{role}: wrong dedicated audience")
        require(not any(key in settings for key in ("authkey", "oauth-secret")),
                f"{name}/{role}: reusable auth key or OAuth secret fallback is forbidden")
        gates = [step for step in steps if str(step.get("name", "")).startswith("Require the dedicated")]
        require(len(gates) == 1, f"{name}/{role}: missing fail-closed credentials gate")
        gate = gates[0]
        env = gate.get("env", {})
        require("secrets." + spec["client_id_secret"] in str(env.get(spec["client_id_secret"], "")),
                f"{name}/{role}: credentials gate does not receive dedicated client ID")
        require("secrets." + spec["audience_secret"] in str(env.get(spec["audience_secret"], "")),
                f"{name}/{role}: credentials gate does not receive dedicated audience")
        script = str(gate.get("run", ""))
        for key in (spec["client_id_secret"], spec["audience_secret"]):
            require(('-z "$' + key + '"') in script,
                    f"{name}/{role}: missing empty-credential rejection for {key}")
        require(re.search(r"^\s*exit 1\s*$", script, flags=re.MULTILINE) is not None,
                f"{name}/{role}: credentials gate must exit unsuccessfully")
        commands = "\n".join(str(step.get("run", "")) for step in steps)
        if role == "client_host":
            require("direct_mtls_operation_path.py connect" in commands,
                    f"{name}/{role}: missing real E-CPU mTLS client")
        else:
            require("direct_mtls_operation_path.py prepare-server" in commands,
                    f"{name}/{role}: missing signed server endpoint")
            require("direct_mtls_operation_path.py serve" in commands,
                    f"{name}/{role}: missing real E-CPU mTLS server")
            require("--advertise-host" in commands and "--bind-host" in commands,
                    f"{name}/{role}: server must advertise and bind to overlay IPv4")
            require(commands.count("steps.overlay.outputs.ip") >= 2,
                    f"{name}/{role}: advertised and bound addresses must come from Tailscale")
    for role in ("verifier_host", "observer_host"):
        if role in jobs:
            if name == "MOR-002":
                require("github.event_name == 'workflow_dispatch'" in str(jobs[role].get("if", "")),
                        f"{name}/{role}: independent live verification requires manual dispatch")
            steps = jobs[role].get("steps", [])
            require(not any("tailscale/github-action@" in str(s.get("uses", "")) for s in steps),
                    f"{name}/{role}: independent observer/verifier must remain off-tailnet")
    require("verifier_host" in jobs, f"{name}: independent verifier required")
    return {
        "experiment": name,
        "workflow": spec["workflow"],
        "tailnet_tag": spec["tag"],
        "oidc_secret_names": [spec["client_id_secret"], spec["audience_secret"]],
        "action_ref": "tailscale/github-action@" + ACTION_SHA,
        "listener": "tcp:41763",
        "static_contract": "verified",
        "live_federation": "not_assessed",
    }


def inspect_repository(root: Path = ROOT) -> dict[str, Any]:
    entries = []
    for name, spec in CONTRACTS.items():
        path = root / spec["workflow"]
        raw = path.read_bytes()
        parsed = yaml.safe_load(raw)
        require(isinstance(parsed, dict), f"{name}: invalid YAML document")
        result = inspect_workflow(parsed, name)
        result["workflow_sha256"] = hashlib.sha256(raw).hexdigest()
        entries.append(result)
    return {
        "schema": "in-formation.federation-contract-audit/0.1",
        "scope": "offline_source_only_no_tailnet_or_secret_access",
        "status": "source_contracts_verified",
        "experiments": entries,
        "limitations": [
            "This audit cannot inspect GitHub secrets or Tailscale federation identities.",
            "This audit cannot establish tailnet authorization, TCP reachability, mTLS or causality.",
            "A live claim requires a successful IHP-006 or MOR-002 run and independent attested reconstruction.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = inspect_repository(args.root)
    except (ContractError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f"federation source contract rejected: {error}\n")
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
