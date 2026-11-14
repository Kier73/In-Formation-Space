"""Emit portable SNC-001 certificates for separately scheduled verification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from compiler import compile_semantics
from certificate_producer import canonical_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    examples = json.loads((Path(__file__).parent / "examples.json").read_text())
    dest = args.output_dir
    (dest / "capsules").mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "schema": "in-formation-space.snc001.producer-report/0.1",
        "status": "unverified-producer-claims",
        "examples": {},
    }
    for name, source in sorted(examples.items()):
        capsule = compile_semantics(source)
        path = dest / "capsules" / (name + ".json")
        path.write_bytes(canonical_bytes(capsule) + b"\n")
        report["examples"][name] = {
            "source_semantic_sha256": capsule["source_semantic_sha256"],
            "network_sha256": capsule["generated_certificate"]["network_sha256"],
            "hidden_neurons": len(source) + 1,
        }
    (dest / "producer-report.json").write_bytes(canonical_bytes(report) + b"\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
