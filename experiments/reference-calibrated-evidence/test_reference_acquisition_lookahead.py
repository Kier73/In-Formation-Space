from __future__ import annotations

import copy
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

import jsonschema

from reference_acquisition_lookahead import (
    ReferenceAcquisitionError,
    ReferenceAcquisitionMismatch,
    build_report,
    build_reference_execution_record,
    new_reference_acquisition_observation_path,
    validate_reference_execution_record,
    validate_report,
)

ROOT = Path(__file__).resolve().parent
REPORT_SCHEMA = json.loads((ROOT / "reference-acquisition-lookahead.schema.json").read_text(encoding="utf-8"))
EXECUTION_SCHEMA = json.loads((ROOT / "reference-acquisition-execution.schema.json").read_text(encoding="utf-8"))


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
                "sensor-1": channel("9/10", "1/10"),
                "sensor-2": channel("7/10", "3/10"),
                "sensor-3": channel("9/10", "1/10"),
            },
        },
        {
            "calibration_id": "profile-2",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-1": channel("3/5", "2/5"),
                "sensor-2": channel("4/5", "1/5"),
                "sensor-3": channel("1/10", "3/5"),
            },
        },
    )
    candidates = (
        {
            "candidate_id": "reference-sensor-1-standard-A",
            "sensor_id": "sensor-1",
            "known_hypothesis": "A",
            "reference_standard_ref": "fixture://standard-A/sensor-1",
            "reference_standard_sha256": sha("known A standard for sensor-1"),
            "cost": "1/2",
        },
        {
            "candidate_id": "reference-sensor-2-standard-A",
            "sensor_id": "sensor-2",
            "known_hypothesis": "A",
            "reference_standard_ref": "fixture://standard-A/sensor-2",
            "reference_standard_sha256": sha("known A standard for sensor-2"),
            "cost": "1/2",
        },
        {
            "candidate_id": "reference-sensor-3-standard-A",
            "sensor_id": "sensor-3",
            "known_hypothesis": "A",
            "reference_standard_ref": "fixture://standard-A/sensor-3",
            "reference_standard_sha256": sha("known A standard for sensor-3"),
            "cost": "1/2",
        },
        {
            "candidate_id": "reference-sensor-3-standard-B",
            "sensor_id": "sensor-3",
            "known_hypothesis": "B",
            "reference_standard_ref": "fixture://standard-B/sensor-3",
            "reference_standard_sha256": sha("known B standard for sensor-3"),
            "cost": "1/2",
        },
    )
    return {
        "prior_hypothesis_a": "1/2",
        "calibrations": calibrations,
        "target_sensor_schedule": ("sensor-1", "sensor-2", "sensor-3"),
        "reference_candidates": candidates,
    }


