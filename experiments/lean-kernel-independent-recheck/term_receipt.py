#!/usr/bin/env python3
"""Proof-term identity / signed VGI receipt admission, bounded to KernelTrial.identity.

The signature validates only against a caller-supplied, separately trusted Ed25519
public key. Neither a GitHub artifact nor a self-provided key is an authority.
A structural fingerprint is not a proof of theorem equivalence or a kernel check.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from vgi.proof import ProofEnvironment, ProofObligation, ProofGround, VerifiedKernelReceipt
import kernel_evidence

ROOT = Path(__file__).resolve().parent
TERM_FORMAT = "in-formation.lean-expr-structural/0.1"
OBS_FORMAT = "in-formation.lean-term-observation/0.1"
RECHECK_FORMAT = "in-formation.lean-term-independent-recheck/0.1"
RECEIPT_FORMAT = "in-formation.lean-term-signed-receipt/0.1"
THEOREM = "KernelTrial.identity"
TOOLCHAIN = "leanprover/lean4:v4.15.0"
ENV_FILES = ("lean-toolchain", "lakefile.toml", "lake-manifest.json", "KernelTrial.lean")
CANON_PROFILE = "python-json-sorted-utf8/0.1"


class TermReceiptError(ValueError):
    """A claimed identity, checker authorization, or evidence binding failed."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _read(path: Path) -> dict:
    def no_duplicate_keys(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise TermReceiptError("duplicate JSON key")
            result[key] = val
        return result
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)
    if not isinstance(value, dict):
        raise TermReceiptError("expected JSON object")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def _fields(document: dict, names: set, name: str) -> None:
    if not isinstance(document, dict) or set(document) != names:
        raise TermReceiptError(f"{name}: unexpected, missing or extra fields")


def _bind_digest(document: dict, name: str) -> None:
    if document.get("document_digest") != digest({k: v for k, v in document.items() if k != "document_digest"}):
        raise TermReceiptError(f"{name}: document digest mismatch")


def make_environment() -> ProofEnvironment:
    entries = {}
    for name in ENV_FILES:
        raw = (ROOT / name).read_bytes()
        entries[name] = hashlib.sha256(raw).hexdigest()
    if (ROOT / "lean-toolchain").read_text().strip() != TOOLCHAIN:
        raise TermReceiptError("unpinned Lean toolchain")
    imports = digest({"toolchain": TOOLCHAIN, "files": entries})
    # This is a fixed-fixture *source/import commitment*, not a complete
    # transitive semantic fingerprint of all dependencies in a Lean environment.
    return ProofEnvironment(
        assistant="Lean", assistant_version="4.15.0",
        environment_fingerprint=digest({"fixture": THEOREM, "imports_fingerprint": imports,
                                         "options_fingerprint": digest({"fixture_options": "default"})}),
        imports_fingerprint=imports,
        options_fingerprint=digest({"fixture_options": "default"}),
    )


def obligation_for(environment: ProofEnvironment, theorem_type: dict) -> ProofObligation:
    return ProofObligation(environment, {"kind": "lean-4.15-structural-type", "expression": theorem_type})


def make_observation(export: dict, *, case_digest: str, host: dict, environment: ProofEnvironment) -> dict:
    _fields(export, {"format", "theorem", "type", "proof"}, "Lean structural export")
    if export["format"] != TERM_FORMAT or export["theorem"] != THEOREM:
        raise TermReceiptError("wrong theorem or unsupported structural export")
    if not isinstance(export["type"], dict) or not isinstance(export["proof"], dict):
        raise TermReceiptError("structural expression fields must be JSON objects")
    obligation = obligation_for(environment, export["type"])
    report = {
        "format": OBS_FORMAT,
        "theorem": THEOREM,
        "toolchain": TOOLCHAIN,
        "canonicalization": CANON_PROFILE,
        "host": host,
        "export": export,
        "type_fingerprint": digest({"format": TERM_FORMAT, "type": export["type"]}),
        "proof_term_fingerprint": digest({"format": TERM_FORMAT, "proof": export["proof"]}),
        "environment": environment.to_dict(),
        "obligation_id": obligation.fingerprint,
        "kernel_case_observation_digest": case_digest,
    }
    return {**report, "document_digest": digest(report)}


