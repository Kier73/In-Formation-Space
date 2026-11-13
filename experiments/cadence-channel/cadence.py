"""Exact analysis of discrete cadence modulation under additive jitter.

This is an independent, standard-library-only model of the timing-channel
semantics used by E-CPU's ``mailcpu/timing_channel.py``.  It is not a copy of
that module.  The model keeps three questions separate:

* the exact symbol and bit error probabilities under Gaussian jitter;
* the behaviour of a decision-directed phase-locked loop (PLL);
* the horizon over which a finite "zero error" observation is informative.

Run ``python cadence.py --scan --source-checks --json`` for the reproducible
artifact used by the README.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


SOURCE_REVISION = "c99af8c927fcbb7ff6f7e8a2d6489fd1489e7b65"
DEFAULT_SEED = 20261112
HORIZON_CAP = 1_000_000_000


# ---------------------------------------------------------------------------
# Configuration and exact Gaussian model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CadenceConfig:
    """Parameters for discrete cadence modulation.

    A symbol ``d`` in ``0 .. 2**bits_per_symbol - 1`` is transmitted as the
    inter-packet interval ``base_delay_ms + d * quantum_ms``.
    """

    base_delay_ms: float = 20.0
    quantum_ms: float = 6.0
    bits_per_symbol: int = 4
    pll_alpha: float = 0.05

    def __post_init__(self) -> None:
        for name, value in (
            ("base_delay_ms", self.base_delay_ms),
            ("quantum_ms", self.quantum_ms),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")
        if (
            not isinstance(self.bits_per_symbol, int)
            or isinstance(self.bits_per_symbol, bool)
            or self.bits_per_symbol <= 0
        ):
            raise ValueError("bits_per_symbol must be a positive integer")
        if self.bits_per_symbol > 31:
            raise ValueError("bits_per_symbol must be at most 31")
        if (
            not isinstance(self.pll_alpha, (int, float))
            or isinstance(self.pll_alpha, bool)
            or not math.isfinite(self.pll_alpha)
            or not 0 <= self.pll_alpha <= 1
        ):
            raise ValueError("pll_alpha must be finite in [0, 1]")

    @property
    def levels(self) -> int:
        return 1 << self.bits_per_symbol

    @property
    def max_symbol(self) -> int:
        return self.levels - 1

    def ideal_interval_ms(self, symbol: int) -> float:
        if not 0 <= symbol <= self.max_symbol:
            raise ValueError("symbol out of range")
        return self.base_delay_ms + symbol * self.quantum_ms


def _normal_cdf(x: float, sigma: float) -> float:
    if x == math.inf:
        return 1.0
    if x == -math.inf:
        return 0.0
    return 0.5 * math.erfc(-x / (sigma * math.sqrt(2.0)))


def _normal_sf(x: float, sigma: float) -> float:
    if x == -math.inf:
        return 1.0
    if x == math.inf:
        return 0.0
    return 0.5 * math.erfc(x / (sigma * math.sqrt(2.0)))


def symbol_transition_matrix(
    config: CadenceConfig, sigma_ms: float
) -> list[list[float]]:
    """Return ``P(decoded=e | sent=d)`` for the fixed-baseline decoder.

    The observation is ``max(0, ideal + J)`` with ``J ~ Normal(0, sigma**2)``.
    The decoder rounds ``(observation - base) / quantum`` to the nearest
    integer and clamps to the symbol alphabet.  The clamping at zero makes the
    lower decision cell of symbol 0 unbounded, which is handled explicitly.
    """

    if not math.isfinite(sigma_ms) or sigma_ms < 0:
        raise ValueError("sigma_ms must be finite and non-negative")

    levels = config.levels
    if sigma_ms == 0:
        return [
            [1.0 if decoded == sent else 0.0 for decoded in range(levels)]
            for sent in range(levels)
        ]

    delta = config.quantum_ms
    rows: list[list[float]] = []
    for sent in range(levels):
        row: list[float] = []
        for decoded in range(levels):
            lower = (
                -math.inf
                if decoded == 0
                else (decoded - sent - 0.5) * delta
            )
            upper = (
                math.inf
                if decoded == levels - 1
                else (decoded - sent + 0.5) * delta
            )
            probability = _normal_cdf(upper, sigma_ms) - _normal_cdf(
                lower, sigma_ms
            )
            row.append(max(0.0, probability))
        total = sum(row)
        if total <= 0 or not math.isfinite(total):
            raise ArithmeticError("transition row has no finite mass")
        rows.append([probability / total for probability in row])
    return rows


def exact_symbol_error_rate(config: CadenceConfig, sigma_ms: float) -> float:
    """Exact average symbol error probability for uniform input symbols.

    For an interior symbol both neighbours are error regions; the two edge
    symbols have only one.  With ``L`` levels the average is therefore
    ``2 * (L - 1) / L * Q(quantum / (2 * sigma))``.
    """

    if not math.isfinite(sigma_ms) or sigma_ms < 0:
        raise ValueError("sigma_ms must be finite and non-negative")
    if sigma_ms == 0:
        return 0.0
    tail = _normal_sf(0.5 * config.quantum_ms, sigma_ms)
    return 2.0 * (config.levels - 1) / config.levels * tail


def exact_bit_error_rate(config: CadenceConfig, sigma_ms: float) -> float:
    """Exact expected bit error rate for uniform symbols and Gray-free labels.

    Symbol labels are ordinary binary integers, so a symbol error can change
    several bits.  The calculation uses the full transition matrix rather than
    assuming that every symbol error changes exactly one bit.
    """

    if not math.isfinite(sigma_ms) or sigma_ms < 0:
        raise ValueError("sigma_ms must be finite and non-negative")
    if sigma_ms == 0:
        return 0.0
    rows = symbol_transition_matrix(config, sigma_ms)
    expected_bits = 0.0
    for sent, row in enumerate(rows):
        for decoded, probability in enumerate(row):
            expected_bits += probability * (sent ^ decoded).bit_count()
    return expected_bits / (config.levels * config.bits_per_symbol)


def zero_error_probability(
    config: CadenceConfig, sigma_ms: float, n_symbols: int
) -> float:
    """Probability of no symbol error in ``n_symbols`` independent draws."""

    if n_symbols < 0:
        raise ValueError("n_symbols must be non-negative")
    ser = exact_symbol_error_rate(config, sigma_ms)
    return (1.0 - ser) ** n_symbols


def horizon_for_clean_run(
    config: CadenceConfig, sigma_ms: float, confidence: float = 0.95
) -> int | None:
    """Largest symbol count with clean-run probability at least ``confidence``.

    ``None`` means the exact symbol error probability is zero, so the horizon
    is unbounded under the model.
    """

    if not 0 < confidence < 1:
        raise ValueError("confidence must lie strictly between 0 and 1")
    ser = exact_symbol_error_rate(config, sigma_ms)
    if ser <= 0:
        return None
    if ser >= 1:
        return 0
    log_survival = math.log1p(-ser)
    if log_survival == 0:
        return None
    horizon = math.floor(math.log(confidence) / log_survival)
    if horizon < 0:
        return 0
    if horizon > HORIZON_CAP:
        return None
    return int(horizon)


# ---------------------------------------------------------------------------
# Decoders and simulation
# ---------------------------------------------------------------------------


def _validate_observed(value: float) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("observed value must be finite and non-negative")


def _clamp_symbol(config: CadenceConfig, raw: float) -> int:
    return max(0, min(config.max_symbol, round(raw)))


def static_decode(config: CadenceConfig, observed_ms: float) -> int:
    """Fixed-baseline nearest-neighbour decoder."""

    _validate_observed(observed_ms)
    raw = (observed_ms - config.base_delay_ms) / config.quantum_ms
    return _clamp_symbol(config, raw)


class PllDecoder:
    """Decision-directed PLL with the same update rule as E-CPU.

    The phase error is measured against the *decoded* symbol.  This is the
    realisable rule used by the source implementation, and it is the rule that
    can be destabilised by a symbol error.
    """

    def __init__(self, config: CadenceConfig) -> None:
        self.config = config
        self.tracked_base_ms = config.base_delay_ms

    def decode_symbol(self, observed_ms: float) -> int:
        _validate_observed(observed_ms)
        raw = (observed_ms - self.tracked_base_ms) / self.config.quantum_ms
        decoded = _clamp_symbol(self.config, raw)
        ideal = self.tracked_base_ms + decoded * self.config.quantum_ms
        phase_error = observed_ms - ideal
        self.tracked_base_ms += self.config.pll_alpha * phase_error
        return decoded


class GeniePllDecoder(PllDecoder):
    """Analysis-only PLL that uses the transmitted symbol in the phase error.

    This decoder is not realisable at a receiver.  It isolates the cost of
    decision-directed tracking from the cost of tracking with perfect symbol
    knowledge.
    """

    def decode_symbol_with_truth(
        self, observed_ms: float, true_symbol: int
    ) -> int:
        _validate_observed(observed_ms)
        if not 0 <= true_symbol <= self.config.max_symbol:
            raise ValueError("true_symbol out of range")
        raw = (observed_ms - self.tracked_base_ms) / self.config.quantum_ms
        decoded = _clamp_symbol(self.config, raw)
        ideal = self.tracked_base_ms + true_symbol * self.config.quantum_ms
        phase_error = observed_ms - ideal
        self.tracked_base_ms += self.config.pll_alpha * phase_error
        return decoded


def generate_stream(
    config: CadenceConfig,
    sigma_ms: float,
    n_symbols: int,
    seed: int,
) -> tuple[list[int], list[float]]:
    """Generate uniform symbols and independent additive Gaussian jitter."""

    if not math.isfinite(sigma_ms) or sigma_ms < 0:
        raise ValueError("sigma_ms must be finite and non-negative")
    if n_symbols < 0:
        raise ValueError("n_symbols must be non-negative")
    rng = random.Random(seed)
    symbols = [rng.randrange(config.levels) for _ in range(n_symbols)]
    jitters = [rng.gauss(0.0, sigma_ms) for _ in range(n_symbols)]
    return symbols, jitters


def decode_stream(
    config: CadenceConfig,
    symbols: Sequence[int],
    jitters_ms: Sequence[float],
    decoder: str = "static",
    true_bases_ms: Sequence[float] | None = None,
) -> dict[str, object]:
    """Decode a stream and return error, run, and baseline statistics.

    ``static`` uses the configured base, ``pll`` uses the decision-directed
    loop, and ``genie`` uses the transmitted symbol for the phase error.
    """

    if len(symbols) != len(jitters_ms):
        raise ValueError("symbols and jitters must have equal length")
    if true_bases_ms is None:
        true_bases_ms = [config.base_delay_ms] * len(symbols)
    if len(true_bases_ms) != len(symbols):
        raise ValueError("true_bases_ms must match the symbol stream length")
    if decoder not in {"static", "pll", "genie"}:
        raise ValueError("decoder must be 'static', 'pll', or 'genie'")

    pll = PllDecoder(config) if decoder == "pll" else None
    genie = GeniePllDecoder(config) if decoder == "genie" else None
    decoded: list[int] = []
    flags: list[bool] = []
    tracked: list[float] = []

    for symbol, jitter, true_base in zip(symbols, jitters_ms, true_bases_ms):
        if not 0 <= symbol <= config.max_symbol:
            raise ValueError("symbol out of range")
        if not math.isfinite(jitter):
            raise ValueError("jitter must be finite")
        if not math.isfinite(true_base):
            raise ValueError("true base must be finite")
        observed = max(0.0, true_base + symbol * config.quantum_ms + jitter)
        if decoder == "static":
            estimate = static_decode(config, observed)
        elif decoder == "pll":
            assert pll is not None
            estimate = pll.decode_symbol(observed)
            tracked.append(pll.tracked_base_ms)
        else:
            assert genie is not None
            estimate = genie.decode_symbol_with_truth(observed, symbol)
            tracked.append(genie.tracked_base_ms)
        decoded.append(estimate)
        flags.append(estimate != symbol)

    n = len(symbols)
    symbol_errors = sum(flags)
    bit_errors = sum(
        (sent ^ got).bit_count() for sent, got in zip(symbols, decoded)
    )

    error_runs = 0
    longest_run = 0
    current_run = 0
    for flag in flags:
        if flag:
            current_run += 1
            longest_run = max(longest_run, current_run)
            if current_run == 1:
                error_runs += 1
        else:
            current_run = 0

    n_prev_error = sum(flags[:-1])
    n_prev_ok = max(0, (n - 1) - n_prev_error)
    n_error_after_error = sum(
        1 for left, right in zip(flags, flags[1:]) if left and right
    )
    n_error_after_ok = sum(
        1 for left, right in zip(flags, flags[1:]) if not left and right
    )

    baseline_error = [
        value - true_base for value, true_base in zip(tracked, true_bases_ms)
    ]
    mean_baseline_error = (
        sum(baseline_error) / len(baseline_error) if baseline_error else None
    )
    var_baseline_error = (
        sum((value - mean_baseline_error) ** 2 for value in baseline_error)
        / (len(baseline_error) - 1)
        if baseline_error and len(baseline_error) > 1
        else None
    )

    return {
        "n": n,
        "symbol_errors": symbol_errors,
        "bit_errors": bit_errors,
        "ser": symbol_errors / n if n else 0.0,
        "ber": bit_errors / (n * config.bits_per_symbol) if n else 0.0,
        "error_runs": error_runs,
        "longest_error_run": longest_run,
        "p_error_after_error": (
            n_error_after_error / n_prev_error if n_prev_error else None
        ),
        "p_error_after_ok": (
            n_error_after_ok / n_prev_ok if n_prev_ok else None
        ),
        "mean_baseline_error_ms": mean_baseline_error,
        "var_baseline_error_ms": var_baseline_error,
        "final_tracked_base_ms": tracked[-1] if tracked else None,
    }


# ---------------------------------------------------------------------------
# Targeted experiments
# ---------------------------------------------------------------------------


def bytes_to_symbols(data: bytes, bits_per_symbol: int = 4) -> list[int]:
    """Split bytes into big-endian symbols; the source uses four-bit symbols."""

    if bits_per_symbol != 4:
        raise ValueError("byte splitting is defined here only for 4-bit symbols")
    symbols: list[int] = []
    for byte in data:
        symbols.append((byte >> 4) & 0x0F)
        symbols.append(byte & 0x0F)
    return symbols


def bounded_jitter_run(
    config: CadenceConfig,
    jmax_ms: float,
    n_drive: int = 200,
    symbol: int | None = None,
) -> dict[str, object]:
    """Drive the PLL toward ``+jmax`` then apply ``-jmax`` once.

    The worst-case decision variable is approximately ``2 * jmax`` after the
    loop has settled.  The run is a concrete check of the sufficient bound
    ``jmax <= quantum / 4``.
    """

    if not math.isfinite(jmax_ms) or jmax_ms < 0:
        raise ValueError("jmax_ms must be finite and non-negative")
    if n_drive < 1:
        raise ValueError("n_drive must be positive")
    chosen = config.levels // 2 if symbol is None else symbol
    symbols = [chosen] * (n_drive + 1)
    jitters = [jmax_ms] * n_drive + [-jmax_ms]
    return decode_stream(config, symbols, jitters, decoder="pll")


def drift_run(
    config: CadenceConfig,
    drift_ms_per_symbol: float,
    n_symbols: int = 400,
    sigma_ms: float = 0.0,
    decoder: str = "pll",
    symbol: int | None = None,
    seed: int = DEFAULT_SEED,
) -> dict[str, object]:
    """Run a constant linear baseline drift with optional Gaussian jitter."""

    if n_symbols < 1:
        raise ValueError("n_symbols must be positive")
    if not math.isfinite(sigma_ms) or sigma_ms < 0:
        raise ValueError("sigma_ms must be finite and non-negative")
    chosen = config.levels // 2 if symbol is None else symbol
    rng = random.Random(seed)
    symbols = [chosen] * n_symbols
    jitters = (
        [rng.gauss(0.0, sigma_ms) for _ in range(n_symbols)]
        if sigma_ms > 0
        else [0.0] * n_symbols
    )
    true_bases = [
        config.base_delay_ms + drift_ms_per_symbol * index
        for index in range(n_symbols)
    ]
    return decode_stream(
        config, symbols, jitters, decoder=decoder, true_bases_ms=true_bases
    )


def source_test_scan(
    config: CadenceConfig,
    sigma_ms: float,
    payload: bytes,
    seeds: Iterable[int],
) -> dict[str, object]:
    """Reproduce the source's fixed-payload, seeded jitter test."""

    symbols = bytes_to_symbols(payload, config.bits_per_symbol)
    failures: list[int] = []
    seed_count = 0
    for seed in seeds:
        seed_count += 1
        rng = random.Random(seed)
        jitters = [rng.gauss(0.0, sigma_ms) for _ in symbols]
        result = decode_stream(config, symbols, jitters, decoder="pll")
        if result["symbol_errors"]:
            failures.append(seed)
    return {
        "symbols_per_message": len(symbols),
        "seeds": seed_count,
        "failures": len(failures),
        "failure_rate": len(failures) / seed_count if seed_count else 0.0,
        "first_failures": failures[:10],
        "exact_ser": exact_symbol_error_rate(config, sigma_ms),
        "exact_ber": exact_bit_error_rate(config, sigma_ms),
        "exact_clean_probability": zero_error_probability(
            config, sigma_ms, len(symbols)
        ),
        "horizon_95": horizon_for_clean_run(config, sigma_ms, 0.95),
    }


