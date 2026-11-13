from __future__ import annotations

import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cadence


def binomial_tolerance(probability: float, trials: int, z: float = 6.0) -> float:
    return z * math.sqrt(max(probability * (1.0 - probability), 0.0) / trials)


class ExactModelTests(unittest.TestCase):
    def test_noiseless_round_trip(self) -> None:
        config = cadence.CadenceConfig(
            base_delay_ms=25.0,
            quantum_ms=5.0,
            bits_per_symbol=4,
            pll_alpha=0.05,
        )
        payload = b"MailCPU_Substrate"
        symbols = cadence.bytes_to_symbols(payload)
        intervals = [config.ideal_interval_ms(symbol) for symbol in symbols]

        self.assertEqual(cadence.static_decode(config, intervals[0]), symbols[0])
        decoded = [
            cadence.static_decode(config, interval) for interval in intervals
        ]
        self.assertEqual(decoded, symbols)

        pll = cadence.PllDecoder(config)
        self.assertEqual(
            [pll.decode_symbol(interval) for interval in intervals], symbols
        )

    def test_transition_rows_are_probability_distributions(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0)
        for sigma in (0.05, 0.15, 0.30, 0.50, 1.0):
            rows = cadence.symbol_transition_matrix(config, sigma)
            self.assertEqual(len(rows), config.levels)
            for row in rows:
                self.assertEqual(len(row), config.levels)
                self.assertTrue(all(probability >= 0.0 for probability in row))
                self.assertAlmostEqual(sum(row), 1.0, delta=1e-12)

    def test_exact_ser_matches_transition_matrix(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0)
        for sigma in (0.05, 0.10, 0.20, 0.30, 0.50, 1.0):
            rows = cadence.symbol_transition_matrix(config, sigma)
            from_matrix = sum(
                probability
                for sent, row in enumerate(rows)
                for decoded, probability in enumerate(row)
                if sent != decoded
            ) / config.levels
            self.assertAlmostEqual(
                from_matrix,
                cadence.exact_symbol_error_rate(config, sigma),
                delta=1e-12,
            )

    def test_exact_ber_is_bounded_and_monotone(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0)
        previous = 0.0
        for sigma in (0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.0, 2.0):
            ber = cadence.exact_bit_error_rate(config, sigma)
            self.assertGreaterEqual(ber, 0.0)
            self.assertLessEqual(ber, 0.5)
            self.assertGreaterEqual(ber, previous - 1e-15)
            previous = ber

    def test_zero_jitter_is_error_free(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0)
        symbols = [index % config.levels for index in range(500)]
        jitters = [0.0] * len(symbols)
        for decoder in ("static", "pll", "genie"):
            result = cadence.decode_stream(config, symbols, jitters, decoder)
            self.assertEqual(result["symbol_errors"], 0)
            self.assertEqual(result["bit_errors"], 0)


