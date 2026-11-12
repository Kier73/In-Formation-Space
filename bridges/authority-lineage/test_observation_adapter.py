import unittest

from authority_lineage import create_ledger, decision_frontier, decision_history, validate_ledger
from observation_adapter import (
    DuplicateObservationEvidenceError,
    ObservationEvidenceError,
    SourceEquivocationError,
    issue_initial_decision_from_attempt,
    propose_revision_from_new_evidence,
)


EVENT = {"kind": "resolver", "logical_time": 11}
POLICY_DIGEST = "f" * 64


def evidence(source, value_digest, *, attempt="attempt-1", observation="observation-1", sequence=1):
    return {
        "attempt_id": attempt,
        "observation_id": observation,
        "source": source,
        "channel": f"resolver-{source}",
        "sequence": sequence,
        "payload_digest": value_digest,
        "event": dict(EVENT),
        "synthetic_value": "hit",
        "authority_effect": "evidence_received_not_yet_authority",
    }


def authorized_attempt():
    sources = ["S00", "S01"]
    return {
        "attempt_id": "attempt-1",
        "observation_id": "observation-1",
        "final_status": "AUTHORIZED",
        "evidence_received_sources": sources,
        "evidence_received_count": len(sources),
        "representative_source": "S00",
        "evidence_partition": {
            "observed_sources": sources,
            "winner_sources": sources,
            "dissenting_sources": [],
            "missing_sources": ["S02", "S03"],
        },
    }


