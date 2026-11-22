"""PNG-002 independent, zero-dependency CNF/XOR ground receipt verifier.

This module deliberately does not import the producer, its row reducer,
its CNF parser, or its reduced-space search. It reconstructs the original
CNF from complete parity encodings, checks independent XOR-linear algebra,
and optionally checks model counts by enumerating only the free coordinates.
"""
from __future__ import annotations

import hashlib
import json


def _canonical(clauses, n):
    found = set()
    for clause in clauses:
        literals = list(clause)
        if any(type(lit) is not int or lit == 0 or abs(lit) > n for lit in literals):
            raise ValueError('invalid literal')
        literal_set = frozenset(literals)
        if any(-v in literal_set for v in literal_set):
            continue
        found.add(tuple(sorted(literal_set, key=lambda v: (abs(v), v < 0))))
    return sorted(found, key=lambda c: (len(c), tuple((abs(x), x < 0) for x in c)))


def digest_source(clauses, n):
    canonical = _canonical(clauses, n)
    return hashlib.sha256(json.dumps([n, canonical], separators=(',', ':')).encode()).hexdigest()


def digest_ground(ground):
    return hashlib.sha256(json.dumps(
        [ground['n'], ground['max_arity'],
         [list(pair) for pair in ground['equations']], ground['residual']],
        separators=(',', ':')).encode()).hexdigest()


def _xor_as_cnf(mask, bit):
    indices = [i for i in range(mask.bit_length()) if mask & (1 << i)]
    clauses = []
    for assignment in range(1 << len(indices)):
        if assignment.bit_count() % 2 == bit:
            continue
        clause = tuple(-i - 1 if (assignment >> offset) & 1 else i + 1
                       for offset, i in enumerate(indices))
        clauses.append(clause)
    return clauses


def _satisfies(clauses, bits):
    for clause in clauses:
        if not any(((bits >> (abs(lit) - 1)) & 1) == int(lit > 0)
                   for lit in clause):
            return False
    return True


def _basis(equations, n):
    """Independent highest-pivot incremental XOR basis, not Gauss-Jordan."""
    basis = {}
    contradiction = None
    for mask, rhs in equations:
        while mask:
            pivot = mask.bit_length() - 1
            if pivot in basis:
                m, r = basis[pivot]
                mask ^= m
                rhs ^= r
            else:
                basis[pivot] = (mask, rhs)
                break
        else:
            if rhs:
                contradiction = True
    return basis, contradiction is not None


def _expand(basis, free, z):
    bits = sum(1 << j for i, j in enumerate(free) if (z >> i) & 1)
    for pivot in sorted(basis):
        mask, rhs = basis[pivot]
        value = rhs ^ ((mask & bits).bit_count() & 1)
        if value:
            bits |= 1 << pivot
    return bits


