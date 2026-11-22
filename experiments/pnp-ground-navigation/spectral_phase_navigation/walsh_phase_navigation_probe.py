#!/usr/bin/env python3
"""Exact Walsh phase/conditioning probe for width-three SAT.

Pure Python standard library.  All spectral arithmetic uses integers
representing 8 * Fourier coefficient (fixed three-literal clauses).
Run: python walsh_phase_navigation_probe.py
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from random import Random

DENOMINATOR = 8


def clauses_from_energy_profile(profile: list[int]):
    """For n=3, one clause forbids each state x; multiplicity=energy[x]."""
    assert len(profile) == 8 and all(v >= 0 for v in profile)
    return [((0, 1, 2), tuple((x >> i) & 1 for i in range(3)))
            for x, count in enumerate(profile) for _ in range(count)]


def violated_count(clauses, assignment: int) -> int:
    return sum(all(((assignment >> i) & 1) == b for i, b in zip(var, forb))
               for var, forb in clauses)


def spectral_coefficients(clauses: list) -> dict[int, int]:
    """Sparse exact coefficients, c[S] = 8 * E_hat(S)."""
    c = defaultdict(int)
    for var, forbidden in clauses:
        if len(var) != 3 or len(set(var)) != 3:
            raise ValueError('this exact kernel expects three distinct variables per clause')
        for choice in range(8):
            mask = 0
            sign = 1
            for j, v in enumerate(var):
                if choice & (1 << j):
                    mask |= 1 << v
                    if forbidden[j]:
                        sign = -sign
            c[mask] += sign
    return dict(c)


def conditional_coefficients(c: dict[int, int], variable: int, bit: int):
    """Exact Fourier restriction: c'[S] = c[S]+(-1)^bit c[S union {i}]."""
    assert bit in (0, 1)
    v = 1 << variable
    sign = 1 if bit == 0 else -1
    out = defaultdict(int)
    for S, amplitude in c.items():
        if S & v:
            out[S ^ v] += sign * amplitude
        else:
            out[S] += amplitude
    return {S: amp for S, amp in out.items() if amp != 0 or S == 0}


def moment3(profile):
    mean = Fraction(sum(profile), len(profile))
    return sum(((Fraction(v) - mean) ** 3 for v in profile), Fraction(0)) / len(profile)


def centered_variance(profile):
    mean = Fraction(sum(profile), len(profile))
    return sum(((Fraction(v) - mean) ** 2 for v in profile), Fraction(0)) / len(profile)


def degree_power_numerators(c):
    # W_w = sum_s c[s]^2 / 64; use integer numerators for exact checks.
    return tuple(sum(amp*amp for mask, amp in c.items() if mask.bit_count() == degree)
                 for degree in (1, 2, 3))


def navigate_by_conditional_mean(c, n):
    """Exact method of conditional expectations, using sparse spectral updates.

    Returns a Boolean assignment, final number of violated clauses and trace.
    The method guarantees E(result) <= mean energy = m/8, not SAT in general.
    """
    remaining = set(range(n))
    x = 0
    trace = []
    current = dict(c)
    while remaining:
        # Choose strongest current first-order influence, then the bit that
        # decreases (or holds) the conditional expectation.
        i = max(sorted(remaining), key=lambda j: abs(current.get(1 << j, 0)))
        first = current.get(1 << i, 0)
        bit = 1 if first > 0 else 0
        if bit:
            x |= 1 << i
        after = conditional_coefficients(current, i, bit)
        assert after[0] <= current[0], 'conditional expectation increased'
        trace.append((i, bit, Fraction(after[0], DENOMINATOR)))
        current = after
        remaining.remove(i)
    assert all(mask == 0 for mask in current)
    assert current[0] % DENOMINATOR == 0
    return x, current[0] // DENOMINATOR, trace


def main():
    # Energy profiles of two ten-clause 3-SAT formulas on three variables.
    sat_profile   = [0, 1, 1, 2, 1, 2, 2, 1]
    unsat_profile = [1, 1, 1, 1, 1, 1, 1, 3]
    A = clauses_from_energy_profile(sat_profile)
    B = clauses_from_energy_profile(unsat_profile)
    assert len(A) == len(B) == 10
    assert [violated_count(A, x) for x in range(8)] == sat_profile
    assert [violated_count(B, x) for x in range(8)] == unsat_profile

    ca, cb = spectral_coefficients(A), spectral_coefficients(B)
    assert ca[0] == cb[0] == 10
    assert all(abs(ca[S]) == abs(cb[S]) == 2 for S in range(1, 8))
    assert degree_power_numerators(ca) == degree_power_numerators(cb) == (12, 12, 4)
    assert centered_variance(sat_profile) == centered_variance(unsat_profile) == Fraction(7,16)
    assert moment3(sat_profile) == Fraction(-3, 32)
    assert moment3(unsat_profile) == Fraction(21, 32)
    assert min(sat_profile) == 0 and min(unsat_profile) == 1

    # The exact same first restriction x0=0 distinguishes the two by *phase*.
    restricted_a = conditional_coefficients(ca, 0, 0)
    restricted_b = conditional_coefficients(cb, 0, 0)
    assert restricted_a[0] == restricted_b[0] == 8
    assert (restricted_a.get(2, 0), restricted_a.get(4, 0)) == (-4, -4)
    assert (restricted_b.get(2, 0), restricted_b.get(4, 0)) == (0, 0)
    # All completions x0=0 in B have energy exactly one: an UNSAT subground.
    assert all(violated_count(B, x) == 1 for x in range(8) if not (x & 1))

    for label, clauses, coeff in [('SAT', A, ca), ('UNSAT', B, cb)]:
        x, final_e, path = navigate_by_conditional_mean(coeff, 3)
        assert final_e == violated_count(clauses, x)
        assert final_e <= Fraction(len(clauses), 8)
        print(f'{label}: E_min={min(violated_count(clauses, v) for v in range(8))}; '
              f'Wnumerator={degree_power_numerators(coeff)}; '
              f'M3={moment3([violated_count(clauses, v) for v in range(8)])}; '
              f'navigation result x={x:03b}, E={final_e}; '
              f'conditional means={[str(step[2]) for step in path]}')

    rng = Random(20261122)
    trials = 300
    satisfiable_count = 0
    greedy_sat_count = 0
    for _ in range(trials):
        n, m = 8, 30
        clauses = []
        for _j in range(m):
            indices = tuple(sorted(rng.sample(range(n), 3)))
            forbidden = tuple(rng.randrange(2) for _ in range(3))
            clauses.append((indices, forbidden))
        c = spectral_coefficients(clauses)
        assert c[0] == m
        x, E, _ = navigate_by_conditional_mean(c, n)
        assert E == violated_count(clauses, x)
        assert E <= m // 8
        sat = any(violated_count(clauses, a) == 0 for a in range(1 << n))
        satisfiable_count += int(sat)
        greedy_sat_count += int(E == 0)
        if E == 0:
            assert sat
    assert (satisfiable_count, greedy_sat_count) == (279, 250)
    print(f'PASS: {trials} random 3-SAT navigation tests; exact E <= m/8 in all cases.')
    print(f'EXPLORATORY: {satisfiable_count} SAT instances by exhaustion; '
          f'{greedy_sat_count} found by phase-preserving conditional-mean navigation.')
    print('PASS: phase-magnitude counterexample, moments, and Fourier restriction invariants.')


if __name__ == '__main__':
    main()