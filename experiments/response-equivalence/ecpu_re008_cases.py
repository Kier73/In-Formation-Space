"""RE-008 temporal integration tests; MUST run with pinned, genuine E-CPU."""
import copy
import unittest

from ecpu_coverage_hosts import controller, verify, witness
from coverage_reconstruction import CoverageError, enrollment, sha


class ECPUCoverageTests(unittest.TestCase):
    def setUp(self):
        self.reg = enrollment(deterministic=True)
        self.ctrl = controller(self.reg['challenge'])
        self.a = witness('A', self.ctrl, self.reg)
        self.b = witness('B', self.ctrl, self.reg)

    def test_real_ecpu_handoff_and_concurrent_observer_stamps(self):
        result = verify(self.ctrl, self.a, self.b, self.reg)
        self.assertEqual(result['causal_relation']['A_concurrent_B'], 'concurrent')
        self.assertEqual(result['coverage']['blind_epoch_bound'], 0)
        self.assertEqual(result['coverage']['slots'][6]['status'], 'corroborated_present')
        self.assertIsNone(result['cross_host_elapsed'])
        self.assertIsNone(result['external_event_loss_bound'])

    def test_role_binding_tamper_rejected_even_when_envelope_rehashed(self):
        bad = copy.deepcopy(self.a)
        bad['bindings'][1]['receipt']['slot_digest'] = '0' * 64
        bad['digest'] = sha({k: v for k,v in bad.items() if k != 'digest'})
        with self.assertRaisesRegex(CoverageError, 'HMAC'):
            verify(self.ctrl, bad, self.b, self.reg)

    def test_frame_swap_after_rehash_rejected(self):
        bad = copy.deepcopy(self.a)
        bad['bindings'][0]['frame'], bad['bindings'][1]['frame'] = (
            bad['bindings'][1]['frame'], bad['bindings'][0]['frame'])
        bad['digest'] = sha({k:v for k,v in bad.items() if k != 'digest'})
        with self.assertRaisesRegex(CoverageError, 'binding'):
            verify(self.ctrl, bad, self.b, self.reg)

    def test_delivery_without_causal_progression_rejected(self):
        bad = copy.deepcopy(self.a)
        bad['delivery_frame'] = copy.deepcopy(bad['bindings'][-1]['frame'])
        bad['digest'] = sha({k:v for k,v in bad.items() if k != 'digest'})
        with self.assertRaisesRegex(CoverageError, 'delivery not causally'):
            verify(self.ctrl, bad, self.b, self.reg)

    def test_untrusted_coverage_claim_rejected(self):
        bad = copy.deepcopy(self.b)
        bad['physical_sensor_attestation'] = True
        bad['digest'] = sha({k:v for k,v in bad.items() if k != 'digest'})
        with self.assertRaisesRegex(CoverageError, 'unsupported physical'):
            verify(self.ctrl, self.a, bad, self.reg)

    def test_bad_controller_challenge_rejected(self):
        bad = copy.deepcopy(self.ctrl)
        bad['challenge'] = 'f' * 48
        bad['digest'] = sha({k:v for k,v in bad.items() if k != 'digest'})
        with self.assertRaisesRegex(CoverageError, 'challenge'):
            verify(bad, self.a, self.b, self.reg)


if __name__ == '__main__':
    unittest.main()
