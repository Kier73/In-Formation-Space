import unittest
from fractions import Fraction
from evidence_accumulation import HistoryLimitError, build_report, validate_report


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


class EvidenceAccumulationTests(unittest.TestCase):
    def test_five_noisy_observations_match_full_history_exactly(self):
        report = build_report(
            observation_count=5, prior_hypothesis_a="1/2",
            p_signal_a_given_hypothesis_a="3/4",
            p_signal_a_given_hypothesis_b="1/4",
        )
        self.assertEqual(ratio(report["summary"]["map_accuracy"]), Fraction(459, 512))
        self.assertEqual(ratio(report["full_history"]["raw_history_accuracy"]), Fraction(459, 512))
        self.assertTrue(report["full_history"]["exact_decision_equivalence"])

    def test_count_accumulator_has_six_states_for_five_signals(self):
        report = build_report(
            observation_count=5, prior_hypothesis_a="1/2",
            p_signal_a_given_hypothesis_a="3/4",
            p_signal_a_given_hypothesis_b="1/4",
        )
        self.assertEqual(report["summary"]["raw_history_count"], 32)
        self.assertEqual(report["summary"]["sufficient_statistic_state_count"], 6)
        self.assertEqual(report["summary"]["raw_history_state_reduction"], 26)

    def test_one_observation_accuracy_equals_best_single_sample_classifier(self):
        report = build_report(
            observation_count=1, prior_hypothesis_a="1/2",
            p_signal_a_given_hypothesis_a="3/4",
            p_signal_a_given_hypothesis_b="1/4",
        )
        self.assertEqual(ratio(report["summary"]["map_accuracy"]), Fraction(3, 4))

    def test_uninformative_sensor_cannot_improve_on_prior(self):
        report = build_report(
            observation_count=5, prior_hypothesis_a="1/5",
            p_signal_a_given_hypothesis_a="1/2",
            p_signal_a_given_hypothesis_b="1/2",
        )
        self.assertEqual(ratio(report["summary"]["map_accuracy"]), Fraction(4, 5))
        self.assertTrue(all(row["map_decision"] == "B" for row in report["sufficient_statistic"]["count_classes"]))

    def test_perfect_sensor_identifies_hypothesis_after_one_sample(self):
        report = build_report(
            observation_count=1, prior_hypothesis_a="2/5",
            p_signal_a_given_hypothesis_a=1,
            p_signal_a_given_hypothesis_b=0,
        )
        self.assertEqual(ratio(report["summary"]["map_accuracy"]), 1)

    def test_asymmetric_channel_still_uses_count_statistic(self):
        report = build_report(
            observation_count=4, prior_hypothesis_a="2/3",
            p_signal_a_given_hypothesis_a="4/5",
            p_signal_a_given_hypothesis_b="2/5",
        )
        self.assertTrue(report["full_history"]["exact_decision_equivalence"])
        self.assertEqual(
            ratio(report["summary"]["map_accuracy"]),
            ratio(report["full_history"]["raw_history_accuracy"]),
        )

    def test_unreachable_count_classes_are_marked(self):
        report = build_report(
            observation_count=3, prior_hypothesis_a="1/2",
            p_signal_a_given_hypothesis_a=1,
            p_signal_a_given_hypothesis_b=0,
        )
        rows = report["sufficient_statistic"]["count_classes"]
        self.assertEqual([row["map_decision"] for row in rows], ["B", "unreachable", "unreachable", "A"])
        self.assertEqual(ratio(report["summary"]["map_accuracy"]), Fraction(1))

    def test_float_probabilities_are_rejected(self):
        with self.assertRaises(ValueError):
            build_report(
                observation_count=2, prior_hypothesis_a=0.5,
                p_signal_a_given_hypothesis_a="3/4",
                p_signal_a_given_hypothesis_b="1/4",
            )

    def test_history_enumeration_cap_fails_closed(self):
        with self.assertRaises(HistoryLimitError):
            build_report(
                observation_count=5, prior_hypothesis_a="1/2",
                p_signal_a_given_hypothesis_a="3/4",
                p_signal_a_given_hypothesis_b="1/4",
                max_histories=16,
            )

    def test_report_reconstruction_rejects_tampering(self):
        report = build_report(
            observation_count=3, prior_hypothesis_a="1/2",
            p_signal_a_given_hypothesis_a="3/4",
            p_signal_a_given_hypothesis_b="1/4",
        )
        self.assertEqual(validate_report(report), report)
        report["summary"]["map_accuracy"] = {"numerator": 0, "denominator": 1}
        with self.assertRaises(ValueError):
            validate_report(report)


if __name__ == "__main__":
    unittest.main()
