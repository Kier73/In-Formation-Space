"""Reconstruct an exported capsule under independently configured model pins."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform

import numpy as np

from .capsule import MAX_CAPSULE, verify_capsule
from .formation import FormationError


def replay(capsule: Path, policy_path: Path, *, expected_source: str, expected_generated: str) -> dict:
    # The small policy sidecar is supplied evidence, not receiver authority.
    if policy_path.stat().st_size > 4096 or capsule.stat().st_size > MAX_CAPSULE:
        raise FormationError("export file size exceeds replay budget")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or set(policy) != {
        "capsule_sha256", "capsule_bytes", "source_digest", "generated_digest"
    }:
        raise FormationError("unexpected export policy schema")
    if policy["source_digest"] != expected_source or policy["generated_digest"] != expected_generated:
        raise FormationError("export does not match independently configured model identities")
    report = verify_capsule(capsule.read_bytes(), policy)
    return {"schema": "ifs.independent-neural-export-replay.v1", "verification": report,
            "environment": {"python": platform.python_version(), "numpy": np.__version__,
                            "platform": platform.platform()},
            "scope": "independent execution environment; shared verifier implementation",
            "source_reobserved": False, "ecpu_transport_in_this_replay": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-generated", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.capsule, args.policy, expected_source=args.expected_source,
                    expected_generated=args.expected_generated)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["verification"]["status"],
                      "capsule_bytes": result["verification"]["capsule_bytes"],
                      "max_absolute_error": result["verification"]["max_absolute_error"],
                      "platform": result["environment"]["platform"]}))


if __name__ == "__main__":
    main()
