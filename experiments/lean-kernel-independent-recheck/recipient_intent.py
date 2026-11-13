#!/usr/bin/env python3
"""Locally construct receiver's *independent* fixed-theorem intent.

This is run by the *recipient*, from its own pinned Lean source checkout.
It never reads the transmitted runner observation, proof report or receipt.
For a different recipient, provision the equivalent intent out-of-band.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import time

import term_receipt as term
import proof_receipt_receiver as receiver

ROOT = Path(__file__).resolve().parent


def create(
    *, source_sha: str, run_id: str, run_attempt: str, scope: str,
    ttl_seconds: int = 1200, now_unix: int | None = None,
    run=subprocess.run,
) -> dict:
    if re.fullmatch(r"[a-f0-9]{40}", source_sha) is None:
        raise receiver.ReceiverReject("recipient source SHA is not pinned")
    for name, value in (("run_id", run_id), ("run_attempt", run_attempt)):
        if re.fullmatch(r"[1-9][0-9]*", value) is None:
            raise receiver.ReceiverReject(f"recipient {name} is invalid")
    if re.fullmatch(receiver.IDENT, scope) is None:
        raise receiver.ReceiverReject("recipient scope is invalid")
    if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 3600:
        raise receiver.ReceiverReject("recipient intent TTL must be 60..3600 seconds")

    # Reconstruct the intended theorem's type on this receiver independently.
    # No byte from any transferred sender artifact is consulted.
    result = run(["lake", "env", "lean", "TermIdentity.lean"], cwd=ROOT,
                 capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        raise receiver.ReceiverReject(
            f"recipient failed to independently establish intended Lean type: {result.stderr[-900:]}"
        )
    export_path = ROOT / "term-identity.json"
    try:
        export = term._read(export_path)
        term._fields(export, {"format", "theorem", "type", "proof"}, "local recipient export")
        if export["format"] != term.TERM_FORMAT or export["theorem"] != term.THEOREM:
            raise receiver.ReceiverReject("local Lean theorem profile mismatch")
        expected_obligation = term.obligation_for(
            term.make_environment(), export["type"]
        ).fingerprint
    finally:
        export_path.unlink(missing_ok=True)

    now = int(time.time()) if now_unix is None else now_unix
    if type(now) is not int or now <= 0:
        raise receiver.ReceiverReject("local receiver clock not available")
    return {
        "format": receiver.POLICY_FORMAT,
        "recipient_scope": scope,
        "expected_obligation_id": expected_obligation,
        "expected_source_sha": source_sha,
        "expected_run_id": run_id,
        "expected_run_attempt": run_attempt,
        "not_before_unix": now - 60,
        "not_after_unix": now + ttl_seconds,
        "revoked_receipt_refs": [],
        "revoked_source_shas": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=1200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = create(
            source_sha=args.source_sha, run_id=args.run_id,
            run_attempt=args.run_attempt, scope=args.scope,
            ttl_seconds=args.ttl_seconds,
        )
        term._write(args.output, result)
        print("RECIPIENT_INTENT: independently derived exact VGI obligation")
    except (receiver.ReceiverReject, term.TermReceiptError,
            subprocess.SubprocessError, OSError, ValueError) as exc:
        parser.exit(1, f"RECIPIENT_INTENT_REJECTED: {exc}\n")


if __name__ == "__main__":
    main()