def validate_observation(report: dict) -> ProofObligation:
    _fields(report, {"format", "theorem", "toolchain", "canonicalization", "host", "export",
                     "type_fingerprint", "proof_term_fingerprint", "environment",
                     "obligation_id", "kernel_case_observation_digest", "document_digest"}, "observation")
    _bind_digest(report, "observation")
    if report["format"] != OBS_FORMAT or report["theorem"] != THEOREM or report["toolchain"] != TOOLCHAIN:
        raise TermReceiptError("unsupported toolchain/theorem observation")
    if report["canonicalization"] != CANON_PROFILE:
        raise TermReceiptError("unsupported canonicalization profile")
    exp = report["export"]
    _fields(exp, {"format", "theorem", "type", "proof"}, "structural export")
    if exp["format"] != TERM_FORMAT or exp["theorem"] != THEOREM:
        raise TermReceiptError("unsupported export format/theorem")
    if report["type_fingerprint"] != digest({"format": TERM_FORMAT, "type": exp["type"]}):
        raise TermReceiptError("theorem type fingerprint mismatch")
    if report["proof_term_fingerprint"] != digest({"format": TERM_FORMAT, "proof": exp["proof"]}):
        raise TermReceiptError("proof-term fingerprint mismatch")
    env = ProofEnvironment(**report["environment"])
    obligation = obligation_for(env, exp["type"])
    if report["obligation_id"] != obligation.fingerprint:
        raise TermReceiptError("VGI obligation fingerprint mismatch")
    if not isinstance(report["kernel_case_observation_digest"], str) or len(report["kernel_case_observation_digest"]) != 64:
        raise TermReceiptError("missing Lean process evidence")
    return obligation


def _run(*args: str) -> None:
    process = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=300)
    if process.returncode != 0:
        raise TermReceiptError(f"{args[0]} failed: {process.stderr[-2000:]} {process.stdout[-1000:]}")


def observe() -> dict:
    _run("lake", "build")
    _run("lake", "env", "lean", "TermIdentity.lean")
    export = _read(ROOT / "term-identity.json")
    with tempfile.TemporaryDirectory() as folder:
        evidence_path = Path(folder) / "kernel-observation.json"
        kernel_evidence.produce(evidence_path)
        checked = _read(evidence_path)
    kernel_evidence._check_cases(checked["cases"])
    positive = checked["cases"][0]
    if positive["status"] != "checked_without_axioms" or any(
        item["status"] != "not_established" for item in checked["cases"][1:]
    ):
        raise TermReceiptError("Lean controls or no-axioms observation failed")
    host = kernel_evidence._host("proof_runner")
    return make_observation(export, case_digest=positive["document_digest"],
                            host=host, environment=make_environment())


def recheck(runner: dict, fresh: dict, private_key: Ed25519PrivateKey) -> dict:
    validate_observation(runner)
    validate_observation(fresh)
    for name in ("theorem", "toolchain", "canonicalization", "export", "type_fingerprint",
                 "proof_term_fingerprint", "environment", "obligation_id"):
        if runner[name] != fresh[name]:
            raise TermReceiptError(f"independent Lean extraction disagrees on {name}")
    if runner["host"].get("role") != "proof_runner":
        raise TermReceiptError("runner role is invalid")
    if fresh["host"].get("role") != "independent_checker":
        raise TermReceiptError("independent checker role is invalid")
    for key in ("repository", "git_sha", "run_id", "run_attempt"):
        if runner["host"].get(key) != fresh["host"].get(key):
            raise TermReceiptError(f"runner/checker mismatch: {key}")
    if runner["host"].get("job") == fresh["host"].get("job"):
        raise TermReceiptError("runner and checker must have distinct job roles")
    # The checker must be authorized by an external trust policy that pins its
    # public key; a successful verification with an untrusted key is insufficient.
    payload = {
        "format": RECHECK_FORMAT,
        "checker_id": "lean-4.15-term-checker-fixture",
        "checker_version": "0.1",
        "result": "accepted",
        "theorem": THEOREM,
        "runner_observation_digest": runner["document_digest"],
        "checker_observation_digest": fresh["document_digest"],
        "type_fingerprint": fresh["type_fingerprint"],
        "proof_term_fingerprint": fresh["proof_term_fingerprint"],
        "obligation_id": fresh["obligation_id"],
        "environment_fingerprint": fresh["environment"]["environment_fingerprint"],
    }
    signature = private_key.sign(canonical(payload))
    envelope = {"format": RECEIPT_FORMAT, "payload": payload,
                "signature_algorithm": "Ed25519",
                "signature_base64": base64.b64encode(signature).decode("ascii")}
    return {**envelope, "document_digest": digest(envelope)}


