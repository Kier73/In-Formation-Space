"""Independent tests of BMO-004's algebraic canopy transition certificate."""

import importlib.util
import math
from fractions import Fraction
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import depth3_phase as phase
import angle_transitions as poly
import canopy


class DepthThreePhaseTests(unittest.TestCase):
    def test_exact_field_order_and_arithmetic(self):
        one = phase.Q46(1)
        alpha = phase.ALPHA
        self.assertTrue(phase.Q46(Fraction(1, 2)) < alpha < one)
        self.assertEqual(144 * alpha ** 2 - 48 * alpha - 42, phase.Q46(0))
        self.assertEqual(phase.Q46(1) + Fraction(1, 2), phase.Q46(Fraction(3, 2)))
        self.assertEqual(phase.Q46(1) * 3, phase.Q46(3))
        self.assertEqual(1 - phase.Q46(Fraction(1, 4)), phase.Q46(Fraction(3, 4)))
        self.assertTrue(phase.Q46(0, 1) > phase.Q46(6))
        self.assertTrue(phase.Q46(0, 1) < phase.Q46(7))
        self.assertTrue(phase.Q46(7, -1) > 0)
        self.assertTrue(phase.Q46(6, -1) < 0)
        with self.assertRaises(ValueError):
            _ = alpha ** -1

    def test_certificate_counts_and_algebraic_boundaries(self):
        cert = phase.certificate()
        self.assertEqual(cert['symbolic_endpoint_count'], 126)
        self.assertEqual(cert['halfplane_certificates'], 2772)
        self.assertEqual(cert['strict_corner_certificates'], 22)
        self.assertEqual([r['vertex_count'] for r in cert['regimes']], [4, 5, 6, 7])
        self.assertEqual([r['hull_vertex_count'] for r in cert['boundaries']], [4, 5, 6])
        self.assertEqual(cert['boundaries'][2]['cross_polynomial_ascending'], [-21, -24, 72])

    def test_exact_hulls_at_independent_interiors_and_boundaries(self):
        points = tuple(map(poly.endpoint_polynomials, phase.endpoint_signatures()))
        for label, lo, hi, indices in phase.REGIMES:
            with self.subTest(label=label):
                for ratio in (Fraction(1, 3), Fraction(2, 3)):
                    c = lo * (1 - ratio) + hi * ratio
                    self.assertEqual(set(phase.exact_hull_at(points, c)), set(indices))
        for c, count in ((Fraction(1, 4), 4), (Fraction(1, 2), 5), (phase.ALPHA, 6)):
            with self.subTest(c=str(c)):
                self.assertEqual(len(phase.exact_hull_at(points, c)), count)

    def test_symbolic_coordinates_match_original_generator(self):
        points = tuple(map(poly.endpoint_polynomials, phase.endpoint_signatures()))
        word = canopy.grammar(3)
        for theta_deg in (10, 30, 50, 68, 80):
            with self.subTest(theta=theta_deg):
                c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
                symbolic = [(s * sum(v * c**k for k, v in enumerate(x)),
                             sum(v * c**k for k, v in enumerate(y)))
                            for x, y in points]
                segments = canopy.trace(word, theta_deg)
                direct = [(0., 0.)] + [(x2, y2) for _, _, x2, y2 in segments]
                self.assertEqual(len(direct), len(symbolic))
                for i, (a, b) in enumerate(direct):
                    x, y = symbolic[i]
                    self.assertLess(math.hypot(x-a, y-b), 1e-10)

    def test_endpoint_count_and_invalid_depth(self):
        self.assertEqual([len(phase.endpoint_signatures(i)) for i in range(4)], [2, 6, 26, 126])
        for depth in (-1, 4, True, 1.5):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                phase.endpoint_signatures(depth)


if __name__ == '__main__':
    unittest.main()
