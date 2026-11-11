#!/usr/bin/env python3
"""Coverage Function Scanner for the Logistic Map.

Empirical evaluation of the Grounded Navigation Coverage Conjecture:
  C(δ, P) = μ({ W_i : period(W_i) <= P and width(W_i) >= δ })

Scans the quadratic family f_r(x) = r * x * (1 - x) across r in [3.5, 4.0].
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


R_MIN = 3.5
R_MAX = 4.0
WARMUP_STEPS = 600
TOLERANCE = 1e-6


@dataclass
class PeriodicWindow:
    period: int
    r_start: float
    r_end: float
    width: float
    sample_count: int


def classify_parameter(r: float, max_period: int = 64) -> Tuple[int, float]:
    """Classify attractor at parameter r.

    Returns:
        (period, multiplier) where period > 0 if stable cycle found, else (0, lyapunov)
    """
    x = 0.5
    # Warmup to reach attractor
    for _ in range(WARMUP_STEPS):
        x = r * x * (1.0 - x)

    # Detect cycle up to max_period
    x_base = x
    detected_p = 0
    orbit = [x_base]
    for p in range(1, max_period + 1):
        x = r * x * (1.0 - x)
        orbit.append(x)
        if abs(x - x_base) < TOLERANCE:
            detected_p = p
            break

    if detected_p > 0:
        # Compute orbit multiplier: lambda = prod(r * (1 - 2*x_i))
        # Use log-sum to prevent overflow
        log_mult = 0.0
        for xi in orbit[:detected_p]:
            deriv = abs(r * (1.0 - 2.0 * xi))
            log_mult += math.log(deriv + 1e-15)

        mult = math.exp(log_mult) if log_mult < 20 else float("inf")
        if mult < 1.0:
            return detected_p, mult

    # If no stable cycle <= max_period found, estimate Lyapunov exponent
    lyap_sum = 0.0
    m_steps = 200
    for _ in range(m_steps):
        x = r * x * (1.0 - x)
        deriv = abs(r * (1.0 - 2.0 * x))
        lyap_sum += math.log(deriv + 1e-15)
    return 0, lyap_sum / m_steps


def scan_windows(n_samples: int = 50000, max_period: int = 64) -> List[PeriodicWindow]:
    """Scan [R_MIN, R_MAX] and extract contiguous stable periodic windows."""
    step = (R_MAX - R_MIN) / n_samples
    windows: List[PeriodicWindow] = []

    current_p: Optional[int] = None
    start_r = R_MIN
    count = 0

    for i in range(n_samples):
        r = R_MIN + i * step
        p, _ = classify_parameter(r, max_period)

        if p > 0:
            if current_p == p:
                count += 1
            else:
                if current_p is not None and current_p > 0:
                    end_r = r
                    windows.append(
                        PeriodicWindow(
                            period=current_p,
                            r_start=round(start_r, 6),
                            r_end=round(end_r, 6),
                            width=round(end_r - start_r, 6),
                            sample_count=count,
                        )
                    )
                current_p = p
                start_r = r
                count = 1
        else:
            if current_p is not None and current_p > 0:
                end_r = r
                windows.append(
                    PeriodicWindow(
                        period=current_p,
                        r_start=round(start_r, 6),
                        r_end=round(end_r, 6),
                        width=round(end_r - start_r, 6),
                        sample_count=count,
                    )
                )
                current_p = None
                count = 0

    if current_p is not None and current_p > 0:
        windows.append(
            PeriodicWindow(
                period=current_p,
                r_start=round(start_r, 6),
                r_end=round(R_MAX, 6),
                width=round(R_MAX - start_r, 6),
                sample_count=count,
            )
        )

    return windows


def compute_coverage_matrix(
    windows: List[PeriodicWindow],
    deltas: List[float],
    periods: List[int],
    domain_width: float = 0.5,
) -> Dict[str, Dict[str, float]]:
    """Compute C(delta, P) = sum(width) / domain_width for windows with period <= P and width >= delta."""
    matrix: Dict[str, Dict[str, float]] = {}

    for delta in deltas:
        d_key = f"delta={delta:.4f}"
        matrix[d_key] = {}
        for p_budget in periods:
            p_key = f"P<={p_budget}"
            # Filter windows
            qualifying = [w for w in windows if w.period <= p_budget and w.width >= delta]
            # Avoid double-counting (windows are disjoint intervals)
            covered_measure = sum(w.width for w in qualifying)
            coverage_fraction = min(1.0, covered_measure / domain_width)
            matrix[d_key][p_key] = round(coverage_fraction, 4)

    return matrix


def main() -> int:
    n_samples = 50000
    max_period = 64
    deltas = [0.0002, 0.0005, 0.001, 0.002, 0.005, 0.010]
    period_budgets = [2, 4, 8, 16, 32, 64]

    print("=== LOGISTIC MAP COVERAGE FUNCTION SCANNER ===")
    print(f"Domain: r in [{R_MIN}, {R_MAX}], Grid points: {n_samples:,}")
    print(f"Max Period Budget: {max_period}, Resolving windows...")

    t0 = time.perf_counter()
    windows = scan_windows(n_samples=n_samples, max_period=max_period)
    t1 = time.perf_counter()

    print(f"Discovered {len(windows)} contiguous periodic windows in {t1 - t0:.2f} seconds.")

    # Show largest 8 windows
    sorted_by_width = sorted(windows, key=lambda w: w.width, reverse=True)
    print("\nTop 8 Largest Periodic Windows:")
    print(f"{'Period':>8} | {'r_start':>10} | {'r_end':>10} | {'Width (Δr)':>12} | {'Samples':>8}")
    print("-" * 58)
    for w in sorted_by_width[:8]:
        print(f"{w.period:8d} | {w.r_start:10.6f} | {w.r_end:10.6f} | {w.width:12.6f} | {w.sample_count:8d}")

    # Compute coverage matrix C(delta, P)
    coverage = compute_coverage_matrix(windows, deltas, period_budgets, domain_width=R_MAX - R_MIN)

    print("\nCoverage Function Matrix C(δ, P) [Fraction of [3.5, 4.0]]:")
    header = f"{'Resolution δ':>14} | " + " | ".join(f"{f'P<={p}':>8}" for p in period_budgets)
    print(header)
    print("-" * len(header))
    for d_key, p_dict in coverage.items():
        row = f"{d_key:>14} | " + " | ".join(f"{p_dict[f'P<={p}']:8.4f}" for p in period_budgets)
        print(row)

    out_data = {
        "experiment": "logistic-map-coverage",
        "date": "2026-11-11",
        "domain": {"r_min": R_MIN, "r_max": R_MAX, "measure": "normalized-lebesgue"},
        "grid_samples": n_samples,
        "runtime_seconds": round(t1 - t0, 3),
        "total_windows_found": len(windows),
        "top_windows": [asdict(w) for w in sorted_by_width[:12]],
        "coverage_matrix": coverage,
    }

    if "--json" in sys.argv:
        print("\nJSON Output:")
        print(json.dumps(out_data, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
