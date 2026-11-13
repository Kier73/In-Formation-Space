"""RE-007 optional true E-CPU TemporalContext integration, run with pinned checkout."""
import copy
import unittest

from ecpu_re007_hosts import controller, enrollment, sensor, verify
from partial_observation import ObservationError, digest, result_receipt


class ActualECpuTests(unittest.TestCase):
    def setUp(self):
        self.reg = enrollment()
        self.ctrl = controller(self.reg['challenge'])
        self.obs = sensor(self.ctrl, self.reg)

    def check(self, *, ctrl=None, obs=None, reg=None):
        return verify(self.ctrl if ctrl is None else ctrl,
                      self.obs if obs is None else obs,
                      self.reg if reg is None else reg)

    def test_real_causal_frame_chain_and_delayed_capture(self):
        r = self.check()
        self.assertEqual(r['survivors'], ['transient'])
        self.assertEqual(r['readings'], [0, 1])
        self.assertEqual(len(r['causal_order']), 5)
        self.assertIsNone(r['cross_host_elapsed'])
        self.assertFalse(r['physical_causation_proved'])

    def test_early_result_not_interpreted_as_post_prime_response(self):
        self.assertEqual(self.check()['delayed_reply_interpreted_at_capture_revision'], 0)

    def test_tampered_sensor_value_rejected_even_with_rehashed_record(self):
        changed = copy.deepcopy(self.obs)
        changed['later']['receipt']['value'] = 2
        changed['digest'] = digest({k:v for k,v in changed.items() if k != 'digest'})
        with self.assertRaisesRegex(ObservationError, 'authentication'):
            self.check(obs=changed)

    def test_stale_causal_order_rejected_with_valid_hmac(self):
        changed = copy.deepcopy(self.obs)
        changed['prime_frame'] = copy.deepcopy(changed['early']['capture_frame'])
        changed['digest'] = digest({k:v for k,v in changed.items() if k != 'digest'})
        with self.assertRaisesRegex(ObservationError, 'causal chain'):
            self.check(obs=changed)

    def test_swapped_post_prime_sensor_frame_rejected(self):
        changed = copy.deepcopy(self.obs)
        changed['later']['delivery_frame'] = copy.deepcopy(changed['early']['delivery_frame'])
        changed['digest'] = digest({k:v for k,v in changed.items() if k != 'digest'})
        with self.assertRaisesRegex(ObservationError, 'sensor frame mismatch'):
            self.check(obs=changed)

    def test_enrollment_swap_fails(self):
        with self.assertRaises(ObservationError):
            self.check(reg=enrollment())

    def test_dropped_late_reading_does_not_identify(self):
        changed = copy.deepcopy(self.obs)
        later = changed['later']
        later['receipt'] = result_receipt(later['pending'], value=None, status='dropped',
            delivered_revision=1, sensor_key=bytes.fromhex(self.reg['sensor_key']),
            sensor_stamp=later['delivery_frame']['causal'])
        changed['digest'] = digest({k:v for k,v in changed.items() if k != 'digest'})
        r = self.check(obs=changed)
        self.assertEqual(sorted(r['survivors']), ['coupled', 'quiet', 'transient'])
        self.assertEqual(r['readings'], [0, None])


if __name__ == '__main__':
    unittest.main(verbosity=2)
