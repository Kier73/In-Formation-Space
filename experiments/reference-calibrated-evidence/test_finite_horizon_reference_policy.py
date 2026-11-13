from __future__ import annotations

import copy
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

import jsonschema

from finite_horizon_reference_policy import (
    FiniteHorizonReferenceError,
    PolicyStateLimitError,
    _RIV007,
    build_report,
    validate_report,
)

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "finite-horizon-reference-policy.schema.json").read_text(encoding="utf-8"))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


def channel(alpha, beta):
    return {
        "p_signal_a_given_hypothesis_a": alpha,
        "p_signal_a_given_hypothesis_b": beta,
    }


def fixture():
    calibrations = (
        {
            "calibration_id": "profile-1",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-0": channel("1/2", "1/2"),
                "sensor-1": channel("1/10", "4/5"),
                "sensor-2": channel("7/10", "7/10"),
            },
        },
        {
            "calibration_id": "profile-2",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-0": channel("1/10", "9/10"),
                "sensor-1": channel("2/5", "4/5"),
                "sensor-2": channel("3/5", "1/5"),
            },
        },
    )
    specifications = (
        ("sensor-0-standard-A", "sensor-0", "A", "1/2"),
        ("sensor-0-standard-B", "sensor-0", "B", "1"),
        ("sensor-1-standard-A", "sensor-1", "A", "1/2"),
        ("sensor-1-standard-B", "sensor-1", "B", "1/4"),
        ("sensor-2-standard-A", "sensor-2", "A", "5/4"),
        ("sensor-2-standard-B", "sensor-2", "B", "5/4"),
    )
    candidates = tuple({
        "candidate_id": candidate_id,
        "sensor_id": sensor_id,
        "known_hypothesis": standard,
        "reference_standard_ref": f"fixture://standards/{candidate_id}",
        "reference_standard_sha256": sha(f"known standard: {candidate_id}"),
        "cost": cost,
    } for candidate_id, sensor_id, standard, cost in specifications)
    return {
        "prior_hypothesis_a": "1/2",
        "calibrations": calibrations,
        "target_sensor_schedule": ("sensor-0", "sensor-1", "sensor-2"),
        "reference_candidates": candidates,
        "max_reference_steps": 3,
        "cost_budget": "3/2",
    }


def update_belief(belief, calibrations, candidate, signal):
    weights = {}
    for calibration in calibrations:
        model = calibration["sensor_models"][candidate["sensor_id"]]
        key = (
            "p_signal_a_given_hypothesis_a"
            if candidate["known_hypothesis"] == "A"
            else "p_signal_a_given_hypothesis_b"
        )
        probability_a = Fraction(model[key])
        likelihood = probability_a if signal == "A" else 1 - probability_a
        weights[calibration["calibration_id"]] = (
            belief[calibration["calibration_id"]] * likelihood
        )
    probability = sum(weights.values(), Fraction(0))
    if probability == 0:
        return probability, None
    return probability, {key: value / probability for key, value in weights.items()}


def target_accuracy(inputs, belief):
    calibrations = []
    for item in inputs["calibrations"]:
        calibrations.append({
            **item,
            "prior_probability": belief[item["calibration_id"]],
        })
    report = _RIV007.build_report(
        prior_hypothesis_a=inputs["prior_hypothesis_a"],
        calibrations=calibrations,
        sensor_schedule=inputs["target_sensor_schedule"],
    )
    return ratio(report["summary"]["shared_calibration_map_accuracy"])


def brute_force_value(inputs, belief, steps, budget):
    """Independent no-memo recursion for the finite action tree."""
    best = target_accuracy(inputs, belief)
    if steps <= 0:
        return best
    for candidate in inputs["reference_candidates"]:
        cost = Fraction(candidate["cost"])
        if cost > budget:
            continue
        expected = Fraction(0)
        for signal in ("A", "B"):
            probability, posterior = update_belief(
                belief, inputs["calibrations"], candidate, signal
            )
            if probability and posterior is not None:
                expected += probability * brute_force_value(
                    inputs, posterior, steps - 1, budget - cost
                )
        best = max(best, expected)
    return best


def max_path_cost(node):
    if node["action"] is None:
        return Fraction(0)
    own = ratio(node["cost"])
    children = [
        branch["child"]
        for branch in node["branches"]
        if branch["reachable"]
    ]
    return own + max((max_path_cost(child) for child in children), default=Fraction(0))


