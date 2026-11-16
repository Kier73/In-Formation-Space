"""Tests include an independent exhaustive bounded-word reference on tiny models."""

import itertools
import random
import unittest

from distinguishing_navigation import FiniteDistinctionNavigator


class FiniteDistinctionNavigationTests(unittest.TestCase):
    def test_zero_step_witness_when_observation_already_differs(self):
        nav = FiniteDistinctionNavigator(
            (0, 1), ("stay",), ("value",),
            lambda state, test: [state], lambda state, action: state,
        )
        result = nav.compare(1, 0)
        self.assertEqual((result.status, result.actions), ("distinguished", ()))
        self.assertEqual((result.left_observation, result.right_observation), ([1], [0]))

    def test_two_step_distinction_is_shortest_and_directional(self):
        states = ("a", "b", "x", "y", "c", "d")
        out = {"a": 0, "b": 0, "x": 0, "y": 0, "c": 1, "d": 2}
        move = {"a": "x", "b": "y", "x": "c", "y": "d", "c": "c", "d": "d"}
        nav = FiniteDistinctionNavigator(
            states, ("tick",), ("read",),
            lambda state, test: out[state], lambda state, action: move[state],
        )
        result = nav.compare("b", "a")
        self.assertEqual(result.actions, ("tick", "tick"))
        self.assertEqual((result.left_final, result.right_final), ("d", "c"))
        self.assertEqual((result.left_observation, result.right_observation), (2, 1))
        self.assertEqual(nav.compare("x", "y").actions, ("tick",))

    def test_equal_outputs_and_different_hidden_state_remain_equivalent(self):
        states = tuple(itertools.product((0, 1), (0, 1)))
        nav = FiniteDistinctionNavigator(
            states, ("flip", "stay"), ("visible",),
            lambda state, test: state[0],
            lambda state, action: (state[0], 1 - state[1]) if action == "flip" else state,
        )
        self.assertEqual(nav.compare((0, 0), (0, 1)).status, "equivalent")
        self.assertEqual(nav.compare((0, 0), (1, 0)).status, "distinguished")
        self.assertEqual(nav.checked_state_pairs, 6)
        self.assertEqual(nav.checked_transitions, 8)

    def test_tie_break_is_declared_action_order(self):
        states = ("a", "b", "c", "d", "e", "f")
        outputs = {s: 0 for s in states} | {"d": 1, "f": 1}
        edges = {
            "a": {"second": "c", "first": "e"},
            "b": {"second": "d", "first": "f"},
        }
        nav = FiniteDistinctionNavigator(
            states, ("first", "second"), ("read",),
            lambda s, t: outputs[s],
            lambda s, a: edges.get(s, {}).get(a, s),
        )
        self.assertEqual(nav.compare("a", "b").actions, ("first",))

    def test_no_actions_or_no_tests_cannot_invent_distinction(self):
        no_actions = FiniteDistinctionNavigator(
            (0, 1), (), ("value",), lambda s, t: s, lambda s, a: s
        )
        self.assertEqual(no_actions.compare(0, 1).status, "distinguished")
        no_tests = FiniteDistinctionNavigator(
            (0, 1), ("toggle",), (), lambda s, t: s,
            lambda s, a: 1 - s,
        )
        self.assertEqual(no_tests.compare(0, 1).status, "equivalent")
        self.assertEqual(no_tests.compare(0, 0).status, "equivalent")

    def test_fails_closed_when_model_is_incomplete(self):
        kwargs = dict(
            states=(0, 1), actions=("next",), tests=("value",),
            observation_fn=lambda s, t: s,
        )
        with self.assertRaisesRegex(ValueError, "finite state universe"):
            FiniteDistinctionNavigator(**kwargs, transition_fn=lambda s, a: s + 1)
        with self.assertRaisesRegex(ValueError, "undefined"):
            FiniteDistinctionNavigator(**kwargs, transition_fn=lambda s, a: 1 / 0)
        with self.assertRaisesRegex(ValueError, "pair budget"):
            FiniteDistinctionNavigator(**kwargs, transition_fn=lambda s, a: s, max_pairs=0)
        with self.assertRaises(ValueError):
            FiniteDistinctionNavigator((0, 0), (), (), lambda s, t: s, lambda s, a: s)
        with self.assertRaises(TypeError):
            FiniteDistinctionNavigator((0, 1), ([],), (), lambda s, t: s, lambda s, a: s)
        with self.assertRaises(ValueError):
            FiniteDistinctionNavigator((0, 1), (), (), lambda s, t: s, lambda s, a: s).compare(0, 2)
        with self.assertRaises(ValueError):
            FiniteDistinctionNavigator((0, 1), (), (), lambda s, t: s, lambda s, a: s, max_pairs=True)

    def test_random_finite_models_against_independent_word_enumeration(self):
        rng = random.Random(20261114)
        for _ in range(45):
            n = rng.randint(2, 5)
            states = tuple(range(n))
            actions = (0, 1)
            output = [rng.randrange(3) for _ in states]
            edge = {(s, a): rng.randrange(n) for s in states for a in actions}
            nav = FiniteDistinctionNavigator(
                states, actions, (0,), lambda s, t: output[s],
                lambda s, a: edge[(s, a)],
            )
            for i, j in itertools.combinations(states, 2):
                reference = None
                # In a finite pair graph, a shortest path to differing outputs
                # cannot repeat an unordered pair. n=5 -> <= 10 steps.
                for length in range(n * (n - 1) // 2 + 1):
                    for word in itertools.product(actions, repeat=length):
                        x, y = i, j
                        for action in word:
                            x, y = edge[(x, action)], edge[(y, action)]
                        if output[x] != output[y]:
                            reference = word
                            break
                    if reference is not None:
                        break
                result = nav.compare(i, j)
                if reference is None:
                    self.assertEqual(result.status, "equivalent")
                else:
                    self.assertEqual(result.status, "distinguished")
                    self.assertEqual(result.actions, reference)
                    x, y = i, j
                    for action in result.actions:
                        x, y = edge[(x, action)], edge[(y, action)]
                    self.assertEqual((result.left_final, result.right_final), (x, y))
                    self.assertEqual(result.left_observation, output[x])
                    self.assertEqual(result.right_observation, output[y])
                    self.assertNotEqual(output[x], output[y])


if __name__ == "__main__":
    unittest.main()
