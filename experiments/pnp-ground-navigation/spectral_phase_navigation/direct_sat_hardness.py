#!/usr/bin/env python3
"""Bounded direct SAT stress across increasing n, not asymptotic evidence.

Source-bound certificates are checked for every SAT/UNSAT. Unresolved
instances remain UNKNOWN. Dense instances are generated deterministically.
"""
import json
from random import Random
from time import perf_counter
from direct_sat_compiler import produce_direct_sat,verify_direct_sat,spectral_form
from adaptive_ground_compiler import produce_adaptive_receipt,verify_adaptive_receipt


def campaign(seed=80488):
    rng=Random(seed)
    rows=[]
    for n,count in ((16,12),(20,12),(24,12),(28,12),(36,12),(48,12),(64,8),(80,8),(96,8),(120,4)):
        group={'n':n,'m':round(4.26*n),'samples':count,'seed':seed,
               'dpll_256':{'SAT':0,'UNSAT':0,'UNKNOWN':0},
               'dpll_2048':{'SAT':0,'UNSAT':0,'UNKNOWN':0},
               'total_ms_256':0.,'total_ms_2048':0.,
               'nodes_256':0,'nodes_2048':0,
               'spectral_128':{'SAT':0,'UNSAT':0,'UNKNOWN':0},
               'spectral_evaluated':0,'spectral_total_ms':0.,
               'recovered_from_256_unknown_by_2048':0,
               'source_hashes':[]}
        for sample in range(count):
            cls=[tuple(v if rng.randrange(2) else -v
                       for v in rng.sample(range(1,n+1),3))
                 for _ in range(group['m'])]
            statuses={}
            for budget in (256,2048):
                start=perf_counter()
                receipt=produce_direct_sat(cls,n,node_budget=budget)
                elapsed=(perf_counter()-start)*1000
                status=verify_direct_sat(cls,n,receipt)
                group[f'dpll_{budget}'][status]+=1
                group[f'total_ms_{budget}']+=elapsed
                group[f'nodes_{budget}']+=next((a['nodes'] for a in receipt['producer_ledger']['attempts']
                     if a['method']=='source_dpll'),0)
                statuses[budget]=status
                if sample==0 and budget==256:group['source_hashes'].append(receipt['source_sha256'])
            if (statuses[256]!='UNKNOWN' and statuses[2048]!='UNKNOWN' and
                    statuses[256]!=statuses[2048]):
                raise AssertionError('contradictory valid direct decisions')
            if statuses[256]=='UNKNOWN' and statuses[2048]!='UNKNOWN':
                group['recovered_from_256_unknown_by_2048']+=1
            if n<=24 and sample<4:
                start=perf_counter()
                spectrum=spectral_form(cls,n)
                receipt=produce_adaptive_receipt(spectrum,n,node_budget=128,rank_cap=3)
                elapsed=(perf_counter()-start)*1000
                status=verify_adaptive_receipt(spectrum,n,receipt)
                group['spectral_128'][status]+=1
                group['spectral_evaluated']+=1
                group['spectral_total_ms']+=elapsed
                for other in statuses.values():
                    if other!='UNKNOWN' and status!='UNKNOWN' and other!=status:
                        raise AssertionError('contradictory accepted solver receipts')
        for key in ('total_ms_256','total_ms_2048','spectral_total_ms'):
            group[key]=round(group[key],3)
        rows.append(group)
    return {'experiment':'SPN-008 increasing-n near-density 4.26 bounded tests',
            'note':'source-bound decisions only; UNKNOWN explicitly preserved; not a worst-case or threshold proof',
            'results':rows}

if __name__=='__main__':print(json.dumps(campaign(),indent=2))
