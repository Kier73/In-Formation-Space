#!/usr/bin/env python3
"""SPN-008 matched *direct SAT* experiment against PNG-001 and SPN-007.

Run from spectral_phase_navigation directory in the normal GitHub checkout.
It imports PNG-001's actual sibling ``frontier_ground.py``. An unpacked
staging directory also works if the identical reference is placed beside it.
One local timing sample; never an asymptotic/runtime superiority claim.
"""
import json
import random
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import frontier_ground as png
from adaptive_ground_compiler import produce_adaptive_receipt,verify_adaptive_receipt
from direct_sat_compiler import (check_assignment,produce_direct_sat,
                                 spectral_form,verify_direct_sat)
from test_direct_sat_compiler import parity_cycle_family


def _bytes(obj):
    return len(json.dumps(obj,sort_keys=True,separators=(',',':')).encode())


def _ms(fn):
    start=perf_counter()
    return fn(),(perf_counter()-start)*1000


def brute_count(clauses,n):
    return sum(check_assignment(clauses,[(mask>>i)&1 for i in range(n)])
               for mask in range(1<<n))


def formula_samples():
    rng=random.Random(84008)
    for n,m in ((8,34),(10,43),(12,51)):
        for i in range(30):
            yield f'random-3sat-{n}-{i}',n,[tuple(v if rng.randrange(2) else -v
                     for v in rng.sample(range(1,n+1),3)) for _ in range(m)]
    for n in (8,10,12):
        for i in range(10):
            planted=[rng.randrange(2) for _ in range(n)]
            cls=[]
            for _ in range(4*n):
                scope=rng.sample(range(1,n+1),3)
                while True:
                    clause=tuple(v if rng.randrange(2) else -v for v in scope)
                    if check_assignment([clause],planted):break
                cls.append(clause)
            yield f'planted-3sat-{n}-{i}',n,cls
    # Pigeonhole principle: 4 pigeons / 3 holes (UNSAT, mixed width 2-3)
    n=12;cls=[]
    for p in range(4):
        cls.append(tuple(1+3*p+h for h in range(3)))
    for h in range(3):
        for p in range(4):
            for q in range(p+1,4):
                cls.append((-(1+3*p+h),-(1+3*q+h)))
    yield 'pigeonhole-4-3',n,cls


def campaign():
    data=[]
    for name,n,clauses in formula_samples():
        truth_count=brute_count(clauses,n)
        truth='SAT' if truth_count else 'UNSAT'
        direct,dt=_ms(lambda:produce_direct_sat(clauses,n,node_budget=512))
        assert verify_direct_sat(clauses,n,direct)==direct['result']==truth,name
        # Time all PNG cost, including factor construction and ordering.
        (count_png,witness_png,ledger_png),full_png_ms=_ms(lambda:png.solve(clauses,n))
        assert count_png==truth_count,name
        assert witness_png is None if count_png==0 else png.verify_assignment(clauses,witness_png)
        spe=spectral_form(clauses,n)
        spec=None
        if spe is not None:
            spec,st=_ms(lambda:produce_adaptive_receipt(spe,n,goal='decision',rank_cap=3,
                                                          node_budget=512))
            assert verify_adaptive_receipt(spe,n,spec)==truth,name
        row={'case':name,'n':n,'m':len(clauses),'sat':truth,
             'reference_solution_count':truth_count,
             'direct_kind':direct['proof']['kind'],'direct_status':direct['result'],
             'direct_ms':round(dt,4),'direct_proof_bytes':_bytes(direct),
             'direct_dpll_nodes':next((a['nodes'] for a in direct['producer_ledger']['attempts']
                                        if a['method']=='source_dpll'),0),
             'png_full_ms':round(full_png_ms,4),'png_width':ledger_png['max_scope'],
             'png_factor_lookups':ledger_png['factor_lookups'],
             'png_projected_entries':ledger_png['projected_entries']}
        if spec is not None:
            row.update(spectral_status=spec['result'],spectral_ms=round(st,4),
                       spectral_bytes=_bytes(spec),
                       spectral_method=spec['producer_policy']['selected_method'],
                       spectral_fallback_nodes=spec['producer_policy']['discovery'].get('decision_nodes_visited',0))
        data.append(row)
    groups={}
    for row in data:
        group='random_3sat' if row['case'].startswith('random') else (
            'planted_3sat' if row['case'].startswith('planted') else 'pigeonhole')
        d=groups.setdefault(group,{'cases':0,'sat':0,'unsat':0,
                        'direct_ms':0.,'png_ms':0.,'spectral_ms':0.,
                        'direct_nodes':0,'spectral_fallback_nodes':0,
                        'direct_receipt_bytes':0,'spectral_receipt_bytes':0})
        d['cases']+=1;d[row['sat'].lower()]+=1
        for dest,src in [('direct_ms','direct_ms'),('png_ms','png_full_ms'),
                         ('spectral_ms','spectral_ms'),('direct_nodes','direct_dpll_nodes'),
                         ('spectral_fallback_nodes','spectral_fallback_nodes'),
                         ('direct_receipt_bytes','direct_proof_bytes'),
                         ('spectral_receipt_bytes','spectral_bytes')]:
            d[dest]+=row.get(src,0)
    for d in groups.values():
        for key in ('direct_ms','png_ms','spectral_ms'):d[key]=round(d[key],3)
    structured=[]
    for blocks in (1,2,4,10,20):
        for frustrated in (False,True):
            clauses,n=parity_cycle_family(blocks,frustrated)
            direct,dt=_ms(lambda:produce_direct_sat(clauses,n,node_budget=64))
            assert verify_direct_sat(clauses,n,direct)==('UNSAT' if frustrated else 'SAT')
            spe=spectral_form(clauses,n)
            spectral,st=_ms(lambda:produce_adaptive_receipt(spe,n,goal='decision',rank_cap=3,
                                                               node_budget=64))
            assert verify_adaptive_receipt(spe,n,spectral)==direct['result']
            # Actual PNG same-source count exact for these disconnected 6-var blocks.
            (p_count,p_wit,p_audit),pt=_ms(lambda:png.solve(clauses,n))
            assert (p_count>0)==(not frustrated)
            assert (p_wit is None) == frustrated
            structured.append({'blocks':blocks,'n':n,'m':len(clauses),
              'sat':direct['result'],'direct_kind':direct['proof']['kind'],
              'direct_ms':round(dt,4),'direct_bytes':_bytes(direct),
              'spectral_ms':round(st,4),'spectral_bytes':_bytes(spectral),
              'spectral_method':spectral['producer_policy']['selected_method'],
              'png_ms':round(pt,4),'png_width':p_audit['max_scope'],
              'png_factor_lookups':p_audit['factor_lookups'],
              'png_count_digits':len(str(p_count))})
    return {'experiment':'SPN-008 direct SAT matched benchmark',
            'seed':84008,'direct_node_budget':512,'spectral_node_budget':512,
            'sampled_groups':groups,'cases':data,'xor_family':structured,
            'evidence':'small cases independently exhaustively counted; all direct and spectral decisions checked from source; large structured XOR cases source-bound direct/ spectral certificates plus PNG exact count recurrence; timings are single-run observations',
            'cautions':'variable elimination PNG count is not separately encoded as an UNSAT proof here; all computation and verification contribute to observed times; P vs NP remains open'}


if __name__=='__main__':
    print(json.dumps(campaign(),indent=2))
