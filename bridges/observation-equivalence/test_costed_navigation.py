"""Independent enumeration provides a small-model cost/length/lex reference."""

import itertools
import random
import unittest

from costed_navigation import CostedDistinctionNavigator


class CostedNavigationTests(unittest.TestCase):
    def test_longer_path_can_cost_less_than_short_path(self):
        states = ("a", "b", "x", "y", "c", "d")
        outputs = {s: 0 for s in states} | {"c": 1, "d": 2}
        edges = {
            ("a", "expensive"): "c", ("b", "expensive"): "d",
            ("a", "cheap"): "x", ("b", "cheap"): "y",
            ("x", "cheap"): "c", ("y", "cheap"): "d",
        }
        nav = CostedDistinctionNavigator(
            states, ("expensive", "cheap"), ("out",),
            lambda s, t: outputs[s], lambda s, a: edges.get((s, a), s),
        )
        self.assertEqual(nav.compare("a", "b").actions, ("expensive",))
        result = nav.plan_min_cost("a", "b", action_costs=(10, 2), test_costs=(1,))
        self.assertEqual(result.witness.actions, ("cheap", "cheap"))
        self.assertEqual((result.total_cost, result.action_cost, result.test_cost), (5, 4, 1))

    def test_cheapest_final_test_is_selected(self):
        nav = CostedDistinctionNavigator(
            (0, 1), ("stay",), ("slow", "fast", "other"),
            lambda s, t: s, lambda s, a: s,
        )
        result = nav.plan_min_cost(0, 1, action_costs=(3,), test_costs=(9, 1, 1))
        self.assertEqual(result.witness.distinguishing_test, "fast")
        self.assertEqual(result.witness.actions, ())
        self.assertEqual(result.total_cost, 1)

    def test_zero_cost_cycle_prefers_shortest_finite_path(self):
        nav = CostedDistinctionNavigator(
            (0, 1, 2), ("rotate", "stay"), ("out",),
            lambda s, t: 1 if s == 2 else 0,
            lambda s, a: (s + 1) % 3 if a == "rotate" else s,
        )
        result = nav.plan_min_cost(0, 1, action_costs=(0, 0), test_costs=(0,))
        self.assertEqual((result.total_cost, result.witness.actions), (0, ("rotate",)))
        self.assertEqual(result.witness.left_observation, 0)
        self.assertEqual(result.witness.right_observation, 1)

    def test_equivalence_and_empty_tests(self):
        nav = CostedDistinctionNavigator(
            (0, 1), ("flip",), (),
            lambda s, t: s, lambda s, a: 1 - s,
        )
        result = nav.plan_min_cost(0, 1, action_costs=(0,), test_costs=())
        self.assertEqual((result.witness.status, result.total_cost), ("equivalent", None))
        self.assertIsNone(nav.plan_min_cost(1, 1, action_costs=(0,), test_costs=()).total_cost)

    def test_invalid_cost_inputs_fail_closed(self):
        nav = CostedDistinctionNavigator(
            (0, 1), ("stay",), ("out",),
            lambda s, t: s, lambda s, a: s,
        )
        for action, test in [((True,), (1,)), ((-1,), (1,)), ((1.0,), (1,)),
                             ((), (1,)), ((1,), ()), ((1,), (-1,))]:
            with self.subTest(action=action, test=test), self.assertRaises(ValueError):
                nav.plan_min_cost(0, 1, action_costs=action, test_costs=test)
        with self.assertRaises(ValueError):
            nav.plan_min_cost(0, 5, action_costs=(0,), test_costs=(0,))

    def test_random_against_independent_exhaustive_word_search(self):
        rng = random.Random(20261114)
        for _ in range(80):
            n = rng.randint(2, 4)
            states = tuple(range(n))
            actions = (0, 1)
            tests = (0, 1)
            output = {(s, t): rng.randrange(3) for s in states for t in tests}
            edge = {(s, a): rng.randrange(n) for s in states for a in actions}
            ac = tuple(rng.randrange(5) for _ in actions)
            tc = tuple(rng.randrange(5) for _ in tests)
            nav = CostedDistinctionNavigator(
                states, actions, tests, lambda s, t: output[(s, t)],
                lambda s, a: edge[(s, a)],
            )
            for i, j in itertools.combinations(states, 2):
                candidates = []
                max_len = n * (n - 1) // 2
                for length in range(max_len + 1):
                    for word in itertools.product(actions, repeat=length):
                        x, y = i, j
                        for action in word:
                            x, y = edge[(x, action)], edge[(y, action)]
                        for test in tests:
                            if output[(x, test)] != output[(y, test)]:
                                score = (sum(ac[a] for a in word) + tc[test], length, word, test)
                                candidates.append((score, (x, y)))
                result = nav.plan_min_cost(i, j, action_costs=ac, test_costs=tc)
                if not candidates:
                    self.assertEqual((result.witness.status, result.total_cost), ("equivalent", None))
                else:
                    score, final = min(candidates)
                    self.assertEqual(result.witness.status, "distinguished")
                    self.assertEqual(result.total_cost, score[0])
                    self.assertEqual(result.witness.actions, score[2])
                    self.assertEqual(result.witness.distinguishing_test, score[3])
                    self.assertEqual((result.witness.left_final, result.witness.right_final), final)
                    self.assertEqual(result.action_cost + result.test_cost, result.total_cost)


if __name__ == "__main__":
    unittest.main()
