"""BMO-007 independent checks for the unbounded-depth hull theorem.

The tests check finite premises and the recurrence. Universal-depth
statements follow separately from the written induction proof.
"""

import math
from fractions import Fraction as F
import unittest

import all_depth_law as theory
from angle_transitions import endpoint_polynomials, oriented_cross, sub, add, scale


class UniversalHullLawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certificate = theory.phase_identity_certificate(verify_prior=True)

    def test_exact_homothety_regimes(self):
        result = self.certificate
        self.assertEqual(result["certified_scale_equalities"], 15)
        self.assertEqual(result["vertex_polynomial_equalities"], 89)
        self.assertEqual(result["sigma_outside_witness"]["bernstein_signs_on_sigma_to_one"],
                         [0, 1, 1, 1, 1])
        self.assertEqual(result["inherited_endpoint_checks"],
                         {"1_to_2": 6, "2_to_3": 26, "3_to_4": 126, "4_to_5": 626})
        self.assertEqual([r["vertices"] for r in result["regimes"]],
                         [4, 5, 6, 4, 5, 6, 7, 7, 4, 5, 6, 7, 7, 8, 8])

    def test_endpoint_index_and_signature_recurrence(self):
        signatures = {n: theory.SIGNATURES[n]() for n in range(1, 6)}
        for n, labels in signatures.items():
            with self.subTest(depth=n):
                a, b = theory.endpoint_pair(n)
                self.assertEqual(b, a + 1)
                self.assertLess(b, len(labels))
                expected_b = {0: 2 * 3 ** (n - 1)}
                for k in range(1, n - 1):
                    expected_b[-k] = 2 * 3 ** (n - 1 - k)
                if n > 1:
                    expected_b[-(n - 1)] = 3
                else:
                    expected_b = {0: 3}
                expected_a = expected_b.copy()
                k = -(n - 1)
                expected_a[k] -= 1
                expected_a[-n] = 1
                self.assertEqual(labels[a], tuple(sorted(expected_a.items())))
                self.assertEqual(labels[b], tuple(sorted(expected_b.items())))

    def test_closed_form_matches_independent_exact_endpoint_cross(self):
        for n in range(1, 6):
            labels = theory.SIGNATURES[n]()
            a, b = theory.endpoint_pair(n)
            actual = oriented_cross(*(endpoint_polynomials(labels[i])
                                      for i in (0, a, b)))
            self.assertEqual(actual, theory.new_corner_polynomial(n))
        self.assertEqual([theory.new_corner_polynomial(n) for n in range(1, 6)], [
            (3,), (-3, 12), (-21, -24, 72),
            (33, -240, -144, 432),
            (195, 408, -2088, -864, 2592),
        ])

    def test_chebyshev_and_three_term_recurrence(self):
        self.assertEqual([theory.chebyshev_u(n) for n in range(-1, 4)],
                         [(0,), (1,), (0, 2), (-1, 0, 4), (0, -4, 0, 8)])
        for n in range(1, 18):
            pn = theory.new_corner_polynomial(n)
            pn1 = theory.new_corner_polynomial(n + 1)
            self.assertEqual(sub(pn1, pn),
                             scale(sub(theory.chebyshev_u(n),
                                       theory.chebyshev_u(n - 1)), 2 * 3 ** n))
        for n in range(3, 17):
            a = theory.new_corner_polynomial(n + 1)
            b = theory.new_corner_polynomial(n)
            c = theory.new_corner_polynomial(n - 1)
            d = theory.new_corner_polynomial(n - 2)
            rhs = add(sub(add(b, scale(theory.d2.mul((0, 1), b), 6)),
                          add(scale(c, 9),
                              scale(theory.d2.mul((0, 1), c), 6))),
                      scale(d, 9))
            self.assertEqual(a, rhs)

    def test_first_candidate_angle_is_strictly_decreasing(self):
        previous = math.pi / 2
        for n in range(2, 70):
            root = theory.first_candidate_zero(n)
            self.assertLess(root, previous)
            self.assertGreater(root, math.pi / (2 * n - 1))
            self.assertLess(root, min(math.pi / 2, math.pi / (n - 0.5)))
            self.assertAlmostEqual(theory.normalized_witness(root, n), 0, delta=1e-12)
            previous = root
        for n, expected in ((2, 75.522487814), (3, 42.957378163),
                            (4, 29.46546822), (5, 22.309473247)):
            self.assertAlmostEqual(math.degrees(theory.first_candidate_zero(n)),
                                   expected, delta=2e-6)

    def test_uniform_limit_bound_and_asymptotic(self):
        for n in (2, 3, 8, 20, 100):
            for fraction in (F(1, 4), F(3, 4), F(3, 2), F(5, 2)):
                x = float(fraction)
                if x / n >= math.pi / 2:
                    continue
                self.assertLessEqual(
                    abs(theory.normalized_witness(x / n, n) - math.cos(x)),
                    x / n + 1e-14)
        self.assertLess(abs(300 * theory.first_candidate_zero(300) - math.pi / 2),
                        0.01)

    def test_input_guardrails(self):
        for n in (0, -1, True, 2.1, 101):
            with self.subTest(n=n), self.assertRaises(ValueError):
                theory.new_corner_polynomial(n)
        for n in (1, 0, -1, True):
            with self.subTest(n=n), self.assertRaises(ValueError):
                theory.first_candidate_zero(n)


if __name__ == "__main__":
    unittest.main()
