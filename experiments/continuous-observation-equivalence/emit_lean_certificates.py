"""COE-007: lossless *data-only* adapter for Lean certificate replay.

This is intentionally not an authority or a mathematical verifier. A small
allowlisted JSON-to-Lean translation serializes exact rational source and
claimed activation cells as typed literal terms. The independent Lean checker
computes all layer laws, roots, joins, and final affine outputs itself.

The trusted verifier-side manifest (COE-002) pins source network digests.
The Python/Go certificate checkers separately verify canonical bytes, semantic
fingerprints, and untrusted producer artifacts.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from verify_certificates import EXPECTED_NETWORK_DIGESTS

SCHEMA = "in-formation-space.coe002.activation-cell-certificate/0.1"
_CANON = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z", re.ASCII)
FILENAMES = frozenset(f"{name}.json" for name in EXPECTED_NETWORK_DIGESTS)


class TranslationRefused(ValueError):
    pass


def require(value: bool, msg: str) -> None:
    if not value:
        raise TranslationRefused(msg)


def ordered_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def strict_json(raw: bytes) -> dict[str, Any]:
    require(type(raw) is bytes and 0 < len(raw) < 8 * 1024 * 1024,
            "certificate byte budget exceeded")
    def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, v in pairs:
            require(key not in out, "duplicate JSON key")
            out[key] = v
        return out
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs)
    except (UnicodeError, ValueError) as exc:
        raise TranslationRefused("invalid certificate JSON") from exc
    require(type(obj) is dict and raw == ordered_bytes(obj) + b"\n",
            "certificate must be canonical JSON with final LF")
    require(set(obj) == {"schema", "network", "network_sha256",
                         "atomic_cells", "semantic_atlas", "semantic_sha256"}
            and obj["schema"] == SCHEMA, "certificate schema mismatch")
    return obj


def lean_rational(value: Any) -> str:
    require(type(value) is str and len(value) <= 128 and _CANON.fullmatch(value) is not None,
            "noncanonical rational token")
    q = Fraction(value)
    require(str(q) == value, "rational fraction is not reduced")
    if q.denominator == 1:
        return f"({q.numerator} : Rat)"
    return f"(({q.numerator} : Rat) / ({q.denominator} : Rat))"


def option_endpoint(value: Any, absent: str) -> str:
    if value == absent:
        return "none"
    return f"some {lean_rational(value)}"


def affine_description(raw: Any) -> str:
    require(type(raw) is list and len(raw) == 2, "invalid affine coordinate")
    return "{ slope := " + lean_rational(raw[0]) + ", offset := " + lean_rational(raw[1]) + " }"


def layer_description(raw: Any) -> str:
    require(type(raw) is dict and set(raw) == {"activation", "weights", "bias"},
            "invalid network layer")
    require(raw["activation"] in ("relu", "linear"), "unknown activation")
    weights, bias = raw["weights"], raw["bias"]
    require(type(weights) is list and type(bias) is list
            and len(weights) == len(bias) and 0 < len(weights) <= 128, "invalid matrix height")
    require(all(type(row) is list and len(row) > 0 for row in weights), "invalid matrix")
    matrix = "[" + ", ".join("[" + ", ".join(lean_rational(v) for v in row) + "]"
                             for row in weights) + "]"
    b = "[" + ", ".join(lean_rational(v) for v in bias) + "]"
    mode = "true" if raw["activation"] == "relu" else "false"
    return "{ weights := " + matrix + ", bias := " + b + ", relu := " + mode + " }"


def cell_description(raw: Any) -> str:
    require(type(raw) is dict and set(raw) == {"left", "right", "affines"},
            "invalid activation cell")
    a = raw["affines"]
    require(type(a) is list and 0 < len(a) <= 128, "invalid cell output width")
    return ("{ left := " + option_endpoint(raw["left"], "-inf") +
            ", right := " + option_endpoint(raw["right"], "+inf") +
            ", output := [" + ", ".join(affine_description(x) for x in a) + "] }")


def convert_one(name: str, raw: bytes) -> tuple[str, int, str]:
    obj = strict_json(raw)
    network = obj["network"]
    require(type(network) is dict and set(network) == {"layers"}, "invalid network schema")
    layers = network["layers"]
    cells = obj["atomic_cells"]
    require(type(layers) is list and 0 < len(layers) <= 64, "invalid layer count")
    require(type(cells) is list and 0 < len(cells) <= 4096, "invalid activation cell count")
    network_digest = hashlib.sha256(ordered_bytes(network)).hexdigest()
    require(network_digest == EXPECTED_NETWORK_DIGESTS[name] == obj["network_sha256"],
            "source network not pinned to independently checked policy")
    model = ("{ layers := [" + ",\n      ".join(layer_description(v) for v in layers) +
             "],\n    cells := [" + ",\n      ".join(cell_description(v) for v in cells) + "] }")
    lines = [
        f"-- source-file-sha256: {hashlib.sha256(raw).hexdigest()}",
        f"-- pinned-source-network-sha256: {network_digest}",
        f"-- source-activation-cell-count: {len(cells)}",
        f"def {name} : COEWireCheck.Cert :=",
        "  " + model,
        f"#eval COEWireCheck.verify {name}",
        f"theorem {name}_arith_verified : COEWireCheck.verify {name} = true := by decide +kernel",
        f"#print axioms COE007.{name}_arith_verified",
    ]
    return "\n".join(lines), len(cells), hashlib.sha256(raw).hexdigest()


def render(directory: Path) -> tuple[str, dict[str, Any]]:
    found = {p.name for p in directory.iterdir() if p.is_file()}
    require(found == FILENAMES, "manifest mismatch: must replay every pinned fixture")
    blocks = []
    originals = {}
    total = 0
    for name in sorted(EXPECTED_NETWORK_DIGESTS):
        raw = (directory / (name + ".json")).read_bytes()
        block, cells, raw_digest = convert_one(name, raw)
        blocks.append(block)
        originals[name] = {"certificate_file_sha256": raw_digest, "cells": cells}
        total += cells
    generated = ("import COEWireCheck\n\n" +
                 "/- COE-007: literal certificate inputs, all arithmetic checked by Lean. -/\n" +
                 "namespace COE007\n\n" + "\n\n".join(blocks) +
                 "\n\nend COE007\n")
    return generated, {"schema": "in-formation-space.coe007.lean-replay-manifest/0.1",
                       "models": originals, "cell_count": total,
                       "model_count": len(originals),
                       "checker": "COEWireCheck.verify",
                       "status": "source-translated-for-kernel-recheck-not-admitted"}


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("certificates", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--manifest", type=Path)
    args = cli.parse_args()
    content, manifest = render(args.certificates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(f"Rendered {manifest['model_count']} exact rational certificates with "
          f"{manifest['cell_count']} activation cells; Lean proof is not asserted here.")


if __name__ == "__main__":
    main()
