"""Integration regression using the pinned real E-CPU TemporalContext."""
import copy
import unittest

from scoped_intervention_audit import AuditError, enroll, sha, check
from ecpu_re006_hosts import produce_bundle, verify_host


class NativeTemporalAuditTests(unittest.TestCase):
    def setUp(self):
        self.reg = enroll(deterministic=True)
        self.bundle = produce_bundle(self.reg)

    def test_actual_native_frame_bracket(self):
        r=verify_host(self.bundle, self.reg)
        self.assertEqual(r['causal_relations']['M0_N0'],'concurrent')
        self.assertEqual(r['causal_relations']['A1_B0'],'before')
        self.assertFalse(r['identification']['conditional_exclusion_admitted'])

    def test_closed_fixture_qualification_is_not_physical(self):
        r=verify_host(self.bundle, self.reg, model_scope='declared_closed_world')
        self.assertTrue(r['identification']['conditional_exclusion_admitted'])
        self.assertFalse(r['physical_causation_proved'])

    def test_unauthorized_monitor_refusal(self):
        r=verify_host(produce_bundle(self.reg, denied=True), self.reg,
                      model_scope='declared_closed_world')
        self.assertFalse(r['identification']['conditional_exclusion_admitted'])

    def test_sentinel_detects_interference(self):
        r=verify_host(produce_bundle(self.reg, drift=True), self.reg,
                      model_scope='declared_closed_world')
        self.assertFalse(r['identification']['conditional_exclusion_admitted'])

    def test_changing_vector_after_rehash_does_not_override_role_mac(self):
        bad=copy.deepcopy(self.bundle)
        bad['monitor']['causal']['vector']['A']=0
        bad['monitor']['digest']=sha({k:v for k,v in bad['monitor'].items() if k!='digest'})
        with self.assertRaisesRegex(AuditError,'MAC'):
            verify_host(bad,self.reg)

    def test_authority_with_all_keys_still_cannot_forge_history(self):
        # In a shared-key fixture, an issuer can re-sign, but the E-CPU verifier
        # also enforces exact causal vectors / cross-role relationships.
        bad=copy.deepcopy(self.bundle)
        from scoped_intervention_audit import record, close_receipt, plant_receipt
        m=bad['monitor']
        causal=copy.deepcopy(m['causal']); causal['vector']['A']=0
        bad['monitor']=record('monitor',m['payload'],causal,self.reg)
        bad['close']=close_receipt(self.reg,bad['close']['causal'],bad['open'],
                                    bad['monitor'],bad['negative_control'])
        bad['plant']=plant_receipt(self.reg,bad['plant']['causal'],bad['close'])
        with self.assertRaisesRegex(AuditError,'vector'):
            verify_host(bad,self.reg)

    def test_no_global_host_duration_inferred(self):
        self.assertIsNone(verify_host(self.bundle,self.reg)['cross_host_elapsed'])


if __name__ == '__main__':
    unittest.main()

