import unittest

from affine_orbit_equivalence import compare_affine_orbits


class AffineOrbitEquivalenceTests(unittest.TestCase):
    def test_equivalent_parameterizations_prove_all_future_outputs_equal(self):
        result = compare_affine_orbits((1, 2, 10), (1, 12, 10), max_steps=None)
        self.assertEqual(result.status, "equivalent")
        self.assertIsNone(result.first_difference_step)
        self.assertIsNotNone(result.cycle_entry_step)
        self.assertGreater(result.cycle_period, 0)

    def test_different_orbits_return_first_distinguishing_coordinate(self):
        result = compare_affine_orbits((1, 2, 10), (2, 1, 10), max_steps=None)
        self.assertEqual(result.status, "different")
        self.assertEqual(result.first_difference_step, 2)
        self.assertEqual(result.left_value, 5)
        self.assertEqual(result.right_value, 7)

    def test_exhausted_budget_returns_unknown_not_equivalent(self):
        result = compare_affine_orbits((1, 1, 101), (1, 1, 101), max_steps=3)
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.checked_steps, 3)

    def test_no_budget_limit_finds_cycle_with_finite_modulus(self):
        result = compare_affine_orbits((1, 1, 17), (1, 1, 17), max_steps=None)
        self.assertEqual(result.status, "equivalent")
        self.assertLessEqual(result.checked_steps, 17 * 17 + 1)

    def test_different_moduli_are_not_compared_as_same_output_space(self):
        with self.assertRaises(ValueError):
            compare_affine_orbits((1, 2, 10), (1, 2, 11))

    def test_invalid_parameters_and_budget_are_rejected(self):
        for args in (
            ((1, 2, 0), (1, 2, 0)),
            ((1, 2, 10), (1, 2, -1)),
            ((1, 2), (1, 2, 10)),
            ((True, 2, 10), (1, 2, 10)),
        ):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    compare_affine_orbits(*args)
        with self.assertRaises(ValueError):
            compare_affine_orbits((1, 2, 10), (1, 2, 10), max_steps=-1)


if __name__ == "__main__":
    unittest.main()
