"""Adversarial tests for TCN-001."""
import math
import unittest
import numpy as np
from theta_cayley import admit, _phase, _sqrt_mod, independent_test, plain_fourier_coherence, three_point_quantized

P = 127


def fixture(a=17, b=31, c=7, sigma=0.17, seed=912):
    rng = np.random.default_rng(seed)
    ids = rng.permutation(P)
    x, vx, tx = ids[:77], ids[77:102], ids[102:]
    y = _phase(P, a, b, c, np.arange(P))
    if sigma:
        y += sigma*(rng.normal(size=P)+1j*rng.normal(size=P))
    return x, y[x], vx, y[vx], tx, y[tx], y


class PhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample = fixture()
        cls.good = admit(P, *cls.sample[:4])

    def test_three_point_baseline_clean_vs_noisy(self):
        pristine=_phase(P,17,31,7,[0,1,2])
        self.assertEqual(three_point_quantized(P,pristine),(17,31,7))
        rng=np.random.default_rng(2026)
        measured=pristine+0.15*(rng.normal(size=3)+1j*rng.normal(size=3))
        self.assertNotEqual(three_point_quantized(P,measured),(17,31,7))

    def test_noisy_curvature_recovered(self):
        g = self.good
        self.assertEqual(g.decision, 'qualified')
        self.assertEqual((g.a, g.b, g.c), (17,31,7))
        self.assertLess(g.validation_rmse, 0.4)
        self.assertLessEqual(g.permutation_pvalue, 0.05)
        self.assertEqual(independent_test(g, *self.sample[4:6])['status'], 'corroborated')

    def test_frequency_only_fft_loses_quadratic_structure(self):
        x, y = self.sample[:2]
        self.assertLess(plain_fourier_coherence(P, x, y), 0.40)
        self.assertGreater(self.good.training_coherence, 0.9)

    def test_cayley_skew_hermiticity_and_arbitrary_large_jump(self):
        g = self.good
        s = g.cayley_generator()
        self.assertAlmostEqual(s.real, 0.0, places=12)
        u = (1-s)/(1+s)
        self.assertAlmostEqual(abs(u), 1.0, places=12)
        for n in (0,1,4,100,1_000_000_000_123):
            y, products = g.navigate_cayley(12, n, allow_unwitnessed=True)
            self.assertLess(abs(y-g.predict(12+n,allow_unwitnessed=True)), 2e-12)
            self.assertLessEqual(products, 14)

    def test_unwitnessed_requires_explicit_optin(self):
        g=self.good
        unwitnessed=next(i for i in range(P) if i not in g.validation_indices)
        with self.assertRaisesRegex(ValueError,'unwitnessed'):
            g.predict(unwitnessed)
        self.assertAlmostEqual(abs(g.predict(unwitnessed,allow_unwitnessed=True)),1.0)
        with self.assertRaisesRegex(ValueError,'unwitnessed'):
            g.navigate_cayley(0,unwitnessed)

    def test_goal_inverse_zero_one_two_roots(self):
        g=self.good
        for target in range(P):
            solutions=g.goal_coordinates(target)
            brute=tuple(i for i in range(P) if (g.a*i*i+g.b*i)%P==target)
            self.assertEqual(solutions,brute)
        self.assertEqual(len(g.goal_coordinates(0)),2)

    def test_tonelli_shanks_generic_primes(self):
        for p in (5,13,17,41,127):
            for x in range(p):
                n=x*x%p
                self.assertEqual(_sqrt_mod(n,p)**2%p,n)

    def test_linear_chirp_and_random_refusal(self):
        f=fixture(a=0,b=29,c=9,sigma=0.17,seed=44)
        g=admit(P,*f[:4],seed=77)
        self.assertEqual(g.decision,'qualified')
        self.assertEqual((g.a,g.b,g.c),(0,29,9))
        self.assertEqual(g.goal_coordinates(29),(1,))
        x,_,vx,_,_,_,_=self.sample
        rng=np.random.default_rng(233)
        random_phases=np.exp(2j*np.pi*rng.random(P))
        bad=admit(P,x,random_phases[x],vx,random_phases[vx])
        self.assertEqual(bad.decision,'refused')
        with self.assertRaisesRegex(ValueError,'refused'):
            bad.goal_coordinates(4)

    def test_training_regime_change_validation_refusal(self):
        x,_,vx,_,_,_,_=self.sample
        y=_phase(P,17,31,7,np.arange(P))
        # Introduce a different law on every validation coordinate, not training.
        y[vx]=_phase(P,3,19,11,vx)
        g=admit(P,x,y[x],vx,y[vx])
        self.assertEqual(g.decision,'refused')

    def test_change_only_in_untouched_test_is_discovered(self):
        x,_,vx,_,tx,_,_=self.sample
        y=_phase(P,17,31,7,np.arange(P))
        y[tx]=_phase(P,3,19,11,tx)
        g=admit(P,x,y[x],vx,y[vx])
        self.assertEqual(g.decision,'qualified')
        self.assertEqual(independent_test(g,tx,y[tx])['status'],'failed_out_of_sample')

    def test_constant_is_not_rejected_as_unstructured_by_other_claim(self):
        x,_,vx,_,_,_,_=self.sample
        constant=np.ones(P,dtype=complex)
        g=admit(P,x,constant[x],vx,constant[vx])
        # Permutation null cannot distinguish a perfectly constant signal;
        # refusal is non-certification, not evidence of randomness.
        self.assertEqual(g.decision,'refused')
        self.assertEqual(g.permutation_pvalue,1.0)

    def test_independent_test_rejects_train_overlap(self):
        g=self.good
        with self.assertRaisesRegex(ValueError,'overlaps'):
            independent_test(g, self.sample[0][:12], self.sample[1][:12])

    def test_arbitrary_precision_coordinate_reduction(self):
        g=self.good
        giant=10**105+47
        phasor=g.predict(giant,allow_unwitnessed=True)
        small=g.predict(giant % P,allow_unwitnessed=True)
        self.assertLess(abs(phasor-small),1e-13)
        value,_=g.navigate_cayley(10**100,10**110,allow_unwitnessed=True)
        self.assertLess(abs(value-g.predict(10**100+10**110,allow_unwitnessed=True)),1e-12)

    def test_validation_is_not_used_in_learning(self):
        x,y,vx,vy,*_=self.sample
        g=admit(P,x,y,vx,vy)
        changed=admit(P,x,y,vx,vy*np.exp(1.3j))
        self.assertEqual((g.a,g.b,g.c),(changed.a,changed.b,changed.c))
        self.assertNotEqual(g.validation_rmse,changed.validation_rmse)

    def test_reject_overlapping_and_bad_modulus(self):
        x,y,vx,vy,*_=self.sample
        with self.assertRaisesRegex(ValueError,'prime'):
            admit(125,x,y,vx,vy)
        with self.assertRaisesRegex(ValueError,'validation indices'):
            admit(P,x,y,x[:25],y[:25])
        with self.assertRaises(ValueError):
            admit(P,x,x.astype(float)*0,vx,vy)


if __name__=='__main__':
    unittest.main()
