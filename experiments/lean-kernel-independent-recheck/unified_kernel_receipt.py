#!/usr/bin/env python3
"""A *single* VGI receipt requires two kinds of independently attested evidence.

(1) Signed source/term re-extraction under an authenticated checker key.
(2) A separate hosted check of the reconstructed serialized Expr using
    Lean.Kernel.check + Lean.Kernel.isDefEq, with negative controls.

These are different evidence types and cannot substitute for one another.
The GitHub/Sigstore trust root, not an artifact-supplied public key, authorizes
each exact artifact. The main-only workflow is the authority boundary.

This is bounded to fixed KernelTrial.identity / Lean 4.15.0. It is NOT
implementation-diverse proof checking, an arbitrary Lean checker, or an
assertion that separately scheduled jobs have independent fault domains.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import attested_admission as provenance
import serialized_kernel_evidence as serialized
import term_receipt as term
from vgi.proof import ProofGround, VerifiedKernelReceipt

REPO = provenance.REPO
REPO_ID = provenance.REPO_ID
MAIN_REF = provenance.MAIN_REF
WORKFLOW = REPO + "/.github/workflows/lean-unified-kernel-receipt.yml"
CERT_IDENTITY = "https://github.com/" + WORKFLOW + "@" + MAIN_REF
FORMAT = "in-formation.unified-attested-lean-kernel-receipt/0.1"
CHECKER_POLICY = "lean-4.15-unified-attested-serialized-kernel/0.1"
SUBJECT_NAMES = ("runner", "checker", "signed", "public_key", "serialized_kernel")
CASE_NAMES = serialized.SAMPLES


class UnifiedReceiptError(term.TermReceiptError):
    """Typed evidence, provenance or identity did not justify kernel admission."""


@dataclass(frozen=True, slots=True)
class ExactObligationBinding:
    """Full scope-sensitive VGI obligation identity, not surface theorem text."""
    obligation_id: str
    proof_term_fingerprint: str
    type_fingerprint: str
    environment_fingerprint: str
    runner_observation_digest: str

    @classmethod
    def from_runner(cls, runner: dict) -> "ExactObligationBinding":
        obligation = term.validate_observation(runner)
        return cls(
            obligation_id=obligation.fingerprint,
            proof_term_fingerprint=runner["proof_term_fingerprint"],
            type_fingerprint=runner["type_fingerprint"],
            environment_fingerprint=obligation.environment.environment_fingerprint,
            runner_observation_digest=runner["document_digest"],
        )


@dataclass(frozen=True, slots=True)
class SerializedKernelAcceptance:
    """A *validated report*, not a string/JSON boolean or a VGI receipt."""
    binding: ExactObligationBinding
    report_digest: str
    checker_source_sha256: str
    checker_run: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class AttestedSourceRecheck:
    """A separately authenticated, signed source/term re-extraction result."""
    binding: ExactObligationBinding
    signed_statement_digest: str
    checker_observation_digest: str
    key_subject_sha256: str


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest_shape(value: Any, what: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise UnifiedReceiptError(f"{what}: not a SHA-256 digest")


def require_main_authority_context(env: Mapping[str, str]) -> dict[str, str]:
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": MAIN_REF,
        "GITHUB_WORKFLOW_REF": WORKFLOW + "@" + MAIN_REF,
        "GITHUB_JOB": "vgi_unified_admission",
    }
    for key, expected_value in expected.items():
        if env.get(key) != expected_value:
            raise UnifiedReceiptError(f"unauthorized unified receipt context: {key}")
    context = {}
    for env_name, key, pattern in (
        ("GITHUB_SHA", "git_sha", r"[a-f0-9]{40}"),
        ("GITHUB_RUN_ID", "run_id", r"[1-9][0-9]*"),
        ("GITHUB_RUN_ATTEMPT", "run_attempt", r"[1-9][0-9]*"),
    ):
        value = env.get(env_name, "")
        if re.fullmatch(pattern, value) is None:
            raise UnifiedReceiptError(f"invalid {env_name}")
        context[key] = value
    return context


def match_host(host: Any, *, role: str, context: Mapping[str, str]) -> None:
    if not isinstance(host, dict):
        raise UnifiedReceiptError(f"{role}: missing host object")
    if host.get("role", role) != role or host.get("job") != role:
        raise UnifiedReceiptError(f"{role}: wrong host role/job")
    if host.get("repository") != REPO:
        raise UnifiedReceiptError(f"{role}: repository mismatch")
    for name in ("git_sha", "run_id", "run_attempt"):
        if host.get(name) != context[name]:
            raise UnifiedReceiptError(f"{role}: distinct commit or workflow run ({name})")


def validate_serialized_kernel_report(
    runner: dict, report: dict, context: Mapping[str, str],
) -> SerializedKernelAcceptance:
    binding = ExactObligationBinding.from_runner(runner)
    term._fields(report, {
        "format", "status", "theorem", "toolchain", "serialized_expression_profile",
        "checker_source_sha256", "original_runner_observation_digest",
        "proof_term_fingerprint", "type_fingerprint", "obligation_id",
        "environment_fingerprint", "checker_host", "cases",
        "vgi_verified_kernel_receipt_issued", "not_established", "document_digest",
    }, "serialized kernel report")
    term._bind_digest(report, "serialized kernel report")
    for name, expected in (
        ("format", serialized.FORMAT),
        ("status", "serialized_term_kernel_rechecked"),
        ("theorem", term.THEOREM),
        ("toolchain", term.TOOLCHAIN),
        ("serialized_expression_profile", term.TERM_FORMAT),
        ("checker_source_sha256", serialized.checker_source_sha()),
        ("original_runner_observation_digest", binding.runner_observation_digest),
        ("proof_term_fingerprint", binding.proof_term_fingerprint),
        ("type_fingerprint", binding.type_fingerprint),
        ("obligation_id", binding.obligation_id),
        ("environment_fingerprint", binding.environment_fingerprint),
    ):
        if report[name] != expected:
            raise UnifiedReceiptError(f"serialized kernel proof disagrees on {name}")
    if report["vgi_verified_kernel_receipt_issued"] is not False:
        raise UnifiedReceiptError("serialized observation may not claim direct receipt authority")
    if not isinstance(report["not_established"], list):
        raise UnifiedReceiptError("serialized report limitations are malformed")

    kernel_host = report["checker_host"]
    if not isinstance(kernel_host, dict) or set(kernel_host) != {
        "repository", "git_sha", "run_id", "run_attempt", "job"
    }:
        raise UnifiedReceiptError("serialized kernel checker host schema mismatch")
    match_host(kernel_host, role="serialized_kernel_checker", context=context)

    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != len(CASE_NAMES):
        raise UnifiedReceiptError("missing serialized-kernel positive/negative controls")
    for observation, case_name in zip(cases, CASE_NAMES):
        term._fields(observation, {
            "case", "input_sha256", "process_exit_code", "stdout_sha256",
            "stderr_sha256", "kernel_accepted_observed",
            "stdout_excerpt", "stderr_excerpt",
        }, f"{case_name} kernel case")
        if observation["case"] != case_name:
            raise UnifiedReceiptError("reordered or substituted kernel case")
        expected_export = serialized._mutant(runner["export"], case_name)
        expected_bytes = term.canonical(expected_export) + b"\n"
        if observation["input_sha256"] != _sha(expected_bytes):
            raise UnifiedReceiptError(f"{case_name} input digest not bound to original proof")
        for key in ("input_sha256", "stdout_sha256", "stderr_sha256"):
            _digest_shape(observation[key], key)
        if type(observation["process_exit_code"]) is not int:
            raise UnifiedReceiptError(f"{case_name} process exit code malformed")
        if not isinstance(observation["stdout_excerpt"], str) or not isinstance(observation["stderr_excerpt"], str):
            raise UnifiedReceiptError(f"{case_name} output evidence malformed")
        if case_name == "accepted":
            if observation["kernel_accepted_observed"] is not True or observation["process_exit_code"] != 0:
                raise UnifiedReceiptError("decoded proof was not accepted by kernel")
            if serialized.ACCEPTED_BANNER not in observation["stdout_excerpt"]:
                raise UnifiedReceiptError("accepted kernel banner missing")
        elif observation["kernel_accepted_observed"] is not False or observation["process_exit_code"] == 0:
            raise UnifiedReceiptError(f"{case_name} counterexample did not fail closed")
    return SerializedKernelAcceptance(
        binding=binding,
        report_digest=report["document_digest"],
        checker_source_sha256=report["checker_source_sha256"],
        checker_run=(context["git_sha"], context["run_id"], context["run_attempt"]),
    )


def authenticate_subject_bytes(
    files: Mapping[str, Path], context: Mapping[str, str],
    *, runner: Callable[..., Any] = subprocess.run,
) -> tuple[str, dict]:
    """Five separately verified subjects, exact workflow SAN and source commit."""
    if set(files) != set(SUBJECT_NAMES):
        raise UnifiedReceiptError("five required provenance subject types missing")
    version = provenance.require_gh_version(
        provenance._execute(["gh", "--version"], runner=runner)
    )
    verified = {}
    for name in SUBJECT_NAMES:
        path = files[name]
        if path.is_symlink() or not path.is_file():
            raise UnifiedReceiptError(f"{name}: subject is missing or symlinked")
        subject_digest = _sha(path.read_bytes())
        command = [
            "gh", "attestation", "verify", str(path),
            "--repo", REPO,
            "--cert-identity", CERT_IDENTITY,
            "--source-ref", MAIN_REF,
            "--source-digest", context["git_sha"],
            "--predicate-type", provenance.PREDICATE,
            "--deny-self-hosted-runners",
            "--format", "json",
        ]
        raw = provenance._execute(command, runner=runner)
        details = provenance.parse_verified_attestation(raw, subject_digest=subject_digest)
        verified[name] = {
            "kind": name,
            "sha256": subject_digest,
            "verification_result_sha256": _sha(raw.encode("utf-8")),
            "source_repository_id": details["source_repository_id"],
        }
        if details["source_repository_id"] != REPO_ID:
            raise UnifiedReceiptError(f"{name}: repository authority mismatch")
    return version, verified


def unify(
    *, runner_doc: dict, checker_doc: dict, signed_doc: dict,
    kernel_doc: dict, public_key: Ed25519PublicKey,
    attested_subjects: Mapping[str, dict], gh_version: str,
    context: Mapping[str, str],
) -> dict:
    """Promote only BOTH typed evidence paths, after all provenance checks."""
    binding = ExactObligationBinding.from_runner(runner_doc)
    match_host(runner_doc["host"], role="proof_runner", context=context)
    match_host(checker_doc["host"], role="independent_checker", context=context)
    kernel_fact = validate_serialized_kernel_report(runner_doc, kernel_doc, context)

    # Valid signature covers the separately reconstructed source/term result.
    signed_source_receipt = term.admit(runner_doc, checker_doc, signed_doc, public_key)
    source_fact = AttestedSourceRecheck(
        binding=binding,
        signed_statement_digest=signed_doc["document_digest"],
        checker_observation_digest=checker_doc["document_digest"],
        key_subject_sha256=attested_subjects["public_key"]["sha256"],
    )
    if (
        signed_source_receipt.obligation_id != source_fact.binding.obligation_id or
        signed_source_receipt.proof_term_fingerprint != kernel_fact.binding.proof_term_fingerprint or
        signed_source_receipt.environment_fingerprint != kernel_fact.binding.environment_fingerprint or
        source_fact.binding != kernel_fact.binding
    ):
        raise UnifiedReceiptError("source and kernel paths concern different VGI obligations")
    if set(attested_subjects) != set(SUBJECT_NAMES):
        raise UnifiedReceiptError("authenticated evidence types incomplete")
    for label in SUBJECT_NAMES:
        subject = attested_subjects[label]
        if subject.get("kind") != label or subject.get("source_repository_id") != REPO_ID:
            raise UnifiedReceiptError(f"{label}: wrong authenticated evidence type")
    if attested_subjects["runner"]["sha256"] != _sha(term.canonical(runner_doc) + b"\n"):
        raise UnifiedReceiptError("attested original runner observation is not identical")
    if attested_subjects["checker"]["sha256"] != _sha(term.canonical(checker_doc) + b"\n"):
        raise UnifiedReceiptError("attested source checker observation is not identical")
    if attested_subjects["signed"]["sha256"] != _sha(term.canonical(signed_doc) + b"\n"):
        raise UnifiedReceiptError("attested checker signature statement is not identical")
    if attested_subjects["serialized_kernel"]["sha256"] != _sha(term.canonical(kernel_doc) + b"\n"):
        raise UnifiedReceiptError("attested serialized kernel report is not identical")

    obligation = term.validate_observation(runner_doc)
    # The combined receipt reference commits to *both* checked evidence paths
    # and their verified provenance, not either pre-existing observation alone.
    binding_payload = {
        "format": FORMAT,
        "checker_policy": CHECKER_POLICY,
        "obligation_id": binding.obligation_id,
        "proof_term_fingerprint": binding.proof_term_fingerprint,
        "type_fingerprint": binding.type_fingerprint,
        "environment_fingerprint": binding.environment_fingerprint,
        "source_recheck_digest": source_fact.signed_statement_digest,
        "serialized_kernel_digest": kernel_fact.report_digest,
        "runner_observation_digest": binding.runner_observation_digest,
        "attested_subjects": dict(attested_subjects),
        "github_workflow": WORKFLOW,
        "github_source_sha": context["git_sha"],
        "github_run_id": context["run_id"],
        "github_run_attempt": context["run_attempt"],
    }
    receipt_ref = "sha256:" + term.digest(binding_payload)
    receipt = VerifiedKernelReceipt(
        obligation_id=obligation.fingerprint,
        proof_term_fingerprint=binding.proof_term_fingerprint,
        environment_fingerprint=obligation.environment.environment_fingerprint,
        checker_id=CHECKER_POLICY,
        checker_version="4.15.0+unified/0.1",
        result="accepted",
        receipt_ref=receipt_ref,
    )
    ground = ProofGround(obligation.environment, [obligation], [], receipts=[receipt])
    if ground.kernel_status(binding.obligation_id) != "kernel_accepted":
        raise UnifiedReceiptError("VGI did not admit both authenticated evidentiary paths")
    result = {
        **binding_payload,
        "status": "unified_attested_serialized_kernel_receipt_admitted",
        "vgi_kernel_status": ground.kernel_status(binding.obligation_id),
        "verified_kernel_receipt": {
            "obligation_id": receipt.obligation_id,
            "proof_term_fingerprint": receipt.proof_term_fingerprint,
            "environment_fingerprint": receipt.environment_fingerprint,
            "checker_id": receipt.checker_id,
            "checker_version": receipt.checker_version,
            "result": receipt.result,
            "receipt_ref": receipt.receipt_ref,
        },
        "source_checker_observation_digest": source_fact.checker_observation_digest,
        "checker_source_sha256": kernel_fact.checker_source_sha256,
        "github_cli_version": gh_version,
        "trust_boundary": (
            "Attested GitHub workflow provenance authorizes this fixed Lean-4.15 "
            "receipt only; VGI receipt re-import must independently enforce its "
            "own issuer policy. This is same-implementation kernel verification."
        ),
    }
    return {**result, "document_digest": term.digest(result)}


def attest_and_unify(
    *, runner_path: Path, checker_path: Path, signed_path: Path,
    public_key_path: Path, serialized_kernel_path: Path,
    env: Mapping[str, str], command_runner: Callable[..., Any] = subprocess.run,
) -> dict:
    context = require_main_authority_context(env)
    paths = {
        "runner": runner_path, "checker": checker_path, "signed": signed_path,
        "public_key": public_key_path, "serialized_kernel": serialized_kernel_path,
    }
    runner_doc = term._read(runner_path)
    checker_doc = term._read(checker_path)
    signed_doc = term._read(signed_path)
    kernel_doc = term._read(serialized_kernel_path)
    match_host(runner_doc["host"], role="proof_runner", context=context)
    match_host(checker_doc["host"], role="independent_checker", context=context)
    validate_serialized_kernel_report(runner_doc, kernel_doc, context)
    version, subjects = authenticate_subject_bytes(paths, context, runner=command_runner)
    key = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise UnifiedReceiptError("authenticated public key must be Ed25519")
    return unify(
        runner_doc=runner_doc, checker_doc=checker_doc, signed_doc=signed_doc,
        kernel_doc=kernel_doc, public_key=key,
        attested_subjects=subjects, gh_version=version, context=context,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runner", "checker", "signed", "public-key", "serialized-kernel", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        report = attest_and_unify(
            runner_path=args.runner, checker_path=args.checker,
            signed_path=args.signed, public_key_path=args.public_key,
            serialized_kernel_path=args.serialized_kernel, env=os.environ,
        )
        term._write(args.output, report)
        print("VGI accepted one unified term-bound authenticated serialized-kernel receipt")
    except (OSError, subprocess.SubprocessError, term.TermReceiptError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"unified VGI kernel receipt rejected: {exc}\n")


if __name__ == "__main__":
    main()