class MonteCarloValidationTests(unittest.TestCase):
    def test_static_decoder_matches_exact_error_rates(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0, pll_alpha=0.05)
        trials = 200_000
        for sigma in (0.15, 0.30):
            symbols, jitters = cadence.generate_stream(
                config, sigma, trials, seed=20261112
            )
            result = cadence.decode_stream(config, symbols, jitters, "static")
            exact_ser = cadence.exact_symbol_error_rate(config, sigma)
            exact_ber = cadence.exact_bit_error_rate(config, sigma)
            self.assertAlmostEqual(
                result["ser"],
                exact_ser,
                delta=binomial_tolerance(exact_ser, trials),
            )
            self.assertAlmostEqual(
                result["ber"],
                exact_ber,
                delta=binomial_tolerance(
                    exact_ber, trials * config.bits_per_symbol
                ),
            )

    def test_pll_baseline_variance_matches_ar1_prediction(self) -> None:
        config = cadence.CadenceConfig(
            quantum_ms=1.0, bits_per_symbol=4, pll_alpha=0.05
        )
        # At sigma = 0.05 the exact symbol error probability is about 1e-23,
        # so the PLL remains in its linear, error-free regime.
        sigma = 0.05
        symbols, jitters = cadence.generate_stream(
            config, sigma, 200_000, seed=20261112
        )
        result = cadence.decode_stream(config, symbols, jitters, "pll")
        self.assertEqual(result["symbol_errors"], 0)
        predicted_ratio = config.pll_alpha / (2.0 - config.pll_alpha)
        measured_ratio = result["var_baseline_error_ms"] / (sigma * sigma)
        self.assertAlmostEqual(
            measured_ratio, predicted_ratio, delta=0.10 * predicted_ratio
        )

    def test_pll_does_not_remove_white_noise(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0, pll_alpha=0.05)
        sigma = 0.30
        symbols, jitters = cadence.generate_stream(
            config, sigma, 200_000, seed=20261112
        )
        static = cadence.decode_stream(config, symbols, jitters, "static")
        pll = cadence.decode_stream(config, symbols, jitters, "pll")
        genie = cadence.decode_stream(config, symbols, jitters, "genie")
        self.assertGreater(static["ser"], 0.0)
        self.assertGreater(pll["ser"], 0.0)
        self.assertGreater(pll["ser"], genie["ser"] * 0.95)
        self.assertGreater(pll["ser"], static["ser"] * 0.95)


class BoundedJitterAndPllTests(unittest.TestCase):
    def test_sufficient_bounded_jitter_condition(self) -> None:
        config = cadence.CadenceConfig(
            base_delay_ms=10.0, quantum_ms=1.0, pll_alpha=0.05
        )
        safe = cadence.bounded_jitter_run(config, 0.25, n_drive=200, symbol=8)
        unsafe = cadence.bounded_jitter_run(config, 0.26, n_drive=200, symbol=8)
        self.assertEqual(safe["symbol_errors"], 0)
        self.assertGreater(unsafe["symbol_errors"], 0)

    def test_random_bounded_jitter_has_no_errors(self) -> None:
        config = cadence.CadenceConfig(
            base_delay_ms=10.0, quantum_ms=1.0, pll_alpha=0.05
        )
        bound = 0.24
        for seed in range(20):
            rng = random.Random(seed)
            symbols = [rng.randrange(config.levels) for _ in range(500)]
            jitters = [rng.uniform(-bound, bound) for _ in symbols]
            result = cadence.decode_stream(config, symbols, jitters, "pll")
            self.assertEqual(result["symbol_errors"], 0)

    def test_pll_tracks_drift_within_limit_and_loses_lock_beyond(self) -> None:
        config = cadence.CadenceConfig(
            base_delay_ms=10.0, quantum_ms=1.0, pll_alpha=0.1
        )
        within = cadence.drift_run(
            config, 0.04, n_symbols=500, sigma_ms=0.0, decoder="pll"
        )
        beyond = cadence.drift_run(
            config, 0.08, n_symbols=500, sigma_ms=0.0, decoder="pll"
        )
        static_within = cadence.drift_run(
            config, 0.04, n_symbols=500, sigma_ms=0.0, decoder="static"
        )
        self.assertEqual(within["symbol_errors"], 0)
        self.assertGreater(static_within["symbol_errors"], 0)
        self.assertGreater(beyond["symbol_errors"], 0)

    def test_pll_error_runs_are_recorded(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0, pll_alpha=0.05)
        symbols, jitters = cadence.generate_stream(
            config, 0.40, 100_000, seed=20261112
        )
        result = cadence.decode_stream(config, symbols, jitters, "pll")
        self.assertGreater(result["error_runs"], 0)
        self.assertGreaterEqual(result["longest_error_run"], 1)
        self.assertIsNotNone(result["p_error_after_error"])
        self.assertIsNotNone(result["p_error_after_ok"])


