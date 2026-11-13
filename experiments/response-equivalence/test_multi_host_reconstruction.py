"""RE-003 finite-fixture regression and negative controls."""
import copy
import unittest

from multi_host_reconstruction import (
    LAWS, EvidenceError, canonical, digest, encode, initial_state, call_host,
    call_verifier, produce, reconstruct, run_encounter, select_active_sequence,
    transition, validate,
)


class HostLocalLawTests(unittest.TestCase):
    def test_stated_transition_is_applied_before_pulse_readout(self):
        value, state, channel = transition(LAWS['gain_variant'], (1, 2, 0), 'pulse')
        self.assertEqual((value, state, channel), (6, (6, 3, 0), 'x'))

    def test_inspection_is_not_read_only(self):
        outcome, state, channel = transition(LAWS['gain_variant'], (0, 2, 0), 'inspect')
        self.assertEqual((outcome, state, channel), (2, (0, 3, 0), 'z'))
        outcome, unchanged, _ = transition(LAWS['gain_variant'], state, 'observe')
        self.assertEqual(outcome, 0)
        self.assertEqual(unchanged, state)

    def test_hidden_coordinate_stays_invisible_to_declared_actions(self):
        for actions in (('pulse',) * 9, ('pulse', 'inspect', 'pulse', 'observe') * 4):
            for host in ('A', 'B'):
                if host == 'A' and 'inspect' in actions:
                    continue
                a, b = initial_state(), initial_state()
                for action in actions:
                    ay, a, _ = transition(LAWS['reference'], a, action)
                    by, b, _ = transition(LAWS['observational_alias'], b, action)
                    self.assertEqual(ay, by)
                self.assertNotEqual(a, b)  # third hidden coordinate really evolves

    def test_independent_calibrations_not_equated_as_raw_values(self):
        a = produce('A', 'reference', ['pulse'])
        b = produce('B', 'reference', ['pulse'])
        self.assertEqual(a['records'][0]['raw'], 1)
        self.assertEqual(b['records'][0]['raw'], 3)
        self.assertEqual(reconstruct(b['records'] + a['records'], {})['survivors'], sorted(LAWS))

    def test_active_probe_requires_intervention_history(self):
        policy = select_active_sequence(('gain_variant', 'hidden_variant'))
        self.assertEqual(policy['status'], 'discriminating_sequence_found')
        self.assertEqual(policy['actions'], ['inspect', 'pulse'])
        self.assertEqual(policy['partitions'], [['gain_variant'], ['hidden_variant']])
        self.assertEqual(select_active_sequence(('gain_variant', 'hidden_variant'), permits=frozenset())['status'],
                         'no_discriminating_sequence_within_scope')

    def test_indistinguishable_alias_retained(self):
        self.assertEqual(select_active_sequence(('reference', 'observational_alias'))['status'],
                         'no_discriminating_sequence_within_scope')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.a = produce('A', 'gain_variant', ['pulse', 'pulse'])['records']
        self.b = produce('B', 'gain_variant', ['inspect', 'pulse'],
                         frozenset({'inspect:z'}))['records']
        self.grants = {'B': ['inspect:z']}

    def test_cross_host_shuffled_arrival_keeps_local_order(self):
        result = reconstruct(list(reversed(self.a + self.b)), self.grants)
        self.assertEqual(result['survivors'], ['gain_variant'])
        self.assertIsNone(result['global_event_order'])
        self.assertLess(self.b[0]['local_tick'], self.a[0]['local_tick'])

    def test_hash_corruption_refused(self):
        fake = copy.deepcopy(self.a)
        fake[0]['raw'] = 3
        with self.assertRaisesRegex(EvidenceError, 'changed record'):
            reconstruct(fake, {})

    def test_dropped_middle_event_refused(self):
        three = produce('B', 'gain_variant', ['inspect', 'pulse', 'pulse'],
                        frozenset({'inspect:z'}))['records']
        with self.assertRaisesRegex(EvidenceError, 'missing, reordered'):
            reconstruct([three[0], three[2]], self.grants)

    def test_host_duplicate_rejected(self):
        with self.assertRaises(EvidenceError):
            reconstruct([self.a[0], self.a[0]], {})

    def test_local_clock_regression_rejected_even_with_valid_hashes(self):
        fake = copy.deepcopy(self.a)
        fake[1]['local_tick'] = fake[0]['local_tick']
        fake[1]['digest'] = digest({k:v for k,v in fake[1].items() if k != 'digest'})
        with self.assertRaisesRegex(EvidenceError, 'clock regressed'):
            reconstruct(fake, {})

    def test_authority_denied_means_not_a_negative_reading(self):
        denied = produce('B', 'gain_variant', ['pulse', 'inspect', 'pulse'])['records']
        self.assertEqual(denied[1]['status'], 'refused')
        self.assertIsNone(denied[1]['raw'])
        self.assertEqual(denied[2]['raw'], 9)
        result = reconstruct(self.a + denied, {})
        self.assertEqual(result['survivors'], ['gain_variant', 'hidden_variant'])
        # A producing host's claim is insufficient if the verifier's trusted
        # synthetic grant manifest does not authorize the reading.
        with self.assertRaisesRegex(EvidenceError, 'unauthorized inspection'):
            reconstruct(self.a + self.b, {})

    def test_inspection_mutation_changes_later_readout(self):
        # B: inspect reports old z=0, increments z; next pulse sees z=1,
        # so gain_variant produces x'=3 -> raw=7, not non-invasive raw=3.
        self.assertEqual([r['raw'] for r in self.b], [1, 7])
        self.assertNotEqual(self.b[1]['raw'], encode('B', 1))

    def test_opaque_refusal_is_permitted_without_grant(self):
        denied = produce('B', 'gain_variant', ['inspect'])['records']
        self.assertEqual(validate(denied, {})['B'][0]['status'], 'refused')
        self.assertEqual(reconstruct(denied, {})['survivors'], sorted(LAWS))

    def test_strict_schema_and_session_rejected(self):
        for field, value in [('session', 'wrong'), ('action', 'admin'), ('raw', True)]:
            fake = copy.deepcopy(self.a)
            fake[0][field] = value
            fake[0]['digest'] = digest({k:v for k,v in fake[0].items() if k != 'digest'})
            with self.assertRaises(EvidenceError, msg=field):
                reconstruct(fake, {})

    def test_distinct_process_and_independent_verifier(self):
        # Actual localhost subprocess boundaries, not independent hardware.
        result = run_encounter('gain_variant')
        self.assertTrue(result['different_process_ids'])
        self.assertEqual(result['initial_host_A_survivors'], ['gain_variant', 'hidden_variant'])
        self.assertEqual(result['host_B_alone_survivors'], ['both_variant', 'gain_variant'])
        self.assertEqual(result['independent_verifier']['survivors'], ['gain_variant'])
        self.assertEqual(result['noninvasive_inspection_counterfactual'], [1, 3])
        self.assertEqual(result['host_B_actions'], ['inspect', 'pulse'])

    def test_refusal_retains_ambiguity_in_hosted_replay(self):
        result = run_encounter('gain_variant', grant_inspection=False)
        self.assertEqual(result['host_B_statuses'], ['applied','refused','applied'])
        self.assertEqual(result['independent_verifier']['status'], 'unresolved_equivalence_class')
        self.assertEqual(result['independent_verifier']['survivors'], ['gain_variant', 'hidden_variant'])


if __name__ == '__main__':
    unittest.main()
