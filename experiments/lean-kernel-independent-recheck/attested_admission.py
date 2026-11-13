#!/usr/bin/env python3
"""GitHub-attestation-gated admission of the fixed Lean/VGI proof receipt.

A checker-supplied public key is NOT a trust root. This adapter uses patched
GitHub CLI / Sigstore verification to authenticate the exact bytes of the key,
checker observation, and signed statement against a pinned repository/workflow,
main-branch ref, source commit, and GitHub-hosted runner policy *before* passing
the key to the existing VGI receipt adapter.

This is GitHub workflow provenance, not formal verification of the workflow,
independence of host fault domains, or proof-term checking by a second kernel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from term_receipt import TermReceiptError, _read, _write, admit, digest

REPO = "Kier73/In-Formation-Space"
REPO_ID = "1454466415"  # stable GitHub repository ID, not the repository name
WORKFLOW = REPO + "/.github/workflows/lean-term-receipt.yml"
MAIN_REF = "refs/heads/main"
CERT_IDENTITY = "https://github.com/" + WORKFLOW + "@" + MAIN_REF
FORMAT = "in-formation.lean-attested-checker-admission/0.1"
PREDICATE = "https://slsa.dev/provenance/v1"
MIN_GH_VERSION = (2, 102, 0)  # GHSA-wjmr-j3rp-mh2g & GHSA-4mq3-hpgx-9cx8
SUBJECTS = ("signed", "checker", "public_key")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require_context(env: Mapping[str, str]) -> dict[str, str]:
    """Do not let a pull-request/fork/job override authorize itself as main."""
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": MAIN_REF,
        "GITHUB_JOB": "vgi_attested_admission",
        "GITHUB_WORKFLOW_REF": WORKFLOW + "@" + MAIN_REF,
    }
    for key, value in expected.items():
        if env.get(key) != value:
            raise TermReceiptError(f"trusted GitHub Actions context mismatch: {key}")
    sha = env.get("GITHUB_SHA", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    run_attempt = env.get("GITHUB_RUN_ATTEMPT", "")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise TermReceiptError("GITHUB_SHA must be an exact source commit")
    if not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise TermReceiptError("GITHUB_RUN_ID is invalid")
    if not re.fullmatch(r"[1-9][0-9]*", run_attempt):
        raise TermReceiptError("GITHUB_RUN_ATTEMPT is invalid")
    return {"git_sha": sha, "run_id": run_id, "run_attempt": run_attempt}


def require_gh_version(output: str) -> str:
    match = re.search(r"\bgh version ([0-9]+)\.([0-9]+)\.([0-9]+)\b", output)
    if not match:
        raise TermReceiptError("GitHub CLI version could not be established")
    version = tuple(int(x) for x in match.groups())
    if version < MIN_GH_VERSION:
        raise TermReceiptError("unpatched GitHub CLI rejected: requires >=2.102.0")
    return ".".join(map(str, version))


def _execute(args: list[str], *, runner: Callable[..., Any] = subprocess.run) -> str:
    try:
        process = runner(args, capture_output=True, text=True, check=False, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise TermReceiptError(f"GitHub attestation verifier did not execute: {exc}") from exc
    if process.returncode != 0:
        raise TermReceiptError(f"GitHub attestation verification failed: {process.stderr[-1200:]}")
    if not isinstance(process.stdout, str) or not process.stdout.strip():
        raise TermReceiptError("GitHub attestation verifier returned no evidence")
    return process.stdout


def parse_verified_attestation(raw: str, *, subject_digest: str) -> dict:
    """Only accept a successful gh cryptographic verifier's JSON; never raw bundles."""
    try:
        reports = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise TermReceiptError("invalid GitHub verifier JSON") from exc
    if not isinstance(reports, list) or not reports:
        raise TermReceiptError("no verified attestations")
    matching = []
    for report in reports:
        try:
            result = report["verificationResult"]
            cert = result["signature"]["certificate"]
            statement = result["statement"]
            subjects = statement["subject"]
            rid = cert["sourceRepositoryIdentifier"]
        except (KeyError, TypeError, IndexError):
            continue
        if str(rid) != REPO_ID or statement.get("predicateType") != PREDICATE:
            continue
        if not isinstance(subjects, list):
            continue
        if not any(
            isinstance(s, dict) and isinstance(s.get("digest"), dict)
            and s["digest"].get("sha256") == subject_digest
            for s in subjects
        ):
            continue
        matching.append({
            "source_repository_id": str(rid),
            "subject_sha256": subject_digest,
            "predicate_type": PREDICATE,
        })
    if not matching:
        raise TermReceiptError("no verifier result matches pinned repository ID and subject digest")
    return matching[0]


