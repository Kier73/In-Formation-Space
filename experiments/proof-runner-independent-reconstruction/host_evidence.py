#!/usr/bin/env python3
"""Produce the three-host proof-runner reconstruction experiment artifacts.

Authority and runner private keys are process-local and never written to the
artifact directories. Public-key documents are attested separately by the
GitHub-hosted job that creates them. The independent Go verifier receives those
public keys only after its host verifies their GitHub artifact attestations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "proof-runner-completion-receipts"))

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from formats.canonical_metadata_v1 import canonical_bytes, canonical_digest, decode_canonical_document
from completion_receipts import (
    CompletionReceiptError,
    create_completion_receipt,
    validate_execution_authorization_event,
    validate_request_document,
)

REPOSITORY = "Kier73/In-Formation-Space"
WORKFLOW_PATH = ".github/workflows/proof-runner-three-host-reconstruction.yml"
SIGNER_WORKFLOW = f"{REPOSITORY}/{WORKFLOW_PATH}"
SOURCE_REF = "refs/heads/main"
LEDGER_FORMAT = "in-formation.proof-action-route-ledger/0.1"
AUTHORITY_ATTESTATION_FORMAT = "in-formation.proof-action-route-ledger-attestation/0.1"
KEY_FORMAT = "in-formation.proof-runner-participant-key/0.1"
BUNDLE_FORMAT = "in-formation.proof-runner-reconstruction-input/0.1"
PREDICATE_TYPE = "https://kier73.github.io/in-formation-space/proof-runner-participant-key/v1"
KEY_PREDICATE_SCHEMA = "in-formation.proof-runner-participant-key-predicate/0.1"
GH_MIN_VERSION = (2, 103, 3)


class EvidenceError(ValueError):
    """Invalid participant artifact, authority statement, or host attestation."""


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(dict(value)) + b"\n")


def _read(path: Path) -> dict[str, Any]:
    try:
        return decode_canonical_document(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"{path} is not a canonical metadata artifact: {exc}") from exc


def _digest(value: Any) -> str:
    return canonical_digest(value)


def _raw_public_key(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _key_id(key: Ed25519PublicKey) -> str:
    return "sha256:" + hashlib.sha256(_raw_public_key(key)).hexdigest()


def _host_identity(role: str, *, fixture: bool = False) -> dict[str, str]:
    if fixture:
        runner_name = "fixture-" + role
        run_id = "fixture-run-0001"
        attempt = "1"
        run_number = "1"
        workflow_ref = f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main"
        workflow_sha = "a" * 40
        git_sha = "b" * 40
        actor = "fixture-contributor"
        return {
            "repository": REPOSITORY,
            "run_id": run_id,
            "run_attempt": attempt,
            "run_number": run_number,
            "workflow_ref": workflow_ref,
            "workflow_sha": workflow_sha,
            "git_ref": SOURCE_REF,
            "git_sha": git_sha,
            "job": role,
            "runner_name": runner_name,
            "runner_os": "Linux",
            "runner_arch": "X64",
            "runner_environment": "github-hosted",
            "actor_id": f"{REPOSITORY}#fixture.{role}.{runner_name}.{actor}",
        }

    names = {
        "repository": "GITHUB_REPOSITORY",
        "run_id": "GITHUB_RUN_ID",
        "run_attempt": "GITHUB_RUN_ATTEMPT",
        "run_number": "GITHUB_RUN_NUMBER",
        "workflow_ref": "GITHUB_WORKFLOW_REF",
        "workflow_sha": "GITHUB_WORKFLOW_SHA",
        "git_ref": "GITHUB_REF",
        "git_sha": "GITHUB_SHA",
        "job": "GITHUB_JOB",
        "runner_name": "RUNNER_NAME",
        "runner_os": "RUNNER_OS",
        "runner_arch": "RUNNER_ARCH",
        "runner_environment": "RUNNER_ENVIRONMENT",
    }
    result = {field: os.environ.get(variable, "").strip() for field, variable in names.items()}
    for field, value in result.items():
        if not value:
            raise EvidenceError(f"required GitHub host identity field {field} is missing")
    if result["repository"] != REPOSITORY:
        raise EvidenceError("host is running in an unexpected repository")
    if result["job"] != role:
        raise EvidenceError(f"expected job {role}, observed {result['job']}")
    if result["git_ref"] != SOURCE_REF:
        raise EvidenceError("live host evidence may only be produced from protected main")
    if result["runner_environment"] != "github-hosted":
        raise EvidenceError("participant jobs must use GitHub-hosted runners")
    result["actor_id"] = (
        f"{result['repository']}#run-{result['run_id']}.attempt-{result['run_attempt']}."
        f"{role}.{result['runner_name']}"
    )
    return result


def _participant_key_document(
    key: Ed25519PrivateKey,
    participant_id: str,
    role: str,
    *,
    fixture: bool = False,
) -> dict[str, Any]:
    public = key.public_key()
    return {
        "format": KEY_FORMAT,
        "participant_id": participant_id,
        "role": role,
        "key_algorithm": "Ed25519",
        "key_id": _key_id(public),
        "public_key_hex": _raw_public_key(public).hex(),
        "host": _host_identity(role, fixture=fixture),
    }


def _make_event(
    *,
    sequence: int,
    previous_event_digest: str,
    event_type: str,
    epoch_id: str,
    epoch_number: int,
    route: Mapping[str, Any],
    details: Mapping[str, Any],
) -> dict[str, Any]:
    core = {
        "sequence": sequence,
        "event_type": event_type,
        "epoch_id": epoch_id,
        "epoch_number": epoch_number,
        "route": dict(route),
        "route_digest": _digest(route),
        "details": dict(details),
        "previous_event_digest": previous_event_digest,
    }
    return {**core, "event_digest": _digest(core)}


def _derive_execution_id(epoch_id: str, attempt_id: str, request_digest: str) -> str:
    return "urn:sha256:" + _digest({
        "epoch_id": epoch_id,
        "attempt_id": attempt_id,
        "request_digest": request_digest,
    })


def _build_authority_material(
    authority_key: Ed25519PrivateKey,
    *,
    fixture: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    host = _host_identity("authority_host", fixture=fixture)
    run_id = host["run_id"]
    attempt_id = "proof-run:fixture:000001" if fixture else f"proof-run:{run_id}:000001"
    epoch_id = "proof-route-epoch-fixture" if fixture else f"proof-route-epoch-{run_id}"
    runner_id = "lean-worker-fixture" if fixture else f"lean-worker-{run_id}"
    owner_id = "route-owner-fixture" if fixture else f"route-owner-{run_id}"

    request_core = {
        "format": "in-formation.proof-action-request/0.1",
        "attempt_id": attempt_id,
        "query_label": "establish identity",
        "plan_digest": "1" * 64,
        "proof_ground_digest": "2" * 64,
        "candidate_transition": {
            "transition_id": "transition-identity",
            "source_id": "obligation-root",
            "tactic": "rfl",
            "proposed_subgoal_ids": [],
        },
    }
    request = {**request_core, "request_digest": _digest(request_core)}
    route = {
        "host_id": "proof-authority-host",
        "worker_id": "proof-runner-host",
        "request_channel": f"proof-request-{run_id}",
        "result_channel": f"proof-result-{run_id}",
        "policy": {"lease_ticks": 3, "max_attempts": 4, "window_size": 8},
    }

    opened = _make_event(
        sequence=1,
        previous_event_digest="0" * 64,
        event_type="opened",
        epoch_id=epoch_id,
        epoch_number=1,
        route=route,
        details={
            "predecessor_close_digest": None,
            "owner_generation": 1,
            "owner_id": owner_id,
        },
    )
    admitted = _make_event(
        sequence=2,
        previous_event_digest=opened["event_digest"],
        event_type="admitted",
        epoch_id=epoch_id,
        epoch_number=1,
        route=route,
        details={
            "owner_id": owner_id,
            "owner_generation": 1,
            "attempt_id": attempt_id,
            "request_digest": request["request_digest"],
            "request_sequence": 1,
        },
    )
    execution_id = _derive_execution_id(epoch_id, attempt_id, request["request_digest"])
    authorized = _make_event(
        sequence=3,
        previous_event_digest=admitted["event_digest"],
        event_type="execution_authorized",
        epoch_id=epoch_id,
        epoch_number=1,
        route=route,
        details={
            "owner_id": owner_id,
            "owner_generation": 1,
            "attempt_id": attempt_id,
            "request_digest": request["request_digest"],
            "request_sequence": 1,
            "admission_event_digest": admitted["event_digest"],
            "execution_id": execution_id,
            "runner_id": runner_id,
        },
    )
    ledger_core = {"format": LEDGER_FORMAT, "entries": [opened, admitted, authorized]}
    ledger = {**ledger_core, "ledger_digest": _digest(ledger_core)}

    attestation_core = {
        "format": AUTHORITY_ATTESTATION_FORMAT,
        "signature_algorithm": "Ed25519",
        "authority_id": "route-authority-fixture" if fixture else f"route-authority-{run_id}",
        "authority_key_id": _key_id(authority_key.public_key()),
        "ledger_digest": ledger["ledger_digest"],
        "ledger_sequence": len(ledger["entries"]),
        "authorization_event_digest": authorized["event_digest"],
        "execution_id": execution_id,
        "attempt_id": attempt_id,
        "request_digest": request["request_digest"],
        "runner_id": runner_id,
    }
    attestation_digest = _digest(attestation_core)
    signed_payload = {**attestation_core, "attestation_digest": attestation_digest}
    authority_attestation = {
        **signed_payload,
        "signature": authority_key.sign(canonical_bytes(signed_payload)).hex(),
    }
    key_doc = _participant_key_document(
        authority_key,
        attestation_core["authority_id"],
        "authority_host",
        fixture=fixture,
    )
    return ledger, request, authority_attestation, key_doc


def _verify_authority_material(
    ledger: Mapping[str, Any],
    request: Mapping[str, Any],
    attestation: Mapping[str, Any],
    key_doc: Mapping[str, Any],
) -> dict[str, Any]:
    if key_doc.get("format") != KEY_FORMAT or key_doc.get("role") != "authority_host":
        raise EvidenceError("authority public-key document has the wrong format or role")
    if key_doc.get("key_algorithm") != "Ed25519":
        raise EvidenceError("authority public-key algorithm is unsupported")
    try:
        public_raw = bytes.fromhex(str(key_doc.get("public_key_hex", "")))
        public_key = Ed25519PublicKey.from_public_bytes(public_raw)
    except (ValueError, TypeError) as exc:
        raise EvidenceError("authority public key is malformed") from exc
    if _key_id(public_key) != key_doc.get("key_id"):
        raise EvidenceError("authority key fingerprint mismatch")

    expected_fields = {
        "format", "signature_algorithm", "authority_id", "authority_key_id",
        "ledger_digest", "ledger_sequence", "authorization_event_digest",
        "execution_id", "attempt_id", "request_digest", "runner_id",
        "attestation_digest", "signature",
    }
    if set(attestation) != expected_fields:
        raise EvidenceError("authority ledger attestation fields are invalid")
    if attestation["format"] != AUTHORITY_ATTESTATION_FORMAT or attestation["signature_algorithm"] != "Ed25519":
        raise EvidenceError("authority ledger attestation format is unsupported")
    core = {key: value for key, value in attestation.items() if key not in {"attestation_digest", "signature"}}
    if attestation["attestation_digest"] != _digest(core):
        raise EvidenceError("authority ledger attestation digest mismatch")
    signed_payload = {**core, "attestation_digest": attestation["attestation_digest"]}
    signature = attestation["signature"]
    if not isinstance(signature, str) or len(signature) != 128:
        raise EvidenceError("authority attestation signature must be 64-byte hex")
    try:
        public_key.verify(bytes.fromhex(signature), canonical_bytes(signed_payload))
    except (InvalidSignature, ValueError) as exc:
        raise EvidenceError("authority ledger attestation signature verification failed") from exc

    ledger_core = {key: value for key, value in ledger.items() if key != "ledger_digest"}
    if ledger.get("format") != LEDGER_FORMAT or ledger.get("ledger_digest") != _digest(ledger_core):
        raise EvidenceError("route ledger digest mismatch")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise EvidenceError("route ledger must contain events")
    event = entries[-1]
    try:
        validated_event = validate_execution_authorization_event(event)
        validated_request = validate_request_document(request)
    except (CompletionReceiptError, TypeError, ValueError) as exc:
        raise EvidenceError(f"authority documents failed request/event validation: {exc}") from exc
    details = validated_event["details"]
    if (
        attestation["authority_id"] != key_doc["participant_id"]
        or attestation["authority_key_id"] != key_doc["key_id"]
        or attestation["ledger_digest"] != ledger["ledger_digest"]
        or attestation["ledger_sequence"] != len(entries)
        or attestation["authorization_event_digest"] != validated_event["event_digest"]
        or attestation["execution_id"] != details["execution_id"]
        or attestation["attempt_id"] != validated_request["attempt_id"]
        or attestation["request_digest"] != validated_request["request_digest"]
        or attestation["runner_id"] != details["runner_id"]
        or details["attempt_id"] != validated_request["attempt_id"]
        or details["request_digest"] != validated_request["request_digest"]
    ):
        raise EvidenceError("authority attestation does not bind the exact ledger, event, and request")
    return dict(validated_event)


def _build_result(request: Mapping[str, Any]) -> dict[str, Any]:
    result_core = {
        "format": "in-formation.proof-action-result/0.1",
        "attempt_id": request["attempt_id"],
        "request_digest": request["request_digest"],
        "return_evidence": {
            "evidence_ref": "encounter://proof-return/fixture",
            "encounter_id": "proof-return-fixture",
            "payload_digest": "3" * 64,
            "canonicalization": "canonical-json-v1",
        },
        "proof_trace": {
            "format": "vgi.lean-proof-trace/0.1",
            "transitions": [
                {
                    "attempt_id": request["attempt_id"],
                    "transition_id": "transition-identity",
                    "status": "elaborated",
                }
            ],
        },
    }
    return {**result_core, "result_digest": _digest(result_core)}


def _build_runner_material(
    runner_key: Ed25519PrivateKey,
    ledger: Mapping[str, Any],
    request: Mapping[str, Any],
    authority_attestation: Mapping[str, Any],
    authority_key_doc: Mapping[str, Any],
    *,
    fixture: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _check_key_doc(authority_key_doc, "authority_host", "authority_host")
    event = _verify_authority_material(
        ledger, request, authority_attestation, authority_key_doc
    )
    runner_host_identity = _host_identity("runner_host", fixture=fixture)
    authority_host_identity = authority_key_doc["host"]
    for field in ("repository", "run_id", "run_attempt", "run_number", "workflow_ref", "workflow_sha", "git_ref", "git_sha"):
        if authority_host_identity[field] != runner_host_identity[field]:
            raise EvidenceError(f"authority and runner host differ in {field}")
    result = _build_result(request)
    receipt = create_completion_receipt(
        event,
        request,
        result,
        private_key=runner_key,
    )
    runner_host = _host_identity("runner_host", fixture=fixture)
    run_id = runner_host["run_id"]
    runner_id = "lean-worker-fixture" if fixture else f"lean-worker-{run_id}"
    if receipt["runner_id"] != runner_id:
        raise EvidenceError("runner public identity differs from route authorization")
    key_doc = _participant_key_document(
        runner_key,
        runner_id,
        "runner_host",
        fixture=fixture,
    )
    return result, receipt, key_doc


def _check_key_doc(document: Mapping[str, Any], expected_role: str, expected_job: str) -> None:
    if document.get("format") != KEY_FORMAT or document.get("role") != expected_role:
        raise EvidenceError("participant key document format or role is invalid")
    host = document.get("host")
    if not isinstance(host, Mapping):
        raise EvidenceError("participant key document is missing its host identity")
    required = {
        "repository", "run_id", "run_attempt", "run_number", "workflow_ref",
        "workflow_sha", "git_ref", "git_sha", "job", "runner_name",
        "runner_os", "runner_arch", "runner_environment", "actor_id",
    }
    if set(host) != required:
        raise EvidenceError("participant host identity fields are invalid")
    if (
        host["repository"] != REPOSITORY
        or host["job"] != expected_job
        or host["git_ref"] != SOURCE_REF
        or host["workflow_ref"] != f"{REPOSITORY}/{WORKFLOW_PATH}@{SOURCE_REF}"
        or host["runner_environment"] != "github-hosted"
        or not isinstance(host["runner_name"], str)
        or not host["runner_name"]
    ):
        raise EvidenceError("participant host identity does not match the protected hosted job")
    if document.get("key_algorithm") != "Ed25519":
        raise EvidenceError("participant key algorithm is unsupported")
    try:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(document["public_key_hex"])))
    except (ValueError, TypeError, KeyError) as exc:
        raise EvidenceError("participant public key is malformed") from exc
    if _key_id(public) != document.get("key_id"):
        raise EvidenceError("participant public-key fingerprint mismatch")


def _participant_key_predicate(document: Mapping[str, Any], subject_sha256: str) -> dict[str, Any]:
    """Bind the participant role and host identity to these exact public-key bytes."""
    return {
        "schema": KEY_PREDICATE_SCHEMA,
        "subject_sha256": subject_sha256,
        "participant": {
            "participant_id": document["participant_id"],
            "role": document["role"],
            "key_algorithm": document["key_algorithm"],
            "key_id": document["key_id"],
            "host": dict(document["host"]),
        },
    }


def write_key_predicate(
    key_path: Path,
    output_path: Path,
    expected_role: str,
    expected_job: str,
) -> None:
    document = _read(key_path)
    _check_key_doc(document, expected_role, expected_job)
    subject_digest = hashlib.sha256(key_path.read_bytes()).hexdigest()
    _write(output_path, _participant_key_predicate(document, subject_digest))


def _gh_version() -> tuple[int, int, int]:
    completed = subprocess.run(["gh", "--version"], check=True, capture_output=True, text=True)
    import re
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", completed.stdout)
    if not match:
        raise EvidenceError("cannot parse GitHub CLI version")
    return tuple(int(item) for item in match.groups())


def verify_key_attestation(path: Path, expected_role: str, expected_job: str) -> dict[str, Any]:
    """Verify the key file's GitHub provenance before using it as a trust anchor."""
    document = _read(path)
    _check_key_doc(document, expected_role, expected_job)
    if _gh_version() < GH_MIN_VERSION:
        raise EvidenceError("GitHub CLI 2.103.3 or newer is required")
    command = [
        "gh", "attestation", "verify", str(path),
        "--repo", REPOSITORY,
        "--signer-workflow", SIGNER_WORKFLOW,
        "--source-ref", SOURCE_REF,
        "--predicate-type", PREDICATE_TYPE,
        "--deny-self-hosted-runners",
        "--format", "json",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        verification = json.loads(completed.stdout)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if exc.stderr else str(exc)
        raise EvidenceError(f"GitHub key-document attestation failed: {detail}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceError("GitHub CLI returned invalid attestation JSON") from exc

    if not isinstance(verification, list):
        raise EvidenceError("GitHub CLI attestation output must be an array")
    target_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    matches = []
    for item in verification:
        if not isinstance(item, Mapping):
            continue
        result = item.get("verificationResult")
        if not isinstance(result, Mapping):
            continue
        statement = result.get("statement")
        if not isinstance(statement, Mapping):
            continue
        subjects = statement.get("subject", [])
        if isinstance(subjects, list) and any(
            isinstance(subject, Mapping)
            and isinstance(subject.get("digest"), Mapping)
            and subject["digest"].get("sha256") == target_digest
            for subject in subjects
        ):
            matches.append((statement, result))
    if not matches:
        raise EvidenceError("no verified GitHub attestation binds the exact public-key file bytes")
    statement, result = matches[0]
    expected_predicate = _participant_key_predicate(document, target_digest)
    if statement.get("predicateType") != PREDICATE_TYPE or statement.get("predicate") != expected_predicate:
        raise EvidenceError("verified GitHub attestation predicate does not bind the participant role and host identity")
    signature = result.get("signature")
    if not isinstance(signature, Mapping) or not isinstance(signature.get("certificate"), Mapping):
        raise EvidenceError("verified key attestation is missing its signing certificate")
    return {
        "verified": True,
        "role": expected_role,
        "job": expected_job,
        "subject_sha256": target_digest,
        "signer_workflow": SIGNER_WORKFLOW,
        "source_ref": SOURCE_REF,
        "self_hosted_runners_denied": True,
    }


def build_fixture(out_dir: Path) -> None:
    """Build deterministic non-secret test artifacts; never use these keys live."""
    authority_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32))
    runner_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("22" * 32))
    ledger, request, attestation, authority_key_doc = _build_authority_material(
        authority_key, fixture=True
    )
    result, receipt, runner_key_doc = _build_runner_material(
        runner_key, ledger, request, attestation, authority_key_doc, fixture=True
    )
    authority_dir = out_dir / "authority"
    runner_dir = out_dir / "runner"
    _write(authority_dir / "route-ledger.json", ledger)
    _write(authority_dir / "request.json", request)
    _write(authority_dir / "authority-attestation.json", attestation)
    authority_key_path = authority_dir / "authority-public-key.json"
    _write(authority_key_path, authority_key_doc)
    write_key_predicate(
        authority_key_path,
        authority_dir / "authority-public-key.predicate.json",
        "authority_host",
        "authority_host",
    )
    _write(runner_dir / "result.json", result)
    _write(runner_dir / "completion-receipt.json", receipt)
    runner_key_path = runner_dir / "runner-public-key.json"
    _write(runner_key_path, runner_key_doc)
    write_key_predicate(
        runner_key_path,
        runner_dir / "runner-public-key.predicate.json",
        "runner_host",
        "runner_host",
    )
    verifier_host = {
        "format": "in-formation.proof-runner-verifier-host/0.1",
        "host": _host_identity("independent_verifier_host", fixture=True),
    }
    _write(out_dir / "verifier-host.json", verifier_host)


