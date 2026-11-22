#!/usr/bin/env python3
"""SPN-009: same-CNF language-selection campaign with full goal cost accounting.

Runs fixed decision, fixed #SAT, source-eligible spectral exact minimum,
and the adaptive compiler on matched inputs. Source generation and exhaustive
oracle are tracked separately; all selected receipts are source-checked.
"""
from __future__ import annotations
import json
import platform
import random
from time import perf_counter
from pathlib import Path

from direct_sat_campaign import formula_samples,brute_count
from direct_sat_compiler import produce_direct_sat,verify_direct_sat,spectral_form
from adaptive_ground_compiler import produce_adaptive_receipt,verify_adaptive_receipt
from language_choice_sat import compile_language,verify_language_receipt
from test_direct_sat_compiler import parity_cycle_family
from test_direct_sum_grounds import shared_variable_cycle_cnf
import frontier_ground as png


def as_cnf(spn_rows):
    return [tuple(v+1 if bit==0 else -(v+1) for v,bit in zip(scope,bits))
            for scope,bits in spn_rows]


def timed(fn):
    start=perf_counter();x=fn();return x,round((perf_counter()-start)*1000,5)


def sizeof(obj):
    return len(json.dumps(obj,sort_keys=True,separators=(',',':')).encode())


def cases():
    # Same 121 small instances as SPN-008; finite exhaustive reference.
    for name,n,clauses in formula_samples():
        yield name,n,clauses,True
    # High-rank source-variable overlap but small Fourier direct-sum blocks.
    for blocks in (2,6,12,24):
        for frustrated in (True,False):
            rows,n=shared_variable_cycle_cnf(blocks,frustrated=frustrated)
            yield f'overlap-rank2-{blocks}-'+('unsat' if frustrated else 'sat'),n,as_cnf(rows),blocks<=6
    for blocks in (1,4,12):
        for frustrated in (False,True):
            clauses,n=parity_cycle_family(blocks,frustrated)
            yield f'xor-cycle-{blocks}-'+('unsat' if frustrated else 'sat'),n,clauses,blocks==1
    # Small full-CNF guarded parity that SFI-001 may be able to recognize.
    yield 'guarded-xor-3',3,[(1,-2,3),(1,-2,-3),(-1,2,3),(-1,2,-3)],True


