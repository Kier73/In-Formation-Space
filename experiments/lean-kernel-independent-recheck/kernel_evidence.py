#!/usr/bin/env python3
"""Independently rerun one pinned Lean theorem and explicit negative controls.

A source-preserving Lean process observation is not a canonical proof-term
fingerprint or a VGI VerifiedKernelReceipt. This bounded experiment records
exactly what a separate checker observed, including axiom-audit output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
TOOLCHAIN = "leanprover/lean4:v4.15.0"
RUNNER_FORMAT = "in-formation.lean-kernel-runner-observation/0.1"
CHECKER_FORMAT = "in-formation.lean-kernel-independent-check/0.1"
CASE_FORMAT = "in-formation.lean-kernel-case-observation/0.1"
CASES = (
    ("KernelTrial.lean", "KernelTrial.identity", True),
    ("KernelTrialSorry.lean", "KernelTrial.sorryTrial", False),
    ("KernelTrialInvalid.lean", "KernelTrial.falseClaim", False),
    ("KernelTrialAxiom.lean", "KernelTrial.axiomTrial", False),
)


class KernelEvidenceError(ValueError):
    """One source, process observation, or host correlation failed validation."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> str:
    return _sha(_canonical(value))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(dict(value)) + b"\n")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise KernelEvidenceError("evidence must be a JSON object")
    return value


def _check_digest(document: Mapping[str, Any], label: str) -> None:
    expected = document.get("document_digest")
    if not isinstance(expected, str) or expected != _digest({
        k: v for k, v in document.items() if k != "document_digest"
    }):
        raise KernelEvidenceError(f"{label} document digest mismatch")


def _host(role: str) -> dict[str, str]:
    if role not in ("proof_runner", "independent_checker"):
        raise KernelEvidenceError("unknown role")
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY", "offline-fixture"),
        "run_id": os.environ.get("GITHUB_RUN_ID", "offline"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "0"),
        "git_sha": os.environ.get("GITHUB_SHA", "offline"),
        "git_ref": os.environ.get("GITHUB_REF", "offline"),
        "job": os.environ.get("GITHUB_JOB", role),
        "role": role,
        "runner_name": os.environ.get("RUNNER_NAME", "offline"),
        "runner_environment": os.environ.get("RUNNER_ENVIRONMENT", "offline"),
    }


def _validate_host(host: Any, role: str) -> None:
    required = {
        "repository", "run_id", "run_attempt", "git_sha", "git_ref",
        "job", "role", "runner_name", "runner_environment",
    }
    if not isinstance(host, dict) or set(host) != required:
        raise KernelEvidenceError(f"{role} host identity fields are invalid")
    if host["role"] != role or host["job"] != role:
        raise KernelEvidenceError(f"{role} host role does not match the workflow job")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if (
            host["repository"] != "Kier73/In-Formation-Space"
            or host["git_ref"] not in ("refs/heads/main", os.environ.get("GITHUB_REF"))
            or host["runner_environment"] != "github-hosted"
        ):
            raise KernelEvidenceError(f"{role} host is not the expected GitHub-hosted workflow")


def _lean_version() -> str:
    completed = subprocess.run(
        ["lake", "env", "lean", "--version"],
        cwd=ROOT, text=True, capture_output=True, timeout=120, check=True,
    )
    version = (completed.stdout + completed.stderr).strip()
    if "Lean" not in version:
        raise KernelEvidenceError("Lean compiler version could not be identified")
    return version


def _source_bytes(name: str) -> bytes:
    if name not in {case[0] for case in CASES}:
        raise KernelEvidenceError("source is not an allowed fixed Lean fixture")
    path = ROOT / name
    if path.is_symlink() or not path.is_file():
        raise KernelEvidenceError("source fixture is missing or a symbolic link")
    return path.read_bytes()


