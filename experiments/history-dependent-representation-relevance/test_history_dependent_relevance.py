import unittest
from fractions import Fraction

from history_dependent_relevance import PolicyLimitError, build_report, validate_report


def memory_fixture():
    return dict(
        states=("a", "b", "after-a", "after-b", "dead"),
        actions=("prepare", "protect-a", "protect-b"),
        initial_distribution={"a": "1/2", "b": "1/2", "after-a": 0, "after-b": 0, "dead": 0},
        transitions={
            "prepare": {
                "a": "after-a", "b": "after-b",
                "after-a": "dead", "after-b": "dead", "dead": "dead",
            },
            "protect-a": {
                "a": "dead", "b": "dead",
                "after-a": "after-a", "after-b": "dead", "dead": "dead",
            },
            "protect-b": {
                "a": "dead", "b": "dead",
                "after-a": "dead", "after-b": "after-b", "dead": "dead",
            },
        },
        viable_states=("a", "b", "after-a", "after-b"),
        representations=(
            {"representation_id": "fine", "cells": {
                "a": "A", "b": "B", "after-a": "C", "after-b": "C", "dead": "C",
            }},
            {"representation_id": "coarse", "cells": {
                "a": "A", "b": "A", "after-a": "C", "after-b": "C", "dead": "C",
            }},
        ),
        ablations=({"baseline": "fine", "ablated": "coarse"},),
        horizon=2,
    )


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


class HistoryDependentRelevanceTests(unittest.TestCase):
    def test_memory_retains_distinction_after_current_observations_converge(self):
        report = build_report(**memory_fixture())
        fine, coarse = report["profiles"]["fine"], report["profiles"]["coarse"]
        self.assertEqual(ratio(fine["stationary"]["max_survival_probability"]), Fraction(1, 2))
        self.assertEqual(ratio(fine["time_aware_reactive"]["max_survival_probability"]), Fraction(1, 2))
        self.assertEqual(ratio(fine["history_dependent"]["max_survival_probability"]), Fraction(1))
        self.assertEqual(ratio(coarse["stationary"]["max_survival_probability"]), Fraction(1, 2))
        self.assertEqual(ratio(coarse["time_aware_reactive"]["max_survival_probability"]), Fraction(1, 2))
        self.assertEqual(ratio(coarse["history_dependent"]["max_survival_probability"]), Fraction(1, 2))
        ablation = report["ablations"][0]
        self.assertEqual(ratio(ablation["time_aware_viability_loss"]), 0)
        self.assertEqual(ratio(ablation["history_viability_loss"]), Fraction(1, 2))
        self.assertEqual(ratio(fine["history_memory_gain"]), Fraction(1, 2))

    def test_history_controller_never_underperforms_time_aware_reactive_controller(self):
        report = build_report(**memory_fixture())
        for profile in report["profiles"].values():
            self.assertGreaterEqual(
                ratio(profile["history_dependent"]["max_survival_probability"]),
                ratio(profile["time_aware_reactive"]["max_survival_probability"]),
            )

    def test_memory_adds_nothing_when_horizon_is_one(self):
        f = memory_fixture()
        f["horizon"] = 1
        report = build_report(**f)
        for profile in report["profiles"].values():
            self.assertEqual(ratio(profile["history_memory_gain"]), 0)

    def test_survival_requires_viability_at_every_step(self):
        f = memory_fixture()
        f["transitions"] = {
            action: {
                "a": "dead", "b": "dead", "after-a": "dead",
                "after-b": "dead", "dead": "dead",
            } for action in f["actions"]
        }
        report = build_report(**f)
        for profile in report["profiles"].values():
            self.assertEqual(ratio(profile["history_dependent"]["max_survival_probability"]), 0)

    def test_exact_probability_inputs_reject_floats(self):
        f = memory_fixture()
        f["initial_distribution"]["a"] = 0.5
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_history_policy_enumeration_is_explicitly_bounded(self):
        f = memory_fixture()
        f["max_policies"] = 10
        with self.assertRaises(PolicyLimitError):
            build_report(**f)

    def test_ablation_requires_a_true_coarsening(self):
        f = memory_fixture()
        f["representations"] = (
            {"representation_id": "fine", "cells": {
                "a": "A", "b": "A", "after-a": "C", "after-b": "D", "dead": "C",
            }},
            {"representation_id": "coarse", "cells": {
                "a": "X", "b": "Y", "after-a": "C", "after-b": "C", "dead": "C",
            }},
        )
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_report_reconstruction_rejects_tampering(self):
        report = build_report(**memory_fixture())
        self.assertEqual(validate_report(report), report)
        report["profiles"]["fine"]["history_memory_gain"] = {"numerator": 0, "denominator": 1}
        with self.assertRaises(ValueError):
            validate_report(report)

    def test_history_witness_uses_observation_history(self):
        report = build_report(**memory_fixture())
        witness = report["profiles"]["fine"]["history_dependent"]["optimal_policy"]
        mapping = {tuple(item["observation_history"]): item["action"] for item in witness}
        self.assertEqual(mapping[("A",)], "prepare")
        self.assertEqual(mapping[("B",)], "prepare")
        self.assertEqual(mapping[("A", "C")], "protect-a")
        self.assertEqual(mapping[("B", "C")], "protect-b")

    def test_time_awareness_is_separated_from_memory(self):
        report = build_report(
            states=("start", "middle", "dead"),
            actions=("advance", "complete"),
            initial_distribution={"start": 1, "middle": 0, "dead": 0},
            transitions={
                "advance": {"start": "middle", "middle": "dead", "dead": "dead"},
                "complete": {"start": "dead", "middle": "middle", "dead": "dead"},
            },
            viable_states=("start", "middle"),
            representations=(
                {"representation_id": "fine", "cells": {"start": "O", "middle": "O", "dead": "D"}},
                {"representation_id": "coarse", "cells": {"start": "O", "middle": "O", "dead": "D"}},
            ),
            ablations=({"baseline": "fine", "ablated": "coarse"},),
            horizon=2,
        )
        profile = report["profiles"]["fine"]
        self.assertEqual(ratio(profile["stationary"]["max_survival_probability"]), 0)
        self.assertEqual(ratio(profile["time_aware_reactive"]["max_survival_probability"]), 1)
        self.assertEqual(ratio(profile["history_dependent"]["max_survival_probability"]), 1)
        self.assertEqual(ratio(profile["time_awareness_gain"]), 1)
        self.assertEqual(ratio(profile["history_memory_gain"]), 0)


if __name__ == "__main__":
    unittest.main()
