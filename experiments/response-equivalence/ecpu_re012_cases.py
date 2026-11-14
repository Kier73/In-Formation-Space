"""RE-012 integration tests: run with actual pinned E-CPU in GitHub Actions."""
import copy
import unittest

from detection_calibration import enrollment,sha
from applicability_monitor import ApplicabilityError, sign
from ecpu_re012_hosts import source_host, observer_host, verify

class ECPUApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.reg=enrollment(deterministic=True)
        self.s=source_host(self.reg)
        self.a=observer_host(self.s,self.reg,'A')
        self.b=observer_host(self.s,self.reg,'B')

    def test_genuine_vector_handoff_and_explicit_statistical_scope(self):
        res=verify(self.s,self.a,self.b,self.reg)
        self.assertEqual(res['causal_relations']['A_concurrent_B'],'concurrent')
        self.assertEqual(res['applicability']['status'],'suspended')
        self.assertIn('statistical_and_physical_assumptions_unestablished',res['applicability']['reasons'])
        self.assertIsNone(res['hosted_physical_detection_guarantee'])

    def test_model_only_explicit_hypothesis_admits_baseline(self):
        res=verify(self.s,self.a,self.b,self.reg,assumptions_accepted=True)
        self.assertEqual(res['applicability']['status'],'conditionally_applicable')
        self.assertFalse(res['physical_sensor_identity_verified'])

    def test_changed_sensor_id_remains_signed_but_suspended(self):
        replaced=observer_host(self.s,self.reg,'A',sensor='new-hardware')
        res=verify(self.s,replaced,self.b,self.reg,assumptions_accepted=True)
        self.assertIn('sensor_configuration_changed',res['applicability']['reasons'])

    def test_latency_breaks_scope(self):
        late=observer_host(self.s,self.reg,'B',late_slots=(2,))
        res=verify(self.s,self.a,late,self.reg,assumptions_accepted=True)
        self.assertIn('latency_envelope_exceeded',res['applicability']['reasons'])

    def test_altered_report_signed_binding_fails(self):
        bad=copy.deepcopy(self.a)
        body=copy.deepcopy(bad['report']['body']);body['slots'][0]['status']='not_detected'
        body['slots'][0]['event_id']=None
        bad['report']=sign(self.reg,'A','monitor_observation',body)
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(ApplicabilityError,'binding mismatched'):
            verify(self.s,bad,self.b,self.reg)

    def test_causal_stamp_rewrite_with_compatible_outer_hash_fails(self):
        bad=copy.deepcopy(self.b)
        bad['frame']['causal']['vector']['S']=0
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(ApplicabilityError,'binding mismatched'):
            verify(self.s,self.a,bad,self.reg)

    def test_wrong_source_challenge_rejected(self):
        bad=copy.deepcopy(self.s)
        bad['challenge']='evil-session'
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(ApplicabilityError,'challenge'):
            verify(bad,self.a,self.b,self.reg)

if __name__=='__main__':unittest.main()
