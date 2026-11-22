#!/usr/bin/env python3
"""SPN-004: parity-rank-bounded Walsh block certificates for width-three SAT.

Exact block minimum uses 2^r sign states, where r is rank over GF(2) of
selected Fourier supports. This avoids enumeration over all n variables for
one block. Packing disjoint *Fourier terms* gives a sound UNSAT lower bound,
though finding a good partition and the residual proof search can be hard.
"""
from __future__ import annotations

from fractions import Fraction
from phase_cycle_bounds import find_positive_triangles, triangle_bound
from spectral_receipts import (validate_formula, formula_digest, direct_energy,
                               independent_residual_coefficients, as_ratio)
from walsh_phase_navigation_probe import (spectral_coefficients,
                                          conditional_coefficients)

VERSION = 'SPN-004-v1'


def parity_basis(masks):
    """Deterministic XOR-echelon basis, ordered by descending pivot bit."""
    pivots = {}
    for s in sorted(set(masks)):
        if type(s) is not int or s <= 0:
            raise ValueError('basis requires positive integer masks')
        v = s
        while v:
            p = v.bit_length() - 1
            if p not in pivots:
                pivots[p] = v
                break
            v ^= pivots[p]
    return tuple(pivots[p] for p in sorted(pivots, reverse=True))


def parity_coordinates(mask, basis):
    remainder, coordinates = mask, 0
    for index, vector in enumerate(basis):
        pivot = 1 << (vector.bit_length() - 1)
        if remainder & pivot:
            remainder ^= vector
            coordinates |= 1 << index
    if remainder:
        raise ValueError('mask outside selected parity span')
    return coordinates


def exact_block_minimum(coeff, masks):
    """Min sum a[S]*chi_S over all assignments, in coefficient units.

    The rank-r parity map is onto {0,1}^r, even when the supports use
    thousands of original variable indices. Intermediate arithmetic is exact.
    """
    if not masks or len(set(masks)) != len(masks):
        raise ValueError('nonempty block with distinct supports required')
    basis = parity_basis(masks)
    positions = [parity_coordinates(s, basis) for s in masks]
    best = None
    for parity_bits in range(1 << len(basis)):
        value = sum(coeff[s] * (-1 if ((parity_bits & pos).bit_count() & 1) else 1)
                    for s, pos in zip(masks, positions))
        if best is None or value < best:
            best = value
    return best, len(basis)



def lift_parity_ground(basis, parity_bits, n):
    """Construct one n-bit x with basis parity(x) = parity_bits.

    Independent equations are consistent for every parity coordinate. Free
    variables are set to zero; GF(2) elimination builds a concrete witness.
    """
    if type(n) is not int or n < 0 or parity_bits < 0 or parity_bits >= 1 << len(basis):
        raise ValueError('invalid parity-coordinate target')
    rows = {}
    for i, mask in enumerate(basis):
        if mask <= 0 or mask.bit_length() > n:
            raise ValueError('basis outside declared original variable domain')
        row, bit = mask, (parity_bits >> i) & 1
        while row:
            p = row.bit_length() - 1
            if p not in rows:
                rows[p] = (row, bit)
                break
            previous_row, previous_bit = rows[p]
            row ^= previous_row
            bit ^= previous_bit
        else:
            if bit:
                raise ValueError('dependent parity target inconsistent')
    witness = 0
    for p in sorted(rows):
        row, bit = rows[p]
        if bit ^ ((row & witness).bit_count() & 1):
            witness |= 1 << p
    if any(((mask & witness).bit_count() & 1) != ((parity_bits >> i) & 1)
           for i, mask in enumerate(basis)):
        raise AssertionError('GF(2) witness reconstruction violated a requested parity')
    return witness


def exact_rank_ground(coeff, n, rank_budget=12):
    """Complete optimization when the FULL signed support has small GF2 rank.

    Return (minimum in coefficient units, full-bitmask witness, rank).
    This is fixed-parameter in rank, NOT a polynomial algorithm for arbitrary
    SAT, and it assumes all coefficients have already been constructed.
    """
    if type(rank_budget) is not int or not 0 <= rank_budget <= 16:
        raise ValueError('rank budget must lie in 0..16')
    supports = sorted(s for s, a in coeff.items() if s and a)
    if any(s.bit_length() > n for s in supports):
        raise ValueError('Fourier support outside declared domain')
    basis = parity_basis(supports)
    rank = len(basis)
    if rank > rank_budget:
        raise ValueError('full Fourier rank exceeds declared budget')
    coords = [parity_coordinates(s, basis) for s in supports]
    best, best_bits = None, None
    for bits in range(1 << rank):
        value = coeff.get(0, 0) + sum(
            coeff[s] * (-1 if ((bits & position).bit_count() & 1) else 1)
            for s, position in zip(supports, coords))
        if best is None or value < best:
            best, best_bits = value, bits
    x = lift_parity_ground(basis, best_bits, n)
    actual = sum(a * (-1 if ((s & x).bit_count() & 1) else 1)
                 for s, a in coeff.items())
    if actual != best:
        raise AssertionError('ground-coordinate reconstruction mismatch')
    return best, x, rank

