"""RE-007 bounded active observation, missed/late evidence and scope tests."""
from __future__ import annotations

import copy
import unittest
from partial_observation import (
    LAWS, State, ObservationError, apply_probe, assess_sampling, demo,
    follow_policy, issue_pending, make_request, plan, response,
    result_receipt, sampled_world, verify_receipt,
)

KEY = bytes.fromhex('ab' * 32)


class SamplingTests(unittest.TestCase):
    def test_transient_lives_between_identical_samples(self):
        quiet, transient = sampled_world('quiet'), sampled_world('transient')
        self.assertEqual([quiet[t] for t in (0, 2, 4)], [transient[t] for t in (0, 2, 4)])
        self.assertNotEqual(quiet, transient)

    def test_sampling_does_not_prove_completeness(self):
        result = assess_sampling({0: 0, 2: 0, 4: 0})
        self.assertEqual(result['unsampled_gaps'], [[0, 2], [2, 4]])
        self.assertFalse(result['absence_of_unobserved_events_established'])

    def test_zero_even_at_every_slot_not_absolute_completeness(self):
        result = assess_sampling({0: 0, 1: 0, 2: 0})
        self.assertEqual(result['unsampled_gaps'], [])
        self.assertFalse(result['absence_of_unobserved_events_established'])

    def test_bad_sampling_fails(self):
        with self.assertRaises(ObservationError):
            assess_sampling({1: False})


class ActivePolicyTests(unittest.TestCase):
    def test_initial_ordinary_resonance_is_uninformative(self):
        self.assertEqual({response(law, State(), 'resonance') for law in LAWS}, {0})

    def test_prime_changes_a_state_and_later_response(self):
        state = apply_probe(State(), 'prime')
        self.assertEqual(state.revision, 1)
        self.assertTrue(state.primed)
        self.assertEqual([response(law, state, 'resonance') for law in LAWS], [2, 0, 1])

    def test_first_probe_does_not_itself_identify(self):
        with self.assertRaises(ObservationError):
            response('transient', State(), 'prime')

    def test_observation_cost_minimax_prefers_intervention(self):
        result = plan(dropout_budget=1)
        self.assertTrue(result['worst_case_guarantee'])
        node = result['policy']
        self.assertEqual(node['probe'], 'prime')
        self.assertEqual(node['worst_observation_cost'], 3)
        self.assertEqual(node['worst_intervention_cost'], 1)

    def test_nonintervention_planning_is_costlier(self):
        result = plan(dropout_budget=1, priority='no_intervention')
        node = result['policy']
        self.assertEqual(node['probe'], 'deep')
        self.assertEqual((node['worst_observation_cost'], node['worst_intervention_cost']), (8, 0))

    def test_drop_first_result_does_not_eliminate_truth(self):
        node = plan(dropout_budget=1)['policy']
        for law in LAWS:
            result = follow_policy(node, law, dropped_reads=(0,))
            self.assertEqual(result['identified'], [law])
            self.assertTrue(any(h['outcome'] == 'dropped:no_value' for h in result['history']))

    def test_missing_budget_is_not_finite_guarantee(self):
        self.assertFalse(plan(dropout_budget=None)['worst_case_guarantee'])
        self.assertIsNone(plan(dropout_budget=None)['policy'])

    def test_too_short_horizon_is_unknown(self):
        result = plan(dropout_budget=1, max_actions=1)
        self.assertEqual(result['status'], 'unresolved_within_budget')

    def test_no_unauthorized_prime(self):
        result = plan(dropout_budget=1, permitted=frozenset({'deep'}))
        self.assertEqual(result['policy']['probe'], 'deep')
        self.assertEqual(result['policy']['worst_intervention_cost'], 0)

    def test_no_deep_and_no_prime_is_unknown(self):
        result = plan(dropout_budget=1, permitted=frozenset({'archive', 'snapshot'}))
        self.assertFalse(result['worst_case_guarantee'])

    def test_unadvertised_loss_detected(self):
        node = plan(dropout_budget=1)['policy']
        with self.assertRaisesRegex(ObservationError, 'violates'):
            follow_policy(node, 'quiet', dropped_reads=(0, 1))

    def test_no_floating_expected_probabilities_smuggled_in(self):
        self.assertEqual(plan(dropout_budget=0)['policy']['worst_observation_cost'], 2)


class LateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.req = make_request('trial-001', 'req-0001', 'resonance', 0)
        self.pending, self.capture_value = issue_pending(self.req, state=State(), law='transient')

    def test_late_return_binds_preintervention_capture(self):
        armed = apply_probe(State(), 'prime')
        self.assertEqual(self.capture_value, 0)
        self.assertEqual(response('transient', armed, 'resonance'), 1)
        receipt = result_receipt(self.pending, value=self.capture_value,
                                status='returned', delivered_revision=armed.revision,
                                sensor_key=KEY)
        result = verify_receipt(self.req, self.pending, receipt, sensor_key=KEY)
        self.assertEqual(result['admitted_measurement'], 0)
        self.assertEqual(result['capture_revision'], 0)
        self.assertEqual(result['delivery_revision'], 1)

    def test_pending_is_not_zero(self):
        self.assertIsNone(self.pending['value'])
        self.assertIsNone(self.pending.get('admitted_measurement'))

    def test_drop_is_not_a_negative_measurement(self):
        receipt = result_receipt(self.pending, value=None, status='dropped',
                                delivered_revision=1, sensor_key=KEY)
        result = verify_receipt(self.req, self.pending, receipt, sensor_key=KEY)
        self.assertIsNone(result['admitted_measurement'])
        self.assertEqual(result['status'], 'dropped')

    def test_refusal_is_not_a_negative_measurement(self):
        receipt = result_receipt(self.pending, value=None, status='refused',
                                delivered_revision=1, sensor_key=KEY)
        result = verify_receipt(self.req, self.pending, receipt, sensor_key=KEY)
        self.assertIsNone(result['admitted_measurement'])
        self.assertEqual(result['status'], 'refused')

    def test_missing_result_cannot_carry_nonzero_or_zero(self):
        with self.assertRaises(ObservationError):
            result_receipt(self.pending, value=0, status='dropped',
                           delivered_revision=1, sensor_key=KEY)

    def test_replay_not_accepted(self):
        receipt = result_receipt(self.pending, value=0, status='returned',
                                delivered_revision=1, sensor_key=KEY)
        with self.assertRaisesRegex(ObservationError, 'replayed'):
            verify_receipt(self.req, self.pending, receipt,
                           sensor_key=KEY, already_accepted=frozenset({'req-0001'}))

    def test_wrong_capture_request_refused(self):
        receipt = result_receipt(self.pending, value=0, status='returned',
                                delivered_revision=1, sensor_key=KEY)
        replaced = {**self.req, 'request_id': 'other'}
        with self.assertRaisesRegex(ObservationError, 'binding'):
            verify_receipt(replaced, self.pending, receipt, sensor_key=KEY)

    def test_tampered_result_mac_fails(self):
        receipt = result_receipt(self.pending, value=0, status='returned',
                                delivered_revision=1, sensor_key=KEY)
        changed = copy.deepcopy(receipt)
        changed['value'] = 1
        with self.assertRaisesRegex(ObservationError, 'authentication'):
            verify_receipt(self.req, self.pending, changed, sensor_key=KEY)

    def test_wrong_key_fails(self):
        receipt = result_receipt(self.pending, value=0, status='returned',
                                delivered_revision=1, sensor_key=KEY)
        with self.assertRaisesRegex(ObservationError, 'authentication'):
            verify_receipt(self.req, self.pending, receipt, sensor_key=b'not the key')

    def test_after_capture_revision_needed(self):
        with self.assertRaisesRegex(ObservationError, 'precedes'):
            result_receipt(self.pending, value=0, status='returned',
                           delivered_revision=-1, sensor_key=KEY)


if __name__ == '__main__':
    unittest.main()
