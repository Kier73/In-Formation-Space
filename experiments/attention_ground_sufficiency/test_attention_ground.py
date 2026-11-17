"""Independent arithmetic, provenance and adversarial checks for AKS-001."""
import math
import unittest
from dataclasses import replace

from attention_ground import (
    AttentionGround, GroundRefused, PrefixGround, TokenEvidence,
    direct_observe, reconstruct, verify_observation,
)


def extend(state, key, value):
    token = TokenEvidence.form(state.ground, state.count, state.history_head, key, value)
    return state.admit(token), token


def softmax(keys, values, q):
    scores = [q * k for k in keys]
    offset = max(scores)
    weights = [math.exp(s - offset) for s in scores]
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


class AttentionGroundTests(unittest.TestCase):
    def test_demand_observation_matches_independent_source_replay(self):
        g = AttentionGround(101, 2, 2)
        state = PrefixGround.empty(g)
        samples = []
        for i in range(113):
            state, token = extend(state, (i % 101, (7 * i + 3) % 101),
                                  ((i * i + 1) % 101, (5 * i + 2) % 101))
            samples.append(token)
        self.assertEqual(state.count, 113)
        self.assertEqual(reconstruct(g, samples), state)
        self.assertEqual(len(state.matrix), 3)
        for query in ((0, 0), (1, 2), (23, 51), (100, 100)):
            for normalized in (False, True):
                try:
                    result = state.query(query, normalized=normalized)
                except GroundRefused as exc:
                    self.assertIn('denominator', str(exc))
                    with self.assertRaises(GroundRefused):
                        direct_observe(g, samples, query, normalized=normalized)
                else:
                    self.assertEqual(result.result, direct_observe(g, samples, query, normalized=normalized))
                    self.assertTrue(verify_observation(g, samples, result, expected_head=state.history_head))

    def test_prefix_update_and_constancy_of_state_shape(self):
        g = AttentionGround(97, 3, 2)
        state = PrefixGround.empty(g)
        for index in range(2000):
            state, _ = extend(state, (index % 97, index % 13, index % 17), (index % 11, index % 23))
        self.assertEqual(state.count, 2000)
        self.assertEqual((len(state.matrix), len(state.matrix[0]), len(state.mass)), (4, 2, 4))
        self.assertEqual(len(state.history_head), 64)

    def test_normalization_refuses_zero_and_modular_composite(self):
        g = AttentionGround(101, 1, 1)
        with self.assertRaisesRegex(GroundRefused, 'denominator'):
            PrefixGround.empty(g).query((2,), normalized=True)
        state, _ = extend(PrefixGround.empty(g), (0,), (9,))
        state, _ = extend(state, (0,), (4,))
        self.assertEqual(state.query((5,), normalized=True).result, (57,))  # 13/2 mod 101 = 57
        with self.assertRaisesRegex(GroundRefused, 'prime'):
            AttentionGround(15, 1, 1)
        with self.assertRaises(GroundRefused):
            AttentionGround(101, True, 1)

    def test_refuses_reordering_deletion_substitution_and_rehashed_rewrite(self):
        g = AttentionGround(101, 1, 1)
        s0 = PrefixGround.empty(g)
        s1, a = extend(s0, (2,), (3,))
        s2, b = extend(s1, (5,), (8,))
        observation = s2.query((9,), normalized=False)
        self.assertTrue(verify_observation(g, (a, b), observation, expected_head=s2.history_head))
        for altered in ((b, a), (b,), (a,)):
            with self.assertRaises(GroundRefused):
                verify_observation(g, altered, observation, expected_head=s2.history_head)
        with self.assertRaisesRegex(GroundRefused, 'digest'):
            reconstruct(g, (replace(a, value=(99,)), b))
        forged_a = TokenEvidence.form(g, 0, s0.history_head, (2,), (4,))
        forged_b = TokenEvidence.form(g, 1, forged_a.digest, (5,), (8,))
        forged = reconstruct(g, (forged_a, forged_b))
        # A completely rehashed sequence still cannot satisfy an independent root pin.
        with self.assertRaisesRegex(GroundRefused, 'pin'):
            verify_observation(g, (forged_a, forged_b), forged.query((9,), normalized=False),
                               expected_head=s2.history_head)
        with self.assertRaisesRegex(GroundRefused, 'observation'):
            verify_observation(g, (a, b), replace(observation, result=(42,)), expected_head=s2.history_head)
        with self.assertRaises(GroundRefused):
            s0.admit(b)

    def test_same_sufficient_ground_not_same_softmax_ground(self):
        """Even matching count/key/value sums and first cross-moments cannot determine softmax."""
        g = AttentionGround(101, 1, 1)
        def build(values):
            state = PrefixGround.empty(g)
            tokens = []
            for key, val in zip((0, 1, 2), values):
                state, token = extend(state, (key,), (val,))
                tokens.append(token)
            return state, tokens
        a, ta = build((2, 2, 2))
        b, tb = build((3, 0, 3))
        self.assertEqual((a.matrix, a.mass, a.count), (b.matrix, b.mass, b.count))
        self.assertNotEqual(a.history_head, b.history_head)
        self.assertEqual(a.query((1,), normalized=True).result,
                         b.query((1,), normalized=True).result)
        self.assertNotAlmostEqual(softmax((0, 1, 2), (2, 2, 2), 1.0),
                                  softmax((0, 1, 2), (3, 0, 3), 1.0))
        self.assertTrue(verify_observation(g, ta, a.query((1,), normalized=True), expected_head=a.history_head))
        self.assertTrue(verify_observation(g, tb, b.query((1,), normalized=True), expected_head=b.history_head))


if __name__ == '__main__':
    unittest.main()

class ExhaustiveAlgebraTests(unittest.TestCase):
    def test_all_two_token_scalar_histories_over_five(self):
        g = AttentionGround(5, 1, 1)
        origin = PrefixGround.empty(g)
        for k1 in range(5):
            for v1 in range(5):
                s1, a = extend(origin, (k1,), (v1,))
                for k2 in range(5):
                    for v2 in range(5):
                        s2, b = extend(s1, (k2,), (v2,))
                        for q in range(5):
                            for normal in (False, True):
                                try:
                                    observed = s2.query((q,), normalized=normal)
                                except GroundRefused:
                                    with self.assertRaises(GroundRefused):
                                        direct_observe(g, (a, b), (q,), normalized=normal)
                                else:
                                    self.assertEqual(observed.result, direct_observe(
                                        g, (a, b), (q,), normalized=normal))

