#!/usr/bin/env python3
"""SPN-003: phase-cycle lower bounds and independently checked proof receipts.

A Fourier character chi_S obeys chi_S chi_T = chi_(S xor T).
For nonzero Fourier terms S,T,U=S xor T with *positive* amplitude
product, their independent-sign minima cannot all be attained. Any such
triple improves the triangle-inequality lower bound by 2*min(|a|).
Disjoint triples of *terms* can be added without assuming variable-disjoint
supports. A bounded, greedy packing is a heuristic; all proofs are exact.

For width-three CNF only, a[S] = integer_coefficient[S] / 8. No claim of
polynomial-time SAT is made: search trees may remain exponential.
"""
from __future__ import annotations

from fractions import Fraction
from spectral_receipts import (validate_formula, formula_digest, direct_energy,
    independent_residual_coefficients, as_ratio)
from walsh_phase_navigation_probe import (spectral_coefficients,
    conditional_coefficients)

VERSION = 'SPN-003-v1'


def find_positive_triangles(coeff):
    """List (gain_numerator, sorted masks) for frustrated Walsh cycles."""
    masks = sorted(s for s, a in coeff.items() if s and a)
    candidates = []
    for index, s in enumerate(masks):
        a = coeff[s]
        for t in masks[index + 1:]:
            u = s ^ t
            if u <= t:   # each unordered triple exactly once
                continue
            b, c = coeff[t], coeff.get(u, 0)
            if b and c and a * b * c > 0:
                candidates.append((2 * min(abs(a), abs(b), abs(c)), (s, t, u)))
    return sorted(candidates, key=lambda item: (-item[0], item[1]))


def triangle_bound(coeff):
    """Return exact lower bound numerator / 8 and a deterministic packing."""
    used = set()
    selected = []
    bonus = 0
    for gain, triangle in find_positive_triangles(coeff):
        if all(s not in used for s in triangle):
            used.update(triangle)
            selected.append(triangle)
            bonus += gain
    naive = coeff.get(0, 0) - sum(abs(a) for s, a in coeff.items() if s)
    return naive + bonus, selected


def independent_triangle_bound(clauses, prefix, proposed_triangles):
    """Rebuild rational Fourier spectrum *from original clauses* and validate.

    This intentionally does not call spectral_coefficients, triangle_bound or
    its packing algorithm. A producer-selected packing is the witness; the
    checker need not agree with its heuristics or maximize the lower bound.
    """
    amplitudes = independent_residual_coefficients(clauses, prefix)
    naive = amplitudes.get(0, Fraction(0)) - sum(
        (abs(a) for s, a in amplitudes.items() if s), Fraction(0))
    used = set()
    improvement = Fraction(0)
    if not isinstance(proposed_triangles, list):
        raise ValueError('triangles must be a list')
    for triangle in proposed_triangles:
        if (not isinstance(triangle, list) or len(triangle) != 3 or
                any(type(s) is not int or s <= 0 for s in triangle) or
                triangle != sorted(set(triangle))):
            raise ValueError('malformed triangle')
        s, t, u = triangle
        if s ^ t != u or any(a in used for a in triangle):
            raise ValueError('cycle identity violated or Fourier term reused')
        coeff = [amplitudes.get(a, Fraction(0)) for a in triangle]
        if coeff[0] * coeff[1] * coeff[2] <= 0:
            raise ValueError('triangle has no positive-phase frustration')
        improvement += 2 * min(map(abs, coeff))
        used.update(triangle)
    return naive + improvement


