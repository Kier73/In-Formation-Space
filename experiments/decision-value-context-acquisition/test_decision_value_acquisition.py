import copy
import hashlib
import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

import jsonschema

from decision_value_acquisition import (
    DecisionValueError,
    build_joint_belief_document,
    build_report,
    validate_report,
)

_RIV006 = Path(__file__).resolve().parents[1] / "context-switching-evidence-accumulator"
if str(_RIV006) not in sys.path:
    sys.path.insert(0, str(_RIV006))
from context_switching_evidence import build_report as build_context_filter_report

_RIV007 = Path(__file__).resolve().parents[1] / "calibration-aware-joint-evidence"
if str(_RIV007) not in sys.path:
    sys.path.insert(0, str(_RIV007))
from calibration_aware_evidence import build_report as build_calibration_filter_report

_RIV009 = Path(__file__).resolve().parents[1] / "reference-calibrated-evidence"
if str(_RIV009) not in sys.path:
    sys.path.insert(0, str(_RIV009))
from reference_calibrated_evidence import build_report as build_reference_calibrated_report
from test_reference_calibrated_evidence import fixture as reference_calibration_fixture


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ratio(document):
    return Fraction(document["numerator"], document["denominator"])


def context_sensor(sensor_id, good_given_good, good_given_degraded, cost):
    outcomes = []
    for outcome, probability_good, probability_degraded in (
        ("good", good_given_good, good_given_degraded),
        ("degraded", 1 - Fraction(good_given_good), 1 - Fraction(good_given_degraded)),
    ):
        outcomes.append({
            "outcome": outcome,
            "likelihoods": [
                {
                    "hypothesis": "A",
                    "context_state": "good",
                    "probability": probability_good,
                },
                {
                    "hypothesis": "A",
                    "context_state": "degraded",
                    "probability": probability_degraded,
                },
                {
                    "hypothesis": "B",
                    "context_state": "good",
                    "probability": probability_good,
                },
                {
                    "hypothesis": "B",
                    "context_state": "degraded",
                    "probability": probability_degraded,
                },
            ],
        })
    return {
        "sensor_id": sensor_id,
        "dimension": "operating-regime",
        "cost": cost,
        "outcomes": outcomes,
    }


def filter_fixture():
    def sensor(name):
        return {
            "sensor_id": name,
            "p_signal_a_given_hypothesis_a_good": "9/10",
            "p_signal_a_given_hypothesis_b_good": "1/10",
            "p_signal_a_given_hypothesis_a_degraded": "1/2",
            "p_signal_a_given_hypothesis_b_degraded": "1/2",
        }
    return {
        "prior_hypothesis_a": "1/2",
        "prior_context_good": "1/2",
        "context_transition": {
            "p_good_next_given_good": "9/10",
            "p_good_next_given_degraded": "1/10",
        },
        "sensors": tuple(sensor(f"sensor-{i}") for i in range(1, 5)),
    }


def fixture():
    source_report = build_context_filter_report(**filter_fixture())
    layer = source_report["joint_posterior_accumulator"]["layers"][2]
    # Either AB or BA has the same two scalar marginals but a distinct joint
    # belief. The first deterministic belief record is enough for this EVSI test.
    state = next(
        item for item in layer["joint_posterior_states"]
        if item["posterior_hypothesis_a"] == {"numerator": 1, "denominator": 2}
        and item["posterior_regime_good"] == {"numerator": 301, "denominator": 890}
    )
    # RIV-006 calls this coordinate "regime"; RIV-008's model-agnostic
    # joint-belief contract normalizes it to "context_state" explicitly.
    normalized_joint_posterior = [
        {
            "hypothesis": row["hypothesis"],
            "context_state": row["regime"],
            "probability": row["probability"],
        }
        for row in state["joint_posterior"]
    ]
    belief = build_joint_belief_document(
        joint_posterior=normalized_joint_posterior,
        source_ref="artifact://RIV-006/context-filter",
        source_report_digest=source_report["content_digest"],
    )
    candidates = (
        context_sensor(
            "high-fidelity-context",
            Fraction(9, 10),
            Fraction(1, 10),
            Fraction(1),
        ),
        context_sensor(
            "budget-proxy",
            Fraction(2, 3),
            Fraction(1, 3),
            Fraction(1, 2),
        ),
        context_sensor(
            "perfect-context-audit",
            Fraction(1),
            Fraction(0),
            Fraction(2),
        ),
        context_sensor(
            "blind-context",
            Fraction(1, 2),
            Fraction(1, 2),
            Fraction(1, 4),
        ),
    )
    return belief, candidates, source_report


class DecisionValueContextAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.belief, self.candidates, self.source_report = fixture()

    def test_belief_document_reconstructs_the_riv006_joint_state(self):
        self.assertEqual(
            ratio(self.belief["posterior_hypothesis_a"]),
            Fraction(1, 2),
        )
        self.assertEqual(
            self.belief["source_report_digest"],
            self.source_report["content_digest"],
        )
        self.assertEqual(
            sum(
                ratio(item["probability"])
                for item in self.belief["joint_posterior"]
            ),
            Fraction(1),
        )

    def test_expected_bayes_risk_and_cost_ranking_are_exact(self):
        report = build_report(
            joint_belief=self.belief,
            candidate_sensors=self.candidates,
        )
        baseline = report["baseline_decision"]
        self.assertEqual(baseline["optimal_decision"], "A")
        self.assertEqual(
            ratio(baseline["bayes_decision_loss"]),
            Fraction(1, 2),
        )
        rows = {
            item["sensor_id"]: item
            for item in report["candidate_evaluations"]
        }
        high = rows["high-fidelity-context"]
        weak = rows["budget-proxy"]
        perfect = rows["perfect-context-audit"]
        blind = rows["blind-context"]

        self.assertEqual(
            ratio(high["expected_posterior_bayes_decision_loss"]),
            Fraction(413, 890),
        )
        self.assertEqual(
            ratio(high["expected_bayes_risk_reduction"]),
            Fraction(16, 445),
        )
        self.assertEqual(
            ratio(high["expected_value_per_cost"]),
            Fraction(16, 445),
        )
        self.assertEqual(
            ratio(weak["expected_posterior_bayes_decision_loss"]),
            Fraction(259, 534),
        )
        self.assertEqual(
            ratio(weak["expected_bayes_risk_reduction"]),
            Fraction(4, 267),
        )
        self.assertEqual(
            ratio(weak["expected_value_per_cost"]),
            Fraction(8, 267),
        )
        self.assertEqual(
            ratio(perfect["expected_bayes_risk_reduction"]),
            Fraction(4, 89),
        )
        self.assertEqual(
            ratio(perfect["expected_value_per_cost"]),
            Fraction(2, 89),
        )
        self.assertEqual(
            ratio(blind["expected_bayes_risk_reduction"]),
            Fraction(0),
        )
        self.assertEqual(
            report["selection"]["selected_sensor_id"],
            "high-fidelity-context",
        )
        self.assertEqual(
            report["measurement_status"],
            "proposal_only_not_dispatched",
        )

    def test_pareto_frontier_retains_cost_value_tradeoffs(self):
        report = build_report(
            joint_belief=self.belief,
            candidate_sensors=self.candidates,
        )
        self.assertEqual(
            report["pareto_frontier_sensor_ids"],
            [
                "blind-context",
                "budget-proxy",
                "high-fidelity-context",
                "perfect-context-audit",
            ],
        )

    def test_cost_budget_changes_eligible_choice_without_rewriting_scores(self):
        report = build_report(
            joint_belief=self.belief,
            candidate_sensors=self.candidates,
            cost_budget="3/4",
        )
        self.assertEqual(
            report["selection"]["eligible_sensor_ids"],
            ["blind-context", "budget-proxy"],
        )
        self.assertEqual(report["selection"]["selected_sensor_id"], "budget-proxy")
        self.assertEqual(
            ratio(next(
                item["expected_bayes_risk_reduction"]
                for item in report["candidate_evaluations"]
                if item["sensor_id"] == "high-fidelity-context"
            )),
            Fraction(16, 445),
        )

    def test_zero_budget_returns_no_measurement(self):
        report = build_report(
            joint_belief=self.belief,
            candidate_sensors=self.candidates,
            cost_budget=0,
        )
        self.assertEqual(report["selection"]["eligible_sensor_ids"], [])
        self.assertIsNone(report["selection"]["selected_sensor_id"])
        self.assertEqual(report["selection"]["status"], "no_candidate_within_cost_budget")

    def test_custom_decision_loss_changes_the_baseline_action(self):
        loss = {
            "decide_a_if_hypothesis_a": 0,
            "decide_a_if_hypothesis_b": 3,
            "decide_b_if_hypothesis_a": 1,
            "decide_b_if_hypothesis_b": 0,
        }
        report = build_report(
            joint_belief=self.belief,
            candidate_sensors=self.candidates,
            loss_matrix=loss,
        )
        self.assertEqual(report["baseline_decision"]["optimal_decision"], "B")
        self.assertEqual(
            ratio(report["baseline_decision"]["bayes_decision_loss"]),
            Fraction(1, 2),
        )
        self.assertTrue(all(
            ratio(item["expected_bayes_risk_reduction"]) >= 0
            for item in report["candidate_evaluations"]
        ))

    def test_candidate_likelihoods_must_normalize_for_every_joint_state(self):
        broken = copy.deepcopy(self.candidates[0])
        broken["outcomes"][0]["likelihoods"][0]["probability"] = "9/10"
        broken["outcomes"][1]["likelihoods"][0]["probability"] = "1/2"
        with self.assertRaises(DecisionValueError):
            build_report(
                joint_belief=self.belief,
                candidate_sensors=(broken,),
            )

    def test_duplicate_candidate_ids_outcomes_and_joint_states_are_rejected(self):
        duplicate_id = (
            self.candidates[0],
            dict(self.candidates[0]),
        )
        with self.assertRaises(DecisionValueError):
            build_report(
                joint_belief=self.belief,
                candidate_sensors=duplicate_id,
            )

        duplicate_outcome = copy.deepcopy(self.candidates[0])
        duplicate_outcome["outcomes"][1]["outcome"] = "good"
        with self.assertRaises(DecisionValueError):
            build_report(
                joint_belief=self.belief,
                candidate_sensors=(duplicate_outcome,),
            )

        duplicate_state = list(self.belief["joint_posterior"])
        duplicate_state.append(dict(duplicate_state[0]))
        with self.assertRaises(DecisionValueError):
            build_joint_belief_document(
                joint_posterior=duplicate_state,
                source_ref="artifact://invalid",
                source_report_digest=self.source_report["content_digest"],
            )

    def test_floats_and_zero_or_negative_costs_are_rejected(self):
        for cost in (0, -1, 0.5, True):
            broken = copy.deepcopy(self.candidates[0])
            broken["cost"] = cost
            with self.subTest(cost=cost), self.assertRaises(DecisionValueError):
                build_report(
                    joint_belief=self.belief,
                    candidate_sensors=(broken,),
                )

    def test_session_shared_calibration_filter_can_supply_the_same_generic_belief_contract(self):
        calibration_report = build_calibration_filter_report(
            prior_hypothesis_a="1/2",
            sensor_schedule=("sensor-1", "sensor-2", "sensor-3"),
            calibrations=(
                {
                    "calibration_id": "profile-1",
                    "prior_probability": "1/2",
                    "sensor_models": {
                        "sensor-1": {"p_signal_a_given_hypothesis_a": "9/10", "p_signal_a_given_hypothesis_b": "1/10"},
                        "sensor-2": {"p_signal_a_given_hypothesis_a": "7/10", "p_signal_a_given_hypothesis_b": "3/10"},
                        "sensor-3": {"p_signal_a_given_hypothesis_a": "9/10", "p_signal_a_given_hypothesis_b": "1/10"},
                    },
                },
                {
                    "calibration_id": "profile-2",
                    "prior_probability": "1/2",
                    "sensor_models": {
                        "sensor-1": {"p_signal_a_given_hypothesis_a": "3/5", "p_signal_a_given_hypothesis_b": "2/5"},
                        "sensor-2": {"p_signal_a_given_hypothesis_a": "4/5", "p_signal_a_given_hypothesis_b": "1/5"},
                        "sensor-3": {"p_signal_a_given_hypothesis_a": "1/10", "p_signal_a_given_hypothesis_b": "3/5"},
                    },
                },
            ),
        )
        raw = next(
            row for row in calibration_report["shared_calibration_full_history"]["raw_history_rows"]
            if row["posterior_joint_latent_state"] is not None
        )
        joint_posterior = [
            {
                "hypothesis": coordinate["hypothesis"],
                "context_state": coordinate["calibration_id"],
                "probability": probability,
            }
            for coordinate, probability in zip(
                calibration_report["latent_state_order"],
                raw["posterior_joint_latent_state"],
            )
        ]
        belief = build_joint_belief_document(
            joint_posterior=joint_posterior,
            source_ref="artifact://RIV-007/shared-calibration-filter",
            source_report_digest=calibration_report["content_digest"],
        )
        outcomes = []
        for outcome, p_profile_1, p_profile_2 in (
            ("profile-1", Fraction(9, 10), Fraction(1, 10)),
            ("profile-2", Fraction(1, 10), Fraction(9, 10)),
        ):
            outcomes.append({
                "outcome": outcome,
                "likelihoods": [
                    {
                        "hypothesis": hypothesis,
                        "context_state": profile,
                        "probability": p_profile_1 if profile == "profile-1" else p_profile_2,
                    }
                    for hypothesis in ("A", "B")
                    for profile in ("profile-1", "profile-2")
                ],
            })
        report = build_report(
            joint_belief=belief,
            candidate_sensors=({
                "sensor_id": "calibration-profile-reader",
                "dimension": "session-calibration",
                "cost": Fraction(1),
                "outcomes": outcomes,
            },),
        )
        self.assertEqual(
            report["source_report_digest"],
            calibration_report["content_digest"],
        )
        self.assertEqual(len(report["joint_belief"]["joint_posterior"]), 4)
        self.assertGreaterEqual(
            ratio(report["candidate_evaluations"][0]["expected_bayes_risk_reduction"]),
            Fraction(0),
        )

    def test_reference_calibrated_riv009_target_belief_uses_the_generic_joint_contract(self):
        upstream = build_reference_calibrated_report(
            **reference_calibration_fixture()
        )
        target = upstream["target_phase"]["reference_conditioned_filter_report"]
        raw = next(
            row for row in target["shared_calibration_full_history"]["raw_history_rows"]
            if row["posterior_joint_latent_state"] is not None
        )
        joint_posterior = [
            {
                "hypothesis": coordinate["hypothesis"],
                "context_state": coordinate["calibration_id"],
                "probability": probability,
            }
            for coordinate, probability in zip(
                target["latent_state_order"],
                raw["posterior_joint_latent_state"],
            )
        ]
        belief = build_joint_belief_document(
            joint_posterior=joint_posterior,
            source_ref="artifact://RIV-009/reference-conditioned-target",
            source_report_digest=upstream["content_digest"],
        )
        likelihood_rows = [
            {
                "hypothesis": item["hypothesis"],
                "context_state": item["context_state"],
                "probability": Fraction(9, 10)
                if item["context_state"] == "profile-1"
                else Fraction(1, 10),
            }
            for item in belief["joint_posterior"]
        ]
        complementary_rows = [
            {
                "hypothesis": item["hypothesis"],
                "context_state": item["context_state"],
                "probability": Fraction(1, 10)
                if item["context_state"] == "profile-1"
                else Fraction(9, 10),
            }
            for item in likelihood_rows
        ]
        # Outcomes distinguish the two profile labels, not H; both per-state
        # likelihood vectors normalize exactly.
        reader = {
            "sensor_id": "reference-calibration-profile-reader",
            "dimension": "session-calibration-profile",
            "cost": Fraction(1, 2),
            "outcomes": (
                {"outcome": "profile-1", "likelihoods": likelihood_rows},
                {"outcome": "profile-2", "likelihoods": complementary_rows},
            ),
        }
        report = build_report(
            joint_belief=belief,
            candidate_sensors=(reader,),
        )
        self.assertEqual(report["source_report_digest"], upstream["content_digest"])
        self.assertEqual(report["joint_belief"]["source_report_digest"], upstream["content_digest"])
        self.assertEqual(
            sum(
                (ratio(item["probability"]) for item in belief["joint_posterior"]),
                Fraction(0),
            ),
            Fraction(1),
        )
        self.assertEqual(len(report["candidate_evaluations"]), 1)

    def test_belief_state_id_and_source_digest_are_checked(self):
        state = list(self.belief["joint_posterior"])
        with self.assertRaises(DecisionValueError):
            build_joint_belief_document(
                joint_posterior=state,
                source_ref="artifact://bad-state",
                source_report_digest=self.source_report["content_digest"],
                source_state_id="0" * 64,
            )
        with self.assertRaises(DecisionValueError):
            build_joint_belief_document(
                joint_posterior=state,
                source_ref="artifact://bad-source",
                source_report_digest="not-a-digest",
            )

    def test_published_schema_accepts_the_complete_report(self):
        report = build_report(
            joint_belief=self.belief,
            candidate_sensors=self.candidates,
        )
        schema_path = Path(__file__).with_name(
            "decision-value-acquisition.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(report, schema)

    def test_report_reconstruction_rejects_tampering(self):
        report = build_report(
            joint_belief=self.belief,
            candidate_sensors=self.candidates,
        )
        self.assertEqual(validate_report(report), report)
        changed = copy.deepcopy(report)
        changed["candidate_evaluations"][0][
            "expected_bayes_risk_reduction"
        ] = {"numerator": 1, "denominator": 1}
        core = {
            key: value for key, value in changed.items()
            if key != "report_digest"
        }
        changed["report_digest"] = sha(json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ))
        with self.assertRaises(DecisionValueError):
            validate_report(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
