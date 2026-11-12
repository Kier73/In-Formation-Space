import unittest
from fractions import Fraction
from task_relative_relevance import PolicyLimitError, build_report, validate_report


def fixture(relevant=True):
    transitions = {
        "protect-a": {"a": "a", "b": "dead", "dead": "dead"},
        "protect-b": {"a": "dead" if relevant else "a", "b": "b", "dead": "dead"},
    }
    return dict(
        states=("a", "b", "dead"), actions=("protect-a", "protect-b"),
        initial_distribution={"a": "1/2", "b": "1/2", "dead": 0},
        transitions=transitions, viable_states=("a", "b"), horizon=1,
        representations=(
            {"representation_id": "fine", "cells": {"a": "A", "b": "B", "dead": "D"}},
            {"representation_id": "coarse", "cells": {"a": "X", "b": "X", "dead": "D"}},
        ), ablations=({"baseline": "fine", "ablated": "coarse"},),
    )


class RelevanceTests(unittest.TestCase):
    def test_task_relevant_distinction_loses_half_survival(self):
        r = build_report(**fixture())
        self.assertEqual(Fraction(**r["ablations"][0]["task_relative_viability_loss"]), Fraction(1, 2))

    def test_redundant_distinction_has_zero_loss(self):
        r = build_report(**fixture(False))
        self.assertEqual(Fraction(**r["ablations"][0]["task_relative_viability_loss"]), Fraction(0))

    def test_refinement_cannot_have_negative_loss(self):
        self.assertGreaterEqual(Fraction(**build_report(**fixture())["ablations"][0]["task_relative_viability_loss"]), 0)

    def test_survival_requires_viability_at_every_step(self):
        f = fixture()
        f["states"] = ("a", "b", "recover", "dead")
        f["initial_distribution"] = {"a": 1, "b": 0, "recover": 0, "dead": 0}
        f["transitions"] = {
            action: {"a": "recover", "b": "dead", "recover": "a", "dead": "a"}
            for action in f["actions"]
        }
        f["representations"] = (
            {"representation_id": "fine", "cells": {"a": "A", "b": "B", "recover": "R", "dead": "D"}},
            {"representation_id": "coarse", "cells": {"a": "X", "b": "X", "recover": "R", "dead": "D"}},
        )
        r = build_report(**f)
        self.assertEqual(Fraction(**r["profiles"]["fine"]["max_survival_probability"]), 0)

    def test_noncongruence_and_viability_alignment_are_separate(self):
        p = build_report(**fixture())["profiles"]["coarse"]
        self.assertTrue(p["viability_aligned"])
        self.assertFalse(p["transition_congruent"])

    def test_float_probabilities_are_rejected(self):
        f = fixture(); f["initial_distribution"] = {"a": 0.5, "b": 0.5, "dead": 0.0}
        with self.assertRaises(ValueError): build_report(**f)

    def test_policy_bound_is_explicit(self):
        f = fixture(); f["max_policies"] = 1
        with self.assertRaises(PolicyLimitError): build_report(**f)

    def test_validator_reconstructs_and_rejects_tampering(self):
        r = build_report(**fixture())
        self.assertEqual(validate_report(r), r)
        r["profiles"]["fine"]["max_survival_probability"] = {"numerator": 0, "denominator": 1}
        with self.assertRaises(ValueError): validate_report(r)

    def test_coarse_must_be_a_coarsening_of_baseline(self):
        f = fixture()
        f["representations"] = (
            {"representation_id": "fine", "cells": {"a": "A", "b": "A", "dead": "D"}},
            {"representation_id": "coarse", "cells": {"a": "X", "b": "Y", "dead": "D"}},
        )
        with self.assertRaises(ValueError): build_report(**f)


if __name__ == "__main__":
    unittest.main()