def check(clauses, n, ground, result, *, max_enumerated_free=16,
          source_digest=None, ground_digest=None):
    """Return a verification report or raise ValueError for invalid receipts.

    An unverified #SAT count is flagged as such, never silently accepted.
    A witnessed YES decision can be verified without counting all solutions.
    A verified 0=1 XOR combination independently proves UNSAT for the source.
    """
    if type(n) is not int or n <= 0:
        raise ValueError('invalid n')
    canonical = _canonical(clauses, n)
    if ground.get('n') != n or type(ground.get('max_arity')) is not int or not 1 <= ground['max_arity'] <= 5:
        raise ValueError('ground scope invalid')
    eqs = ground.get('equations')
    residual = ground.get('residual')
    if not isinstance(eqs, list) or not isinstance(residual, list):
        raise ValueError('missing ground relations')
    reconstructed = set(_canonical(residual, n))
    for row in eqs:
        if (len(row) != 2 or type(row[0]) is not int or type(row[1]) is not int or
                row[1] not in (0, 1) or not 0 < row[0] < 1 << n or
                row[0].bit_count() > ground['max_arity']):
            raise ValueError('invalid lifted equation')
        reconstructed.update(_canonical(_xor_as_cnf(row[0], row[1]), n))
    if reconstructed != set(canonical):
        raise ValueError('ground is not exactly equivalent to the source CNF')
    actual_source_digest = digest_source(clauses, n)
    actual_ground_digest = digest_ground(ground)
    if source_digest is not None and actual_source_digest != source_digest:
        raise ValueError('source digest mismatch')
    if ground_digest is not None and actual_ground_digest != ground_digest:
        raise ValueError('ground digest mismatch')
    basis, contradiction = _basis(eqs, n)
    rank = len(basis)
    if rank != result['ledger']['rank']:
        raise ValueError('false claimed rank')
    if result['ledger'].get('free_dimension') != n-rank:
        raise ValueError('false claimed free dimension')
    reported_count = result.get('count')
    status = result['status']
    witness = result.get('witness')
    if status not in ('sat', 'unsat', 'undetermined'):
        raise ValueError('unknown status')
    if status == 'undetermined':
        if reported_count is not None or witness is not None:
            raise ValueError('undetermined state cannot include claimed result')
        return {'compilation_verified': True, 'count_verified': False,
                'decision_verified': False, 'reason': 'budgeted-undetermined',
                'independent_rank': rank, 'source_digest': actual_source_digest,
                'ground_digest': actual_ground_digest}
    if type(reported_count) is not int or reported_count < 0:
        raise ValueError('invalid count')
    if (status == 'sat') != (reported_count > 0):
        raise ValueError('inconsistent solution-count status')
    witness_verified = False
    if witness is not None:
        normalized_witness = {int(k): v for k, v in witness.items()}
        if (set(normalized_witness) != set(range(1,n+1)) or
                any(type(v) is not int or v not in (0, 1) for v in normalized_witness.values())):
            raise ValueError('invalid model witness')
        assignment_bits = sum(v << (k-1) for k, v in normalized_witness.items())
        if not _satisfies(canonical, assignment_bits):
            raise ValueError('invalid original-CNF witness')
        witness_verified = True
    if status == 'sat' and not witness_verified:
        raise ValueError('a satisfiable claim needs a witness')
    if status == 'unsat' and witness is not None:
        raise ValueError('UNSAT cannot have a witness')
    ref = result.get('refutation_equation_indices')
    refutation_verified = False
    if ref is not None:
        if (type(ref) is not list or not ref or
                any(type(i) is not int or not 0 <= i < len(eqs) for i in ref) or
                len(set(ref)) != len(ref)):
            raise ValueError('bad refutation indices')
        mask = rhs = 0
        for i in ref:
            mask ^= eqs[i][0]
            rhs ^= eqs[i][1]
        if mask != 0 or rhs != 1:
            raise ValueError('refutation does not derive 0=1')
        refutation_verified = True
    if contradiction:
        if reported_count != 0 or not refutation_verified:
            raise ValueError('XOR-inconsistent source requires a verified contradiction')
        return {'compilation_verified': True, 'decision_verified': True,
                'count_verified': True, 'refutation_verified': True,
                'independent_rank': rank, 'source_digest': actual_source_digest,
                'ground_digest': actual_ground_digest}
    if refutation_verified:
        raise ValueError('refutation cannot exist for a consistent XOR system')
    free = [v for v in range(n) if v not in basis]
    if len(free) <= max_enumerated_free:
        independent_count = 0
        for z in range(1 << len(free)):
            bits = _expand(basis, free, z)
            if not _satisfies(canonical, bits):
                continue
            independent_count += 1
        if independent_count != reported_count:
            raise ValueError('independently enumerated count differs')
        return {'compilation_verified': True, 'decision_verified': True,
                'count_verified': True, 'refutation_verified': False,
                'enumerated_coordinates': 1 << len(free),
                'independent_rank': rank, 'source_digest': actual_source_digest,
                'ground_digest': actual_ground_digest}
    if not residual:
        if reported_count != (1 << len(free)):
            raise ValueError('affine rank count differs')
        return {'compilation_verified': True, 'decision_verified': True,
                'count_verified': True, 'refutation_verified': False,
                'independent_rank': rank, 'source_digest': actual_source_digest,
                'ground_digest': actual_ground_digest}
    if () in canonical and reported_count == 0:
        return {'compilation_verified': True, 'decision_verified': True,
                'count_verified': True, 'refutation_verified': False,
                'independent_rank': rank, 'source_digest': actual_source_digest,
                'ground_digest': actual_ground_digest}
    return {'compilation_verified': True, 'decision_verified': witness_verified,
            'count_verified': False, 'reason': 'free-coordinate verification-budget',
            'independent_rank': rank, 'source_digest': actual_source_digest,
            'ground_digest': actual_ground_digest}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Independently verify a PNG-002 receipt')
    parser.add_argument('receipt')
    args = parser.parse_args()
    with open(args.receipt, encoding='utf8') as f:
        receipt = json.load(f)
    print(json.dumps(check(receipt['clauses'], receipt['n'], receipt['ground'],
                           receipt['result'], source_digest=receipt['source_sha256'],
                           ground_digest=receipt['ground_sha256']), indent=2))
