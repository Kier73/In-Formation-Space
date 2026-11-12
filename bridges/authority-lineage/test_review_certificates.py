import copy
import json
import unittest
from pathlib import Path

import jsonschema

from authority_lineage import (
    create_ledger,
    decision_frontier,
    event_entries,
    issue_decision,
    propose_revision,
    resolve_proposal,
    validate_ledger,
)
from review_certificates import (
    ReviewCertificateError,
    build_review_certificate,
    record_review_certificate,
    resolve_reviewed_proposal,
    validate_review_certificate,
    validate_review_certificates_in_ledger,
)

EVENT = {"kind": "resolver", "logical_time": 21}
POLICY_DIGEST = "d" * 64


def initial_proposal():
    ledger = create_ledger("certified-authority", created_by="test-suite")
    ledger, initial_id = issue_decision(
        ledger,
        event_key=EVENT,
        status="AUTHORIZED",
        evidence_set_digest="a" * 64,
        policy_digest=POLICY_DIGEST,
        representative_ref="evidence://initial",
        issued_by="authority-original",
        rationale="Initial authority decision.",
    )
    ledger, proposal_id = propose_revision(
        ledger,
        event_key=EVENT,
        base_decision_ids=[initial_id],
        evidence_refs=[{"ref": "evidence://late-source", "sha256": "b" * 64}],
        reason="A late source requests a reviewed revision.",
        proposed_by="agent://proposer",
    )
    return ledger, initial_id, proposal_id


def vote(seat, reviewer_ref, state, suffix):
    return {
        "seat": seat,
        "reviewer_ref": reviewer_ref,
        "vote": state,
        "rationale": f"{seat} reviewed the cited proposal and records {state}.",
        "review_ref": f"review://{suffix}",
        "review_sha256": suffix[0].lower() * 64,
    }


