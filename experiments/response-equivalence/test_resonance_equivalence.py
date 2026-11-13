import unittest
from fractions import Fraction as Q

from resonance_equivalence import (
    analyze, examples, hankel_rank, rank_exact, rdm,
    recover_two_mode_recurrence, response,
)


class ResonanceEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.plants = examples(delay=6)

    def test_similarity_and_unobserved_mode_same_response(self):
        baseline = self.plants["base"].markov(40)
        self.assertEqual(self.plants["coordinate"].markov(40), baseline)
        self.assertEqual(self.plants["hidden"].markov(40), baseline)

    def test_hidden_mode_increases_internal_not_observable_dimension(self):
        self.assertEqual(len(self.plants["base"].B), 2)
        self.assertEqual(len(self.plants["hidden"].B), 3)
        self.assertEqual(hankel_rank(self.plants["hidden"].markov(6), 3), 2)

    def test_same_modes_different_output(self):
        other = self.plants["same_modes_changed_output"]
        self.assertEqual(other.A, self.plants["base"].A)
        self.assertNotEqual(other.markov(8), self.plants["base"].markov(8))
        self.assertEqual(other.markov(1), [Q(0)])

    def test_delayed_impostor_not_identified_by_finite_prefix(self):
        left = self.plants["base"].markov(20)
        right = self.plants["delayed"].markov(20)
        self.assertEqual(left[:6], right[:6])
        self.assertEqual(right[6] - left[6], Q(1))
        self.assertEqual(hankel_rank(right, 9), 9)

    def test_exact_recurrence_reconstruction(self):
        h = self.plants["base"].markov(30)
        a, b = recover_two_mode_recurrence(h)
        self.assertEqual((a, b), (Q(3, 4), Q(-1, 8)))
        self.assertTrue(all(h[i+2] == a*h[i+1] + b*h[i]
                            for i in range(28)))

    def test_affine_sensor_covariance_of_response_distances(self):
        original = rdm(self.plants["base"], 10)
        transformed = rdm(self.plants["base"], 10, gain=Q(3), offset=Q(2))
        self.assertEqual(len(original), 10)
        self.assertEqual(transformed, {k: 9*v for k, v in original.items()})
        self.assertEqual(rdm(self.plants["coordinate"], 10), original)

    def test_convolution_and_validation(self):
        self.assertEqual(
            response(self.plants["base"], (Q(1),), 3),
            (Q(2), Q(3,4), Q(5,16)),
        )
        self.assertEqual(rank_exact([[Q(1), Q(2)], [Q(2), Q(4)]]), 1)
        with self.assertRaises(ValueError):
            recover_two_mode_recurrence([Q(1), Q(2), Q(4), Q(8)])
        with self.assertRaises(ValueError):
            hankel_rank([Q(1)], 2)

    def test_report_contract(self):
        summary = analyze()
        self.assertEqual(summary["hankel_rank_base_3x3"], 2)
        self.assertEqual(
            summary["compared_to_base"]["delayed"]["first_difference_index"], 6,
        )


if __name__ == "__main__":
    unittest.main()
