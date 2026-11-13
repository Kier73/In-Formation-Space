"""Produce a portable, deterministic collection of COE-002 claims."""
from __future__ import annotations
import argparse
from pathlib import Path
from certificate_producer import canonical_bytes, produce
from coe_fixtures import fixtures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, layers in fixtures().items():
        cert = produce(layers)
        (args.output_dir / f"{name}.json").write_bytes(canonical_bytes(cert) + b"\n")
        print(name, cert["network_sha256"], cert["semantic_sha256"],
              len(cert["atomic_cells"]), len(cert["semantic_atlas"]))


if __name__ == "__main__":
    main()
