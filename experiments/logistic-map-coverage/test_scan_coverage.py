import unittest

from scan_coverage import (
    PeriodicWindow,
    classify_parameter,
    compute_coverage_matrix,
    scan_windows,
)


class LogisticCoverageTests(unittest.TestCase):
    def test_known_stable_attractors_are_classified(self):
        # r=2.8 has a stable non-zero fixed point with multiplier magnitude 0.8.
        period, multiplier = classify_parameter(2.8)
        self.assertEqual(period, 1)
        self.assertLess(multiplier, 1.0)
        self.assertAlmostEqual(multiplier, 0.8, places=5)

        # These parameter values lie inside familiar stable periodic windows.
        period_two, multiplier_two = classify_parameter(3.2)
        self.assertEqual(period_two, 2)
        self.assertLess(multiplier_two, 1.0)

        period_three, multiplier_three = classify_parameter(3.83)
        self.assertEqual(period_three, 3)
        self.assertLess(multiplier_three, 1.0)

    def test_coverage_is_nonincreasing_with_coarser_resolution(self):
        windows = [
            PeriodicWindow(period=1, r_start=3.50, r_end=3.60, width=0.10, sample_count=100),
            PeriodicWindow(period=2, r_start=3.70, r_end=3.75, width=0.05, sample_count=50),
            PeriodicWindow(period=8, r_start=3.80, r_end=3.803, width=0.003, sample_count=3),
        ]
        matrix = compute_coverage_matrix(
            windows,
            deltas=[0.001, 0.01, 0.1],
            periods=[1, 2, 8],
            domain_width=0.5,
        )
        keys = ["delta=0.0010", "delta=0.0100", "delta=0.1000"]
        for period_key in ("P<=1", "P<=2", "P<=8"):
            values = [matrix[key][period_key] for key in keys]
            self.assertGreaterEqual(values[0], values[1])
            self.assertGreaterEqual(values[1], values[2])

    def test_coverage_is_nondecreasing_with_larger_period_budget(self):
        windows = [
            PeriodicWindow(period=1, r_start=3.50, r_end=3.60, width=0.10, sample_count=100),
            PeriodicWindow(period=2, r_start=3.70, r_end=3.75, width=0.05, sample_count=50),
            PeriodicWindow(period=8, r_start=3.80, r_end=3.803, width=0.003, sample_count=3),
        ]
        matrix = compute_coverage_matrix(
            windows,
            deltas=[0.001, 0.01],
            periods=[1, 2, 8],
            domain_width=0.5,
        )
        for delta_key in ("delta=0.0010", "delta=0.0100"):
            values = [matrix[delta_key][key] for key in ("P<=1", "P<=2", "P<=8")]
            self.assertLessEqual(values[0], values[1])
            self.assertLessEqual(values[1], values[2])

    def test_coverage_never_exceeds_normalized_domain(self):
        windows = [
            PeriodicWindow(period=1, r_start=3.5, r_end=4.0, width=0.5, sample_count=50000),
            PeriodicWindow(period=2, r_start=3.6, r_end=3.9, width=0.3, sample_count=30000),
        ]
        matrix = compute_coverage_matrix(
            windows,
            deltas=[0.0, 0.1],
            periods=[1, 2],
            domain_width=0.5,
        )
        for row in matrix.values():
            for value in row.values():
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_small_scan_returns_ordered_in_domain_candidate_runs(self):
        windows = scan_windows(n_samples=1000, max_period=16)
        previous_end = 3.5
        for window in windows:
            self.assertGreaterEqual(window.r_start, 3.5)
            self.assertLessEqual(window.r_end, 4.0)
            self.assertGreater(window.width, 0.0)
            self.assertGreaterEqual(window.sample_count, 1)
            self.assertGreaterEqual(window.r_start, previous_end)
            self.assertLessEqual(window.period, 16)
            previous_end = window.r_end


if __name__ == "__main__":
    unittest.main()
