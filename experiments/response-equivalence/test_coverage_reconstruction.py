"""RE-008: integrity, coverage, delayed captures, overlaps and cautious claims."""
import copy
import unittest

from coverage_reconstruction import (
    ACTORS, EPOCHS, CoverageError, choose_audit, delayed_delivery,
    enrollment, fixture, produce_log, reconstruct, sha, verify_log,
)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.logs, self.reg, self.late = fixture()

    def test_each_witness_alone_has_loss(self):
        self.assertEqual([x["epoch"] for x in self.logs["A"]["records"] if x["outcome"] == "dropout"], [2, 5])
        self.assertEqual([x["epoch"] for x in self.logs["B"]["records"] if x["outcome"] == "dropout"], [1, 4])

    def test_union_has_no_blind_slots(self):
        report = reconstruct(self.logs, self.reg)
        self.assertEqual(report["blind_epoch_bound"], 0)
        self.assertEqual(report["status"], "declared_epochs_observed")
        self.assertFalse(report["full_physical_coverage_proved"])
        self.assertIsNone(report["physical_event_loss_bound"])

    def test_late_delivery_refines_without_rewriting_capture(self):
        before = reconstruct(self.logs, self.reg)
        after = reconstruct(self.logs, self.reg, self.late)
        self.assertIn(6, before["single_observer_epochs"])
        self.assertNotIn(6, after["single_observer_epochs"])
        self.assertEqual(after["slots"][6]["status"], "corroborated_present")
        self.assertEqual(self.logs["A"]["records"][6]["outcome"], "pending")

    def test_missing_archived_record_blocks_bound_until_recovery(self):
        damaged = copy.deepcopy(self.logs)
        damaged["B"]["records"] = [r for r in damaged["B"]["records"] if r["epoch"] != 3]
        bad = reconstruct(damaged, self.reg)
        self.assertEqual(bad["status"], "unresolved_log_continuity")
        self.assertEqual(bad["archive_gaps"]["B"], [3])
        self.assertIsNone(bad["blind_epoch_bound"])
        self.assertEqual(choose_audit(damaged, self.reg)["action"], "retrieve_signed_archived_slot")
        damaged["B"]["records"].append(self.logs["B"]["records"][3])
        self.assertEqual(reconstruct(damaged, self.reg)["blind_epoch_bound"], 0)

    def test_missing_terminal_slot_detected_by_seal(self):
        damaged = copy.deepcopy(self.logs)
        damaged["A"]["records"].pop()
        self.assertEqual(reconstruct(damaged, self.reg)["archive_gaps"]["A"], [7])

    def test_missing_seal_cannot_prove_completeness(self):
        damaged = copy.deepcopy(self.logs)
        damaged["A"]["seal"] = None
        self.assertEqual(reconstruct(damaged, self.reg)["status"], "unresolved_log_continuity")

    def test_signed_record_tamper_rejected_even_with_rehash(self):
        damaged = copy.deepcopy(self.logs)
        damaged["A"]["records"][1]["event"] = "0" * 64
        rec = damaged["A"]["records"][1]
        rec["digest"] = sha({k: v for k, v in rec.items() if k != "digest"})
        with self.assertRaisesRegex(CoverageError, "HMAC"):
            reconstruct(damaged, self.reg)

    def test_reordered_archived_records_are_safe(self):
        changed = copy.deepcopy(self.logs)
        changed["B"]["records"].reverse()
        self.assertEqual(reconstruct(changed, self.reg)["blind_epoch_bound"], 0)

    def test_duplicate_record_evidence_rejected(self):
        changed = copy.deepcopy(self.logs)
        changed["B"]["records"].append(changed["B"]["records"][3])
        with self.assertRaisesRegex(CoverageError, "duplicate"):
            reconstruct(changed, self.reg)

    def test_broken_adjacent_chain_rejected_even_with_valid_individual_signatures(self):
        other = enrollment(deterministic=True)
        replacement = produce_log("B", other, {2: "dropout"})
        changed = copy.deepcopy(self.logs)
        changed["B"]["records"][3] = replacement["records"][3]
        with self.assertRaisesRegex(CoverageError, "chain"):
            reconstruct(changed, self.reg)

    def test_changed_enrollment_key_rejected(self):
        changed = copy.deepcopy(self.reg)
        changed["keys"]["B"] = "ef" * 32
        with self.assertRaises(CoverageError):
            reconstruct(self.logs, changed)

    def test_different_challenge_fails_closed(self):
        changed = copy.deepcopy(self.reg)
        changed["challenge"] = "different-session-challenge"
        with self.assertRaisesRegex(CoverageError, "identity"):
            reconstruct(self.logs, changed)

    def test_delivery_unbound_to_capture_rejected(self):
        bad = copy.deepcopy(self.late)
        bad[0]["capture_digest"] = "f" * 64
        with self.assertRaisesRegex(CoverageError, "HMAC"):
            reconstruct(self.logs, self.reg, bad)

    def test_duplicate_delivery_rejected(self):
        with self.assertRaisesRegex(CoverageError, "replayed"):
            reconstruct(self.logs, self.reg, self.late * 2)

    def test_unauthorized_physical_claim_never_emitted(self):
        r = reconstruct(self.logs, self.reg, self.late)
        self.assertIsNone(r["physical_event_loss_bound"])
        self.assertIs(r["full_physical_coverage_proved"], False)
        self.assertEqual(r["coverage_scope"], "declared eight capture epochs under CI-enrolled roles")

    def test_both_dropout_yields_blind_slot(self):
        a = produce_log("A", self.reg, {3: "dropout"})
        b = produce_log("B", self.reg, {3: "dropout"})
        r = reconstruct({"A": a, "B": b}, self.reg)
        self.assertEqual(r["blind_epochs"], [3])
        self.assertEqual(choose_audit({"A": a, "B": b}, self.reg)["action"],
                         "new_authorized_reobservation")

    def test_conflicting_witness_reports_do_not_resolve(self):
        a = produce_log("A", self.reg)
        b = produce_log("B", self.reg, {1: "absent"})
        r = reconstruct({"A": a, "B": b}, self.reg)
        self.assertEqual(r["status"], "conflicted")
        self.assertEqual(r["conflict_epochs"], [1])
        self.assertEqual(choose_audit({"A": a, "B": b}, self.reg)["action"],
                         "independent_disagreement_review")

    def test_both_absent_is_only_observer_relative(self):
        r = reconstruct(self.logs, self.reg)
        self.assertEqual(r["slots"][0]["status"], "corroborated_absent")
        self.assertFalse(r["full_physical_coverage_proved"])

    def test_both_present_different_fingerprint_is_conflict(self):
        # Alternate synthetic event content with a correctly signed independent log.
        # The core fixture uses a single event payload catalogue, so construct an
        # independently valid conflicting report by changing the declared source mark.
        import coverage_reconstruction as impl
        original = impl.EVENTS[1]
        try:
            impl.EVENTS[1] = "other-mark"
            b = produce_log("B", self.reg)
        finally:
            impl.EVENTS[1] = original
        a = produce_log("A", self.reg)
        r = reconstruct({"A": a, "B": b}, self.reg)
        self.assertEqual(r["slots"][1]["status"], "conflicting_events")

    def test_audit_plans_are_not_executed(self):
        plan = choose_audit(self.logs, self.reg)
        self.assertEqual(plan["action"], "request_capture_bound_delivery")
        self.assertEqual(plan["target"], ["A", 6])
        self.assertEqual(plan["outcome"], "planned_only")
        self.assertEqual(choose_audit(self.logs, self.reg, self.late)["action"], "none")

    def test_untrusted_observer_fabrication_not_detectable_from_key_alone(self):
        # An authorized holder can sign a false reading; no honest-world guarantee.
        a = produce_log("A", self.reg, {2: "absent"})
        b = produce_log("B", self.reg, {2: "absent"})
        r = reconstruct({"A": a, "B": b}, self.reg)
        self.assertEqual(r["slots"][2]["status"], "corroborated_absent")
        self.assertFalse(r["physical_sensor_identity_proved"])

    def test_unsupported_outcome_rejected_at_producer(self):
        with self.assertRaisesRegex(CoverageError, "planned outcome"):
            produce_log("A", self.reg, {2: "no_event_in_universe"})


if __name__ == "__main__":
    unittest.main()
