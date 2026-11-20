"""TCN-008: falsification, family obstructions, budget and receipt checks."""
import copy
import json
import unittest

import numpy as np

from intention_ground import (Host, Intent, SynthesizedGround, make_intent,
                              make_receipt, synthesize, verify_receipt)


def phases(p, coefficients):
    return [sum(c * pow(y, k, p) for k, c in enumerate(coefficients)) % p
            for y in range(p)]


def hosts(p):
    return (Host('a-clifford', 2, tuple(range(p)), 1, 1, 4, 100),
            Host('b-cubic', 3, tuple(range(p)), 2, 1, 4, 100),
            Host('c-polynomial', 5, tuple(range(p)), 3, 1, 4, 100))


class IntentionTests(unittest.TestCase):
    def setUp(self):
        self.p = 31
        self.hosts = hosts(self.p)

    def check_case(self, coefficients, expected_degree, family, selected_host):
        intent = make_intent(self.p, phases(self.p, coefficients))
        decision = synthesize(intent, self.hosts)
        self.assertEqual(decision['status'], 'realizable')
        self.assertEqual(decision['selected_host'], selected_host)
        self.assertEqual(decision['ground']['family'], family)
        ground = SynthesizedGround(self.p, tuple(decision['ground']['coefficients']),
                                   decision['ground']['source'])
        self.assertEqual(ground.degree, expected_degree)
        self.assertLess(np.max(np.abs(ground.full_vector() - ground.dense_independent())), 1e-12)
        self.assertTrue(all(ground.relative_residue(x) == r for x, r in intent.constraints))
        self.assertTrue(verify_receipt(make_receipt(intent, self.hosts)))
        return ground

    def test_zero_degree(self):
        self.check_case([0], 0, 'quadratic', 'a-clifford')

    def test_linear_degree(self):
        self.check_case([0, 7], 1, 'quadratic', 'a-clifford')

    def test_quadratic_degree(self):
        self.check_case([0, 7, 4], 2, 'quadratic', 'a-clifford')

    def test_cubic_needs_new_ground(self):
        ground = self.check_case([0, 7, 4, 9], 3, 'cubic', 'b-cubic')
        intent = make_intent(self.p, phases(self.p, [0, 7, 4, 9]))
        refused = synthesize(intent, self.hosts[:1])
        self.assertEqual(refused['status'], 'unreachable_with_declared_hosts')
        self.assertEqual(refused['minimality_witness']['excluded_degree_at_most'], 2)
        self.assertLess(np.max(np.abs(ground.full_vector() - ground.legacy_cubic()._dense_via_blocks())), 1e-12)

    def test_quartic_outside_cubic_then_expanded(self):
        self.check_case([0, 7, 4, 9, 5], 4, 'higher_polynomial', 'c-polynomial')
        intent = make_intent(self.p, phases(self.p, [0, 7, 4, 9, 5]))
        self.assertEqual(synthesize(intent, self.hosts[:2])['status'], 'unreachable_with_declared_hosts')

    def test_quintic_expansion(self):
        self.check_case([0, 0, 1, 0, 0, 3], 5, 'higher_polynomial', 'c-polynomial')

    def test_degree_six_negative_control_with_explicit_obstruction(self):
        intent = make_intent(self.p, phases(self.p, [0,0,0,0,0,0,1]))
        outcome = synthesize(intent, self.hosts)
        self.assertEqual(outcome['status'], 'unreachable_in_degree_5_family')
        proof = outcome['obstruction']
        self.assertEqual(proof['kind'], 'degree_bound_witness')
        self.assertEqual(len(proof['fixed_by']), 6)
        x, target, predicted = proof['first_mismatch']
        self.assertNotEqual(target, predicted)
        self.assertEqual(target, intent.constraints[x][1])
        self.assertTrue(verify_receipt(make_receipt(intent, self.hosts)))

    def test_random_full_target_refused_without_incompressibility_claim(self):
        rng = np.random.default_rng(303)
        target = [int(v) for v in rng.integers(0, self.p, self.p)]
        target[0] = 0
        out = synthesize(make_intent(self.p, target), self.hosts)
        self.assertEqual(out['status'], 'unreachable_in_degree_5_family')
        self.assertNotIn('incompressib', out['reason'])

    def test_partial_constraints_are_not_full_truth(self):
        law = [0, 3, 4, 5]
        points = tuple((x, phases(self.p, law)[x]) for x in (0, 1, 5, 13))
        intent = Intent(self.p, points, 100)
        out = synthesize(intent, self.hosts)
        self.assertEqual(out['status'], 'realizable')
        self.assertEqual(out['ground']['coefficients'], law)
        self.assertFalse(out['complete_target'])
        # Alternate completions outside the four sampled coordinates remain open.
        conflicting = list(phases(self.p, law))
        conflicting[23] = (conflicting[23] + 1) % self.p
        self.assertNotEqual(conflicting, phases(self.p, law))

    def test_limited_sources_can_block_even_quadratic_ground(self):
        intent = make_intent(self.p, phases(self.p, [0, 7, 3]))
        no_source = (Host('one-source', 5, (0,)),)
        out = synthesize(intent, no_source)
        self.assertEqual(out['status'], 'unreachable_with_declared_hosts')

    def test_cost_limit_is_not_unreachable(self):
        intent = make_intent(self.p, phases(self.p, [0, 3, 7, 4]), max_cost=2)
        out = synthesize(intent, self.hosts)
        self.assertEqual(out['status'], 'refused_budget')
        self.assertIsNone(out['selected_host'])

    def test_prefer_cheapest_qualified_host(self):
        p = self.p
        hs = (Host('slow', 5, tuple(range(p)), 11, 1, 5),
              Host('fast', 5, tuple(range(p)), 1, 1, 2))
        intent = make_intent(p, phases(p, [0, 2, 0, 4]))
        out = synthesize(intent, hs)
        self.assertEqual(out['selected_host'], 'fast')
        self.assertEqual(out['estimated_cost'], 4)

    def test_reordered_hosts_tie_breaks_by_name(self):
        p = self.p
        hs = (Host('z', 5, (0,)), Host('a', 5, (0,)))
        out = synthesize(make_intent(p, phases(p, [0,0,1])), hs)
        self.assertEqual(out['selected_host'], 'a')

    def test_independent_dense_for_multiple_primes_and_degrees(self):
        for p in (7, 11, 31, 127):
            for degree in range(6):
                coeffs = tuple([0] + [(2*k+3) % p for k in range(1, degree+1)])
                self.assertTrue(degree < p)
                ground = SynthesizedGround(p, coeffs, coeffs[1] if degree else 0)
                self.assertLess(np.max(np.abs(ground.full_vector() - ground.dense_independent())), 2e-12)
                self.assertAlmostEqual(np.linalg.norm(ground.full_vector()),1.0, places=11)

    def test_huge_coordinate_alias_exact_modular(self):
        g = SynthesizedGround(127, (0, 3, 7, 11, 2, 1), 3)
        giant = 10**200 + 108
        self.assertEqual(g.relative_residue(giant),g.relative_residue(giant % 127))
        self.assertLess(abs(g.amplitude(giant)-g.amplitude(giant%127)),1e-14)

    def test_degree_above_cubic_does_not_claim_legacy_compatibility(self):
        g = SynthesizedGround(31,(0,3,4,5,6),3)
        with self.assertRaisesRegex(ValueError, 'does not support'):
            g.legacy_cubic()

    def test_receipt_tamper_detection_with_recomputed_digest(self):
        i=make_intent(self.p,phases(self.p,[0,1,2,3,4]))
        r=make_receipt(i,self.hosts)
        self.assertTrue(verify_receipt(r))
        for key, value in [('selected_host','fake'),('status','refused_budget'),('estimated_cost',0)]:
            bad=copy.deepcopy(r)
            bad['result'][key]=value
            # Even if an attacker recalculates the unkeyed hash, replay fails.
            bad['sha256']=__import__('hashlib').sha256(json.dumps({k:v for k,v in bad.items() if k!='sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
            self.assertFalse(verify_receipt(bad))

    def test_receipt_full_input_change_does_not_authenticate_source(self):
        i=make_intent(self.p,phases(self.p,[0,1,2]))
        r=make_receipt(i,self.hosts)
        self.assertTrue(verify_receipt(r))
        self.assertFalse(r['authenticated_hosts'])
        self.assertFalse(r['external_realization_witnessed'])

    def test_invalid_inputs_and_canonicality(self):
        with self.assertRaises(ValueError):
            make_intent(9,[0]*9)
        with self.assertRaises(ValueError):
            Intent(11,((0,0),(2,4),(1,2)),10)
        with self.assertRaises(ValueError):
            make_intent(11,[1]*11)
        with self.assertRaises(ValueError):
            make_intent(11,[0]*7)
        with self.assertRaises(ValueError):
            synthesize(make_intent(self.p,[0]*self.p),(Host('x',5,(1,0)),))
        with self.assertRaises(ValueError):
            synthesize(make_intent(self.p,[0]*self.p),(self.hosts[0],self.hosts[0]))
        with self.assertRaises(ValueError):
            SynthesizedGround(11,(0,3,4,2),2)


if __name__=='__main__':
    unittest.main()
