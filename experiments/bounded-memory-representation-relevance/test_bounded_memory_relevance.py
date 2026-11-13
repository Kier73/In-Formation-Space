import unittest
from fractions import Fraction
from bounded_memory_relevance import ControllerLimitError, build_report, validate_report


def fixture():
    return dict(
        states=("a", "b", "after-a", "after-b", "dead"),
        actions=("prepare", "protect-a", "protect-b"),
        initial_distribution={"a": "1/2", "b": "1/2", "after-a": 0, "after-b": 0, "dead": 0},
        transitions={
            "prepare": {"a": "after-a", "b": "after-b", "after-a": "dead", "after-b": "dead", "dead": "dead"},
            "protect-a": {"a": "dead", "b": "dead", "after-a": "after-a", "after-b": "dead", "dead": "dead"},
            "protect-b": {"a": "dead", "b": "dead", "after-a": "dead", "after-b": "after-b", "dead": "dead"},
        },
        viable_states=("a", "b", "after-a", "after-b"),
        representations=(
            {"representation_id": "fine", "cells": {"a": "A", "b": "B", "after-a": "C", "after-b": "C", "dead": "C"}},
            {"representation_id": "coarse", "cells": {"a": "A", "b": "A", "after-a": "C", "after-b": "C", "dead": "C"}},
        ),
        ablations=({"baseline": "fine", "ablated": "coarse"},),
        horizon=2, memory_sizes=(1, 2),
    )


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


class BoundedMemoryRelevanceTests(unittest.TestCase):
    def test_two_memory_states_preserve_full_history_value(self):
        report = build_report(**fixture())
        fine = report["profiles"]["fine"]
        values = [ratio(item["max_survival_probability"]) for item in fine["finite_state_controllers"]]
        self.assertEqual(values, [Fraction(1, 2), Fraction(1)])
        self.assertEqual(ratio(fine["full_history_target"]["max_survival_probability"]), 1)
        self.assertEqual(fine["smallest_tested_memory_size_attaining_history_value"], 2)

    def test_one_memory_state_reproduces_stationary_value(self):
        report = build_report(**fixture())
        fine = report["profiles"]["fine"]["finite_state_controllers"][0]
        self.assertEqual(ratio(fine["max_survival_probability"]), Fraction(1, 2))

    def test_coarse_representation_cannot_recover_removed_distinction(self):
        report = build_report(**fixture())
        coarse = report["profiles"]["coarse"]
        values = [ratio(item["max_survival_probability"]) for item in coarse["finite_state_controllers"]]
        self.assertEqual(values, [Fraction(1, 2), Fraction(1, 2)])
        self.assertEqual(coarse["smallest_tested_memory_size_attaining_history_value"], 1)

    def test_controller_witness_retains_distinct_initial_observations(self):
        report = build_report(**fixture())
        controller = report["profiles"]["fine"]["finite_state_controllers"][1]["optimal_controller"]
        action = {(x["memory_state"], x["observation"]): x["action"] for x in controller["action_map"]}
        update = {(x["memory_state"], x["observation"]): x["next_memory_state"] for x in controller["memory_update_map"]}
        self.assertEqual(action[(0, "A")], "prepare")
        self.assertEqual(action[(0, "B")], "prepare")
        self.assertNotEqual(update[(0, "A")], update[(0, "B")])
        self.assertEqual(action[(update[(0, "A")], "C")], "protect-a")
        self.assertEqual(action[(update[(0, "B")], "C")], "protect-b")

    def test_controller_value_is_bounded_by_full_history_value(self):
        report = build_report(**fixture())
        for profile in report["profiles"].values():
            target = ratio(profile["full_history_target"]["max_survival_probability"])
            for controller in profile["finite_state_controllers"]:
                self.assertLessEqual(ratio(controller["max_survival_probability"]), target)

    def test_memory_sizes_must_be_unique_positive_integers(self):
        for sizes in ((0,), (1, 1), (True, 2), (1.5,)):
            f = fixture()
            f["memory_sizes"] = sizes
            with self.assertRaises(ValueError):
                build_report(**f)

    def test_controller_enumeration_has_an_explicit_cap(self):
        f = fixture()
        f["max_controllers"] = 100
        with self.assertRaises(ControllerLimitError):
            build_report(**f)

    def test_exact_probability_inputs_reject_floats(self):
        f = fixture()
        f["initial_distribution"]["a"] = 0.5
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_ablation_requires_a_true_coarsening(self):
        f = fixture()
        f["representations"] = (
            {"representation_id": "fine", "cells": {"a": "A", "b": "A", "after-a": "C", "after-b": "D", "dead": "C"}},
            {"representation_id": "coarse", "cells": {"a": "X", "b": "Y", "after-a": "C", "after-b": "C", "dead": "C"}},
        )
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_report_reconstruction_rejects_tampering(self):
        report = build_report(**fixture())
        self.assertEqual(validate_report(report), report)
        report["profiles"]["fine"]["smallest_tested_memory_size_attaining_history_value"] = 1
        with self.assertRaises(ValueError):
            validate_report(report)


if __name__ == "__main__":
    unittest.main()
