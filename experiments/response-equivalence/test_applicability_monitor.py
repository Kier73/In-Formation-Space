"""RE-012 regression: certificate admission, drift, malicious receipts, and recovery."""
import copy
import unittest

from applicability_monitor import (
    ApplicabilityError, MAX_LATENCY, assess, calibration, create_certificate,
    fixture, observer, plan, sign, stratum, validate_window, verify_certificate,
    weighted_limit,
)
from detection_calibration import enrollment, CalibrationError


class ApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.reg=enrollment(deterministic=True)
        self.src,self.ba,self.bb=calibration(self.reg)
        self.cert=create_certificate(self.reg,self.src,self.ba,self.bb)
        self.p=plan(self.reg)
        self.a=observer(self.reg,self.p,'A')
        self.b=observer(self.reg,self.p,'B')

    def runcheck(self,p=None,a=None,b=None,**kwargs):
        return assess(self.cert,self.reg,self.src,self.ba,self.bb,
                      self.p if p is None else p,self.a if a is None else a,
                      self.b if b is None else b,**kwargs)

    def test_conditional_baseline_has_explicit_scope(self):
        result=self.runcheck(assumptions_accepted=True)
        self.assertEqual(result['status'],'conditionally_applicable')
        self.assertEqual(result['reasons'],[])
        self.assertIsNone(result['physical_detection_guarantee'])
        self.assertFalse(result['source_truthfulness_verified'])

    def test_default_does_not_infer_assumptions(self):
        self.assertIn('statistical_and_physical_assumptions_unestablished',self.runcheck()['reasons'])
        self.assertEqual(self.runcheck()['status'],'suspended')

    def test_verified_baseline_samples_are_stratified(self):
        body=verify_certificate(self.cert,self.reg,self.src,self.ba,self.bb)
        self.assertEqual(body['calibration_counts']['ordinary'],{'n':48,'joint_misses':0})
        self.assertEqual(body['calibration_counts']['edge'],{'n':12,'joint_misses':0})
        self.assertEqual(sum(body['calibration_counts'][k]['n'] for k in ('ordinary','edge')),60)
        self.assertLess(body['conditional_weighted_upper'],body['max_conditional_miss'])

    def test_per_stratum_confidence_is_not_naive_product(self):
        b=self.cert['body']
        self.assertGreater(b['limits']['edge'],b['limits']['ordinary'])
        self.assertGreater(b['conditional_weighted_upper'], b['limits']['ordinary'])
        self.assertEqual(self.runcheck(assumptions_accepted=True)['sampling_assumptions_explicitly_accepted'],True)

    def test_population_shift_suspends_even_without_missed_event(self):
        p=plan(self.reg,mode='shifted')
        a=observer(self.reg,p,'A');b=observer(self.reg,p,'B')
        result=self.runcheck(p,a,b,assumptions_accepted=True)
        self.assertIn('event_population_shift',result['reasons'])
        self.assertEqual(result['reported_joint_misses'],0)
        self.assertIn('conditional_performance_limit_exceeded',result['reasons'])

    def test_firmware_update_suspends(self):
        a=observer(self.reg,self.p,'A',firmware='detector-2')
        self.assertIn('sensor_configuration_changed',self.runcheck(a=a,assumptions_accepted=True)['reasons'])

    def test_replaced_sensor_uses_valid_key_but_not_valid_calibration(self):
        a=observer(self.reg,self.p,'A',sensor='fixture-A@2')
        self.assertIn('sensor_configuration_changed',self.runcheck(a=a,assumptions_accepted=True)['reasons'])

    def test_latency_exceeded_in_local_sensor_scope(self):
        a=observer(self.reg,self.p,'A',late_slots=(3,))
        r=self.runcheck(a=a,assumptions_accepted=True)
        self.assertIn('latency_envelope_exceeded',r['reasons'])
        self.assertEqual(MAX_LATENCY,50)

    def test_untested_population_is_out_of_scope(self):
        p=plan(self.reg,mode='unseen_stratum')
        r=self.runcheck(p,observer(self.reg,p,'A'),observer(self.reg,p,'B'),assumptions_accepted=True)
        self.assertIn('unrepresented_event_stratum',r['reasons'])
        self.assertIsNone(r['physical_detection_guarantee'])

    def test_targeted_common_mode_violates_operational_trigger(self):
        p=plan(self.reg,mode='edge_focused')
        a=observer(self.reg,p,'A',miss_slots=(2,8))
        b=observer(self.reg,p,'B',miss_slots=(2,8))
        r=self.runcheck(p,a,b,assumptions_accepted=True)
        self.assertIn('observed_joint_miss_trigger',r['reasons'])
        self.assertEqual(r['reported_joint_misses'],2)

    def test_individual_missing_but_no_joint_miss_does_not_trigger(self):
        a=observer(self.reg,self.p,'A',miss_slots=(1,))
        b=observer(self.reg,self.p,'B',miss_slots=(2,))
        self.assertEqual(self.runcheck(a=a,b=b,assumptions_accepted=True)['status'],'conditionally_applicable')

    def test_refusal_is_not_negative_observation(self):
        a=observer(self.reg,self.p,'A',refused_slots=(2,))
        self.assertEqual(a['body']['slots'][2]['status'],'refused')
        self.assertIsNone(a['body']['slots'][2]['event_id'])
        self.assertIsNone(a['body']['slots'][2]['local_latency_ms'])
        self.assertEqual(self.runcheck(a=a,assumptions_accepted=True)['reported_joint_misses'],0)

    def test_both_refuse_counts_against_certification(self):
        a=observer(self.reg,self.p,'A',refused_slots=(2,8))
        b=observer(self.reg,self.p,'B',refused_slots=(2,8))
        self.assertIn('observed_joint_miss_trigger',self.runcheck(a=a,b=b,assumptions_accepted=True)['reasons'])

    def test_certificate_has_finite_window_expiry(self):
        p=plan(self.reg,window=6,parent='a'*64)
        a=observer(self.reg,p,'A');b=observer(self.reg,p,'B')
        self.assertIn('certificate_expired',self.runcheck(p,a,b,expected_window=6,expected_parent='a'*64,
                         assumptions_accepted=True)['reasons'])

    def test_suspension_is_sticky_until_new_calibration(self):
        self.assertIn('previously_suspended_requires_new_calibration',
                      self.runcheck(assumptions_accepted=True,prior_suspended=True)['reasons'])

    def test_valid_window_two_requires_parent(self):
        p=plan(self.reg,window=2,parent=self.p['digest'])
        a=observer(self.reg,p,'A');b=observer(self.reg,p,'B')
        self.assertEqual(self.runcheck(p,a,b,expected_window=2,expected_parent=self.p['digest'],
                                     assumptions_accepted=True)['status'],'conditionally_applicable')
        with self.assertRaisesRegex(ApplicabilityError,'sequence/replay'):
            self.runcheck(p,a,b,expected_window=2,expected_parent='b'*64,assumptions_accepted=True)

    def test_replay_first_window_under_second_window_rejected(self):
        with self.assertRaisesRegex(ApplicabilityError,'sequence/replay'):
            self.runcheck(expected_window=2,expected_parent=self.p['digest'])

    def test_changed_certificate_after_rehash_fails_mac(self):
        bad=copy.deepcopy(self.cert);bad['body']['max_local_latency_ms']=500
        from detection_calibration import sha
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(ApplicabilityError,'HMAC'):
            assess(bad,self.reg,self.src,self.ba,self.bb,self.p,self.a,self.b)

    def test_certificate_signed_by_source_but_inconsistent_baseline_rejected(self):
        doc=copy.deepcopy(self.cert['body']);doc['limits']['edge']=.0
        invalid=sign(self.reg,'S','calibration_certificate',doc)
        with self.assertRaisesRegex(ApplicabilityError,'does not match'):
            assess(invalid,self.reg,self.src,self.ba,self.bb,self.p,self.a,self.b)

    def test_modified_baseline_record_fails(self):
        b=copy.deepcopy(self.ba);b['records'][3]['status']='not_detected'
        with self.assertRaisesRegex(CalibrationError,'HMAC'):
            self.runcheck_baseline(b)

    def runcheck_baseline(self,baseline_a):
        return assess(self.cert,self.reg,self.src,baseline_a,self.bb,self.p,self.a,self.b)

    def test_missing_signed_monitor_sample_rejected(self):
        bad=copy.deepcopy(self.a);bad['body']['slots'].pop()
        with self.assertRaisesRegex(ApplicabilityError,'HMAC'):
            self.runcheck(a=bad)

    def test_signed_incomplete_sample_rejected(self):
        body=copy.deepcopy(self.a['body']);body['slots'].pop()
        bad=sign(self.reg,'A','monitor_observation',body)
        with self.assertRaisesRegex(ApplicabilityError,'missing slots'):
            self.runcheck(a=bad)

    def test_forged_sensor_role_cannot_validate(self):
        bad=copy.deepcopy(self.b);bad['role']='A'
        with self.assertRaisesRegex(ApplicabilityError,'identity mismatch'):
            self.runcheck(b=bad)

    def test_wrong_plan_linkage_rejected(self):
        body=copy.deepcopy(self.a['body']);body['plan_digest']='0'*64
        bad=sign(self.reg,'A','monitor_observation',body)
        with self.assertRaisesRegex(ApplicabilityError,'wrong plan'):
            self.runcheck(a=bad)

    def test_duplicate_or_reordered_samples_rejected(self):
        body=copy.deepcopy(self.b['body']);body['slots'][2],body['slots'][3]=body['slots'][3],body['slots'][2]
        bad=sign(self.reg,'B','monitor_observation',body)
        with self.assertRaisesRegex(ApplicabilityError,'status/identity'):
            self.runcheck(b=bad)

    def test_nondetection_must_not_carry_event_id(self):
        body=copy.deepcopy(self.a['body']);body['slots'][2]['status']='not_detected'
        bad=sign(self.reg,'A','monitor_observation',body)
        with self.assertRaisesRegex(ApplicabilityError,'status/identity'):
            self.runcheck(a=bad)

    def test_unknown_event_population_requires_new_calibration(self):
        p=plan(self.reg,mode='unseen_stratum')
        a=observer(self.reg,p,'A');b=observer(self.reg,p,'B')
        self.assertEqual(self.runcheck(p,a,b,assumptions_accepted=True)['status'],'suspended')

    def test_untruthful_authorized_signer_not_detected_by_crypto(self):
        # Two distinct latent physical worlds: a truthful sensor vs one lying
        # about a concentrated failure. Both have the same signed data.
        report=self.runcheck(assumptions_accepted=True)
        physical_world_a={'missed_real_events':0}
        physical_world_b={'missed_real_events':12}
        self.assertNotEqual(physical_world_a,physical_world_b)
        self.assertEqual(report['status'],'conditionally_applicable')
        self.assertIsNone(report['physical_detection_guarantee'])

    def test_assumption_flag_must_be_explicit_boolean(self):
        with self.assertRaisesRegex(ApplicabilityError,'boolean'):
            self.runcheck(assumptions_accepted='yes')

    def test_source_plan_fork_not_accepted_as_continuation(self):
        fork=plan(self.reg,window=2,parent='a'*64)
        a=observer(self.reg,fork,'A');b=observer(self.reg,fork,'B')
        with self.assertRaisesRegex(ApplicabilityError,'sequence/replay'):
            self.runcheck(fork,a,b,expected_window=2,expected_parent=self.p['digest'])

if __name__=='__main__':unittest.main()
