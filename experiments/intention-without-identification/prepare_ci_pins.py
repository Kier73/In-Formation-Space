"""CI-only test pin extraction from ALREADY workflow-audited GCI-005 artifacts.

This does not create an independent trust root. Real deployments must source
pinned CA/certificate identity from a separate trusted authority.
"""
import argparse
import json
from pathlib import Path

import native_gci_lineage as b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    d = args.directory
    if (d / "gci003-private.json").exists():
        raise RuntimeError("private phase entered phase-blind evidence verifier")
    blind = b.h.blind_audit(d)
    archived = json.loads((d / "gci005-blind-audit.json").read_text(encoding="utf8"))
    if blind != archived:
        raise RuntimeError("independent GCI-005 auditor report changed")
    binding, public, plan = b.h.get_binding(d)
    report = json.loads((d / "gci005-quorum.json").read_text(encoding="utf8"))
    pins = b.make_test_pins(report, binding, public, plan)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(pins.as_dict(), sort_keys=True) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
