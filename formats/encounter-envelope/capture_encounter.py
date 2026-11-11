#!/usr/bin/env python3
"""Encounter Capture Utility for In-Formation Encounter Envelope (experimental 0.1).

Wraps command execution, function results, or raw observations and produces
a schema-compliant in-formation.encounter/0.1 record with cryptographic digests.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import local validator if available
try:
    from validate_envelope import validate_encounter
except ImportError:
    # Handle import if executed from parent or different directory
    sys.path.insert(0, str(Path(__file__).parent))
    from validate_envelope import validate_encounter


SCHEMA_FORMAT = "in-formation.encounter/0.1"


def get_utc_iso8601() -> str:
    """Return current UTC time in strict ISO 8601 format."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def compute_sha256(data: str | bytes) -> str:
    """Compute hex SHA-256 digest."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def build_encounter_envelope(
    encounter_id: str,
    source_kind: str,
    payload_value: Any = None,
    payload_ref: Optional[str] = None,
    source_name: Optional[str] = None,
    source_ref: Optional[str] = None,
    capture_method: Optional[str] = "automatic-capture",
    context: Optional[Dict[str, Any]] = None,
    relations: Optional[List[Dict[str, Any]]] = None,
    extensions: Optional[Dict[str, Any]] = None,
    observed_at: Optional[str] = None,
    recorded_at: Optional[str] = None,
    media_type: str = "application/json",
) -> Dict[str, Any]:
    """Construct an encounter record conforming to in-formation.encounter/0.1."""
    if recorded_at is None:
        recorded_at = get_utc_iso8601()

    envelope: Dict[str, Any] = {
        "format": SCHEMA_FORMAT,
        "id": encounter_id,
        "observed_at": observed_at,
        "recorded_at": recorded_at,
        "source": {
            "kind": source_kind,
            "name": source_name,
            "reference": source_ref,
            "capture_method": capture_method,
        },
        "context": context or {},
    }

    payload: Dict[str, Any] = {
        "media_type": media_type,
    }

    if payload_ref is not None:
        payload["reference"] = payload_ref
    else:
        payload["value"] = payload_value
        # Canonical digest of value
        if isinstance(payload_value, str):
            val_bytes = payload_value.encode("utf-8")
        else:
            val_bytes = json.dumps(payload_value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["digest"] = f"sha256:{compute_sha256(val_bytes)}"

    envelope["payload"] = payload
    envelope["relations"] = relations or []

    if "digest" in payload:
        canon_mode = "utf8-raw-v1" if isinstance(payload_value, str) else "json-sort-keys-utf8-v1"
        envelope["integrity"] = {
            "algorithm": "sha256",
            "digest": payload["digest"].replace("sha256:", ""),
            "canonicalization": canon_mode,
        }

    if extensions:
        envelope["extensions"] = extensions

    # Self-validation
    is_valid, errors = validate_encounter(envelope)
    if not is_valid:
        raise ValueError(f"Generated envelope violates schema: {errors}")

    return envelope


def capture_command(
    command_str: str,
    encounter_id: Optional[str] = None,
    source_name: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a shell command, capture stdout/stderr/status, and wrap in an encounter envelope."""
    obs_start = get_utc_iso8601()
    t0 = time.perf_counter()

    proc = subprocess.run(
        command_str,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    t1 = time.perf_counter()
    obs_end = get_utc_iso8601()

    if encounter_id is None:
        ts_slug = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        encounter_id = f"cmd-run:{ts_slug}:{abs(hash(command_str)) % 100000:05d}"

    ctx: Dict[str, Any] = {
        "command": command_str,
        "exit_code": proc.returncode,
        "duration_ms": round((t1 - t0) * 1000.0, 3),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "python_version": platform.python_version(),
        },
        "cwd": os.getcwd(),
    }
    if extra_context:
        ctx.update(extra_context)

    payload_value = {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

    return build_encounter_envelope(
        encounter_id=encounter_id,
        source_kind="subprocess",
        source_name=source_name or "shell-command-runner",
        capture_method="subprocess.run",
        payload_value=payload_value,
        observed_at=obs_start,
        recorded_at=obs_end,
        context=ctx,
        media_type="application/json",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture an encounter envelope from a command or raw value.")
    subparsers = parser.add_subparsers(dest="subcommand", help="Mode of capture")

    # Command capture
    cmd_parser = subparsers.add_parser("cmd", help="Execute and capture a command")
    cmd_parser.add_argument("command", type=str, help="Command string to run")
    cmd_parser.add_argument("--id", type=str, default=None, help="Encounter ID")
    cmd_parser.add_argument("--name", type=str, default=None, help="Source name")
    cmd_parser.add_argument("--out", type=str, default=None, help="Output JSON path")

    # Value capture
    val_parser = subparsers.add_parser("value", help="Wrap a given text/json value into an encounter")
    val_parser.add_argument("value", type=str, help="Value string (or json string)")
    val_parser.add_argument("--id", type=str, required=True, help="Encounter ID")
    val_parser.add_argument("--kind", type=str, default="manual-entry", help="Source kind")
    val_parser.add_argument("--name", type=str, default=None, help="Source name")
    val_parser.add_argument("--media-type", type=str, default="text/plain", help="Payload media type")
    val_parser.add_argument("--out", type=str, default=None, help="Output JSON path")

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        return 2

    if args.subcommand == "cmd":
        envelope = capture_command(args.command, encounter_id=args.id, source_name=args.name)
    elif args.subcommand == "value":
        # Check if value is valid json
        try:
            val_obj = json.loads(args.value)
        except json.JSONDecodeError:
            val_obj = args.value
        envelope = build_encounter_envelope(
            encounter_id=args.id,
            source_kind=args.kind,
            source_name=args.name,
            payload_value=val_obj,
            media_type=args.media_type,
        )
    else:
        return 2

    rendered = json.dumps(envelope, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        print(f"[OK] Captured encounter saved to {args.out} (id: {envelope['id']})")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    sys.exit(main())
