"""COE-013: embed ORIGINAL canonical JSON file bytes as Lean literals.

Deliberately does not call json.loads or normalize/interpret JSON tokens,
objects, arrays, numbers, hashes, or neural certificate structure. Lean's
COE013Json parser owns those checks. File-name allowlisting, size limits,
the file's ASCII bytes and SHA256 receipts remain in the external transport
trust boundary. Independent Python/Go verifier checks still run separately.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from emit_lean_certificates import FILENAMES, TranslationRefused, require
from verify_certificates import EXPECTED_NETWORK_DIGESTS


def nat_bytes(raw: bytes) -> str:
    require(type(raw) is bytes and 0 < len(raw) < 8 * 1024 * 1024,
            "JSON transport byte budget exceeded")
    return "[" + ", ".join(str(x) for x in raw) + "]"


def render(directory: Path) -> tuple[str, dict[str, Any]]:
    found = {p.name for p in directory.iterdir() if p.is_file()}
    require(found == FILENAMES,
            "raw JSON manifest mismatch: must replay each pinned fixture")
    sources: list[str] = []
    receipts: dict[str, dict[str, Any]] = {}
    for name in sorted(EXPECTED_NETWORK_DIGESTS):
        raw = (directory / (name + ".json")).read_bytes()
        data = nat_bytes(raw)
        receipts[name] = {
            "original_file_sha256": sha256(raw).hexdigest(),
            "length_bytes": len(raw),
        }
        sources.append(
            f"-- original-file-sha256: {sha256(raw).hexdigest()}\n"
            f"-- original-file-length: {len(raw)}\n"
            f"def {name}_raw : COE013Json.Bytes := {data}\n"
            f"theorem {name}_json_wire :\n"
            f"  (COE013Json.parseEnvelope {name}_raw).map "
            f"COE013Json.Envelope.wire = some COE012.{name}_wire := by decide +kernel\n"
            f"theorem {name}_json_admitted :\n"
            f"  COE013Json.acceptBytes {name}_raw = true := by decide +kernel\n"
            f"#print axioms COE013.{name}_json_wire\n"
            f"#print axioms COE013.{name}_json_admitted"
        )
    result = (
        "import COE013Json\nimport GeneratedWireProofs\n\n"
        "/- COE-013: ORIGINAL FILE BYTES ONLY; Lean parses JSON itself. -/\n"
        "namespace COE013\n\n" +
        "\n\n".join(sources) +
        "\n\nend COE013\n"
    )
    receipt = {
        "schema": "in-formation-space.coe013.original-canonical-json-replay/0.1",
        "files": receipts,
        "count": len(sources),
        "parser": "COE013Json.parseEnvelope",
        "source_encoding": "uninterpreted file bytes embedded as Nat literals",
        "status": "kernel-checked-JSON-structure-after-unverified-raw-byte-embedding",
    }
    return result, receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("certificates", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    code, receipt = render(args.certificates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(code, encoding="utf-8")
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
    print(f"Embedded {receipt['count']} original JSON byte streams as Lean Nat literals; "
          "Lean admission remains an unproven obligation until kernel replay passes.")


if __name__ == "__main__":
    main()
