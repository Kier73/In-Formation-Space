#!/usr/bin/env python3
"""SPN-010: regression probe for redundant compilation scans.

Old behavior is emulated by (i) the unnecessary spectral eligibility scan
on a small decision case and (ii) re-invoking full XOR recognition from its
already screened direct-SAT fallback. This is not an archival old-checkout
benchmark; it isolates the work removed by the code changes.
"""
from __future__ import annotations
import json,random
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import language_choice_sat as choice
import direct_sat_compiler as direct


def cases(seed=78001):
    rng=random.Random(seed)
    for n in (8,10,12,14):
        for j in range(15):
            clauses=[tuple(v if rng.randrange(2) else -v for v in
                         rng.sample(range(1,n+1),3)) for k in range(round(4.26*n))]
            yield f'random-{n}-{j}',clauses,n


def trace(clauses,n,emulate_pre_fix):
    counters={'parity_scans':0,'spectral_conversions':0}
    original_parity=choice.parity_blocks
    original_spectral=choice.spectral_form
    original_direct=choice.produce_direct_sat
    def audited_parity(*args,**kwargs):
        counters['parity_scans']+=1
        return original_parity(*args,**kwargs)
    def audited_spectral(*args,**kwargs):
        counters['spectral_conversions']+=1
        return original_spectral(*args,**kwargs)
    def original_redundant_fallback(*args,**kwargs):
        kwargs.pop('skip_complete_xor',None)
        return original_direct(*args,**kwargs)
    started=perf_counter_ns()
    with patch.object(choice,'parity_blocks',audited_parity),\
         patch.object(direct,'parity_blocks',audited_parity),\
         patch.object(choice,'spectral_form',audited_spectral),\
         patch.object(choice,'produce_direct_sat',
                      original_redundant_fallback if emulate_pre_fix else original_direct):
        if emulate_pre_fix:
            # SPN-009 used to perform this check before discovering that a
            # small decision instance was ineligible for spectral admission.
            audited_spectral(clauses,n)
        receipt=choice.compile_language(clauses,n,goal='decision',node_budget=128,
                                         allow_sfi=False)
        verdict=choice.verify_language_receipt(clauses,n,receipt)
    elapsed=(perf_counter_ns()-started)/1e6
    return {'verdict':verdict,'proof_kind':receipt['proof']['kind'],
            'counters':counters,'elapsed_ms':elapsed}


def run():
    outcomes=[]
    for name,cls,n in cases():
        previous=trace(cls,n,True)
        updated=trace(cls,n,False)
        if (previous['verdict']!=updated['verdict'] or
                previous['proof_kind']!=updated['proof_kind']):
            raise AssertionError('optimization changed source-checked semantics')
        outcomes.append({'case':name,'previous':previous,'updated':updated})
    return {'schema':'SPN-010-redundancy-probe-v1',
      'cases':len(outcomes),
      'previous_total_ms':round(sum(r['previous']['elapsed_ms'] for r in outcomes),4),
      'updated_total_ms':round(sum(r['updated']['elapsed_ms'] for r in outcomes),4),
      'previous_parity_scans':sum(r['previous']['counters']['parity_scans'] for r in outcomes),
      'updated_parity_scans':sum(r['updated']['counters']['parity_scans'] for r in outcomes),
      'previous_spectral_conversions':sum(r['previous']['counters']['spectral_conversions'] for r in outcomes),
      'updated_spectral_conversions':sum(r['updated']['counters']['spectral_conversions'] for r in outcomes),
      'all_verdicts_source_checked':True,
      'note':'pre-fix behavior reconstructed via injected redundant passes, not a standalone historical checkout; measured times are observational'}

if __name__=='__main__':
    result=run()
    Path(__file__).with_name('self_use_overhead_results.json').write_text(
        json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
