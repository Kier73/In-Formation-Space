import unittest
from fractions import Fraction as Q

from active_resonance import (
    Probe, analyze, candidates, choose_probe, compare_event_clock_shapes,
    navigate, normalized_rdm, partition, probe_catalogue,
)


class ActiveResonanceTests(unittest.TestCase):
    def setUp(self):
        self.models = candidates()
        self.names = tuple(sorted(self.models))
        self.probes = probe_catalogue()

    def test_primary_only_cannot_discriminate(self):
        self.assertEqual(len(partition(self.models, self.probes[0], self.names)), 1)

    def test_active_secondary_probe_separates_laws(self):
        selected = choose_probe(self.models, self.names)
        self.assertEqual(selected.name, 'secondary_v')
        self.assertEqual(len(partition(self.models, selected, self.names)), 3)

    def test_hidden_mode_and_coordinate_alias_same_primary(self):
        for p in self.probes[:2]:
            ref = self.models['baseline'].predict(p)
            self.assertEqual(self.models['hidden_extra_mode'].predict(p), ref)
            self.assertEqual(self.models['coordinate_alias'].predict(p), ref)

    def test_refusal_is_not_negative_measurement(self):
        result = navigate('baseline')
        self.assertEqual(result['survivors'],
                         ['baseline', 'coordinate_alias', 'hidden_extra_mode'])
        refused = [s for s in result['steps'] if s['stage'] == 'evidence_refused']
        self.assertEqual(len(refused), 1)
        self.assertNotIn('observation', refused[0])
        self.assertEqual(refused[0]['before'], refused[0]['after'])

    def test_authorized_auxiliary_refines_not_overclaims(self):
        result = navigate('baseline', frozenset({'auxiliary_read'}))
        self.assertEqual(result['survivors'], ['baseline', 'coordinate_alias'])
        self.assertEqual(result['status'], 'unresolved_equivalence_class')

    def test_authorized_auxiliary_reveals_hidden_candidate(self):
        result = navigate('hidden_extra_mode', frozenset({'auxiliary_read'}))
        self.assertEqual(result['survivors'], ['hidden_extra_mode'])
        self.assertEqual(result['status'], 'singleton_within_declared_candidates')

    def test_same_mode_poles_not_equal_response(self):
        second = self.probes[1]
        left = self.models['baseline'].predict(second)
        self.assertNotEqual(left, self.models['alternate_third'].predict(second))
        self.assertNotEqual(left, self.models['alternate_three_quarters'].predict(second))

    def test_affine_readout_invariant_normalized_rdm(self):
        base = self.models['baseline']
        traces = {p.name: base.predict(p) for p in self.probes[:2]}
        traces['combined'] = tuple(sum(v) for v in zip(*traces.values()))
        first = normalized_rdm(traces)
        second = normalized_rdm({k: tuple(-7*x+13 for x in v)
                                 for k,v in traces.items()})
        self.assertEqual(first, second)

    def test_nonlinear_readout_does_not_preserve_geometry(self):
        base = self.models['baseline']
        traces = {p.name: base.predict(p) for p in self.probes[:2]}
        traces['combined'] = tuple(sum(v) for v in zip(*traces.values()))
        square = {k: tuple(x*x for x in v) for k,v in traces.items()}
        self.assertNotEqual(normalized_rdm(traces), normalized_rdm(square))

    def test_invalid_undistinguishable_rdm(self):
        with self.assertRaises(ValueError):
            normalized_rdm({'a': (Q(0),), 'b': (Q(0),)})

    def test_independent_clocks_with_given_correspondence(self):
        latent = [Q(0), Q(1), Q(4), Q(6), Q(11)]
        a = tuple((f'e{i}', Q(5)+2*t) for i,t in enumerate(latent))
        b = tuple((f'e{i}', Q(-11)+3*t) for i,t in enumerate(latent))
        result = compare_event_clock_shapes(a,b)
        self.assertEqual(result['status'], 'matched_interval_shape')
        self.assertFalse(result['causal_order_established'])

    def test_unpaired_events_remain_unresolved(self):
        a = (('a',Q(0)),('b',Q(1)),('c',Q(4)))
        b = (('z',Q(5)),('x',Q(8)),('y',Q(17)))
        self.assertEqual(compare_event_clock_shapes(a,b)['status'],
                         'unresolved_unpaired_event_ids')
        with self.assertRaises(ValueError):
            compare_event_clock_shapes(a, (('a',Q(0)),('b',Q(0)),('c',Q(1))))

    def test_summary(self):
        report = analyze()
        self.assertTrue(report['normalized_affine_sensor_rdm_equal'])
        self.assertEqual(report['minimax_first_probe'], 'secondary_v')


if __name__ == '__main__':
    unittest.main()