def make_authorized_path(report, *, signal="A", authorize=True, mutate_return=None):
    selected_id = report["selection"]["selected_candidate_id"]
    candidate = next(
        item for item in report["candidate_evaluations"]
        if item["candidate_id"] == selected_id
    )
    path = new_reference_acquisition_observation_path(
        reference_acquisition_report=report,
        attempt_id="reference-attempt-001",
    )
    path.append(
        "dispatched",
        "reference-sensor-agent",
        evidence_ref="dispatch://reference-attempt-001",
        details={"request_id": "reference-attempt-001"},
    )
    path.append(
        "admitted",
        "reference-receiver",
        evidence_ref="admission://reference-attempt-001",
        details={"receiver_id": "reference-receiver-01"},
    )
    returned = {
        "encounter_id": "reference-encounter-001",
        "payload_digest": sha(f"reference payload signal {signal}"),
        "canonicalization": "canonical-json-v1",
        "candidate_id": candidate["candidate_id"],
        "sensor_id": candidate["sensor_id"],
        "dimension": "calibration-reference",
        "known_hypothesis": candidate["known_hypothesis"],
        "reference_standard_ref": candidate["reference_standard_ref"],
        "reference_standard_sha256": candidate["reference_standard_sha256"],
        "reference_acquisition_report_digest": report["report_digest"],
        "observed_outcome": signal,
    }
    if mutate_return:
        returned.update(mutate_return)
    path.append(
        "returned",
        "reference-receiver",
        evidence_ref="encounter://reference-attempt-001",
        details=returned,
    )
    if authorize:
        path.append(
            "evidence_authorized",
            "reference-consensus",
            evidence_ref="consensus://reference-attempt-001",
            details={
                "decision_status": "AUTHORIZED",
                "policy_digest": sha("reference quorum policy"),
                "decision_digest": sha("reference authority decision"),
                "quorum": 2,
                "strict": True,
                "observed_sources": ["reference-sensor-a", "reference-sensor-b"],
                "dissenting_sources": [],
                "missing_sources": [],
                "representative_source": "reference-sensor-a",
            },
        )
        path.append(
            "interpreted",
            "reference-interpreter",
            evidence_ref="interpretation://reference-attempt-001",
            details={
                "method": "exact-calibration-reference-outcome-v1",
                "candidate_id": candidate["candidate_id"],
                "sensor_id": candidate["sensor_id"],
                "dimension": "calibration-reference",
                "known_hypothesis": candidate["known_hypothesis"],
                "reference_standard_ref": candidate["reference_standard_ref"],
                "reference_standard_sha256": candidate["reference_standard_sha256"],
                "reference_acquisition_report_digest": report["report_digest"],
                "observed_outcome": signal,
            },
        )
    return path


