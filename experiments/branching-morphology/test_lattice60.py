"""Exact 60-degree hull identity and independent turtle reconstruction."""
import importlib.util
from fractions import Fraction
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("lattice60", Path(__file__).with_name("lattice60.py"))
lattice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lattice)


class ExactLatticeTests(unittest.TestCase):
    def test_rotations_act_on_six_directions(self):
        for i, d in enumerate(lattice.DIRECTIONS):
            self.assertEqual(lattice.rotate60(d, 1), lattice.DIRECTIONS[(i + 1) % 6])
            self.assertEqual(lattice.rotate60(d, -1), lattice.DIRECTIONS[(i - 1) % 6])
        with self.assertRaises(ValueError):
            lattice.rotate60((1, 0), 1)
        with self.assertRaises(ValueError):
            lattice.rotate60((0, 0), 0)

    def test_hull_matches_full_word_for_depths_zero_to_six(self):
        word = "F"
        for depth in range(7):
            with self.subTest(depth=depth):
                traced = lattice.convex_hull(lattice.trace_points(word))
                self.assertEqual(traced, lattice.hull_at_depth(depth))
            word = "".join("F[+F]F[-F]F" if c == "F" else c for c in word)

    def test_exact_homothety_and_fraction(self):
        h2 = lattice.hull_at_depth(2)
        self.assertEqual(lattice.area_fraction(lattice.hull_at_depth(1)), Fraction(1, 2))
        self.assertEqual(lattice.area_fraction(h2), Fraction(19, 36))
        for n in range(2, 7):
            scale = 3 ** (n - 2)
            target = lattice.convex_hull(tuple((u * scale, v * scale) for u, v in h2))
            self.assertEqual(lattice.hull_at_depth(n), target)
            self.assertEqual(lattice.area_fraction(target), Fraction(19, 36))

    def test_certificate_and_rejections(self):
        data = lattice.certificate()
        self.assertEqual(data["derived_for_all_depths_n_ge_2"]["area_fraction"], "19/36")
        for depth in (-1, 7, True, 2.5):
            with self.assertRaises(ValueError):
                lattice.hull_at_depth(depth)
        for word in ("[F", "F]", "FX"):
            with self.assertRaises(ValueError):
                lattice.trace_points(word)
        with self.assertRaises(ValueError):
            lattice.hull_step(((0, -2), (0, 0)), 0)


if __name__ == "__main__":
    unittest.main()
