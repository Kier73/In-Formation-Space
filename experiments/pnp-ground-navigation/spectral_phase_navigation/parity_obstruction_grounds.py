#!/usr/bin/env python3
"""SPN-006: proof-carrying XOR-inconsistent Fourier-term circuits.

For nonzero a_S chi_S, simultaneous termwise minimization wants
  <S,x>_2 = 1 if a_S>0 else 0.
An inconsistent GF(2) linear subsystem provides a subset C with
  XOR_{S in C} S = 0  and  XOR_{S in C} [a_S>0] = 1.
It forces at least one term in C to be +|a_S| instead of -|a_S|;
therefore gain 2 min(|a_S|) is sound. Greedy disjoint circuits add.
This is standard GF(2) linear algebra / parity frustration, not a novel
polynomial-time decision procedure for SAT.
"""
from __future__ import annotations

from fractions import Fraction
from spectral_receipts import (as_ratio, direct_energy, formula_digest,
    independent_residual_coefficients, validate_formula)
from rank_block_bounds import rank_block_bound, independent_rank_block_bound
from walsh_phase_navigation_probe import spectral_coefficients, conditional_coefficients

VERSION = 'SPN-006-v1'


def first_inconsistent_circuit(coeff):
    """Find a dependency with inconsistent preferred signs using GF(2) rows.

    Deterministic descending-amplitude order. A row stores (support, RHS,
    expression over previously processed *input Fourier-term indices*).
    Complexity: O(t * n) big-int XORs in the basic elimination, excluding
    Python integer bit costs; certificate size may be O(t).
    """
    keys = sorted((s for s, a in coeff.items() if s and a),
                  key=lambda s: (-abs(coeff[s]), s))
    pivots = {}
    reductions = 0
    for index, support in enumerate(keys):
        residue = support
        desired = int(coeff[support] > 0)
        expression = 1 << index
        while residue:
            pivot = residue.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (residue, desired, expression)
                break
            row, bit, used = pivots[pivot]
            residue ^= row
            desired ^= bit
            expression ^= used
            reductions += 1
        if residue == 0 and desired:
            circuit = tuple(sorted(keys[j] for j in range(len(keys))
                                   if expression & (1 << j)))
            assert len(circuit) >= 3
            assert all(coeff[s] for s in circuit)
            assert xor_masks(circuit) == 0
            assert sum(int(coeff[s] > 0) for s in circuit) % 2 == 1
            return circuit, reductions, len(pivots)
    return None, reductions, len(pivots)


def xor_masks(masks):
    value = 0
    for mask in masks:
        value ^= mask
    return value


def compatible_preference_ground(coeff, n):
    """Construct an exact global minimizer when ALL termwise signs agree.

    Return (assignment_mask, exact_minimum_in_coeff_units, parity_rank),
    or (None, triangle_lower_bound, rank) when sign preferences conflict.
    This uses GF(2) elimination, not 2^rank state enumeration. Caller must
    still account for Fourier construction and independently verify claims.
    """
    if type(n) is not int or n < 0:
        raise ValueError('n must be nonnegative integer')
    pivots = {}
    keys = sorted((s for s,a in coeff.items() if s and a),
                  key=lambda s:(-abs(coeff[s]),s))
    if any(s.bit_length() > n for s in keys):
        raise ValueError('spectral support outside declared variable domain')
    lower = coeff.get(0,0) - sum(abs(coeff[s]) for s in keys)
    for s in keys:
        residue = s
        desired = int(coeff[s] > 0)
        while residue:
            pivot = residue.bit_length()-1
            if pivot not in pivots:
                pivots[pivot] = residue, desired
                break
            row, bit = pivots[pivot]
            residue ^= row
            desired ^= bit
        if residue == 0 and desired:
            return None, lower, len(pivots)
    x = 0
    for pivot,(row,bit) in sorted(pivots.items()):
        if bit ^ ((row & x).bit_count() & 1):
            x |= 1 << pivot
    if any(((s & x).bit_count() & 1) != int(coeff[s] > 0) for s in keys):
        raise AssertionError('reconstructed solution does not satisfy parity equations')
    actual = sum(a * (-1 if (s & x).bit_count() & 1 else 1)
                 for s,a in coeff.items())
    if actual != lower:
        raise AssertionError('termwise minimum not attained')
    return x, lower, len(pivots)


def obstruction_bound(coeff):
    """Return coefficient-unit lower bound, disjoint circuits, and ledger."""
    available = {s: a for s, a in coeff.items() if s and a}
    selected = []
    bonus = 0
    total_reductions = 0
    rank_peak = 0
    while available:
        circuit, reductions, rank = first_inconsistent_circuit(available)
        total_reductions += reductions
        rank_peak = max(rank_peak, rank)
        if circuit is None:
            break
        selected.append(circuit)
        bonus += 2 * min(abs(available[s]) for s in circuit)
        for s in circuit:
            del available[s]
    basic = coeff.get(0, 0) - sum(abs(a) for s, a in coeff.items() if s)
    return basic + bonus, selected, {'circuit_count':len(selected),
        'circuit_terms':sum(map(len,selected)),
        'gaussian_row_reductions':total_reductions,
        'max_active_rank':rank_peak}


