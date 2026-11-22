#!/usr/bin/env python3
"""SPN-007: proof-carrying exact minimum via Fourier direct-sum Grounds.

The source CNF is width-three with distinct variables in each clause. A
fundamental-circuit partition of its nonzero Fourier supports has independent
linear spans. Each component can be exactly minimized in its own GF(2) rank.

Builder: integer amplitudes, with a source verifier that separately expands
rational clause coefficients and enumerates spans using a different algorithm.
General instances may contain a rank-n component; in that case this module
refuses rather than attempting exponential enumeration.
"""
from __future__ import annotations

from fractions import Fraction
from math import gcd
from time import perf_counter

from spectral_receipts import (as_ratio, direct_energy, formula_digest,
    independent_residual_coefficients, validate_formula)
from walsh_phase_navigation_probe import spectral_coefficients

VERSION = 'SPN-007-direct-sum-v1'


def _canonical_ratio(v):
    return (isinstance(v,list) and len(v)==2 and
            all(type(x) is int for x in v) and v[1]>0 and
            gcd(v[0],v[1])==1)


def gf2_rank(supports):
    """Rank, using highest-pivot bitset elimination; O(t*n) bitset XORs."""
    pivots = {}
    for mask in supports:
        v = mask
        while v:
            p = v.bit_length()-1
            if p not in pivots:
                pivots[p] = v
                break
            v ^= pivots[p]
    return len(pivots)


def fundamental_components(supports):
    """Partition term indices using fundamental circuits of one GF(2) basis.

    The procedure unions supports in each discovered dependency, including
    independent basis terms participating in that dependency. It returns a
    deterministic partition, together with the counted XORs and unions.
    Its claimed direct-sum property is never trusted by the proof checker.
    """
    masks = sorted(set(supports))
    if not masks or masks[0] <= 0:
        if masks:
            raise ValueError('supports must be strictly positive')
        return [], {'reduction_xors':0, 'dependencies':0, 'unions':0, 'rank':0}
    pivots = {}  # highest bit -> (reduced support, original-index expression)
    parent = list(range(len(masks)))
    reductions = dependencies = unions = independent = 0

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        nonlocal unions
        x, y = find(a), find(b)
        if x != y:
            parent[max(x,y)] = min(x,y)
            unions += 1

    for index, mask in enumerate(masks):
        residue, expr = mask, 1 << index
        while residue:
            p = residue.bit_length() - 1
            if p not in pivots:
                pivots[p] = (residue, expr)
                independent += 1
                break
            row, provenance = pivots[p]
            residue ^= row
            expr ^= provenance
            reductions += 1
        if residue == 0:
            dependencies += 1
            participants = [j for j in range(index+1) if (expr >> j) & 1]
            for j in participants[1:]:
                union(participants[0], j)
    groups = {}
    for i, mask in enumerate(masks):
        groups.setdefault(find(i), []).append(mask)
    ordered = sorted((tuple(v) for v in groups.values()), key=lambda x:x[0])
    actual_rank = sum(gf2_rank(g) for g in ordered)
    if actual_rank != independent:
        raise AssertionError('fundamental circuit components are not independent')
    return ordered, {'reduction_xors':reductions,'dependencies':dependencies,
                     'unions':unions,'rank':independent}


def linear_coordinates(masks):
    """Construct source-term coordinates in an independent parity basis."""
    pivots = {}
    basis = []
    coordinates = {}
    for mask in sorted(masks):
        residue, expression = mask, 0
        inserted = False
        while residue:
            pivot = residue.bit_length()-1
            if pivot not in pivots:
                row_index = len(basis)
                basis.append(mask)
                singleton = 1 << row_index
                # The reduced row equals the ORIGINAL new basis mask XOR
                # previously subtracted basis vectors. Its stored expression
                # is therefore their XOR, not the new singleton alone.
                pivots[pivot] = (residue, expression ^ singleton)
                coordinates[mask] = singleton
                inserted = True
                break
            row, coord = pivots[pivot]
            residue ^= row
            expression ^= coord
        if not inserted:
            coordinates[mask] = expression
    if any(mask != _xor_supports(basis, coordinates[mask]) for mask in masks):
        raise AssertionError('bad parity coordinate map')
    return tuple(basis), coordinates


