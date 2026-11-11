import random
import unittest

from adaptive_attention import (
    AdaptiveObservation,
    PolicyNode,
    select_adaptive_policy,
)


def observation(name, cost, values):
    return AdaptiveObservation(name, cost, lambda state: values[state])


def evaluate_policy(node, state, observation_values):
    if node.query_result is not None:
        return node.query_result
    value = observation_values[node.observation_name][state]
    for outcome, child in node.branches:
        if outcome == value:
            return evaluate_policy(child, state, observation_values)
    raise AssertionError(f"no branch for observation outcome {value!r}")


class AdaptiveAttentionTests(unittest.TestCase):
    def test_already_resolved_query_needs_no_observations(self):
        plan = select_adaptive_policy(("a", "b"), lambda _: True, ())
        self.assertTrue(plan.complete)
        self.assertEqual(plan.expected_cost, 0.0)
        self.assertEqual(plan.selected_observations, ())
        self.assertEqual(plan.policy.query_result, True)

    def test_adaptive_policy_avoids_static_collect_everything_cost(self):
        hypotheses = ("A", "B", "C", "D")
        query = lambda state: state in ("A", "B")
        obs = [
            observation("coarse", 1.0, {"A": "left", "C": "left", "B": "right", "D": "right"}),
            observation("left-refinement", 1.0, {"A": "yes", "B": "same", "C": "no", "D": "same"}),
            observation("right-refinement", 1.0, {"A": "same", "B": "yes", "C": "same", "D": "no"}),
            observation("direct-but-costly", 2.5, {"A": True, "B": True, "C": False, "D": False}),
        ]
        plan = select_adaptive_policy(hypotheses, query, obs)
        self.assertTrue(plan.complete)
        self.assertEqual(plan.policy.observation_name, "coarse")
        self.assertAlmostEqual(plan.expected_cost, 2.0)
        self.assertAlmostEqual(plan.worst_case_cost, 2.0)
        self.assertEqual(set(plan.selected_observations), {"coarse", "left-refinement", "right-refinement"})

        observation_values = {
            "coarse": {"A": "left", "B": "right", "C": "left", "D": "right"},
            "left-refinement": {"A": "yes", "B": "same", "C": "no", "D": "same"},
            "right-refinement": {"A": "same", "B": "yes", "C": "same", "D": "no"},
        }
        for state in hypotheses:
            self.assertEqual(evaluate_policy(plan.policy, state, observation_values), query(state))

    def test_prior_weights_change_expected_cost_but_not_query_correctness(self):
        hypotheses = ("A", "B", "C", "D")
        query = lambda state: state in ("A", "B")
        observations = [
            observation("coarse", 1.0, {"A": "left", "C": "left", "B": "right", "D": "right"}),
            observation("left-refinement", 1.0, {"A": "yes", "B": "same", "C": "no", "D": "same"}),
            observation("right-refinement", 1.0, {"A": "same", "B": "yes", "C": "same", "D": "no"}),
            observation("direct", 2.5, {"A": True, "B": True, "C": False, "D": False}),
        ]
        uniform = select_adaptive_policy(hypotheses, query, observations)
        skewed = select_adaptive_policy(
            hypotheses,
            query,
            observations,
            weights={"A": 100.0, "B": 1.0, "C": 1.0, "D": 1.0},
        )
        self.assertTrue(uniform.complete and skewed.complete)
        self.assertLess(skewed.expected_cost, uniform.expected_cost)

    def test_unresolvable_cross_query_pair_is_reported(self):
        plan = select_adaptive_policy(
            ("true-a", "true-b", "false-a", "false-b"),
            lambda state: state.startswith("true"),
            [observation("same-pair", 1.0, {
                "true-a": 0, "true-b": 1, "false-a": 0, "false-b": 1
            })],
        )
        self.assertFalse(plan.complete)
        self.assertIsNone(plan.policy)
        self.assertEqual(len(plan.unresolved_pairs), 2)

    def test_random_small_policies_match_independent_reference_recurrence(self):
        rng = random.Random(20261111)
        for sample in range(24):
            with self.subTest(sample=sample):
                states = tuple(f"s{i}" for i in range(5))
                truth = set(rng.sample(states, rng.randint(1, 4)))
                query = lambda state, wanted=truth: state in wanted
                weights = {state: rng.randint(1, 8) for state in states}
                candidates = []
                for index in range(4):
                    values = {state: rng.randrange(3) for state in states}
                    candidates.append(observation(f"o{index}", rng.randint(1, 7), values))
                values = [
                    {state: candidate.observe(state) for state in states}
                    for candidate in candidates
                ]

                memo = {}
                def reference(mask):
                    if mask in memo:
                        return memo[mask]
                    members = [states[i] for i in range(len(states)) if mask & (1 << i)]
                    results = {query(state) for state in members}
                    if len(results) == 1:
                        memo[mask] = 0.0
                        return 0.0
                    best = float("inf")
                    for index, candidate in enumerate(candidates):
                        groups = {}
                        for i, state in enumerate(states):
                            if mask & (1 << i):
                                outcome = values[index][state]
                                groups.setdefault(outcome, 0)
                                groups[outcome] |= 1 << i
                        if len(groups) <= 1:
                            continue
                        children = [(group, reference(group)) for group in groups.values()]
                        if any(cost == float("inf") for _, cost in children):
                            continue
                        mass = sum(weights[s] for s in members)
                        expected = float(candidate.cost) + sum(
                            (sum(weights[states[i]] for i in range(len(states)) if group & (1 << i)) / mass) * cost
                            for group, cost in children
                        )
                        best = min(best, expected)
                    memo[mask] = best
                    return best

                pairs_unresolved = any(
                    query(a) and not query(b) and all(values[j][a] == values[j][b] for j in range(len(candidates)))
                    for a in states for b in states
                )
                plan = select_adaptive_policy(states, query, candidates, weights=weights)
                if pairs_unresolved:
                    self.assertFalse(plan.complete)
                else:
                    self.assertTrue(plan.complete)
                    self.assertAlmostEqual(plan.expected_cost, reference((1 << len(states)) - 1))

    def test_bad_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            select_adaptive_policy((), lambda _: True, ())
        with self.assertRaises(ValueError):
            select_adaptive_policy(("a", "b"), lambda _: True, (), weights={"a": 1.0})
        with self.assertRaises(TypeError):
            select_adaptive_policy(("a",), lambda _: 1, ())
        with self.assertRaises(ValueError):
            select_adaptive_policy(("a",), lambda _: True, (), max_hypotheses=0)
        with self.assertRaises(ValueError):
            select_adaptive_policy(("a", "b"), lambda _: True, [
                observation("bad-cost", float("inf"), {"a": 0, "b": 1})
            ])
        with self.assertRaises(ValueError):
            select_adaptive_policy(
                tuple(range(4)),
                lambda x: x % 2 == 0,
                (),
                max_hypotheses=3,
            )


if __name__ == "__main__":
    unittest.main()
