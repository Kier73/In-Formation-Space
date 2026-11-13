import unittest
from fractions import Fraction
from calibration_aware_evidence import HistoryLimitError, build_report, validate_report


def calibration(name, prior, models):
    return {"calibration_id": name, "prior_probability": prior, "sensor_models": models}


def channel(alpha, beta):
    return {
        "p_signal_a_given_hypothesis_a": alpha,
        "p_signal_a_given_hypothesis_b": beta,
    }


def fixture():
    return dict(
        prior_hypothesis_a="1/2",
        sensor_schedule=("sensor-1", "sensor-2", "sensor-3"),
        calibrations=(
            calibration("profile-1", "1/2", {
                "sensor-1": channel("9/10", "1/10"),
                "sensor-2": channel("7/10", "3/10"),
                "sensor-3": channel("9/10", "1/10"),
            }),
            calibration("profile-2", "1/2", {
                "sensor-1": channel("3/5", "2/5"),
                "sensor-2": channel("4/5", "1/5"),
                "sensor-3": channel("1/10", "3/5"),
            }),
        ),
    )


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


class CalibrationAwareEvidenceTests(unittest.TestCase):
    def test_joint_belief_accumulator_matches_every_raw_history(self):
        report = build_report(**fixture())
        self.assertEqual(report["shared_calibration_full_history"]["raw_histories_checked"], 8)
        self.assertEqual(
            report["joint_belief_accumulator"]["terminal_joint_belief_state_count"],
            report["shared_calibration_full_history"]["joint_belief_state_count"],
        )

    def test_scalar_marginal_collision_does_not_determine_next_update(self):
        report = build_report(**fixture())
        example = report["same_marginal_future_update_counterexample"]
        self.assertEqual(example["left_prefix"], "AB")
        self.assertEqual(example["right_prefix"], "BA")
        self.assertEqual(ratio(example["shared_model_posterior_A_before_next_signal"]), Fraction(1, 2))
        self.assertNotEqual(
            example["left_joint_posterior_before_next_signal"],
            example["right_joint_posterior_before_next_signal"],
        )
        self.assertEqual(
            ratio(example["left_shared_model_posterior_A_after_next_signal"]), Fraction(255, 454)
        )
        self.assertEqual(
            ratio(example["right_shared_model_posterior_A_after_next_signal"]), Fraction(95, 194)
        )
        self.assertNotEqual(
            example["left_shared_model_posterior_A_after_next_signal"],
            example["right_shared_model_posterior_A_after_next_signal"],
        )
        self.assertEqual(example["left_shared_model_map_decision_after_next_signal"], "A")
        self.assertEqual(example["right_shared_model_map_decision_after_next_signal"], "B")
        self.assertEqual(
            ratio(example["left_independent_redraw_posterior_A_after_next_signal"]), Fraction(10, 17)
        )
        self.assertEqual(example["left_independent_redraw_map_decision_after_next_signal"], "A")
        self.assertEqual(example["right_independent_redraw_map_decision_after_next_signal"], "A")

    def test_joint_belief_vectors_are_normalized(self):
        report = build_report(**fixture())
        for group in report["shared_calibration_full_history"]["posterior_groups"]:
            vector = group["posterior_joint_latent_state"]
            if vector is not None:
                self.assertEqual(sum((ratio(x) for x in vector), Fraction(0)), 1)

    def test_independent_redraw_policy_disagrees_on_some_shared_model_histories(self):
        report = build_report(**fixture())
        self.assertEqual(
            ratio(report["summary"]["decision_disagreement_probability_under_shared_model"]),
            Fraction(39, 200),
        )
        self.assertEqual(
            ratio(report["summary"]["shared_calibration_map_accuracy"]),
            Fraction(153, 200),
        )
        self.assertEqual(
            ratio(report["summary"]["independent_redraw_policy_accuracy_under_shared_model"]),
            Fraction(763, 1000),
        )

    def test_calibration_is_shared_across_position_specific_sensor_models(self):
        report = build_report(**fixture())
        models = report["model"]["calibrations"]
        self.assertEqual(len(models), 2)
        self.assertEqual(report["model"]["sensor_schedule"], ["sensor-1", "sensor-2", "sensor-3"])
        self.assertIn("shared across the complete observation session", report["model"]["calibration_scope"])

    def test_fixed_calibration_reduces_to_known_sensor_channel(self):
        schedule = ("same", "same", "same")
        report = build_report(
            prior_hypothesis_a="1/2",
            sensor_schedule=schedule,
            calibrations=(calibration("known", 1, {"same": channel("3/4", "1/4")}),),
        )
        for row in report["shared_calibration_full_history"]["raw_history_rows"]:
            self.assertEqual(row["posterior_A_shared_calibration"], row["independent_redraw_posterior_A"])
        self.assertEqual(report["summary"]["terminal_joint_belief_state_count"], 4)

    def test_calibration_prior_must_sum_exactly_to_one(self):
        f = fixture()
        f["calibrations"] = (
            calibration("profile-1", "1/3", {
                "sensor-1": channel("9/10", "1/10"),
                "sensor-2": channel("7/10", "3/10"),
                "sensor-3": channel("9/10", "1/10"),
            }),
            calibration("profile-2", "1/2", {
                "sensor-1": channel("3/5", "2/5"),
                "sensor-2": channel("4/5", "1/5"),
                "sensor-3": channel("1/10", "3/5"),
            }),
        )
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_exact_probabilities_reject_floats(self):
        f = fixture()
        f["calibrations"][0]["sensor_models"]["sensor-1"]["p_signal_a_given_hypothesis_a"] = 0.9
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_duplicate_calibration_ids_are_rejected(self):
        f = fixture()
        second = dict(f["calibrations"][1])
        second["calibration_id"] = "profile-1"
        f["calibrations"] = (f["calibrations"][0], second)
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_unknown_or_missing_sensor_models_are_rejected(self):
        f = fixture()
        model = dict(f["calibrations"][0])
        model["sensor_models"] = {"sensor-1": channel("9/10", "1/10")}
        f["calibrations"] = (model, f["calibrations"][1])
        with self.assertRaises(ValueError):
            build_report(**f)

    def test_impossible_histories_are_retained_as_unreachable(self):
        report = build_report(
            prior_hypothesis_a="1/2",
            sensor_schedule=("perfect", "perfect"),
            calibrations=(calibration("deterministic", 1, {"perfect": channel(1, 0)}),),
        )
        self.assertEqual(report["shared_calibration_full_history"]["unreachable_history_count"], 2)
        self.assertEqual(report["summary"]["terminal_joint_belief_state_count"], 2)

    def test_history_cap_fails_closed(self):
        f = fixture()
        f["max_histories"] = 4
        with self.assertRaises(HistoryLimitError):
            build_report(**f)

    def test_report_reconstruction_rejects_tampering(self):
        report = build_report(**fixture())
        self.assertEqual(validate_report(report), report)
        report["summary"]["terminal_joint_belief_state_count"] = 1
        with self.assertRaises(ValueError):
            validate_report(report)


if __name__ == "__main__":
    unittest.main()
