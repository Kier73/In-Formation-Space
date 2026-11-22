#!/usr/bin/env python3
"""SPN-007: goal-aware, cost-accounted Ground compilation for width-three SAT.

The compiler chooses between a direct SAT witness, termwise-compatible exact
minimum, independently checkable direct-sum exact minimum, and certified search.
It never treats failure to construct a Ground as a proof of UNSAT. Decisions
are admitted ONLY by the source-bound checker, not by the strategy selector.

All discovery ledgers and timings are producer observations, NOT verified claims.
The source CNF digest and the proof payload determine correctness.
"""
from __future__ import annotations

from fractions import Fraction
import json
from time import perf_counter

from direct_sum_grounds import (produce_direct_sum_ground,
    verify_direct_sum_ground, _independent_rank)
from nonlocal_rank_grounds import (produce_nonlocal_receipt,
                                  verify_nonlocal_receipt)
from parity_obstruction_grounds import (compatible_preference_ground,
    produce_obstruction_receipt, verify_obstruction_receipt)
from spectral_receipts import (as_ratio,direct_energy,formula_digest,
    independent_residual_coefficients,validate_formula)
from walsh_phase_navigation_probe import (navigate_by_conditional_mean,
                                           spectral_coefficients)

VERSION = 'SPN-007-adaptive-v1'


def verify_adaptive_receipt(clauses,n,receipt):
    """Source-bound decision/ground checker with no trust in choice or ledger."""
    if (not isinstance(receipt,dict) or receipt.get('version')!=VERSION or
            receipt.get('formula_sha256')!=formula_digest(clauses,n)):
        raise ValueError('invalid source identity or adaptive version')
    goal=receipt.get('goal')
    if goal not in ('decision','exact_ground'):
        raise ValueError('unsupported observer goal')
    proof=receipt.get('proof')
    if not isinstance(proof,dict):
        raise ValueError('missing proof')
    kind=proof.get('kind')
    energy=None
    degeneracy=None
    if kind=='sat_witness':
        if goal!='decision':
            raise ValueError('a SAT witness is not an exact-ground certificate')
        bits=proof.get('witness')
        if (not isinstance(bits,list) or len(bits)!=n or
                any(type(b) is not int or b not in (0,1) for b in bits) or
                direct_energy(clauses,bits)!=0):
            raise ValueError('invalid SAT witness')
        result='SAT'
    elif kind=='termwise_exact':
        bits=proof.get('witness')
        if (not isinstance(bits,list) or len(bits)!=n or
                any(type(b) is not int or b not in (0,1) for b in bits)):
            raise ValueError('invalid full assignment')
        coeff=independent_residual_coefficients(clauses,{})
        low=coeff.get(0,Fraction())-sum((abs(a) for s,a in coeff.items() if s),Fraction())
        if proof.get('ground_energy')!=as_ratio(low) or direct_energy(clauses,bits)!=low:
            raise ValueError('source witness does not attain claimed termwise minimum')
        energy=as_ratio(low)
        degeneracy=str(1 << (n-_independent_rank(s for s,v in coeff.items() if s and v)))
        if proof.get('ground_degeneracy')!=degeneracy:
            raise ValueError('incorrect termwise Ground degeneracy')
        result='SAT' if low==0 else 'UNSAT'
    elif kind=='direct_sum_ground':
        nested=proof.get('receipt')
        result=verify_direct_sum_ground(clauses,n,nested)
        energy=nested['ground_energy']
        degeneracy=nested['ground_degeneracy']
    elif kind=='decision_proof':
        if goal!='decision':
            raise ValueError('decision proof is not an exact-ground receipt')
        method=proof.get('method')
        nested=proof.get('receipt')
        if method=='gaussian_circuits':
            result=verify_obstruction_receipt(clauses,n,nested)
        elif method=='nonlocal_pair_scan':
            result=verify_nonlocal_receipt(clauses,n,nested)
        else:
            raise ValueError('unrecognized certified decision method')
    elif kind=='unknown':
        if proof.get('reason')!='exact_ground_not_admitted' or goal!='exact_ground':
            raise ValueError('unsupported explicit refusal')
        result='UNKNOWN'
    else:
        raise ValueError('unknown or unsupported adaptive proof kind')
    if (result!=receipt.get('result') or receipt.get('ground_energy')!=energy or
        receipt.get('ground_degeneracy')!=degeneracy):
        raise ValueError('adaptive result/ground energy not established')
    return result


