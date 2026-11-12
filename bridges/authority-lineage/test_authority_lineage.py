import copy
import json
import unittest
from pathlib import Path

import jsonschema

from authority_lineage import (
    create_ledger,
    decision_frontier,
    decision_history,
    event_entries,
    issue_decision,
    propose_revision,
    resolve_proposal,
    validate_ledger,
)
from demonstration import build_demonstration


EVENT = {"kind": "resolver", "logical_time": 5}
OTHER_EVENT = {"kind": "resolver", "logical_time": 6}
EVIDENCE_1 = [{"ref": "artifact://observation-1", "sha256": "a" * 64}]
EVIDENCE_2 = [{"ref": "artifact://observation-2", "sha256": "b" * 64}]
EVIDENCE_MERGE = [
    {"ref": "artifact://observation-2", "sha256": "b" * 64},
    {"ref": "artifact://review-3", "sha256": "c" * 64},
]


def initial_ledger():
    ledger = create_ledger("resolver-authority", created_by="test-suite")
    ledger, decision_id = issue_decision(
        ledger,
        event_key=EVENT,
        status="AUTHORIZED",
        evidence_set_digest="1" * 64,
        policy_digest="2" * 64,
        representative_ref="evidence://resolver-hit",
        issued_by="authority-A",
        rationale="Initial quorum decision.",
    )
    return ledger, decision_id


