import unittest

from scan_coverage_v2 import (
    CandidateWindow,
    classify_parameter,
    compute_coverage_matrix,
    scan_candidate_windows,
)


class LogisticCoverageV2Tests(unittest.TestCase):
    def test_known_stable_periods_agree_across_initial_conditions(self):
        expected = ((2.8, 1), (3.2, 2), (3.83, 3))
        for parameter, expected_period in expected:
            with self.subTest(parameter=parameter):
                period, multiplier = classify_parameter(parameter)
                self.assertEqual(period, expected_period)
                self.assertLess(multiplier, 1.0)

    def test_parameter_with_no_confirmed_candidate_is_not_called_chaotic(self):
        period, multiplier = classify_parameter(3.9)
        self.assertEqual(period, 0)
        self.assertEqual(multiplier, float("inf"))

    def test_bad_configuration_is_rejected(self):
        for kwargs in (
            {"n_samples": 0},
            {"max_period": 0},
            {"warmup_steps": -1},
            {"tolerance": 0.0},
            {"repeated_returns": 0},
            {"stability_margin": 1.0},
            {"initial_conditions": ()},
            {"initial_conditions": (0.0,)},
        ):
            with self.subTest(kwargs=kwargs):
                if "n_samples" in kwargs:
                    with self.assertRaises(ValueError):
                        scan_candidate_windows(**kwargs)
                else:
                    with self.assertRaises(ValueError):
                        classify_parameter(2.8, **kwargs)

    def test_cell_centered_windows_have_exact_sample_width(self):
        windows = scan_candidate_windows(
            n_samples=256,
            max_period=16,
            warmup_steps=600,
        )
        step = 0.5 / 256
        previous_end = 3.5
        for window in windows:
            self.assertGreaterEqual(window.r_start, 3.5)
            self.assertLessEqual(window.r_end, 4.0)
            self.assertGreater(window.width, 0.0)
            self.assertAlmostEqual(window.width, window.sample_count * step, places=8)
            self.assertGreaterEqual(window.r_start, previous_end)
            previous_end = window.r_end

    def test_coverage_is_monotone_in_resolution_and_period_budget(self):
        windows = [
            CandidateWindow(1, 3.5, 3.6, 0.1, 100),
            CandidateWindow(2, 3.7, 3.75, 0.05, 50),
            CandidateWindow(8, 3.8, 3.803, 0.003, 3),
        ]
        matrix = compute_coverage_matrix(
            windows,
            deltas=(0.001, 0.01, 0.1),
            period_budgets=(1, 2, 8),
        )
        for period_key in ("P<=1", "P<=2", "P<=8"):
            values = [matrix[key][period_key] for key in ("delta=0.0010", "delta=0.0100", "delta=0.1000")]
            self.assertGreaterEqual(values[0], values[1])
            self.assertGreaterEqual(values[1], values[2])
        for delta_key in ("delta=0.0010", "delta=0.0100", "delta=0.1000"):
            values = [matrix[delta_key][key] for key in ("P<=1", "P<=2", "P<=8")]
            self.assertLessEqual(values[0], values[1])
            self.assertLessEqual(values[1], values[2])


if __name__ == "__main__":
    unittest.main()
