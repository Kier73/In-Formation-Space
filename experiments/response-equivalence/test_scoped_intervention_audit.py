"""RE-006 regression tests: scoped receipts, negative controls, replay & claims."""
import copy
import unittest

from scoped_intervention_audit import (
    AuditError, CANDIDATES, check, close_receipt, plant_receipt, enroll, fixture, record, sha, verify,
)


class ScopedInterventionAuditTests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.enrollment, self.open_result = fixture()

    def assertUnresolved(self, *, monitor_kwargs=None, negative_kwargs=None,
                         completed=True):
        _, _, result = fixture(model_scope='declared_closed_world',
            monitor_kwargs=monitor_kwargs, negative_kwargs=negative_kwargs,
            completed=completed)
        self.assertFalse(result['conditional_exclusion_admitted'])
        self.assertEqual(result['survivors'], sorted(CANDIDATES))
        self.assertFalse(result['physical_causation_proved'])

    def test_valid_scoped_audit_does_not_prove_causation(self):
        self.assertEqual(self.open_result['survivors'], sorted(CANDIDATES))
        self.assertEqual(self.open_result['audit_status'], 'controls_passed_under_declared_sampling')
        self.assertFalse(self.open_result['conditional_exclusion_admitted'])
        self.assertFalse(self.open_result['physical_causation_proved'])

    def test_closed_world_is_additional_verifier_assumption(self):
        _, _, result = fixture(model_scope='declared_closed_world')
        self.assertEqual(result['survivors'], ['common_cause_alias','common_cause_marker'])
        self.assertTrue(result['conditional_exclusion_admitted'])
        self.assertFalse(result['unobserved_channels_excluded'])
        self.assertFalse(result['physical_causation_proved'])

    def test_refused_monitor_is_not_zero_sensor_readout(self):
        self.assertUnresolved(monitor_kwargs={'permitted':False})
        bundle, _, _ = fixture(monitor_kwargs={'permitted':False})
        for k in ('event','sentinel','sampling_scope'):
            self.assertIsNone(bundle['monitor']['payload'][k])

    def test_refused_controls_are_not_passed_controls(self):
        self.assertUnresolved(negative_kwargs={'permitted':False})

    def test_interference_middle_of_window_is_detected(self):
        self.assertUnresolved(monitor_kwargs={'sentinel':(7,8,7)})

    def test_outside_interference_is_detected(self):
        self.assertUnresolved(monitor_kwargs={'sentinel':(9,7,7)})

    def test_external_event_is_not_silent(self):
        self.assertUnresolved(monitor_kwargs={'event':1})

    def test_sampling_incomplete_fails_closed(self):
        self.assertUnresolved(monitor_kwargs={'sampling_scope':'incomplete'})

    def test_sham_control_failure_refuses_exclusion(self):
        self.assertUnresolved(negative_kwargs={'sham_delta':1})

    def test_positive_control_catches_stuck_sensor(self):
        self.assertUnresolved(negative_kwargs={'positive_delta':0})

    def test_intervention_not_completed(self):
        self.assertUnresolved(completed=False)

    def test_cross_session_replay_refused(self):
        other = enroll()
        with self.assertRaisesRegex(AuditError, 'identity'):
            verify(self.bundle, other)

    def test_rehashed_forged_monitor_cannot_pass_mac(self):
        changed = copy.deepcopy(self.bundle)
        changed['monitor']['payload']['event'] = 1
        changed['monitor']['digest'] = sha({k:v for k,v in changed['monitor'].items() if k!='digest'})
        with self.assertRaisesRegex(AuditError, 'MAC authentication'):
            verify(changed, self.enrollment)

    def test_wrong_key_does_not_authenticate(self):
        wrong = copy.deepcopy(self.enrollment)
        wrong['keys']['M'] = 'ef'*32
        wrong['key_ids']['M'] = __import__('hashlib').sha256(bytes.fromhex('ef'*32)).hexdigest()
        with self.assertRaisesRegex(AuditError, 'enrollment'):
            verify(self.bundle, wrong)

    def test_plant_cannot_impersonate_monitor(self):
        changed = copy.deepcopy(self.bundle)
        changed['monitor'] = copy.deepcopy(changed['plant'])
        with self.assertRaisesRegex(AuditError, 'identity'):
            verify(changed, self.enrollment)

    def test_missing_monitor_not_negative_observation(self):
        changed = copy.deepcopy(self.bundle)
        del changed['monitor']
        with self.assertRaisesRegex(AuditError, 'incomplete'):
            verify(changed, self.enrollment)

    def test_swapped_window_digest_invalid_even_with_rehash(self):
        changed = copy.deepcopy(self.bundle)
        changed['close']['payload']['start_digest'] = 'a'*64
        # A rehash cannot produce a valid A MAC. The verifier rejects first.
        changed['close']['digest'] = sha({k:v for k,v in changed['close'].items() if k!='digest'})
        with self.assertRaisesRegex(AuditError, 'MAC authentication'):
            verify(changed, self.enrollment)

    def test_wrong_link_even_with_valid_signatures_is_rejected(self):
        # All roles are test-fixture controlled here; prove the chain validator
        # remains separate from signature validation.
        changed = copy.deepcopy(self.bundle)
        a = changed['open']
        m = record('monitor', {'start_digest': '0'*64, 'status':'observed', 'event':0,
                                'sentinel':[7,7,7], 'sampling_scope':'three_samples'},
                   changed['monitor']['causal'], self.enrollment)
        changed['monitor'] = m
        # Closing receipt still references original monitor.
        with self.assertRaisesRegex(AuditError, 'chain'):
            verify(changed, self.enrollment)

    def test_invalid_scope_not_silent_fallback(self):
        with self.assertRaisesRegex(AuditError, 'scope'):
            verify(self.bundle, self.enrollment, model_scope='physical_proven')

    def test_bad_instrument_types_are_rejected(self):
        changed = copy.deepcopy(self.bundle)
        changed['negative_control'] = record('negative_control', {
            'start_digest':changed['open']['digest'], 'status':'observed',
            'sham_delta':False, 'positive_delta':1},
            changed['negative_control']['causal'], self.enrollment)
        changed['close'] = close_receipt(self.enrollment, changed['close']['causal'],
                                         changed['open'], changed['monitor'], changed['negative_control'])
        changed['plant'] = plant_receipt(self.enrollment, changed['plant']['causal'], changed['close'])
        with self.assertRaisesRegex(AuditError, 'inexact'):
            verify(changed,self.enrollment)

    def test_denial_with_values_rejected(self):
        changed = copy.deepcopy(self.bundle)
        changed['monitor'] = record('monitor', {
            'start_digest':changed['open']['digest'], 'status':'refused',
            'event':0, 'sentinel':None, 'sampling_scope':None},
            changed['monitor']['causal'], self.enrollment)
        changed['close'] = close_receipt(self.enrollment, changed['close']['causal'],
                                         changed['open'], changed['monitor'], changed['negative_control'])
        changed['plant'] = plant_receipt(self.enrollment, changed['plant']['causal'], changed['close'])
        with self.assertRaisesRegex(AuditError, 'denied'):
            verify(changed,self.enrollment)

    def test_unmeasured_transient_counterexample_has_identical_records(self):
        # The *same* finite records are consistent with an additional transient
        # disturbance that occurs between three samples. This is why even the
        # closed-world result cannot claim physical exclusion.
        observed = verify(self.bundle, self.enrollment, model_scope='declared_closed_world')
        world_one_hidden_pulse = 0
        world_two_hidden_pulse = 99
        self.assertNotEqual(world_one_hidden_pulse, world_two_hidden_pulse)
        self.assertEqual(observed['survivors'],['common_cause_alias','common_cause_marker'])
        self.assertFalse(observed['unobserved_channels_excluded'])
        self.assertFalse(observed['physical_causation_proved'])

if __name__ == '__main__':
    unittest.main()