def _xor_supports(basis, code):
    x = 0
    for j, mask in enumerate(basis):
        if code & (1 << j):
            x ^= mask
    return x


def solve_parities(equations, n):
    """Construct an original-variable assignment from compatible parity targets."""
    pivots={}
    xors = 0
    for mask,bit in equations:
        if type(mask) is not int or mask <= 0 or mask.bit_length() > n or bit not in (0,1):
            raise ValueError('invalid parity equation')
        v, value = mask, bit
        while v:
            p = v.bit_length()-1
            if p not in pivots:
                pivots[p]=(v,value)
                break
            row, rhs = pivots[p]
            v ^= row
            value ^= rhs
            xors += 1
        if v == 0 and value:
            return None, xors
    answer = 0
    for pivot,(mask,bit) in sorted(pivots.items()):
        if ((mask & answer).bit_count() & 1) ^ bit:
            answer |= 1 << pivot
    return answer, xors


def _minimum_for_component(coeff, group):
    """Exact minimum and selected coordinates, in integer coefficient units."""
    basis, coords = linear_coordinates(group)
    best, best_bits, ground_count = None, 0, 0
    for bits in range(1 << len(basis)):
        energy = sum(coeff[s] * (-1 if ((coords[s] & bits).bit_count() & 1) else 1)
                     for s in group)
        if best is None or energy < best:
            best, best_bits, ground_count = energy, bits, 1
        elif energy == best:
            ground_count += 1
    equations = [(mask, (best_bits >> i)&1) for i,mask in enumerate(basis)]
    return best, equations, len(basis), 1 << len(basis), ground_count


def produce_direct_sum_ground(clauses, n, rank_cap=6, coeff=None):
    """Return (source-ground receipt or None, discovery ledger).

    The maximum component rank is discovered BEFORE enumeration. A refusal
    means the method does not currently admit an exact Ground, not UNSAT.
    """
    validate_formula(clauses, n)
    if type(rank_cap) is not int or not 1 <= rank_cap <= 10:
        raise ValueError('rank_cap must be 1..10')
    started = perf_counter()
    coeff = spectral_coefficients(clauses) if coeff is None else coeff
    groups, counters = fundamental_components(s for s,a in coeff.items() if s and a)
    ranks = [gf2_rank(g) for g in groups]
    audit = {**counters,'component_count':len(groups), 'component_ranks':ranks,
             'largest_component_rank':max(ranks,default=0),'rank_cap':rank_cap,
             'states_enumerated':0,'reconstruction_xors':0,
             'supported':all(r<=rank_cap for r in ranks)}
    if not audit['supported']:
        audit['elapsed_ms']=round((perf_counter()-started)*1000,3)
        return None,audit
    minimum = coeff.get(0,0)
    equations=[]
    items=[]
    # Every rank-r parity configuration lifts to 2^(n-r) original states.
    degeneracy = 1 << (n - audit['rank'])
    for group in groups:
        low, required, rank, states, local_count = _minimum_for_component(coeff,group)
        degeneracy *= local_count
        minimum += low
        equations.extend(required)
        audit['states_enumerated']+=states
        items.append({'supports':list(group),'rank':rank,'minimum':as_ratio(Fraction(low,8)),
                      'minimizers':local_count})
    assignment,xors=solve_parities(equations,n)
    audit['reconstruction_xors']=xors
    if assignment is None:
        raise AssertionError('independent Ground coordinates should have a joint realization')
    witness=[(assignment>>i)&1 for i in range(n)]
    if direct_energy(clauses,witness)*8 != minimum:
        raise AssertionError('constructed witness does not attain certified global minimum')
    receipt={'version':VERSION,'formula_sha256':formula_digest(clauses,n),
             'rank_cap':rank_cap, 'result':'SAT' if minimum==0 else 'UNSAT',
             'ground_energy':as_ratio(Fraction(minimum,8)),
             'ground_degeneracy':str(degeneracy),
             'proof':{'kind':'exact_direct_sum_ground','components':items,
                      'witness':witness}}
    audit['elapsed_ms']=round((perf_counter()-started)*1000,3)
    return receipt,audit