def _check_compiler_observation(
    *,
    name: str,
    theorem: str,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> bool:
    if exit_code != 0:
        return False
    output = stdout + "\n" + stderr
    if re.search(r"\b(sorryAx|sorry|admit|error:|warning:)\b", output, re.IGNORECASE):
        return False
    # Requiring the exact theorem name prevents accepting an unrelated no-axioms
    # banner or a successful compilation of another source.
    pattern = re.compile(
        re.escape(theorem) + r"[^\r\n]*does not depend on any axioms",
        re.IGNORECASE,
    )
    return pattern.search(output) is not None


def _observe(name: str, theorem: str, should_accept: bool) -> dict[str, Any]:
    source = _source_bytes(name)
    try:
        completed = subprocess.run(
            ["lake", "env", "lean", name],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise KernelEvidenceError(f"Lean timed out on {name}") from exc
    kernel_checked = _check_compiler_observation(
        name=name,
        theorem=theorem,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    observation = {
        "format": CASE_FORMAT,
        "filename": name,
        "theorem": theorem,
        "source_sha256": _sha(source),
        "expected_axiom_free": should_accept,
        "process_exit_code": completed.returncode,
        "stdout_sha256": _sha(completed.stdout.encode("utf-8")),
        "stderr_sha256": _sha(completed.stderr.encode("utf-8")),
        "axiom_free_checker_output": kernel_checked,
        "status": "checked_without_axioms" if kernel_checked else "not_established",
    }
    return {**observation, "document_digest": _digest(observation)}


def _check_cases(cases: Any, *, strict_expected: bool = True) -> None:
    if not isinstance(cases, list) or len(cases) != len(CASES):
        raise KernelEvidenceError("case observations must cover the complete fixed set")
    for (name, theorem, expected), document in zip(CASES, cases):
        if not isinstance(document, dict):
            raise KernelEvidenceError("case observation must be an object")
        required = {
            "format", "filename", "theorem", "source_sha256",
            "expected_axiom_free", "process_exit_code", "stdout_sha256",
            "stderr_sha256", "axiom_free_checker_output", "status", "document_digest",
        }
        if set(document) != required or document["format"] != CASE_FORMAT:
            raise KernelEvidenceError("case observation fields or format are invalid")
        _check_digest(document, name)
        if (
            document["filename"] != name
            or document["theorem"] != theorem
            or document["source_sha256"] != _sha(_source_bytes(name))
            or document["expected_axiom_free"] is not expected
        ):
            raise KernelEvidenceError("case observation is not bound to the fixed source")
        checked = document["axiom_free_checker_output"]
        if not isinstance(checked, bool):
            raise KernelEvidenceError("case checker status must be boolean")
        if document["status"] != (
            "checked_without_axioms" if checked else "not_established"
        ):
            raise KernelEvidenceError("case reported status is internally inconsistent")
        if checked and document["process_exit_code"] != 0:
            raise KernelEvidenceError("nonzero Lean process cannot establish kernel acceptance")
        for field in ("stdout_sha256", "stderr_sha256"):
            value = document[field]
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise KernelEvidenceError("case stream digest is malformed")
        if strict_expected and checked is not expected:
            raise KernelEvidenceError(
                f"{name}: expected {'axiom-free acceptance' if expected else 'rejection'}, got {document['status']}"
            )


def produce(output: Path) -> None:
    if (ROOT / "lean-toolchain").read_text(encoding="utf-8").strip() != TOOLCHAIN:
        raise KernelEvidenceError("unpinned Lean toolchain")
    cases = [_observe(*case) for case in CASES]
    _check_cases(cases)
    report = {
        "format": RUNNER_FORMAT,
        "host": _host("proof_runner"),
        "toolchain": TOOLCHAIN,
        "lean_version": _lean_version(),
        "cases": cases,
    }
    _write(output, {**report, "document_digest": _digest(report)})


def verify(runner_document: Path, output: Path) -> None:
    runner = _read(runner_document)
    if set(runner) != {
        "format", "host", "toolchain", "lean_version", "cases", "document_digest"
    } or runner["format"] != RUNNER_FORMAT:
        raise KernelEvidenceError("runner evidence format or fields are invalid")
    _check_digest(runner, "runner")
    _validate_host(runner["host"], "proof_runner")
    _check_cases(runner["cases"])
    if runner["toolchain"] != TOOLCHAIN:
        raise KernelEvidenceError("runner used an unexpected Lean toolchain")
    version = _lean_version()
    if runner["lean_version"] != version:
        raise KernelEvidenceError("checker and runner Lean versions do not match")
    checker_host = _host("independent_checker")
    _validate_host(checker_host, "independent_checker")
    for field in ("repository", "run_id", "run_attempt", "git_sha", "git_ref"):
        if runner["host"][field] != checker_host[field]:
            raise KernelEvidenceError("runner and checker are not from the same source/run")
    if runner["host"]["job"] == checker_host["job"]:
        raise KernelEvidenceError("runner and checker must be separate jobs")

    checked = [_observe(*case) for case in CASES]
    _check_cases(checked)
    report = {
        "format": CHECKER_FORMAT,
        "status": "independently_rechecked",
        "runner_host": runner["host"],
        "checker_host": checker_host,
        "toolchain": TOOLCHAIN,
        "lean_version": version,
        "runner_observation_digest": runner["document_digest"],
        "runner_case_digests": [case["document_digest"] for case in runner["cases"]],
        "checker_case_digests": [case["document_digest"] for case in checked],
        "accepted_theorem": "KernelTrial.identity",
        "negative_cases_rejected": [
            "KernelTrial.sorryTrial",
            "KernelTrial.falseClaim",
            "KernelTrial.axiomTrial",
        ],
        "vgi_verified_kernel_receipt_issued": False,
        "proof_term_fingerprint_observed": False,
        "not_established": [
            "canonical elaborated Lean Expr/proof-term fingerprint",
            "authenticated VGI VerifiedKernelReceipt",
            "general theorem or arbitrary user-supplied tactic correctness",
            "independent physical or administrative fault domains",
            "direct E-CPU transport or a production distributed proof worker",
        ],
    }
    _write(output, {**report, "document_digest": _digest(report)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    producer = sub.add_parser("produce")
    producer.add_argument("--output", type=Path, required=True)
    verifier = sub.add_parser("verify")
    verifier.add_argument("--runner-report", type=Path, required=True)
    verifier.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "produce":
            produce(args.output)
        else:
            verify(args.runner_report, args.output)
    except (KernelEvidenceError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Lean kernel evidence rejected: {exc}\n")


if __name__ == "__main__":
    main()