def admit(runner: dict, signed: dict, trusted_key: Ed25519PublicKey, *,
          expected_checker_id: str = "lean-4.15-term-checker-fixture") -> VerifiedKernelReceipt:
    obligation = validate_observation(runner)
    _fields(signed, {"format", "payload", "signature_algorithm",
                     "signature_base64", "document_digest"}, "signed receipt")
    _bind_digest(signed, "signed receipt")
    if signed["format"] != RECEIPT_FORMAT or signed["signature_algorithm"] != "Ed25519":
        raise TermReceiptError("unsupported signature envelope")
    payload = signed["payload"]
    _fields(payload, {"format", "checker_id", "checker_version", "result", "theorem",
                      "runner_observation_digest", "checker_observation_digest",
                      "type_fingerprint", "proof_term_fingerprint", "obligation_id",
                      "environment_fingerprint"}, "receipt payload")
    if payload["format"] != RECHECK_FORMAT or payload["checker_id"] != expected_checker_id or payload["checker_version"] != "0.1":
        raise TermReceiptError("untrusted checker identity/version")
    if payload["result"] != "accepted" or payload["theorem"] != THEOREM:
        raise TermReceiptError("receipt does not accept required theorem")
    for name in ("type_fingerprint", "proof_term_fingerprint", "obligation_id"):
        if payload[name] != runner[name]:
            raise TermReceiptError(f"signed receipt is not bound to {name}")
    if payload["environment_fingerprint"] != runner["environment"]["environment_fingerprint"]:
        raise TermReceiptError("signed checker environment mismatch")
    if payload["runner_observation_digest"] != runner["document_digest"]:
        raise TermReceiptError("runner observation substitution")
    if not isinstance(payload["checker_observation_digest"], str) or len(payload["checker_observation_digest"]) != 64:
        raise TermReceiptError("missing checker evidence digest")
    try:
        raw_signature = base64.b64decode(signed["signature_base64"], validate=True)
        trusted_key.verify(raw_signature, canonical(payload))
    except (ValueError, InvalidSignature) as exc:
        raise TermReceiptError("untrusted or tampered checker signature") from exc
    receipt = VerifiedKernelReceipt(
        obligation_id=obligation.fingerprint,
        proof_term_fingerprint=payload["proof_term_fingerprint"],
        environment_fingerprint=obligation.environment.environment_fingerprint,
        checker_id=payload["checker_id"], checker_version=payload["checker_version"],
        result="accepted", receipt_ref="sha256:" + signed["document_digest"],
    )
    ground = ProofGround(obligation.environment, [obligation], [], receipts=[receipt])
    if ground.kernel_status(obligation.fingerprint) != "kernel_accepted":
        raise TermReceiptError("VGI did not admit the authenticated obligation")
    return receipt


def generate_keys(private_path: Path, public_path: Path) -> None:
    if private_path.exists() or public_path.exists():
        raise TermReceiptError("key destination already exists")
    key = Ed25519PrivateKey.generate()
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(private_path, 0o600)
    public_path.write_bytes(key.public_key().public_bytes(
                            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("produce")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("keys")
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--public", type=Path, required=True)
    p = sub.add_parser("recheck")
    p.add_argument("--runner", type=Path, required=True)
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("admit")
    p.add_argument("--runner", type=Path, required=True)
    p.add_argument("--signed", type=Path, required=True)
    p.add_argument("--trusted-public", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "keys":
            generate_keys(args.private, args.public)
        elif args.command == "produce":
            _write(args.output, observe())
        elif args.command == "recheck":
            runner = _read(args.runner)
            fresh = observe()
            fresh["host"]["role"] = "independent_checker"
            fresh["host"]["job"] = "independent_checker"
            fresh["document_digest"] = digest({k: v for k, v in fresh.items() if k != "document_digest"})
            # Do not misrepresent the original process evidence: only the
            # workflow's actual independent checker job may issue a receipt.
            if os.environ.get("GITHUB_JOB") != "independent_checker" or os.environ.get("GITHUB_ACTIONS") != "true":
                raise TermReceiptError("recheck issuance requires independent_checker hosted job")
            private = serialization.load_pem_private_key(args.private.read_bytes(), password=None)
            if not isinstance(private, Ed25519PrivateKey):
                raise TermReceiptError("unsupported private-key algorithm")
            _write(args.output, recheck(runner, fresh, private))
        elif args.command == "admit":
            public = serialization.load_pem_public_key(args.trusted_public.read_bytes())
            if not isinstance(public, Ed25519PublicKey):
                raise TermReceiptError("unsupported public-key algorithm")
            receipt = admit(_read(args.runner), _read(args.signed), public)
            _write(args.output, {
                "format": "in-formation.vgi-admission-observation/0.1",
                "obligation_id": receipt.obligation_id,
                "proof_term_fingerprint": receipt.proof_term_fingerprint,
                "environment_fingerprint": receipt.environment_fingerprint,
                "checker_id": receipt.checker_id, "checker_version": receipt.checker_version,
                "kernel_status": "kernel_accepted",
                "receipt_ref": receipt.receipt_ref,
                "trust_note": "Signature verified against caller-supplied public key; key authority itself is not established by this program.",
            })
    except (TermReceiptError, OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Lean term receipt rejected: {exc}\n")


if __name__ == "__main__":
    main()
