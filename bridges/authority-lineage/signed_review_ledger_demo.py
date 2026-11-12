"""End-to-end demonstration of signed review receipts anchored in authority lineage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from authority_lineage import (
    create_ledger,
    decision_frontier,
    digest,
    issue_decision,
    propose_revision,
    validate_ledger,
)
from review_certificates import build_review_certificate, record_review_certificate
from signed_review_receipts import (
    build_signed_review_bundle,
    build_trust_store,
    record_signed_review_bundle,
    resolve_signed_reviewed_proposal,
    sign_review_vote,
    validate_signed_review_bundles_in_ledger,
)


def build_demonstration() -> dict[str, Any]:
    event = {"kind": "resolver", "logical_time": 91}
    ledger = create_ledger("signed-authority-review-ledger-demo", created_by="demo")
    ledger, initial_id = issue_decision(
        ledger,
        event_key=event,
        status="AUTHORIZED",
        evidence_set_digest="1" * 64,
        policy_digest="2" * 64,
        representative_ref="evidence://initial-resolver",
        issued_by="agent://initial-authority",
        rationale="Initial authority decision before the later evidence arrived.",
    )
    ledger, proposal_id = propose_revision(
        ledger,
        event_key=event,
        base_decision_ids=[initial_id],
        evidence_refs=[{
            "ref": "evidence://late-observation",
            "sha256": "3" * 64,
        }],
        reason="A late observation requests review of the current authority decision.",
        proposed_by="agent://proposal-author",
    )
    review_artifacts = {
        "review://r01/91": (
            "Reviewer one independently checks the late observation and supports the revision."
        ),
        "review://r02/91": (
            "Reviewer two independently checks the same cited observation and supports the revision."
        ),
    }
    votes = [
        {
            "seat": "R01",
            "reviewer_ref": "agent://reviewer-one",
            "vote": "APPROVE",
            "rationale": "Independent reviewer one approves this exact proposal and base.",
            "review_ref": "review://r01/91",
            "review_sha256": hashlib.sha256(
                review_artifacts["review://r01/91"].encode("utf-8")
            ).hexdigest(),
        },
        {
            "seat": "R02",
            "reviewer_ref": "agent://reviewer-two",
            "vote": "APPROVE",
            "rationale": "Independent reviewer two approves this exact proposal and base.",
            "review_ref": "review://r02/91",
            "review_sha256": hashlib.sha256(
                review_artifacts["review://r02/91"].encode("utf-8")
            ).hexdigest(),
        },
    ]
    certificate = build_review_certificate(
        ledger,
        proposal_id,
        policy_name="independent_two_of_two",
        votes=votes,
    )
    ledger = record_review_certificate(
        ledger, certificate, recorded_by="agent://review-coordinator"
    )

    # Demo-only ephemeral keys. A deployment must provision its own trusted
    # key mapping and keep private keys outside this repository/artifact.
    private_keys = {
        vote["reviewer_ref"]: Ed25519PrivateKey.generate()
        for vote in votes
    }
    trust_store = build_trust_store([
        {
            "seat": vote["seat"],
            "principal": vote["reviewer_ref"],
            "public_key": private_keys[vote["reviewer_ref"]].public_key(),
        }
        for vote in votes
    ])
    envelopes = [
        sign_review_vote(certificate, vote, private_keys[vote["reviewer_ref"]])
        for vote in votes
    ]
    bundle = build_signed_review_bundle(
        certificate,
        envelopes,
        trust_store,
        review_artifacts=review_artifacts,
    )
    ledger = record_signed_review_bundle(
        ledger,
        proposal_id,
        bundle,
        trust_store,
        recorded_by="agent://receipt-recorder",
        review_artifacts=review_artifacts,
    )
    ledger = resolve_signed_reviewed_proposal(
        ledger,
        proposal_id,
        trusted_trust_store=trust_store,
        rationale="The exact two-reviewer signature bundle satisfies the review policy.",
        resolved_by="agent://review-coordinator",
        review_artifacts=review_artifacts,
    )
    ledger, revised_id = issue_decision(
        ledger,
        event_key=event,
        status="CONFLICT",
        evidence_set_digest="4" * 64,
        policy_digest="5" * 64,
        issued_by="agent://authority-after-review",
        rationale="The signed and accepted proposal authorizes this successor decision.",
        proposal_id=proposal_id,
    )
    validate_ledger(ledger)
    validate_signed_review_bundles_in_ledger(
        ledger,
        trusted_store_digests={proposal_id: digest(trust_store)},
        review_artifacts_by_proposal={proposal_id: review_artifacts},
    )
    resolution = next(
        entry["payload"] for entry in ledger["entries"]
        if entry["entry_type"] == "proposal_resolved"
        and entry["payload"]["proposal_id"] == proposal_id
    )
    signed_entry = next(
        entry for entry in ledger["entries"]
        if entry["entry_type"] == "proposal_review_signed"
    )
    core = {
        "format": "in-formation.signed-review-ledger-example",
        "schema": "in-formation.signed-review-ledger-example/0.1",
        "key_provisioning": (
            "Ephemeral demonstration keys only. This example proves possession "
            "within this run but does not authenticate persistent agent identities."
        ),
        "private_keys_included": False,
        "event_key": event,
        "initial_decision_id": initial_id,
        "proposal_id": proposal_id,
        "certificate": certificate,
        "signed_review_bundle": bundle,
        "trust_store": trust_store,
        "review_artifacts": [
            {"ref": ref, "content": body, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
            for ref, body in sorted(review_artifacts.items())
        ],
        "signed_ledger_entry": signed_entry,
        "resolution": resolution,
        "revised_decision_id": revised_id,
        "frontier": decision_frontier(ledger, event),
        "ledger": ledger,
        "trust_store_digest": digest(trust_store),
        "verification": {
            "signature_count": len(bundle["signed_review_votes"]),
            "all_review_votes_signed": (
                len(bundle["signed_review_votes"]) == len(certificate["votes"])
            ),
            "review_artifacts_verified": bundle["review_artifacts_verified"],
            "resolution_cites_certificate": (
                resolution["review_certificate_digest"] == certificate["certificate_digest"]
            ),
            "resolution_cites_signed_bundle": (
                resolution["signed_review_bundle_digest"] == bundle["bundle_digest"]
            ),
            "ledger_digest": ledger["ledger_digest"],
            "status": "VERIFIED_WITH_EPHEMERAL_DEMO_TRUST_STORE",
        },
    }
    return {**core, "example_digest": digest(core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an authority lineage with embedded signed reviewer receipts."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    example = build_demonstration()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(example, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(example["verification"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