def _independent_rational_component_minimum(coeff, supports, rank_cap):
    """Verifier: expand each span by exhaustive XOR closure, no producer basis code.

    Maps each support mask to an expression in an independently chosen basis.
    Enumeration cost is <= 2^rank_cap, with Fraction arithmetic only.
    """
    span={0:0}
    rank=0
    expressions={}
    for support in supports:
        if support not in span:
            if rank>=rank_cap:
                raise ValueError('component rank beyond declared cap')
            bit = 1 << rank
            additional={mask^support: code|bit for mask,code in span.items()}
            if span.keys() & additional.keys():
                raise AssertionError('independent extension unexpectedly overlaps span')
            span.update(additional)
            rank+=1
        expressions[support]=span[support]
    minimum=None
    ground_count=0
    for state in range(1<<rank):
        value=sum(coeff[s]*(-1 if ((state & expressions[s]).bit_count() & 1) else 1)
                  for s in supports)
        if minimum is None or value < minimum:
            minimum, ground_count=value, 1
        elif value == minimum:
            ground_count += 1
    return minimum, rank, ground_count


def _independent_rank(masks):
    """Separate verifier rank: forward elimination using the lowest set bit."""
    pivots={}
    for mask in masks:
        v=mask
        while v:
            p=(v & -v).bit_length()-1
            if p not in pivots:
                pivots[p]=v
                break
            v ^= pivots[p]
    return len(pivots)


def verify_direct_sum_ground(clauses,n,receipt):
    """Recompute exact minima and direct-sum rank from *source* rational CNF.

    Neither the producer's partition, its cached coefficients, its GF(2)
    reduction, its result, nor its complexity ledger are trusted.
    """
    if (not isinstance(receipt,dict) or receipt.get('version')!=VERSION or
            receipt.get('formula_sha256')!=formula_digest(clauses,n)):
        raise ValueError('invalid ground source or version')
    cap=receipt.get('rank_cap')
    if type(cap) is not int or not 1<=cap<=10:
        raise ValueError('invalid rank cap')
    proof=receipt.get('proof')
    if not isinstance(proof,dict) or proof.get('kind')!='exact_direct_sum_ground':
        raise ValueError('missing exact Ground proof')
    components=proof.get('components')
    if not isinstance(components,list):
        raise ValueError('invalid components')
    coeff=independent_residual_coefficients(clauses,{})
    required={s for s,v in coeff.items() if s and v}
    observed=set()
    total=coeff.get(0,Fraction())
    local_rank=0
    ground_product=1
    previous_first=0
    for component in components:
        if not isinstance(component,dict):
            raise ValueError('malformed component')
        group=component.get('supports')
        if (not isinstance(group,list) or not group or
            any(type(s) is not int or s<=0 or s.bit_length()>n for s in group) or
            group!=sorted(set(group)) or group[0]<=previous_first or
            any(s not in required or s in observed for s in group)):
            raise ValueError('noncanonical or incorrect component partition')
        previous_first=group[0]
        value,rank,multiplicity=_independent_rational_component_minimum(coeff,group,cap)
        if (type(component.get('rank')) is not int or
            component['rank']!=rank or not _canonical_ratio(component.get('minimum')) or
            component['minimum']!=as_ratio(value) or
            type(component.get('minimizers')) is not int or
            component['minimizers']!=multiplicity):
            raise ValueError('incorrect component rank or minimum')
        observed.update(group)
        local_rank+=rank
        ground_product*=multiplicity
        total+=value
    if observed!=required:
        raise ValueError('Fourier support omitted from exact Ground certificate')
    if _independent_rank(required)!=local_rank:
        raise ValueError('component spaces are not linearly independent')
    ground_product *= 1 << (n-local_rank)
    if receipt.get('ground_degeneracy')!=str(ground_product):
        raise ValueError('incorrect source Ground degeneracy')
    witness=proof.get('witness')
    if (not isinstance(witness,list) or len(witness)!=n or
            any(type(b) is not int or b not in (0,1) for b in witness)):
        raise ValueError('invalid Ground witness')
    if (total!=direct_energy(clauses,witness) or
        not _canonical_ratio(receipt.get('ground_energy')) or
        receipt['ground_energy']!=as_ratio(total)):
        raise ValueError('claimed exact minimum is not attained by the source witness')
    status='SAT' if total==0 else 'UNSAT'
    if receipt.get('result')!=status:
        raise ValueError('unsupported exact ground SAT/UNSAT claim')
    return status
