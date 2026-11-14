"""Receive SNC-001 capsules without importing their generator or its atlas builder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from verifier import verify_capsule
from independent_certificate_checker import CertificateError, hash_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsules", type=Path, required=True)
    args = parser.parse_args()
    # These checked-in descriptions are receiver policy, not untrusted
    # statements taken from the transferred capsules or producer report.
    source_file = Path(__file__).parent / "examples.json"
    source = json.loads(source_file.read_text())
    expected_names = {name + ".json" for name in source}
    actual_names = {p.name for p in args.capsules.iterdir() if p.is_file()}
    if actual_names != expected_names:
        raise CertificateError("capsule manifest incomplete or unexpected")
    results = {}
    for name in sorted(source):
        results[name] = verify_capsule(
            (args.capsules / (name + ".json")).read_bytes(),
            expected_source_sha256=hash_bytes(source[name]),
        )
    report = {
        "schema": "in-formation-space.snc001.receiver-report/0.1",
        "status": "all-five-verified",
        "cases": results,
        "ground_admitted": False,
        "numeric_execution_verified": False,
        "trust": "receiver-owned checked-in sources, not external authenticity",
    }
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
