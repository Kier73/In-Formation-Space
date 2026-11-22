"""BENCH-01H: compare algebraic, source-variable, native SPN and CDCL paths."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from time import perf_counter_ns

from bench01_algebraic import build, verify, cycle_xor
from bench01_separator import run as separator_run, verify_receipt as separator_verify


def _case(case_id,n,clauses,origin,expected=None):
    return {'id':case_id,'n':n,'clauses':[list(c) for c in clauses],
            'origin':origin,'expected':expected}


def fixtures():
    from random import Random
    r=Random(8172)
    generic=[]
    for _ in range(52):
        v=r.sample(range(1,17),3)
        generic.append([x*r.choice((-1,1)) for x in v])
    return [
      _case('xor-cycle-19-sat',19,cycle_xor(19),'source-generated-strict-3xor','SAT'),
      _case('xor-cycle-31-sat',31,cycle_xor(31),'source-generated-strict-3xor','SAT'),
      _case('xor-cycle-80-sat',80,cycle_xor(80),'source-generated-strict-3xor','SAT'),
      _case('xor-cycle-31-unsat',31,cycle_xor(31,unsat=True),'source-generated-conflicting-3xor','UNSAT'),
      _case('unstructured-16',16,generic,'seeded-unstructured-3cnf',None),
    ]


def one(item,*,cdcl=False,spn=False,require_native=False,coordinate_rank=6,coordinate_cells=4096,seconds=8):
    from bench01_3sat import run_case
    n,src=item['n'],item['clauses']
    t=perf_counter_ns(); algebraic=build(src,n,max_rank=coordinate_rank,max_cells=coordinate_cells)
    a_ms=(perf_counter_ns()-t)/1e6
    t=perf_counter_ns();check=verify(src,n,algebraic)
    v_ms=(perf_counter_ns()-t)/1e6
    if require_native and not algebraic['observation']['native_spn007_used']:
        raise AssertionError('the native SPN-007 fundamental circuit utility was NOT executed')
    t=perf_counter_ns();cut=separator_run(src,n,max_cut=1)
    cut_ms=(perf_counter_ns()-t)/1e6
    t=perf_counter_ns();cut_status=separator_verify(src,n,cut)
    cut_verify_ms=(perf_counter_ns()-t)/1e6
    if item['expected'] is not None and check['status'] in ('SAT','UNSAT') and check['status']!=item['expected']:
        raise AssertionError('qualified coordinates disagree with source-generated known result')
    if check['status'] in ('SAT','UNSAT') and cut_status in ('SAT','UNSAT') and check['status']!=cut_status:
        raise AssertionError('two qualified source interpreters disagree')
    record={'id':item['id'],'source':{'n':n,'clauses':len(src),
         'source_sha256':algebraic['source_sha256'],'origin':item['origin'],
         'fixture_expected':item['expected']},
        'algebraic':{'status':check['status'],'model_count':check['count'],
            'rank':check['global_rank'],'components':len(algebraic['components']),
            'coordinates_checked':sum(c['coordinates_evaluated'] for c in algebraic['components']),
            'build_ms':round(a_ms,4),'verification_ms':round(v_ms,4),
            'total_ms':round(a_ms+v_ms,4),
            'native_spn007_used':algebraic['observation']['native_spn007_used']},
        'variable_separator':{'status':cut_status,'count':cut['count'],
            'separator':cut['separator'],'total_ms':round(cut_ms+cut_verify_ms,4)}}
    if spn:
        sp=run_case({'id':item['id'],'n':n,'clauses':src,'origin':item['origin']},
                    timeout=seconds,spn_fallback=True,spn_nodes=8192,
                    max_source_vars=0,max_spn_vars=128,max_spn_clauses=4096,
                    resolution_attempts=256)
        if sp['status'] in ('SAT','UNSAT') and check['status'] in ('SAT','UNSAT') and sp['status']!=check['status']:
            raise AssertionError('source-verified SPN disagrees with Fourier proof')
        record['direct_spn008']={'status':sp['status'],'wall_ms':sp['wall_ms'],
             'verification':sp['verification'],'reason':sp.get('reason')}
    if cdcl:
        from bench01_external import run_cdcl
        d=run_cdcl(n,src,timeout=seconds)
        if d['accepted']=='UNVERIFIED_UNSAT':
            if check['status']=='UNSAT':
                d['accepted']='UNSAT'
                d['reason']='independent-source-Fourier-coordinate-refutation'
            elif spn and sp['status']=='UNSAT':
                # SPN-008's proof has crossed the worker boundary and was
                # independently replayed against the original CNF by run_case.
                d['accepted']='UNSAT'
                d['reason']='independent-original-source-SPN008-refutation'
        if d['accepted'] in ('SAT','UNSAT') and check['status'] in ('SAT','UNSAT') and d['accepted']!=check['status']:
            raise AssertionError('source-qualified CDCL contradicts algebraic certificate')
        record['cdcl_cadical195']={k:d.get(k) for k in ('claim','accepted','reason','wall_ms','engine_ms')}
    return record


def campaign(*,include_external=False,cdcl=False,spn=False,require_native=False,seconds=8):
    cases=fixtures()
    if include_external:
        from bench01_external import manifest,fetch_one
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            for ent in manifest()[:2]:
                _path,data=fetch_one(ent,Path(td),timeout=seconds)
                cases.append(_case(ent['id'],data['n'],data['clauses'],
                                   'third-party-Git-SHA1-pinned-'+ent['github_blob_sha1'],None))
    result=[one(item,cdcl=cdcl,spn=spn,require_native=require_native,seconds=seconds) for item in cases]
    return {'schema':'ifs.bench01h.coordinate-representation-comparison.v1',
            'scope':'finite strict 3-CNF only; independent exact source verification; no P-vs-NP claim',
            'source_pins':{'repository':'Kier73/In-Formation-Space',
                           'cross_repos':'SPN-007, SFI-002, BENCH-01G, BENCH-01E'},
            'record_count':len(result),'records':result}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--external',action='store_true')
    p.add_argument('--cdcl',action='store_true')
    p.add_argument('--spn',action='store_true')
    p.add_argument('--require-native',action='store_true')
    p.add_argument('--timeout',type=float,default=8.)
    p.add_argument('--output',default='BENCH01H-results.json')
    args=p.parse_args()
    report=campaign(include_external=args.external,cdcl=args.cdcl,spn=args.spn,
                    require_native=args.require_native,seconds=args.timeout)
    out=Path(__file__).with_name(args.output)
    out.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'saved':str(out),'instances':report['record_count'],
        'decisions':[(x['id'],x['algebraic']['status'],x['variable_separator']['status']) for x in report['records']]},indent=2))

if __name__=='__main__':main()