def block_candidates(coeff, clauses, max_rank=3):
    """Heuristic: rank-2 cycles + clause-local rank-3 closures.

    Each candidate is made of nonzero current Fourier terms. Supports may
    share original variables with other candidates; selected TERM groups may
    not overlap. This discovers an exact local quotient but not an optimal
    global partition, and does not discover arbitrary nonlocal rank-3 blocks.
    """
    nonzero = sorted(s for s, a in coeff.items() if s and a)
    seen = set()
    for _, cycle in find_positive_triangles(coeff):
        seen.add(cycle)
    if max_rank >= 3:
        for vs, _ in clauses:
            union = sum(1 << v for v in vs)
            group = tuple(s for s in nonzero if s & ~union == 0)
            if len(group) >= 3:
                seen.add(group)
    candidates = []
    for masks in seen:
        if len(parity_basis(masks)) > max_rank:
            continue
        minimum, rank = exact_block_minimum(coeff, masks)
        naive = -sum(abs(coeff[s]) for s in masks)
        gain = minimum - naive
        if gain > 0:
            candidates.append((gain, rank, masks))
    return sorted(candidates, key=lambda row: (-row[0], row[1], row[2]))


def rank_block_bound(coeff, clauses, max_rank=3):
    """Exact lower-bound numerator /8 and a greedy disjoint-term packing."""
    if type(max_rank) is not int or max_rank not in (2, 3):
        raise ValueError('this experimental producer supports rank caps 2 and 3')
    used = set()
    selected = []
    bonus = 0
    for gain, rank, masks in block_candidates(coeff, clauses, max_rank):
        if all(s not in used for s in masks):
            selected.append(masks)
            used.update(masks)
            bonus += gain
    naive = coeff.get(0, 0) - sum(abs(a) for s, a in coeff.items() if s)
    result = naive + bonus
    # A greedy rank-3 block can consume terms that make two rank-2 cycles
    # mutually compatible. Retain the stronger of the two certified packings.
    cycle_result, cycle_packing = triangle_bound(coeff)
    if cycle_result > result:
        return cycle_result, cycle_packing
    return result, selected


def independent_rank_block_bound(clauses, prefix, proposed_blocks, rank_cap):
    """Recompute rational source Fourier coefficients; check each block min."""
    if type(rank_cap) is not int or rank_cap not in (2, 3):
        raise ValueError('unsupported verifier rank cap')
    if not isinstance(proposed_blocks, list):
        raise ValueError('blocks must be a list')
    coeff = independent_residual_coefficients(clauses, prefix)
    total = coeff.get(0, Fraction()) - sum(
        (abs(v) for s, v in coeff.items() if s), Fraction())
    used = set()
    for block in proposed_blocks:
        if (not isinstance(block, list) or len(block) < 3 or
                any(type(s) is not int or s <= 0 for s in block) or
                block != sorted(set(block))):
            raise ValueError('noncanonical or invalid Fourier block')
        if any(s in used for s in block):
            raise ValueError('Fourier term reused between proof blocks')
        if any(coeff.get(s, Fraction()) == 0 for s in block):
            raise ValueError('block contains a missing or zero term')
        minimum, rank = exact_block_minimum(coeff, block)
        if rank > rank_cap:
            raise ValueError('declared block rank exceeds certificate budget')
        improvement = minimum + sum(abs(coeff[s]) for s in block)
        if improvement < 0:
            raise AssertionError('algebraic block min cannot be below termwise bound')
        total += improvement
        used.update(block)
    return total