def campaign():
    rows=[]
    for name,n,clauses,exhaustive in cases():
        truth=brute_count(clauses,n) if exhaustive else None
        direct,dt=timed(lambda:produce_direct_sat(clauses,n,node_budget=512))
        assert verify_direct_sat(clauses,n,direct)==direct['result']
        if truth is not None and direct['result']!='UNKNOWN':
            assert direct['result']==('SAT' if truth else 'UNSAT'),name
        decision,decision_ms=timed(lambda:compile_language(clauses,n,goal='decision',
                              node_budget=512,rank_cap=3,frontier_cell_cap=200000))
        assert verify_language_receipt(clauses,n,decision)==decision['result']
        count,count_ms=timed(lambda:compile_language(clauses,n,goal='count',
                              rank_cap=3,frontier_cell_cap=200000,allow_sfi=True))
        assert verify_language_receipt(clauses,n,count)==count['result']
        if truth is not None:
            assert count['result']==str(truth),name
            assert decision['result']==('SAT' if truth else 'UNSAT'),name
        if count['result']!='UNKNOWN':
            assert decision['result']==('SAT' if int(count['result']) else 'UNSAT'),name
        row={'case':name,'n':n,'clauses':len(clauses),'reference_count':truth,
             'direct':{'result':direct['result'],'ms':dt,'bytes':sizeof(direct),
                'kind':direct['proof']['kind']},
             'selection_decision':{'result':decision['result'],'ms':decision_ms,
                'bytes':sizeof(decision),'language':decision['language'],
                'attempts':decision['cost_ledger']['attempts']},
             'selection_count':{'result':count['result'],'ms':count_ms,
                'bytes':sizeof(count),'language':count['language'],
                'attempts':count['cost_ledger']['attempts']}}
        # Fixed PNG-001 baseline does exact #SAT; do not compare it to an
        # existence-only runtime without clearly stating the different goal.
        if n<=50:
            (models,witness,ledger),png_ms=timed(lambda:png.solve(clauses,n))
            if truth is not None:assert models==truth,name
            if count['result']!='UNKNOWN':assert models==int(count['result']),name
            row['fixed_frontier_count']={'count':str(models),'ms':png_ms,
                'projected_entries':ledger['projected_entries'],
                'max_scope':ledger['max_scope']}
        if (n<=12 and spectral_form(clauses,n) is not None):
            spn=spectral_form(clauses,n)
            spec,spec_ms=timed(lambda:produce_adaptive_receipt(spn,n,
                                      goal='exact_ground',rank_cap=3))
            assert verify_adaptive_receipt(spn,n,spec)==spec['result']
            row['fixed_spectral_exact']={'result':spec['result'],'ms':spec_ms,
                'ground_degeneracy':spec['ground_degeneracy']}
            if truth is not None and spec['result']!='UNKNOWN' and spec['ground_energy']==[0,1]:
                assert int(spec['ground_degeneracy'])==truth,name
        rows.append(row)
    # Hardness probe is separate: it may return UNKNOWN. No large truth oracle.
    rng=random.Random(49009)
    harder=[]
    for n in (48,64,80):
        for index in range(5):
            cls=[tuple(v if rng.randrange(2) else -v for v in rng.sample(range(1,n+1),3))
                 for _ in range(round(4.26*n))]
            d,ms=timed(lambda:compile_language(cls,n,goal='decision',node_budget=256))
            assert verify_language_receipt(cls,n,d)==d['result']
            harder.append({'n':n,'index':index,'outcome':d['result'],
                           'language':d['language'],'elapsed_ms':ms})
    grouped={}
    for row in rows:
        if row['case'].startswith('random'):group='random'
        elif row['case'].startswith('planted'):group='planted'
        elif row['case'].startswith('pigeonhole'):group='pigeonhole'
        elif row['case'].startswith('overlap'):group='spectral_overlap'
        elif row['case'].startswith('xor'):group='source_xor'
        else:group='guarded_xor'
        g=grouped.setdefault(group,{'cases':0,'decision_methods':{},'count_methods':{},
                    'decision_ms':0,'count_ms':0,'fixed_direct_ms':0,
                    'known_count_refusals':0,'known_decision_refusals':0})
        g['cases']+=1
        for field,role in [('selection_decision','decision'),('selection_count','count')]:
            method=row[field]['language']
            g[f'{role}_methods'][method]=g[f'{role}_methods'].get(method,0)+1
            g[f'{role}_ms']+=row[field]['ms']
        g['fixed_direct_ms']+=row['direct']['ms']
        g['known_count_refusals']+=row['selection_count']['result']=='UNKNOWN'
        g['known_decision_refusals']+=row['selection_decision']['result']=='UNKNOWN'
    for row in grouped.values():
        for field in ('decision_ms','count_ms','fixed_direct_ms'):
            row[field]=round(row[field],3)
    return {'schema':'SPN-009-matched-language-choice-v1',
            'environment':{'python':platform.python_version(),
                'parallelism':'one local single-process run, no calibrated hardware comparisons'},
            'selected_budgets':{'decision_nodes':512,'spectral_rank':3,
                'frontier_cells':200000},
            'summary':grouped,'cases':rows,'large_budgeted_decision':harder,
            'epistemic_status':{
              'small_finite':'independent full-truth enumeration',
              'structured_large':'source-bound certificates; PNG factor replay on selected <=50 variable cases',
              'larger_random':'checked answers or explicit UNKNOWN; no exhaustive oracle',
              'elapsed_ms':'observed on this process, not asymptotic or independently calibrated',
              'SFI':'SFI-001 used only when complete source modules are importable and policy chooses it'},
            'claim_boundary':'No general polynomial-time SAT/#SAT method or P versus NP result.'}


if __name__=='__main__':
    result=campaign()
    dest=Path(__file__).with_name('language_choice_results.json')
    dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'summary':result['summary'],
                     'hard':result['large_budgeted_decision']},indent=2))