def produce_authority(out_dir: Path) -> None:
    key = Ed25519PrivateKey.generate()
    ledger, request, attestation, key_doc = _build_authority_material(key, fixture=False)
    _write(out_dir / "route-ledger.json", ledger)
    _write(out_dir / "request.json", request)
    _write(out_dir / "authority-attestation.json", attestation)
    key_path = out_dir / "authority-public-key.json"
    _write(key_path, key_doc)
    write_key_predicate(
        key_path,
        out_dir / "authority-public-key.predicate.json",
        "authority_host",
        "authority_host",
    )


def produce_runner(authority_dir: Path, out_dir: Path) -> None:
    ledger = _read(authority_dir / "route-ledger.json")
    request = _read(authority_dir / "request.json")
    attestation = _read(authority_dir / "authority-attestation.json")
    authority_key_doc = _read(authority_dir / "authority-public-key.json")
    runner_key = Ed25519PrivateKey.generate()
    result, receipt, runner_key_doc = _build_runner_material(
        runner_key, ledger, request, attestation, authority_key_doc, fixture=False
    )
    _write(out_dir / "result.json", result)
    _write(out_dir / "completion-receipt.json", receipt)
    runner_key_path = out_dir / "runner-public-key.json"
    _write(runner_key_path, runner_key_doc)
    write_key_predicate(
        runner_key_path,
        out_dir / "runner-public-key.predicate.json",
        "runner_host",
        "runner_host",
    )