class ObservationAdapterTests(unittest.TestCase):
    def test_initial_authority_decision_is_bound_to_admitted_evidence_set(self):
        ledger = create_ledger("adapter-test", created_by="test-suite")
        records = [
            evidence("S00", "a" * 64),
            evidence("S01", "b" * 64),
        ]
        updated, decision_id, receipt = issue_initial_decision_from_attempt(
            ledger,
            authorized_attempt(),
            records,
            policy_digest=POLICY_DIGEST,
            issued_by="authority",
            rationale="Quorum authority from the admitted observation records.",
        )
        decision = decision_history(updated, EVENT)[0]
        self.assertEqual(decision["decision_id"], decision_id)
        self.assertEqual(decision["status"], "AUTHORIZED")
        self.assertIn("S00", decision["representative_ref"])
        self.assertEqual(receipt["evidence_sources"], ["S00", "S01"])
        self.assertEqual(receipt["evidence_record_count"], 2)
        self.assertEqual(decision_frontier(updated, EVENT)["decision_ids"], [decision_id])
        validate_ledger(updated)

    def test_conflicted_attempt_can_be_recorded_without_representative(self):
        ledger = create_ledger("adapter-conflict", created_by="test-suite")
        attempt = dict(authorized_attempt(), final_status="CONFLICT", representative_source=None)
        records = [
            evidence("S00", "a" * 64),
            evidence("S01", "b" * 64),
        ]
        updated, decision_id, receipt = issue_initial_decision_from_attempt(
            ledger, attempt, records, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="Cross-source disagreement is preserved.",
        )
        decision = decision_history(updated, EVENT)[0]
        self.assertEqual(decision["status"], "CONFLICT")
        self.assertIsNone(decision["representative_ref"])
        self.assertEqual(receipt["decision_id"], decision_id)

    def test_late_new_source_becomes_revision_proposal_not_mutated_authority(self):
        ledger = create_ledger("adapter-late", created_by="test-suite")
        known = [evidence("S00", "a" * 64), evidence("S01", "b" * 64)]
        ledger, decision_id, _ = issue_initial_decision_from_attempt(
            ledger, authorized_attempt(), known, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="Initial two-source quorum.",
        )
        new = evidence(
            "S02", "c" * 64, attempt="attempt-late",
            observation="observation-late", sequence=1,
        )
        updated, proposal_id, receipt = propose_revision_from_new_evidence(
            ledger, event_key=EVENT, base_decision_ids=[decision_id],
            known_evidence_records=known, new_evidence_records=[new],
            reason="A previously absent source has now supplied evidence.",
            proposed_by="reviewer",
        )
        self.assertEqual(decision_frontier(updated, EVENT)["decision_ids"], [decision_id])
        proposal = next(
            item["payload"] for item in updated["entries"]
            if item["entry_type"] == "revision_proposed"
        )
        self.assertEqual(proposal["proposal_id"], proposal_id)
        self.assertEqual(receipt["new_sources"], ["S02"])
        self.assertEqual(proposal["evidence_refs"][0]["sha256"], "c" * 64)
        validate_ledger(updated)

    def test_exact_late_replay_is_duplicate_not_revision(self):
        ledger = create_ledger("adapter-duplicate", created_by="test-suite")
        known = [evidence("S00", "a" * 64), evidence("S01", "b" * 64)]
        ledger, decision_id, _ = issue_initial_decision_from_attempt(
            ledger, authorized_attempt(), known, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="Initial authority.",
        )
        duplicate = evidence("S00", "a" * 64, attempt="attempt-replay", observation="replay")
        with self.assertRaises(DuplicateObservationEvidenceError):
            propose_revision_from_new_evidence(
                ledger, event_key=EVENT, base_decision_ids=[decision_id],
                known_evidence_records=known, new_evidence_records=[duplicate],
                reason="Exact replay must not be proposed.", proposed_by="reviewer",
            )

    def test_same_source_changed_payload_is_equivocation_not_revision(self):
        ledger = create_ledger("adapter-equivocation", created_by="test-suite")
        known = [evidence("S00", "a" * 64), evidence("S01", "b" * 64)]
        ledger, decision_id, _ = issue_initial_decision_from_attempt(
            ledger, authorized_attempt(), known, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="Initial authority.",
        )
        changed = evidence("S00", "c" * 64, attempt="attempt-late", observation="changed")
        with self.assertRaises(SourceEquivocationError):
            propose_revision_from_new_evidence(
                ledger, event_key=EVENT, base_decision_ids=[decision_id],
                known_evidence_records=known, new_evidence_records=[changed],
                reason="Equivocation must not be disguised as late evidence.",
                proposed_by="reviewer",
            )

    def test_initial_decision_rejects_evidence_partition_mismatch(self):
        ledger = create_ledger("adapter-mismatch", created_by="test-suite")
        with self.assertRaisesRegex(ObservationEvidenceError, "sources differ"):
            issue_initial_decision_from_attempt(
                ledger,
                authorized_attempt(),
                [evidence("S00", "a" * 64)],
                policy_digest=POLICY_DIGEST,
                issued_by="authority",
                rationale="Incomplete evidence record set.",
            )

    def test_revision_rejects_evidence_from_another_logical_event(self):
        ledger = create_ledger("adapter-other-event", created_by="test-suite")
        known = [evidence("S00", "a" * 64), evidence("S01", "b" * 64)]
        ledger, decision_id, _ = issue_initial_decision_from_attempt(
            ledger, authorized_attempt(), known, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="Initial authority.",
        )
        late = evidence("S02", "c" * 64, attempt="late", observation="late")
        late["event"] = {"kind": "resolver", "logical_time": 12}
        with self.assertRaisesRegex(ObservationEvidenceError, "different logical event"):
            propose_revision_from_new_evidence(
                ledger, event_key=EVENT, base_decision_ids=[decision_id],
                known_evidence_records=known, new_evidence_records=[late],
                reason="Wrong event must not enter review.", proposed_by="reviewer",
            )

    def test_revision_requires_known_records_to_reconstruct_current_decision(self):
        ledger = create_ledger("adapter-evidence-binding", created_by="test-suite")
        known = [evidence("S00", "a" * 64), evidence("S01", "b" * 64)]
        ledger, decision_id, _ = issue_initial_decision_from_attempt(
            ledger, authorized_attempt(), known, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="Initial authority.",
        )
        altered_known = [evidence("S00", "c" * 64), known[1]]
        late = evidence("S02", "d" * 64, attempt="late", observation="late")
        with self.assertRaisesRegex(ObservationEvidenceError, "do not reconstruct"):
            propose_revision_from_new_evidence(
                ledger, event_key=EVENT, base_decision_ids=[decision_id],
                known_evidence_records=altered_known, new_evidence_records=[late],
                reason="Mismatched evidence store must not revise authority.",
                proposed_by="reviewer",
            )

    def test_revision_adapter_requires_complete_current_frontier(self):
        ledger = create_ledger("adapter-frontier", created_by="test-suite")
        known = [evidence("S00", "a" * 64), evidence("S01", "b" * 64)]
        ledger, decision_id, _ = issue_initial_decision_from_attempt(
            ledger, authorized_attempt(), known, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="Initial authority.",
        )
        late = evidence("S02", "c" * 64, attempt="late", observation="late")
        with self.assertRaisesRegex(ObservationEvidenceError, "complete current"):
            propose_revision_from_new_evidence(
                ledger, event_key=EVENT, base_decision_ids=[],
                known_evidence_records=known, new_evidence_records=[late],
                reason="A revision cannot omit its base.", proposed_by="reviewer",
            )

    def test_initial_decision_requires_attempt_evidence_count_to_match(self):
        ledger = create_ledger("adapter-count", created_by="test-suite")
        attempt = dict(authorized_attempt(), evidence_received_count=3)
        records = [evidence("S00", "a" * 64), evidence("S01", "b" * 64)]
        with self.assertRaisesRegex(ObservationEvidenceError, "evidence count"):
            issue_initial_decision_from_attempt(
                ledger, attempt, records, policy_digest=POLICY_DIGEST,
                issued_by="authority", rationale="Count mismatch must not be accepted.",
            )

    def test_empty_evidence_refusal_requires_an_explicit_event_key(self):
        ledger = create_ledger("adapter-empty", created_by="test-suite")
        attempt = {
            "attempt_id": "attempt-empty",
            "observation_id": "observation-empty",
            "final_status": "REFUSED",
            "evidence_received_sources": [],
            "evidence_received_count": 0,
            "representative_source": None,
            "evidence_partition": {
                "observed_sources": [],
                "source_count": 0,
                "winner_sources": [],
                "dissenting_sources": [],
                "missing_sources": ["S00", "S01", "S02", "S03"],
            },
        }
        with self.assertRaisesRegex(ObservationEvidenceError, "explicit event key"):
            issue_initial_decision_from_attempt(
                ledger, attempt, [], policy_digest=POLICY_DIGEST,
                issued_by="authority", rationale="Empty evidence requires event coordinates.",
            )
        updated, decision_id, receipt = issue_initial_decision_from_attempt(
            ledger, attempt, [], event_key=EVENT, policy_digest=POLICY_DIGEST,
            issued_by="authority", rationale="No observation evidence arrived before finalization.",
        )
        decision = decision_history(updated, EVENT)[0]
        self.assertEqual(decision["decision_id"], decision_id)
        self.assertEqual(decision["status"], "REFUSED")
        self.assertIsNone(decision["representative_ref"])
        self.assertEqual(receipt["evidence_record_count"], 0)

    def test_authorized_representative_must_belong_to_winning_group(self):
        ledger = create_ledger("adapter-winner", created_by="test-suite")
        attempt = dict(authorized_attempt())
        attempt["evidence_partition"] = {
            **attempt["evidence_partition"],
            "winner_sources": ["S01"],
        }
        with self.assertRaisesRegex(ObservationEvidenceError, "winning evidence group"):
            issue_initial_decision_from_attempt(
                ledger, attempt,
                [evidence("S00", "a" * 64), evidence("S01", "b" * 64)],
                policy_digest=POLICY_DIGEST, issued_by="authority",
                rationale="Representative outside winner must be rejected.",
            )


if __name__ == "__main__":
    unittest.main()
