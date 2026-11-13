"""COE-007 adversarial certificates: change claims, never network source.

The adversarial generator itself does not claim verification. Every resulting
bundle retains the complete five-certificate source manifest and exact pinned
network descriptions. COEWireCheck must reject these through its own math.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

from emit_lean_certificates import FILENAMES, ordered_bytes, strict_json


def make_negatives(source: Path, target: Path) -> None:
    if {p.name for p in source.iterdir() if p.is_file()} != FILENAMES:
        raise ValueError("incomplete original fixture manifest")
    target.mkdir(parents=True, exist_ok=True)
    originals = {name: (source / name).read_bytes() for name in FILENAMES}

    def altered(case_name: str, filename: str, mutate) -> None:
        directory = target / case_name
        directory.mkdir(exist_ok=True)
        for other in FILENAMES:
            (directory / other).write_bytes(originals[other])
        obj = strict_json(originals[filename])
        copy = deepcopy(obj)
        mutate(copy)
        assert copy["network"] == obj["network"]
        assert copy["network_sha256"] == obj["network_sha256"]
        (directory / filename).write_bytes(ordered_bytes(copy) + b"\n")

    # A correct compact *output* atlas cannot be submitted as an activation
    # atlas: two hidden neurons switch at x=0 even though the output is x.
    altered("hidden-root", "relu_identity.json",
            lambda c: c.__setitem__("atomic_cells", deepcopy(c["semantic_atlas"])))
    # Forged affine law on a real interior interval.
    altered("wrong-slope", "triangular_bump.json",
            lambda c: c["atomic_cells"][1]["affines"][0].__setitem__(0, "2"))
    # A missing interval segment must not be accepted as full coverage.
    altered("cover-gap", "triangular_bump.json",
            lambda c: c["atomic_cells"][0].__setitem__("right", "-1"))
    print("Created hidden-root, wrong-slope and cover-gap negative bundles.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: make_lean_negative_certificates.py SOURCE TARGET")
    make_negatives(Path(sys.argv[1]), Path(sys.argv[2]))
