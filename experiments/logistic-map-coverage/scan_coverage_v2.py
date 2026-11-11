#!/usr/bin/env python3
"""More conservative numerical scan of logistic-map periodic windows.

Compared with scan_coverage.py, this version:
- samples parameter-cell centers and reports cell-boundary intervals;
- requires repeated p-step returns after the first candidate return;
- requires agreement across multiple initial conditions;
- applies an explicit stability margin;
- labels results as numerical candidate windows, not certified intervals.

This is still a floating-point heuristic, not a proof-producing interval method.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


R_MIN = 3.5
R_MAX = 4.0
DEFAULT_INITIALS = (0.5, 0.123456789)


@dataclass(frozen=True)
class CandidateWindow:
    period: int
    r_start: float
    r_end: float
    width: float
    sample_count: int


def logistic_step(r: float, x: float) -> float:
    return r * x * (1.0 - x)


def _classify_one_initial(
    r: float,
    initial: float,
    max_period: int,
    warmup_steps: int,
    tolerance: float,
    repeated_returns: int,
    stability_margin: float,
) -> Tuple[int, float]:
    x = initial
    for _ in range(warmup_steps):
        x = logistic_step(r, x)

    base = x
    orbit = [base]
    candidate_period = 0

    for period in range(1, max_period + 1):
        x = logistic_step(r, x)
        orbit.append(x)
        if abs(x - base) <= tolerance:
            candidate_period = period
            break

    if candidate_period == 0:
        return 0, float("inf")

    # Verify the proposed return repeatedly. A single near-recurrence is
    # insufficient evidence of an attracting periodic orbit.
    for _ in range(repeated_returns):
        for _ in range(candidate_period):
            x = logistic_step(r, x)
        if abs(x - base) > tolerance:
            return 0, float("inf")

    log_multiplier = 0.0
    for point in orbit[:candidate_period]:
        derivative = abs(r * (1.0 - 2.0 * point))
        if derivative == 0.0:
            log_multiplier = float("-inf")
            break
        log_multiplier += math.log(derivative)

    # A margin avoids classifying nearly neutral numerical returns as stable.
    if log_multiplier >= math.log1p(-stability_margin):
        return 0, float("inf")

    multiplier = math.exp(log_multiplier) if log_multiplier > -745 else 0.0
    return candidate_period, multiplier


def classify_parameter(
    r: float,
    max_period: int = 64,
    warmup_steps: int = 2000,
    tolerance: float = 1e-9,
    repeated_returns: int = 2,
    stability_margin: float = 1e-6,
    initial_conditions: Sequence[float] = DEFAULT_INITIALS,
) -> Tuple[int, float]:
    """Return a stable candidate period only when all initial conditions agree.

    A return period of zero means no stable candidate was established under
    these finite numerical settings. It does not mean the orbit is chaotic.
    """
    if not 0.0 < r <= 4.0:
        raise ValueError("r must be within (0, 4] for the logistic-map family")
    if max_period < 1:
        raise ValueError("max_period must be positive")
    if warmup_steps < 0:
        raise ValueError("warmup_steps must be non-negative")
    if tolerance <= 0.0 or not math.isfinite(tolerance):
        raise ValueError("tolerance must be finite and positive")
    if repeated_returns < 1:
        raise ValueError("repeated_returns must be positive")
    if not 0.0 <= stability_margin < 1.0:
        raise ValueError("stability_margin must be in [0, 1)")
    if not initial_conditions:
        raise ValueError("at least one initial condition is required")
    if any(not 0.0 < initial < 1.0 for initial in initial_conditions):
        raise ValueError("initial conditions must lie strictly inside (0, 1)")

    results = [
        _classify_one_initial(
            r=r,
            initial=initial,
            max_period=max_period,
            warmup_steps=warmup_steps,
            tolerance=tolerance,
            repeated_returns=repeated_returns,
            stability_margin=stability_margin,
        )
        for initial in initial_conditions
    ]

    periods = {period for period, _ in results}
    if len(periods) != 1:
        return 0, float("inf")
    period = next(iter(periods))
    if period == 0:
        return 0, float("inf")
    return period, max(multiplier for _, multiplier in results)


def scan_candidate_windows(
    n_samples: int = 20_000,
    max_period: int = 64,
    warmup_steps: int = 2000,
    tolerance: float = 1e-9,
    repeated_returns: int = 2,
    stability_margin: float = 1e-6,
    initial_conditions: Sequence[float] = DEFAULT_INITIALS,
) -> List[CandidateWindow]:
    """Scan parameter-cell centers and return grouped numerical candidates."""
    if n_samples < 1:
        raise ValueError("n_samples must be positive")

    step = (R_MAX - R_MIN) / n_samples
    windows: List[CandidateWindow] = []
    current_period: Optional[int] = None
    start_index = 0
    sample_count = 0

    def close_window(end_index: int) -> None:
        nonlocal current_period, start_index, sample_count
        if current_period is None or sample_count == 0:
            return
        start = R_MIN + start_index * step
        end = R_MIN + end_index * step
        windows.append(
            CandidateWindow(
                period=current_period,
                r_start=round(start, 10),
                r_end=round(end, 10),
                width=round(end - start, 10),
                sample_count=sample_count,
            )
        )
        current_period = None
        sample_count = 0

    for index in range(n_samples):
        r = R_MIN + (index + 0.5) * step
        period, _ = classify_parameter(
            r,
            max_period=max_period,
            warmup_steps=warmup_steps,
            tolerance=tolerance,
            repeated_returns=repeated_returns,
            stability_margin=stability_margin,
            initial_conditions=initial_conditions,
        )

        if period > 0 and period == current_period:
            sample_count += 1
        else:
            close_window(index)
            if period > 0:
                current_period = period
                start_index = index
                sample_count = 1

    close_window(n_samples)
    return windows


def compute_coverage_matrix(
    windows: Sequence[CandidateWindow],
    deltas: Sequence[float],
    period_budgets: Sequence[int],
    domain_width: float = R_MAX - R_MIN,
) -> Dict[str, Dict[str, float]]:
    if domain_width <= 0.0:
        raise ValueError("domain_width must be positive")
    if any(delta < 0.0 for delta in deltas):
        raise ValueError("resolution values must be non-negative")
    if any(period < 0 for period in period_budgets):
        raise ValueError("period budgets must be non-negative")

    matrix: Dict[str, Dict[str, float]] = {}
    for delta in deltas:
        row: Dict[str, float] = {}
        for period_budget in period_budgets:
            covered = sum(
                window.width
                for window in windows
                if window.period <= period_budget and window.width >= delta
            )
            row[f"P<={period_budget}"] = round(min(1.0, covered / domain_width), 6)
        matrix[f"delta={delta:.4f}"] = row
    return matrix


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20_000)
    parser.add_argument("--max-period", type=int, default=64)
    parser.add_argument("--warmup", type=int, default=2000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    deltas = [0.0002, 0.0005, 0.001, 0.002, 0.005, 0.010]
    period_budgets = [2, 4, 8, 16, 32, args.max_period]

    started = time.perf_counter()
    windows = scan_candidate_windows(
        n_samples=args.samples,
        max_period=args.max_period,
        warmup_steps=args.warmup,
    )
    elapsed = time.perf_counter() - started
    coverage = compute_coverage_matrix(windows, deltas, period_budgets)

    output = {
        "experiment": "logistic-map-coverage-v2",
        "domain": {"r_min": R_MIN, "r_max": R_MAX, "measure": "normalized-lebesgue"},
        "grid_samples": args.samples,
        "max_period": args.max_period,
        "warmup_steps": args.warmup,
        "initial_conditions": list(DEFAULT_INITIALS),
        "tolerance": 1e-9,
        "repeated_returns": 2,
        "stability_margin": 1e-6,
        "runtime_seconds": round(elapsed, 4),
        "candidate_window_count": len(windows),
        "candidate_windows": [asdict(window) for window in windows],
        "coverage_matrix": coverage,
        "interpretation": "finite-grid numerical candidate coverage; not certified parameter intervals",
    }

    print(f"Scanned {args.samples:,} cell-centered parameter values in {elapsed:.2f}s.")
    print(f"Found {len(windows)} candidate windows under repeated-return, two-initial-condition checks.")
    for delta, row in coverage.items():
        print(delta + " " + " ".join(f"{key}:{value:.4f}" for key, value in row.items()))
    if args.json:
        print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