class SourceClaimTests(unittest.TestCase):
    def test_short_source_test_is_horizon_limited(self) -> None:
        config = cadence.CadenceConfig(
            base_delay_ms=20.0,
            quantum_ms=6.0,
            bits_per_symbol=4,
            pll_alpha=0.05,
        )
        sigma = 1.0
        ser = cadence.exact_symbol_error_rate(config, sigma)
        self.assertAlmostEqual(ser, 0.0025310588093064297, delta=1e-15)
        self.assertAlmostEqual(
            cadence.zero_error_probability(config, sigma, 32),
            0.9221046530345578,
            delta=1e-12,
        )
        self.assertEqual(cadence.horizon_for_clean_run(config, sigma, 0.95), 20)

    def test_wan_source_test_is_effectively_deterministic(self) -> None:
        config = cadence.CadenceConfig(
            base_delay_ms=50.0,
            quantum_ms=25.0,
            bits_per_symbol=4,
            pll_alpha=0.05,
        )
        sigma = 2.0
        ser = cadence.exact_symbol_error_rate(config, sigma)
        self.assertLess(ser, 1e-9)
        self.assertAlmostEqual(
            cadence.zero_error_probability(config, sigma, 16), 1.0, delta=1e-8
        )
        horizon = cadence.horizon_for_clean_run(config, sigma, 0.95)
        self.assertIsNotNone(horizon)
        assert horizon is not None
        self.assertGreater(horizon, 100_000_000)

    def test_source_drift_test_is_inside_tracking_region(self) -> None:
        config = cadence.CadenceConfig(
            base_delay_ms=20.0,
            quantum_ms=8.0,
            bits_per_symbol=4,
            pll_alpha=0.1,
        )
        payload = b"ABCDEFGHIJ" * 4
        symbols = cadence.bytes_to_symbols(payload)
        total = len(symbols)
        true_bases = [
            config.base_delay_ms + 10.0 * (index / total)
            for index in range(total)
        ]
        result = cadence.decode_stream(
            config,
            symbols,
            [0.0] * total,
            "pll",
            true_bases_ms=true_bases,
        )
        self.assertEqual(result["symbol_errors"], 0)
        final_base = result["final_tracked_base_ms"]
        self.assertIsNotNone(final_base)
        assert final_base is not None
        # The source test checks that the tracked base moved past 25 ms.
        self.assertGreater(final_base, 25.0)

    def test_source_test_reproduction(self) -> None:
        short = cadence.CadenceConfig(
            base_delay_ms=20.0,
            quantum_ms=6.0,
            bits_per_symbol=4,
            pll_alpha=0.05,
        )
        wan = cadence.CadenceConfig(
            base_delay_ms=50.0,
            quantum_ms=25.0,
            bits_per_symbol=4,
            pll_alpha=0.05,
        )
        short_result = cadence.source_test_scan(
            short, 1.0, b"QuantumTiming123", range(500)
        )
        wan_result = cadence.source_test_scan(
            wan, 2.0, b"WAN-Test", range(500)
        )
        # The exact clean-run probability is about 0.922, so failures are
        # expected.  The interval is deliberately wider than one RNG path.
        self.assertGreaterEqual(short_result["failures"], 30)
        self.assertLessEqual(short_result["failures"], 80)
        self.assertEqual(wan_result["failures"], 0)


class HorizonTests(unittest.TestCase):
    def test_horizon_boundary_is_consistent(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0)
        for sigma in (0.15, 0.20, 0.25, 0.30):
            horizon = cadence.horizon_for_clean_run(config, sigma, 0.95)
            self.assertIsNotNone(horizon)
            assert horizon is not None
            clean_at = cadence.zero_error_probability(config, sigma, horizon)
            clean_beyond = cadence.zero_error_probability(
                config, sigma, horizon + 1
            )
            self.assertGreaterEqual(clean_at, 0.95)
            self.assertLess(clean_beyond, 0.95)

    def test_zero_jitter_has_no_finite_horizon(self) -> None:
        config = cadence.CadenceConfig(quantum_ms=1.0)
        self.assertIsNone(cadence.horizon_for_clean_run(config, 0.0, 0.95))


if __name__ == "__main__":
    unittest.main()