class ReferenceAcquisitionLookaheadTests(unittest.TestCase):
    def setUp(self):
        self.inputs = fixture()
        self.report = build_report(**self.inputs)

    def test_exact_downstream_value_selects_the_most_useful_reference(self):
        self.assertEqual(
            ratio(self.report["baseline_target_map_accuracy"]),
            Fraction(153, 200),
        )
        rows = {
            row["candidate_id"]: row
            for row in self.report["candidate_evaluations"]
        }
        best = rows["reference-sensor-3-standard-A"]
        self.assertEqual(
            ratio(best["expected_target_map_accuracy"]),
            Fraction(4269, 5000),
        )
        self.assertEqual(
            ratio(best["expected_downstream_decision_value"]),
            Fraction(111, 1250),
        )
        self.assertEqual(
            ratio(best["expected_downstream_decision_value_per_cost"]),
            Fraction(111, 625),
        )
        self.assertEqual(
            self.report["selection"]["selected_candidate_id"],
            "reference-sensor-3-standard-A",
        )

    def test_reference_outcome_branches_retain_exact_calibration_posteriors(self):
        selected = next(
            row for row in self.report["candidate_evaluations"]
            if row["candidate_id"] == self.report["selection"]["selected_candidate_id"]
        )
        branches = {row["signal"]: row for row in selected["branches"]}
        self.assertEqual(
            ratio(branches["A"]["predictive_probability"]),
            Fraction(1, 2),
        )
        self.assertEqual(
            ratio(branches["B"]["predictive_probability"]),
            Fraction(1, 2),
        )
        posterior_a = {
            row["calibration_id"]: ratio(row["probability"])
            for row in branches["A"]["posterior_calibration_probabilities"]
        }
        posterior_b = {
            row["calibration_id"]: ratio(row["probability"])
            for row in branches["B"]["posterior_calibration_probabilities"]
        }
        self.assertEqual(
            posterior_a,
            {"profile-1": Fraction(9, 10), "profile-2": Fraction(1, 10)},
        )
        self.assertEqual(
            posterior_b,
            {"profile-1": Fraction(1, 10), "profile-2": Fraction(9, 10)},
        )
        self.assertEqual(
            ratio(branches["A"]["target_map_accuracy"]),
            Fraction(4507, 5000),
        )
        self.assertEqual(
            ratio(branches["B"]["target_map_accuracy"]),
            Fraction(4031, 5000),
        )

    def test_riv008_myopic_evsi_is_zero_while_downstream_lookahead_is_positive(self):
        for row in self.report["candidate_evaluations"]:
            self.assertEqual(
                ratio(row["myopic_riv008_comparator"]["expected_bayes_risk_reduction"]),
                Fraction(0),
            )
            self.assertEqual(
                ratio(row["myopic_riv008_comparator"]["expected_value_per_cost"]),
                Fraction(0),
            )
        self.assertGreater(
            ratio(next(
                row for row in self.report["candidate_evaluations"]
                if row["candidate_id"] == "reference-sensor-3-standard-A"
            )["expected_downstream_decision_value"]),
            0,
        )

    def test_reference_candidates_keep_cost_and_value_pareto_dimensions_separate(self):
        frontier = self.report["pareto_frontier_candidate_ids"]
        self.assertIn("reference-sensor-3-standard-A", frontier)
        self.assertTrue(set(frontier).issubset({
            row["candidate_id"] for row in self.report["candidate_evaluations"]
        }))

    def test_budget_filters_selection_without_changing_candidate_scores(self):
        inputs = dict(self.inputs)
        inputs["cost_budget"] = "1/4"
        report = build_report(**inputs)
        self.assertEqual(
            report["selection"]["status"],
            "no_candidate_within_cost_budget",
        )
        self.assertIsNone(report["selection"]["selected_candidate_id"])
        self.assertEqual(
            report["candidate_evaluations"],
            self.report["candidate_evaluations"],
        )

    def test_no_positive_value_candidate_is_not_selected(self):
        inputs = dict(self.inputs)
        calibrations = []
        for item in inputs["calibrations"]:
            models = {
                sensor: channel("3/4", "1/4")
                for sensor in item["sensor_models"]
            }
            calibrations.append({
                **item,
                "sensor_models": models,
            })
        inputs["calibrations"] = tuple(calibrations)
        report = build_report(**inputs)
        self.assertEqual(
            report["selection"]["status"],
            "no_positive_value_candidate_within_cost_budget",
        )
        self.assertIsNone(report["selection"]["selected_candidate_id"])

    def test_report_reconstruction_and_schema(self):
        self.assertEqual(validate_report(self.report), self.report)
        jsonschema.Draft202012Validator.check_schema(REPORT_SCHEMA)
        jsonschema.validate(self.report, REPORT_SCHEMA)

    def test_tampered_branch_is_rejected_even_with_recomputed_outer_digest(self):
        changed = copy.deepcopy(self.report)
        changed["candidate_evaluations"][0]["expected_downstream_decision_value"] = {
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
        with self.assertRaises(ReferenceAcquisitionError):
            validate_report(changed)

    def test_input_validation_rejects_bad_digest_float_cost_duplicate_and_unknown_sensor(self):
        for field, value in (
            ("reference_standard_sha256", "not-a-digest"),
            ("cost", 0.5),
            ("cost", 0),
            ("sensor_id", "sensor-not-in-target-schedule"),
        ):
            inputs = dict(self.inputs)
            candidates = list(inputs["reference_candidates"])
            candidates[0] = {**candidates[0], field: value}
            inputs["reference_candidates"] = tuple(candidates)
            with self.subTest(field=field, value=value), self.assertRaises(ReferenceAcquisitionError):
                build_report(**inputs)
        inputs = dict(self.inputs)
        candidates = list(inputs["reference_candidates"])
        candidates[1] = {**candidates[1], "candidate_id": candidates[0]["candidate_id"]}
        inputs["reference_candidates"] = tuple(candidates)
        with self.assertRaises(ReferenceAcquisitionError):
            build_report(**inputs)

    def test_planner_creates_planned_only_authority_gated_observation_path(self):
        path = new_reference_acquisition_observation_path(
            reference_acquisition_report=self.report,
            attempt_id="planned-reference",
        )
        candidate_id = self.report["selection"]["selected_candidate_id"]
        self.assertEqual(path.status, "planned")
        self.assertFalse(path.terminal)
        self.assertTrue(path.intent.authority_required)
        self.assertFalse(path.intent.application_required)
        self.assertFalse(path.intent.sender_ack_required)
        self.assertEqual(
            path.intent.candidate_name,
            f"reference-calibration:{candidate_id}",
        )
        self.assertEqual(
            path.intent.hypothesis_set_digest,
            self.report["report_digest"],
        )

    def test_authorized_interpreted_reference_becomes_riv009_update(self):
        path = make_authorized_path(self.report, signal="A")
        record = build_reference_execution_record(
            reference_acquisition_report=self.report,
            observation_path=path,
        )
        self.assertEqual(
            record["measurement_status"],
            "interpreted_authorized_reference_observation",
        )
        self.assertEqual(record["belief_effect"], "new_reference_conditioned_calibration_report")
        self.assertEqual(record["ground_effect"], "none")
        self.assertEqual(record["sensor_model_effect"], "none")
        self.assertEqual(record["reference_observation"]["known_hypothesis"], "A")
        self.assertEqual(record["reference_observation"]["signal"], "A")
        self.assertEqual(record["measurement_manifest"]["authority_decision_status"], "AUTHORIZED")
        posterior = {
            row["calibration_id"]: ratio(row["probability"])
            for row in record["updated_riv009_report"]["reference_phase"]["posterior_calibration_probabilities"]
        }
        self.assertEqual(
            posterior,
            {"profile-1": Fraction(9, 10), "profile-2": Fraction(1, 10)},
        )
        self.assertEqual(
            record["updated_riv009_report"]["reference_phase"]["observation_count"],
            1,
        )
        self.assertEqual(validate_reference_execution_record(record), record)
        jsonschema.Draft202012Validator.check_schema(EXECUTION_SCHEMA)
        jsonschema.validate(record, EXECUTION_SCHEMA)

    def test_authorized_outcome_b_creates_the_other_exact_calibration_posterior(self):
        path = make_authorized_path(self.report, signal="B")
        record = build_reference_execution_record(
            reference_acquisition_report=self.report,
            observation_path=path,
        )
        posterior = {
            row["calibration_id"]: ratio(row["probability"])
            for row in record["updated_riv009_report"]["reference_phase"]["posterior_calibration_probabilities"]
        }
        self.assertEqual(
            posterior,
            {"profile-1": Fraction(1, 10), "profile-2": Fraction(9, 10)},
        )

    def test_path_without_authority_cannot_create_reference_update(self):
        path = make_authorized_path(self.report, authorize=False)
        with self.assertRaises((ReferenceAcquisitionError, ValueError)):
            build_reference_execution_record(
                reference_acquisition_report=self.report,
                observation_path=path,
            )

    def test_standard_sensor_candidate_or_report_mismatch_is_rejected(self):
        bad_path = make_authorized_path(
            self.report,
            mutate_return={"known_hypothesis": "B"},
        )
        with self.assertRaises(ReferenceAcquisitionMismatch):
            build_reference_execution_record(
                reference_acquisition_report=self.report,
                observation_path=bad_path,
            )
        bad_path = make_authorized_path(
            self.report,
            mutate_return={"reference_acquisition_report_digest": sha("other report")},
        )
        with self.assertRaises(ReferenceAcquisitionMismatch):
            build_reference_execution_record(
                reference_acquisition_report=self.report,
                observation_path=bad_path,
            )

    def test_reference_record_rejects_tampered_path_even_with_recomputed_outer_digest(self):
        record = build_reference_execution_record(
            reference_acquisition_report=self.report,
            observation_path=make_authorized_path(self.report),
        )
        changed = copy.deepcopy(record)
        changed["observation_path"]["events"][3]["details"]["payload_digest"] = sha("tampered payload")
        core = {key: value for key, value in changed.items() if key != "record_digest"}
        changed["record_digest"] = sha(json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ))
        with self.assertRaises(ReferenceAcquisitionError):
            validate_reference_execution_record(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
