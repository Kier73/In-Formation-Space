"""RE-009: source report versus correlated observer blindness and audit limits."""
import copy
import unittest

from coverage_reconstruction import produce_log, delayed_delivery, sha
from common_mode_counter import (
    CounterError, acknowledge, choose_audit, fixture, produce_source,
    reconstruct, register, verify_source, verify_acknowledgements,
)


class CounterDisagreementTests(unittest.TestCase):
    def setUp(self):
        self.source, self.logs, self.acks, self.reg, self.late = fixture()

    def report(self, *, source=None, logs=None, acks=None, reg=None, late=None):
        return reconstruct(self.source if source is None else source,
                           self.logs if logs is None else logs,
                           self.acks if acks is None else acks,
                           self.reg if reg is None else reg,
                           self.late if late is None else late)

    def test_common_mode_absent_looks_like_full_epoch_coverage(self):
        result = self.report()
        self.assertEqual(result['observer_blind_declared_epochs'], [])
        self.assertEqual(result['observed_epochs'], [1, 4, 6])
        self.assertEqual(result['status'], 'source_observer_disagreement')
        self.assertEqual(result['source_observer_discrepancy'], 1)
        self.assertEqual(result['windows'][0]['source_minus_observers'], 1)
        self.assertEqual(result['windows'][1]['source_minus_observers'], 0)

    def test_no_physical_truth_claim_even_when_source_exceeds(self):
        result = self.report()
        for field in ('source_truthfulness_proved', 'physical_common_mode_loss_proved',
                      'physical_event_completeness_proved', 'causation_proved'):
            self.assertIs(result[field], False)
        self.assertIsNone(result['cross_host_elapsed'])

    def test_source_counter_overreport_is_observationally_indistinguishable(self):
        # The same public source and observer records fit two latent worlds:
        # a real missing event, or a false additional event counter increment.
        result1 = self.report()
        result2 = self.report()
        self.assertEqual(result1, result2)
        self.assertFalse(result1['physical_common_mode_loss_proved'])

    def test_honest_agreement_is_not_exhaustive_physical_coverage(self):
        other = produce_source(self.reg, (0, 1, 3))
        ack = {a: acknowledge(a, self.logs[a], other, self.reg) for a in ('A', 'B')}
        r = self.report(source=other, acks=ack)
        self.assertEqual(r['source_observer_discrepancy'], 0)
        self.assertEqual(r['status'], 'source_observer_counts_agree')
        self.assertIs(r['physical_event_completeness_proved'], False)

    def test_source_underreports_detectable_without_auto_selecting_side(self):
        other = produce_source(self.reg, (0, 1, 2))
        ack = {a: acknowledge(a, self.logs[a], other, self.reg) for a in ('A', 'B')}
        r = self.report(source=other, acks=ack)
        self.assertEqual(r['source_observer_discrepancy'], -1)
        self.assertEqual(r['status'], 'source_observer_disagreement')
        self.assertIs(r['source_truthfulness_proved'], False)

    def test_source_early_window_discrepancy_is_not_exact_epoch_location(self):
        r = self.report()
        self.assertEqual(r['windows'][0]['start'], 0)
        self.assertEqual(r['windows'][0]['end_exclusive'], 4)
        self.assertNotIn('missing_event_epoch', str(r))
        self.assertEqual(choose_audit(r)['target_window'], [0, 4])

    def test_delayed_reading_still_counted_at_capture_epoch(self):
        r = self.report(late=[])
        self.assertEqual(r['observed_total'], 3)
        self.assertEqual(r['source_observer_discrepancy'], 1)

    def test_duplicate_two_observers_count_single_event(self):
        r = self.report()
        self.assertEqual(r['observed_total'], 3)
        self.assertEqual(r['windows'][1]['observer_reported_distinct_events'], 2)

    def test_missing_observer_archive_blocks_comparison(self):
        damaged = copy.deepcopy(self.logs)
        damaged['B']['records'] = [item for item in damaged['B']['records'] if item['epoch'] != 3]
        r = self.report(logs=damaged)
        self.assertEqual(r['status'], 'unresolved_archive_continuity')
        self.assertIsNone(r['source_observer_discrepancy'])
        self.assertEqual(r['missing_archived_records']['B'], [3])
        self.assertEqual(choose_audit(r)['action'], 'retrieve_signed_archived_observer_slot')
        damaged['B']['records'].append(self.logs['B']['records'][3])
        self.assertEqual(self.report(logs=damaged)['source_observer_discrepancy'], 1)

    def test_conflicting_observer_reports_prevent_count_comparison(self):
        damaged = copy.deepcopy(self.logs)
        damaged['B'] = produce_log('B', self.reg, {1: 'absent', 4: 'dropout'})
        acks = {a: acknowledge(a, damaged[a], self.source, self.reg) for a in ('A','B')}
        r = self.report(logs=damaged, acks=acks)
        self.assertEqual(r['status'], 'unresolved_conflicting_observers')
        self.assertIsNone(r['observed_total'])

    def test_corrupted_signed_source_counter_rejected_even_after_rehash(self):
        changed = copy.deepcopy(self.source)
        changed['receipts'][1]['cumulative'] += 1
        rec = changed['receipts'][1]
        rec['digest'] = sha({k: v for k, v in rec.items() if k != 'digest'})
        with self.assertRaises(CounterError):
            self.report(source=changed)

    def test_missing_source_receipt_rejected(self):
        bad = copy.deepcopy(self.source)
        bad['receipts'].pop(1)
        with self.assertRaisesRegex(CounterError, 'missing or duplicated'):
            self.report(source=bad)

    def test_reordered_source_boundary_rejected(self):
        bad = copy.deepcopy(self.source)
        bad['receipts'][1], bad['receipts'][2] = bad['receipts'][2], bad['receipts'][1]
        with self.assertRaises(CounterError):
            self.report(source=bad)

    def test_missing_observer_acknowledgement_rejected(self):
        with self.assertRaisesRegex(CounterError, 'missing independent'):
            self.report(acks={'A': self.acks['A']})

    def test_acknowledgement_cannot_switch_to_a_new_valid_source_log(self):
        other = produce_source(self.reg, (0, 1, 3))
        with self.assertRaisesRegex(CounterError, 'detached'):
            self.report(source=other)

    def test_acknowledgement_cannot_switch_seal_even_after_rehash(self):
        changed = copy.deepcopy(self.acks)
        changed['A']['observer_seal'] = '0' * 64
        changed['A']['digest'] = sha({k:v for k,v in changed['A'].items() if k != 'digest'})
        with self.assertRaisesRegex(Exception, 'HMAC'):
            self.report(acks=changed)

    def test_malformed_enrollment_key_fails(self):
        reg = copy.deepcopy(self.reg)
        reg['keys']['S'] = 'ab' * 32
        with self.assertRaisesRegex(CounterError, 'enrollment'):
            self.report(reg=reg)

    def test_cross_session_source_replay_fails(self):
        reg = copy.deepcopy(self.reg)
        reg['challenge'] = 'a-different-challenge-value'
        with self.assertRaisesRegex(CounterError, 'identity'):
            self.report(reg=reg)

    def test_source_counts_must_be_monotone_and_within_epoch_capacity(self):
        for counts in ((0,3,2), (0,5,5), (1,2,3), (0,2,9)):
            with self.subTest(counts=counts):
                with self.assertRaises(CounterError):
                    produce_source(self.reg, counts)

    def test_missing_capture_bound_delivery_replay_fails(self):
        with self.assertRaisesRegex(Exception, 'replayed'):
            self.report(late=self.late*2)

    def test_planner_only_recommends_new_evidence(self):
        plan = choose_audit(self.report())
        self.assertEqual(plan['action'], 'request_independent_event_origin_evidence')
        self.assertIn('planned_only', plan['outcome'])

    def test_self_consistent_false_observer_hmac_cannot_establish_truth(self):
        # The key-owning role can lie; re-signing its report does not attest the world.
        false = copy.deepcopy(self.logs)
        false['B'] = produce_log('B', self.reg, {1:'dropout', 4:'dropout'})
        acks = {a: acknowledge(a, false[a], self.source, self.reg) for a in ('A','B')}
        r = self.report(logs=false, acks=acks)
        self.assertFalse(r['source_truthfulness_proved'])


if __name__ == '__main__':
    unittest.main()
