#!/usr/bin/env python3
"""Corrected guarded-shortcut benchmark with a quotient-aware residue check.

The primary recurrence is evaluated modulo M_PRIMARY. A secondary check
computes the expected residue of that *canonical primary representative*
modulo M_CHECK by evaluating the affine transform modulo M_PRIMARY*M_CHECK,
then projecting first modulo M_PRIMARY and only then modulo M_CHECK.

This avoids the invalid assumption that recurrence modulo M_CHECK is the
projection of recurrence modulo M_PRIMARY when M_CHECK does not divide
M_PRIMARY.
"""

from __future__ import annotations

import json
import math
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Tuple


M_PRIMARY = (1 << 61) - 1
M_CHECK = (1 << 31) - 1
A_PARAM = 6364136223846793005
B_PARAM = 1442695040888963407


def raw_execution(x0: int, steps: int, a: int, b: int, modulus: int) -> int:
    """Direct execution in the primary ring: O(steps)."""
    x = x0
    for _ in range(steps):
        x = (a * x + b) % modulus
    return x


def matrix_multiply(
    left: Tuple[int, int, int, int],
    right: Tuple[int, int, int, int],
    modulus: int,
) -> Tuple[int, int, int, int]:
    """Multiply upper-triangular affine 2x2 matrices."""
    a1, b1, _, _ = left
    a2, b2, _, _ = right
    return (
        (a1 * a2) % modulus,
        (a1 * b2 + b1) % modulus,
        0,
        1,
    )


def matrix_power(
    base: Tuple[int, int, int, int], exponent: int, modulus: int
) -> Tuple[int, int, int, int]:
    """Binary matrix exponentiation: O(log exponent)."""
    result = (1, 0, 0, 1)
    while exponent:
        if exponent & 1:
            result = matrix_multiply(result, base, modulus)
        base = matrix_multiply(base, base, modulus)
        exponent >>= 1
    return result


def shortcut_orbit(x0: int, steps: int, a: int, b: int, modulus: int) -> int:
    """Compute the exact primary-ring state using an affine matrix power."""
    if steps < 0:
        raise ValueError("steps must be non-negative")
    if steps == 0:
        return x0 % modulus
    transform = matrix_power((a % modulus, b % modulus, 0, 1), steps, modulus)
    return (transform[0] * x0 + transform[1]) % modulus


def _compose_affine(
    left: Tuple[int, int], right: Tuple[int, int], modulus: int
) -> Tuple[int, int]:
    """Compose f(x)=a1*x+b1 after g(x)=a2*x+b2."""
    a1, b1 = left
    a2, b2 = right
    return (a1 * a2 % modulus, (a1 * b2 + b1) % modulus)


def _affine_power_coefficients(
    a: int, b: int, exponent: int, modulus: int
) -> Tuple[int, int]:
    """Independent pair-based exponentiation of an affine transform."""
    result = (1, 0)
    base = (a % modulus, b % modulus)
    while exponent:
        if exponent & 1:
            result = _compose_affine(result, base, modulus)
        base = _compose_affine(base, base, modulus)
        exponent >>= 1
    return result


def quotient_aware_guard_residue(
    x0: int,
    steps: int,
    a: int,
    b: int,
    primary_modulus: int = M_PRIMARY,
    check_modulus: int = M_CHECK,
) -> int:
    """Return the expected x_steps mod check_modulus for the primary recurrence.

    If U is the unbounded affine result, reducing U modulo the product
    M_PRIMARY*M_CHECK preserves U modulo M_PRIMARY. Therefore:

        ((U mod (M_PRIMARY*M_CHECK)) mod M_PRIMARY) mod M_CHECK

    is exactly the check residue of the canonical primary-ring representative.
    The inner product reduction is the essential quotient-aware correction.
    """
    if steps < 0:
        raise ValueError("steps must be non-negative")
    product_modulus = primary_modulus * check_modulus
    coeff_a, coeff_b = _affine_power_coefficients(
        a, b, steps, product_modulus
    )
    lifted = (coeff_a * x0 + coeff_b) % product_modulus
    canonical_primary = lifted % primary_modulus
    return canonical_primary % check_modulus


def guard_accepts(
    primary_state: int,
    expected_check_residue: int,
    check_modulus: int = M_CHECK,
) -> bool:
    """Check a primary result against its independently computed residue."""
    return primary_state % check_modulus == expected_check_residue


@dataclass
class BenchmarkPoint:
    steps: int
    raw_median_us: float
    shortcut_median_us: float
    guard_median_us: float
    navigation_median_us: float
    speedup: float
    raw_shortcut_match: bool
    guard_accepts_nominal: bool


def _median_seconds(
    operation: Callable[[], object], repeats: int
) -> Tuple[float, object]:
    operation()  # warm-up, excluded from sample
    samples: List[float] = []
    result: object = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = operation()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples), result


