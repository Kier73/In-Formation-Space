#!/usr/bin/env python3
"""Independently verify and admit a transferred unified Lean/VGI proof receipt.

Trust roots: a *recipient-owned* exact intent/issuer policy, GitHub's
Sigstore attestation verifier, pinned trusted workflow & repository identity,
and this receiver's installed checker/VGI code. The sender's process, JSON
claims, and self-supplied key are never independently sufficient.

Only a durable SQLite uniqueness transaction turns verified evidence into a
one-time admission. Separate GitHub jobs demonstrate host/process transfer;
they do not prove distinct physical, administrative, or implementation
fault domains or an E-CPU transport link.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import attested_admission as provenance
import term_receipt as term
import unified_kernel_receipt as unified

FORMAT = "in-formation.proof-transfer-receiver-decision/0.1"
POLICY_FORMAT = "in-formation.proof-transfer-receiver-intent/0.1"
PROFILE = "github-main-unified-lean-4.15-verified-transfer/0.1"
SUBJECTS = (*unified.SUBJECT_NAMES, "unified_receipt")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}")


class ReceiverReject(unified.UnifiedReceiptError):
    """The recipient has not admitted this untrusted delivery."""


class ReplayRejected(ReceiverReject):
    """The exact receipt or logical proof admission was already recorded."""


@dataclass(frozen=True, slots=True)
class ReceiverIntent:
    """Recipient-owned policy, NOT a claim copied from the incoming receipt."""
    recipient_scope: str
    expected_obligation_id: str
    expected_source_sha: str
    expected_run_id: str
    expected_run_attempt: str
    not_before_unix: int
    not_after_unix: int
    revoked_receipt_refs: frozenset[str]
    revoked_source_shas: frozenset[str]
    policy_digest: str

    @classmethod
    def load(cls, path: Path) -> "ReceiverIntent":
        if path.is_symlink() or not path.is_file():
            raise ReceiverReject("trusted receiver intent must be a local regular file")
        doc = term._read(path)
        term._fields(doc, {
            "format", "recipient_scope", "expected_obligation_id",
            "expected_source_sha", "expected_run_id", "expected_run_attempt",
            "not_before_unix", "not_after_unix",
            "revoked_receipt_refs", "revoked_source_shas",
        }, "recipient-owned intent")
        if doc["format"] != POLICY_FORMAT:
            raise ReceiverReject("unsupported recipient policy profile")
        for name, pattern in (
            ("recipient_scope", IDENT),
            ("expected_obligation_id", HEX64),
            ("expected_source_sha", HEX40),
            ("expected_run_id", re.compile(r"[1-9][0-9]*")),
            ("expected_run_attempt", re.compile(r"[1-9][0-9]*")),
        ):
            value = doc[name]
            if not isinstance(value, str) or pattern.fullmatch(value) is None:
                raise ReceiverReject(f"invalid recipient-owned {name}")
        for name in ("not_before_unix", "not_after_unix"):
            if type(doc[name]) is not int or doc[name] < 0:
                raise ReceiverReject(f"{name} must be a nonnegative Unix timestamp")
        if doc["not_before_unix"] >= doc["not_after_unix"]:
            raise ReceiverReject("recipient approval interval is empty")
        sets = {}
        for field, pattern in (
            ("revoked_receipt_refs", re.compile(r"sha256:[a-f0-9]{64}")),
            ("revoked_source_shas", HEX40),
        ):
            value = doc[field]
            if not isinstance(value, list) or len(value) != len(set(map(str, value))):
                raise ReceiverReject(f"malformed or duplicate {field}")
            if any(not isinstance(x, str) or pattern.fullmatch(x) is None for x in value):
                raise ReceiverReject(f"invalid {field}")
            sets[field] = frozenset(value)
        return cls(
            recipient_scope=doc["recipient_scope"],
            expected_obligation_id=doc["expected_obligation_id"],
            expected_source_sha=doc["expected_source_sha"],
            expected_run_id=doc["expected_run_id"],
            expected_run_attempt=doc["expected_run_attempt"],
            not_before_unix=doc["not_before_unix"],
            not_after_unix=doc["not_after_unix"],
            revoked_receipt_refs=sets["revoked_receipt_refs"],
            revoked_source_shas=sets["revoked_source_shas"],
            policy_digest=term.digest(doc),
        )

    def assert_active(self, now: int) -> None:
        if type(now) is not int or not self.not_before_unix <= now < self.not_after_unix:
            raise ReceiverReject("recipient approval window is not active")
        if self.expected_source_sha in self.revoked_source_shas:
            raise ReceiverReject("source commit explicitly revoked in recipient policy")

    def issuer_run(self) -> dict[str, str]:
        return {
            "git_sha": self.expected_source_sha,
            "run_id": self.expected_run_id,
            "run_attempt": self.expected_run_attempt,
        }


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_subjects(paths: Mapping[str, Path]) -> tuple[dict, dict[str, bytes]]:
    """Require exact canonical transfers; validate *bytes*, not only JSON values."""
    if set(paths) != set(SUBJECTS):
        raise ReceiverReject("receiver requires all six distinct typed subjects")
    if len({str(path.resolve()) for path in paths.values()}) != len(SUBJECTS):
        raise ReceiverReject("distinct evidence kinds may not share a single file")
    documents = {}
    raw_files = {}
    for kind in SUBJECTS:
        path = paths[kind]
        if path.is_symlink() or not path.is_file():
            raise ReceiverReject(f"{kind}: missing or symlinked transfer artifact")
        raw = path.read_bytes()
        if len(raw) > 2_000_000:
            raise ReceiverReject(f"{kind}: unexpected oversized transfer artifact")
        raw_files[kind] = raw
        if kind == "public_key":
            continue
        doc = term._read(path)
        if raw != term.canonical(doc) + b"\n":
            raise ReceiverReject(f"{kind}: transferred JSON is not exact canonical bytes")
        documents[kind] = doc
    return documents, raw_files


def _verify_attestations(
    paths: Mapping[str, Path], raw_files: Mapping[str, bytes],
    intent: ReceiverIntent, *, command_runner: Callable[..., Any] = subprocess.run,
) -> tuple[str, dict]:
    version = provenance.require_gh_version(
        provenance._execute(["gh", "--version"], runner=command_runner)
    )
    verified = {}
    for kind in SUBJECTS:
        sha = _sha(raw_files[kind])
        argv = [
            "gh", "attestation", "verify", str(paths[kind]),
            "--repo", unified.REPO,
            "--cert-identity", unified.CERT_IDENTITY,
            "--source-ref", unified.MAIN_REF,
            "--source-digest", intent.expected_source_sha,
            "--predicate-type", provenance.PREDICATE,
            "--deny-self-hosted-runners",
            "--format", "json",
        ]
        output = provenance._execute(argv, runner=command_runner)
        validated = provenance.parse_verified_attestation(output, subject_digest=sha)
        if validated["source_repository_id"] != unified.REPO_ID:
            raise ReceiverReject(f"{kind}: untrusted GitHub repository identity")
        verified[kind] = {
            "kind": kind, "sha256": sha,
            "verification_result_sha256": _sha(output.encode("utf-8")),
            "source_repository_id": unified.REPO_ID,
        }
    return version, verified


def _validate_report_and_reconstruct(
    documents: Mapping[str, dict], raw_files: Mapping[str, bytes],
    intent: ReceiverIntent, verified: Mapping[str, dict],
) -> tuple[str, dict]:
    final = documents["unified_receipt"]
    term._bind_digest(final, "unified transferred receipt")
    for name in ("status", "format", "github_workflow",
                 "github_source_sha", "github_run_id", "github_run_attempt"):
        if name not in final:
            raise ReceiverReject(f"missing unified receipt field: {name}")
    if (final["format"] != unified.FORMAT
        or final["status"] != "unified_attested_serialized_kernel_receipt_admitted"
        or final["github_workflow"] != unified.WORKFLOW
        or final["github_source_sha"] != intent.expected_source_sha
        or final["github_run_id"] != intent.expected_run_id
        or final["github_run_attempt"] != intent.expected_run_attempt):
        raise ReceiverReject("unified receipt was not issued under intended source run")
    if final.get("obligation_id") != intent.expected_obligation_id:
        raise ReceiverReject("unified receipt is for the wrong recipient obligation")

    receipt = final.get("verified_kernel_receipt")
    if not isinstance(receipt, dict):
        raise ReceiverReject("unified receipt lacks typed kernel receipt")
    ref = receipt.get("receipt_ref")
    if not isinstance(ref, str) or re.fullmatch(r"sha256:[a-f0-9]{64}", ref) is None:
        raise ReceiverReject("invalid or unsupported VGI receipt reference")
    if ref in intent.revoked_receipt_refs:
        raise ReceiverReject("VGI receipt was revoked by recipient policy")
    if receipt.get("checker_id") != unified.CHECKER_POLICY:
        raise ReceiverReject("unrecognized typed VGI checker authority")

    issuer_claims = final.get("attested_subjects")
    if not isinstance(issuer_claims, dict) or set(issuer_claims) != set(unified.SUBJECT_NAMES):
        raise ReceiverReject("missing typed upstream attestations")
    for kind in unified.SUBJECT_NAMES:
        claim = issuer_claims[kind]
        if not isinstance(claim, dict) or set(claim) != {
            "kind", "sha256", "source_repository_id", "verification_result_sha256"
        }:
            raise ReceiverReject(f"{kind}: malformed claimed source attestation")
        if claim["kind"] != kind or claim["sha256"] != verified[kind]["sha256"]:
            raise ReceiverReject(f"{kind}: substituted source subject")
        if claim["source_repository_id"] != unified.REPO_ID:
            raise ReceiverReject(f"{kind}: wrong claimed attestation authority")
        digest = claim["verification_result_sha256"]
        if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
            raise ReceiverReject(f"{kind}: invalid issuer verification digest")

    key = serialization.load_pem_public_key(raw_files["public_key"])
    if not isinstance(key, Ed25519PublicKey):
        raise ReceiverReject("transferred key is not Ed25519")
    # Reconstruct the trusted issuance from *all five upstream observations*,
    # never from receipt.status or receipt_ref alone. The verifier-output hashes
    # captured by the issuer may legitimately differ from a later gh invocation;
    # we verify their provenance-bearing *subject digests* independently.
    reconstructed = unified.unify(
        runner_doc=documents["runner"], checker_doc=documents["checker"],
        signed_doc=documents["signed"], kernel_doc=documents["serialized_kernel"],
        public_key=key, attested_subjects=issuer_claims,
        gh_version=final.get("github_cli_version"),
        context=intent.issuer_run(),
    )
    recorded_gh_version = final.get("github_cli_version")
    if not isinstance(recorded_gh_version, str):
        raise ReceiverReject("issuer verifier version is missing")
    provenance.require_gh_version(f"gh version {recorded_gh_version}")
    if reconstructed != final:
        raise ReceiverReject("received VGI receipt cannot be independently reconstructed")

    source_runner = documents["runner"]["host"]
    source_checker = documents["checker"]["host"]
    for role, host in (("proof_runner", source_runner), ("independent_checker", source_checker)):
        unified.match_host(host, role=role, context=intent.issuer_run())
    if final["obligation_id"] != intent.expected_obligation_id:
        raise ReceiverReject("obligation not authorized by recipient")
    if verified["unified_receipt"]["sha256"] != _sha(raw_files["unified_receipt"]):
        raise ReceiverReject("final verified subject bytes changed")
    return ref, reconstructed


def _accept_once(ledger: Path, intent: ReceiverIntent, receipt_ref: str,
                 final_digest: str, now: int) -> None:
    """SQLite single-winner transaction survives independent process restarts."""
    if str(ledger) == ":memory:" or ledger.is_symlink():
        raise ReceiverReject("replay ledger must be a durable nonsymlink SQLite file")
    if not ledger.parent.is_dir():
        raise ReceiverReject("durable ledger parent directory does not exist")
    conn = sqlite3.connect(str(ledger), timeout=15, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accepted_proof_transfers (
                recipient_scope TEXT NOT NULL,
                receipt_ref TEXT NOT NULL,
                obligation_id TEXT NOT NULL,
                source_sha TEXT NOT NULL,
                run_id TEXT NOT NULL,
                run_attempt TEXT NOT NULL,
                issuer_receipt_sha256 TEXT NOT NULL,
                recipient_policy_sha256 TEXT NOT NULL,
                accepted_unix INTEGER NOT NULL,
                PRIMARY KEY (recipient_scope, receipt_ref),
                UNIQUE (recipient_scope, obligation_id, source_sha, run_id, run_attempt)
            )
        """)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("""
                INSERT INTO accepted_proof_transfers (
                    recipient_scope, receipt_ref, obligation_id, source_sha,
                    run_id, run_attempt, issuer_receipt_sha256,
                    recipient_policy_sha256, accepted_unix
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                intent.recipient_scope, receipt_ref,
                intent.expected_obligation_id, intent.expected_source_sha,
                intent.expected_run_id, intent.expected_run_attempt,
                final_digest, intent.policy_digest, now,
            ))
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise ReplayRejected("replayed receipt or already accepted logical obligation/run") from exc
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def receive(
    *, paths: Mapping[str, Path], intent_path: Path, ledger_path: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    now_unix: int | None = None,
) -> dict:
    """Authenticate all six transfers, reconstruct VGI decision, then commit."""
    intent = ReceiverIntent.load(intent_path)
    now = int(time.time()) if now_unix is None else now_unix
    intent.assert_active(now)
    documents, raw_files = _load_subjects(paths)
    # Validation against caller-owned intent is performed BEFORE retrieving
    # attestations, so any cross-run substitution fails early and cheaply.
    final = documents["unified_receipt"]
    if (final.get("github_source_sha") != intent.expected_source_sha
        or final.get("github_run_id") != intent.expected_run_id
        or final.get("github_run_attempt") != intent.expected_run_attempt
        or final.get("obligation_id") != intent.expected_obligation_id):
        raise ReceiverReject("transferred receipt conflicts with recipient-owned intent")
    gh_version, verified = _verify_attestations(
        paths, raw_files, intent, command_runner=command_runner
    )
    ref, _reconstruction = _validate_report_and_reconstruct(documents, raw_files, intent, verified)
    final_digest = documents["unified_receipt"]["document_digest"]
    _accept_once(ledger_path, intent, ref, final_digest, now)
    output = {
        "format": FORMAT,
        "status": "accepted_once_after_independent_verification",
        "recipient_scope": intent.recipient_scope,
        "recipient_policy_digest": intent.policy_digest,
        "obligation_id": intent.expected_obligation_id,
        "proof_term_fingerprint": final["proof_term_fingerprint"],
        "environment_fingerprint": final["environment_fingerprint"],
        "source_sha": intent.expected_source_sha,
        "source_run_id": intent.expected_run_id,
        "source_run_attempt": intent.expected_run_attempt,
        "receipt_ref": ref,
        "issuer_receipt_document_digest": final_digest,
        "receiver_gh_cli_version": gh_version,
        "subject_sha256": {name: verified[name]["sha256"] for name in SUBJECTS},
        "anti_replay": "sqlite-unique-recipient-scope-and-obligation-run",
        "accepted_unix": now,
        "limitations": [
            "The sender's artifact channel is not E-CPU ReliableChannel",
            "Durable replay detection is local to this SQLite ledger, not global",
            "Recipient intent and revocation policy are locally provisioned; no global registry",
            "GitHub workflow identity and trusted main review are assumptions",
            "Same Lean kernel implementation; no separate physical fault-domain proof",
        ],
    }
    return {**output, "document_digest": term.digest(output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*SUBJECTS, "intent", "ledger", "output"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    paths = {name: getattr(args, name) for name in SUBJECTS}
    try:
        output = receive(paths=paths, intent_path=args.intent, ledger_path=args.ledger)
        term._write(args.output, output)
        print("RECIPIENT_ACCEPTED: independently reconstructed VGI proof transfer")
    except (ReceiverReject, OSError, sqlite3.Error, TypeError, ValueError, KeyError) as exc:
        parser.exit(1, f"RECIPIENT_REJECTED: {exc}\n")


if __name__ == "__main__":
    main()