def independent_obstruction_bound(clauses, prefix, proposed_circuits):
    """Check only algebraic parity obligations against source-derived fractions."""
    if not isinstance(proposed_circuits, list):
        raise ValueError('circuits must be a list')
    coeff = independent_residual_coefficients(clauses, prefix)
    lower = coeff.get(0, Fraction()) - sum(
        (abs(a) for s, a in coeff.items() if s), Fraction())
    used = set()
    for circuit in proposed_circuits:
        if (not isinstance(circuit, list) or len(circuit) < 3 or
            any(type(s) is not int or s <= 0 for s in circuit) or
            circuit != sorted(set(circuit))):
            raise ValueError('invalid or noncanonical parity circuit')
        if any(s in used for s in circuit):
            raise ValueError('Fourier term used by more than one circuit')
        if any(coeff.get(s, Fraction()) == 0 for s in circuit):
            raise ValueError('missing or zero spectral term')
        if xor_masks(circuit) != 0:
            raise ValueError('character product is not one')
        if sum(int(coeff[s] > 0) for s in circuit) % 2 != 1:
            raise ValueError('no sign frustration established')
        lower += 2 * min(abs(coeff[s]) for s in circuit)
        used.update(circuit)
    return lower


def verify_obstruction_receipt(clauses, n, receipt):
    """Independently recompute each leaf from original clauses.

    Reuses the existing rational source-expansion code, but the new circuit
    proof grammar uses only support XOR, sign parity and coefficient magnitudes
    (no producer Gaussian elimination or block-minimum enumeration).
    """
    if (not isinstance(receipt, dict) or receipt.get('version') != VERSION or
            receipt.get('formula_sha256') != formula_digest(clauses, n)):
        raise ValueError('wrong source or version')

    def check(node, prefix):
        if not isinstance(node, dict):
            raise ValueError('invalid proof node')
        kind = node.get('kind')
        if kind == 'sat':
            witness = node.get('witness')
            if (not isinstance(witness, list) or len(witness) != n or
                any(type(b) is not int or b not in (0, 1) for b in witness) or
                any(witness[v] != b for v,b in prefix.items()) or
                direct_energy(clauses, witness) != 0):
                raise ValueError('invalid SAT witness')
            return 'SAT'
        if kind in ('parity_circuit_bound','rank_block_bound'):
            bound = node.get('bound')
            if (not isinstance(bound, list) or len(bound) != 2 or
                any(type(v) is not int for v in bound) or bound[1] <= 0):
                raise ValueError('invalid bound encoding')
            if kind == 'parity_circuit_bound':
                exact = independent_obstruction_bound(clauses, prefix, node.get('circuits'))
            else:
                exact = independent_rank_block_bound(clauses, prefix, node.get('blocks'), 3)
            if exact <= 0 or bound != as_ratio(exact):
                raise ValueError('unsupported UNSAT claim')
            return 'UNSAT'
        if kind == 'split':
            v = node.get('variable')
            if type(v) is not int or not 0 <= v < n or v in prefix:
                raise ValueError('invalid split variable')
            prefix[v] = 0
            zero = check(node.get('zero'),prefix)
            prefix[v] = 1
            one = check(node.get('one'),prefix)
            del prefix[v]
            if 'SAT' in (zero,one):
                return 'SAT'
            if zero == one == 'UNSAT':
                return 'UNSAT'
            return 'UNKNOWN'
        if kind == 'unknown' and node.get('reason') == 'budget':
            return 'UNKNOWN'
        raise ValueError('unsupported proof node')

    result = check(receipt.get('proof'), {})
    if result != receipt.get('result'):
        raise ValueError('claim does not follow from receipt')
    return result


