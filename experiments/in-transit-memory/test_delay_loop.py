#!/usr/bin/env python3
"""Tests for the in-transit delay-loop retention model."""

import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from delay_loop import (
    SCAN_SCENARIOS,
    exact_half_life_time,
    half_life_rounds,
    main,
    repair_median_epochs,
    repair_survival_probability,
    retention_probability,
    simulate_retention,
    source_formula_half_life_time,
    summarize,
)


class DelayLoopRetentionTests(unittest.TestCase):
    def test_intact_block_matches_closed_form(self):
        slots = 7
        loss = 0.13
        for rounds in (0, 1, 2, 10):
            expected = (1.0 - loss) ** (slots * rounds)
            actual = retention_probability(slots, slots, loss, rounds)
            self.assertAlmostEqual(actual, expected, places=12)

    def test_any_one_packet_matches_closed_form(self):
        slots = 6
        loss = 0.2
        for rounds in (0, 1, 3, 25):
            survival = (1.0 - loss) ** rounds
            expected = 1.0 - (1.0 - survival) ** slots
            actual = retention_probability(slots, 1, loss, rounds)
            self.assertAlmostEqual(actual, expected, places=12)

    def test_intact_half_life_matches_closed_form(self):
        slots = 9
        loss = 0.04
        expected = math.log(0.5) / (slots * math.log1p(-loss))
        actual = half_life_rounds(slots, slots, loss)
        self.assertIsNotNone(actual)
        self.assertAlmostEqual(actual, expected, places=10)
        self.assertAlmostEqual(
            retention_probability(slots, slots, loss, actual), 0.5, places=9
        )

    def test_any_one_half_life_matches_closed_form(self):
        slots = 8
        loss = 0.07
        expected = math.log(1.0 - 2.0 ** (-1.0 / slots)) / math.log1p(-loss)
        actual = half_life_rounds(slots, 1, loss)
        self.assertIsNotNone(actual)
        self.assertAlmostEqual(actual, expected, places=10)
        self.assertAlmostEqual(
            retention_probability(slots, 1, loss, actual), 0.5, places=9
        )

    def test_source_formula_is_small_p_intact_approximation(self):
        slots = 32
        loss = 0.001
        period = 2.5
        exact = exact_half_life_time(slots, slots, loss, period)
        formula = source_formula_half_life_time(slots, loss, period)
        self.assertIsNotNone(exact)
        self.assertLess(abs(formula / exact - 1.0), 0.001)

    def test_source_formula_overestimates_at_high_loss(self):
        slots = 8
        loss = 0.5
        exact = exact_half_life_time(slots, slots, loss)
        formula = source_formula_half_life_time(slots, loss)
        self.assertIsNotNone(exact)
        ratio = formula / exact
        self.assertGreater(ratio, 1.3)
        self.assertLess(ratio, 1.5)

    def test_retention_decreases_with_recovery_threshold(self):
        slots = 64
        loss = 0.01
        rounds = 500
        thresholds = (1, 2, 4, 8, 64)
        probabilities = [
            retention_probability(slots, threshold, loss, rounds)
            for threshold in thresholds
        ]
        for stricter, looser in zip(probabilities[1:], probabilities[:-1]):
            self.assertLess(stricter, looser)

    def test_half_life_increases_with_more_redundancy(self):
        slots = 64
        loss = 0.02
        intact = half_life_rounds(slots, slots, loss)
        middle = half_life_rounds(slots, slots // 2, loss)
        replicated = half_life_rounds(slots, 1, loss)
        self.assertIsNotNone(intact)
        self.assertIsNotNone(middle)
        self.assertIsNotNone(replicated)
        self.assertLess(intact, middle)
        self.assertLess(middle, replicated)

    def test_larger_intact_block_has_shorter_half_life(self):
        small = half_life_rounds(16, 16, 0.02)
        large = half_life_rounds(64, 64, 0.02)
        self.assertIsNotNone(small)
        self.assertIsNotNone(large)
        self.assertGreater(small, large)

    def test_monte_carlo_agrees_at_half_life(self):
        slots = 16
        required = 12
        loss = 0.05
        rounds = half_life_rounds(slots, required, loss)
        self.assertIsNotNone(rounds)
        exact = retention_probability(slots, required, loss, rounds)
        simulated = simulate_retention(
            slots, required, loss, rounds, trials=30000, seed=1234
        )
        self.assertLess(abs(simulated - exact), 0.02)

    def test_monte_carlo_is_seeded(self):
        arguments = (12, 9, 0.03, 40, 5000, 77)
        first = simulate_retention(*arguments)
        second = simulate_retention(*arguments)
        self.assertEqual(first, second)

    def test_zero_loss_has_infinite_half_life(self):
        self.assertEqual(retention_probability(5, 3, 0.0, 1000), 1.0)
        self.assertIsNone(half_life_rounds(5, 3, 0.0))
        self.assertIsNone(exact_half_life_time(5, 3, 0.0))

    def test_complete_loss_is_discontinuous_at_zero(self):
        self.assertEqual(retention_probability(5, 1, 1.0, 0), 1.0)
        self.assertEqual(retention_probability(5, 1, 1.0, 1), 0.0)
        with self.assertRaises(ValueError):
            half_life_rounds(5, 1, 1.0)

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            retention_probability(0, 0, 0.1, 1)
        with self.assertRaises(ValueError):
            retention_probability(4, 5, 0.1, 1)
        with self.assertRaises(ValueError):
            retention_probability(4, 2, -0.1, 1)
        with self.assertRaises(ValueError):
            retention_probability(4, 2, 1.1, 1)
        with self.assertRaises(ValueError):
            retention_probability(4, 2, 0.1, -1)
        with self.assertRaises(ValueError):
            source_formula_half_life_time(4, 0.0)
        with self.assertRaises(ValueError):
            source_formula_half_life_time(4, 1.0)

    def test_repair_survival_is_geometric_in_epochs(self):
        slots, required, loss, epoch_rounds = 8, 6, 0.1, 10
        epoch_survival = retention_probability(
            slots, required, loss, epoch_rounds
        )
        for epochs in (0, 1, 3, 50):
            expected = epoch_survival ** epochs
            actual = repair_survival_probability(
                slots, required, loss, epoch_rounds, epochs
            )
            self.assertAlmostEqual(actual, expected, places=12)

    def test_repair_median_is_continuous_half_life(self):
        slots, required, loss, epoch_rounds = 8, 6, 0.1, 10
        epoch_survival = retention_probability(
            slots, required, loss, epoch_rounds
        )
        median = repair_median_epochs(slots, required, loss, epoch_rounds)
        self.assertIsNotNone(median)
        self.assertAlmostEqual(epoch_survival ** median, 0.5, places=10)

    def test_repair_median_resolves_near_certain_epochs(self):
        # The per-epoch survival is so close to 1 that the probability rounds
        # to 1 in double precision, but the log-tail calculation still exposes
        # a very large finite median.
        median = repair_median_epochs(64, 32, 0.01, 10)
        self.assertIsNotNone(median)
        self.assertGreater(median, 1.0e10)

    def test_repair_with_no_loss_never_fails(self):
        self.assertIsNone(repair_median_epochs(8, 6, 0.0, 10))
        self.assertEqual(
            repair_survival_probability(8, 6, 0.0, 10, 1000000), 1.0
        )

    def test_summarize_marks_formula_applicability(self):
        intact = summarize(8, 8, 0.5)
        self.assertTrue(intact["source_formula_applicable"])
        self.assertAlmostEqual(intact["retention_at_half_life"], 0.5, places=9)

        coded = summarize(8, 4, 0.5)
        self.assertFalse(coded["source_formula_applicable"])
        self.assertAlmostEqual(coded["retention_at_half_life"], 0.5, places=9)

    def test_cli_scan_emits_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--scan", "--json"])
        self.assertEqual(exit_code, 0)
        rows = json.loads(output.getvalue())
        self.assertEqual(len(rows), len(SCAN_SCENARIOS))
        for row in rows:
            self.assertIn("exact_half_life_rounds", row)
            self.assertIn("source_formula_applicable", row)

    def test_cli_output_writes_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "scan.json"
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    ["--scan", "--json", "--output", str(path)]
                )
            self.assertEqual(exit_code, 0)
            rows = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), len(SCAN_SCENARIOS))


if __name__ == "__main__":
    unittest.main()
