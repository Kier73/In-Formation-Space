"""RE-009 requires actual mailcpu.temporal; run with pinned E-CPU in CI."""
import copy
import unittest

from common_mode_counter import CounterError, register, sha
from ecpu_common_mode_hosts import source_host, observer_host, verify


class HostedECPURe009Tests(unittest.TestCase):
    def setUp(self):
        self.reg = register(deterministic=True)
        self.s = source_host(self.reg)
        self.a = observer_host('A', self.s, self.reg)
        self.b = observer_host('B', self.s, self.reg)

    def test_real_ecpu_vector_stamps_and_counter_disagreement(self):
        report = verify(self.s, self.a, self.b, self.reg)
        self.assertEqual(report['status'], 'source_counter_discrepancy_verified')
        self.assertEqual(report['counter_reconstruction']['source_observer_discrepancy'], 1)
        self.assertEqual(report['causal_relation']['A_concurrent_B'], 'concurrent')
        self.assertFalse(report['physical_common_mode_loss_proved'])

    def test_changed_controller_frame_refused_even_when_envelope_rehashed(self):
        changed = copy.deepcopy(self.s)
        changed['controller']['frame']['causal']['vector']['C'] = 0
        changed['controller']['digest'] = sha({k:v for k,v in changed['controller'].items() if k != 'digest'})
        changed['digest'] = sha({k:v for k,v in changed.items() if k != 'digest'})
        with self.assertRaisesRegex(CounterError, 'unbound'):
            verify(changed, self.a, self.b, self.reg)

    def test_tampered_signed_acknowledgement_rejected(self):
        bad = copy.deepcopy(self.b)
        bad['ack']['source_head'] = '1' * 64
        bad['ack']['digest'] = sha({k:v for k,v in bad['ack'].items() if k != 'digest'})
        bad['digest'] = sha({k:v for k,v in bad.items() if k != 'digest'})
        with self.assertRaisesRegex(Exception, 'HMAC'):
            verify(self.s, self.a, bad, self.reg)

    def test_rehashed_wrong_observer_causal_binding_rejected(self):
        bad = copy.deepcopy(self.a)
        bad['witness']['bindings'][0]['frame']['causal']['vector']['C'] = 0
        bad['witness']['digest'] = sha({k:v for k,v in bad['witness'].items() if k != 'digest'})
        bad['digest'] = sha({k:v for k,v in bad.items() if k != 'digest'})
        with self.assertRaisesRegex(Exception, 'HMAC|binding'):
            verify(self.s, bad, self.b, self.reg)

    def test_cross_session_ack_replayed_rejected(self):
        other = register(deterministic=True)
        other['challenge'] = 'a-distinct-session-challenge'
        with self.assertRaisesRegex(Exception, 'identity|challenge'):
            verify(self.s, self.a, self.b, other)


if __name__ == '__main__':
    unittest.main()
