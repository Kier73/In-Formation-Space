import unittest

from attention_selection import (
    ObservationCandidate,
    select_attention_packet,
)


def candidate(name, cost, values):
    return ObservationCandidate(name, cost, lambda state: values[state])


class ActiveDistinctionSelectionTests(unittest.TestCase):
    def test_already_unique_target_needs_no_observation(self):
        states = ("target", "other")
        plan = select_attention_packet(
            states,
            target="target",
            candidates=(),
            current_signatures={"target": "unique", "other": "other"},
        )
        self.assertTrue(plan.complete)
        self.assertTrue(plan.exact)
        self.assertEqual(plan.selected_names, ())
        self.assertEqual(plan.total_cost, 0.0)

    def test_one_candidate_can_isolate_target(self):
        states = ("target", "a", "b")
        plan = select_attention_packet(
            states,
            target="target",
            candidates=[
                candidate("sensor-a", 2.0, {"target": 0, "a": 1, "b": 1})
            ],
        )
        self.assertTrue(plan.complete)
        self.assertEqual(plan.selected_names, ("sensor-a",))
        self.assertEqual(plan.separated_states, ("a", "b"))
        self.assertEqual(plan.total_cost, 2.0)

    def test_exact_solver_finds_minimum_cost_observation_packet(self):
        states = ("target", "a", "b", "c")
        plan = select_attention_packet(
            states,
            target="target",
            candidates=[
                candidate("covers-ab", 1.0, {"target": 0, "a": 1, "b": 1, "c": 0}),
                candidate("covers-bc", 1.0, {"target": 0, "a": 0, "b": 1, "c": 1}),
                candidate("covers-ac", 1.0, {"target": 0, "a": 1, "b": 0, "c": 1}),
                candidate("covers-all-expensive", 2.5, {"target": 0, "a": 1, "b": 1, "c": 1}),
            ],
        )
        self.assertTrue(plan.complete)
        self.assertTrue(plan.exact)
        self.assertEqual(plan.selected_names, ("covers-ab", "covers-bc"))
        self.assertEqual(plan.total_cost, 2.0)

    def test_uses_only_target_equivalence_class(self):
        states = ("target", "ambiguous", "already-known")
        signatures = {"target": ("known",), "ambiguous": ("known",), "already-known": ("other",)}
        plan = select_attention_packet(
            states,
            target="target",
            current_signatures=signatures,
            candidates=[
                candidate("disambiguator", 1.0, {"target": "T", "ambiguous": "A", "already-known": "X"})
            ],
        )
        self.assertEqual(plan.ambiguity_before, 1)
        self.assertEqual(plan.separated_states, ("ambiguous",))

    def test_unseparable_state_is_reported_as_incomplete(self):
        states = ("target", "a", "b")
        plan = select_attention_packet(
            states,
            target="target",
            candidates=[
                candidate("only-separates-a", 1.0, {"target": 0, "a": 1, "b": 0})
            ],
        )
        self.assertFalse(plan.complete)
        self.assertEqual(plan.separated_states, ("a",))
        self.assertEqual(plan.unseparable_states, ("b",))

    def test_large_ambiguity_uses_greedy_fallback(self):
        states = ("target",) + tuple(f"s{i}" for i in range(22))
        values = {"target": 0, **{f"s{i}": 1 for i in range(22)}}
        plan = select_attention_packet(
            states,
            target="target",
            candidates=[candidate("all-states", 1.0, values)],
            max_exact_alternatives=20,
        )
        self.assertTrue(plan.complete)
        self.assertFalse(plan.exact)
        self.assertEqual(plan.solver, "greedy-set-cover")
        self.assertEqual(plan.selected_names, ("all-states",))

    def test_bad_candidates_and_signatures_are_rejected(self):
        states = ("target", "a")
        with self.assertRaises(ValueError):
            select_attention_packet(states, target="missing", candidates=())
        with self.assertRaises(ValueError):
            select_attention_packet(states, target="target", candidates=[candidate("bad", 0.0, {"target": 0, "a": 1})])
        with self.assertRaises(ValueError):
            select_attention_packet(states, target="target", candidates=[
                candidate("dup", 1.0, {"target": 0, "a": 1}),
                candidate("dup", 1.0, {"target": 0, "a": 1}),
            ])
        with self.assertRaises(ValueError):
            select_attention_packet(states, target="target", candidates=(), current_signatures={"target": ()})
        with self.assertRaises(TypeError):
            select_attention_packet(
                states,
                target="target",
                candidates=[ObservationCandidate("bad-output", 1.0, lambda state: [])],
            )


if __name__ == "__main__":
    unittest.main()
