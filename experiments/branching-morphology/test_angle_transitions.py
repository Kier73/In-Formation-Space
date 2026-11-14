"""Independent numerical and exact tests for BMO-003 regime certificate."""
from fractions import Fraction
import importlib.util
import math
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


angles = load("angle_transitions")
canopy = load("canopy")


class AngleTransitionsTests(unittest.TestCase):
    def test_exact_certificate_and_breakpoints(self):
        cert = angles.certify()
        self.assertEqual(cert["endpoint_count"], 26)
        self.assertEqual(cert["half_plane_constraints_certified"], 390)
        self.assertEqual(cert["strict_corner_checks"], 15)
        self.assertEqual([r["open_interval_vertex_count"] for r in cert["regimes"]], [6, 5, 4])
        self.assertEqual([r["cosine"] for r in cert["transitions"]], ["1/2", "1/4"])

    def test_bernstein_positive_and_negative_examples(self):
        c = angles.bernstein_homogenized
        self.assertEqual(c((-1, 2), Fraction(1, 2), Fraction(1)),
                         (Fraction(0), Fraction(1)))
        self.assertEqual(c((-1,), Fraction(0), Fraction(1)), (Fraction(-1),))
        for lo, hi in ((Fraction(0), Fraction(1, 4)),
                       (Fraction(1, 4), Fraction(1, 2)),
                       (Fraction(1, 2), Fraction(1))):
            # Identity after homogenization agrees with exact original at midpoint.
            p = (3, -5, 2, 8)
            q = c(p, lo, hi)
            midpoint = (lo + hi) / 2
            self.assertEqual(angles.evaluate(p, midpoint),
                             sum((val for val in q), Fraction(0)) / 2 ** (len(p) - 1))

    def test_exact_hull_at_interior_and_boundary_cosines(self):
        points = tuple(angles.endpoint_polynomials(s) for s in angles.endpoint_signatures())
        expected = (
            (Fraction(7, 8), (19, 20, 25, 10, 7, 0)),
            (Fraction(3, 8), (19, 20, 25, 10, 0)),
            (Fraction(1, 8), (20, 25, 10, 0)),
            (Fraction(1, 2), (19, 20, 25, 10, 0)),
            (Fraction(1, 4), (20, 25, 10, 0)),
        )
        for cosine, corners in expected:
            with self.subTest(cosine=str(cosine)):
                self.assertEqual(set(angles.convex_hull_at_cos(points, cosine)), set(corners))

    def test_each_polynomial_endpoint_matches_existing_float_turtle(self):
        # The generator's line endpoints are compared with a separately written
        # symbolic interpreter (counts of turn headings), not with its own output.
        points = tuple(angles.endpoint_polynomials(s) for s in angles.endpoint_signatures())
        word = canopy.grammar(2)
        for degree in (15, 45, 65, 82):
            with self.subTest(degree=degree):
                theta = math.radians(degree)
                c, s = math.cos(theta), math.sin(theta)
                from_symbolic = [(s * sum(v * c ** k for k, v in enumerate(x)),
                                  sum(v * c ** k for k, v in enumerate(y)))
                                 for x, y in points]
                segments = canopy.trace(word, degree)
                from_turtle = [(0.0, 0.0)] + [(x2, y2) for _, _, x2, y2 in segments]
                self.assertEqual(len(from_turtle), len(from_symbolic))
                for x, y in from_turtle:
                    self.assertTrue(any(math.hypot(x - a, y - b) < 1e-10
                                        for a, b in from_symbolic), (degree, x, y))

    def test_transition_orientation_changes_exactly_at_roots(self):
        points = tuple(angles.endpoint_polynomials(s) for s in angles.endpoint_signatures())
        first = angles.oriented_cross(points[10], points[7], points[0])
        second = angles.oriented_cross(points[0], points[19], points[20])
        self.assertEqual(first, (-3, 6))
        self.assertEqual(second, (-3, 12))
        for poly, root in ((first, Fraction(1, 2)), (second, Fraction(1, 4))):
            self.assertLess(angles.evaluate(poly, root - Fraction(1, 20)), 0)
            self.assertEqual(angles.evaluate(poly, root), 0)
            self.assertGreater(angles.evaluate(poly, root + Fraction(1, 20)), 0)


if __name__ == "__main__":
    unittest.main()
