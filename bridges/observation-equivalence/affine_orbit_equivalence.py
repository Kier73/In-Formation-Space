"""Bounded exact comparison of two affine generator orbits.

For a fixed positive modulus M, the paired state (x_left, x_right) belongs
to a finite set of size M^2. If the pair repeats after every earlier output
matched, deterministic evolution repeats the same cycle forever. This
provides a finite proof of equality for all future steps in this model.

A step budget may stop before a mismatch or cycle is found. That result is
reported as "unknown", never as equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class AffineOrbitComparison:
    status: str
    checked_steps: int
    first_difference_step: Optional[int]
    left_value: Optional[int]
    right_value: Optional[int]
    cycle_entry_step: Optional[int]
    cycle_period: Optional[int]


def _validate_parameters(params: Tuple[int, int, int], name: str) -> Tuple[int, int, int]:
    if not isinstance(params, tuple) or len(params) != 3:
        raise ValueError(f"{name} must be a tuple (a, b, modulus)")
    a, b, modulus = params
    for label, value in (("a", a), ("b", b), ("modulus", modulus)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name}.{label} must be an integer")
    if modulus <= 0:
        raise ValueError(f"{name}.modulus must be positive")
    return a, b, modulus


def compare_affine_orbits(
    left: Tuple[int, int, int],
    right: Tuple[int, int, int],
    initial_left: int = 1,
    initial_right: int = 1,
    max_steps: Optional[int] = 100_000,
) -> AffineOrbitComparison:
    """Compare x[k+1]=(a*x[k]+b) mod M from k=0 onward.

    The two generators must use the same modulus. Equality is exact when a
    repeated pair-state is reached without any differing output. A concrete
    mismatch returns its first step as a finite counterexample. If max_steps
    is exhausted first, status is "unknown".

    With no step limit, at most M^2+1 pair states are needed in the worst case.
    This can be infeasible for large moduli, so the default uses a finite budget.
    """
    left_a, left_b, left_modulus = _validate_parameters(left, "left")
    right_a, right_b, right_modulus = _validate_parameters(right, "right")
    if left_modulus != right_modulus:
        raise ValueError("both affine generators must use the same modulus")
    for name, value in (("initial_left", initial_left), ("initial_right", initial_right)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if max_steps is not None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0:
            raise ValueError("max_steps must be a non-negative integer or None")

    modulus = left_modulus
    x_left = initial_left % modulus
    x_right = initial_right % modulus
    seen = {}
    step = 0

    while True:
        if x_left != x_right:
            return AffineOrbitComparison(
                status="different",
                checked_steps=step + 1,
                first_difference_step=step,
                left_value=x_left,
                right_value=x_right,
                cycle_entry_step=None,
                cycle_period=None,
            )

        pair = (x_left, x_right)
        if pair in seen:
            entry = seen[pair]
            return AffineOrbitComparison(
                status="equivalent",
                checked_steps=step,
                first_difference_step=None,
                left_value=None,
                right_value=None,
                cycle_entry_step=entry,
                cycle_period=step - entry,
            )

        if max_steps is not None and step >= max_steps:
            return AffineOrbitComparison(
                status="unknown",
                checked_steps=step,
                first_difference_step=None,
                left_value=None,
                right_value=None,
                cycle_entry_step=None,
                cycle_period=None,
            )

        seen[pair] = step
        x_left = (left_a * x_left + left_b) % modulus
        x_right = (right_a * x_right + right_b) % modulus
        step += 1
