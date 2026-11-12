"""Generate the two-sided uncertainty clock calibration demonstration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from clock_calibration import build_interval_demonstration


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a calibration example with uncertainty intervals on both clocks."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_interval_demonstration()
    serialized = json.dumps(
        report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    print(json.dumps({
        "calibration_id": report["calibration"]["calibration_id"],
        "anchor_count": len(report["calibration"]["anchors"]),
        "feasible_region_vertices": len(report["calibration"]["feasible_region"]),
        "strict_relation": report["comparisons"]["strictly_ordered"]["relation"],
        "overlap_relation": report["comparisons"]["overlapping_uncertainty"]["relation"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
