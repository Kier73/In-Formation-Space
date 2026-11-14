"""COE-012: transport exact source ASCII token bytes into Lean.

No numeric token is parsed into a Python Fraction or normalized here.
Lean's separate COE012Wire decoder owns exact rational parsing, sentinel
decoding, activation decoding, and certificate admission.

The JSON envelope and array structure still pass through unverified Python.
The pin manifest and separately implemented Python/Go checkers retain their
independent responsibilities; this script alone does not confer authority.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from emit_lean_certificates import (
    FILENAMES, TranslationRefused, require, ordered_bytes, strict_json,
    EXPECTED_NETWORK_DIGESTS,
)


def literal(value: Any) -> str:
    """Transport original token ASCII byte codes, with NO numeric parsing.

    ASCII-to-Nat structure conversion remains in the Python envelope trust
    boundary. Actual numeric interpretation is wholly Lean kernel reducible.
    """
    require(type(value) is str and len(value) <= 128 and value.isascii(),
            "invalid non-ASCII source token")
    return "[" + ", ".join(str(code) for code in value.encode("ascii")) + "]"


def wire_affine(raw: Any) -> str:
    require(type(raw) is list and len(raw) == 2, "invalid wire affine")
    return "{ slope := " + literal(raw[0]) + ", offset := " + literal(raw[1]) + " }"


def wire_layer(raw: Any) -> str:
    require(type(raw) is dict and set(raw) == {"activation", "weights", "bias"},
            "invalid network layer structure")
    matrix, bias = raw["weights"], raw["bias"]
    require(type(matrix) is list and type(bias) is list and
            0 < len(matrix) <= 128 and len(matrix) == len(bias),
            "invalid network height")
    require(all(type(row) is list and 0 < len(row) <= 128 for row in matrix),
            "invalid wire row shape")
    weights = "[" + ", ".join(
        "[" + ", ".join(literal(token) for token in row) + "]"
        for row in matrix
    ) + "]"
    terms = "[" + ", ".join(literal(token) for token in bias) + "]"
    return ("{ weights := " + weights + ", bias := " + terms +
            ", activation := " + literal(raw["activation"]) + " }")


def wire_cell(raw: Any) -> str:
    require(type(raw) is dict and set(raw) == {"left", "right", "affines"},
            "invalid wire cell")
    affines = raw["affines"]
    require(type(affines) is list and 0 < len(affines) <= 128,
            "invalid wire output width")
    return ("{ left := " + literal(raw["left"]) +
            ", right := " + literal(raw["right"]) +
            ", affines := [" + ", ".join(wire_affine(v) for v in affines) + "] }")


def convert_one(name: str, raw: bytes) -> tuple[str, str]:
    obj = strict_json(raw)
    network = obj["network"]
    require(type(network) is dict and set(network) == {"layers"},
            "invalid wire network envelope")
    require(type(network["layers"]) is list and 0 < len(network["layers"]) <= 64,
            "invalid wire layers")
    cells = obj["atomic_cells"]
    require(type(cells) is list and 0 < len(cells) <= 4096,
            "invalid wire cells")
    digest = sha256(ordered_bytes(network)).hexdigest()
    require(digest == EXPECTED_NETWORK_DIGESTS[name] == obj["network_sha256"],
            "wire source network not pinned")
    wl = ",\n    ".join(wire_layer(x) for x in network["layers"])
    wc = ",\n    ".join(wire_cell(x) for x in cells)
    block = (
        f"-- original-canonical-json-sha256: {sha256(raw).hexdigest()}\n"
        f"-- pinned-network-sha256: {digest}\n"
        f"def {name}_wire : COE012Wire.WireCert :=\n"
        f"  {{ layers := [{wl}],\n    cells := [{wc}] }}\n"
        f"theorem {name}_wire_decoded :\n"
        f"    COE012Wire.decodeCert {name}_wire = some COE007.{name} := by decide +kernel\n"
        f"theorem {name}_wire_verified :\n"
        f"    COE012Wire.acceptWire {name}_wire = true := by decide +kernel\n"
        f"#print axioms COE012.{name}_wire_decoded\n"
        f"#print axioms COE012.{name}_wire_verified"
    )
    return block, sha256(raw).hexdigest()


def render(directory: Path) -> tuple[str, dict[str, Any]]:
    found = {p.name for p in directory.iterdir() if p.is_file()}
    require(found == FILENAMES,
            "wire manifest mismatch: must carry all pinned source certificates")
    blocks: list[str] = []
    fingerprints: dict[str, str] = {}
    for name in sorted(EXPECTED_NETWORK_DIGESTS):
        raw = (directory / (name + ".json")).read_bytes()
        block, digest = convert_one(name, raw)
        blocks.append(block)
        fingerprints[name] = digest
    result = (
        "import COE012Wire\n"
        "import GeneratedCertificateProofs\n\n"
        "/- COE-012: original STRING TOKENS; all conversion inside Lean. -/\n"
        "namespace COE012\n\n" +
        "\n\n".join(blocks) +
        "\n\nend COE012\n"
    )
    receipt = {
        "schema": "in-formation-space.coe012.wire-token-replay/0.1",
        "original_certificate_file_sha256": fingerprints,
        "model_count": len(blocks),
        "decoded_by": "COE012Wire.decodeCert",
        "matched_to": "COE007 original typed certificate",
        "status": "unverified-python-envelope-and-hash-kernel-checked-token-decoding",
    }
    return result, receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("certificates", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    content, receipt = render(args.certificates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(f"Transported {receipt['model_count']} original wire token sets, "
          "with no Python rational interpretation. Lean proof not asserted.")


if __name__ == "__main__":
    main()
