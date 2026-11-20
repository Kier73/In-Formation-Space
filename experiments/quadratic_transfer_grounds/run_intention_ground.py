"""Deterministic TCN-008 experiment: exact goal synthesis and exclusion audit."""
from __future__ import annotations

import json
import math
import time

import numpy as np

from intention_ground import (Host, SynthesizedGround, make_intent,
                              make_receipt, synthesize, verify_receipt)


def phases(p, coefficients):
    return [sum(c*pow(x,j,p) for j,c in enumerate(coefficients)) % p
            for x in range(p)]


def run():
    p=127
    hs=(Host('quadratic',2,tuple(range(p)),transfer_cost=1,higher_phase_cost=4),
        Host('cubic',3,tuple(range(p)),transfer_cost=2,higher_phase_cost=4),
        Host('analytic-degree-5',5,tuple(range(p)),transfer_cost=3,higher_phase_cost=4))
    candidates={
        'quadratic': [0,19,7],
        'cubic': [0,19,7,11],
        'quartic': [0,19,7,11,3],
        'quintic': [0,19,7,11,3,5],
        'degree_six_negative': [0,19,7,11,3,5,1],
    }
    trials={}
    for name, coeffs in candidates.items():
        intent=make_intent(p, phases(p,coeffs))
        plan=synthesize(intent,hs)
        receipt=make_receipt(intent,hs)
        entry={'status':plan['status'], 'selected_host':plan['selected_host'],
               'target_constraints':len(intent.constraints),
               'plan_reconstructed':verify_receipt(receipt),
               'full_target':plan.get('complete_target',True),
               'family':plan['ground']['family'] if plan['ground'] else None,
               'minimality_witness':plan.get('minimality_witness',plan.get('obstruction')),
               'estimated_cost':plan['estimated_cost']}
        if plan['status']=='realizable':
            ground=SynthesizedGround(p,tuple(plan['ground']['coefficients']),plan['ground']['source'])
            reference=ground.dense_independent()
            entry['dense_max_absolute_error']=float(np.max(np.abs(ground.full_vector()-reference)))
            giant=10**100+83
            entry['huge_coordinate_digits']=len(str(giant))
            entry['huge_coordinate_exact_alias']=ground.relative_residue(giant)==ground.relative_residue(giant%p)
            entry['description_coefficients']=len(ground.coefficients)
        trials[name]=entry
    restricted_intent=make_intent(p, phases(p,candidates['cubic']),max_cost=2)
    budget=synthesize(restricted_intent,hs)
    cubic_block=synthesize(make_intent(p,phases(p,candidates['cubic'])),(hs[0],))
    random=np.random.default_rng(2026).integers(0,p,size=p).tolist()
    random[0]=0
    negative=synthesize(make_intent(p,random),hs)
    return {'experiment':'TCN-008','field':p,'trials':trials,
            'controls':{'cost_budget_status':budget['status'],
                        'cubic_without_cubic_host':cubic_block['status'],
                        'random_target_status':negative['status']},
            'scope':'exact declared finite-field phase intentions only; symbolic hosts are unauthenticated',
            'calibration':'no timed performance or performance advantage asserted; dense error is numerical rendering only',
            'external_realization_witnessed':False}


if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
