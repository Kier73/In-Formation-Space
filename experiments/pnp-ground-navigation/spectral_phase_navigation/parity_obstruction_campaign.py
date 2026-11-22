#!/usr/bin/env python3
"""SPN-006: matched 90-instance parity-circuit comparison with SPN-004/005."""
from __future__ import annotations
import json
from random import Random
from time import perf_counter

from parity_obstruction_grounds import (produce_obstruction_receipt,
                                          verify_obstruction_receipt,
                                          compatible_preference_ground)
from nonlocal_rank_grounds import parity_cycle_cnf,produce_nonlocal_receipt
from rank_block_bounds import produce_rank_receipt
from walsh_phase_navigation_probe import spectral_coefficients,violated_count
from spectral_receipts import direct_energy


def campaign(seed=73176, budget=256):
    rng=Random(seed)
    rows=[]
    for n,m in ((8,34),(10,43),(12,51)):
        row={'n':n,'m':m,'samples':30,'sat':0,'unsat':0,
             'local_nodes':0,'pair_scan_nodes':0,'gaussian_nodes':0,
             'gaussian_better_than_local':0, 'gaussian_worse_than_local':0,
             'producer_local_ms':0.0,'producer_pair_scan_ms':0.0,
             'producer_gaussian_ms':0.0,'gaussian_row_reductions':0,
             'gaussian_circuit_leaves':0,'gaussian_receipt_bytes':0}
        for _ in range(30):
            clauses=[(tuple(sorted(rng.sample(range(n),3))),
                      tuple(rng.randrange(2) for _ in range(3))) for _ in range(m)]
            actual='SAT' if any(violated_count(clauses,x)==0 for x in range(1<<n)) else 'UNSAT'
            timer=perf_counter(); local=produce_rank_receipt(clauses,n,budget=budget)
            row['producer_local_ms']+=(perf_counter()-timer)*1000
            timer=perf_counter(); pair=produce_nonlocal_receipt(clauses,n,budget=budget)
            row['producer_pair_scan_ms']+=(perf_counter()-timer)*1000
            timer=perf_counter(); gauss=produce_obstruction_receipt(clauses,n,budget=budget)
            row['producer_gaussian_ms']+=(perf_counter()-timer)*1000
            assert local['result']==pair['result']==gauss['result']==actual
            assert verify_obstruction_receipt(clauses,n,gauss)==actual
            row[actual.lower()]+=1
            row['local_nodes']+=local['producer_nodes_visited']
            row['pair_scan_nodes']+=pair['producer_nodes_visited']
            row['gaussian_nodes']+=gauss['producer_nodes_visited']
            row['gaussian_better_than_local']+=int(gauss['producer_nodes_visited']<local['producer_nodes_visited'])
            row['gaussian_worse_than_local']+=int(gauss['producer_nodes_visited']>local['producer_nodes_visited'])
            row['gaussian_row_reductions']+=gauss['producer_discovery']['gaussian_row_reductions']
            row['gaussian_circuit_leaves']+=gauss['producer_discovery']['circuit_leaves']
            row['gaussian_receipt_bytes']+=len(json.dumps(gauss,sort_keys=True,separators=(',',':')))
        for name in ('producer_local_ms','producer_pair_scan_ms','producer_gaussian_ms'):
            row[name]=round(row[name],3)
        rows.append(row)
    structured=[]
    for blocks in (1,2,4,8,16,24):
        cl,n=parity_cycle_cnf(blocks)
        start=perf_counter(); g=produce_obstruction_receipt(cl,n,budget=64)
        elapsed=round((perf_counter()-start)*1000,3)
        assert g['result']=='UNSAT' and g['producer_nodes_visited']==1
        sat_cls,_=parity_cycle_cnf(blocks,frustrated=False)
        start=perf_counter(); x,ground,rank=compatible_preference_ground(spectral_coefficients(sat_cls),n)
        sat_elapsed=round((perf_counter()-start)*1000,3)
        assert ground==0 and direct_energy(sat_cls,[(x>>i)&1 for i in range(n)])==0
        structured.append({'blocks':blocks,'n':n,'clauses':len(cl),
             'unsat_circuit_count':len(g['proof']['circuits']),
             'unsat_nodes':g['producer_nodes_visited'],'unsat_bound':g['proof']['bound'],
             'unsat_producer_ms':elapsed,
             'unsat_receipt_bytes':len(json.dumps(g,sort_keys=True,separators=(',',':'))),
             'sat_fourier_rank':rank,'sat_exact_ground':ground,
             'sat_ground_reconstruction_ms':sat_elapsed,
             'gaussian_row_reductions':g['producer_discovery']['gaussian_row_reductions']})
    return {'seed':seed,'node_budget_random':budget,
            'random_3sat':rows,'strided_parity_cycles':structured,
            'timing_note':'One local Python run; each producer internally checks its own receipt; times are not calibrated or cross-host comparisons.'}

if __name__=='__main__':
    print(json.dumps(campaign(),indent=2))
