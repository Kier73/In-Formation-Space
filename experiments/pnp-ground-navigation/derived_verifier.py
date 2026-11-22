"""PNG-003 independent proof-replay verifier.

No import from the PNG-003 producer. Replays exact equivalence contractions,
resolution inference, source-ground reconstruction and independent PNG-002
finite-field/count verifier. No trust in producer claims or hashes alone.
"""
from __future__ import annotations

import json

from ground_verifier import check as check_ground, digest_ground, digest_source


def canonical(clauses, n):
    if type(n) is not int or n < 1:
        raise ValueError('n must be positive')
    output = set()
    for input_clause in clauses:
        literals = list(input_clause)
        if any(type(l) is not int or l == 0 or abs(l) > n for l in literals):
            raise ValueError('invalid literal')
        c = set(literals)
        if any(-l in c for l in c):
            continue
        output.add(tuple(sorted(c, key=lambda v: (abs(v), v < 0))))
    return output


def xor_clauses(mask, rhs, n, max_arity):
    if (type(mask) is not int or type(rhs) is not int or rhs not in (0, 1)
        or mask <= 0 or mask >= 1 << n or mask.bit_count() > max_arity):
        raise ValueError('bad derived XOR')
    indices = [i for i in range(n) if mask >> i & 1]
    return {tuple((-(i+1) if bits >> j & 1 else i+1)
                  for j, i in enumerate(indices))
            for bits in range(1 << len(indices)) if bits.bit_count() % 2 != rhs}


def tuple_clause(data, n):
    c = canonical([data], n)
    if len(c) != 1:
        raise ValueError('proof must contain one canonical non-tautological clause')
    out = next(iter(c))
    if tuple(data) != out:
        raise ValueError('proof clause non-canonical or duplicated')
    return out


def verify_receipt(receipt, *, max_enumerated_free=16,
                   max_proof_steps=50000):
    if receipt.get('format') != 'PNG-003-resolution-ground-v1':
        raise ValueError('wrong receipt format')
    n = receipt['n']
    original = canonical(receipt['original_clauses'], n)
    if original != set(map(tuple, receipt['original_clauses'])):
        raise ValueError('source clauses not normalized')
    if digest_source(receipt['original_clauses'], n) != receipt['source_sha256']:
        raise ValueError('source digest changed')
    state = set(original)
    steps = receipt['contract_steps']
    if len(steps) > max_proof_steps:
        raise ValueError('contraction proof too large for verifier')
    for step in steps:
        pivot = step['pivot']
        if type(pivot) is not int or not 1 <= pivot <= n:
            raise ValueError('invalid consensus pivot')
        pos = tuple_clause(step['positive'], n)
        neg = tuple_clause(step['negative'], n)
        child = tuple_clause(step['child'], n)
        if pos not in state or neg not in state or pivot not in pos or -pivot not in neg:
            raise ValueError('missing consensus parents')
        if set(pos) - {pivot} != set(neg) - {-pivot} or set(child) != set(pos) - {pivot}:
            raise ValueError('consensus rewrite not equivalent')
        state.remove(pos)
        state.remove(neg)
        state.add(child)
    terminal = canonical(receipt['terminal_clauses'], n)
    if state != terminal or terminal != set(map(tuple, receipt['terminal_clauses'])):
        raise ValueError('consensus replay differs from asserted terminal')

    base_rows = receipt['base_equations']
    learned = receipt['learned_equations']
    ground = receipt['ground']
    max_arity = ground.get('max_arity')
    if type(max_arity) is not int or not 1 <= max_arity <= 5:
        raise ValueError('invalid arity')
    if any(not isinstance(pair, (tuple, list)) or len(pair) != 2
           for pair in base_rows + learned):
        raise ValueError('bad row shape')
    base_reconstruction = canonical(receipt['base_residual'], n)
    for mask, rhs in base_rows:
        base_reconstruction.update(xor_clauses(mask, rhs, n, max_arity))
    if base_reconstruction != terminal:
        raise ValueError('base extraction not exactly equivalent')

    derived = set(terminal)
    derivations = receipt['resolution_steps']
    if len(derivations) > max_proof_steps:
        raise ValueError('resolution proof too large for verifier')
    for step in derivations:
        left = tuple_clause(step['left'], n)
        right = tuple_clause(step['right'], n)
        child = tuple_clause(step['child'], n)
        pivot = step['pivot']
        if type(pivot) is not int or pivot == 0 or abs(pivot) > n:
            raise ValueError('invalid resolution pivot')
        if left not in derived or right not in derived:
            raise ValueError('resolution parent unavailable')
        if pivot not in left or -pivot not in right:
            raise ValueError('resolution pivot not complementary')
        resolvent = set(left) - {pivot} | (set(right) - {-pivot})
        if any(-v in resolvent for v in resolvent) or resolvent != set(child):
            raise ValueError('invalid resolution inference')
        derived.add(child)
    for mask, rhs in learned:
        if not xor_clauses(mask, rhs, n, max_arity).issubset(derived):
            raise ValueError('claimed nonlocal XOR lacks resolution derivations')
    if receipt['resolution_empty'] and () not in derived:
        raise ValueError('missing empty-clause resolution refutation')

    augmented = set(canonical(receipt['base_residual'], n))
    for mask, rhs in base_rows + learned:
        augmented.update(xor_clauses(mask, rhs, n, max_arity))
    if receipt['resolution_empty']:
        augmented.add(())
    canonical_augmented = sorted(augmented, key=lambda c: (len(c), tuple((abs(v),v<0) for v in c)))
    if digest_source(canonical_augmented, n) != receipt['augmented_sha256']:
        raise ValueError('augmented ground digest changed')
    if digest_ground(ground) != receipt['ground_sha256']:
        raise ValueError('ground digest changed')
    audit = check_ground(canonical_augmented, n, ground, receipt['result'],
                         max_enumerated_free=max_enumerated_free,
                         source_digest=receipt['augmented_sha256'],
                         ground_digest=receipt['ground_sha256'])
    if receipt['result']['witness'] is not None:
        witness = {int(k):v for k,v in receipt['result']['witness'].items()}
        if len(witness) != n or set(witness) != set(range(1,n+1)):
            raise ValueError('witness incomplete')
        if not all(any(witness[abs(v)] == int(v>0) for v in clause)
                   for clause in original):
            raise ValueError('source witness invalid')
    return {**audit, 'source_rewrite_verified': True, 'resolution_verified': True,
            'exact_source_equivalence_verified': True,
            'contractions_checked': len(steps), 'resolution_steps_checked':len(derivations),
            'independent_original_source_digest':digest_source(receipt['original_clauses'],n)}


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('receipt')
    args=p.parse_args()
    with open(args.receipt,encoding='utf8') as h:
        receipt=json.load(h)
    print(json.dumps(verify_receipt(receipt),indent=2))
