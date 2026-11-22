#!/usr/bin/env python3
"""SPN-005: bounded nonlocal rank-three Fourier-Ground discovery.

A pair-XOR collision S^T=U^V exposes a four-term dependency even when
none of the terms share a source clause. Search is budgeted; the independent
SPN-004 verifier recomputes every claimed minimum directly from source clauses.
No general worst-case speedup or complete budgeted discovery is claimed.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction

from rank_block_bounds import (VERSION as RANK_VERSION, block_candidates,
    exact_block_minimum, parity_basis, rank_block_bound, verify_rank_receipt)
from spectral_receipts import direct_energy, formula_digest, validate_formula, as_ratio
from walsh_phase_navigation_probe import spectral_coefficients, conditional_coefficients

VERSION = 'SPN-005-v1'


def nonlocal_four_circuits(coeff, pair_budget=12000, candidate_budget=800,
                           bucket_limit=8):
    """Discover rank-three candidates from bounded pair-XOR collisions.

    All source terms are eligible regardless of variable span or clause scope.
    Round-robin pair enumeration by index gap gives coverage across large
    spectra before the pair budget is exhausted. Returns (candidates, costs).
    Coefficients are signed integers in units of 1/8.
    """
    if any(type(v) is not int or v < 0 for v in
           (pair_budget, candidate_budget, bucket_limit)):
        raise ValueError('search budgets must be nonnegative integers')
    if bucket_limit < 1:
        raise ValueError('bucket limit must be positive')
    masks = sorted((s for s, a in coeff.items() if s and a),
                   key=lambda s: (-abs(coeff[s]), s))
    pairs = defaultdict(list)
    candidates = {}
    pairs_examined = collisions = evaluated = parity_states = 0
    max_pairs = len(masks) * (len(masks) - 1) // 2
    stopped = False
    for gap in range(1, len(masks)):
        for i in range(len(masks) - gap):
            if pairs_examined >= pair_budget or evaluated >= candidate_budget:
                stopped = True
                break
            s, t = masks[i], masks[i + gap]
            pairs_examined += 1
            delta = s ^ t
            for u, v in pairs[delta]:
                collisions += 1
                circuit = tuple(sorted((s, t, u, v)))
                if len(set(circuit)) != 4:
                    continue
                # chi_s chi_t chi_u chi_v=1; negative coefficient product
                # makes four independently desirable signs incompatible.
                if coeff[s] * coeff[t] * coeff[u] * coeff[v] >= 0:
                    continue
                basis = parity_basis(circuit)
                if len(basis) != 3:
                    raise AssertionError('four distinct XOR-linked terms must have rank 3')
                span = {a ^ b ^ c for a in (0, basis[0])
                        for b in (0, basis[1]) for c in (0, basis[2])}
                complete = tuple(sorted(z for z in span if z and coeff.get(z, 0)))
                for block in (circuit, complete):
                    if block in candidates:
                        continue
                    if evaluated >= candidate_budget:
                        stopped = True
                        break
                    minimum, rank = exact_block_minimum(coeff, block)
                    evaluated += 1
                    parity_states += 1 << rank
                    gain = minimum + sum(abs(coeff[z]) for z in block)
                    if gain > 0:
                        candidates[block] = (gain, rank, block)
                if stopped:
                    break
            if stopped:
                break
            if len(pairs[delta]) < bucket_limit:
                pairs[delta].append((s, t))
        if stopped:
            break
    ledger = {'pairs_examined': pairs_examined,
              'total_possible_pairs': max_pairs,
              'collisions_considered': collisions,
              'block_minima_evaluated': evaluated,
              'block_parity_states_evaluated': parity_states,
              'candidate_blocks': len(candidates),
              'discovery_truncated': pairs_examined < max_pairs or stopped}
    return sorted(candidates.values(), key=lambda row: (-row[0], row[1], row[2])), ledger


def nonlocal_rank_bound(coeff, clauses, pair_budget=12000, candidate_budget=800):
    """Return certified numerator /8, blocks, and producer discovery counters."""
    old_bound, old_blocks = rank_block_bound(coeff, clauses, max_rank=3)
    if old_bound > 0:
        # Already a certified UNSAT leaf: no need to discover another Ground.
        return old_bound, old_blocks, {
            'pairs_examined': 0, 'total_possible_pairs': 0,
            'collisions_considered': 0, 'block_minima_evaluated': 0,
            'block_parity_states_evaluated': 0, 'candidate_blocks': 0,
            'discovery_truncated': False, 'skipped_local_certificate': True}
    novel, cost = nonlocal_four_circuits(coeff, pair_budget, candidate_budget)
    cost['skipped_local_certificate'] = False
    pool = {masks: (gain, rank, masks)
            for gain, rank, masks in block_candidates(coeff, clauses, 3)}
    for gain, rank, masks in novel:
        if masks not in pool or gain > pool[masks][0]:
            pool[masks] = gain, rank, masks
    selected = []
    used = set()
    gain = 0
    for bonus, rank, group in sorted(pool.values(), key=lambda row:(-row[0], row[1], row[2])):
        if all(m not in used for m in group):
            selected.append(group)
            used.update(group)
            gain += bonus
    naive = coeff.get(0, 0) - sum(abs(a) for s, a in coeff.items() if s)
    new_bound = naive + gain
    if new_bound > old_bound:
        return new_bound, selected, cost
    return old_bound, old_blocks, cost


def verify_nonlocal_receipt(clauses, n, receipt):
    """Check the SPN-005 envelope with SPN-004's source-recomputed kernel.

    This is *not* a separate codebase or a novel independent verifier:
    it deliberately reuses the existing rational source-expansion checker,
    exact GF(2) block-minimum checker and proof-tree grammar.
    """
    if not isinstance(receipt, dict) or receipt.get('version') != VERSION:
        raise ValueError('wrong SPN-005 receipt version')
    if receipt.get('rank_cap') != 3:
        raise ValueError('SPN-005 rank_cap must be three')
    legacy = dict(receipt)
    legacy['version'] = RANK_VERSION
    return verify_rank_receipt(clauses, n, legacy)


def produce_nonlocal_receipt(clauses, n, budget=256, pair_budget=12000,
                             candidate_budget=800):
    validate_formula(clauses, n)
    if type(budget) is not int or budget < 1:
        raise ValueError('proof-node budget must be positive integer')
    visited = 0
    operations = {'pairs_examined': 0, 'collisions_considered': 0,
                  'block_minima_evaluated': 0,
                  'block_parity_states_evaluated': 0,
                  'truncated_nodes': 0, 'bound_leaves': 0,
                  'local_only_leaves': 0}

    def search(coeff, prefix):
        nonlocal visited
        visited += 1
        if visited > budget:
            return {'kind': 'unknown', 'reason': 'budget'}, 'UNKNOWN'
        # Witness-first admission avoids expensive subspace discovery when a
        # directly verified SAT witness already solves the observer's task.
        remaining = [v for v in range(n) if v not in prefix]
        if remaining:
            probe, bits = dict(coeff), dict(prefix)
            for _ in remaining:
                choices = [v for v in range(n) if v not in bits]
                variable = max(choices, key=lambda v: (abs(probe.get(1 << v, 0)), -v))
                bit = int(probe.get(1 << variable, 0) > 0)
                bits[variable] = bit
                probe = conditional_coefficients(probe, variable, bit)
            witness = [bits[v] for v in range(n)]
            if direct_energy(clauses, witness) == 0:
                return {'kind': 'sat', 'witness': witness}, 'SAT'
        lower, blocks, cost = nonlocal_rank_bound(coeff, clauses, pair_budget, candidate_budget)
        for key in ('pairs_examined', 'collisions_considered', 'block_minima_evaluated',
                    'block_parity_states_evaluated'):
            operations[key] += cost[key]
        operations['truncated_nodes'] += int(cost['discovery_truncated'])
        if lower > 0:
            operations['bound_leaves'] += 1
            operations['local_only_leaves'] += int(cost['skipped_local_certificate'])
            return {'kind': 'rank_block_bound', 'bound': as_ratio(Fraction(lower, 8)),
                    'blocks': [list(b) for b in blocks]}, 'UNSAT'
        if not remaining:
            raise AssertionError('nonzero full assignment has positive certified bound')
        variable = max(remaining, key=lambda v: (
            sum(abs(a) for s, a in coeff.items() if s & (1 << v)), -v))
        zero, st0 = search(conditional_coefficients(coeff, variable, 0),
                           {**prefix, variable: 0})
        if st0 == 'SAT':
            return zero, 'SAT'
        one, st1 = search(conditional_coefficients(coeff, variable, 1),
                          {**prefix, variable: 1})
        if st1 == 'SAT':
            return one, 'SAT'
        return ({'kind': 'split', 'variable': variable, 'zero': zero, 'one': one},
                'UNSAT' if st0 == st1 == 'UNSAT' else 'UNKNOWN')

    proof, result = search(spectral_coefficients(clauses), {})
    receipt = {'version': VERSION, 'formula_sha256': formula_digest(clauses, n),
               'rank_cap': 3, 'result': result, 'proof': proof,
               'producer_nodes_visited': visited, 'producer_budget': budget,
               'producer_discovery': operations,
               'pair_budget_per_node': pair_budget,
               'candidate_budget_per_node': candidate_budget}
    assert verify_nonlocal_receipt(clauses, n, receipt) == result
    return receipt


def parity_cycle_cnf(block_count, span_layout=True, frustrated=True):
    """Return (clauses,n), width-3 CNF for frustrated signed 4-cycles.

    Each edge contributes (1+sign*chi_u*chi_v)/2 using four width-3
    clauses, with z an auxiliary free bit in the energy (cancels exactly).
    Odd sign product yields an exact ground energy of 1 per cycle.
    With frustrated=False each cycle has a zero-energy completion.
    """
    if type(block_count) is not int or block_count < 1:
        raise ValueError('positive block count required')
    n = 5 * block_count
    result = []
    for b in range(block_count):
        if span_layout:
            v = [b + j * block_count for j in range(5)]
        else:
            v = [5 * b + j for j in range(5)]
        a, c, d, e, z = v
        for u, w, sign in ((a, c, +1), (c, d, +1),
                           (d, e, +1), (e, a, -1 if frustrated else +1)):
            forbidden_pairs = ((0, 0), (1, 1)) if sign == 1 else ((0, 1), (1, 0))
            for first, second in forbidden_pairs:
                for zbit in (0, 1):
                    result.append(((u, w, z), (first, second, zbit)))
    return result, n
