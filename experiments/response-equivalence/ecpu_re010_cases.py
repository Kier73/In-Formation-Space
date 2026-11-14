"""RE-010 tests importing actual E-CPU mailcpu.temporal (pinned in CI)."""
import copy
import unittest
from event_origin_commitment import OriginError, registration, sha
from ecpu_re010_hosts import (
    make_controller, source_from_controller, origin_host, observer_host,
    verify, verify_hosted_origin,
)


class ECPUOriginHostTests(unittest.TestCase):
    def setUp(self):
        self.reg=registration(deterministic=True)
        self.c=make_controller(self.reg['challenge'])
        self.s=source_from_controller(self.c,self.reg)
        self.a=observer_host('A',self.s,self.reg)
        self.b=observer_host('B',self.s,self.reg)
        self.o=origin_host(self.c,self.reg)

    def test_actual_ecpu_causal_origin_independence(self):
        r=verify(self.s,self.a,self.b,self.o,self.reg)
        self.assertEqual(r['status'],'scoped_origin_counter_triangle_verified')
        self.assertEqual(r['origin_causal_evidence']['origin_concurrent_A_and_B'],'concurrent')
        self.assertEqual(r['triangulation']['origin_only_epochs'],[3])
        self.assertFalse(r['physical_event_attested'])

    def test_rehash_cannot_forge_signed_origin_stamp(self):
        bad=copy.deepcopy(self.o)
        bad['bindings'][0]['receipt']['stamp']['vector']['C']=0
        bad['bindings'][0]['receipt']['digest']=sha({k:v for k,v in bad['bindings'][0]['receipt'].items() if k!='digest'})
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(OriginError,'HMAC'):
            verify(self.s,self.a,self.b,bad,self.reg)

    def test_rehashed_frame_swap_rejected(self):
        bad=copy.deepcopy(self.o)
        bad['bindings'][0]['frame'],bad['bindings'][1]['frame']=bad['bindings'][1]['frame'],bad['bindings'][0]['frame']
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(OriginError,'binding'):
            verify(self.s,self.a,self.b,bad,self.reg)

    def test_cross_controller_origin_claim_rejected(self):
        wrong=make_controller('an-alternative-controller-challenge')
        with self.assertRaisesRegex(OriginError,'mismatch|identity'):
            verify_hosted_origin(wrong,self.o,self.reg)

    def test_unsupported_physical_attestation_refused(self):
        bad=copy.deepcopy(self.o)
        bad['physical_event_attestation']=True
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(OriginError,'physical'):
            verify(self.s,self.a,self.b,bad,self.reg)

    def test_origin_receipt_does_not_embed_source_or_observer_counts(self):
        for receipt in self.o['origin']['receipts']:
            self.assertNotIn('source',receipt)
            self.assertNotIn('observer',receipt)
            self.assertNotIn('cumulative',receipt)

    def test_origin_receipt_missing_blocked(self):
        bad=copy.deepcopy(self.o)
        del bad['bindings'][1]
        bad['digest']=sha({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(OriginError,'missing'):
            verify_hosted_origin(self.c,bad,self.reg)

if __name__=='__main__':
    unittest.main()