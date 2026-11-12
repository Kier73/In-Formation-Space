"""Generate a reproducible certificate-backed authority revision example."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from authority_lineage import (
    create_ledger,
    decision_frontier,
    digest,
    issue_decision,
    propose_revision,
    validate_ledger,
)
from review_certificates import (
    build_review_certificate,
    record_review_certificate,
    resolve_reviewed_proposal,
    validate_review_certificates_in_ledger,
)


def _review_vote(seat: str, reviewer_ref: str, body: str, vote: str) -> dict[str, str]:
    ref = f"review://{seat.lower()}/proposal-000001"
    return {
        "seat": seat,
        "reviewer_ref": reviewer_ref,
        "vote": vote,
        "rationale": body,
        "review_ref": ref,
        "review_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def build_demonstration() -> dict[str, Any]:
    event = {"kind": "resolver", "logical_time": 29}
    ledger = create_ledger("authority-review-certificate-demo", created_by="demo")
    ledger, initial_id = issue_decision(
        ledger,
        event_key=event,
        status="AUTHORIZED",
        evidence_set_digest="1" * 64,
        policy_digest="2" * 64,
        representative_ref="evidence://initial-resolver-hit",
        issued_by="authority-original",
        rationale="Initial decision recorded before late evidence.",
    )
    ledger, proposal_id = propose_revision(
        ledger,
        event_key=event,
        base_decision_ids=[initial_id],
        evidence_refs=[{
            "ref": "evidence://late-review-material",
            "sha256": "3" * 64,
        }],
        reason="A late evidence item requests review of the original authority decision.",
        proposed_by="agent://proposal-author",
    )
    review_bodies = {
        "review://r01/proposal-000001": (
            "Independent reviewer one checked the late evidence reference and approves review."
        ),
        "review://r02/proposal-000001": (
            "Independent reviewer two independently checked the cited material and approves review."
        ),
    }
    certificate = build_review_certificate(
        ledger,
        proposal_id,
        policy_name="independent_two_of_two",
        votes=[
            _review_vote(
                "R01", "agent://reviewer-one",
                review_bodies["review://r01/proposal-000001"], "APPROVE",
            ),
            _review_vote(
                "R02", "agent://reviewer-two",
                review_bodies["review://r02/proposal-000001"], "APPROVE",
            ),
        ],
    )
    ledger = record_review_certificate(
        ledger, certificate, recorded_by="agent://review-coordinator"
    )
    ledger = resolve_reviewed_proposal(
        ledger,
        proposal_id,
        rationale="The independent-two-of-two certificate accepts the revision proposal.",
        resolved_by="agent://review-coordinator",
    )
    ledger, revised_id = issue_decision(
        ledger,
        event_key=event,
        status="CONFLICT",
        evidence_set_digest="4" * 64,
        policy_digest="5" * 64,
        issued_by="agent://authority-after-review",
        rationale="The accepted proposal permits a new conflicting decision.",
        proposal_id=proposal_id,
    )
    validate_ledger(ledger)
    validate_review_certificates_in_ledger(ledger)

    core = {
        "format": "in-formation.authority-review-certificate-example",
        "schema": "in-formation.authority-review-certificate-example/0.1",
        "event_key": event,
        "initial_decision_id": initial_id,
        "proposal_id": proposal_id,
        "certificate": certificate,
        "review_artifacts": [
            {"ref": ref, "content": body, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
            for ref, body in sorted(review_bodies.items())
        ],
        "resolution": next(
            entry["payload"] for entry in ledger["entries"]
            if entry["entry_type"] == "proposal_resolved"
            and entry["payload"]["proposal_id"] == proposal_id
        ),
        "revised_decision_id": revised_id,
        "frontier": decision_frontier(ledger, event),
        "ledger": ledger,
        "interpretation": (
            "The review certificate binds two explicit reviewer receipts to one proposal, "
            "the exact prior decision frontier, and a frozen policy definition. The lineage "
            "resolution cites the certificate digest. Reviewer references remain unauthenticated labels."
        ),
    }
    return {**core, "example_digest": digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a certificate-backed authority revision example."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    example = build_demonstration()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(example, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "proposal_id": example["proposal_id"],
        "certificate_digest": example["certificate"]["certificate_digest"],
        "review_outcome": example["certificate"]["evaluation"]["outcome"],
        "resolution_outcome": example["resolution"]["outcome"],
        "revised_decision_id": example["revised_decision_id"],
        "frontier": example["frontier"]["status"],
        "ledger_digest": example["ledger"]["ledger_digest"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