class FiniteHorizonReferencePolicyTests(unittest.TestCase):
    def setUp(self):
        self.inputs = fixture()
        self.report = build_report(**self.inputs)

    def test_exact_policy_improves_on_receding_greedy_under_same_budget(self):
        report = self.report
        self.assertEqual(
            ratio(report["baseline_target_map_accuracy"]),
            Fraction(623, 800),
        )
        finite = report["finite_horizon_policy"]
        greedy = report["greedy_reselection_policy"]
        self.assertEqual(
            ratio(finite["expected_target_map_accuracy"]),
            Fraction(5347, 6400),
        )
        self.assertEqual(
            ratio(greedy["expected_target_map_accuracy"]),
            Fraction(13351, 16000),
        )
        self.assertEqual(
            ratio(report["comparison"]["finite_horizon_accuracy_gain_over_greedy"]),
            Fraction(33, 32000),
        )
        self.assertEqual(ratio(finite["expected_reference_cost"]), Fraction(549, 400))
        self.assertEqual(ratio(greedy["expected_reference_cost"]), Fraction(6, 5))
        self.assertLessEqual(
            ratio(finite["expected_reference_cost"]),
            Fraction(3, 2),
        )
        self.assertLessEqual(
            ratio(greedy["expected_reference_cost"]),
            Fraction(3, 2),
        )

    def test_optimal_next_reference_depends_on_the_first_signal(self):
        root = self.report["finite_horizon_policy"]["root"]
        self.assertEqual(root["candidate_id"], "sensor-0-standard-A")
        branches = {item["signal"]: item for item in root["branches"]}
        self.assertEqual(
            branches["A"]["child"]["candidate_id"],
            "sensor-1-standard-A",
        )
        self.assertEqual(
            branches["B"]["child"]["candidate_id"],
            "sensor-0-standard-A",
        )
        self.assertNotEqual(
            branches["A"]["child"]["candidate_id"],
            branches["B"]["child"]["candidate_id"],
        )

    def test_policy_respects_the_budget_on_every_realized_path(self):
        root = self.report["finite_horizon_policy"]["root"]
        self.assertLessEqual(max_path_cost(root), Fraction(3, 2))
        greedy_root = self.report["greedy_reselection_policy"]["root"]
        self.assertLessEqual(max_path_cost(greedy_root), Fraction(3, 2))

    def test_dynamic_program_matches_independent_brute_force_tree_enumeration(self):
        initial = {
            item["calibration_id"]: Fraction(**item["prior_probability"])
            for item in self.report["model"]["calibrations_with_current_prior"]
        }
        brute = brute_force_value(
            self.inputs, initial, self.inputs["max_reference_steps"], Fraction(3, 2)
        )
        self.assertEqual(
            brute,
            ratio(self.report["finite_horizon_policy"]["expected_target_map_accuracy"]),
        )

    def test_zero_horizon_stops_without_reference_cost(self):
        inputs = dict(self.inputs)
        inputs["max_reference_steps"] = 0
        report = build_report(**inputs)
        node = report["finite_horizon_policy"]["root"]
        self.assertIsNone(node["candidate_id"])
        self.assertEqual(ratio(node["expected_target_map_accuracy"]), Fraction(623, 800))
        self.assertEqual(ratio(node["expected_reference_cost"]), Fraction(0))

    def test_zero_budget_stops_without_selecting_a_candidate(self):
        inputs = dict(self.inputs)
        inputs["cost_budget"] = 0
        report = build_report(**inputs)
        self.assertIsNone(report["finite_horizon_policy"]["root"]["candidate_id"])
        self.assertIsNone(report["greedy_reselection_policy"]["root"]["candidate_id"])

    def test_state_cap_fails_closed(self):
        inputs = dict(self.inputs)
        inputs["max_policy_states"] = 1
        with self.assertRaises(PolicyStateLimitError):
            build_report(**inputs)

    def test_bad_candidate_cost_digest_and_duplicate_ids_are_rejected(self):
        for field, value in (
            ("cost", 0.5),
            ("cost", 0),
            ("reference_standard_sha256", "bad-digest"),
            ("sensor_id", "missing-sensor"),
        ):
            inputs = dict(self.inputs)
            candidates = list(inputs["reference_candidates"])
            candidates[0] = {**candidates[0], field: value}
            inputs["reference_candidates"] = tuple(candidates)
            with self.subTest(field=field, value=value), self.assertRaises(FiniteHorizonReferenceError):
                build_report(**inputs)
        inputs = dict(self.inputs)
        candidates = list(inputs["reference_candidates"])
        candidates[1] = {
            **candidates[1],
            "candidate_id": candidates[0]["candidate_id"],
        }
        inputs["reference_candidates"] = tuple(candidates)
        with self.assertRaises(FiniteHorizonReferenceError):
            build_report(**inputs)

    def test_report_reconstruction_and_schema(self):
        self.assertEqual(validate_report(self.report), self.report)
        jsonschema.Draft202012Validator.check_schema(SCHEMA)
        jsonschema.validate(self.report, SCHEMA)

    def test_tampered_policy_tree_is_rejected_even_with_recomputed_outer_digest(self):
        changed = copy.deepcopy(self.report)
        changed["finite_horizon_policy"]["root"]["expected_target_map_accuracy"] = {
            "numerator": 1,
            "denominator": 1,
        }
        core = {key: value for key, value in changed.items() if key != "report_digest"}
        changed["report_digest"] = sha(json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ))
        with self.assertRaises(FiniteHorizonReferenceError):
            validate_report(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
