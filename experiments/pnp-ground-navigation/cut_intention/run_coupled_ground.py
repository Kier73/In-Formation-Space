"""CIG-002: repeatable wall-clock ledger and native PNG-001 control when available.

Usage from experiments/pnp-ground-navigation/cut_intention/:
    python run_coupled_ground.py > CIG-002-results.json

No network, no hidden result cache, no asserted universal complexity advantage.
"""
from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from coupled_ground import compile_ground, make_one_clause_source
from verify_coupled_ground import verify

# Use the repository's *actual* PNG-001 factor-elimination implementation.
PARENT=Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:sys.path.insert(0,str(PARENT))
try:
    from frontier_ground import solve as png_solve,verify_assignment as png_verify
except ImportError:
    png_solve=None


def _case(k,ell,kind,repetitions=9):
    source,cut=make_one_clause_source(k,ell,kind)
    results={}
    for intent in ('SAT','#SAT','CUT_RANK'):
        runtimes=[];samples=[]
        for _ in range(repetitions):
            start=perf_counter_ns()
            cert,ledger=compile_ground(source,intent,cut if intent=='CUT_RANK' else None)
            verify(source,cert)
            total=perf_counter_ns()-start
            samples.append((cert,ledger))
            runtimes.append(total/1e6)
        cert,ledger=samples[0]
        results[intent]={'median_construct_and_independent_verify_ms':round(median(runtimes),4),
                         'source_and_ground_digest':cert['source_digest'],
                         'ground_bytes':len(json.dumps(cert,sort_keys=True,separators=(',',':')).encode()),
                         'work':cert['work'],
                         'result':({k:v for k,v in cert['result'].items() if k!='witness'} if intent!='SAT'
                                   else {'status':cert['result']['status'],'witness_verified':True})}
    if png_solve is not None:
        # PNG is applied to exactly the source-qualified active-label residual,
        # so we compare the same reduced computation and charge its construction.
        reduced=cert['reduced_cnf']; r=len(cert['active_labels'])
        if r>0 and not any(not c for c in reduced):
            start=perf_counter_ns()
            counted,witness,stats=png_solve(reduced,r)
            elapsed=(perf_counter_ns()-start)/1e6
            assert counted*(1<<(k*(k-1)*ell//2-r))==int(results['#SAT']['result']['count'])
            assert witness is None or png_verify(reduced,witness)
            results['native_png_reduced_control']={
                'status':'executed','count_active':counted,
                'elapsed_total_ms':round(elapsed,4),
                'factor_lookups':stats['factor_lookups'],
                'projected_entries':stats['projected_entries'],
                'max_scope':stats['max_scope']}
        else:
            results['native_png_reduced_control']={'status':'not_applicable_empty_or_zero_active'}
    else:
        results['native_png_reduced_control']={'status':'not_available_outside_repo_checkout'}
    return {'case':f'k{k}-ell{ell}-{kind}','n_source':source['base']['n'],
            'source_clauses':len(source['base']['clauses'])+len(source['coupling']),
            'cut':list(cut),'coupling':source['coupling'],'intentions':results}


def campaign():
    cases=[]
    for k,ell in ((4,1),(12,1),(24,2)):
        for kind in ('none','cross-cross','left-right','left-cross'):
            cases.append(_case(k,ell,kind))
    return {'schema':'ifs.cut-intention-coupled-benchmark.v1',
            'environment':{'python':platform.python_version(),'platform':platform.platform(),
                           'runner':'single-process standard-library Python',
                           'trials_per_intention':9},
            'accounting':'construct + independently verify original source each trial; reducer control is a separately charged operation',
            'cases':cases}

if __name__=='__main__':print(json.dumps(campaign(),indent=2,sort_keys=True))
