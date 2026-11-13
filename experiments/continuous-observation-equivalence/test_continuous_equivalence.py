"""Independent arithmetic observations, equivalence and negative controls."""
import random
import unittest
from fractions import Fraction

from continuous_equivalence import (InvalidNetwork, RegionBudgetExceeded,
                                    atlas, compare, evaluate, fingerprint, layer, q, token)


def identity():
    return (layer([[1]], [0], "linear"),)


def relu_identity():
    return (layer([[1], [-1]], [0, 0], "relu"),
            layer([[1, -1]], [0], "linear"))


def zero():
    return (layer([[0]], [0], "linear"),)


def bump():
    return (layer([[1], [1], [1]], [0, "-1/2", -1], "relu"),
            layer([[1, -2, 1]], [0], "linear"))


def equivalent_rescaled_bump():
    return (layer([[2], [1], [1]], [0, "-1/2", -1], "relu"),
            layer([["1/2", -2, 1]], [0], "linear"))


class ContinuousEquivalenceTests(unittest.TestCase):
    def test_identity_vs_different_relu_architecture_over_all_real_inputs(self):
        result = compare(identity(), relu_identity())
        self.assertEqual(result["status"], "equivalent")
        self.assertEqual(result["left_regions"], 1)
        self.assertEqual(result["right_regions"], 1)
        self.assertEqual(fingerprint(atlas(identity())), fingerprint(atlas(relu_identity())))

    def test_rescaled_neuron_homogeneity_equivalence_for_all_real_inputs(self):
        result = compare(bump(), equivalent_rescaled_bump())
        self.assertEqual(result["status"], "equivalent")
        self.assertEqual(result["left_regions"], 4)

    def test_binary_samples_cannot_establish_real_domain_equivalence(self):
        self.assertEqual(evaluate(zero(), Fraction(0)), evaluate(bump(), Fraction(0)))
        self.assertEqual(evaluate(zero(), Fraction(1)), evaluate(bump(), Fraction(1)))
        result = compare(zero(), bump())
        self.assertEqual(result["status"], "different")
        witness = q(result["witness"])
        self.assertNotEqual(evaluate(zero(), witness), evaluate(bump(), witness))
        self.assertGreater(evaluate(bump(), witness)[0], 0)

    def test_breakpoint_evaluation_with_exact_independent_interpreter(self):
        for x in [Fraction(0), Fraction(1, 2), Fraction(1), Fraction(-20), Fraction(20)]:
            for network in (bump(), equivalent_rescaled_bump(), relu_identity()):
                regions = atlas(network)
                matches = [reg for reg in regions if
                           (reg.left is None or reg.left <= x) and
                           (reg.right is None or x <= reg.right)]
                self.assertTrue(matches)
                for reg in matches:
                    self.assertEqual(tuple(y.at(x) for y in reg.output), evaluate(network, x))

    def test_resource_budget_is_unknown_not_false(self):
        self.assertEqual(compare(zero(), bump(), max_regions=2)["status"], "unresolved")
        with self.assertRaises(RegionBudgetExceeded):
            atlas(bump(), max_regions=2)

    def test_invalid_or_inexact_inputs_rejected(self):
        for value in (0.1, True, "1e3", " 1", "1/0", "01"):
            with self.assertRaises((InvalidNetwork, ZeroDivisionError)):
                q(value)
        with self.assertRaises(InvalidNetwork):
            atlas((layer([[1, 2]], [0], "relu"),))
        with self.assertRaises(InvalidNetwork):
            compare(identity(), (layer([[1], [1]], [0, 0], "linear"),))

    def test_randomized_symbolic_atlas_matches_direct_exact_evaluation(self):
        rng = random.Random(20261113)
        for case in range(120):
            depth = rng.randint(1, 4)
            width = 1
            network = []
            for i in range(depth):
                height = rng.randint(1, 3)
                weights = [[rng.randint(-2, 2) for _ in range(width)] for _ in range(height)]
                bias = [Fraction(rng.randint(-3, 3), 2) for _ in range(height)]
                network.append(layer(weights, bias, "linear" if i == depth-1 else "relu"))
                width = height
            network = tuple(network)
            regions = atlas(network, max_regions=1024)
            probes = {Fraction(n, 3) for n in range(-12, 13)}
            for region in regions:
                probes.add(Fraction(0) if region.left is None else region.left)
                probes.add(Fraction(0) if region.right is None else region.right)
                if region.left is not None and region.right is not None:
                    probes.add((region.left + region.right) / 2)
            for x in probes:
                symbolic = [region for region in regions if
                            (region.left is None or region.left < x) and
                            (region.right is None or x < region.right)]
                if symbolic:
                    self.assertEqual(tuple(v.at(x) for v in symbolic[0].output),
                                     evaluate(network, x), (case, x))
                else:
                    self.assertTrue(any(x == region.left or x == region.right for region in regions))


if __name__ == "__main__":
    unittest.main()
