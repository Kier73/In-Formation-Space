"""Run with the pinned real E-CPU runtime on GitHub Actions (not a mocked clock)."""
import copy
import unittest

from mailcpu.temporal import CausalRelation
from ecpu_temporal_check import produce_source, produce_receiver, verify
from intervention_or_drift import EvidenceError, digest


class ECpuIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.source = produce_source('triggered_external')
        self.receiver = produce_receiver('triggered_external', self.source['public'], self.source['private'])

    def test_actual_ecpu_causal_stamps_and_model_identification(self):
        result = verify(self.source['public'], self.receiver)
        self.assertEqual(result['causal_relation'], {'A0_A1':'before','A1_B0':'before'})
        self.assertEqual(result['model_reconstruction']['survivors'], ['triggered_external'])
        self.assertIsNone(result['external_event_source_attribution'])
        self.assertIsNone(result['cross_host_elapsed'])

    def test_refusal_is_unobserved_not_negative(self):
        denied = produce_receiver('triggered_external', self.source['public'],
                                  self.source['private'], permitted=False)
        result = verify(self.source['public'], denied)
        self.assertEqual(result['model_reconstruction']['survivors'],
                         ['coordinate_alias','high_gain','triggered_external'])

    def test_frame_swap_is_rejected(self):
        bad = copy.deepcopy(self.source['public'])
        bad['bindings'][0], bad['bindings'][1] = bad['bindings'][1],bad['bindings'][0]
        with self.assertRaisesRegex(EvidenceError, 'commitment'):
            verify(bad, self.receiver)

    def test_rehashed_causal_stamp_does_not_override_vector_relation(self):
        bad = copy.deepcopy(self.receiver)
        frame = bad['bindings'][0]['temporal_frame']
        frame['causal']['vector']['A'] = 0
        bad['bindings'][0]['binding_digest'] = digest({
            'record_digest': bad['bindings'][0]['record_digest'],
            'temporal_frame': frame})
        with self.assertRaisesRegex(EvidenceError, 'causally follow'):
            verify(self.source['public'], bad)

if __name__ == '__main__':
    unittest.main(verbosity=2)