def scan(
    config: CadenceConfig,
    sigma_ratios: Sequence[float],
    n_symbols: int,
    seed: int,
) -> list[dict[str, float | int | None]]:
    """Compare exact, static, PLL, and genie results over a jitter scan."""

    rows: list[dict[str, float | int | None]] = []
    for ratio in sigma_ratios:
        sigma_ms = ratio * config.quantum_ms
        symbols, jitters = generate_stream(config, sigma_ms, n_symbols, seed)
        static = decode_stream(config, symbols, jitters, decoder="static")
        pll = decode_stream(config, symbols, jitters, decoder="pll")
        genie = decode_stream(config, symbols, jitters, decoder="genie")
        ser = exact_symbol_error_rate(config, sigma_ms)
        ber = exact_bit_error_rate(config, sigma_ms)
        baseline_variance = pll["var_baseline_error_ms"]
        rows.append(
            {
                "sigma_over_quantum": ratio,
                "sigma_ms": sigma_ms,
                "exact_ser": ser,
                "exact_ber": ber,
                "static_ser": static["ser"],
                "static_ber": static["ber"],
                "pll_ser": pll["ser"],
                "pll_ber": pll["ber"],
                "genie_ser": genie["ser"],
                "genie_ber": genie["ber"],
                "clean_probability_32": (1.0 - ser) ** 32,
                "horizon_95": horizon_for_clean_run(config, sigma_ms, 0.95),
                "pll_error_after_error": pll["p_error_after_error"],
                "pll_error_after_ok": pll["p_error_after_ok"],
                "pll_longest_error_run": pll["longest_error_run"],
                "pll_baseline_variance_ratio": (
                    baseline_variance / (sigma_ms * sigma_ms)
                    if baseline_variance is not None and sigma_ms > 0
                    else None
                ),
            }
        )
    return rows