def benchmark_point(steps: int, repeats: int = 7) -> BenchmarkPoint:
    x0 = 42

    raw_time, raw_result = _median_seconds(
        lambda: raw_execution(x0, steps, A_PARAM, B_PARAM, M_PRIMARY),
        repeats,
    )
    shortcut_time, shortcut_result = _median_seconds(
        lambda: shortcut_orbit(x0, steps, A_PARAM, B_PARAM, M_PRIMARY),
        repeats,
    )
    guard_time, guard_result = _median_seconds(
        lambda: quotient_aware_guard_residue(
            x0, steps, A_PARAM, B_PARAM, M_PRIMARY, M_CHECK
        ),
        repeats,
    )
    guard_ok = guard_accepts(int(shortcut_result), int(guard_result))
    navigation_time = shortcut_time + guard_time
    speedup = raw_time / navigation_time if navigation_time else 0.0

    return BenchmarkPoint(
        steps=steps,
        raw_median_us=raw_time * 1e6,
        shortcut_median_us=shortcut_time * 1e6,
        guard_median_us=guard_time * 1e6,
        navigation_median_us=navigation_time * 1e6,
        speedup=speedup,
        raw_shortcut_match=(raw_result == shortcut_result),
        guard_accepts_nominal=guard_ok,
    )


def inject_intermediate_bitflip(
    x0: int,
    steps: int,
    fault_step: int,
    bit: int = 0,
) -> int:
    """Run the recurrence with one bit flipped after fault_step transitions."""
    if not 0 <= fault_step <= steps:
        raise ValueError("fault_step must be between 0 and steps")
    state = raw_execution(x0, fault_step, A_PARAM, B_PARAM, M_PRIMARY)
    state ^= 1 << bit
    return raw_execution(state, steps - fault_step, A_PARAM, B_PARAM, M_PRIMARY)


def fault_injection_result() -> Dict[str, object]:
    x0, steps, fault_step = 42, 10_000, 5_000
    nominal = shortcut_orbit(x0, steps, A_PARAM, B_PARAM, M_PRIMARY)
    expected_check = quotient_aware_guard_residue(
        x0, steps, A_PARAM, B_PARAM, M_PRIMARY, M_CHECK
    )
    faulty = inject_intermediate_bitflip(x0, steps, fault_step)
    return {
        "steps": steps,
        "fault_step": fault_step,
        "fault": "flip bit 0 of the primary state after fault_step transitions",
        "nominal_primary": nominal,
        "expected_check_residue": expected_check,
        "nominal_guard_accepts": guard_accepts(nominal, expected_check),
        "faulty_primary": faulty,
        "faulty_guard_accepts": guard_accepts(faulty, expected_check),
        "fault_detected": not guard_accepts(faulty, expected_check),
        "scope": (
            "This checks one injected state fault against an independently computed "
            "expected residue. A residue check can miss differences divisible by "
            "the check modulus; it is not a proof against all faults."
        ),
    }


def main() -> int:
    steps_values = [
        10, 15, 20, 25, 30, 35, 40, 50, 100, 500, 1_000, 5_000,
        10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000,
    ]
    rows = []
    for steps in steps_values:
        repeats = 3 if steps >= 1_000_000 else 7
        row = benchmark_point(steps, repeats=repeats)
        rows.append(row)
        print(
            f"{steps:>10,d} | {row.raw_median_us:>12.2f} | "
            f"{row.shortcut_median_us:>12.2f} | {row.guard_median_us:>12.2f} | "
            f"{row.navigation_median_us:>12.2f} | {row.speedup:>8.2f}x | "
            f"{row.raw_shortcut_match!s:>5} | {row.guard_accepts_nominal!s:>5}"
        )

    fault = fault_injection_result()
    print("\nFault injection:")
    print(json.dumps(fault, indent=2))

    first_winner = next((row.steps for row in rows if row.speedup > 1.0), None)
    print(f"\nFirst tested coordinate where guarded navigation wins: {first_winner}")

    result = {
        "experiment": "guarded-shortcut-tradeoff-v2",
        "parameters": {
            "primary_modulus": M_PRIMARY,
            "check_modulus": M_CHECK,
            "a": A_PARAM,
            "b": B_PARAM,
            "check_method": "affine exponentiation modulo product, then project to primary, then check modulus",
            "timing_statistic": "median",
            "python": sys.version,
            "platform": platform.platform(),
        },
        "points": [asdict(row) for row in rows],
        "fault_test": fault,
        "limitations": [
            "Interpreter setup cost and p_exit fallback cost are not included in navigation_median_us.",
            "A finite benchmark does not establish asymptotic performance on all platforms.",
            "The residue check can miss differences that are multiples of the check modulus.",
        ],
    }
    if "--json" in sys.argv:
        print("\nJSON:")
        print(json.dumps(result, indent=2))
    if not all(row.raw_shortcut_match and row.guard_accepts_nominal for row in rows):
        return 1
    if not fault["nominal_guard_accepts"] or not fault["fault_detected"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
