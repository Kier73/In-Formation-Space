"""OE-004 finite Ground semantics tested separately from live E-CPU artifact audit."""

import copy
import unittest

from witness_binding import (
    plan_parity_distinction, filter_parity_candidates, digest
)


class ParityWitnessTests(unittest.TestCase):
    def test_zero_action_witness_distinguishes_parity_not_full_phase(self):
        plan = plan_parity_distinction([0, 1, 2, 3], "pinned-source-policy")
        self.assertEqual(plan["status"], "planned-not-executed")
        self.assertEqual(plan["selected"]["actions"], [])
        self.assertEqual(plan["selected"]["test"], "parity")
        self.assertEqual(plan["selected"]["expected"]["left"]["value"], 0)
        self.assertEqual(plan["selected"]["expected"]["right"]["value"], 1)
        self.assertEqual(plan["selected"]["estimated_total_ns"], 1)
        self.assertEqual(digest({k:v for k,v in plan.items() if k!="plan_digest"}),
                         plan["plan_digest"])
        self.assertEqual(filter_parity_candidates([0, 1, 2, 3], 0),
                         ([0, 2], [1, 3]))
        self.assertEqual(filter_parity_candidates([0, 1, 2, 3], 1),
                         ([1, 3], [0, 2]))

    def test_witness_is_independent_of_reading_and_filters_both_branches(self):
        plan = plan_parity_distinction([1, 2, 5, 6], "policy-A")
        self.assertEqual(plan["selected"]["expected"]["left"]["state"], "2")
        self.assertEqual(plan["selected"]["expected"]["right"]["state"], "1")
        self.assertEqual(filter_parity_candidates([1, 2, 5, 6], 1),
                         ([1, 5], [2, 6]))
        self.assertEqual(filter_parity_candidates([1, 2, 5, 6], 0),
                         ([2, 6], [1, 5]))

    def test_same_observation_class_does_not_prove_unique_state(self):
        remaining, excluded = filter_parity_candidates([0, 1, 2, 3], 0)
        self.assertEqual(len(remaining), 2)
        self.assertEqual(len(excluded), 2)

    def test_nonseparating_fiber_refused(self):
        with self.assertRaisesRegex(ValueError, "does not distinguish"):
            plan_parity_distinction([0, 2, 4, 6], "policy-A")

    def test_untrusted_candidates_refused(self):
        for states in ([], [0, 0, 1], [3, 1, 2], [0, True, 1], [0, 8],
                       [0, -1], ["0", "1"]):
            with self.subTest(states=states), self.assertRaises(ValueError):
                plan_parity_distinction(states, "policy-A")

    def test_missing_policy_refused(self):
        with self.assertRaises(ValueError):
            plan_parity_distinction([0, 1], "")

    def test_invalid_signed_reading_refused(self):
        for reading in (None, True, 2, -1, 1.0, "1"):
            with self.subTest(reading=reading), self.assertRaises(ValueError):
                filter_parity_candidates([0, 1], reading)

    def test_input_model_is_not_modified(self):
        candidate_set = [0, 1, 2, 3]
        original = copy.deepcopy(candidate_set)
        plan_parity_distinction(candidate_set, "policy-A")
        filter_parity_candidates(candidate_set, 1)
        self.assertEqual(candidate_set, original)


if __name__ == "__main__":
    unittest.main()
