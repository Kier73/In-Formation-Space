#!/usr/bin/env python3
"""GRC-001: reproducible source-revision benchmarks; not a solver speedup claim."""
import json
import platform
import random
import statistics
from time import perf_counter

from direct_sat_compiler import check_assignment
from language_choice_sat import compile_language,verify_language_receipt
from ground_revision_continuity import construct_revision,verify_revision


def run():
    cases=[('implied-clause-200',200,[(1,)],[(1,),(1,2,3)]),
           ('delta-count-3',3,[(1,2),(-1,2)],[(1,2),(-1,2),(1,)]),
           ('monotone-zero-24',24,[(1,),(-1,)],[(1,),(-1,),(2,3)]),
           ('semantic-equivalent-24',24,[(1,2),(-1,2)],
                  [(2,1),(-1,2),(1,2),(3,-3)])]
    rng=random.Random(726114)
    for i in range(40):
        n=6+(i%3)
        old=[]
        for _ in range(2*n):
            vs=rng.sample(range(1,n+1),rng.randint(1,3))
            old.append(tuple(v if rng.randrange(2) else -v for v in vs))
        vs=rng.sample(range(1,n+1),rng.randint(1,3))
        new=old+[tuple(v if rng.randrange(2) else -v for v in vs)]
        cases.append((f'seeded-{i:02d}',n,old,new))
    out=[]
    for name,n,old,new in cases:
        t=perf_counter()
        baseline=compile_language(old,n,goal='count',allow_sfi=False)
        baseline_ms=(perf_counter()-t)*1000
        t=perf_counter()
        revision=construct_revision(old,new,n,baseline)
        revision_ms=(perf_counter()-t)*1000
        assert verify_revision(old,new,n,revision)==revision['result']
        t=perf_counter()
        fresh=compile_language(new,n,goal='count',allow_sfi=False)
        fresh_ms=(perf_counter()-t)*1000
        assert verify_language_receipt(new,n,fresh)==fresh['result']
        assert revision['result']==fresh['result']
        if n<=12:
            brute=sum(check_assignment(new,[(mask>>j)&1 for j in range(n)])
                      for mask in range(1<<n))
            assert str(brute)==fresh['result']
        out.append({'name':name,'n':n,'old_clauses':len(old),
                    'added_clauses':len(new)-len(old),
                    'old_models':baseline['result'],'new_models':revision['result'],
                    'method':[s['kind'] for s in revision['steps']],
                    'old_compilation_ms':round(baseline_ms,4),
                    'revision_produce_and_self_check_ms':round(revision_ms,4),
                    'fresh_recount_and_self_check_ms':round(fresh_ms,4),
                    'revision_receipt_bytes':len(json.dumps(revision).encode())})
    groups={}
    for row in out:
        key=row['method'][0] if row['method'] else 'no_new_semantic_constraint'
        groups.setdefault(key,[]).append(row)
    return {'schema':'grc.sat.incremental-campaign.v1',
            'python':platform.python_version(),
            'case_count':len(out),'all_revisions_agree_with_fresh_count':True,
            'groups':{key:{'instances':len(rows),
                            'median_revision_ms':round(statistics.median(x['revision_produce_and_self_check_ms'] for x in rows),4),
                            'median_fresh_recount_ms':round(statistics.median(x['fresh_recount_and_self_check_ms'] for x in rows),4)}
                      for key,rows in groups.items()},
            'cases':out}

if __name__=='__main__':
    print(json.dumps(run(),indent=2))
