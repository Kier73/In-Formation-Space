import math
import unittest

import numpy as np
from navigator import ExactWeilGround, fit_spectral, test_report, cancellation_hint, _fit_delay


class ExactTests(unittest.TestCase):
    def setUp(self):
        self.g = ExactWeilGround.admit(5, 2, -8, {3: 2, 4: -28, 5: -198, 6: -8})

    def test_observed_curve_and_million(self):
        self.assertEqual(self.g.coefficients, (2, 6, 10, 25))
        for n, s in enumerate([2, -8, 2, -28, -198, -8], 1):
            self.assertEqual(self.g.navigate_mod(n, 2**61-1)[0], s % (2**61-1))
            self.assertEqual(self.g.point_count_mod(n, 2**61-1)[0], (5**n+1-s)%(2**61-1))
        val, products = self.g.navigate_mod(10**6, 2**61-1)
        self.assertEqual(val, 1187996290252243319)
        self.assertLessEqual(products, 40)

    def test_wrong_critical_line_rejected(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            ExactWeilGround.admit(5, 5, 13, {n: 3**n+2**n for n in range(3, 7)})

    def test_insufficient_witness_or_invalid_input(self):
        with self.assertRaises(ValueError):
            ExactWeilGround.admit(5, 2, -8, {3: 2})
        with self.assertRaises(ValueError):
            self.g.navigate_mod(-2, 31)
        with self.assertRaises(ValueError):
            self.g.navigate_mod(8, 1)

    def test_general_moduli_parity(self):
        for modulus in (7, 123, 2**31-1):
            for n in range(1, 60):
                self.assertEqual(self.g.navigate_mod(n, modulus)[0], self.g._trace(n)%modulus)


class SpectralTests(unittest.TestCase):
    def setUp(self):
        self.t = np.arange(1., 321.)

    def test_periodic_prediction_and_horizon_guard(self):
        y = np.cos(.23*self.t) + .35*np.sin(.41*self.t)
        g = fit_spectral(self.t, y)
        self.assertEqual(g.decision, 'qualified')
        self.assertEqual(g.clock, 'linear')
        self.assertLess(g.validation_rmse, 1e-6)
        self.assertEqual(test_report(g, self.t, y)['status'], 'corroborated')
        with self.assertRaisesRegex(ValueError, 'outside held-out'):
            g.predict(g.validation_steps + 1)
        self.assertTrue(np.isfinite(g.predict(10000, allow_unwitnessed=True)))

    def test_clock_warp_chirp(self):
        y = np.sin(.035 * self.t**1.5)
        g = fit_spectral(self.t, y)
        self.assertEqual(g.clock, 'power-1.5')
        self.assertEqual(g.decision, 'qualified')
        self.assertGreater(g.relative_improvement, .9)
        self.assertEqual(test_report(g, self.t, y)['status'], 'corroborated')

    def test_log_clock_with_sqrt_amplitude(self):
        t = np.exp(np.linspace(0, 7, 320))
        y = np.sqrt(t) * (np.cos(2.3*np.log(t))+.35*np.sin(3.4*np.log(t)))
        g = fit_spectral(t, y)
        self.assertEqual(g.clock, 'log')
        self.assertEqual(g.decision, 'qualified')
        self.assertLess(g.validation_rmse, 1e-6)
        self.assertEqual(test_report(g, t, y)['status'], 'corroborated')

    def test_dissipation_stays_unconstrained(self):
        y = np.exp(-.02*self.t)*np.sin(.24*self.t)
        g = fit_spectral(self.t, y)
        self.assertFalse(g.circle)
        self.assertEqual(g.decision, 'qualified')
        self.assertEqual(test_report(g, self.t, y)['status'], 'corroborated')

    def test_chaos_and_noise_refused(self):
        x = .237
        samples = []
        for _ in range(len(self.t)):
            x = 4*x*(1-x)
            samples.append(x)
        for y in (np.asarray(samples), np.random.default_rng(2026).normal(size=len(self.t))):
            g = fit_spectral(self.t, y)
            self.assertEqual(g.decision, 'refused')
            with self.assertRaisesRegex(ValueError, 'refused'):
                g.predict(1)

    def test_regime_shift_cannot_be_extrapolated(self):
        y = np.where(self.t<=265, np.sin(.23*self.t), np.sin(.39*self.t))
        g = fit_spectral(self.t, y)
        self.assertEqual(g.decision, 'qualified')
        result = test_report(g, self.t, y)
        self.assertEqual(result['status'], 'failed_out_of_sample')
        self.assertLess(result['test_relative_improvement'], .15)

    def test_histogram_audit_is_not_order_inference(self):
        y = np.sin(.23*self.t)
        shuffled = np.random.default_rng(2).permutation(y)
        self.assertAlmostEqual(cancellation_hint(y)['cancel'], cancellation_hint(shuffled)['cancel'])
        self.assertNotAlmostEqual(cancellation_hint(y)['lag_cancel'], cancellation_hint(shuffled)['lag_cancel'])

    def test_projection_has_unit_modulus_only_when_selected(self):
        y = np.sin(.24*self.t)
        basis, mat, state, cond = _fit_delay(y[:192], 2, 24, True)
        self.assertTrue(np.allclose(np.abs(np.linalg.eigvals(mat)), 1.0))
        self.assertLess(cond, 5)

    def test_errors_are_explicit(self):
        y = np.sin(self.t)
        with self.assertRaises(ValueError):
            fit_spectral(self.t, y, train_count=20)
        with self.assertRaises(ValueError):
            fit_spectral(self.t[::-1], y)
        with self.assertRaises(ValueError):
            fit_spectral(self.t, np.full(len(self.t), np.nan))


if __name__ == '__main__':
    unittest.main()