"""Reproducible PNG-003 campaign and portable evidence receipts (standard library)."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from time import perf_counter

from algebraic_ground import (compile_ground, encode_xor, frontier_estimate,
                              planted_dense, random_cubic_tseitin)
from derived_ground import compile_proven_ground, implication_equalities, split_guard
from derived_verifier import verify_receipt
from frontier_ground import brute_count, random_3cnf

HERE = Path(__file__).resolve().parent


def cases():
    pure, _, _ = planted_dense(96, 8, 22, False)
    mixed, _, _ = planted_dense(96, 8, 22, True)
    tseitin, nt, _ = random_cubic_tseitin(80, 7301)
    chain, nc = implication_equalities(12)
    chain_unsat, nu = implication_equalities(5)
    hidden_parity = split_guard(encode_xor(0b1111,1),guard_id=5)
    return [
        ('two-guards-dense-98', split_guard(split_guard(pure,guard_id=97),guard_id=98),98,{}),
        ('two-guards-mixed-98', split_guard(split_guard(mixed,guard_id=97),guard_id=98),98,{}),
        ('guarded-tseitin-121', split_guard(tseitin,guard_id=nt+1),nt+1,{}),
        ('non-twin-implication-23', chain,nc,{}),
        ('nonlocal-unsat-9', chain_unsat+[(1,),(-5,)],nu,{}),
        ('incomplete-guard-5', hidden_parity[:-1],5,{}),
        ('random-35-budget-refusal', random_3cnf(35,140,73),35,
            {'max_resolution_attempts':1}),
    ]


def campaign(*, write_receipts=False):
    results=[]
    if write_receipts:
        (HERE/'receipts_png003').mkdir(exist_ok=True)
    for name, clauses, n, kwargs in cases():
        input_generation_done = perf_counter()
        discovered_direct = len(compile_ground(clauses,n)['equations'])
        receipt=compile_proven_ground(clauses,n,**kwargs)
        verified_start=perf_counter()
        verification=verify_receipt(receipt)
        verification_ms=round((perf_counter()-verified_start)*1000,3)
        estimate=frontier_estimate(clauses,n)
        if n<=16:
            reference=brute_count(clauses,n)
            if receipt['result']['count']!=reference:
                raise AssertionError('original CNF exhaustive reference disagrees')
        entry={'name':name,'n':n,'original_clauses':len(clauses),
            'direct_png002_equations':discovered_direct,
            'status':receipt['result']['status'],'count':receipt['result']['count'],
            'method':receipt['result']['method'],
            'rank':receipt['result']['ledger']['rank'],
            'free_dimension':receipt['result']['ledger']['free_dimension'],
            'ordinary_min_fill_estimate':estimate,
            'construction':receipt['compilation_ledger'],
            'independent_verification':verification,
            'independent_verification_ms':verification_ms,
            'source_sha256':receipt['source_sha256'],
            'ground_sha256':receipt['ground_sha256']}
        results.append(entry)
        if write_receipts:
            (HERE/'receipts_png003'/(name+'.json')).write_text(
                json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return {'research_id':'PNG-003','environment':{'python':platform.python_version(),
                'platform':platform.platform(),
                'mode':'single-process CPU, Python standard library, deterministic synthetic fixtures'},
            'measurement':'single local run; construction and verifier times separate; generation excluded',
            'cases':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--write-results',action='store_true')
    parser.add_argument('--write-receipts',action='store_true')
    args=parser.parse_args()
    report=campaign(write_receipts=args.write_receipts)
    if args.write_results:
        (HERE/'PNG-003-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    for case in report['cases']:
        print(json.dumps({k:case[k] for k in ('name','n','original_clauses','status','count','rank','free_dimension','direct_png002_equations','independent_verification_ms')}|
              {'ground_ms':case['construction']['elapsed_ms'],
               'contractions':case['construction']['contraction']['contractions'],
               'derived_parity':case['construction']['learned_equations'],
               'resolution_proof_steps':case['construction']['proof_steps'],
               'verified_count':case['independent_verification']['count_verified']}))
