import unittest
from fractions import Fraction
from heterogeneous_evidence import HistoryLimitError, build_report, validate_report


def sensor(name, a, b):
    return {
        "sensor_id": name,
        "p_signal_a_given_hypothesis_a": a,
        "p_signal_a_given_hypothesis_b": b,
    }


def ratio(value):
    return Fraction(value["numerator"], value["denominator"])


def fixture():
    return dict(
        prior_hypothesis_a="1/2",
        sensors=(
            sensor("strong-1", "9/10", "1/10"),
            sensor("strong-2", "9/10", "1/10"),
            sensor("weak-1", "3/5", "2/5"),
            sensor("weak-2", "3/5", "2/5"),
        ),
    )


class HeterogeneousEvidenceTests(unittest.TestCase):
    def test_posterior_accumulator_matches_all_sixteen_histories(self):
        report = build_report(**fixture())
        self.assertEqual(report["full_history"]["raw_history_count"], 16)
        self.assertEqual(report["full_history"]["raw_histories_checked"], 16)
        self.assertEqual(report["summary"]["map_accuracy"], report["full_history"]["raw_history_accuracy"])
        self.assertEqual(report["summary"]["terminal_posterior_state_count"], 9)
        self.assertEqual(report["posterior_accumulator"]["terminal_posterior_state_count"], 9)

    def test_posterior_layers_merge_histories_as_the_evidence_arrives(self):
        report = build_report(**fixture())
        self.assertEqual(report["summary"]["posterior_state_counts_by_layer"], [1, 2, 3, 6, 9])
        self.assertEqual(report["summary"]["raw_prefix_history_node_count"], 31)
        self.assertEqual(report["summary"]["layered_posterior_accumulator_state_count"], 21)

    def test_plain_count_is_not_sufficient_for_posterior_or_map_decision(self):
        report = build_report(**fixture())
        diagnostic = report["count_A_diagnostic"]
        self.assertFalse(diagnostic["sufficient_for_posterior"])
        self.assertFalse(diagnostic["sufficient_for_map_decision"])
        middle = next(row for row in diagnostic["classes"] if row["count_A"] == 2)
        self.assertEqual(len(middle["distinct_map_decisions"]), 2)

    def test_same_total_count_can_yield_opposite_decisions(self):
        report = build_report(**fixture())
        rows = {row["history"]: row for row in report["full_history"]["raw_history_rows"]}
        strong_positive = rows["AABB"]
        strong_negative = rows["BBAA"]
        self.assertEqual(strong_positive["count_A"], strong_negative["count_A"])
        self.assertEqual(strong_positive["map_decision"], "A")
        self.assertEqual(strong_negative["map_decision"], "B")
        self.assertEqual(ratio(strong_positive["posterior_A"]), Fraction(36, 37))
        self.assertEqual(ratio(strong_negative["posterior_A"]), Fraction(1, 37))

    def test_posterior_grouping_merges_histories_with_same_evidence(self):
        report = build_report(**fixture())
        grouped = report["full_history"]["posterior_groups"]
        self.assertEqual(sum(item["history_count"] for item in grouped), 16)
        self.assertEqual(len(grouped), 9)
        self.assertTrue(any(item["history_count"] > 1 for item in grouped))

    def test_repeated_identical_sensors_reduce_to_count_statistic(self):
        report = build_report(
            prior_hypothesis_a="1/2",
            sensors=tuple(sensor(f"sensor-{i}", "3/4", "1/4") for i in range(5)),
        )
        self.assertTrue(report["count_A_diagnostic"]["sufficient_for_posterior"])
        self.assertTrue(report["count_A_diagnostic"]["sufficient_for_map_decision"])
        self.assertEqual(report["summary"]["terminal_posterior_state_count"], 6)

    def test_uninformative_sensors_leave_posterior_at_prior(self):
        report = build_report(
            prior_hypothesis_a="1/4",
            sensors=(sensor("u1", "1/2", "1/2"), sensor("u2", "1/2", "1/2")),
        )
        self.assertEqual(report["summary"]["terminal_posterior_state_count"], 1)
        self.assertEqual(ratio(report["full_history"]["posterior_groups"][0]["posterior_A"]), Fraction(1, 4))
        self.assertEqual(ratio(report["summary"]["map_accuracy"]), Fraction(3, 4))

    def test_perfect_heterogeneous_schedule_marks_impossible_histories(self):
        report = build_report(
            prior_hypothesis_a="1/2",
            sensors=(sensor("perfect-1", 1, 0), sensor("perfect-2", 1, 0)),
        )
        impossible = [row for row in report["full_history"]["raw_history_rows"] if row["posterior_A"] is None]
        self.assertEqual(len(impossible), 2)
        self.assertEqual(report["full_history"]["unreachable_history_count"], 2)
        self.assertEqual(report["summary"]["terminal_posterior_state_count"], 2)
        self.assertEqual(ratio(report["summary"]["map_accuracy"]), 1)

    def test_float_probabilities_are_rejected(self):
        with self.assertRaises(ValueError):
            build_report(prior_hypothesis_a=0.5, sensors=(sensor("s", "3/4", "1/4"),))

    def test_history_cap_fails_closed(self):
        with self.assertRaises(HistoryLimitError):
            build_report(prior_hypothesis_a="1/2", sensors=fixture()["sensors"], max_histories=8)

    def test_duplicate_sensor_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            build_report(
                prior_hypothesis_a="1/2",
                sensors=(sensor("same", "3/4", "1/4"), sensor("same", "2/3", "1/3")),
            )

    def test_report_reconstruction_rejects_tampering(self):
        report = build_report(**fixture())
        self.assertEqual(validate_report(report), report)
        report["summary"]["terminal_posterior_state_count"] = 1
        with self.assertRaises(ValueError):
            validate_report(report)


if __name__ == "__main__":
    unittest.main()
