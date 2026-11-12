"""Generate an exhaustive, probability-free reviewer adjudication state space."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from review_policy_space import (
    POLICIES,
    PROPOSER,
    REVIEWERS,
    REVIEW_STATES,
    enumerate_review_space,
    summarize_review_space,
    validate_review_space,
)

EXPERIMENT_ID = "authority-adjudication-review-space-v1"
SCHEMA = "in-formation.authority-adjudication-review-space/0.1"


def canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _report_core() -> dict[str, Any]:
    records = enumerate_review_space()
    summary = summarize_review_space(records)
    validate_review_space(records, summary)
    return {
        "format": "in-formation.authority-adjudication-review-space",
        "schema": SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "state_model": {
            "reviewers": list(REVIEWERS),
            "proposer": PROPOSER,
            "review_states": list(REVIEW_STATES),
            "pattern_count": len(records),
            "probability_assignment": None,
        },
        "policy_ids": list(POLICIES),
        "policy_summary": summary,
        "pattern_records": records,
        "interpretation_limits": [
            "This is an exhaustive finite state enumeration for three named reviewer roles and four participation/vote states.",
            "Every reviewer-state pattern is listed once; no vote probabilities or reviewer reliability estimates are assigned.",
            "Reviewer identities are symbolic role labels, not authenticated people or cryptographic signers.",
            "Approval and rejection thresholds are candidate adjudication rules, not calibrated authority policies.",
            "This state space does not model correlated reviewers, private information, deliberation, changing votes, or adversarial collusion.",
            "An INCONCLUSIVE result is a visible lack of decision, not a hidden approval or rejection.",
        ],
    }


def build_report() -> dict[str, Any]:
    core = _report_core()
    report = {**core, "report_digest": digest(core)}
    validate_report(report)
    return report


def validate_report(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping):
        raise TypeError("adjudication report must be a mapping")
    supplied = dict(report)
    supplied_digest = supplied.pop("report_digest", None)
    if supplied_digest != digest(supplied):
        raise ValueError("adjudication report digest mismatch")
    if supplied != _report_core():
        raise ValueError("adjudication report differs from exhaustive reconstruction")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enumerate finite reviewer voting, abstention, and adjudication policies."
    )
    parser.add_argument("--output-dir", required=True, metavar="DIR")
    args = parser.parse_args(argv)
    try:
        report = build_report()
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        summary_core = {
            "format": "in-formation.authority-adjudication-review-space-summary",
            "schema": SCHEMA + "/summary",
            "experiment_id": EXPERIMENT_ID,
            "pattern_count": report["state_model"]["pattern_count"],
            "policy_count": len(report["policy_ids"]),
            "policy_summary": report["policy_summary"]["policies"],
            "report_digest": report["report_digest"],
            "interpretation_limits": report["interpretation_limits"],
        }
        summary = {**summary_core, "summary_digest": digest(summary_core)}
        (output / "adjudication-space.json").write_text(
            json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "adjudication-space-summary.json").write_text(
            json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
        return 2
    print(json.dumps({
        "experiment_id": EXPERIMENT_ID,
        "pattern_count": report["state_model"]["pattern_count"],
        "policy_count": len(report["policy_ids"]),
        "report_digest": report["report_digest"],
        "output_dir": str(output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
