import copy
import unittest
from fractions import Fraction

from context_switching_evidence import (
    HistoryLimitError,
    build_report,
    validate_report,
)


def sensor(name, good_aa, good_ba, degraded_aa, degraded_ba):
    return {
        "sensor_id": name,
        "p_signal_a_given_hypothesis_a_good": good_aa,
        "p_signal_a_given_hypothesis_b_good": good_ba,
        "p_signal_a_given_hypothesis_a_degraded": degraded_aa,
        "p_signal_a_given_hypothesis_b_degraded": degraded_ba,
    }


def ratio(document):
    return Fraction(document["numerator"], document["denominator"])


def persistent_fixture():
    return {
        "prior_hypothesis_a": "1/2",
        "prior_context_good": "1/2",
        "context_transition": {
            "p_good_next_given_good": "9/10",
            "p_good_next_given_degraded": "1/10",
        },
        "sensors": tuple(
            sensor(
                f"sensor-{index}",
                "9/10", "1/10",
                "1/2", "1/2",
            )
            for index in range(1, 5)
        ),
    }


class ContextSwitchingEvidenceTests(unittest.TestCase):
    def test_joint_filter_reconstructs_every_ordered_history(self):
        report = build_report(**persistent_fixture())
        self.assertEqual(report["history_verification"]["raw_history_count"], 16)
        self.assertEqual(report["history_verification"]["raw_histories_checked"], 16)
        self.assertEqual(
            ratio(report["history_verification"]["total_history_probability"]),
            Fraction(1),
        )
        self.assertEqual(
            report["summary"]["joint_posterior_state_counts_by_layer"],
            [1, 2, 4, 8, 16],
        )
        self.assertEqual(
            report["summary"]["hypothesis_marginal_state_counts_by_layer"],
            [1, 2, 3, 6, 9],
        )
        self.assertEqual(report["summary"]["terminal_joint_posterior_state_count"], 16)
        self.assertEqual(report["summary"]["terminal_hypothesis_marginal_state_count"], 9)
        self.assertEqual(validate_report(report), report)

    def test_ab_and_ba_have_the_same_separate_marginals_but_different_joint_beliefs(self):
        report = build_report(**persistent_fixture())
        layer = next(
            item for item in report["joint_posterior_accumulator"]["layers"]
            if item["step"] == 2
        )
        self.assertEqual(layer["joint_posterior_state_count"], 4)
        self.assertEqual(layer["hypothesis_marginal_state_count"], 3)
        self.assertEqual(layer["separate_marginals_state_count"], 3)
        self.assertEqual(
            layer["same_separate_marginals_different_joint_group_count"],
            1,
        )

        witness = next(
            item for item in layer["separate_marginal_next_update_divergences"]
            if ratio(item["shared_posterior_hypothesis_a"]) == Fraction(1, 2)
        )
        self.assertEqual(
            ratio(witness["shared_posterior_regime_good"]),
            Fraction(301, 890),
        )
        rows = {item["history"]: item for item in witness["histories"]}
        self.assertEqual(set(rows), {"AB", "BA"})
        for history in ("AB", "BA"):
            self.assertEqual(
                ratio(next(
                    row["probability"]
                    for row in rows[history]["joint_posterior"]
                    if row["hypothesis"] == "A" and row["regime"] == "good"
                )) + ratio(next(
                    row["probability"]
                    for row in rows[history]["joint_posterior"]
                    if row["hypothesis"] == "A" and row["regime"] == "degraded"
                )),
                Fraction(1, 2),
            )
        self.assertEqual(
            ratio(rows["AB"]["next_posterior_hypothesis_a_on_signal_a"]),
            Fraction(2747, 4290),
        )
        self.assertEqual(
            ratio(rows["BA"]["next_posterior_hypothesis_a_on_signal_a"]),
            Fraction(2907, 4610),
        )
        self.assertNotEqual(
            rows["AB"]["next_posterior_hypothesis_a_on_signal_a"],
            rows["BA"]["next_posterior_hypothesis_a_on_signal_a"],
        )
        diagnostic = report["marginal_sufficiency_diagnostic"]
        self.assertFalse(
            diagnostic["hypothesis_marginal_preserves_next_update_under_schedule"]
        )
        self.assertFalse(
            diagnostic["separate_marginals_preserve_next_update_under_schedule"]
        )

    def test_joint_posterior_contains_hypothesis_regime_association(self):
        report = build_report(**persistent_fixture())
        layer = report["joint_posterior_accumulator"]["layers"][2]
        witness = next(
            item for item in layer["separate_marginal_next_update_divergences"]
            if ratio(item["shared_posterior_hypothesis_a"]) == Fraction(1, 2)
        )
        rows = {row["history"]: row for row in witness["histories"]}
        ab = {
            (row["hypothesis"], row["regime"]): ratio(row["probability"])
            for row in rows["AB"]["joint_posterior"]
        }
        ba = {
            (row["hypothesis"], row["regime"]): ratio(row["probability"])
            for row in rows["BA"]["joint_posterior"]
        }
        self.assertEqual(sum(v for (h, _), v in ab.items() if h == "A"), Fraction(1, 2))
        self.assertEqual(sum(v for (_, z), v in ab.items() if z == "good"), Fraction(301, 890))
        self.assertEqual(sum(v for (h, _), v in ba.items() if h == "A"), Fraction(1, 2))
        self.assertEqual(sum(v for (_, z), v in ba.items() if z == "good"), Fraction(301, 890))
        self.assertNotEqual(ab, ba)
        self.assertNotEqual(
            ab[("A", "good")] - ab[("A", "degraded")],
            ba[("A", "good")] - ba[("A", "degraded")],
        )

    def test_memoryless_context_transition_reduces_to_hypothesis_posterior(self):
        fixture = persistent_fixture()
        fixture["context_transition"] = {
            "p_good_next_given_good": "1/2",
            "p_good_next_given_degraded": "1/2",
        }
        report = build_report(**fixture)
        layers = report["joint_posterior_accumulator"]["layers"]
        for layer in layers:
            self.assertEqual(
                layer["same_hypothesis_marginal_different_joint_group_count"],
                0,
            )
            self.assertEqual(
                layer["same_separate_marginals_different_joint_group_count"],
                0,
            )
            self.assertEqual(
                layer["joint_posterior_state_count"],
                layer["hypothesis_marginal_state_count"],
            )
        self.assertTrue(
            report["marginal_sufficiency_diagnostic"][
                "hypothesis_marginal_preserves_next_update_under_schedule"
            ]
        )
        self.assertTrue(
            report["marginal_sufficiency_diagnostic"][
                "separate_marginals_preserve_next_update_under_schedule"
            ]
        )

    def test_perfect_regime_independent_sensors_mark_impossible_histories(self):
        fixture = {
            "prior_hypothesis_a": "1/2",
            "prior_context_good": "1/3",
            "context_transition": {
                "p_good_next_given_good": "2/3",
                "p_good_next_given_degraded": "1/4",
            },
            "sensors": (
                sensor("perfect-1", 1, 0, 1, 0),
                sensor("perfect-2", 1, 0, 1, 0),
            ),
        }
        report = build_report(**fixture)
        rows = report["full_history"]["rows"]
        self.assertEqual(
            sum(not item["reachable"] for item in rows),
            2,
        )
        self.assertEqual(report["history_verification"]["unreachable_history_count"], 2)
        self.assertEqual(
            ratio(report["history_verification"]["total_history_probability"]),
            Fraction(1),
        )

    def test_heterogeneous_sensor_schedule_is_retained_per_position(self):
        fixture = persistent_fixture()
        fixture["sensors"] = (
            sensor("strong", "9/10", "1/10", "3/5", "2/5"),
            sensor("weak", "3/5", "2/5", "1/2", "1/2"),
            sensor("medium", "4/5", "1/5", "11/20", "9/20"),
        )
        report = build_report(**fixture)
        self.assertEqual(
            [item["sensor_id"] for item in report["model"]["sensors"]],
            ["strong", "weak", "medium"],
        )
        self.assertEqual(report["history_verification"]["raw_history_count"], 8)
        self.assertEqual(
            ratio(report["history_verification"]["total_history_probability"]),
            Fraction(1),
        )

    def test_history_cap_fails_closed(self):
        with self.assertRaises(HistoryLimitError):
            build_report(**persistent_fixture(), max_histories=15)

    def test_invalid_probabilities_and_duplicate_sensor_ids_are_rejected(self):
        fixture = persistent_fixture()
        broken = dict(fixture["sensors"][0])
        broken["p_signal_a_given_hypothesis_a_good"] = 1.1
        fixture["sensors"] = (broken,)
        with self.assertRaises(ValueError):
            build_report(**fixture)

        fixture = persistent_fixture()
        duplicate = dict(fixture["sensors"][0])
        fixture["sensors"] = (fixture["sensors"][0], duplicate)
        with self.assertRaises(ValueError):
            build_report(**fixture)

    def test_float_probability_and_transition_parameters_are_rejected(self):
        fixture = persistent_fixture()
        broken = dict(fixture["sensors"][0])
        broken["p_signal_a_given_hypothesis_a_good"] = 0.9
        fixture["sensors"] = (broken,)
        with self.assertRaises(ValueError):
            build_report(**fixture)

        fixture = persistent_fixture()
        fixture["context_transition"] = {
            "p_good_next_given_good": 0.9,
            "p_good_next_given_degraded": "1/10",
        }
        with self.assertRaises(ValueError):
            build_report(**fixture)

    def test_report_validator_rejects_tampered_joint_transition(self):
        report = build_report(**persistent_fixture())
        changed = copy.deepcopy(report)
        changed["joint_posterior_accumulator"]["layers"][2][
            "joint_posterior_states"
        ][0]["map_decision"] = "B" if (
            changed["joint_posterior_accumulator"]["layers"][2][
                "joint_posterior_states"
            ][0]["map_decision"] == "A"
        ) else "A"
        with self.assertRaises(ValueError):
            validate_report(changed)

    def test_identical_context_likelihoods_remove_regime_information(self):
        fixture = persistent_fixture()
        for sensor_record in fixture["sensors"]:
            sensor_record["p_signal_a_given_hypothesis_a_degraded"] = (
                sensor_record["p_signal_a_given_hypothesis_a_good"]
            )
            sensor_record["p_signal_a_given_hypothesis_b_degraded"] = (
                sensor_record["p_signal_a_given_hypothesis_b_good"]
            )
        report = build_report(**fixture)
        for layer in report["joint_posterior_accumulator"]["layers"]:
            self.assertEqual(
                layer["same_hypothesis_marginal_different_joint_group_count"],
                0,
            )
        self.assertTrue(
            report["marginal_sufficiency_diagnostic"][
                "hypothesis_marginal_preserves_next_update_under_schedule"
            ]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
