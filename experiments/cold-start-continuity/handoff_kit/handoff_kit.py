#!/usr/bin/env python3
"""Inspect cold-start handoff run records.

The tool checks that a run manifest and its referenced artifacts agree, and
that the declared isolation level is not stronger than the recorded controls.
It is a consistency checker, not an attestation service: it cannot prove that
a recipient obeyed an instruction, that a tool call did not occur, or that a
workspace was actually unreachable.

Zero external dependencies. Python 3.10+.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


MANIFEST_FORMAT = "in-formation.cold-start-run/0.1"
MANIFEST_NAME = "manifest.json"
LEVELS = ("L0", "L1", "L2", "L3")
TOOL_POLICIES = ("unknown", "available", "prohibited-by-instruction", "disabled", "instrumented")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")

# Files that belong to a standard run record. Review notes are annotations,
# not material supplied to the recipient.
DEFAULT_ALLOWED = {
    MANIFEST_NAME,
    "prompt.md",
    "response.md",
    "conditions.md",
    "evaluation.md",
    "review-note.md",
    "supplementary-review.md",
}


def normalize_lf(data: bytes) -> bytes:
    """Normalize CRLF and CR line endings to LF."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_lf(path: Path) -> str:
    """Return the SHA-256 of a file's UTF-8 bytes with LF line endings."""
    return hashlib.sha256(normalize_lf(path.read_bytes())).hexdigest()


def read_text_lf(path: Path) -> str:
    """Read a UTF-8 text file after LF normalization."""
    return normalize_lf(path.read_bytes()).decode("utf-8")


def _display_path(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        try:
            return os.path.relpath(path.resolve(), base.resolve()).replace("\\", "/")
        except ValueError:
            return path.resolve().as_posix()


@dataclass
class Check:
    name: str
    status: str  # "pass", "warn", or "fail"
    detail: str


@dataclass
class AuditResult:
    run_dir: Path
    checks: List[Check] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add(self, status: str, name: str, detail: str) -> None:
        self.checks.append(Check(name=name, status=status, detail=detail))
        if status == "fail":
            self.errors.append(f"{name}: {detail}")
        elif status == "warn":
            self.warnings.append(f"{name}: {detail}")

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checks": [
                {"name": check.name, "status": check.status, "detail": check.detail}
                for check in self.checks
            ],
        }


