import itertools
import random
import unittest

from query_attention import QueryObservation, select_query_packet


def observation(name, cost, values):
    return QueryObservation(name, cost, lambda state: values[state])


class QueryDirectedAttentionTests(unittest.TestCase):
    def test_query_already_determined_requires_no_observation(self):
        hypotheses = ("a", "b", "c")
        plan = select_query_packet(
            hypotheses,
            query=lambda state: True,
            observations=(),
        )
        self.assertTrue(plan.complete)
        self.assertEqual(plan.cross_boundary_pair_count, 0)
        self.assertEqual(plan.selected_names, ())
        self.assertEqual(plan.total_cost, 0.0)

    def test_selects_minimum_cost_packet_without_identifying_each_side(self):
        hypotheses = ("t1", "t2", "f1", "f2")
        query = lambda state: state.startswith("t")
        plan = select_query_packet(
            hypotheses,
            query=query,
            observations=[
                observation("all-separating-expensive", 3.0, {"t1": 1, "t2": 1, "f1": 0, "f2": 0}),
                observation("separate-t1", 1.0, {"t1": 1, "t2": 0, "f1": 0, "f2": 0}),
                observation("separate-t2", 1.0, {"t1": 0, "t2": 1, "f1": 0, "f2": 0}),
            ],
        )
        self.assertTrue(plan.complete)
        self.assertTrue(plan.exact)
        self.assertEqual(plan.selected_names, ("separate-t1", "separate-t2"))
        self.assertEqual(plan.total_cost, 2.0)
        self.assertEqual(plan.cross_boundary_pair_count, 4)
        self.assertEqual(plan.separated_pair_count, 4)

    def test_does_not_pay_to_distinguish_hypotheses_on_same_query_side(self):
        hypotheses = ("t1", "t2", "f1", "f2")
        plan = select_query_packet(
            hypotheses,
            query=lambda state: state.startswith("t"),
            observations=[
                observation("side-marker", 0.5, {"t1": "T", "t2": "T", "f1": "F", "f2": "F"})
            ],
        )
        self.assertTrue(plan.complete)
        self.assertEqual(plan.selected_names, ("side-marker",))
        self.assertEqual(plan.total_cost, 0.5)

    def test_unresolvable_cross_query_pair_is_reported(self):
        hypotheses = ("true-a", "true-b", "false-a", "false-b")
        plan = select_query_packet(
            hypotheses,
            query=lambda state: state.startswith("true"),
            observations=[
                observation("same-on-hard-pair", 1.0, {
                    "true-a": 0, "true-b": 1, "false-a": 0, "false-b": 1
                })
            ],
        )
        self.assertFalse(plan.complete)
        self.assertEqual(len(plan.unresolved_pairs), 2)

    def test_poset_linear_extensions_can_leave_target_relation_unresolvable(self):
        events = ("C0", "C1", "S0", "S1")
        extensions = [
            order for order in itertools.permutations(events)
            if order.index("C0") < order.index("C1")
            and order.index("S0") < order.index("S1")
        ]
        self.assertEqual(len(extensions), 6)

        query = lambda order: order.index("C0") < order.index("S0")
        available = []
        for left, right in itertools.combinations(events, 2):
            if (left, right) == ("C0", "S0"):
                continue
            if (left, right) == ("S0", "C0"):
                continue
            available.append(
                QueryObservation(
                    f"compare:{left}:{right}",
                    1.0,
                    lambda order, a=left, b=right: order.index(a) < order.index(b),
                )
            )

        unresolved = select_query_packet(extensions, query, available)
        self.assertFalse(unresolved.complete)
        self.assertTrue(unresolved.exact)
        self.assertEqual(len(unresolved.unresolved_pairs), 2)

        direct = QueryObservation(
            "shared-clock-compare:C0:S0",
            2.0,
            lambda order: order.index("C0") < order.index("S0"),
        )
        resolved = select_query_packet(extensions, query, available + [direct])
        self.assertTrue(resolved.complete)
        self.assertEqual(resolved.selected_names, ("shared-clock-compare:C0:S0",))
        self.assertEqual(resolved.total_cost, 2.0)

    def test_greedy_fallback_is_labelled_and_complete(self):
        hypotheses = ("t1", "t2", "t3", "f1", "f2", "f3")
        values = {state: (1 if state.startswith("t") else 0) for state in hypotheses}
        plan = select_query_packet(
            hypotheses,
            query=lambda state: state.startswith("t"),
            observations=[observation("one-sensor", 1.0, values)],
            max_exact_pairs=2,
        )
        self.assertTrue(plan.complete)
        self.assertFalse(plan.exact)
        self.assertEqual(plan.solver, "greedy-cross-pair-cover")

    def test_exact_solver_matches_brute_force_random_small_instances(self):
        rng = random.Random(20261111)
        for sample in range(35):
            with self.subTest(sample=sample):
                hypotheses = tuple(f"s{i}" for i in range(6))
                true_count = rng.randint(1, 5)
                true_states = set(rng.sample(hypotheses, true_count))
                query = lambda state, true=true_states: state in true
                candidates = []
                for index in range(6):
                    values = {state: rng.randrange(3) for state in hypotheses}
                    candidates.append(observation(f"o{index}", rng.randint(1, 7), values))

                plan = select_query_packet(hypotheses, query, candidates)
                candidate_values = [
                    {state: candidate.observe(state) for state in hypotheses}
                    for candidate in candidates
                ]
                pairs = [
                    (a, b)
                    for a in hypotheses if query(a)
                    for b in hypotheses if not query(b)
                ]
                best = None
                for mask in range(1 << len(candidates)):
                    covered = set()
                    cost = 0.0
                    for index, candidate in enumerate(candidates):
                        if mask & (1 << index):
                            cost += float(candidate.cost)
                            values = candidate_values[index]
                            covered.update(
                                (a, b) for a, b in pairs if values[a] != values[b]
                            )
                    if len(covered) == len(pairs) and (best is None or cost < best):
                        best = cost

                self.assertTrue(plan.exact)
                if best is None:
                    self.assertFalse(plan.complete)
                else:
                    self.assertTrue(plan.complete)
                    self.assertEqual(plan.total_cost, best)

    def test_bad_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            select_query_packet((), lambda _: True, ())
        with self.assertRaises(TypeError):
            select_query_packet(("a",), lambda _: 1, ())
        with self.assertRaises(ValueError):
            select_query_packet(("a",), lambda _: True, (), max_exact_pairs=0)
        with self.assertRaises(ValueError):
            select_query_packet(
                ("a", "b"),
                lambda state: state == "a",
                [observation("bad-cost", 0.0, {"a": 0, "b": 1})],
            )
        with self.assertRaises(ValueError):
            select_query_packet(
                ("a", "b"),
                lambda state: state == "a",
                [
                    observation("duplicate", 1.0, {"a": 0, "b": 1}),
                    observation("duplicate", 1.0, {"a": 0, "b": 1}),
                ],
            )


if __name__ == "__main__":
    unittest.main()