def targeted_experiments() -> dict[str, object]:
    """Small deterministic probes of the PLL's guarantee and failure modes."""

    bounded_config = CadenceConfig(
        base_delay_ms=10.0,
        quantum_ms=1.0,
        bits_per_symbol=4,
        pll_alpha=0.05,
    )
    bounded: list[dict[str, object]] = []
    for jmax in (0.20, 0.24, 0.25, 0.26, 0.30):
        result = bounded_jitter_run(
            bounded_config, jmax, n_drive=200, symbol=8
        )
        bounded.append(
            {
                "jmax_over_quantum": jmax,
                "symbol_errors": result["symbol_errors"],
                "longest_error_run": result["longest_error_run"],
                "mean_baseline_error_ms": result["mean_baseline_error_ms"],
            }
        )

    drift_config = CadenceConfig(
        base_delay_ms=10.0,
        quantum_ms=1.0,
        bits_per_symbol=4,
        pll_alpha=0.1,
    )
    drift: list[dict[str, object]] = []
    for per_symbol in (0.02, 0.04, 0.049, 0.05, 0.051, 0.08):
        pll = drift_run(
            drift_config,
            per_symbol,
            n_symbols=500,
            sigma_ms=0.0,
            decoder="pll",
            symbol=8,
        )
        static = drift_run(
            drift_config,
            per_symbol,
            n_symbols=500,
            sigma_ms=0.0,
            decoder="static",
            symbol=8,
        )
        drift.append(
            {
                "drift_ms_per_symbol": per_symbol,
                "drift_over_alpha_quantum": per_symbol
                / (drift_config.pll_alpha * drift_config.quantum_ms),
                "pll_errors": pll["symbol_errors"],
                "static_errors": static["symbol_errors"],
                "pll_mean_baseline_error_ms": pll[
                    "mean_baseline_error_ms"
                ],
            }
        )

    variance_config = CadenceConfig(
        base_delay_ms=20.0,
        quantum_ms=1.0,
        bits_per_symbol=4,
        pll_alpha=0.05,
    )
    variance_rows: list[dict[str, object]] = []
    for sigma, trials in ((0.05, 200_000), (0.20, 200_000)):
        symbols, jitters = generate_stream(
            variance_config, sigma, trials, DEFAULT_SEED
        )
        pll = decode_stream(variance_config, symbols, jitters, "pll")
        variance_rows.append(
            {
                "sigma_ms": sigma,
                "trials": trials,
                "pll_ser": pll["ser"],
                "baseline_variance_ratio": (
                    pll["var_baseline_error_ms"] / (sigma * sigma)
                ),
                "linear_prediction": variance_config.pll_alpha
                / (2.0 - variance_config.pll_alpha),
            }
        )

    return {
        "bounded_jitter": bounded,
        "drift": drift,
        "baseline_variance": variance_rows,
    }