def verify_cycle_receipt(clauses, n, receipt):
    """Check a source-bound proof tree without trusting builder coefficients."""
    identity = formula_digest(clauses, n)
    if not isinstance(receipt, dict) or receipt.get('version') != VERSION or receipt.get('formula_sha256') != identity:
        raise ValueError('wrong version or source formula')

    def check(node, prefix):
        if not isinstance(node, dict):
            raise ValueError('malformed proof node')
        kind = node.get('kind')
        if kind == 'sat':
            bits = node.get('witness')
            if (not isinstance(bits, list) or len(bits) != n or
                    any(type(b) is not int or b not in (0, 1) for b in bits) or
                    any(bits[v] != b for v, b in prefix.items()) or
                    direct_energy(clauses, bits) != 0):
                raise ValueError('invalid SAT witness')
            return 'SAT'
        if kind == 'phase_cycle_bound':
            claimed = node.get('bound')
            if (not isinstance(claimed, list) or len(claimed) != 2 or
                    any(type(a) is not int for a in claimed) or claimed[1] <= 0):
                raise ValueError('invalid bound encoding')
            proved = independent_triangle_bound(clauses, prefix, node.get('triangles'))
            if proved <= 0 or claimed != as_ratio(proved):
                raise ValueError('false UNSAT phase-cycle bound')
            return 'UNSAT'
        if kind == 'split':
            variable = node.get('variable')
            if type(variable) is not int or not 0 <= variable < n or variable in prefix:
                raise ValueError('invalid split variable')
            prefix[variable] = 0
            zero = check(node.get('zero'), prefix)
            prefix[variable] = 1
            one = check(node.get('one'), prefix)
            del prefix[variable]
            return ('UNSAT' if zero == one == 'UNSAT' else 'SAT' if
                    'SAT' in (zero, one) else 'UNKNOWN')
        if kind == 'unknown' and node.get('reason') == 'budget':
            return 'UNKNOWN'
        raise ValueError('unsupported proof node')

    status = check(receipt.get('proof'), {})
    if status != receipt.get('result'):
        raise ValueError('claimed result does not follow from proof')
    return status


def produce_cycle_receipt(clauses, n, budget=256):
    """Bounded navigation using the strengthened, phase-sensitive lower bound."""
    validate_formula(clauses, n)
    if type(budget) is not int or budget < 1:
        raise ValueError('budget must be positive integer')
    coeff = spectral_coefficients(clauses)
    visits = 0
    cycle_leaves = 0

    def search(c, prefix):
        nonlocal visits, cycle_leaves
        visits += 1
        if visits > budget:
            return {'kind': 'unknown', 'reason': 'budget'}, 'UNKNOWN'
        lower, triangles = triangle_bound(c)
        if lower > 0:
            cycle_leaves += int(bool(triangles))
            return {'kind': 'phase_cycle_bound',
                    'bound': as_ratio(Fraction(lower, 8)),
                    'triangles': [list(t) for t in triangles]}, 'UNSAT'
        remaining = [i for i in range(n) if i not in prefix]
        if not remaining:
            bits = [prefix[i] for i in range(n)]
            if direct_energy(clauses, bits) == 0:
                return {'kind': 'sat', 'witness': bits}, 'SAT'
            raise AssertionError('positive full-state energy must be certified')

        probe, bits = dict(c), dict(prefix)
        for _ in remaining:
            candidates = [i for i in range(n) if i not in bits]
            i = max(candidates, key=lambda v: (abs(probe.get(1 << v, 0)), -v))
            b = int(probe.get(1 << i, 0) > 0)
            bits[i] = b
            probe = conditional_coefficients(probe, i, b)
        witness = [bits[i] for i in range(n)]
        if direct_energy(clauses, witness) == 0:
            return {'kind': 'sat', 'witness': witness}, 'SAT'

        variable = max(remaining, key=lambda i: (
            sum(abs(v) for mask, v in c.items() if mask & (1 << i)), -i))
        zero, status_zero = search(conditional_coefficients(c, variable, 0),
                                   {**prefix, variable: 0})
        if status_zero == 'SAT':
            return zero, 'SAT'
        one, status_one = search(conditional_coefficients(c, variable, 1),
                                 {**prefix, variable: 1})
        if status_one == 'SAT':
            return one, 'SAT'
        node = {'kind': 'split', 'variable': variable, 'zero': zero, 'one': one}
        status = ('UNSAT' if status_zero == status_one == 'UNSAT'
                  else 'UNKNOWN')
        return node, status

    proof, result = search(coeff, {})
    receipt = {'version': VERSION, 'formula_sha256': formula_digest(clauses, n),
               'result': result, 'proof': proof, 'producer_nodes_visited': visits,
               'producer_cycle_bound_leaves': cycle_leaves, 'producer_budget': budget}
    assert verify_cycle_receipt(clauses, n, receipt) == result
    return receipt