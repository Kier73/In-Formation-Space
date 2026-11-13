#!/usr/bin/env python3
"""Independent fixed-theorem Lean *kernel* check of a reconstructed serialized Expr.

Unlike source re-elaboration, this checker takes only the previously observed
serialized term/type and reconstructs both in a Lean file that does not import
the source theorem. It then calls Lean's Kernel.check and Kernel.isDefEq.
This is still the same pinned Lean implementation and a fixed-fixture profile.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import os
from pathlib import Path
import subprocess
from typing import Any

import kernel_evidence
import term_receipt as t

ROOT = Path(__file__).resolve().parent
SERIALIZED = ROOT / "term-identity.json"
CHECKER = ROOT / "SerializedKernelCheck.lean"
FORMAT = "in-formation.lean-serialized-kernel-recheck/0.1"
ACCEPTED_BANNER = "SERIALIZED_TERM_KERNEL_ACCEPTED:KernelTrial.identity"
SAMPLES = ("accepted", "unbound_variable", "wrong_theorem_type", "unknown_constructor")


class SerializedKernelError(ValueError):
    """A claimed kernel check was not independently reproduced."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def checker_source_sha() -> str:
    source = CHECKER.read_bytes()
    if not source.startswith(b"import Lean\n"):
        raise SerializedKernelError("serialized checker must import exactly Lean first")
    if b"\nimport KernelTrial" in source or b"\nimport Lean.KernelTrial" in source:
        raise SerializedKernelError("checker may not import the source theorem module")
    return _sha(source)


def _observe(export: dict, case: str, *, run=subprocess.run) -> dict:
    t._write(SERIALIZED, export)
    completed = run(["lake", "env", "lean", CHECKER.name], cwd=ROOT,
                    capture_output=True, text=True, check=False, timeout=180)
    combined = completed.stdout + "\n" + completed.stderr
    accepted = (completed.returncode == 0 and
                combined.count(ACCEPTED_BANNER) == 1 and
                "error:" not in combined.lower() and "warning:" not in combined.lower())
    return {
        "case": case,
        "input_sha256": _sha(SERIALIZED.read_bytes()),
        "process_exit_code": completed.returncode,
        "stdout_sha256": _sha(completed.stdout.encode("utf-8")),
        "stderr_sha256": _sha(completed.stderr.encode("utf-8")),
        "kernel_accepted_observed": accepted,
    }


def _mutant(export: dict, case: str) -> dict:
    doc = copy.deepcopy(export)
    if case == "accepted":
        return doc
    if case == "unbound_variable":
        doc["proof"] = {"kind": "bvar", "index": 0}
    elif case == "wrong_theorem_type":
        doc["type"] = {"kind": "const", "name": {"kind": "str", "prefix": {"kind": "anonymous"}, "value": "Nat"}, "levels": []}
    elif case == "unknown_constructor":
        doc["proof"] = {"kind": "mvar", "id": "forged"}
    else:
        raise SerializedKernelError(f"unknown adversarial case: {case}")
    return doc


def verify(runner_document: dict, *, run=subprocess.run,
           github_context: dict[str, str] | None = None) -> dict:
    obligation = t.validate_observation(runner_document)
    env = dict(os.environ if github_context is None else github_context)
    host = runner_document["host"]
    if env.get("GITHUB_ACTIONS") == "true":
        required = {
            "GITHUB_REPOSITORY": "Kier73/In-Formation-Space",
            "GITHUB_JOB": "serialized_kernel_checker",
            "GITHUB_SHA": host["git_sha"],
            "GITHUB_RUN_ID": host["run_id"],
            "GITHUB_RUN_ATTEMPT": host["run_attempt"],
        }
        for name, value in required.items():
            if env.get(name) != value:
                raise SerializedKernelError(f"kernel checker host/source correlation failed: {name}")
        if host.get("role") != "proof_runner" or host.get("job") != "proof_runner":
            raise SerializedKernelError("not derived from the fixed proof runner job")
    src_sha = checker_source_sha()
    observations = []
    try:
        for case in SAMPLES:
            observation = _observe(_mutant(runner_document["export"], case), case, run=run)
            observations.append(observation)
            if observation["kernel_accepted_observed"] != (case == "accepted"):
                raise SerializedKernelError(f"kernel check did not reject/accept as expected: {case}")
    finally:
        SERIALIZED.unlink(missing_ok=True)

    report = {
        "format": FORMAT,
        "status": "serialized_term_kernel_rechecked",
        "theorem": t.THEOREM,
        "toolchain": t.TOOLCHAIN,
        "serialized_expression_profile": t.TERM_FORMAT,
        "checker_source_sha256": src_sha,
        "original_runner_observation_digest": runner_document["document_digest"],
        "proof_term_fingerprint": runner_document["proof_term_fingerprint"],
        "type_fingerprint": runner_document["type_fingerprint"],
        "obligation_id": obligation.fingerprint,
        "environment_fingerprint": obligation.environment.environment_fingerprint,
        "checker_host": {
            "repository": env.get("GITHUB_REPOSITORY", "offline"),
            "git_sha": env.get("GITHUB_SHA", "offline"),
            "run_id": env.get("GITHUB_RUN_ID", "offline"),
            "run_attempt": env.get("GITHUB_RUN_ATTEMPT", "0"),
            "job": env.get("GITHUB_JOB", "offline"),
        },
        "cases": observations,
        "vgi_verified_kernel_receipt_issued": False,
        "not_established": [
            "implementation-diverse kernel check",
            "independent physical/administrative fault domains",
            "arbitrary VGI obligation translation and complete environment closure",
            "authenticated serialized-kernel-checker authority or VGI receipt admission",
        ],
    }
    return {**report, "document_digest": t.digest(report)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(t._read(args.runner))
        t._write(args.output, report)
        print("independent serialized-term kernel recheck passed")
    except (OSError, subprocess.SubprocessError, SerializedKernelError,
            t.TermReceiptError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"serialized kernel recheck rejected: {exc}\n")


if __name__ == "__main__":
    main()