def write_verifier_host(output_path: Path, *, fixture: bool = False) -> None:
    document = {
        "format": "in-formation.proof-runner-verifier-host/0.1",
        "host": _host_identity("independent_verifier_host", fixture=fixture),
    }
    _write(output_path, document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fixture = sub.add_parser("fixture", help="write deterministic test evidence")
    fixture.add_argument("--out-dir", type=Path, required=True)

    authority = sub.add_parser("authority", help="produce a route-authority checkpoint")
    authority.add_argument("--out-dir", type=Path, required=True)

    runner = sub.add_parser("runner", help="produce the signed proof-action result")
    runner.add_argument("--authority-dir", type=Path, required=True)
    runner.add_argument("--out-dir", type=Path, required=True)

    verify = sub.add_parser("verify-key-attestation", help="verify a participant public-key attestation")
    verify.add_argument("--path", type=Path, required=True)
    verify.add_argument("--role", choices=("authority_host", "runner_host"), required=True)
    verify.add_argument("--job", choices=("authority_host", "runner_host"), required=True)

    verifier = sub.add_parser("verifier-host", help="write the independent third-host identity")
    verifier.add_argument("--output", type=Path, required=True)
    verifier.add_argument("--fixture", action="store_true", help="write deterministic test identity")

    args = parser.parse_args()
    try:
        if args.command == "fixture":
            build_fixture(args.out_dir)
        elif args.command == "authority":
            produce_authority(args.out_dir)
        elif args.command == "runner":
            produce_runner(args.authority_dir, args.out_dir)
        elif args.command == "verify-key-attestation":
            result = verify_key_attestation(args.path, args.role, args.job)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "verifier-host":
            write_verifier_host(args.output, fixture=args.fixture)
    except (EvidenceError, CompletionReceiptError, OSError, ValueError) as exc:
        parser.exit(1, f"proof-runner reconstruction: {exc}\n")


if __name__ == "__main__":
    main()