class AuthorityLineageTests(unittest.TestCase):
    def test_initial_decision_is_immutable_and_is_the_single_frontier(self):
        ledger = create_ledger("resolver-authority", created_by="test-suite")
        original = copy.deepcopy(ledger)
        ledger, decision_id = issue_decision(
            ledger,
            event_key=EVENT,
            status="AUTHORIZED",
            evidence_set_digest="1" * 64,
            policy_digest="2" * 64,
            representative_ref="evidence://resolver-hit",
            issued_by="authority-A",
            rationale="Initial decision.",
        )
        self.assertEqual(original["entries"], [ledger["entries"][0]])
        frontier = decision_frontier(ledger, EVENT)
        self.assertEqual(frontier["status"], "SINGLE_DECISION")
        self.assertEqual(frontier["decision_ids"], [decision_id])
        self.assertEqual(len(decision_history(ledger, EVENT)), 1)
        self.assertEqual(len(ledger["entries"]), 2)
        validate_ledger(ledger)

    def test_late_evidence_proposal_does_not_mutate_current_authority(self):
        ledger, original_id = initial_ledger()
        ledger, proposal_id = propose_revision(
            ledger,
            event_key=EVENT,
            base_decision_ids=[original_id],
            evidence_refs=EVIDENCE_1,
            reason="A source arrived after event finalization.",
            proposed_by="observer-B",
        )
        self.assertEqual(decision_frontier(ledger, EVENT)["decision_ids"], [original_id])
        ledger = resolve_proposal(
            ledger,
            proposal_id,
            outcome="REJECTED",
            rationale="Late evidence cannot alter the issued decision.",
            resolved_by="authority-A",
        )
        self.assertEqual(decision_frontier(ledger, EVENT)["decision_ids"], [original_id])
        self.assertEqual(len(decision_history(ledger, EVENT)), 1)
        validate_ledger(ledger)

    def test_accepted_revision_supersedes_without_erasing_prior_decision(self):
        ledger, original_id = initial_ledger()
        ledger, proposal_id = propose_revision(
            ledger,
            event_key=EVENT,
            base_decision_ids=[original_id],
            evidence_refs=EVIDENCE_2,
            reason="Independent evidence review requested reconsideration.",
            proposed_by="reviewer-B",
        )
        ledger = resolve_proposal(
            ledger,
            proposal_id,
            outcome="ACCEPTED",
            rationale="The review is authorized to issue a superseding decision.",
            resolved_by="authority-B",
        )
        ledger, replacement_id = issue_decision(
            ledger,
            event_key=EVENT,
            status="CONFLICT",
            evidence_set_digest="3" * 64,
            policy_digest="4" * 64,
            representative_ref=None,
            issued_by="authority-B",
            rationale="New evidence changes the authority outcome to conflict.",
            proposal_id=proposal_id,
        )
        history = decision_history(ledger, EVENT)
        self.assertEqual([item["decision_id"] for item in history], [original_id, replacement_id])
        self.assertEqual(history[0]["status"], "AUTHORIZED")
        self.assertEqual(history[1]["status"], "CONFLICT")
        self.assertEqual(history[1]["supersedes_decision_ids"], [original_id])
        self.assertEqual(history[1]["generation"], 1)
        self.assertEqual(decision_frontier(ledger, EVENT)["decision_ids"], [replacement_id])
        validate_ledger(ledger)

    def test_competing_accepted_revisions_create_ambiguous_frontier_until_merge(self):
        ledger, original_id = initial_ledger()
        ledger, proposal_a = propose_revision(
            ledger, event_key=EVENT, base_decision_ids=[original_id],
            evidence_refs=EVIDENCE_1, reason="Review path A.", proposed_by="reviewer-A",
        )
        ledger, proposal_b = propose_revision(
            ledger, event_key=EVENT, base_decision_ids=[original_id],
            evidence_refs=EVIDENCE_2, reason="Review path B.", proposed_by="reviewer-B",
        )
        ledger = resolve_proposal(
            ledger, proposal_a, outcome="ACCEPTED",
            rationale="Path A may issue a candidate decision.", resolved_by="authority-A",
        )
        ledger = resolve_proposal(
            ledger, proposal_b, outcome="ACCEPTED",
            rationale="Path B may issue a competing candidate decision.", resolved_by="authority-B",
        )
        ledger, decision_a = issue_decision(
            ledger, event_key=EVENT, status="REFUSED",
            evidence_set_digest="3" * 64, policy_digest="4" * 64,
            representative_ref=None, issued_by="authority-A",
            rationale="Path A finds the evidence insufficient.", proposal_id=proposal_a,
        )
        ledger, decision_b = issue_decision(
            ledger, event_key=EVENT, status="AUTHORIZED",
            evidence_set_digest="5" * 64, policy_digest="6" * 64,
            representative_ref="evidence://reviewed-hit", issued_by="authority-B",
            rationale="Path B accepts the reviewed evidence.", proposal_id=proposal_b,
        )
        frontier = decision_frontier(ledger, EVENT)
        self.assertEqual(frontier["status"], "AMBIGUOUS_FRONTIER")
        self.assertEqual(set(frontier["decision_ids"]), {decision_a, decision_b})

        ledger, merge_proposal = propose_revision(
            ledger,
            event_key=EVENT,
            base_decision_ids=frontier["decision_ids"],
            evidence_refs=EVIDENCE_MERGE,
            reason="An adjudication reconciles both competing revision branches.",
            proposed_by="review-committee",
        )
        ledger = resolve_proposal(
            ledger, merge_proposal, outcome="ACCEPTED",
            rationale="The merged review is authorized to supersede both branches.",
            resolved_by="review-chair",
        )
        ledger, merged_id = issue_decision(
            ledger, event_key=EVENT, status="AUTHORIZED",
            evidence_set_digest="7" * 64, policy_digest="8" * 64,
            representative_ref="evidence://merged-authority-result",
            issued_by="review-chair",
            rationale="This decision explicitly merges both reviewed branches.",
            proposal_id=merge_proposal,
        )
        merged = decision_history(ledger, EVENT)[-1]
        self.assertEqual(set(merged["supersedes_decision_ids"]), {decision_a, decision_b})
        self.assertEqual(merged["generation"], 2)
        self.assertEqual(decision_frontier(ledger, EVENT)["status"], "SINGLE_DECISION")
        self.assertEqual(decision_frontier(ledger, EVENT)["decision_ids"], [merged_id])
        self.assertEqual(len(decision_history(ledger, EVENT)), 4)
        validate_ledger(ledger)

    def test_stale_proposal_cannot_be_accepted_after_frontier_changes(self):
        ledger, original_id = initial_ledger()
        ledger, stale_proposal = propose_revision(
            ledger, event_key=EVENT, base_decision_ids=[original_id],
            evidence_refs=EVIDENCE_1, reason="Proposal later rendered stale.",
            proposed_by="reviewer-A",
        )
        ledger, winning_proposal = propose_revision(
            ledger, event_key=EVENT, base_decision_ids=[original_id],
            evidence_refs=EVIDENCE_2, reason="Proposal that advances first.",
            proposed_by="reviewer-B",
        )
        ledger = resolve_proposal(
            ledger, winning_proposal, outcome="ACCEPTED",
            rationale="Accepted against the current base.", resolved_by="authority-B",
        )
        ledger, _ = issue_decision(
            ledger, event_key=EVENT, status="AUTHORIZED",
            evidence_set_digest="3" * 64, policy_digest="4" * 64,
            representative_ref="evidence://new-hit", issued_by="authority-B",
            rationale="New decision advances the frontier.", proposal_id=winning_proposal,
        )
        with self.assertRaisesRegex(ValueError, "stale proposal"):
            resolve_proposal(
                ledger, stale_proposal, outcome="ACCEPTED",
                rationale="Must not accept an obsolete base.", resolved_by="authority-A",
            )
        ledger = resolve_proposal(
            ledger, stale_proposal, outcome="STALE",
            rationale="The cited base decision has already been superseded.",
            resolved_by="authority-A",
        )
        self.assertEqual(decision_frontier(ledger, EVENT)["status"], "SINGLE_DECISION")
        validate_ledger(ledger)

    def test_revision_cannot_cross_event_or_bypass_accepted_proposal(self):
        ledger, original_id = initial_ledger()
        with self.assertRaisesRegex(ValueError, "proposal"):
            issue_decision(
                ledger, event_key=EVENT, status="REFUSED",
                evidence_set_digest="3" * 64, policy_digest="4" * 64,
                representative_ref=None, issued_by="authority-B",
                rationale="Missing proposal.",
            )
        ledger, proposal_id = propose_revision(
            ledger, event_key=EVENT, base_decision_ids=[original_id],
            evidence_refs=EVIDENCE_1, reason="Event-local review.", proposed_by="reviewer",
        )
        ledger = resolve_proposal(
            ledger, proposal_id, outcome="ACCEPTED",
            rationale="Accepted for its stated event only.", resolved_by="authority",
        )
        with self.assertRaisesRegex(ValueError, "event"):
            issue_decision(
                ledger, event_key=OTHER_EVENT, status="REFUSED",
                evidence_set_digest="3" * 64, policy_digest="4" * 64,
                representative_ref=None, issued_by="authority",
                rationale="Cannot move proposal to another event.", proposal_id=proposal_id,
            )

    def test_authorized_decisions_require_a_representative(self):
        ledger = create_ledger("resolver-authority", created_by="test-suite")
        with self.assertRaisesRegex(ValueError, "representative"):
            issue_decision(
                ledger, event_key=EVENT, status="AUTHORIZED",
                evidence_set_digest="1" * 64, policy_digest="2" * 64,
                representative_ref=None, issued_by="authority",
                rationale="Authorized decisions name their representative.",
            )
        with self.assertRaisesRegex(ValueError, "representative"):
            issue_decision(
                ledger, event_key=EVENT, status="CONFLICT",
                evidence_set_digest="1" * 64, policy_digest="2" * 64,
                representative_ref="evidence://not-authorized", issued_by="authority",
                rationale="Conflicts do not select a representative.",
            )

    def test_demonstration_preserves_fork_and_merges_frontier(self):
        example = build_demonstration()
        ledger = example["ledger"]
        self.assertEqual(
            example["frontier_before_merge"]["status"], "AMBIGUOUS_FRONTIER"
        )
        self.assertEqual(
            example["frontier_after_merge"]["status"], "SINGLE_DECISION"
        )
        merged = decision_history(ledger, example["event_key"])[-1]
        self.assertEqual(
            set(merged["supersedes_decision_ids"]),
            set(example["branch_decision_ids"]),
        )
        validate_ledger(ledger)

    def test_tampering_with_prior_entry_is_detected(self):
        ledger, _ = initial_ledger()
        altered = copy.deepcopy(ledger)
        altered["entries"][1]["payload"]["status"] = "REFUSED"
        with self.assertRaisesRegex(ValueError, "entry digest"):
            validate_ledger(altered)

    def test_event_history_includes_proposal_resolution_and_excludes_other_events(self):
        ledger, initial_id = initial_ledger()
        ledger, proposal_id = propose_revision(
            ledger,
            event_key=EVENT,
            base_decision_ids=[initial_id],
            evidence_refs=EVIDENCE_1,
            reason="Review proposal for event history test.",
            proposed_by="reviewer",
        )
        ledger = resolve_proposal(
            ledger,
            proposal_id,
            outcome="REJECTED",
            rationale="The new evidence does not change the decision.",
            resolved_by="authority",
        )

        other_ledger = create_ledger("other-event", created_by="test-suite")
        other_ledger, _ = issue_decision(
            other_ledger, event_key=OTHER_EVENT, status="REFUSED",
            evidence_set_digest="9" * 64, policy_digest="a" * 64,
            representative_ref=None, issued_by="authority",
            rationale="Independent logical event.",
        )
        event_types = {
            item["entry_type"] for item in event_entries(ledger, EVENT)
        }
        self.assertEqual(
            event_types,
            {"decision_issued", "revision_proposed", "proposal_resolved"},
        )
        self.assertEqual(event_entries(ledger, OTHER_EVENT), [])
        self.assertEqual(
            {item["entry_type"] for item in event_entries(other_ledger, OTHER_EVENT)},
            {"decision_issued"},
        )

    def test_portable_json_schema_accepts_a_valid_ledger(self):
        ledger, _ = initial_ledger()
        schema_path = Path(__file__).with_name("authority-lineage.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(ledger, schema)

    def test_decision_frontier_validates_the_hash_chain(self):
        ledger, _ = initial_ledger()
        altered = copy.deepcopy(ledger)
        altered["entries"][1]["payload"]["status"] = "REFUSED"
        with self.assertRaisesRegex(ValueError, "entry digest"):
            decision_frontier(altered, EVENT)


if __name__ == "__main__":
    unittest.main()
