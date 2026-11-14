"""Integration tests: genuine pinned E-CPU on hosted CI; optional local stub."""
import copy
import unittest

from active_recalibration import RenewalError, registration, old_fixture
from ecpu_re013_hosts import source_host, observer_host, verify
from detection_calibration import sha


class RealECPUContractTests(unittest.TestCase):
    def setUp(self):
        self.reg=registration(deterministic=True)
        self.old=old_fixture(self.reg)
        self.source=source_host(self.reg,self.old)
        self.a=observer_host(self.source,self.reg,'A')
        self.b=observer_host(self.source,self.reg,'B')

    def test_actual_causal_handoff_and_conditional_revision(self):
        out=verify(self.source,self.a,self.b,self.old,self.reg,assumptions_accepted=True)
        self.assertEqual(out['causal_relations'],{'S_before_A':'before','S_before_B':'before','A_concurrent_B':'concurrent'})
        self.assertEqual(out['renewal']['status'],'conditional_revision_issued')
        self.assertFalse(out['hardware_sensor_attested'])
        self.assertIsNone(out['cross_host_elapsed'])

    def test_hosted_default_refuses_unproved_assumptions(self):
        out=verify(self.source,self.a,self.b,self.old,self.reg)
        self.assertEqual(out['renewal']['status'],'renewal_not_admitted')

    def test_scoped_observer_never_receives_source_secret(self):
        for role in ('A','B'):
            subset={'challenge':self.reg['challenge'],'key_ids':self.reg['key_ids'],
                    'keys':{role:self.reg['keys'][role]}}
            report=observer_host(self.source,subset,role)
            self.assertEqual(report['role'],role)
        self.assertNotIn('S',subset['keys'])

    def test_source_causal_tamper_refused(self):
        bad=copy.deepcopy(self.source)
        bad['frame']['causal']['vector']['S']=0
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(RenewalError,'binding'):
            verify(bad,self.a,self.b,self.old,self.reg)

    def test_swapping_observer_frame_breaks_signed_binding(self):
        bad=copy.deepcopy(self.a)
        bad['frame']=self.b['frame']
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaises(RenewalError):
            verify(self.source,bad,self.b,self.old,self.reg)

    def test_tampered_source_plan_cannot_be_admitted(self):
        bad=copy.deepcopy(self.source)
        bad['plan']['body']['proposal']['observation_cost']=0
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaises(ValueError):
            verify(bad,self.a,self.b,self.old,self.reg)

    def test_replaced_sensor_refuses_old_scope(self):
        bad=observer_host(self.source,self.reg,'A',sensor='fixture-A@3')
        with self.assertRaisesRegex(RenewalError,'scope'):
            verify(self.source,bad,self.b,self.old,self.reg,assumptions_accepted=True)


if __name__ == '__main__':
    unittest.main()
