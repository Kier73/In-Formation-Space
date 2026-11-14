"""Contract tests for the deterministic L-system and morphology measurements."""
import json
import math
import unittest
from pathlib import Path
import importlib.util

SPEC = importlib.util.spec_from_file_location("canopy", Path(__file__).with_name("canopy.py"))
canopy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canopy)


class GrammarTests(unittest.TestCase):
    def test_segment_count_and_balanced_brackets(self):
        for n in range(7):
            word = canopy.grammar(n)
            self.assertEqual(word.count("F"), 5 ** n)
            self.assertEqual(word.count("["), word.count("]"))
            self.assertEqual(len(canopy.trace(word, 30)), 5 ** n)

    def test_invalid_grammar_and_turns_are_rejected(self):
        for n in (-1, 7, 1.5, True):
            with self.subTest(n=n), self.assertRaises(ValueError):
                canopy.grammar(n)
        for a in (float("nan"), float("inf"), -1, 0, 90, 100):
            with self.subTest(a=a), self.assertRaises(ValueError):
                canopy.trace("F", a)
        for word in ("F]", "[F", "FX"):
            with self.subTest(word=word), self.assertRaises(ValueError):
                canopy.trace(word, 25)

    def test_turtle_state_is_restored(self):
        segments = canopy.trace("F[+F]F", 45)
        self.assertEqual(len(segments), 3)
        # The post-branch F resumes from the endpoint of the first F.
        self.assertAlmostEqual(segments[0][2], segments[2][0])
        self.assertAlmostEqual(segments[0][3], segments[2][1])
        self.assertAlmostEqual(segments[2][2], 0.0, places=9)
        self.assertAlmostEqual(segments[2][3], -2.0, places=9)

    def test_known_convex_hull(self):
        square = [(0, 0), (2, 0), (2, 2), (0, 2), (1, 1)]
        self.assertAlmostEqual(canopy.hull_area(square), 4)
        self.assertEqual(canopy.hull_area([(0, 0), (1, 1)]), 0)

    def test_fixed_topology_changes_geometry(self):
        a, b = (canopy.metrics(canopy.trace(canopy.grammar(3), angle))
                for angle in (12, 60))
        self.assertEqual(a["segments"], b["segments"])
        self.assertNotEqual(a["aspect_width_over_height"], b["aspect_width_over_height"])
        for metrics in (a, b):
            self.assertGreater(metrics["width"], 0)
            self.assertGreater(metrics["height"], 0)
            self.assertGreater(metrics["hull_area"], 0)
            self.assertGreater(metrics["hull_fraction_of_bbox"], 0)
            self.assertLessEqual(metrics["hull_fraction_of_bbox"], 1.000001)

    def test_svg_and_json_reproducibility(self):
        svg1, result1 = canopy.atlas(3, (15.0, 40.0))
        svg2, result2 = canopy.atlas(3, (15.0, 40.0))
        self.assertEqual(svg1.encode(), svg2.encode())
        self.assertEqual(result1, result2)
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', svg1)
        self.assertEqual([r["segments"] for r in result1["records"]], [125, 125])
        self.assertEqual(json.loads(json.dumps(result1, allow_nan=False)), result1)
        with self.assertRaises(ValueError):
            canopy.atlas(2, ())


if __name__ == "__main__":
    unittest.main()
