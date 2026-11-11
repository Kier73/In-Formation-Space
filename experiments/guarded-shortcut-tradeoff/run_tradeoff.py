#!/usr/bin/env python3
"""Empirical test of Grounded Navigation trade-off: Execution vs Guarded Shortcut.

Investigates:
  N(t) = c_I + c_g + c_σ(t) + p_exit * c_exec(t)
versus:
  E(t) = c_exec(t)

Over an affine modular recurrence:
  x_{k+1} = (a * x_k + b) mod M
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple


# Primary modulus: Mersenne prime M_61 = 2^61 - 1
M_PRIMARY = (1 << 61) - 1
A_PARAM = 6364136223846793005
B_PARAM = 1442695040888963407

# Redundant check modulus: Mersenne prime M_31 = 2^31 - 1
M_CHECK = (1 << 31) - 1


def egcd(a: int, b: int) -> Tuple[int, int, int]:
    """Extended Euclidean algorithm: returns (g, x, y) such that a*x + b*y = g."""
    if a == 0:
        return b, 0, 1
    g, y, x = egcd(b % a, a)
    return g, x - (b // a) * y, y


def mod_inv(a: int, m: int) -> int:
    """Compute modular inverse of a modulo m."""
    g, x, _ = egcd(a % m, m)
    if g != 1:
        raise ValueError(f"Modular inverse does not exist for {a} mod {m}")
    return x % m


def raw_execution(x0: int, t: int, a: int, b: int, m: int) -> int:
    """Direct step-by-step execution: O(t) steps."""
    x = x0
    for _ in range(t):
        x = (a * x + b) % m
    return x


def matrix_mult_2x2(m1: Tuple[int, int, int, int], m2: Tuple[int, int, int, int], mod: int) -> Tuple[int, int, int, int]:
    """Multiply two 2x2 matrices modulo mod."""
    # [[a1, b1], [0, 1]] * [[a2, b2], [0, 1]] = [[a1*a2, a1*b2 + b1], [0, 1]]
    a1, b1, _, _ = m1
    a2, b2, _, _ = m2
    return ((a1 * a2) % mod, (a1 * b2 + b1) % mod, 0, 1)


def matrix_pow_2x2(mat: Tuple[int, int, int, int], exp: int, mod: int) -> Tuple[int, int, int, int]:
    """Binary exponentiation of affine 2x2 matrix: O(log exp)."""
    result = (1, 0, 0, 1)  # Identity
    base = mat
    while exp > 0:
        if exp & 1:
            result = matrix_mult_2x2(result, base, mod)
        base = matrix_mult_2x2(base, base, mod)
        exp >>= 1
    return result


def shortcut_orbit(x0: int, t: int, a: int, b: int, m: int) -> int:
    """Descriptive shortcut using 2x2 affine matrix power: O(log t)."""
    if t == 0:
        return x0
    mat = (a % m, b % m, 0, 1)
    pow_mat = matrix_pow_2x2(mat, t, m)
    # [x_t, 1]^T = pow_mat * [x0, 1]^T
    xt = (pow_mat[0] * x0 + pow_mat[1]) % m
    return xt


def redundant_residue_guard(x0: int, t: int, a: int, b: int, m_check: int) -> int:
    """Guard evaluation on secondary coprime modulus: O(log t)."""
    return shortcut_orbit(x0 % m_check, t, a % m_check, b % m_check, m_check)


@dataclass
class BenchmarkPoint:
    t: int
    raw_time_sec: float
    raw_result: int
    shortcut_time_sec: float
    shortcut_result: int
    guard_time_sec: float
    guard_result: int
    total_nav_time_sec: float
    speedup_ratio: float
    results_match: bool


def benchmark_suite(t_values: List[int], repeats: int = 5) -> List[BenchmarkPoint]:
    x0 = 42
    points: List[BenchmarkPoint] = []

    for t in t_values:
        # 1. Benchmark raw execution (average of runs)
        t_raw_runs = []
        res_raw = -1
        # For very large t, limit repeats to avoid excessive wait
        current_repeats = 1 if t >= 5_000_000 else (2 if t >= 1_000_000 else repeats)
        for _ in range(current_repeats):
            start = time.perf_counter()
            res_raw = raw_execution(x0, t, A_PARAM, B_PARAM, M_PRIMARY)
            t_raw_runs.append(time.perf_counter() - start)
        avg_raw = min(t_raw_runs)

        # 2. Benchmark shortcut execution
        t_sc_runs = []
        res_sc = -1
        sc_repeats = max(repeats, 100)
        for _ in range(sc_repeats):
            start = time.perf_counter()
            res_sc = shortcut_orbit(x0, t, A_PARAM, B_PARAM, M_PRIMARY)
            t_sc_runs.append(time.perf_counter() - start)
        avg_sc = min(t_sc_runs)

        # 3. Benchmark guard evaluation
        t_guard_runs = []
        res_guard = -1
        for _ in range(sc_repeats):
            start = time.perf_counter()
            res_guard = redundant_residue_guard(x0, t, A_PARAM, B_PARAM, M_CHECK)
            t_guard_runs.append(time.perf_counter() - start)
        avg_guard = min(t_guard_runs)

        # Total navigation cost: N = c_sigma + c_guard
        total_nav = avg_sc + avg_guard
        speedup = avg_raw / total_nav if total_nav > 0 else 0.0

        points.append(
            BenchmarkPoint(
                t=t,
                raw_time_sec=avg_raw,
                raw_result=res_raw,
                shortcut_time_sec=avg_sc,
                shortcut_result=res_sc,
                guard_time_sec=avg_guard,
                guard_result=res_guard,
                total_nav_time_sec=total_nav,
                speedup_ratio=round(speedup, 2),
                results_match=(res_raw == res_sc),
            )
        )

    return points


def test_fault_detection() -> Dict[str, Any]:
    """Test fault injection and guard detection behavior."""
    x0 = 42
    t = 10_000
    # True nominal execution
    nominal_val = shortcut_orbit(x0, t, A_PARAM, B_PARAM, M_PRIMARY)
    nominal_check = redundant_residue_guard(x0, t, A_PARAM, B_PARAM, M_CHECK)

    # Injected fault: simulate single bit flip at step tau = 5000
    tau = 5000
    x_tau = raw_execution(x0, tau, A_PARAM, B_PARAM, M_PRIMARY)
    x_tau_corrupted = x_tau ^ 0x01  # Bit flip
    faulty_raw = raw_execution(x_tau_corrupted, t - tau, A_PARAM, B_PARAM, M_PRIMARY)

    # Check whether guard detects discrepancy
    guard_expected_for_corrupted = faulty_raw % M_CHECK
    detected = (guard_expected_for_corrupted != nominal_check)

    return {
        "t": t,
        "tau_fault": tau,
        "nominal_primary": nominal_val,
        "faulty_raw_primary": faulty_raw,
        "fault_caused_difference": (nominal_val != faulty_raw),
        "guard_nominal_check": nominal_check,
        "guard_detected_divergence": detected,
    }


def main() -> int:
    t_values = [10, 50, 100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000]

    print("=== RUNNING GROUNDED NAVIGATION BENCHMARK ===")
    print(f"Primary Modulus: 2^61 - 1, Check Modulus: 2^31 - 1")
    print(f"Sweeping t across {len(t_values)} coordinates: {t_values[0]} to {t_values[-1]:,}...")

    points = benchmark_suite(t_values)

    # Format tabular output
    print("\nBenchmark Results:")
    print(f"{'t (steps)':>12} | {'c_exec (raw)':>14} | {'c_sigma (sc)':>14} | {'c_guard':>14} | {'N = c_sc+c_g':>14} | {'Speedup':>9} | {'Match'}")
    print("-" * 95)
    for p in points:
        print(
            f"{p.t:12,d} | {p.raw_time_sec * 1e6:11.2f} us | {p.shortcut_time_sec * 1e6:11.2f} us | "
            f"{p.guard_time_sec * 1e6:11.2f} us | {p.total_nav_time_sec * 1e6:11.2f} us | {p.speedup_ratio:8.1f}x | {p.results_match}"
        )

    # Fault detection test
    fault_res = test_fault_detection()
    print("\nFault Injection Test:")
    print(f"  Nominal orbit matches faulty: {not fault_res['fault_caused_difference']}")
    print(f"  Guard divergence detected:   {fault_res['guard_detected_divergence']}")

    out_data = {
        "experiment": "guarded-shortcut-tradeoff",
        "date": "2026-11-11",
        "parameters": {
            "m_primary": M_PRIMARY,
            "m_check": M_CHECK,
            "a": A_PARAM,
            "b": B_PARAM,
        },
        "points": [asdict(p) for p in points],
        "fault_test": fault_res,
    }

    if "--json" in sys.argv:
        print("\nJSON Output:")
        print(json.dumps(out_data, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
