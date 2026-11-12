import unittest
from fractions import Fraction

from intervention_attention import (
    FrontierLimitError,
    build_intervention_attention_frontier,
    validate_intervention_attention_document,
)


def transition(outcome, next_state, intervention=0):
    return {
        "outcome": outcome,
        "next_state": next_state,
        "intervention_cost": intervention,
    }


def metric(plan, name, frontier_index=0):
    value = plan["frontier"][frontier_index]["costs"][name]
    return Fraction(value["numerator"], value["denominator"])


class InterventionAttentionTests(unittest.TestCase):
    def test_intervention_can_enable_a_later_observation(self):
        plan = build_intervention_attention_frontier(
            world_states=("a0", "b0", "a1", "b1"),
            hypotheses=(
                {"hypothesis_id": "A", "initial_state": "a0", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "B", "initial_state": "b0", "query_value": False, "prior": "1/2"},
            ),
            probes=(
                {
                    "probe_id": "prepare",
                    "observation_cost": 1,
                    "transitions": {
                        "a0": transition("ready", "a1", 1),
                        "b0": transition("ready", "b1", 1),
                        "a1": transition("ready", "a1", 1),
                        "b1": transition("ready", "b1", 1),
                    },
                },
                {
                    "probe_id": "read",
                    "observation_cost": 1,
                    "transitions": {
                        "a0": transition("same", "a0"),
                        "b0": transition("same", "b0"),
                        "a1": transition("positive", "a1"),
                        "b1": transition("negative", "b1"),
                    },
                },
            ),
            max_depth=2,
        )
        self.assertEqual(plan["status"], "complete_frontier")
        self.assertEqual(plan["frontier"][0]["policy"]["probe_id"], "prepare")
        child = plan["frontier"][0]["policy"]["branches"][0]["child"]
        self.assertEqual(child["probe_id"], "read")
        self.assertEqual(metric(plan, "expected_observation"), Fraction(2))
        self.assertEqual(metric(plan, "expected_intervention"), Fraction(1))
        self.assertEqual(metric(plan, "worst_case_observation"), Fraction(2))
        self.assertEqual(metric(plan, "worst_case_intervention"), Fraction(1))
        self.assertEqual(plan["query_scope"], "initial_hypothesis")

    def test_nonintervening_reduction_preserves_trial_06_fixture(self):
        states = ("A", "B", "C", "D")
        truth = {"A", "B"}
        observations = {
            "coarse": {"A": "left", "B": "right", "C": "left", "D": "right"},
            "left-refinement": {"A": "yes", "B": "same", "C": "no", "D": "same"},
            "right-refinement": {"A": "same", "B": "yes", "C": "same", "D": "no"},
            "direct": {"A": "yes", "B": "yes", "C": "no", "D": "no"},
        }
        costs = {"coarse": 1, "left-refinement": 1, "right-refinement": 1, "direct": "5/2"}
        probes = [
            {
                "probe_id": name,
                "observation_cost": costs[name],
                "transitions": {
                    state: transition(values[state], state, 0)
                    for state in states
                },
            }
            for name, values in observations.items()
        ]
        plan = build_intervention_attention_frontier(
            world_states=states,
            hypotheses=tuple(
                {
                    "hypothesis_id": state,
                    "initial_state": state,
                    "query_value": state in truth,
                    "prior": "1/4",
                }
                for state in states
            ),
            probes=probes,
            max_depth=4,
        )
        optimum = min(
            Fraction(item["costs"]["expected_observation"]["numerator"],
                     item["costs"]["expected_observation"]["denominator"])
            for item in plan["frontier"]
        )
        self.assertEqual(plan["status"], "complete_frontier")
        self.assertEqual(optimum, Fraction(3, 2))
        self.assertTrue(all(metric(plan, "expected_intervention", i) == 0
                            for i in range(len(plan["frontier"]))))

    def test_pareto_frontier_keeps_safe_slow_and_fast_invasive_options(self):
        plan = build_intervention_attention_frontier(
            world_states=("a", "b", "a2", "b2"),
            hypotheses=(
                {"hypothesis_id": "yes", "initial_state": "a", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "no", "initial_state": "b", "query_value": False, "prior": "1/2"},
            ),
            probes=(
                {
                    "probe_id": "safe-slow",
                    "observation_cost": 3,
                    "transitions": {
                        "a": transition("yes", "a"), "b": transition("no", "b"),
                        "a2": transition("yes", "a2"), "b2": transition("no", "b2"),
                    },
                },
                {
                    "probe_id": "fast-invasive",
                    "observation_cost": 1,
                    "transitions": {
                        "a": transition("yes", "a2", 2), "b": transition("no", "b2", 2),
                        "a2": transition("yes", "a2", 2), "b2": transition("no", "b2", 2),
                    },
                },
            ),
            max_depth=1,
        )
        self.assertEqual(len(plan["frontier"]), 2)
        values = {
            (
                metric(plan, "expected_observation", i),
                metric(plan, "expected_intervention", i),
            )
            for i in range(2)
        }
        self.assertEqual(values, {(Fraction(3), Fraction(0)), (Fraction(1), Fraction(2))})

    def test_worst_case_cost_keeps_each_hypothesis_on_its_own_path(self):
        plan = build_intervention_attention_frontier(
            world_states=("a0", "b0", "a1", "b1"),
            hypotheses=(
                {"hypothesis_id": "a", "initial_state": "a0", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "b", "initial_state": "b0", "query_value": False, "prior": "1/2"},
            ),
            probes=(
                {
                    "probe_id": "prime",
                    "observation_cost": 0,
                    "transitions": {
                        "a0": transition("ready", "a1", 2),
                        "b0": transition("ready", "b1", 0),
                        "a1": transition("ready", "a1", 2),
                        "b1": transition("ready", "b1", 0),
                    },
                },
                {
                    "probe_id": "finish",
                    "observation_cost": 1,
                    "transitions": {
                        "a0": transition("same", "a0"),
                        "b0": transition("same", "b0"),
                        "a1": transition("yes", "a1"),
                        "b1": transition("no", "b1", 10),
                    },
                },
            ),
            max_depth=2,
        )
        self.assertEqual(metric(plan, "expected_intervention"), Fraction(6))
        self.assertEqual(metric(plan, "worst_case_intervention"), Fraction(10))
        costs = {
            item["hypothesis_id"]: Fraction(
                item["intervention_cost"]["numerator"],
                item["intervention_cost"]["denominator"],
            )
            for item in plan["frontier"][0]["path_costs"]
        }
        self.assertEqual(costs, {"a": Fraction(2), "b": Fraction(10)})

    def test_same_outcome_can_still_transform_hypotheses_differently(self):
        plan = build_intervention_attention_frontier(
            world_states=("x0", "y0", "x1", "y1"),
            hypotheses=(
                {"hypothesis_id": "x", "initial_state": "x0", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "y", "initial_state": "y0", "query_value": False, "prior": "1/2"},
            ),
            probes=(
                {
                    "probe_id": "silent-transform",
                    "observation_cost": 0,
                    "transitions": {
                        "x0": transition("ack", "x1"), "y0": transition("ack", "y1"),
                        "x1": transition("ack", "x1"), "y1": transition("ack", "y1"),
                    },
                },
                {
                    "probe_id": "later-sensor",
                    "observation_cost": 1,
                    "transitions": {
                        "x0": transition("same", "x0"), "y0": transition("same", "y0"),
                        "x1": transition("X", "x1"), "y1": transition("Y", "y1"),
                    },
                },
            ),
            max_depth=2,
        )
        self.assertEqual(plan["frontier"][0]["policy"]["probe_id"], "silent-transform")
        self.assertEqual(plan["status"], "complete_frontier")

    def test_unresolved_status_is_preserved_at_the_depth_bound(self):
        plan = build_intervention_attention_frontier(
            world_states=("a", "b"),
            hypotheses=(
                {"hypothesis_id": "a", "initial_state": "a", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "b", "initial_state": "b", "query_value": False, "prior": "1/2"},
            ),
            probes=(),
            max_depth=0,
        )
        self.assertEqual(plan["status"], "unresolved_within_depth")
        self.assertEqual(plan["frontier"], [])

    def test_validation_rebuilds_model_and_rejects_tampering(self):
        plan = build_intervention_attention_frontier(
            world_states=("on", "off"),
            hypotheses=(
                {"hypothesis_id": "on", "initial_state": "on", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "off", "initial_state": "off", "query_value": False, "prior": "1/2"},
            ),
            probes=(
                {
                    "probe_id": "inspect",
                    "observation_cost": 1,
                    "transitions": {
                        "on": transition("true", "on"),
                        "off": transition("false", "off"),
                    },
                },
            ),
            max_depth=1,
        )
        self.assertEqual(validate_intervention_attention_document(plan), plan)
        altered = dict(plan)
        altered["frontier"] = [dict(plan["frontier"][0])]
        altered["frontier"][0]["costs"] = dict(plan["frontier"][0]["costs"])
        altered["frontier"][0]["costs"]["expected_observation"] = {
            "numerator": 999,
            "denominator": 1,
        }
        with self.assertRaises(ValueError):
            validate_intervention_attention_document(altered)

    def test_exact_rationals_and_normalized_priors_are_required(self):
        base = {
            "world_states": ("a", "b"),
            "hypotheses": (
                {"hypothesis_id": "a", "initial_state": "a", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "b", "initial_state": "b", "query_value": False, "prior": "1/2"},
            ),
            "probes": (),
            "max_depth": 1,
        }
        with self.assertRaises(ValueError):
            build_intervention_attention_frontier(**{
                **base,
                "hypotheses": (
                    {**base["hypotheses"][0], "prior": 0.5},
                    base["hypotheses"][1],
                ),
            })
        with self.assertRaises(ValueError):
            build_intervention_attention_frontier(**{
                **base,
                "hypotheses": (
                    {**base["hypotheses"][0], "prior": "3/4"},
                    base["hypotheses"][1],
                ),
            })

    def test_frontier_limit_fails_explicitly(self):
        with self.assertRaises(FrontierLimitError):
            build_intervention_attention_frontier(
                world_states=("a", "b", "a2", "b2"),
                hypotheses=(
                    {"hypothesis_id": "yes", "initial_state": "a", "query_value": True, "prior": "1/2"},
                    {"hypothesis_id": "no", "initial_state": "b", "query_value": False, "prior": "1/2"},
                ),
                probes=(
                    {
                        "probe_id": "slow-safe",
                        "observation_cost": 3,
                        "transitions": {
                            "a": transition("yes", "a"), "b": transition("no", "b"),
                            "a2": transition("yes", "a2"), "b2": transition("no", "b2"),
                        },
                    },
                    {
                        "probe_id": "fast-risky",
                        "observation_cost": 1,
                        "transitions": {
                            "a": transition("yes", "a2", 2), "b": transition("no", "b2", 2),
                            "a2": transition("yes", "a2", 2), "b2": transition("no", "b2", 2),
                        },
                    },
                ),
                max_depth=1,
                max_frontier=1,
            )


    def test_nested_frontier_pruning_preserves_state_dependent_prefix_costs(self):
        plan = build_intervention_attention_frontier(
            world_states=("a0", "b0", "a1", "b1"),
            hypotheses=(
                {"hypothesis_id": "a", "initial_state": "a0", "query_value": True, "prior": "1/2"},
                {"hypothesis_id": "b", "initial_state": "b0", "query_value": False, "prior": "1/2"},
            ),
            probes=(
                {
                    "probe_id": "prepare",
                    "observation_cost": 0,
                    "transitions": {
                        "a0": transition("ready", "a1", 100),
                        "b0": transition("ready", "b1", 0),
                        "a1": transition("ready", "a1", 0),
                        "b1": transition("ready", "b1", 0),
                    },
                },
                {
                    "probe_id": "finish-a",
                    "observation_cost": 1,
                    "transitions": {
                        "a0": transition("hidden", "a0"),
                        "b0": transition("hidden", "b0"),
                        "a1": transition("yes", "a1", 10),
                        "b1": transition("no", "b1", 0),
                    },
                },
                {
                    "probe_id": "finish-b",
                    "observation_cost": 1,
                    "transitions": {
                        "a0": transition("hidden", "a0"),
                        "b0": transition("hidden", "b0"),
                        "a1": transition("yes", "a1", 0),
                        "b1": transition("no", "b1", 10),
                    },
                },
            ),
            max_depth=2,
        )
        self.assertEqual(plan["status"], "complete_frontier")
        self.assertEqual(len(plan["frontier"]), 1)
        policy = plan["frontier"][0]["policy"]
        self.assertEqual(policy["probe_id"], "prepare")
        self.assertEqual(policy["branches"][0]["child"]["probe_id"], "finish-b")
        self.assertEqual(metric(plan, "expected_intervention"), Fraction(55))
        self.assertEqual(metric(plan, "worst_case_intervention"), Fraction(100))



if __name__ == "__main__":
    unittest.main()