def verify_rank_receipt(clauses, n, receipt):
    source_digest = formula_digest(clauses, n)
    if not isinstance(receipt, dict) or receipt.get('version') != VERSION or receipt.get('formula_sha256') != source_digest:
        raise ValueError('wrong receipt version or source formula')
    rank_cap = receipt.get('rank_cap')
    if type(rank_cap) is not int or rank_cap not in (2, 3):
        raise ValueError('unsupported rank cap')

    def check(node, prefix):
        if not isinstance(node, dict):
            raise ValueError('invalid proof node')
        kind = node.get('kind')
        if kind == 'sat':
            witness = node.get('witness')
            if (not isinstance(witness, list) or len(witness) != n or
                    any(type(b) is not int or b not in (0, 1) for b in witness) or
                    any(witness[v] != b for v, b in prefix.items()) or
                    direct_energy(clauses, witness) != 0):
                raise ValueError('invalid SAT witness')
            return 'SAT'
        if kind == 'rank_block_bound':
            bound = node.get('bound')
            if (not isinstance(bound, list) or len(bound) != 2 or
                    any(type(q) is not int for q in bound) or bound[1] <= 0):
                raise ValueError('invalid rational bound encoding')
            certified = independent_rank_block_bound(
                clauses, prefix, node.get('blocks'), rank_cap)
            if certified <= 0 or as_ratio(certified) != bound:
                raise ValueError('forged or insufficient UNSAT block bound')
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
            return 'UNSAT' if zero == one == 'UNSAT' else 'SAT' if 'SAT' in (zero, one) else 'UNKNOWN'
        if kind == 'unknown' and node.get('reason') == 'budget':
            return 'UNKNOWN'
        raise ValueError('unsupported proof node')

    result = check(receipt.get('proof'), {})
    if result != receipt.get('result'):
        raise ValueError('conclusion is not entailed by provided proof tree')
    return result


def produce_rank_receipt(clauses, n, budget=256, rank_cap=3):
    validate_formula(clauses, n)
    if type(budget) is not int or budget < 1:
        raise ValueError('budget must be a positive integer')
    if type(rank_cap) is not int or rank_cap not in (2, 3):
        raise ValueError('rank_cap must be 2 or 3')
    visits = 0
    block_leaves = 0

    def search(c, prefix):
        nonlocal visits, block_leaves
        visits += 1
        if visits > budget:
            return {'kind': 'unknown', 'reason': 'budget'}, 'UNKNOWN'
        lower, blocks = rank_block_bound(c, clauses, rank_cap)
        if lower > 0:
            block_leaves += 1
            return {'kind': 'rank_block_bound', 'bound': as_ratio(Fraction(lower, 8)),
                    'blocks': [list(b) for b in blocks]}, 'UNSAT'
        remaining = [i for i in range(n) if i not in prefix]
        if not remaining:
            bits = [prefix[i] for i in range(n)]
            if direct_energy(clauses, bits) == 0:
                return {'kind': 'sat', 'witness': bits}, 'SAT'
            raise AssertionError('full nonzero assignment should have positive bound')

        probe, bits = dict(c), dict(prefix)
        for _ in remaining:
            choices = [i for i in range(n) if i not in bits]
            v = max(choices, key=lambda i: (abs(probe.get(1 << i, 0)), -i))
            b = int(probe.get(1 << v, 0) > 0)
            bits[v] = b
            probe = conditional_coefficients(probe, v, b)
        witness = [bits[i] for i in range(n)]
        if direct_energy(clauses, witness) == 0:
            return {'kind': 'sat', 'witness': witness}, 'SAT'

        variable = max(remaining, key=lambda i: (
            sum(abs(a) for s, a in c.items() if s & (1 << i)), -i))
        zero, st0 = search(conditional_coefficients(c, variable, 0),
                            {**prefix, variable: 0})
        if st0 == 'SAT':
            return zero, 'SAT'
        one, st1 = search(conditional_coefficients(c, variable, 1),
                           {**prefix, variable: 1})
        if st1 == 'SAT':
            return one, 'SAT'
        return ({'kind': 'split', 'variable': variable, 'zero': zero, 'one': one},
                'UNSAT' if st0 == st1 == 'UNSAT' else 'UNKNOWN')

    proof, result = search(spectral_coefficients(clauses), {})
    receipt = {'version': VERSION, 'formula_sha256': formula_digest(clauses, n),
               'rank_cap': rank_cap, 'result': result, 'proof': proof,
               'producer_nodes_visited': visits, 'producer_bound_leaves': block_leaves,
               'producer_budget': budget}
    assert verify_rank_receipt(clauses, n, receipt) == result
    return receipt