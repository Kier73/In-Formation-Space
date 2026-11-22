#!/usr/bin/env python3
"""SPN-007 matched seeded experiment: goal/representation/cost accounting."""
from __future__ import annotations
import json
from random import Random
from statistics import median
from time import perf_counter

from adaptive_ground_compiler import produce_adaptive_receipt,verify_adaptive_receipt
from direct_sum_grounds import produce_direct_sum_ground,verify_direct_sum_ground
from parity_obstruction_grounds import produce_obstruction_receipt
from test_direct_sum_grounds import shared_variable_cycle_cnf
from nonlocal_rank_grounds import parity_cycle_cnf
from walsh_phase_navigation_probe import violated_count


def _bytes(data):
    return len(json.dumps(data,sort_keys=True,separators=(',',':')).encode())


def campaign(seed=73176, budget=256):
    rng=Random(seed)
    random_rows=[]
    for n,m in ((8,34),(10,43),(12,51)):
        row={'n':n,'m':m,'sample_count':30,'sat':0,'unsat':0,
             'gaussian_nodes':0,'adaptive_fallback_nodes':0,
             'adaptive_exact_ground_count':0,'adaptive_witness_count':0,
             'adaptive_gaussian_count':0,'adaptive_pair_count':0,
             'gaussian_wall_ms':0.,'adaptive_wall_ms':0.,
             'gaussian_receipt_bytes':0,'adaptive_receipt_bytes':0,
             'exact_cap_refusals':0,'largest_component_ranks':[]}
        for _ in range(30):
            clauses=[(tuple(sorted(rng.sample(range(n),3))),
                      tuple(rng.randrange(2) for _ in range(3))) for _ in range(m)]
            truth='SAT' if any(violated_count(clauses,x)==0 for x in range(1<<n)) else 'UNSAT'
            t=perf_counter(); old=produce_obstruction_receipt(clauses,n,budget=budget)
            row['gaussian_wall_ms']+=(perf_counter()-t)*1000
            t=perf_counter(); new=produce_adaptive_receipt(clauses,n,goal='decision',
                                                rank_cap=3,node_budget=budget)
            row['adaptive_wall_ms']+=(perf_counter()-t)*1000
            assert old['result']==new['result']==truth
            assert verify_adaptive_receipt(clauses,n,new)==truth
            row[truth.lower()]+=1
            row['gaussian_nodes']+=old['producer_nodes_visited']
            row['gaussian_receipt_bytes']+=_bytes(old)
            row['adaptive_receipt_bytes']+=_bytes(new)
            selection=new['producer_policy']['selected_method']
            if selection=='conditional_mean_witness':row['adaptive_witness_count']+=1
            elif selection in ('compatible_sign_ground','direct_sum_ground'):
                row['adaptive_exact_ground_count']+=1
            elif selection=='gaussian_circuits':
                row['adaptive_gaussian_count']+=1
                row['adaptive_fallback_nodes']+=new['producer_policy']['discovery']['decision_nodes_visited']
            elif selection=='nonlocal_pair_scan':
                row['adaptive_pair_count']+=1
                row['adaptive_fallback_nodes']+=new['producer_policy']['discovery']['decision_nodes_visited']
            else:raise AssertionError(selection)
            _,audit=produce_direct_sum_ground(clauses,n,rank_cap=3)
            if not audit['supported']:row['exact_cap_refusals']+=1
            row['largest_component_ranks'].append(audit['largest_component_rank'])
        for field in ('gaussian_wall_ms','adaptive_wall_ms'):
            row[field]=round(row[field],3)
        ranks=row.pop('largest_component_ranks')
        row['median_largest_component_rank']=median(ranks)
        row['max_largest_component_rank']=max(ranks)
        random_rows.append(row)

    structured=[]
    for blocks in (1,4,12,24,64,128):
        for frustrated in (False,True):
            cls,n=shared_variable_cycle_cnf(blocks,frustrated)
            t=perf_counter(); ground,audit=produce_direct_sum_ground(cls,n,rank_cap=2)
            construction_ms=(perf_counter()-t)*1000
            assert ground is not None and verify_direct_sum_ground(cls,n,ground)==ground['result']
            t=perf_counter(); verify_direct_sum_ground(cls,n,ground)
            verifier_ms=(perf_counter()-t)*1000
            t=perf_counter(); adaptive=produce_adaptive_receipt(cls,n,goal='exact_ground',rank_cap=2)
            adaptive_ms=(perf_counter()-t)*1000
            assert adaptive['ground_energy']==[blocks if frustrated else 0,1]
            assert adaptive['result']==('UNSAT' if frustrated else 'SAT')
            row={'family':'shared-central-variable parity triangles',
                 'blocks':blocks,'n':n,'m':len(cls),'frustrated':frustrated,
                 'global_fourier_rank':audit['rank'],
                 'component_count':audit['component_count'],
                 'max_component_rank':audit['largest_component_rank'],
                 'parity_states_enumerated':audit['states_enumerated'],
                 'exact_minimum':adaptive['ground_energy'],
                 'ground_degeneracy':adaptive['ground_degeneracy'],
                 'direct_sum_producer_ms':round(construction_ms,3),
                 'direct_sum_verifier_ms':round(verifier_ms,3),
                 'adaptive_total_ms':round(adaptive_ms,3),
                 'direct_sum_receipt_bytes':_bytes(ground),
                 'adaptive_receipt_bytes':_bytes(adaptive),
                 'adaptive_selected_method':adaptive['producer_policy']['selected_method']}
            if blocks<=24 and frustrated:
                t=perf_counter(); old=produce_obstruction_receipt(cls,n,budget=256)
                row['gaussian_decision_ms']=round((perf_counter()-t)*1000,3)
                row['gaussian_decision_nodes']=old['producer_nodes_visited']
                assert old['result']=='UNSAT'
            structured.append(row)
    old_cls,old_n=parity_cycle_cnf(24)
    old_ground,old_audit=produce_direct_sum_ground(old_cls,old_n,rank_cap=3)
    assert old_ground['ground_energy']==[24,1]
    assert verify_direct_sum_ground(old_cls,old_n,old_ground)=='UNSAT'
    return {'experiment':'SPN-007','seed':seed,'node_budget':budget,
            'random_3sat':random_rows,'source_connected_parity_family':structured,
            'former_spn006_family':{'n':old_n,'clauses':len(old_cls),
               'rank':old_audit['rank'],'component_count':old_audit['component_count'],
               'max_rank':old_audit['largest_component_rank'],
               'parity_states':old_audit['states_enumerated'],
               'exact_ground_energy':old_ground['ground_energy'],
               'ground_degeneracy':old_ground['ground_degeneracy']},
            'timing_scope':'single local CPython 3 run, source-expansion checker included in adaptive output; no timing calibration; portfolio attempt, quotient construction, and verification costs are charged',
            'complexity_scope':'exactness requires a partition with per-component rank <= cap; worst-case a single rank-n component forces refusal; no general polynomial-time SAT claim'}

if __name__=='__main__':
    print(json.dumps(campaign(),indent=2))