def produce_adaptive_receipt(clauses,n,goal='decision',rank_cap=4,
                              node_budget=256,pair_budget=0,candidate_budget=200):
    """Compile goal-relative receipts with explicit attempt/cost accounting.

    Static policy:
      decision: try cheapest conditional-mean witness, then Gaussian exact
                preferred-sign minimization, direct-sum quotient, then search;
      exact_ground: try Gaussian preferred signs and direct-sum quotient only;
      small collision search is eligible only when EVERY possible support pair
                fits within the user-declared pair budget, and t<=24.
    No speculative pair scan is silently performed. All source verification
    is charged to total execution elapsed time and counted as a separate step.
    """
    validate_formula(clauses,n)
    if goal not in ('decision','exact_ground'):
        raise ValueError('goal must be decision or exact_ground')
    if type(node_budget) is not int or node_budget<1:
        raise ValueError('node_budget must be positive integer')
    if (type(pair_budget) is not int or pair_budget<0 or
        type(candidate_budget) is not int or candidate_budget<0):
        raise ValueError('pair/candidate budgets must be nonnegative integers')
    if type(rank_cap) is not int or not 1<=rank_cap<=10:
        raise ValueError('rank_cap must be 1..10')
    source=formula_digest(clauses,n)
    started=perf_counter()
    attempts=[]
    coeff=spectral_coefficients(clauses)
    active=sum(bool(s and a) for s,a in coeff.items())
    pair_possible=active*(active-1)//2
    proof=None
    result=None
    energy=None
    degeneracy=None
    chosen=None
    discovery={}

    def mark(name, t, outcome):
        attempts.append({'method':name,'outcome':outcome,
                         'observed_ms':round((perf_counter()-t)*1000,3)})

    if goal=='decision':
        t=perf_counter()
        mask,value,_=navigate_by_conditional_mean(coeff,n)
        bits=[(mask>>i)&1 for i in range(n)]
        if value==0 and direct_energy(clauses,bits)==0:
            result,chosen='SAT','conditional_mean_witness'
            proof={'kind':'sat_witness','witness':bits}
        mark('conditional_mean_witness',t,'SAT' if proof is not None else 'not_solved')

    if proof is None:
        t=perf_counter()
        ground_mask,low,rank=compatible_preference_ground(coeff,n)
        discovery['preferred_sign_rank']=rank
        if ground_mask is not None:
            bits=[(ground_mask>>i)&1 for i in range(n)]
            energy=as_ratio(Fraction(low,8))
            degeneracy=str(1 << (n-rank))
            proof={'kind':'termwise_exact','witness':bits,'ground_energy':energy,
                   'ground_degeneracy':degeneracy}
            result='SAT' if low==0 else 'UNSAT'
            chosen='compatible_sign_ground'
        mark('compatible_sign_ground',t,'exact' if proof is not None else 'incompatible')

    if proof is None:
        t=perf_counter()
        ground,audit=produce_direct_sum_ground(clauses,n,rank_cap,coeff=coeff)
        discovery['direct_sum']=audit
        if ground is not None:
            proof={'kind':'direct_sum_ground','receipt':ground}
            result=ground['result']
            energy=ground['ground_energy']
            degeneracy=ground['ground_degeneracy']
            chosen='direct_sum_ground'
        mark('direct_sum_ground',t,'exact' if ground is not None else 'rank_cap_refusal')

    if proof is None and goal=='exact_ground':
        result,chosen='UNKNOWN','exact_ground_refusal'
        proof={'kind':'unknown','reason':'exact_ground_not_admitted'}

    if proof is None:
        use_pairs=(0<pair_possible<=pair_budget and active<=24 and candidate_budget>0)
        chosen='nonlocal_pair_scan' if use_pairs else 'gaussian_circuits'
        t=perf_counter()
        if use_pairs:
            decision=produce_nonlocal_receipt(clauses,n,budget=node_budget,
                                              pair_budget=pair_budget,
                                              candidate_budget=candidate_budget)
        else:
            decision=produce_obstruction_receipt(clauses,n,budget=node_budget)
        discovery['decision_nodes_visited']=decision.get('producer_nodes_visited')
        discovery['decision_producer_discovery']=decision.get('producer_discovery')
        proof={'kind':'decision_proof','method':chosen,'receipt':decision}
        result=decision['result']
        mark(chosen,t,result)

    receipt={'version':VERSION,'formula_sha256':source,'goal':goal,
             'result':result,'ground_energy':energy,
             'ground_degeneracy':degeneracy,'proof':proof,
             'producer_policy':{'max_component_rank':rank_cap,'node_budget':node_budget,
                                'pair_budget':pair_budget,
                                'candidate_budget':candidate_budget,
                                'nonzero_spectral_terms':active,
                                'possible_pairs':pair_possible,
                                'selected_method':chosen,
                                'attempts':attempts,'discovery':discovery}}
    t=perf_counter()
    established=verify_adaptive_receipt(clauses,n,receipt)
    receipt['producer_policy']['observed_verification_ms']=round((perf_counter()-t)*1000,3)
    receipt['producer_policy']['observed_total_ms']=round((perf_counter()-started)*1000,3)
    assert established==result
    return receipt


if __name__=='__main__':
    from test_direct_sum_grounds import shared_variable_cycle_cnf
    clauses,n=shared_variable_cycle_cnf(12)
    print(json.dumps(produce_adaptive_receipt(clauses,n,goal='exact_ground',rank_cap=2),indent=2))