def verify_subjects(
    files: Mapping[str, Path], context: Mapping[str, str],
    *, runner: Callable[..., Any] = subprocess.run,
) -> tuple[str, dict]:
    """Invoke patched gh for each subject with every authority constraint fixed."""
    if set(files) != set(SUBJECTS):
        raise TermReceiptError("all three required attested subjects must be supplied")
    version = require_gh_version(_execute(["gh", "--version"], runner=runner))
    results = {}
    for name in SUBJECTS:
        path = files[name]
        if path.is_symlink() or not path.is_file():
            raise TermReceiptError(f"missing or symlinked attested subject: {name}")
        expected_digest = _sha(path.read_bytes())
        command = [
            "gh", "attestation", "verify", str(path),
            "--repo", REPO,
            # Exact SAN enforces the workflow and ref in a single mutually
            # exclusive policy flag (gh forbids --signer-workflow with it).
            "--cert-identity", CERT_IDENTITY,
            "--source-ref", MAIN_REF,
            "--source-digest", context["git_sha"],
            "--predicate-type", PREDICATE,
            "--deny-self-hosted-runners",
            "--format", "json",
        ]
        verified = _execute(command, runner=runner)
        details = parse_verified_attestation(verified, subject_digest=expected_digest)
        results[name] = {**details, "verification_result_sha256": _sha(verified.encode("utf-8"))}
    return version, results


def check_run_binding(runner: dict, checker: dict, context: Mapping[str, str]) -> None:
    for role, document in (("proof_runner", runner), ("independent_checker", checker)):
        host = document.get("host")
        if not isinstance(host, dict) or host.get("role") != role or host.get("job") != role:
            raise TermReceiptError(f"{role} evidence has a mismatched host role")
        if host.get("repository") != REPO:
            raise TermReceiptError("runner/checker repository differs from attestation policy")
        for key in ("git_sha", "run_id", "run_attempt"):
            if host.get(key) != context[key]:
                raise TermReceiptError(f"{role} evidence not bound to verified workflow run: {key}")


def attest_and_admit(
    *, runner_path: Path, checker_path: Path, signed_path: Path, public_key_path: Path,
    env: Mapping[str, str], command_runner: Callable[..., Any] = subprocess.run,
) -> dict:
    """The only main-branch entrypoint: policy check -> cryptographic attest -> VGI."""
    context = require_context(env)
    runner_doc = _read(runner_path)
    checker_doc = _read(checker_path)
    check_run_binding(runner_doc, checker_doc, context)
    version, subjects = verify_subjects({
        "signed": signed_path, "checker": checker_path,
        "public_key": public_key_path,
    }, context, runner=command_runner)

    # This key can be trusted for this narrowly scoped run only because the
    # independent gh verifier authenticated its bytes and pinned workflow.
    key = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise TermReceiptError("checker attestation key is not Ed25519")
    signed = _read(signed_path)
    receipt = admit(runner_doc, checker_doc, signed, key)

    report = {
        "format": FORMAT,
        "status": "attested_workflow_receipt_admitted",
        "trust_profile": "github-public-sigstore-provenance-plus-ed25519-fixture/0.1",
        "github_cli_version": version,
        "repository": REPO,
        "repository_id": REPO_ID,
        "workflow": WORKFLOW,
        "cert_identity": CERT_IDENTITY,
        "source_ref": MAIN_REF,
        "source_sha": context["git_sha"],
        "run_id": context["run_id"],
        "run_attempt": context["run_attempt"],
        "attested_subjects": subjects,
        "runner_observation_digest": runner_doc["document_digest"],
        "checker_observation_digest": checker_doc["document_digest"],
        "signed_receipt_digest": signed["document_digest"],
        "obligation_id": receipt.obligation_id,
        "proof_term_fingerprint": receipt.proof_term_fingerprint,
        "environment_fingerprint": receipt.environment_fingerprint,
        "checker_id": receipt.checker_id,
        "checker_version": receipt.checker_version,
        "vgi_kernel_status": "kernel_accepted",
        "not_established": [
            "checker software is uncompromised; workflow identity does not prove honest execution",
            "production checker-key registration, rotation, or revocation",
            "independent physical host or implementation-diverse kernel",
            "arbitrary proof-term standalone kernel verification",
            "independently audited source-workflow security",
        ],
    }
    return {**report, "document_digest": digest(report)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--signed", type=Path, required=True)
    parser.add_argument("--checker-public", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = attest_and_admit(
            runner_path=args.runner, checker_path=args.checker,
            signed_path=args.signed, public_key_path=args.checker_public,
            env=os.environ,
        )
        _write(args.output, output)
        print("authenticated GitHub workflow evidence admitted to VGI for fixed Lean theorem")
    except (TermReceiptError, OSError, TypeError, ValueError, KeyError) as exc:
        parser.exit(1, f"authenticated checker authority rejected: {exc}\n")


if __name__ == "__main__":
    main()
