"""COE-016: fail-closed convergence of independently executed COE evidence.

This module does not verify signatures or prove Lean theorems. CI must run the
Go Ed25519 verifier, Python and Go semantic checkers, and Lean kernel replay
in separate successful jobs before providing their artifacts here. This
module checks that each reports the same *actual received* certificate bytes.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from verify_certificates import EXPECTED_NETWORK_DIGESTS

HEX = re.compile(r"[0-9a-f]{64}\Z")
PASS = re.compile(
    r"COE-014 ([a-z][a-z0-9_]*): original network SHA-256 and pin "
    r"PASS, two mutations rejected\Z"
)


class BindingError(ValueError):
    """Independent verification evidence cannot be joined safely."""


def require(condition: bool, problem: str) -> None:
    if not condition:
        raise BindingError(f"COE-016 rejected: {problem}")


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(0 < len(raw) <= 8 * 1024 * 1024, f"invalid evidence length: {path.name}")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON evidence key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda _: require(False, "nonfinite JSON evidence"))
    except (UnicodeError, ValueError) as exc:
        raise BindingError(f"COE-016 rejected: malformed evidence JSON: {path.name}") from exc
    require(type(value) is dict, f"evidence must be object: {path.name}")
    return value


def named_map(value: object, names: set[str], description: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == names, f"{description} source set mismatch")
    return value


def digest(value: object, description: str) -> str:
    require(type(value) is str and HEX.fullmatch(value) is not None,
            f"{description} must be lowercase SHA-256")
    return value


def join(
    cert_dir: Path,
    authority: dict[str, Any],
    lean: dict[str, Any],
    python: dict[str, Any],
    go: dict[str, Any],
    lean_log: str,
) -> dict[str, Any]:
    names = set(EXPECTED_NETWORK_DIGESTS)
    require(authority.get("schema") == "ifs.coe015.source-authority-receipt/v1" and
            authority.get("status") == "verified-policy-scoped-signatures-and-network-bytes",
            "unverified Ed25519 receiver receipt")
    require(authority.get("policy_mode") == "test-only" and
            authority.get("ground_admitted") is False and
            authority.get("origin_authenticated") is False,
            "test-only proof chain cannot claim production origin or Ground admission")
    quorum = authority.get("threshold")
    signers = authority.get("verified_signers")
    require(type(quorum) is int and quorum >= 2 and
            type(signers) is list and len(signers) >= quorum and
            all(type(s) is str and s for s in signers) and
            len(signers) == len(set(signers)),
            "invalid signed-manifest signature quorum evidence")
    require(type(authority.get("manifest_version")) is int and
            authority["manifest_version"] > 0 and
            type(authority.get("authority")) is str and bool(authority["authority"]),
            "missing signed authority scope")

    network = named_map(authority.get("network_hashes"), names, "signed network")
    require(lean.get("schema") == "in-formation-space.coe013.original-canonical-json-replay/0.1" and
            lean.get("status") ==
            "kernel-checked-JSON-structure-after-unverified-raw-byte-embedding" and
            lean.get("parser") == "COE013Json.parseEnvelope" and
            type(lean.get("count")) is int and lean["count"] == len(names),
            "invalid Lean original-byte transport receipt")
    lean_files = named_map(lean.get("files"), names, "Lean raw-byte")
    for label, report_schema in (
        (python, "in-formation-space.coe002.independent-check-report/0.1"),
        (go, "in-formation-space.coe003.go-independent-report/0.1"),
    ):
        require(label.get("schema") == report_schema and label.get("status") == "all_verified" and
                type(label.get("claim_count")) is int and label["claim_count"] == len(names),
                "invalid independent mathematical checker report")
    py_claims = named_map(python.get("claims"), names, "Python mathematical")
    go_claims = named_map(go.get("claims"), names, "Go mathematical")

    expected_files = {name + ".json" for name in names}
    require(cert_dir.is_dir() and {p.name for p in cert_dir.iterdir()} == expected_files,
            "original received certificate file set mismatch")
    file_hashes: dict[str, str] = {}
    semantic: dict[str, str] = {}
    for name in sorted(names):
        file = cert_dir / (name + ".json")
        require(file.is_file() and not file.is_symlink(), f"unsafe original certificate: {name}")
        raw = file.read_bytes()
        require(0 < len(raw) <= 8 * 1024 * 1024, f"invalid original byte budget: {name}")
        real_file_hash = sha256(raw).hexdigest()
        original = lean_files[name]
        pc, gc = py_claims[name], go_claims[name]
        require(type(original) is dict and type(pc) is dict and type(gc) is dict,
                f"malformed per-source evidence: {name}")
        require(type(original.get("length_bytes")) is int and
                original["length_bytes"] == len(raw), f"Lean original file length mismatch: {name}")
        for value, label in (
            (original.get("original_file_sha256"), "Lean"),
            (pc.get("certificate_sha256"), "Python"),
            (gc.get("certificate_sha256"), "Go"),
        ):
            require(digest(value, f"{label} certificate hash: {name}") == real_file_hash,
                    f"{label} did not verify these exact certificate bytes: {name}")
        expected = EXPECTED_NETWORK_DIGESTS[name]
        for value, label in (
            (network[name], "signed Go authority"),
            (pc.get("network_sha256"), "Python"),
            (gc.get("network_sha256"), "Go"),
        ):
            require(digest(value, f"{label} network hash: {name}") == expected,
                    f"{label} network identity mismatch: {name}")
        require(pc.get("status") == "verified" and gc.get("status") == "verified",
                f"independent semantic admission absent: {name}")
        ps = digest(pc.get("semantic_sha256"), f"Python semantic hash: {name}")
        gs = digest(gc.get("semantic_sha256"), f"Go semantic hash: {name}")
        require(ps == gs, f"Python / Go semantic claims disagree: {name}")
        file_hashes[name] = real_file_hash
        semantic[name] = ps

    observed: list[str] = []
    for line in lean_log.splitlines():
        if line.startswith("COE-014 "):
            match = PASS.fullmatch(line)
            require(match is not None, "unexpected Lean pinned-byte replay line")
            observed.append(match.group(1))
    require(len(observed) == len(names) and set(observed) == names,
            "incomplete or duplicate Lean original-network replay evidence")

    # Success is strictly about this CI run's independently produced artifacts,
    # not about a cryptographically self-attesting Lean transcript.
    return {
        "schema": "ifs.coe016.same-received-source-evidence/v1",
        "status": "test-only-verified-evidence-convergence",
        "source_count": len(names),
        "original_certificate_sha256": file_hashes,
        "network_sha256": {name: EXPECTED_NETWORK_DIGESTS[name] for name in sorted(names)},
        "semantic_sha256": semantic,
        "signed_authority": authority["authority"],
        "signed_manifest_version": authority["manifest_version"],
        "signature_quorum": quorum,
        "signed_by": signers,
        "ground_admitted": False,
        "origin_authenticated": False,
        "trust_scope": (
            "Depends on successful trusted same-run CI execution of Go Ed25519, "
            "Python and Go mathematical checkers, and Lean kernel replay. "
            "Evidence files are not individually signed. Demo keys convey no external identity."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("certs", "authority", "lean", "python", "go", "lean-log", "output"):
        parser.add_argument("--" + arg, required=True, type=Path)
    args = parser.parse_args()
    receipt = join(args.certs, read_json(args.authority), read_json(args.lean),
                   read_json(args.python), read_json(args.go),
                   args.lean_log.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    print("COE-016: same received original bytes verified across signed Go, Lean, Python and Go evidence")


if __name__ == "__main__":
    main()
