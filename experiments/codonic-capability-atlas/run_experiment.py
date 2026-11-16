"""Deterministic research fixture: witnessed adaptive versus static capability selection."""
from __future__ import annotations
import json
import time
from adaptive_arbiter import fixture_atlas
from test_adaptive_arbiter import run_one


def audit() -> dict:
    start=time.perf_counter()
    cases=[]
    for feature in ('parity-x','parity-y','parity-sum','half-x'):
        for seed in range(100):
            active,hits,static,policy,n=run_one(feature,seed,budget=4,method='active')
            random_control,rhits,_,rpolicy,_=run_one(feature,seed,budget=4,method='random')
            cases.append({'feature':feature,'seed':seed,'heldout':n,
                          'active_correct':hits,'static_correct':static,
                          'random_query_correct':rhits,'final_viable':len(active.viable),
                          'active_selected':policy.__dict__,
                          'active_evidence_head':active.head,
                          'passive_evidence_head':random_control.head})
    results={'format':'COG-002-adaptive-evidence-audit/1',
             'ground':fixture_atlas().fingerprint,
             'cases':len(cases),'budget_per_case':4,
             'heldout_per_case':cases[0]['heldout'],
             'mean_active_accuracy':sum(c['active_correct'] for c in cases)/(len(cases)*cases[0]['heldout']),
             'mean_static_accuracy':sum(c['static_correct'] for c in cases)/(len(cases)*cases[0]['heldout']),
             'mean_random_query_accuracy':sum(c['random_query_correct'] for c in cases)/(len(cases)*cases[0]['heldout']),
             'active_perfect_count':sum(c['active_correct']==c['heldout'] for c in cases),
             'random_perfect_count':sum(c['random_query_correct']==c['heldout'] for c in cases),
             'mean_remaining_hypotheses':sum(c['final_viable'] for c in cases)/len(cases),
             'elapsed_local_seconds':round(time.perf_counter()-start,3),
             'method':'deterministic synthetic labels, exact equality, disjoint heldout states; no model training'}
    return results

if __name__=='__main__':
    print(json.dumps(audit(),sort_keys=True,indent=2))