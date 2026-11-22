#!/usr/bin/env python3
"""SPN-002: exact Walsh restrictions with independently checkable SAT receipts.

Builder uses the fixed-width integer Walsh representation from SPN-001.
Verifier starts from original clauses and builds independent rational residual
coefficients; only original clauses, simple integers, and fractions are trusted.
This is a bounded decision procedure, NOT a polynomial-time SAT algorithm.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
import json

from walsh_phase_navigation_probe import (spectral_coefficients,
                                          conditional_coefficients)

VERSION = 'SPN-002-v1'


def validate_formula(clauses, n):
    if not isinstance(n, int) or n < 3:
        raise ValueError('n must be an integer >= 3')
    for variables, forbidden in clauses:
        if (len(variables) != 3 or len(forbidden) != 3 or
            any(not isinstance(v, int) or v < 0 or v >= n for v in variables) or
            len(set(variables)) != 3 or
            any(b not in (0, 1) for b in forbidden)):
            raise ValueError('each clause requires three distinct valid variables and bits')


def formula_digest(clauses, n):
    validate_formula(clauses, n)
    canonical = {'n': n, 'clauses': [[list(v), list(b)] for v, b in clauses]}
    return sha256(json.dumps(canonical, sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


def direct_energy(clauses, bits):
    """Clause-by-clause evaluator; does not use the Fourier engine."""
    return sum(all(bits[v] == b for v, b in zip(vs, forb))
               for vs, forb in clauses)


def independent_residual_coefficients(clauses, prefix):
    """Re-expand restricted original clauses into rational characters.

    This intentionally DOES NOT call spectral_coefficients or restriction.
    A falsified fixed literal remains, a satisfied literal drops its clause.
    """
    coeff = defaultdict(Fraction)
    for variables, forbidden in clauses:
        if any(v in prefix and prefix[v] != b for v, b in zip(variables, forbidden)):
            continue
        rest = [(v, b) for v, b in zip(variables, forbidden) if v not in prefix]
        scale = Fraction(1, 1 << len(rest))
        for selector in range(1 << len(rest)):
            mask, sign = 0, 1
            for i, (variable, forbidden_bit) in enumerate(rest):
                if (selector >> i) & 1:
                    mask |= 1 << variable
                    if forbidden_bit:
                        sign = -sign
            coeff[mask] += scale * sign
    return dict(coeff)


def independent_lower_bound(clauses, prefix):
    coeff = independent_residual_coefficients(clauses, prefix)
    return coeff.get(0, Fraction(0)) - sum(
        (abs(value) for key, value in coeff.items() if key), Fraction(0))


def as_ratio(q):
    return [q.numerator, q.denominator]


def verify_receipt(clauses, n, receipt):
    """Return independently established SAT/UNSAT/UNKNOWN or reject a forgery.

    A SAT node carries a full witness. An UNSAT node either provides a strictly
    positive Fourier lower bound or branches over both values of a free bit.
    UNKNOWN is never silently treated as UNSAT.
    """
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
        if kind == 'positive_lower_bound':
            bound = node.get('bound')
            if (not isinstance(bound, list) or len(bound) != 2 or
                any(type(x) is not int for x in bound) or bound[1] <= 0):
                raise ValueError('invalid bound encoding')
            proved = independent_lower_bound(clauses, prefix)
            if proved <= 0 or bound != as_ratio(proved):
                raise ValueError('invalid UNSAT lower-bound claim')
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
            if zero == 'UNSAT' and one == 'UNSAT':
                return 'UNSAT'
            if zero == 'SAT' or one == 'SAT':
                return 'SAT'
            return 'UNKNOWN'
        if kind == 'unknown' and node.get('reason') == 'budget':
            return 'UNKNOWN'
        raise ValueError('unsupported proof node')

    status = check(receipt.get('proof'), {})
    if status != receipt.get('result'):
        raise ValueError('claimed result does not follow from proof')
    return status


def produce_receipt(clauses, n, budget=256):
    """Bounded proof search; UNKNOWN is the only possible budget refusal.

    Every leaf is checked against the original CNF by verify_receipt.
    Source construction and certificates require O(m*2^k) arithmetic per node
    for fixed clause width k; tree size can still be exponential in n.
    """
    validate_formula(clauses, n)
    if type(budget) is not int or budget < 1:
        raise ValueError('budget must be positive integer')
    root = spectral_coefficients(clauses)
    visits = 0

    def search(c, prefix):
        nonlocal visits
        visits += 1
        if visits > budget:
            return {'kind': 'unknown', 'reason': 'budget'}, 'UNKNOWN'

        # Restriction is maintained by the builder. The independent checker
        # obtains the same bound from original clauses in its own arithmetic.
        lower = Fraction(c.get(0, 0) - sum(abs(value) for mask, value in c.items() if mask), 8)
        if lower > 0:
            return {'kind': 'positive_lower_bound', 'bound': as_ratio(lower)}, 'UNSAT'

        remaining = [i for i in range(n) if i not in prefix]
        if not remaining:
            bits = [prefix[i] for i in range(n)]
            if direct_energy(clauses, bits) == 0:
                return {'kind': 'sat', 'witness': bits}, 'SAT'
            # For a full assignment, all non-constant coefficients vanished,
            # and the bound would have been >0 above.
            raise AssertionError('positive full-state energy must be certified')

        # First attempt a phase-preserving conditional-mean descent to an
        # explicit witness. Failure does NOT imply UNSAT.
        probe = dict(c)
        bits = dict(prefix)
        for _ in remaining:
            candidates = [i for i in range(n) if i not in bits]
            i = max(candidates, key=lambda v: (abs(probe.get(1 << v, 0)), -v))
            b = int(probe.get(1 << i, 0) > 0)
            bits[i] = b
            probe = conditional_coefficients(probe, i, b)
        witness = [bits[i] for i in range(n)]
        if direct_energy(clauses, witness) == 0:
            return {'kind': 'sat', 'witness': witness}, 'SAT'

        # Expose the most strongly involved remaining variable when the
        # direct navigator fails. This branching rule is a heuristic only.
        variable = max(remaining, key=lambda i: (
            sum(abs(v) for mask, v in c.items() if mask & (1 << i)), -i))
        zero, zero_status = search(conditional_coefficients(c, variable, 0),
                                   {**prefix, variable: 0})
        if zero_status == 'SAT':
            return zero, 'SAT'
        one, one_status = search(conditional_coefficients(c, variable, 1),
                                 {**prefix, variable: 1})
        if one_status == 'SAT':
            return one, 'SAT'
        node = {'kind': 'split', 'variable': variable, 'zero': zero, 'one': one}
        if zero_status == one_status == 'UNSAT':
            return node, 'UNSAT'
        return node, 'UNKNOWN'

    proof, result = search(root, {})
    receipt = {'version': VERSION, 'formula_sha256': formula_digest(clauses, n),
               'result': result, 'proof': proof, 'producer_nodes_visited': visits,
               'producer_budget': budget}
    assert verify_receipt(clauses, n, receipt) == result
    return receipt


if __name__ == '__main__':
    from walsh_phase_navigation_probe import clauses_from_energy_profile
    for profile in ([0, 1, 1, 2, 1, 2, 2, 1],
                    [1, 1, 1, 1, 1, 1, 1, 3]):
        cls = clauses_from_energy_profile(profile)
        print(json.dumps(produce_receipt(cls, 3, budget=32), sort_keys=True))