def build_manifest(
    run_dir: Path,
    packet: Path,
    template: Path,
    *,
    run_id: Optional[str] = None,
    level: str = "L1",
    tool_policy: str = "prohibited-by-instruction",
    tool_instrumentation: bool = False,
    workspace_isolation: bool = False,
    recipient_context: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a manifest for an existing run directory.

    Artifact hashes are included for files that are present. Run this again
    after adding a prompt or response to refresh the record.
    """
    run_dir = Path(run_dir)
    packet = Path(packet)
    template = Path(template)

    manifest: Dict[str, Any] = {
        "format": MANIFEST_FORMAT,
        "run_id": run_id or run_dir.name,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "isolation_level": level,
        "packet": {
            "path": _display_path(packet, run_dir),
            "sha256_lf": sha256_lf(packet),
        },
        "template": {
            "path": _display_path(template, run_dir),
            "sha256_lf": sha256_lf(template),
        },
        "supplied_material": ["packet.md", "report-template.md"],
        "tool_policy": tool_policy,
        "tool_instrumentation": bool(tool_instrumentation),
        "workspace_isolation": bool(workspace_isolation),
        "artifacts": {},
    }

    for name in ("prompt", "response", "conditions", "evaluation"):
        artifact = run_dir / f"{name}.md"
        if artifact.is_file():
            manifest["artifacts"][name] = {
                "path": artifact.name,
                "sha256_lf": sha256_lf(artifact),
            }

    if recipient_context:
        manifest["recipient"] = {
            "context": recipient_context,
            "identity_verified": False,
        }
    if notes:
        manifest["notes"] = notes

    return manifest


def write_manifest(run_dir: Path, manifest: Dict[str, Any]) -> Path:
    """Write a manifest with stable JSON formatting and LF newlines."""
    path = Path(run_dir) / MANIFEST_NAME
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def _check_file(
    result: AuditResult,
    name: str,
    entry: Any,
    run_dir: Path,
    *,
    required_hash: bool,
    mismatch_is_warning: bool = False,
) -> Optional[Path]:
    if not isinstance(entry, dict):
        result.add("fail", name, "entry must be an object with 'path' and 'sha256_lf'.")
        return None

    rel = entry.get("path")
    if not isinstance(rel, str) or not rel.strip():
        result.add("fail", name, "path must be a non-empty string.")
        return None

    path = (run_dir / rel).resolve()
    if not path.is_file():
        result.add("fail", name, f"referenced file not found: {rel}")
        return None

    expected = entry.get("sha256_lf")
    if expected is None:
        if required_hash:
            result.add("fail", name, "sha256_lf is required for this artifact.")
        else:
            result.add("pass", name, f"present: {rel} (hash optional)")
        return path

    if not isinstance(expected, str) or not _HEX64.fullmatch(expected):
        result.add("fail", name, "sha256_lf must be a 64-character hexadecimal digest.")
        return path

    actual = sha256_lf(path)
    if actual != expected.lower():
        status = "warn" if mismatch_is_warning else "fail"
        result.add(status, name, f"hash mismatch: recorded {expected.lower()}, actual {actual}.")
    else:
        result.add("pass", name, f"hash matches: {rel}")
    return path


def _check_manifest_root(result: AuditResult, manifest: Dict[str, Any], run_dir: Path) -> None:
    if manifest.get("format") != MANIFEST_FORMAT:
        result.add("fail", "format", f"expected {MANIFEST_FORMAT!r}, got {manifest.get('format')!r}.")
    else:
        result.add("pass", "format", MANIFEST_FORMAT)

    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        result.add("fail", "run_id", "must be a non-empty string.")
    else:
        result.add("pass", "run_id", run_id)
        if run_id != run_dir.name:
            result.add("warn", "run_id", f"run_id {run_id!r} does not match directory name {run_dir.name!r}.")

    level = manifest.get("isolation_level")
    if level not in LEVELS:
        result.add("fail", "isolation_level", f"must be one of {', '.join(LEVELS)}.")
    else:
        result.add("pass", "isolation_level", level)

    policy = manifest.get("tool_policy")
    if policy not in TOOL_POLICIES:
        result.add("fail", "tool_policy", f"must be one of {', '.join(TOOL_POLICIES)}.")
    else:
        result.add("pass", "tool_policy", policy)

    for key in ("tool_instrumentation", "workspace_isolation"):
        value = manifest.get(key)
        if not isinstance(value, bool):
            result.add("fail", key, "must be a boolean.")
        else:
            result.add("pass", key, str(value).lower())

    if policy == "instrumented" and manifest.get("tool_instrumentation") is not True:
        result.add("fail", "tool_policy", "policy 'instrumented' requires tool_instrumentation=true.")

    supplied = manifest.get("supplied_material")
    if not isinstance(supplied, list) or not all(isinstance(item, str) for item in supplied):
        result.add("fail", "supplied_material", "must be an array of strings.")
    else:
        lowered = [item.lower() for item in supplied]
        if any("reviewer" in item for item in lowered):
            result.add("fail", "supplied_material", "must not include reviewer-guide material.")
        else:
            result.add("pass", "supplied_material", ", ".join(supplied))
        if not any("packet" in item for item in lowered):
            result.add("warn", "supplied_material", "does not mention the packet.")
        if not any("template" in item for item in lowered):
            result.add("warn", "supplied_material", "does not mention the report template.")


def _check_isolation(result: AuditResult, manifest: Dict[str, Any]) -> None:
    level = manifest.get("isolation_level")
    policy = manifest.get("tool_policy")
    instrumented = manifest.get("tool_instrumentation") is True
    isolated = manifest.get("workspace_isolation") is True

    if level == "L0":
        result.add("warn", "L0 scope", "open-workspace runs do not establish packet-only continuity.")
        if isolated:
            result.add("warn", "L0 isolation", "workspace_isolation=true is stronger than the L0 definition; consider L2.")
    elif level == "L1":
        result.add("warn", "L1 scope", "material-limited runs support packet-limited evidence, not ambient independence.")
        if isolated:
            result.add("warn", "L1 isolation", "workspace_isolation=true is stronger than the L1 definition; consider L2.")
        if instrumented:
            result.add("warn", "L1 instrumentation", "tool_instrumentation=true is stronger than the L1 definition; consider L2.")
        if policy == "disabled":
            result.add("warn", "L1 tool policy", "tool policy 'disabled' is stronger than the L1 definition; consider L2.")
    elif level in ("L2", "L3"):
        if not isolated:
            result.add("fail", "L2/L3 isolation", "workspace_isolation must be true for L2 or L3.")
        if not instrumented and policy != "disabled":
            result.add(
                "fail",
                "L2/L3 tool control",
                "L2/L3 require tool_instrumentation=true or tool_policy='disabled'.",
            )
        result.add(
            "warn",
            "isolation declaration",
            "controls are declared by the manifest, not independently verified by this tool.",
        )


def _check_prompt_material(
    result: AuditResult,
    manifest: Dict[str, Any],
    prompt_path: Optional[Path],
    packet_path: Optional[Path],
    template_path: Optional[Path],
) -> None:
    if manifest.get("isolation_level") != "L1":
        return
    if prompt_path is None or packet_path is None or template_path is None:
        return

    try:
        prompt = read_text_lf(prompt_path)
        packet = read_text_lf(packet_path).strip()
        template = read_text_lf(template_path).strip()
    except (OSError, UnicodeDecodeError) as exc:
        result.add("fail", "L1 prompt", f"could not read prompt/material for inline check: {exc}")
        return

    if not packet:
        result.add("fail", "L1 prompt", "packet is empty; cannot verify inline material.")
    elif packet not in prompt:
        result.add("fail", "L1 prompt", "prompt.md does not contain the packet text; L1 requires inline material.")
    else:
        result.add("pass", "L1 prompt", "packet text is present in prompt.md.")

    if not template:
        result.add("fail", "L1 prompt", "report template is empty; cannot verify inline material.")
    elif template not in prompt:
        result.add("fail", "L1 template", "prompt.md does not contain the report template; L1 requires inline material.")
    else:
        result.add("pass", "L1 template", "report template text is present in prompt.md.")


def _check_run_files(result: AuditResult, run_dir: Path) -> None:
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        name = path.name.lower()

        if name in {"reviewer-guide.md", "reviewer_guide.md"}:
            result.add("fail", "forbidden file", f"{rel} is present; keep the reviewer guide away from recipients.")
        elif name == "readme.md":
            result.add("warn", "possible context leak", f"{rel} is present; check whether it exposes reviewer context.")
        elif rel in DEFAULT_ALLOWED or rel.startswith("results/"):
            continue
        else:
            result.add("warn", "unexpected file", f"{rel} is not in the standard run record set.")


def audit_run(run_dir: Path, manifest_path: Optional[Path] = None) -> AuditResult:
    """Audit a run directory against its manifest."""
    run_dir = Path(run_dir).resolve()
    result = AuditResult(run_dir=run_dir)

    if not run_dir.is_dir():
        result.add("fail", "run directory", f"not found: {run_dir}")
        return result

    manifest_file = Path(manifest_path) if manifest_path else run_dir / MANIFEST_NAME
    if not manifest_file.is_file():
        result.add("fail", "manifest", f"not found: {manifest_file}")
        return result

    try:
        with manifest_file.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.add("fail", "manifest", f"cannot read JSON: {exc}")
        return result

    if not isinstance(manifest, dict):
        result.add("fail", "manifest", "root must be a JSON object.")
        return result
    result.add("pass", "manifest", f"parsed {manifest_file.name}.")

    _check_manifest_root(result, manifest, run_dir)

    packet_path = _check_file(
        result, "packet", manifest.get("packet"), run_dir, required_hash=True
    )
    template_path = _check_file(
        result, "template", manifest.get("template"), run_dir, required_hash=True
    )

    artifacts = manifest.get("artifacts")
    artifact_paths: Dict[str, Optional[Path]] = {}
    if not isinstance(artifacts, dict):
        result.add("fail", "artifacts", "must be an object.")
    else:
        for required in ("prompt", "response"):
            if required not in artifacts:
                result.add("fail", "artifacts", f"missing required artifact: {required}")
        for name, entry in artifacts.items():
            required_hash = name in {"prompt", "response"}
            artifact_paths[name] = _check_file(
                result,
                f"artifact:{name}",
                entry,
                run_dir,
                required_hash=required_hash,
                mismatch_is_warning=not required_hash,
            )

    prompt_path = artifact_paths.get("prompt")
    response_path = artifact_paths.get("response")

    if prompt_path is not None:
        try:
            if not read_text_lf(prompt_path).strip():
                result.add("fail", "artifact:prompt", "prompt is empty.")
        except (OSError, UnicodeDecodeError) as exc:
            result.add("fail", "artifact:prompt", f"cannot read prompt: {exc}")

    if response_path is not None:
        try:
            if not read_text_lf(response_path).strip():
                result.add("fail", "artifact:response", "response is empty.")
        except (OSError, UnicodeDecodeError) as exc:
            result.add("fail", "artifact:response", f"cannot read response: {exc}")

    _check_isolation(result, manifest)
    _check_prompt_material(result, manifest, prompt_path, packet_path, template_path)
    _check_run_files(result, run_dir)

    created_at = manifest.get("created_at")
    if created_at is not None:
        if not isinstance(created_at, str):
            result.add("fail", "created_at", "must be an ISO 8601 string when present.")
        else:
            try:
                datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                result.add("fail", "created_at", "must be a parseable ISO 8601 date-time.")

    return result


def format_audit(result: AuditResult) -> str:
    """Format an audit result for a terminal."""
    lines = [
        f"Run: {result.run_dir}",
        f"Status: {'PASS' if result.ok else 'FAIL'} "
        f"({len(result.errors)} errors, {len(result.warnings)} warnings)",
    ]
    for check in result.checks:
        lines.append(f"[{check.status.upper()}] {check.name}: {check.detail}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record and audit cold-start handoff run manifests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest", help="Write a manifest for a run directory.")
    manifest_parser.add_argument("--run-dir", required=True, type=Path)
    manifest_parser.add_argument("--packet", required=True, type=Path)
    manifest_parser.add_argument("--template", required=True, type=Path)
    manifest_parser.add_argument("--run-id")
    manifest_parser.add_argument("--level", required=True, choices=LEVELS)
    manifest_parser.add_argument("--tool-policy", choices=TOOL_POLICIES, default="prohibited-by-instruction")
    manifest_parser.add_argument("--tool-instrumentation", action="store_true")
    manifest_parser.add_argument("--workspace-isolation", action="store_true")
    manifest_parser.add_argument("--recipient-context")
    manifest_parser.add_argument("--notes")
    manifest_parser.add_argument("--force", action="store_true")

    audit_parser = subparsers.add_parser("audit", help="Audit a run directory against its manifest.")
    audit_parser.add_argument("--run-dir", required=True, type=Path)
    audit_parser.add_argument("--manifest", type=Path)
    audit_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "manifest":
        if args.level in ("L2", "L3") and not args.workspace_isolation:
            parser.error("L2/L3 require --workspace-isolation.")
        if args.level in ("L2", "L3") and not args.tool_instrumentation and args.tool_policy != "disabled":
            parser.error("L2/L3 require --tool-instrumentation or --tool-policy disabled.")

        run_dir = args.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = run_dir / MANIFEST_NAME
        if manifest_file.exists() and not args.force:
            print(f"Manifest already exists: {manifest_file}. Use --force to replace it.", file=sys.stderr)
            return 2
        try:
            manifest = build_manifest(
                run_dir,
                args.packet,
                args.template,
                run_id=args.run_id,
                level=args.level,
                tool_policy=args.tool_policy,
                tool_instrumentation=args.tool_instrumentation,
                workspace_isolation=args.workspace_isolation,
                recipient_context=args.recipient_context,
                notes=args.notes,
            )
        except (OSError, ValueError) as exc:
            print(f"Cannot build manifest: {exc}", file=sys.stderr)
            return 2
        path = write_manifest(run_dir, manifest)
        print(path)
        return 0

    result = audit_run(args.run_dir, args.manifest)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_audit(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
