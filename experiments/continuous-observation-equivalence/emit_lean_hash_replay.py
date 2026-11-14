"""COE-014 source-byte integrity test transport.

Emits a Lean runner referencing ORIGINAL COE-013 byte literals and two
single-byte mutations (one network value and one embedded digest value).
Python finds offsets but never decides cryptographic or mathematical
admission; all actual SHA-256 comparisons execute in independent Lean.

The mutation fixture creation is untrusted test scaffolding; it is NOT
part of the formal provenance acceptance theorem.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from emit_lean_certificates import FILENAMES, require
from verify_certificates import EXPECTED_NETWORK_DIGESTS


def find_mutations(raw: bytes) -> tuple[int, int, int]:
    prefix = b'"network":{"layers":'
    start = raw.index(prefix) + len(prefix)
    end = raw.index(b'},"network_sha256":', start)
    inside = next(
        i for i in range(start, end)
        if 48 <= raw[i] <= 57 and raw[i - 1] == 34
    )
    changed = 49 if raw[inside] == 48 else 48
    header = raw.index(b'"network_sha256":"') + len(b'"network_sha256":"')
    require(raw[header] in b"0123456789abcdef", "missing network header digest")
    return inside, changed, header


def render(directory: Path) -> str:
    files = {p.name for p in directory.iterdir() if p.is_file()}
    require(files == FILENAMES, "raw-byte SHA replay file manifest mismatch")
    lines = [
        "import GeneratedJSONProofs",
        "import COE014Provenance",
        "",
        "/- COE-014: recompute SHA-256 from original network JSON bytes in Lean. -/",
        "namespace COE014Replay",
        "open COE013Json COE014SHA256 COE014Provenance",
        "",
        "def flipAt (raw : Bytes) (offset value : Nat) : Bytes :=",
        "  raw.take offset ++ [value] ++ raw.drop (offset + 1)",
        "",
        "def verifyOne (name : String) (raw : Bytes) (networkIndex replacement headerIndex : Nat) : IO Unit := do",
        "  if !(acceptPinnedBytes raw) then",
        "    throw (IO.userError s!\"{name}: source provenance rejected\")",
        "  let changedNetwork := flipAt raw networkIndex replacement",
        "  match parseEnvelope changedNetwork with",
        "  | none => throw (IO.userError s!\"{name}: mutated network was not syntactically valid\")",
        "  | some env =>",
        "      if hashMatchesHeader env then",
        "        throw (IO.userError s!\"{name}: modified network incorrectly preserved SHA-256\")",
        "  if acceptPinnedBytes changedNetwork then",
        "    throw (IO.userError s!\"{name}: modified network incorrectly passed manifest\")",
        "  let forgedHeader := flipAt raw headerIndex 48",
        "  match parseEnvelope forgedHeader with",
        "  | none => throw (IO.userError s!\"{name}: forged header was not syntactically valid\")",
        "  | some env =>",
        "      if hashMatchesHeader env then",
        "        throw (IO.userError s!\"{name}: forged network SHA-256 header matched\")",
        "  if acceptPinnedBytes forgedHeader then",
        "    throw (IO.userError s!\"{name}: forged header incorrectly passed manifest\")",
        "  IO.println s!\"COE-014 {name}: original network SHA-256 and pin PASS, two mutations rejected\"",
        "",
        "end COE014Replay",
        "",
        "def main : IO Unit := do",
    ]
    for name in sorted(EXPECTED_NETWORK_DIGESTS):
        raw = (directory / (name + ".json")).read_bytes()
        i, replacement, j = find_mutations(raw)
        # A forged header must ALWAYS differ from the source: choose ASCII
        # digit 0 or 1 depending on the current first digest nibble.
        headerReplacement = 49 if raw[j] == 48 else 48
        # Include a dedicated invocation of verifyOne for each source; its
        # header replacement is passed separately from the network value.
        lines[lines.index("def verifyOne (name : String) (raw : Bytes) (networkIndex replacement headerIndex : Nat) : IO Unit := do")] = (
            "def verifyOne (name : String) (raw : Bytes) (networkIndex replacement headerIndex headerReplacement : Nat) : IO Unit := do"
        )
        lines[lines.index("  let forgedHeader := flipAt raw headerIndex 48")] = (
            "  let forgedHeader := flipAt raw headerIndex headerReplacement"
        )
        lines.append(
            f'  COE014Replay.verifyOne "{name}" COE013.{name}_raw {i} {replacement} {j} {headerReplacement}'
        )
    lines.extend(["", ""])
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("certificates", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    content = render(args.certificates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print("Emitted original-source SHA-256 and adversarial mutation replay obligations")


if __name__ == "__main__":
    main()
