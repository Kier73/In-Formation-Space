"""Adversarial and independent direct-FFT checks for TCN-002."""
from __future__ import annotations

import copy
from fractions import Fraction
import unittest

import numpy as np

from transfer import (Ground, Ray, _mm, diagnose_quadratic_ray,
                      direct_transfer, fidelity, verify_receipt, quadratic_frame_audit)


class ExactSymplecticTests(unittest.TestCase):
    def test_complete_small_prime_matrix_and_ray_against_independent_fft(self):
        # Includes 3 mod 4 and 1 mod 4 primes and different input sites.
        for p in (5, 7, 11, 17, 31):
            for pattern in ((0,), (3,), (2, 5, 7)):
                ground = Ground(p, pattern)
                for source in (0, 1, 3):
                    direct = np.zeros(p, dtype=complex)
                    direct[source] = 1
                    x = np.arange(p)
                    for n in range(25):
                        ray, matrix, _ = ground.navigate(n, source)
                        self.assertEqual((matrix[0][0]*matrix[1][1]
                                          - matrix[0][1]*matrix[1][0]) % p, 1)
                        self.assertGreater(fidelity(ray, direct), 1-2e-11,
                                           (p, pattern, source, n, ray))
                        # Independent reference uses actual complex p-vector FFT.
                        direct = np.fft.ifft(direct) * np.sqrt(p)
                        a = pattern[n % len(pattern)]
                        direct *= np.exp(2j*np.pi*((a*x*x) % p)/p)

    def test_matrix_periodic_order(self):
        g = Ground(101, (7, 13, 29))
        for n in range(35):
            matrix, _ = g.advance_matrix(n)
            left, _ = g.advance_matrix(n+3)
            cycle, _ = g.advance_matrix(3)
            self.assertEqual(left, _mm(matrix, cycle, g.p))

    def test_huge_integer_and_finite_cost(self):
        g = Ground(101, (7, 13, 29))
        huge = 10**100 + 123
        ray, matrix, products = g.navigate(huge, source=33)
        self.assertEqual(matrix, ((19,67),(59,38)))
        self.assertEqual(ray, Ray(101, 'flat', a=44, b=99))
        self.assertLess(products, 6*huge.bit_length())
        self.assertEqual(ray.probability(5), Fraction(1,101))
        self.assertEqual(g.advance_matrix(0), (((1,0),(0,1)),0))
        self.assertEqual(g.advance_matrix(1)[1], 1)

    def test_goal_coordinates_are_exact_quadratic_roots(self):
        g = Ground(127,(17,31,7))
        for n in range(1,8):
            ray,_,_=g.navigate(n,42)
            if ray.kind == 'delta':
                with self.assertRaises(ValueError):
                    ray.goal_coordinates(3)
                continue
            for h in range(127):
                expected = tuple(x for x in range(127)
                                 if ray.relative_phase_residue(x,0) == h)
                self.assertEqual(ray.goal_coordinates(h), expected)

    def test_exact_rational_flatness_and_delta(self):
        g = Ground(101,(7,13,29))
        for n in range(12):
            ray,_,_=g.navigate(n,17)
            weights = [ray.probability(x) for x in range(101)]
            self.assertEqual(sum(weights),1)
            nonzero = sorted(set(w for w in weights if w))
            self.assertTrue(nonzero in ([Fraction(1)], [Fraction(1,101)]))
            if ray.kind == 'flat':
                # Even after long interference, arbitrary marked sets are not
                # given constructive relative probability amplification.
                self.assertEqual(sum(weights[5:11]), Fraction(6,101))

    def test_receipt_independent_recomputation_and_tamper(self):
        g=Ground(101,(7,13,29))
        r=g.receipt(10**100+123,33)
        self.assertTrue(verify_receipt(r))
        self.assertEqual(len(r['sha256']),64)
        for path in ('source','steps_decimal','pattern','matrix','ray', 'sha256'):
            changed=copy.deepcopy(r)
            if path=='source':changed[path]=1
            if path=='steps_decimal':changed[path]='123'
            if path=='pattern':changed[path][1]=12
            if path=='matrix':changed[path][0][0]=20
            if path=='ray':changed[path]['b']=12
            if path=='sha256':changed[path]='0'*64
            self.assertFalse(verify_receipt(changed),path)
        changed=copy.deepcopy(r)
        changed['ray']['b']=12
        # Re-hashing cannot impersonate a valid recomputed mathematical claim.
        from transfer import _digest
        changed['sha256']=_digest({k:v for k,v in changed.items() if k!='sha256'})
        self.assertFalse(verify_receipt(changed))
        self.assertFalse(verify_receipt({**r,'steps_decimal':'0001'}))
        self.assertFalse(verify_receipt({**r,'independent_measurement':True}))

    def test_unitarity_in_direct_state_and_global_gauge(self):
        g=Ground(97,(4,0,12))
        direct=direct_transfer(97,g.pattern,117,7)
        ray,_,_=g.navigate(117,7)
        self.assertAlmostEqual(float(np.vdot(direct,direct).real),1,places=11)
        self.assertGreater(fidelity(ray,direct*np.exp(0.83j)),1-1e-10)

    def test_finite_operator_order_and_inverse_temporal_navigation(self):
        for p in (3,5,7,11,17,31,101):
            for pattern in ((0,), (3,), (3,4,0)):
                g=Ground(p,pattern)
                bound=g.operator_period_bound()
                self.assertGreater(bound,0)
                self.assertEqual(g.advance_matrix(bound)[0],((1,0),(0,1)))
                for n in range(min(35,bound)):
                    matrix,_=g.advance_matrix(n)
                    found=g.find_operator_coordinate(matrix)
                    self.assertIsNotNone(found)
                    self.assertLessEqual(found,n)
                    self.assertEqual(g.advance_matrix(found)[0],matrix)
                # The giant-index operator aliases a bounded finite orbit.
                huge=10**100+123
                matrix,_=g.advance_matrix(huge)
                earliest=g.find_operator_coordinate(matrix)
                self.assertLess(earliest,bound)
                self.assertEqual(g.advance_matrix(earliest)[0],matrix)

    def test_nonmember_inverse_and_invalid_matrix(self):
        g=Ground(11,(0,))
        self.assertIsNone(g.find_operator_coordinate(((1,1),(0,1))))
        with self.assertRaises(ValueError):
            g.find_operator_coordinate(((1,0),(0,0)))
        with self.assertRaises(ValueError):
            g.find_operator_coordinate(((1,0),))

    def test_quadratic_frame_compression_and_nonquadratic_rank(self):
        p=31
        x=np.arange(p)
        quadratic=np.exp(2j*np.pi*((7*x*x+11*x+4)%p)/p)/np.sqrt(p)
        cubic=np.exp(2j*np.pi*((x**3)%p)/p)/np.sqrt(p)
        random_phase=np.exp(2j*np.pi*np.random.default_rng(2026).random(p))/np.sqrt(p)
        first=quadratic_frame_audit(quadratic,p)
        self.assertEqual(first['modes_for_target'],1)
        self.assertEqual((first['best_curvature'],first['best_frequency']),(7,11))
        self.assertGreater(first['best_single_mode_fidelity'],1-1e-12)
        self.assertGreater(quadratic_frame_audit(cubic,p)['modes_for_target'],15)
        self.assertGreater(quadratic_frame_audit(random_phase,p)['modes_for_target'],15)
        self.assertEqual(first['transform_candidates'],p*p)

    def test_frame_audit_not_automatic_navigational_authority(self):
        p=31
        x=np.arange(p)
        signal=np.exp(2j*np.pi*((x**3)%p)/p)/np.sqrt(p)
        for threshold in (0.5,0.9,0.99,1.0):
            result=quadratic_frame_audit(signal,p,energy_target=threshold)
            self.assertGreaterEqual(result['captured_energy']+1e-10,threshold)
        with self.assertRaises(ValueError):
            quadratic_frame_audit(signal,p,energy_target=1.1)
        with self.assertRaises(ValueError):
            quadratic_frame_audit(np.zeros(p),p)

    def test_no_absolute_phase_claim(self):
        g=Ground(11,(3,))
        ray,_,_=g.navigate(2,1)
        direct=direct_transfer(11,g.pattern,2,1)
        self.assertGreater(fidelity(ray,direct),1-1e-12)
        self.assertEqual(ray.description()['global_phase'],'unobserved')
        self.assertAlmostEqual(ray.probability(3),Fraction(1,11))

    def test_explicit_in_family_closure_diagnostic(self):
        for p in (5,7,11,31,101):
            g=Ground(p,(3,7,0))
            for n in range(11):
                v=direct_transfer(p,g.pattern,n,source=2)
                result=diagnose_quadratic_ray(v,p)
                self.assertTrue(result['admitted'],(p,n,result))
                ray,_,_=g.navigate(n,2)
                if ray.kind=='flat':
                    self.assertEqual((result['a'],result['b']),(ray.a,ray.b))
                else:
                    self.assertEqual(result['site'],ray.site)

    def test_nonquadratic_cubic_phase_breaks_closure(self):
        p=31
        x=np.arange(p)
        initial=np.zeros(p,complex)
        initial[0]=1
        # A cubic, rather than quadratic, diagonal oracle D_f.
        actual=np.fft.ifft(initial)*np.sqrt(p)*np.exp(2j*np.pi*((x**3)%p)/p)
        self.assertFalse(diagnose_quadratic_ray(actual,p)['admitted'])
        quadratic=Ground(p,(0,)).navigate(1)[0]
        self.assertLess(fidelity(quadratic,actual),0.5)

    def test_nonflat_generic_state_refused(self):
        p=31
        rng=np.random.default_rng(2026)
        random_complex=rng.normal(size=p)+1j*rng.normal(size=p)
        self.assertFalse(diagnose_quadratic_ray(random_complex,p)['admitted'])

    def test_phases_relative_not_global(self):
        r=Ray(101,'flat',a=4,b=9)
        for x in range(101):
            for y in (0,1,7):
                residue=r.relative_phase_residue(x,y)
                v=r.relative_profile()
                self.assertAlmostEqual(abs(v[x]/v[y] - np.exp(2j*np.pi*residue/101)),0,places=12)
        delta=Ray(101,'delta',site=33)
        self.assertIsNone(delta.relative_phase_residue(0,33))
        self.assertEqual(delta.relative_phase_residue(33,33),0)

    def test_bad_inputs_are_refused(self):
        for p in (2,9,15,0,1,True):
            with self.assertRaises(ValueError):
                Ground(p,(1,))
        for pattern in ((),[1],(1.5,),('2',),tuple([1]*257)):
            with self.assertRaises(ValueError):
                Ground(11,pattern)
        g=Ground(11,(5,))
        for step in (-1,1.5,True):
            with self.assertRaises(ValueError):
                g.navigate(step)
        with self.assertRaises(ValueError):
            g.navigate(4,source=3.5)
        with self.assertRaises(ValueError):
            Ray(11,'flat',a=2)
        with self.assertRaises(ValueError):
            Ray(11,'delta',site=0,a=3)
        with self.assertRaises(ValueError):
            Ray(11,'unknown',site=0)

    def test_unknown_schedule_cannot_be_inferred_from_nice_output(self):
        p=101
        assumed=Ground(p,(5,11))
        true=Ground(p,(5,11,17))
        # Both methods are exact *for their own premise*, but inaccurate
        # for a different schedule; the receipt cannot authorize the premise.
        actual=direct_transfer(p,true.pattern,12,3)
        model=assumed.navigate(12,3)[0]
        self.assertLess(fidelity(model,actual),0.10)
        self.assertTrue(verify_receipt(assumed.receipt(12,3)))


if __name__=='__main__':
    unittest.main()
