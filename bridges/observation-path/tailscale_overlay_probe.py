#!/usr/bin/env python3
"""Attested, ephemeral Tailscale overlay reachability probe for IHP-003."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

REPOSITORY = "Kier73/In-Formation-Space"
WORKFLOW_PATH = ".github/workflows/tailscale-overlay-preflight.yml"
SIGNER_WORKFLOW = f"{REPOSITORY}/{WORKFLOW_PATH}"
SOURCE_REF = "refs/heads/main"
TAG = "tag:ihp003-ci"
ADDRESS_SCHEMA = "in-formation.ihp003-overlay-address/0.1"
ADDRESS_PREDICATE_SCHEMA = "in-formation.ihp003-overlay-address-predicate/0.1"
RECORD_SCHEMA = "in-formation.ihp003-overlay-probe-record/0.1"
RECORD_PREDICATE_SCHEMA = "in-formation.ihp003-overlay-probe-record-predicate/0.1"
REPORT_SCHEMA = "in-formation.ihp003-overlay-report/0.1"
REPORT_PREDICATE_SCHEMA = "in-formation.ihp003-overlay-report-predicate/0.1"
ADDRESS_PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/ihp003-overlay-address/v1"
RECORD_PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/ihp003-overlay-probe-record/v1"
REPORT_PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/ihp003-overlay-report/v1"
GH_MIN_VERSION = (2, 103, 3)
PEER_WAIT_SECONDS = 180.0
PING_COUNT = 8
PING_TIMEOUT_SECONDS = 45.0


class OverlayProbeError(ValueError):
    """An overlay identity, attestation, or route measurement is invalid."""


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise OverlayProbeError(f"value is not canonical finite JSON: {error}") from error


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_object(value: object) -> str:
    return digest_bytes(canonical(value))


def file_digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OverlayProbeError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise OverlayProbeError(f"{path} must contain one JSON object")
    return value


def _env(source: Mapping[str, str], name: str) -> str:
    value = source.get(name)
    if not isinstance(value, str) or not value.strip():
        raise OverlayProbeError(f"required GitHub runner environment field {name} is missing")
    return value.strip()


def host_metadata(role: str, env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    if role not in {"client_host", "server_host", "verifier_host"}:
        raise OverlayProbeError("unsupported IHP-003 host role")
    result = {
        "role": role,
        "repository": _env(source, "GITHUB_REPOSITORY"),
        "run_id": _env(source, "GITHUB_RUN_ID"),
        "run_attempt": _env(source, "GITHUB_RUN_ATTEMPT"),
        "run_number": _env(source, "GITHUB_RUN_NUMBER"),
        "workflow_ref": _env(source, "GITHUB_WORKFLOW_REF"),
        "workflow_sha": _env(source, "GITHUB_WORKFLOW_SHA"),
        "git_ref": _env(source, "GITHUB_REF"),
        "git_sha": _env(source, "GITHUB_SHA"),
        "job": _env(source, "GITHUB_JOB"),
        "runner_name": _env(source, "RUNNER_NAME"),
        "runner_os": _env(source, "RUNNER_OS"),
        "runner_arch": _env(source, "RUNNER_ARCH"),
        "runner_environment": _env(source, "RUNNER_ENVIRONMENT"),
    }
    if result["repository"] != REPOSITORY:
        raise OverlayProbeError("runner repository does not match the pinned repository")
    if result["workflow_ref"] != f"{REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}":
        raise OverlayProbeError("runner workflow identity is not the protected IHP-003 main workflow")
    if result["git_ref"] != SOURCE_REF or result["runner_environment"] != "github-hosted":
        raise OverlayProbeError("IHP-003 evidence must come from a main-branch GitHub-hosted runner")
    if result["job"] != role:
        raise OverlayProbeError(f"expected job {role}, received {result['job']}")
    result["actor_id"] = (
        f"{REPOSITORY}#run-{result['run_id']}.attempt-{result['run_attempt']}."
        f"{role}.{result['runner_name']}"
    )
    return result


def _validate_host(value: object, role: str) -> dict[str, str]:
    expected = {
        "role", "repository", "run_id", "run_attempt", "run_number",
        "workflow_ref", "workflow_sha", "git_ref", "git_sha", "job",
        "runner_name", "runner_os", "runner_arch", "runner_environment", "actor_id",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise OverlayProbeError(f"{role} host identity fields are incomplete or unexpected")
    if any(not isinstance(value[key], str) or not value[key] for key in expected):
        raise OverlayProbeError(f"{role} host identity values must be non-empty strings")
    if value["role"] != role or value["job"] != role:
        raise OverlayProbeError(f"host identity does not represent {role}")
    if value["repository"] != REPOSITORY:
        raise OverlayProbeError("host identity repository mismatch")
    if value["workflow_ref"] != f"{REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}":
        raise OverlayProbeError("host identity workflow is not pinned")
    if value["git_ref"] != SOURCE_REF or value["runner_environment"] != "github-hosted":
        raise OverlayProbeError("host identity ref or runner environment is not permitted")
    return dict(value)


def _run(command: Sequence[str], *, timeout: float, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command), capture_output=True, text=True, timeout=timeout,
            env=None if env is None else dict(env), check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OverlayProbeError(f"command failed to start or complete: {command[0]}: {error}") from error


def _tailscale_ip(tailscale_bin: str = "tailscale") -> str:
    result = _run([tailscale_bin, "ip", "-4"], timeout=8.0)
    if result.returncode != 0:
        raise OverlayProbeError(f"tailscale ip -4 failed: {(result.stderr or result.stdout).strip()}")
    value = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise OverlayProbeError("Tailscale did not return a valid IPv4 address") from error
    if address.version != 4:
        raise OverlayProbeError("Tailscale address must be IPv4")
    return str(address)


def create_address(
    role: str,
    output_dir: Path,
    *,
    enabled: bool,
    tailscale_bin: str = "tailscale",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    host = host_metadata(role, env)
    if enabled:
        overlay_ip = _tailscale_ip(tailscale_bin)
        status = "ready"
    else:
        overlay_ip = None
        status = "credentials_missing"
    core = {
        "schema": ADDRESS_SCHEMA,
        "role": role,
        "host": host,
        "status": status,
        "overlay_provider": "tailscale",
        "overlay_tag": TAG,
        "overlay_ipv4": overlay_ip,
    }
    address = {**core, "address_digest": digest_object(core)}
    predicate = {
        "schema": ADDRESS_PREDICATE_SCHEMA,
        "role": role,
        "host": host,
        "address_sha256": digest_bytes(canonical(address) + b"\n"),
        "address_digest": address["address_digest"],
        "status": status,
        "overlay_ipv4": overlay_ip,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "address.json", address)
    write_json(output_dir / "address.predicate.json", predicate)
    return address


def _attestation_command(path: Path, predicate_type: str, gh: str) -> list[str]:
    return [
        gh, "attestation", "verify", str(path),
        "--repo", REPOSITORY,
        "--predicate-type", predicate_type,
        "--signer-workflow", SIGNER_WORKFLOW,
        "--source-ref", SOURCE_REF,
        "--deny-self-hosted-runners",
        "--format", "json",
    ]


def _gh_version(gh: str) -> tuple[int, int, int]:
    result = subprocess.run([gh, "--version"], check=True, capture_output=True, text=True)
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match:
        raise OverlayProbeError("cannot parse GitHub CLI version")
    return tuple(int(value) for value in match.groups())


def _find_statement(output: Any, subject_digest: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(output, list):
        raise OverlayProbeError("attestation verification output must be an array")
    matches = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        verification = item.get("verificationResult")
        statement = verification.get("statement") if isinstance(verification, Mapping) else None
        if not isinstance(statement, Mapping):
            continue
        subjects = statement.get("subject", [])
        if any(
            isinstance(subject, Mapping)
            and isinstance(subject.get("digest"), Mapping)
            and subject["digest"].get("sha256") == subject_digest
            for subject in subjects
        ):
            matches.append((dict(statement), dict(verification)))
    if not matches:
        raise OverlayProbeError("no verified attestation subject matches the exact artifact bytes")
    return matches[0]


def verify_artifact_attestation(
    path: Path,
    predicate_type: str,
    expected_predicate: Mapping[str, Any],
    *,
    gh: str = "gh",
) -> dict[str, Any]:
    if _gh_version(gh) < GH_MIN_VERSION:
        raise OverlayProbeError("GitHub CLI 2.103.3 or newer is required")
    exact_digest = file_digest(path)
    try:
        completed = subprocess.run(
            _attestation_command(path, predicate_type, gh),
            check=True, capture_output=True, text=True, env=os.environ.copy(),
        )
        output = json.loads(completed.stdout)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() if error.stderr else str(error)
        raise OverlayProbeError(f"artifact attestation verification failed: {detail}") from error
    except json.JSONDecodeError as error:
        raise OverlayProbeError("GitHub CLI returned invalid attestation JSON") from error
    statement, verification = _find_statement(output, exact_digest)
    predicate = statement.get("predicate")
    if statement.get("predicateType") != predicate_type or not isinstance(predicate, Mapping):
        raise OverlayProbeError("artifact attestation predicate type/object is invalid")
    if dict(predicate) != dict(expected_predicate):
        raise OverlayProbeError("signed artifact predicate differs from the expected document")
    signature = verification.get("signature")
    if not isinstance(signature, Mapping) or not isinstance(signature.get("certificate"), Mapping):
        raise OverlayProbeError("verified artifact attestation has no signature certificate")
    return {
        "verified": True,
        "subject_sha256": exact_digest,
        "predicate_type": predicate_type,
        "signer_workflow": SIGNER_WORKFLOW,
        "source_ref": SOURCE_REF,
        "self_hosted_runners_denied": True,
        "verified_timestamp_count": len(verification.get("verifiedTimestamps", [])),
    }


def _download_artifact(
    artifact_name: str,
    destination: Path,
    *,
    timeout_seconds: float = PEER_WAIT_SECONDS,
    gh: str = "gh",
) -> Path:
    run_id = _env(os.environ, "GITHUB_RUN_ID")
    deadline = time.monotonic() + timeout_seconds
    last_error = "artifact not available yet"
    while time.monotonic() < deadline:
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [gh, "run", "download", run_id, "--repo", REPOSITORY,
             "--name", artifact_name, "--dir", str(destination)],
            capture_output=True, text=True, env=os.environ.copy(), check=False,
        )
        if result.returncode == 0 and any(p.is_file() for p in destination.rglob("*")):
            return destination
        last_error = (result.stderr or result.stdout or "artifact not found").strip()
        time.sleep(2.0)
    raise OverlayProbeError(f"timed out waiting for {artifact_name}: {last_error[-800:]}")


def _validate_address(
    address: Mapping[str, Any],
    *,
    expected_role: str,
    expected_run_id: str,
    expected_attempt: str,
) -> dict[str, Any]:
    required = {
        "schema", "role", "host", "status", "overlay_provider",
        "overlay_tag", "overlay_ipv4", "address_digest",
    }
    if not isinstance(address, Mapping) or set(address) != required:
        raise OverlayProbeError("overlay address fields are incomplete or unexpected")
    core = {key: address[key] for key in required if key != "address_digest"}
    if address["schema"] != ADDRESS_SCHEMA or address["address_digest"] != digest_object(core):
        raise OverlayProbeError("overlay address schema or digest is invalid")
    host = _validate_host(address["host"], expected_role)
    if host["run_id"] != expected_run_id or host["run_attempt"] != expected_attempt:
        raise OverlayProbeError("peer address belongs to another workflow run/attempt")
    if address["overlay_provider"] != "tailscale" or address["overlay_tag"] != TAG:
        raise OverlayProbeError("peer address does not identify the IHP-003 Tailscale overlay")
    if address["status"] not in {"ready", "credentials_missing"}:
        raise OverlayProbeError("peer address status is unsupported")
    if address["status"] == "ready":
        try:
            parsed = ipaddress.ip_address(address["overlay_ipv4"])
        except ValueError as error:
            raise OverlayProbeError("peer overlay address is invalid") from error
        tailscale_ipv4 = ipaddress.ip_network("100.64.0.0/10")
        if parsed.version != 4 or parsed not in tailscale_ipv4:
            raise OverlayProbeError("peer overlay address must be inside Tailscale's 100.64.0.0/10 IPv4 allocation")
    elif address["overlay_ipv4"] is not None:
        raise OverlayProbeError("unconfigured peer must not advertise an overlay IP")
    return dict(address)


def classify_route(output: str, return_code: int) -> str:
    lower = output.lower()
    if re.search(r"\bvia\s+\d{1,3}(?:\.\d{1,3}){3}:\d+", lower):
        return "direct"
    if re.search(r"\bvia\s+peer[- ]relay", lower) or "peer-relay(" in lower:
        return "peer_relay"
    if "via derp(" in lower or re.search(r"\brelay\s+\"", lower):
        return "derp_relay"
    if return_code == 0 and "pong from" in lower:
        return "reachable_unclassified"
    return "unreachable"


def probe_peer(
    role: str,
    output_dir: Path,
    *,
    peer_artifact: str,
    enabled: bool,
    gh: str = "gh",
    tailscale_bin: str = "tailscale",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    host = host_metadata(role, env)
    address_path = output_dir / "address.json"
    predicate_path = output_dir / "address.predicate.json"
    own_address = read_json(address_path)
    _validate_address(
        own_address,
        expected_role=role,
        expected_run_id=host["run_id"],
        expected_attempt=host["run_attempt"],
    )
    if dict(own_address["host"]) != host:
        raise OverlayProbeError("local overlay address host differs from the current runner")

    status = "credentials_missing"
    peer_address: dict[str, Any] | None = None
    peer_attestation: dict[str, Any] | None = None
    peer_digest: str | None = None
    route_type = "not_attempted"
    ping_output = ""
    ping_exit_code: int | None = None

    if enabled and own_address["status"] == "ready":
        peer_role = "server_host" if role == "client_host" else "client_host"
        peer_dir = _download_artifact(peer_artifact, output_dir / "peer-bootstrap", gh=gh)
        peer_path = peer_dir / "address.json"
        peer_predicate_path = peer_dir / "address.predicate.json"
        peer_address = read_json(peer_path)
        peer_predicate = read_json(peer_predicate_path)
        _validate_address(
            peer_address,
            expected_role=peer_role,
            expected_run_id=host["run_id"],
            expected_attempt=host["run_attempt"],
        )
        expected_predicate = {
            "schema": ADDRESS_PREDICATE_SCHEMA,
            "role": peer_role,
            "host": peer_address["host"],
            "address_sha256": file_digest(peer_path),
            "address_digest": peer_address["address_digest"],
            "status": peer_address["status"],
            "overlay_ipv4": peer_address["overlay_ipv4"],
        }
        if dict(peer_predicate) != expected_predicate:
            raise OverlayProbeError("peer address predicate does not bind the exact address file")
        peer_attestation = verify_artifact_attestation(
            peer_path, ADDRESS_PREDICATE_TYPE, expected_predicate, gh=gh
        )
        peer_digest = file_digest(peer_path)
        if peer_address["status"] != "ready":
            status = "peer_overlay_not_configured"
        else:
            command = [tailscale_bin, "ping", "-c", str(PING_COUNT), str(peer_address["overlay_ipv4"])]
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True, timeout=PING_TIMEOUT_SECONDS,
                    env=os.environ.copy(), check=False,
                )
                ping_output = (completed.stdout + "\n" + completed.stderr).strip()[-6000:]
                ping_exit_code = completed.returncode
                route_type = classify_route(ping_output, completed.returncode)
            except subprocess.TimeoutExpired as error:
                raw = error.stdout or ""
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                ping_output = (str(raw) + "\nprobe timed out").strip()[-6000:]
                ping_exit_code = 124
                route_type = "unreachable"
            status = "route_observed" if route_type != "unreachable" else "route_unavailable"
    else:
        status = "credentials_missing"

    core = {
        "schema": RECORD_SCHEMA,
        "role": role,
        "host": host,
        "status": status,
        "overlay_provider": "tailscale",
        "overlay_tag": TAG,
        "overlay_ipv4": own_address["overlay_ipv4"],
        "address_digest": own_address["address_digest"],
        "peer_address_digest": peer_digest,
        "peer_role": "server_host" if role == "client_host" else "client_host",
        "peer_overlay_ipv4": None if peer_address is None else peer_address["overlay_ipv4"],
        "peer_address_attestation": peer_attestation,
        "route_type": route_type,
        "ping_count": PING_COUNT if ping_exit_code is not None else 0,
        "ping_exit_code": ping_exit_code,
        "ping_output": ping_output,
        "diagnostic": (
            "Tailscale peer-path probe only; no E-CPU application payload was sent by this IHP-003 preflight."
        ),
    }
    record = {**core, "record_digest": digest_object(core)}
    predicate = {
        "schema": RECORD_PREDICATE_SCHEMA,
        "role": role,
        "host": host,
        "record_sha256": digest_bytes(canonical(record) + b"\n"),
        "record_digest": record["record_digest"],
        "status": status,
        "route_type": route_type,
    }
    write_json(output_dir / "record.json", record)
    write_json(output_dir / "record.predicate.json", predicate)
    return record


def _validate_record(
    record: Mapping[str, Any],
    role: str,
    *,
    expected_run_id: str,
    expected_attempt: str,
) -> dict[str, Any]:
    required = {
        "schema", "role", "host", "status", "overlay_provider", "overlay_tag",
        "overlay_ipv4", "address_digest", "peer_address_digest", "peer_role",
        "peer_overlay_ipv4", "peer_address_attestation", "route_type",
        "ping_count", "ping_exit_code", "ping_output", "diagnostic", "record_digest",
    }
    if not isinstance(record, Mapping) or set(record) != required:
        raise OverlayProbeError(f"{role} record fields are incomplete or unexpected")
    core = {key: record[key] for key in required if key != "record_digest"}
    if record["schema"] != RECORD_SCHEMA or record["role"] != role:
        raise OverlayProbeError(f"{role} record schema or role is invalid")
    if record["record_digest"] != digest_object(core):
        raise OverlayProbeError(f"{role} record digest does not match")
    host = _validate_host(record["host"], role)
    if host["run_id"] != expected_run_id or host["run_attempt"] != expected_attempt:
        raise OverlayProbeError(f"{role} record belongs to another workflow run/attempt")
    expected_peer_role = "server_host" if role == "client_host" else "client_host"
    if record["peer_role"] != expected_peer_role:
        raise OverlayProbeError(f"{role} peer role does not match")
    if record["overlay_provider"] != "tailscale" or record["overlay_tag"] != TAG:
        raise OverlayProbeError("record does not use the pinned Tailscale overlay")
    if record["status"] not in {"route_observed", "route_unavailable", "credentials_missing", "peer_overlay_not_configured"}:
        raise OverlayProbeError("record status is unsupported")
    if record["route_type"] not in {"direct", "derp_relay", "peer_relay", "reachable_unclassified", "unreachable", "not_attempted"}:
        raise OverlayProbeError("route type is unsupported")
    if record["status"] == "route_observed":
        if record["route_type"] not in {"direct", "derp_relay", "peer_relay", "reachable_unclassified"}:
            raise OverlayProbeError("route-observed record lacks a reachable route classification")
        if not record["overlay_ipv4"] or not record["peer_overlay_ipv4"] or not record["peer_address_digest"] or not isinstance(record["peer_address_attestation"], Mapping):
            raise OverlayProbeError("route-observed record lacks both attested peer address commitments")
        if record["ping_exit_code"] != 0 or record["ping_count"] < 1:
            raise OverlayProbeError("route-observed record lacks a successful Tailscale ping")
    if record["status"] == "route_unavailable":
        if record["route_type"] != "unreachable" or not record["peer_address_digest"] or not isinstance(record["peer_address_attestation"], Mapping) or record["ping_count"] < 1:
            raise OverlayProbeError("route-unavailable record lacks an attested peer probe")
    if record["status"] == "peer_overlay_not_configured":
        if record["route_type"] != "not_attempted" or not record["peer_address_digest"] or not isinstance(record["peer_address_attestation"], Mapping):
            raise OverlayProbeError("unconfigured peer result lacks the peer address attestation")
    if record["status"] == "credentials_missing":
        if record["route_type"] != "not_attempted" or record["peer_address_digest"] is not None or record["peer_address_attestation"] is not None:
            raise OverlayProbeError("missing local credentials cannot claim a peer address or route")
    return dict(record)


def _require_same_run(client: Mapping[str, Any], server: Mapping[str, Any], verifier: Mapping[str, Any]) -> None:
    fields = ("repository", "run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_ref", "git_sha")
    for field in fields:
        if client.get(field) != server.get(field) or client.get(field) != verifier.get(field):
            raise OverlayProbeError(f"overlay records disagree on shared run field {field}")
    actors = {client["actor_id"], server["actor_id"], verifier["actor_id"]}
    if len(actors) != 3:
        raise OverlayProbeError("client, server, and verifier must be distinct workflow actors")


def build_report(
    client_record: Mapping[str, Any],
    server_record: Mapping[str, Any],
    client_attestation: Mapping[str, Any],
    server_attestation: Mapping[str, Any],
    client_address_attestation: Mapping[str, Any],
    server_address_attestation: Mapping[str, Any],
    verifier_host: Mapping[str, Any],
) -> dict[str, Any]:
    verifier = _validate_host(verifier_host, "verifier_host")
    client = _validate_record(
        client_record, "client_host",
        expected_run_id=verifier["run_id"], expected_attempt=verifier["run_attempt"],
    )
    server = _validate_record(
        server_record, "server_host",
        expected_run_id=verifier["run_id"], expected_attempt=verifier["run_attempt"],
    )
    _require_same_run(client["host"], server["host"], verifier)
    if client["peer_address_digest"] not in {None, server_address_attestation.get("subject_sha256")}:
        raise OverlayProbeError("client did not bind the exact attested server address file bytes")
    if server["peer_address_digest"] not in {None, client_address_attestation.get("subject_sha256")}:
        raise OverlayProbeError("server did not bind the exact attested client address file bytes")
    if client["peer_overlay_ipv4"] not in {None, server["overlay_ipv4"]}:
        raise OverlayProbeError("client probe peer IP differs from server's attested overlay IP")
    if server["peer_overlay_ipv4"] not in {None, client["overlay_ipv4"]}:
        raise OverlayProbeError("server probe peer IP differs from client's attested overlay IP")

    if client["peer_address_attestation"] is not None and dict(client["peer_address_attestation"]) != dict(server_address_attestation):
        raise OverlayProbeError("client record peer-address attestation differs from verifier's server-address verification")
    if server["peer_address_attestation"] is not None and dict(server["peer_address_attestation"]) != dict(client_address_attestation):
        raise OverlayProbeError("server record peer-address attestation differs from verifier's client-address verification")

    if client["status"] == "credentials_missing" or server["status"] == "credentials_missing":
        status = "overlay_credentials_missing"
    elif client["status"] == "peer_overlay_not_configured" or server["status"] == "peer_overlay_not_configured":
        status = "overlay_peer_not_configured"
    elif client["status"] != "route_observed" or server["status"] != "route_observed":
        status = "overlay_path_unavailable"
    elif client["route_type"] == "direct" and server["route_type"] == "direct":
        status = "direct_peer_to_peer"
    elif client["route_type"] in {"direct", "derp_relay", "peer_relay", "reachable_unclassified"} and server["route_type"] in {"direct", "derp_relay", "peer_relay", "reachable_unclassified"}:
        status = "overlay_reachable_with_relay_or_asymmetry"
    else:
        status = "overlay_path_unavailable"

    report_core = {
        "schema": REPORT_SCHEMA,
        "path_id": f"run-{verifier['run_id']}-ihp003-tailscale-overlay",
        "repository": REPOSITORY,
        "run_id": verifier["run_id"],
        "run_attempt": verifier["run_attempt"],
        "client": {
            "host": client["host"],
            "status": client["status"],
            "overlay_ipv4": client["overlay_ipv4"],
            "route_type": client["route_type"],
            "peer_overlay_ipv4": client["peer_overlay_ipv4"],
            "address_digest": client["address_digest"],
            "record_digest": client["record_digest"],
            "address_attestation": dict(client_address_attestation),
            "record_attestation": dict(client_attestation),
            "ping_exit_code": client["ping_exit_code"],
            "ping_output": client["ping_output"],
        },
        "server": {
            "host": server["host"],
            "status": server["status"],
            "overlay_ipv4": server["overlay_ipv4"],
            "route_type": server["route_type"],
            "peer_overlay_ipv4": server["peer_overlay_ipv4"],
            "address_digest": server["address_digest"],
            "record_digest": server["record_digest"],
            "address_attestation": dict(server_address_attestation),
            "record_attestation": dict(server_attestation),
            "ping_exit_code": server["ping_exit_code"],
            "ping_output": server["ping_output"],
        },
        "verifier": verifier,
        "status": status,
        "path_semantics": {
            "probe": "tailscale ping",
            "direct_means": "WireGuard overlay packet path observed as peer-to-peer direct UDP",
            "derp_relay_means": "WireGuard-encrypted traffic relayed through a Tailscale DERP server",
            "peer_relay_means": "WireGuard-encrypted traffic relayed through a tagged tailnet peer",
            "application_payload_sent": False,
            "next_step": "Use the reported tailnet IPs for E-CPU SocketTransport/mTLS in IHP-004; preserve and record the Tailscale route classification.",
        },
        "limitations": [
            "This experiment measures Tailscale overlay peer reachability only; it does not yet send E-CPU application payload or establish mTLS.",
            "A direct Tailscale route is a direct WireGuard UDP path between peers; a DERP or peer-relay route is still end-to-end WireGuard encrypted but traverses a relay.",
            "The tag permissions and Tailscale tailnet control plane are part of the trust base.",
            "GitHub hosted runner isolation and OIDC attestation are part of the workflow provenance trust base.",
            "Overlay IPs and route observations are ephemeral and valid for this workflow run only.",
        ],
    }
    return {**report_core, "report_digest": digest_object(report_core)}


def _verify_peer_address_artifact(
    address_path: Path,
    predicate_path: Path,
    role: str,
    run_id: str,
    attempt: str,
    gh: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    address = read_json(address_path)
    validated = _validate_address(address, expected_role=role, expected_run_id=run_id, expected_attempt=attempt)
    expected_predicate = {
        "schema": ADDRESS_PREDICATE_SCHEMA,
        "role": role,
        "host": validated["host"],
        "address_sha256": file_digest(address_path),
        "address_digest": validated["address_digest"],
        "status": validated["status"],
        "overlay_ipv4": validated["overlay_ipv4"],
    }
    predicate = read_json(predicate_path)
    if dict(predicate) != expected_predicate:
        raise OverlayProbeError("peer address predicate does not match its exact artifact")
    attestation = verify_artifact_attestation(address_path, ADDRESS_PREDICATE_TYPE, expected_predicate, gh=gh)
    return validated, attestation


def verify_to_report(directory: Path, output_path: Path, *, gh: str = "gh") -> dict[str, Any]:
    client_dir = directory / "client"
    server_dir = directory / "server"
    client_address_path = client_dir / "address.json"
    server_address_path = server_dir / "address.json"
    client_record_path = client_dir / "record.json"
    server_record_path = server_dir / "record.json"
    client_address_predicate = client_dir / "address.predicate.json"
    server_address_predicate = server_dir / "address.predicate.json"
    client_record_predicate = client_dir / "record.predicate.json"
    server_record_predicate = server_dir / "record.predicate.json"

    client_record = read_json(client_record_path)
    server_record = read_json(server_record_path)

    client_address, client_address_attestation = _verify_peer_address_artifact(
        client_address_path, client_address_predicate, "client_host",
        _env(os.environ, "GITHUB_RUN_ID"), _env(os.environ, "GITHUB_RUN_ATTEMPT"), gh,
    )
    server_address, server_address_attestation = _verify_peer_address_artifact(
        server_address_path, server_address_predicate, "server_host",
        _env(os.environ, "GITHUB_RUN_ID"), _env(os.environ, "GITHUB_RUN_ATTEMPT"), gh,
    )
    if (
        client_record.get("address_digest") != client_address["address_digest"]
        or client_record.get("overlay_ipv4") != client_address["overlay_ipv4"]
        or server_record.get("address_digest") != server_address["address_digest"]
        or server_record.get("overlay_ipv4") != server_address["overlay_ipv4"]
    ):
        raise OverlayProbeError("host probe records do not bind their own attested overlay-address artifacts")
    for path, record, role in (
        (client_record_path, client_record, "client_host"),
        (server_record_path, server_record, "server_host"),
    ):
        predicate = read_json(client_record_predicate if role == "client_host" else server_record_predicate)
        expected = {
            "schema": RECORD_PREDICATE_SCHEMA,
            "role": role,
            "host": record["host"],
            "record_sha256": file_digest(path),
            "record_digest": record["record_digest"],
            "status": record["status"],
            "route_type": record["route_type"],
        }
        if dict(predicate) != expected:
            raise OverlayProbeError(f"{role} record predicate does not bind exact record bytes")
        verify_artifact_attestation(path, RECORD_PREDICATE_TYPE, expected, gh=gh)

    client_record_attestation = verify_artifact_attestation(
        client_record_path, RECORD_PREDICATE_TYPE,
        read_json(client_record_predicate), gh=gh,
    )
    server_record_attestation = verify_artifact_attestation(
        server_record_path, RECORD_PREDICATE_TYPE,
        read_json(server_record_predicate), gh=gh,
    )
    report = build_report(
        client_record, server_record,
        client_record_attestation, server_record_attestation,
        client_address_attestation, server_address_attestation,
        host_metadata("verifier_host"),
    )
    write_json(output_path, report)
    return report


def write_report_predicate(report_path: Path, predicate_path: Path) -> dict[str, Any]:
    report = read_json(report_path)
    core = {key: value for key, value in report.items() if key != "report_digest"}
    if report.get("schema") != REPORT_SCHEMA or report.get("report_digest") != digest_object(core):
        raise OverlayProbeError("overlay report schema or digest is invalid")
    host = host_metadata("verifier_host")
    if report.get("verifier") != host:
        raise OverlayProbeError("report verifier identity differs from this job")
    predicate = {
        "schema": REPORT_PREDICATE_SCHEMA,
        "repository": host["repository"],
        "run_id": host["run_id"],
        "run_attempt": host["run_attempt"],
        "workflow_ref": host["workflow_ref"],
        "workflow_sha": host["workflow_sha"],
        "git_ref": host["git_ref"],
        "git_sha": host["git_sha"],
        "job": host["job"],
        "runner_name": host["runner_name"],
        "runner_environment": host["runner_environment"],
        "report_sha256": file_digest(report_path),
        "report_digest": report["report_digest"],
        "status": report["status"],
        "path_id": report["path_id"],
    }
    write_json(predicate_path, predicate)
    return predicate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    address_parser = commands.add_parser("create-address")
    address_parser.add_argument("--role", choices=("client_host", "server_host"), required=True)
    address_parser.add_argument("--output-dir", type=Path, required=True)
    address_parser.add_argument("--enabled", choices=("true", "false"), required=True)

    probe_parser = commands.add_parser("probe")
    probe_parser.add_argument("--role", choices=("client_host", "server_host"), required=True)
    probe_parser.add_argument("--output-dir", type=Path, required=True)
    probe_parser.add_argument("--peer-artifact", required=True)
    probe_parser.add_argument("--gh", default="gh")

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--directory", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--gh", default="gh")

    predicate_parser = commands.add_parser("write-report-predicate")
    predicate_parser.add_argument("--report", type=Path, required=True)
    predicate_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "create-address":
            create_address(args.role, args.output_dir, enabled=args.enabled == "true")
        elif args.command == "probe":
            probe_peer(args.role, args.output_dir, peer_artifact=args.peer_artifact, enabled=os.environ.get("IHP003_TAILSCALE_ENABLED") == "true", gh=args.gh)
        elif args.command == "verify":
            verify_to_report(args.directory, args.output, gh=args.gh)
        elif args.command == "write-report-predicate":
            write_report_predicate(args.report, args.output)
    except (OverlayProbeError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"ihp003-overlay-probe: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