def source_checks(seed_count: int = 500) -> list[dict[str, object]]:
    """Run the two source benchmark configurations and exact predictions."""

    cases = [
        {
            "name": "short_jitter_test",
            "config": CadenceConfig(
                base_delay_ms=20.0,
                quantum_ms=6.0,
                bits_per_symbol=4,
                pll_alpha=0.05,
            ),
            "sigma_ms": 1.0,
            "payload": b"QuantumTiming123",
        },
        {
            "name": "wan_benchmark",
            "config": CadenceConfig(
                base_delay_ms=50.0,
                quantum_ms=25.0,
                bits_per_symbol=4,
                pll_alpha=0.05,
            ),
            "sigma_ms": 2.0,
            "payload": b"WAN-Test",
        },
    ]
    results: list[dict[str, object]] = []
    for case in cases:
        config = case["config"]  # type: ignore[assignment]
        sigma_ms = float(case["sigma_ms"])  # type: ignore[arg-type]
        payload = case["payload"]  # type: ignore[assignment]
        scan_result = source_test_scan(
            config, sigma_ms, payload, range(seed_count)  # type: ignore[arg-type]
        )
        quotient = (3.0 * sigma_ms) / config.quantum_ms
        scan_result.update(
            {
                "name": case["name"],
                "base_delay_ms": config.base_delay_ms,
                "quantum_ms": config.quantum_ms,
                "sigma_over_quantum": sigma_ms / config.quantum_ms,
                "three_sigma_over_quantum": quotient,
                "three_sigma_bound_holds": 3.0 * sigma_ms <= config.quantum_ms / 4.0,
            }
        )
        results.append(scan_result)
    return results


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _format_text(report: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("Cadence channel: exact Gaussian-jitter analysis")
    lines.append(f"source revision: {report['source_revision']}")
    lines.append(f"python: {report['python']}")
    lines.append(f"seed: {report['seed']}   trials: {report['trials']}")
    lines.append("")

    if "scan" in report:
        lines.append("sigma/delta   exact SER    exact BER   static SER   PLL SER   genie SER   clean P(32)   N95")
        for row in report["scan"]:  # type: ignore[union-attr]
            lines.append(
                f"{row['sigma_over_quantum']:>10.3f}"
                f"   {row['exact_ser']:.6g}"
                f"   {row['exact_ber']:.6g}"
                f"   {row['static_ser']:.6g}"
                f"   {row['pll_ser']:.6g}"
                f"   {row['genie_ser']:.6g}"
                f"   {row['clean_probability_32']:.6g}"
                f"   {row['horizon_95']}"
            )
        lines.append("")

    if "source_checks" in report:
        lines.append("source checks")
        for case in report["source_checks"]:  # type: ignore[union-attr]
            lines.append(
                f"  {case['name']}: symbols={case['symbols_per_message']}"
                f" sigma/delta={case['sigma_over_quantum']:.4f}"
                f" exact SER={case['exact_ser']:.6g}"
                f" clean P={case['exact_clean_probability']:.6g}"
                f" failures={case['failures']}/{case['seeds']}"
                f" 3sigma bound={case['three_sigma_bound_holds']}"
            )
        lines.append("")

    if "targeted" in report:
        targeted = report["targeted"]
        assert isinstance(targeted, dict)
        lines.append("bounded jitter: drive +jmax for 200 symbols, then -jmax")
        for row in targeted["bounded_jitter"]:  # type: ignore[union-attr]
            lines.append(
                f"  jmax/delta={row['jmax_over_quantum']:.2f}"
                f" errors={row['symbol_errors']}"
                f" longest_run={row['longest_error_run']}"
            )
        lines.append("")
        lines.append("linear drift, 500 symbols, alpha=0.1, quantum=1")
        for row in targeted["drift"]:  # type: ignore[union-attr]
            lines.append(
                f"  drift/alpha*delta={row['drift_over_alpha_quantum']:.2f}"
                f" PLL errors={row['pll_errors']}"
                f" static errors={row['static_errors']}"
            )
        lines.append("")

    lines.append("Note: the exact model assumes uniform independent symbols,")
    lines.append("independent additive Gaussian jitter, a fixed baseline for the")
    lines.append("static decoder, and no packet loss or reordering.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exact cadence-channel error and PLL analysis"
    )
    parser.add_argument(
        "--scan", action="store_true", help="run the jitter-ratio scan"
    )
    parser.add_argument(
        "--source-checks",
        action="store_true",
        help="reproduce the two source benchmark configurations",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=100000,
        help="symbols per scan row (default: 100000)",
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="Monte Carlo seed"
    )
    parser.add_argument(
        "--seed-count",
        type=int,
        default=500,
        help="number of seeds in the source-test reproduction",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of a table"
    )
    parser.add_argument(
        "--out", type=Path, help="write the report to this path"
    )
    args = parser.parse_args(argv)

    if not args.scan and not args.source_checks:
        args.scan = True
        args.source_checks = True

    report: dict[str, object] = {
        "source_revision": SOURCE_REVISION,
        "python": platform.python_version(),
        "seed": args.seed,
        "trials": args.trials,
        "horizon_cap": HORIZON_CAP,
        "horizon_note": (
            "A null 95% clean-run horizon means the computed horizon exceeds "
            "horizon_cap; the exact symbol error probability is still positive "
            "for every sigma > 0."
        ),
        "targeted": targeted_experiments(),
    }

    if args.scan:
        config = CadenceConfig(
            base_delay_ms=20.0,
            quantum_ms=1.0,
            bits_per_symbol=4,
            pll_alpha=0.05,
        )
        ratios = [0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
        report["scan_config"] = asdict(config)
        report["scan"] = scan(config, ratios, args.trials, args.seed)

    if args.source_checks:
        report["source_checks"] = source_checks(args.seed_count)

    text = (
        json.dumps(report, indent=2, sort_keys=True)
        if args.json
        else _format_text(report)
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
