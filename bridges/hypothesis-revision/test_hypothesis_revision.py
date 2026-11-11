import unittest

from hypothesis_revision import HypothesisDefinition, HypothesisRevisionLedger


class HypothesisRevisionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = HypothesisRevisionLedger(
            (
                HypothesisDefinition("H1", "Command C-17 caused the mode transition."),
                HypothesisDefinition("H2", "The sensor changed independently."),
            )
        )

    def propose(self, hypothesis_id="H3"):
        return self.ledger.propose(
            hypothesis_id,
            "A previously unmodelled reset caused the transient.",
            source_attempt_id="query-01:0001",
            encounter_ref="encounters/unexpected-01.json",
            interpretation_ref="interpretations/unexpected-01.json",
            proposal_method="counterexample-guided-generation-v1",
            proposer="model-reviser",
        )

    def test_proposal_is_not_automatically_added_to_active_revision(self):
        self.propose()
        self.assertEqual(self.ledger.current_revision.revision_id, "revision-0001")
        self.assertEqual(
            tuple(item.hypothesis_id for item in self.ledger.current_revision.hypotheses),
            ("H1", "H2"),
        )
        self.assertEqual(self.ledger.candidates[0].validation_result, None)

    def test_unvalidated_or_inconclusive_candidate_cannot_be_activated(self):
        self.propose()
        with self.assertRaises(ValueError):
            self.ledger.activate_supported(revision_id="revision-0002", actor="reviewer")
        self.ledger.validate_candidate(
            "H3", "inconclusive",
            validation_ref="reviews/H3-inconclusive.json",
            validator="independent-reviewer",
        )
        with self.assertRaises(ValueError):
            self.ledger.activate_supported(revision_id="revision-0002", actor="reviewer")

    def test_supported_candidate_creates_new_revision_and_retains_parent(self):
        self.propose()
        self.ledger.validate_candidate(
            "H3", "supported",
            validation_ref="reviews/H3-supported.json",
            validator="controlled-replay",
        )
        old = self.ledger.revisions[0]
        new = self.ledger.activate_supported(revision_id="revision-0002", actor="model-curator")
        self.assertEqual(new.parent_revision_id, old.revision_id)
        self.assertEqual(
            tuple(item.hypothesis_id for item in old.hypotheses),
            ("H1", "H2"),
        )
        self.assertEqual(
            tuple(item.hypothesis_id for item in new.hypotheses),
            ("H1", "H2", "H3"),
        )
        self.assertNotEqual(old.hypothesis_set_digest, new.hypothesis_set_digest)

    def test_rejected_candidate_is_recorded_but_never_activated(self):
        self.propose()
        self.ledger.validate_candidate(
            "H3", "rejected",
            validation_ref="reviews/H3-rejected.json",
            validator="counterexample-checker",
        )
        with self.assertRaises(ValueError):
            self.ledger.activate_supported(revision_id="revision-0002", actor="curator")
        self.assertEqual(len(self.ledger.revisions), 1)
        self.assertEqual(self.ledger.candidates[0].validation_result, "rejected")

    def test_multiple_supported_candidates_are_activated_together(self):
        self.propose("H3")
        self.propose("H4")
        for hypothesis_id in ("H3", "H4"):
            self.ledger.validate_candidate(
                hypothesis_id, "supported",
                validation_ref=f"reviews/{hypothesis_id}.json",
                validator="reviewer",
            )
        new = self.ledger.activate_supported(revision_id="revision-0002", actor="curator")
        self.assertEqual(
            tuple(item.hypothesis_id for item in new.hypotheses),
            ("H1", "H2", "H3", "H4"),
        )

    def test_event_history_is_append_only_and_snapshotted(self):
        self.propose()
        event = self.ledger.events[-1]
        details = event.details
        details["hypothesis_id"] = "corrupted"
        self.assertEqual(event.details["hypothesis_id"], "H3")
        self.ledger.validate_candidate(
            "H3", "supported",
            validation_ref="reviews/H3.json",
            validator="reviewer",
        )
        self.ledger.activate_supported(revision_id="revision-0002", actor="curator")
        self.assertEqual(
            [event.event_type for event in self.ledger.events],
            ["revision_created", "hypothesis_proposed", "hypothesis_validated", "revision_activated"],
        )

    def test_duplicate_identifiers_and_missing_provenance_are_rejected(self):
        with self.assertRaises(ValueError):
            HypothesisRevisionLedger(
                (HypothesisDefinition("H1", "one"), HypothesisDefinition("H1", "duplicate"))
            )
        with self.assertRaises(ValueError):
            self.ledger.propose(
                "H3", "candidate",
                source_attempt_id=" ",
                encounter_ref="encounter.json",
                interpretation_ref="interpretation.json",
                proposal_method="method",
                proposer="agent",
            )
        self.propose()
        with self.assertRaises(ValueError):
            self.ledger.propose(
                "H3", "duplicate",
                source_attempt_id="attempt",
                encounter_ref="encounter.json",
                interpretation_ref="interpretation.json",
                proposal_method="method",
                proposer="agent",
            )

    def test_validation_is_explicit_and_only_once(self):
        self.propose()
        self.ledger.validate_candidate(
            "H3", "supported",
            validation_ref="reviews/H3.json",
            validator="reviewer",
        )
        with self.assertRaises(ValueError):
            self.ledger.validate_candidate(
                "H3", "rejected",
                validation_ref="reviews/H3-second.json",
                validator="second-reviewer",
            )

    def test_revision_identifiers_are_unique(self):
        self.propose()
        self.ledger.validate_candidate(
            "H3", "supported",
            validation_ref="reviews/H3.json",
            validator="reviewer",
        )
        self.ledger.activate_supported(revision_id="revision-0002", actor="curator")
        self.propose("H4")
        self.ledger.validate_candidate(
            "H4", "supported",
            validation_ref="reviews/H4.json",
            validator="reviewer",
        )
        with self.assertRaises(ValueError):
            self.ledger.activate_supported(revision_id="revision-0002", actor="curator")

    def test_later_revision_does_not_duplicate_prior_supported_candidates(self):
        self.propose("H3")
        self.ledger.validate_candidate(
            "H3", "supported", validation_ref="reviews/H3.json", validator="reviewer"
        )
        second = self.ledger.activate_supported(revision_id="revision-0002", actor="curator")
        self.assertEqual(tuple(h.hypothesis_id for h in second.hypotheses), ("H1", "H2", "H3"))

        self.propose("H4")
        self.ledger.validate_candidate(
            "H4", "supported", validation_ref="reviews/H4.json", validator="reviewer"
        )
        third = self.ledger.activate_supported(revision_id="revision-0003", actor="curator")
        self.assertEqual(tuple(h.hypothesis_id for h in third.hypotheses), ("H1", "H2", "H3", "H4"))
        self.assertEqual(len({h.hypothesis_id for h in third.hypotheses}), 4)

    def test_unknown_validation_result_is_rejected(self):
        self.propose()
        with self.assertRaises(ValueError):
            self.ledger.validate_candidate(
                "H3", "maybe", validation_ref="reviews/H3.json", validator="reviewer"
            )
    def unresolved_attempt(self, reason="interpreted observation value was not predicted by the policy"):
        return {
            "attempt_id": "query-01:0001",
            "status": "unresolved",
            "events": [
                {"stage": "planned", "evidence_ref": "plans/policy.json", "details": {}},
                {"stage": "dispatched", "evidence_ref": "transport/send.json", "details": {}},
                {"stage": "admitted", "evidence_ref": "receiver/admission.json", "details": {}},
                {"stage": "returned", "evidence_ref": "encounters/unexpected.json", "details": {
                    "encounter_id": "unexpected-01",
                    "payload_digest": "sha256:unexpected-payload",
                    "canonicalization": "utf8-raw-v1",
                }},
                {"stage": "interpreted", "evidence_ref": "interpretations/unexpected.json", "details": {"method": "parser-v1"}},
                {"stage": "unresolved", "evidence_ref": "interpretations/unexpected.json", "details": {"reason": reason}},
            ],
        }

    def test_model_mismatch_attempt_supplies_candidate_provenance(self):
        candidate = self.ledger.propose_from_unresolved_attempt(
            self.unresolved_attempt(),
            "H3",
            "A previously unmodelled reset caused the transient.",
            proposal_method="counterexample-guided-generation-v1",
            proposer="model-reviser",
        )
        self.assertEqual(candidate.source_attempt_id, "query-01:0001")
        self.assertEqual(candidate.encounter_ref, "encounters/unexpected.json")
        self.assertEqual(candidate.interpretation_ref, "interpretations/unexpected.json")
        self.assertEqual(candidate.source_payload_digest, "sha256:unexpected-payload")
        self.assertEqual(candidate.source_canonicalization, "utf8-raw-v1")
        self.assertIsNone(candidate.validation_result)
        self.assertEqual(tuple(h.hypothesis_id for h in self.ledger.current_revision.hypotheses), ("H1", "H2"))

    def test_timeout_rejection_and_unadmitted_return_cannot_create_hypothesis(self):
        for status, stages in (
            ("no_result", ["planned", "dispatched", "admitted", "no_result"]),
            ("rejected", ["planned", "dispatched", "rejected"]),
            ("returned_unadmitted", ["planned", "dispatched", "returned_unadmitted"]),
        ):
            with self.subTest(status=status):
                attempt = {"attempt_id": "attempt", "status": status, "events": [{"stage": stage, "details": {}} for stage in stages]}
                with self.assertRaises(ValueError):
                    self.ledger.propose_from_unresolved_attempt(
                        attempt, "H3", "candidate",
                        proposal_method="method", proposer="agent",
                    )

    def test_unresolved_attempt_with_other_reason_is_not_model_mismatch(self):
        with self.assertRaises(ValueError):
            self.ledger.propose_from_unresolved_attempt(
                self.unresolved_attempt("operator cancelled the run"),
                "H3", "candidate",
                proposal_method="method", proposer="agent",
            )

    def test_reordered_or_malformed_event_history_is_rejected(self):
        attempt = self.unresolved_attempt()
        attempt["events"][2], attempt["events"][3] = attempt["events"][3], attempt["events"][2]
        with self.assertRaises(ValueError):
            self.ledger.propose_from_unresolved_attempt(
                attempt, "H3", "candidate",
                proposal_method="method", proposer="agent",
            )

if __name__ == "__main__":
    unittest.main()
