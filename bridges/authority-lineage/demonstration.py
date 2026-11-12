"""Build a branching-and-merge authority lineage example."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from authority_lineage import (
    create_ledger,
    decision_frontier,
    digest,
    issue_decision,
    propose_revision,
    resolve_proposal,
    validate_ledger,
)


def build_demonstration() -> dict[str, Any]:
    event = {"kind": "resolver", "logical_time": 17}
    ledger = create_ledger("authority-lineage-demo", created_by="demo")
    ledger, initial_id = issue_decision(
        ledger,
        event_key=event,
        status="AUTHORIZED",
        evidence_set_digest="1" * 64,
        policy_digest="2" * 64,
        representative_ref="evidence://original-observation",
        issued_by="authority-original",
        rationale="Initial event decision.",
    )

    ledger, proposal_a = propose_revision(
        ledger,
        event_key=event,
        base_decision_ids=[initial_id],
        evidence_refs=[{"ref": "evidence://late-observation", "sha256": "3" * 64}],
        reason="Late observation proposes that the event should be treated as conflicting.",
        proposed_by="reviewer-A",
    )
    ledger, proposal_b = propose_revision(
        ledger,
        event_key=event,
        base_decision_ids=[initial_id],
        evidence_refs=[{"ref": "evidence://source-provenance-review", "sha256": "4" * 64}],
        reason="A separate review questions whether the evidence was sufficient.",
        proposed_by="reviewer-B",
    )
    ledger = resolve_proposal(
        ledger, proposal_a, outcome="ACCEPTED",
        rationale="The late observation is accepted for a competing review path.",
        resolved_by="review-chair-A",
    )
    ledger = resolve_proposal(
        ledger, proposal_b, outcome="ACCEPTED",
        rationale="The provenance review is accepted for a separate review path.",
        resolved_by="review-chair-B",
    )

    ledger, branch_a = issue_decision(
        ledger,
        event_key=event,
        status="CONFLICT",
        evidence_set_digest="5" * 64,
        policy_digest="2" * 64,
        representative_ref=None,
        issued_by="authority-A",
        rationale="Branch A concludes that the evidence conflicts.",
        proposal_id=proposal_a,
    )
    ledger, branch_b = issue_decision(
        ledger,
        event_key=event,
        status="REFUSED",
        evidence_set_digest="6" * 64,
        policy_digest="2" * 64,
        representative_ref=None,
        issued_by="authority-B",
        rationale="Branch B concludes that the available evidence is insufficient.",
        proposal_id=proposal_b,
    )
    fork_frontier = decision_frontier(ledger, event)

    ledger, merge_proposal = propose_revision(
        ledger,
        event_key=event,
        base_decision_ids=fork_frontier["decision_ids"],
        evidence_refs=[{"ref": "evidence://joint-adjudication", "sha256": "7" * 64}],
        reason="A joint adjudication explicitly reconciles both reviewed branches.",
        proposed_by="review-committee",
    )
    ledger = resolve_proposal(
        ledger, merge_proposal, outcome="ACCEPTED",
        rationale="The committee may issue one decision superseding both branches.",
        resolved_by="review-chair",
    )
    ledger, merged_id = issue_decision(
        ledger,
        event_key=event,
        status="AUTHORIZED",
        evidence_set_digest="8" * 64,
        policy_digest="9" * 64,
        representative_ref="evidence://joint-adjudication-representative",
        issued_by="review-chair",
        rationale="The merged review issues a new authorized decision.",
        proposal_id=merge_proposal,
    )
    final_frontier = decision_frontier(ledger, event)
    validate_ledger(ledger)
    core = {
        "format": "in-formation.authority-lineage-example",
        "schema": "in-formation.authority-lineage-example/0.1",
        "event_key": event,
        "initial_decision_id": initial_id,
        "branch_decision_ids": [branch_a, branch_b],
        "frontier_before_merge": fork_frontier,
        "merge_decision_id": merged_id,
        "frontier_after_merge": final_frontier,
        "ledger": ledger,
        "interpretation": (
            "Both revision branches remain in the immutable history. The merged decision "
            "supersedes both branches and becomes the single derived frontier tip."
        ),
    }
    return {**core, "example_digest": digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an authority-lineage fork/merge example.")
    parser.add_argument("--output", metavar="JSON", help="write the example JSON (default: stdout)")
    args = parser.parse_args(argv)
    try:
        example = build_demonstration()
        rendered = json.dumps(example, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
