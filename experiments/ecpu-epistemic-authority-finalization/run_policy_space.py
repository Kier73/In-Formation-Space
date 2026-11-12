"""Generate the exhaustive four-source authority-policy state space."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from policy_space import (
    POLICY_NAMES,
    enumerate_evidence_space,
    summarize_policy_space,
    validate_policy_space,
)

EXPERIMENT_ID = "ecpu-epistemic-authority-policy-space-v1"
SCHEMA = "in-formation.ecpu-epistemic-authority-policy-space/0.1"


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def build_report() -> dict[str, Any]:
    records = enumerate_evidence_space()
    summary = summarize_policy_space(records)
    validate_policy_space(records, summary)
    core = {
        "format": "in-formation.ecpu-epistemic-authority-policy-space",
        "schema": SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "pattern_model": {
            "source_count": 4,
            "source_ids": summary["source_ids"],
            "source_states": summary["source_states"],
            "quorum": summary["quorum"],
            "pattern_count": summary["pattern_count"],
            "probability_assignment": None,
        },
        "policy_names": list(POLICY_NAMES),
        "policy_summary": summary,
        "pattern_records": records,
        "interpretation_limits": [
            "This is an exhaustive finite state enumeration for four sources and binary HIT/MISS outcomes plus absence.",
            "It assigns no probabilities to patterns; aggregate counts are not estimates of real-world frequency or reliability.",
            "The runtime strict/permissive policies are faithful abstractions of the inspected pinned E-CPU consensus decision rule, without transport or VM costs.",
            "Source equivocation, cryptographic identity, source dependence, calibration, and cross-time revision are not represented in this 3-state-per-source product.",
            "Alternative policies are candidate decision rules for comparison, not approved or calibrated authority policy.",
        ],
    }
    report = {**core, "report_digest": digest(core)}
    validate_report(report)
    return report


def validate_report(report: dict[str, Any]) -> None:
    supplied = dict(report)
    supplied_digest = supplied.pop("report_digest", None)
    if supplied_digest != digest(supplied):
        raise ValueError("policy-space report digest mismatch")
    summary = supplied.get("policy_summary")
    records = supplied.get("pattern_records")
    if not isinstance(summary, dict) or not isinstance(records, list):
        raise ValueError("policy-space report lacks summary or pattern records")
    validate_policy_space(records, summary)
    rebuilt = build_report_without_validation()
    if rebuilt != dict(report):
        raise ValueError("policy-space report differs from exhaustive reconstruction")


def build_report_without_validation() -> dict[str, Any]:
    records = enumerate_evidence_space()
    summary = summarize_policy_space(records)
    core = {
        "format": "in-formation.ecpu-epistemic-authority-policy-space",
        "schema": SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "pattern_model": {
            "source_count": 4,
            "source_ids": summary["source_ids"],
            "source_states": summary["source_states"],
            "quorum": summary["quorum"],
            "pattern_count": summary["pattern_count"],
            "probability_assignment": None,
        },
        "policy_names": list(POLICY_NAMES),
        "policy_summary": summary,
        "pattern_records": records,
        "interpretation_limits": [
            "This is an exhaustive finite state enumeration for four sources and binary HIT/MISS outcomes plus absence.",
            "It assigns no probabilities to patterns; aggregate counts are not estimates of real-world frequency or reliability.",
            "The runtime strict/permissive policies are faithful abstractions of the inspected pinned E-CPU consensus decision rule, without transport or VM costs.",
            "Source equivocation, cryptographic identity, source dependence, calibration, and cross-time revision are not represented in this 3-state-per-source product.",
            "Alternative policies are candidate decision rules for comparison, not approved or calibrated authority policy.",
        ],
    }
    return {**core, "report_digest": digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enumerate the finite four-source evidence and authority policy space."
    )
    parser.add_argument("--output-dir", required=True, metavar="DIR")
    args = parser.parse_args(argv)
    try:
        report = build_report()
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        summary_core = {
            "format": "in-formation.ecpu-epistemic-authority-policy-space-summary",
            "schema": SCHEMA + "/summary",
            "experiment_id": EXPERIMENT_ID,
            "pattern_count": report["pattern_model"]["pattern_count"],
            "policy_count": len(report["policy_names"]),
            "policy_summary": report["policy_summary"]["policies"],
            "report_digest": report["report_digest"],
        }
        summary = {**summary_core, "summary_digest": digest(summary_core)}
        (output / "policy-space.json").write_text(
            json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "policy-space-summary.json").write_text(
            json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
        return 2
    print(json.dumps({
        "experiment_id": EXPERIMENT_ID,
        "pattern_count": report["pattern_model"]["pattern_count"],
        "policy_count": len(report["policy_names"]),
        "report_digest": report["report_digest"],
        "output_dir": str(output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