class ReviewCertificateTests(unittest.TestCase):
    def test_certificate_is_recorded_then_resolves_and_authorizes_revision(self):
        ledger, initial_id, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "APPROVE", "Two"),
            ],
        )
        self.assertEqual(certificate["evaluation"]["outcome"], "ACCEPTED")
        self.assertEqual(certificate["evaluation"]["approval_count"], 2)
        self.assertEqual(certificate["evaluation"]["eligible_reviewers"], ["R01", "R02"])

        ledger = record_review_certificate(
            ledger, certificate, recorded_by="review-coordinator"
        )
        validate_review_certificates_in_ledger(ledger)
        ledger = resolve_reviewed_proposal(
            ledger,
            proposal_id,
            rationale="The independently reviewed certificate accepts this proposal.",
            resolved_by="review-coordinator",
        )
        resolution = next(
            item["payload"] for item in ledger["entries"]
            if item["entry_type"] == "proposal_resolved"
        )
        self.assertEqual(resolution["outcome"], "ACCEPTED")
        self.assertEqual(
            resolution["review_certificate_digest"], certificate["certificate_digest"]
        )

        ledger, revised_id = issue_decision(
            ledger,
            event_key=EVENT,
            status="CONFLICT",
            evidence_set_digest="c" * 64,
            policy_digest=POLICY_DIGEST,
            issued_by="authority-after-review",
            rationale="The certified review authorizes a superseding decision.",
            proposal_id=proposal_id,
        )
        self.assertEqual(
            decision_frontier(ledger, EVENT)["decision_ids"], [revised_id]
        )
        self.assertEqual(
            [item["entry_type"] for item in event_entries(ledger, EVENT)].count(
                "proposal_review_certified"
            ),
            1,
        )
        validate_ledger(ledger)
        validate_review_certificates_in_ledger(ledger)

    def test_proposer_vote_is_retained_but_not_counted_by_independent_policy(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R00", "agent://proposer", "REJECT", "Prop"),
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "APPROVE", "Two"),
            ],
        )
        self.assertEqual(certificate["evaluation"]["outcome"], "ACCEPTED")
        self.assertFalse(certificate["evaluation"]["proposer_vote_counted"])
        self.assertEqual(certificate["evaluation"]["approval_count"], 2)
        self.assertEqual(certificate["evaluation"]["rejection_count"], 0)
        validate_review_certificate(ledger, certificate)

    def test_abstention_counts_as_participation_not_approval(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "ABSTAIN", "Two"),
            ],
        )
        self.assertEqual(certificate["evaluation"]["outcome"], "INCONCLUSIVE")
        self.assertEqual(certificate["evaluation"]["abstention_count"], 1)
        self.assertEqual(certificate["evaluation"]["approval_count"], 1)

    def test_conflicting_thresholds_remain_inconclusive(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="two_approval_veto",
            votes=[
                vote("R00", "agent://proposer", "APPROVE", "Prop"),
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "REJECT", "Two"),
            ],
        )
        self.assertEqual(certificate["evaluation"]["outcome"], "INCONCLUSIVE")
        self.assertTrue(certificate["evaluation"]["conflicting_thresholds"])

    def test_missing_reviewers_are_absent_not_fabricated(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[vote("R01", "agent://reviewer-one", "APPROVE", "One")],
        )
        self.assertEqual(certificate["evaluation"]["seat_pattern"], [
            "ABSENT", "APPROVE", "ABSENT"
        ])
        self.assertEqual(certificate["evaluation"]["outcome"], "INCONCLUSIVE")
        self.assertEqual(len(certificate["votes"]), 1)

    def test_duplicate_seat_is_rejected(self):
        ledger, _, proposal_id = initial_proposal()
        with self.assertRaises(ReviewCertificateError):
            build_review_certificate(
                ledger,
                proposal_id,
                policy_name="independent_two_of_two",
                votes=[
                    vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                    vote("R01", "agent://reviewer-one-alt", "APPROVE", "Alt"),
                ],
            )

    def test_duplicate_reviewer_reference_across_seats_is_rejected(self):
        ledger, _, proposal_id = initial_proposal()
        with self.assertRaises(ReviewCertificateError):
            build_review_certificate(
                ledger,
                proposal_id,
                policy_name="independent_two_of_two",
                votes=[
                    vote("R01", "agent://same-reviewer", "APPROVE", "One"),
                    vote("R02", "agent://same-reviewer", "APPROVE", "Two"),
                ],
            )

    def test_proposer_seat_must_match_proposal_actor(self):
        ledger, _, proposal_id = initial_proposal()
        with self.assertRaises(ReviewCertificateError):
            build_review_certificate(
                ledger,
                proposal_id,
                policy_name="single_approval_permissive",
                votes=[vote("R00", "agent://impostor", "APPROVE", "Prop")],
            )

    def test_review_artifact_digest_must_be_sha256(self):
        ledger, _, proposal_id = initial_proposal()
        invalid = vote("R01", "agent://reviewer-one", "APPROVE", "One")
        invalid["review_sha256"] = "not-a-digest"
        with self.assertRaises(ValueError):
            build_review_certificate(
                ledger,
                proposal_id,
                policy_name="independent_two_of_two",
                votes=[invalid],
            )

    def test_certificate_detects_tampered_votes_even_after_digest_recomputed(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "APPROVE", "Two"),
            ],
        )
        altered = copy.deepcopy(certificate)
        altered["votes"][1]["vote"] = "REJECT"
        core = {key: value for key, value in altered.items() if key != "certificate_digest"}
        from authority_lineage import digest
        altered["certificate_digest"] = digest(core)
        with self.assertRaises(ReviewCertificateError):
            validate_review_certificate(ledger, altered)

    def test_certificate_is_bound_to_proposal_and_base_decision_digests(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "APPROVE", "Two"),
            ],
        )
        altered = copy.deepcopy(certificate)
        altered["base_decision_digests"]["decision-000001"] = "e" * 64
        with self.assertRaises(ReviewCertificateError):
            validate_review_certificate(ledger, altered)

    def test_resolution_cannot_disagree_with_recorded_certificate(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "APPROVE", "Two"),
            ],
        )
        ledger = record_review_certificate(ledger, certificate, recorded_by="review-coordinator")
        with self.assertRaises(ValueError):
            resolve_proposal(
                ledger,
                proposal_id,
                outcome="REJECTED",
                rationale="Contradictory manual result.",
                resolved_by="manual-reviewer",
            )

    def test_certificate_record_after_resolution_is_rejected(self):
        ledger, _, proposal_id = initial_proposal()
        ledger = resolve_proposal(
            ledger,
            proposal_id,
            outcome="REJECTED",
            rationale="Resolved without a certificate.",
            resolved_by="manual-reviewer",
        )
        with self.assertRaises(ReviewCertificateError):
            build_review_certificate(
                ledger,
                proposal_id,
                policy_name="independent_two_of_two",
                votes=[],
            )

    def test_certificate_on_changed_frontier_resolves_stale(self):
        ledger, initial_id, proposal_id = initial_proposal()
        ledger, competing_id = propose_revision(
            ledger,
            event_key=EVENT,
            base_decision_ids=[initial_id],
            evidence_refs=[{"ref": "evidence://competing", "sha256": "f" * 64}],
            reason="A competing proposal may advance first.",
            proposed_by="agent://competitor",
        )
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "APPROVE", "Two"),
            ],
        )
        ledger = record_review_certificate(ledger, certificate, recorded_by="review-coordinator")
        ledger = resolve_proposal(
            ledger,
            competing_id,
            outcome="ACCEPTED",
            rationale="The competing proposal advances.",
            resolved_by="independent-chair",
        )
        ledger, _ = issue_decision(
            ledger,
            event_key=EVENT,
            status="CONFLICT",
            evidence_set_digest="9" * 64,
            policy_digest=POLICY_DIGEST,
            issued_by="independent-chair",
            rationale="Competing branch supersedes the original decision.",
            proposal_id=competing_id,
        )
        ledger = resolve_reviewed_proposal(
            ledger,
            proposal_id,
            rationale="The certificate is retained but its base is stale.",
            resolved_by="review-coordinator",
        )
        resolution = [
            item["payload"] for item in ledger["entries"]
            if item["entry_type"] == "proposal_resolved"
            and item["payload"]["proposal_id"] == proposal_id
        ][0]
        self.assertEqual(resolution["outcome"], "STALE")
        self.assertEqual(
            resolution["review_certificate_digest"], certificate["certificate_digest"]
        )
        validate_review_certificates_in_ledger(ledger)

    def test_schema_accepts_certificate_bearing_ledger(self):
        ledger, _, proposal_id = initial_proposal()
        certificate = build_review_certificate(
            ledger,
            proposal_id,
            policy_name="independent_two_of_two",
            votes=[
                vote("R01", "agent://reviewer-one", "APPROVE", "One"),
                vote("R02", "agent://reviewer-two", "APPROVE", "Two"),
            ],
        )
        ledger = record_review_certificate(ledger, certificate, recorded_by="review-coordinator")
        ledger = resolve_reviewed_proposal(
            ledger,
            proposal_id,
            rationale="Certificate-backed accepted review.",
            resolved_by="review-coordinator",
        )
        schema_path = Path(__file__).with_name("authority-lineage.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=ledger, schema=schema)
        validate_ledger(ledger)
        validate_review_certificates_in_ledger(ledger)


if __name__ == "__main__":
    unittest.main()
