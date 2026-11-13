from __future__ import annotations

import copy
import hashlib
import json
import unittest
from fractions import Fraction
from pathlib import Path

try:
    import jsonschema
except ImportError:  # CI installs jsonschema; unit semantics remain stdlib-only.
    jsonschema = None

from reference_calibrated_evidence import (
    ImpossibleReferenceEvidenceError,
    ReferenceCalibrationError,
    build_report,
    validate_report,
)

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "reference-calibrated-evidence.schema.json"


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
                "sensor-2": channel("9/10", "1/10"),
                "sensor-3": channel("8/10", "2/10"),
            },
        },
        {
            "calibration_id": "profile-2",
            "prior_probability": "1/2",
            "sensor_models": {
                "sensor-1": channel("3/5", "2/5"),
                "sensor-2": channel("2/5", "3/5"),
                "sensor-3": channel("1/5", "4/5"),
            },
        },
    )
    references = (
        {
            "observation_id": "reference-001",
            "sensor_id": "sensor-1",
            "known_hypothesis": "A",
            "signal": "A",
            "reference_standard_ref": "fixture://known-standard/A/run-1",
            "reference_standard_sha256": sha("known standard A, run 1"),
            "observation_ref": "fixture://sensor-observation/reference-001",
            "observation_sha256": sha("reference observation 001: sensor-1 -> A"),
            "cost": "1/2",
        },
        {
            "observation_id": "reference-002",
            "sensor_id": "sensor-1",
            "known_hypothesis": "A",
            "signal": "A",
            "reference_standard_ref": "fixture://known-standard/A/run-2",
            "reference_standard_sha256": sha("known standard A, run 2"),
            "observation_ref": "fixture://sensor-observation/reference-002",
            "observation_sha256": sha("reference observation 002: sensor-1 -> A"),
            "cost": "1/2",
        },
    )
    return {
        "prior_hypothesis_a": "1/2",
        "calibrations": calibrations,
        "target_sensor_schedule": ("sensor-1", "sensor-2", "sensor-3"),
        "reference_observations": references,
    }


class ReferenceCalibratedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.inputs = fixture()
        self.report = build_report(**self.inputs)

    def test_known_reference_observations_update_shared_profile_posterior_exactly(self):
        reference = self.report["reference_phase"]
        posterior = {
            row["calibration_id"]: ratio(row["probability"])
            for row in reference["posterior_calibration_probabilities"]
        }
        self.assertEqual(posterior, {"profile-1": Fraction(9, 13), "profile-2": Fraction(4, 13)})
        self.assertEqual(ratio(reference["reference_evidence_probability"]), Fraction(117, 200))
        self.assertEqual(ratio(reference["total_declared_reference_cost"]), Fraction(1))
        self.assertEqual(reference["support_count_before"], 2)
        self.assertEqual(reference["support_count_after"], 2)

    def test_calibrated_policy_beats_prior_and_map_plugin_under_one_common_world(self):
        comparison = self.report["comparison_in_one_reference_conditioned_target_world"]
        self.assertEqual(ratio(comparison["uncalibrated_prior_policy_accuracy"]), Fraction(5119, 6500))
        self.assertEqual(ratio(comparison["reference_conditioned_bayes_policy_accuracy"]), Fraction(21, 26))
        self.assertEqual(ratio(comparison["map_profile_plugin_policy_accuracy"]), Fraction(4981, 6500))
        self.assertEqual(ratio(comparison["reference_conditioned_gain_over_uncalibrated_prior_policy"]), Fraction(131, 6500))
        self.assertEqual(ratio(comparison["reference_conditioned_gain_over_map_profile_plugin"]), Fraction(269, 6500))
        self.assertEqual(ratio(comparison["optimal_target_map_accuracy"]), Fraction(21, 26))
        self.assertEqual(ratio(comparison["baseline_probability_mass_requiring_fallback"]), Fraction(0))
        self.assertEqual(comparison["map_profile_plugin_unreachable_history_fallback"], "A")

    def test_reference_prefix_trace_exposes_exact_posterior_and_common_world_policy_value(self):
        rows = self.report["reference_phase"]["target_policy_prefix_trace"]
        self.assertEqual([row["reference_count"] for row in rows], [0, 1, 2])
        self.assertEqual(ratio(rows[0]["cumulative_reference_cost"]), Fraction(0))
        self.assertEqual(ratio(rows[1]["cumulative_reference_cost"]), Fraction(1, 2))
        self.assertEqual(ratio(rows[2]["cumulative_reference_cost"]), Fraction(1))
        first = {row["calibration_id"]: ratio(row["probability"]) for row in rows[1]["posterior_calibration_probabilities"]}
        final = {row["calibration_id"]: ratio(row["probability"]) for row in rows[2]["posterior_calibration_probabilities"]}
        self.assertEqual(first, {"profile-1": Fraction(3, 5), "profile-2": Fraction(2, 5)})
        self.assertEqual(final, {"profile-1": Fraction(9, 13), "profile-2": Fraction(4, 13)})
        self.assertEqual(ratio(rows[0]["target_policy_accuracy_under_final_reference_posterior_world"]), Fraction(5119, 6500))
        self.assertEqual(ratio(rows[2]["target_policy_accuracy_under_final_reference_posterior_world"]), Fraction(21, 26))

    def test_reference_observation_order_does_not_change_final_calibration_posterior(self):
        reversed_inputs = dict(self.inputs)
        reversed_inputs["reference_observations"] = tuple(reversed(self.inputs["reference_observations"]))
        reversed_report = build_report(**reversed_inputs)
        self.assertEqual(
            self.report["reference_phase"]["posterior_calibration_probabilities"],
            reversed_report["reference_phase"]["posterior_calibration_probabilities"],
        )

    def test_no_reference_observations_preserve_calibration_prior_and_policy(self):
        no_refs = dict(self.inputs)
        no_refs["reference_observations"] = ()
        report = build_report(**no_refs)
        self.assertEqual(
            report["reference_phase"]["posterior_calibration_probabilities"],
            report["reference_phase"]["prior_calibration_probabilities"],
        )
        comparison = report["comparison_in_one_reference_conditioned_target_world"]
        self.assertEqual(
            ratio(comparison["uncalibrated_prior_policy_accuracy"]),
            ratio(comparison["reference_conditioned_bayes_policy_accuracy"]),
        )
        self.assertEqual(ratio(report["reference_phase"]["total_declared_reference_cost"]), Fraction(0))

    def test_known_reference_hypothesis_b_updates_beta_likelihood_not_alpha(self):
        inputs = dict(self.inputs)
        refs = list(inputs["reference_observations"])
        refs[0] = {**refs[0], "known_hypothesis": "B"}
        inputs["reference_observations"] = tuple(refs)
        report = build_report(**inputs)
        posterior = {row["calibration_id"]: ratio(row["probability"]) for row in report["reference_phase"]["posterior_calibration_probabilities"]}
        self.assertEqual(posterior, {"profile-1": Fraction(3, 11), "profile-2": Fraction(8, 11)})

    def test_impossible_reference_evidence_fails_closed(self):
        inputs = dict(self.inputs)
        refs = list(inputs["reference_observations"])
        refs[0] = {**refs[0], "known_hypothesis": "A", "signal": "B"}
        refs[1] = {**refs[1], "known_hypothesis": "A", "signal": "B"}
        calibrations = list(inputs["calibrations"])
        for index, cal in enumerate(calibrations):
            models = dict(cal["sensor_models"])
            models["sensor-1"] = channel("1", "1")
            calibrations[index] = {**cal, "sensor_models": models}
        inputs["calibrations"] = tuple(calibrations)
        inputs["reference_observations"] = tuple(refs)
        with self.assertRaises(ImpossibleReferenceEvidenceError):
            build_report(**inputs)

    def test_reference_sensor_must_exist_in_target_schedule(self):
        inputs = dict(self.inputs)
        refs = list(inputs["reference_observations"])
        refs[0] = {**refs[0], "sensor_id": "reference-only-sensor"}
        inputs["reference_observations"] = tuple(refs)
        with self.assertRaises(ReferenceCalibrationError):
            build_report(**inputs)

    def test_duplicate_reference_ids_are_rejected(self):
        inputs = dict(self.inputs)
        refs = list(inputs["reference_observations"])
        refs[1] = {**refs[1], "observation_id": refs[0]["observation_id"]}
        inputs["reference_observations"] = tuple(refs)
        with self.assertRaises(ReferenceCalibrationError):
            build_report(**inputs)

    def test_reference_evidence_requires_digest_valid_cost_and_exact_probabilities(self):
        for field, value in (
            ("observation_sha256", "not-a-digest"),
            ("reference_standard_sha256", "not-a-digest"),
            ("cost", 0),
            ("cost", True),
            ("cost", 0.5),
        ):
            inputs = dict(self.inputs)
            refs = list(inputs["reference_observations"])
            refs[0] = {**refs[0], field: value}
            inputs["reference_observations"] = tuple(refs)
            with self.subTest(field=field, value=value), self.assertRaises(ReferenceCalibrationError):
                build_report(**inputs)

    def test_reference_evidence_digest_binds_both_standard_and_observation_sources(self):
        original = self.report["reference_phase"]["reference_evidence_digest"]
        changed = dict(self.inputs)
        refs = list(changed["reference_observations"])
        refs[0] = {**refs[0], "reference_standard_ref": "fixture://different-standard"}
        changed["reference_observations"] = tuple(refs)
        report = build_report(**changed)
        self.assertNotEqual(original, report["reference_phase"]["reference_evidence_digest"])

    def test_riv007_nested_reports_reconstruct(self):
        from reference_calibrated_evidence import _RIV007
        for key in (
            "uncalibrated_prior_filter_report",
            "reference_conditioned_filter_report",
            "map_profile_plugin_filter_report",
        ):
            _RIV007.validate_report(self.report["target_phase"][key])

    def test_target_history_cap_is_enforced_by_riv007(self):
        inputs = dict(self.inputs)
        inputs["max_histories"] = 4
        with self.assertRaises(ValueError):
            build_report(**inputs)

    def test_report_reconstruction_rejects_tampering_even_with_recomputed_outer_digest(self):
        self.assertEqual(validate_report(self.report), self.report)
        tampered = copy.deepcopy(self.report)
        tampered["reference_phase"]["posterior_calibration_probabilities"][0]["probability"] = {
            "numerator": 1,
            "denominator": 1,
        }
        core = {key: value for key, value in tampered.items() if key != "content_digest"}
        tampered["content_digest"] = hashlib.sha256(json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()).hexdigest()
        with self.assertRaises(ReferenceCalibrationError):
            validate_report(tampered)

    def test_published_json_schema_accepts_complete_report(self):
        if jsonschema is None:
            self.skipTest("jsonschema is installed in the repository workflow")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(self.report, schema)


if __name__ == "__main__":
    unittest.main(verbosity=2)
