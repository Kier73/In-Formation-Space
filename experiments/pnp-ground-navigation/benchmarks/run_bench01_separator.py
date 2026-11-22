"""Reproduce BENCH-01G source-qualified separator experiments; charge replay."""
from __future__ import annotations
from pathlib import Path
import json
from time import perf_counter

from bench01_separator import run,verify_receipt
from test_bench01_separator import fixture,seven
from self_selecting_sat import choose_composite


def campaign():
    records=[]
    for name,(cnf,n) in [('interleaved',seven()),('connected-structured',fixture())]:
        t=perf_counter();baseline=choose_composite(cnf,n);base_ms=(perf_counter()-t)*1000
        t=perf_counter();result=run(cnf,n);build_ms=(perf_counter()-t)*1000
        t=perf_counter();admitted=verify_receipt(cnf,n,result);proof_ms=(perf_counter()-t)*1000
        records.append({'id':name,'original_variables':n,'clauses':len(cnf),
             'baseline':{'status':baseline['status'],'count':baseline['count'],
                         'elapsed_ms':round(base_ms,3)},
             'separator':result['separator'],'branch_components':[
                     b['component_count'] for b in result['branches']],
             'verified_status':admitted,'verified_count':result['count'],
             'construction_execution_ms':round(build_ms,3),
             'verification_replay_ms':round(proof_ms,3),
             'total_ms':round(build_ms+proof_ms,3),
             'source_sha256':result['source_sha256']})
    return {'schema':'ifs.bench01.separator-campaign.v1','records':records,
            'note':'local single-run timings include source-verified rerun; not CDCL ranking'}


if __name__=='__main__':
    data=campaign()
    path=Path(__file__).with_name('BENCH01-structural-results.json')
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    print(json.dumps(data,indent=2))