def produce_obstruction_receipt(clauses, n, budget=256):
    """Proof producer: witness-first, local rank blocks, then XOR circuits.

    Does NOT scan all pairs. For each unsupported leaf it branches, preserving
    UNKNOWN. Algebraically stronger rank blocks may win when circuits are weak.
    """
    validate_formula(clauses, n)
    if type(budget) is not int or budget < 1:
        raise ValueError('budget must be positive integer')
    visited = 0
    ledgers = {'gaussian_row_reductions':0, 'circuit_terms_examined':0,
               'circuit_leaves':0,'rank_leaves':0}

    def search(coeff, prefix):
        nonlocal visited
        visited += 1
        if visited > budget:
            return {'kind':'unknown','reason':'budget'}, 'UNKNOWN'
        remaining = [v for v in range(n) if v not in prefix]
        if remaining:
            probe, bits = dict(coeff), dict(prefix)
            for _ in remaining:
                choices = [v for v in range(n) if v not in bits]
                variable = max(choices, key=lambda v:(abs(probe.get(1<<v,0)), -v))
                bit = int(probe.get(1<<variable,0)>0)
                bits[variable] = bit
                probe = conditional_coefficients(probe,variable,bit)
            witness = [bits[v] for v in range(n)]
            if direct_energy(clauses,witness)==0:
                return {'kind':'sat','witness':witness}, 'SAT'
        local,blocks = rank_block_bound(coeff, clauses, 3)
        if local > 0:
            ledgers['rank_leaves'] += 1
            return {'kind':'rank_block_bound','bound':as_ratio(Fraction(local,8)),
                    'blocks':[list(b) for b in blocks]}, 'UNSAT'
        circ_bound, circuits, metrics = obstruction_bound(coeff)
        ledgers['gaussian_row_reductions'] += metrics['gaussian_row_reductions']
        ledgers['circuit_terms_examined'] += metrics['circuit_terms']
        if circ_bound > 0:
            ledgers['circuit_leaves'] += 1
            return {'kind':'parity_circuit_bound','bound':as_ratio(Fraction(circ_bound,8)),
                    'circuits':[list(c) for c in circuits]}, 'UNSAT'
        if not remaining:
            raise AssertionError('positive full-state energy should have been detected')
        variable = max(remaining, key=lambda v:(
            sum(abs(a) for s,a in coeff.items() if s & (1<<v)), -v))
        zero,st0 = search(conditional_coefficients(coeff,variable,0),
                          {**prefix,variable:0})
        if st0=='SAT':
            return zero,'SAT'
        one,st1 = search(conditional_coefficients(coeff,variable,1),
                         {**prefix,variable:1})
        if st1=='SAT':
            return one,'SAT'
        return ({'kind':'split','variable':variable,'zero':zero,'one':one},
                'UNSAT' if st0==st1=='UNSAT' else 'UNKNOWN')

    proof,status=search(spectral_coefficients(clauses),{})
    receipt={'version':VERSION,'formula_sha256':formula_digest(clauses,n),
             'result':status,'proof':proof,'producer_nodes_visited':visited,
             'producer_budget':budget,'producer_discovery':ledgers}
    assert verify_obstruction_receipt(clauses,n,receipt)==status
    return receipt

GROUND_VERSION = 'SPN-006-ground-v1'


def produce_compatible_ground_receipt(clauses, n):
    """Proof-carrying exact minimum for globally sign-compatible landscapes.

    Returns UNKNOWN if the elementary termwise minima conflict. UNKNOWN says
    nothing about the existence of SAT solutions or an exact ground elsewhere.
    """
    validate_formula(clauses, n)
    x, lower, rank = compatible_preference_ground(spectral_coefficients(clauses), n)
    if x is None:
        result = {'kind':'unknown','reason':'incompatible_termwise_preferences'}
    else:
        result = {'kind':'exact_ground', 'energy':as_ratio(Fraction(lower,8)),
                  'witness':[(x>>i)&1 for i in range(n)]}
    receipt={'version':GROUND_VERSION,'formula_sha256':formula_digest(clauses,n),
             'result':result,'producer_fourier_rank':rank}
    verify_compatible_ground_receipt(clauses,n,receipt)
    return receipt


def verify_compatible_ground_receipt(clauses,n,receipt):
    """Trust only the original clauses, rational Fourier bound and direct energy."""
    if (not isinstance(receipt,dict) or receipt.get('version')!=GROUND_VERSION or
            receipt.get('formula_sha256')!=formula_digest(clauses,n)):
        raise ValueError('incorrect exact-ground source or version')
    result=receipt.get('result')
    if not isinstance(result,dict):
        raise ValueError('invalid exact-ground result')
    if result.get('kind')=='unknown' and result.get('reason')=='incompatible_termwise_preferences':
        return 'UNKNOWN'
    if result.get('kind')!='exact_ground':
        raise ValueError('unsupported exact-ground claim')
    witness=result.get('witness')
    claimed=result.get('energy')
    if (not isinstance(witness,list) or len(witness)!=n or
            any(type(b) is not int or b not in (0,1) for b in witness)):
        raise ValueError('invalid exact-ground witness')
    coeff=independent_residual_coefficients(clauses,{})
    lower=coeff.get(0,Fraction())-sum((abs(a) for s,a in coeff.items() if s), Fraction())
    if claimed != as_ratio(lower) or Fraction(direct_energy(clauses,witness)) != lower:
        raise ValueError('witness does not attain an independently verified global lower bound')
    return 'EXACT'
