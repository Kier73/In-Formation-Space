#!/usr/bin/env python3
"""SPN-010 reproducible self-use / held-out policy compilation experiment."""
from __future__ import annotations
import json,random,platform
from collections import Counter
from pathlib import Path
from time import perf_counter_ns
from self_use_cycle import (observe,train_policy,produce_self_use_receipt,
    verify_self_use_receipt,evaluate_frozen, _hash, validate_policy)
from test_direct_sum_grounds import shared_variable_cycle_cnf
from test_direct_sat_compiler import parity_cycle_family


def _from_spn(rows):
    return [tuple(v+1 if b==0 else -(v+1) for v,b in zip(scope,bits))
            for scope,bits in rows]


def fixtures(seed,variant):
    """Source-only seeded generators; train and hold-out have separate seeds."""
    rng=random.Random(seed)
    result=[]
    for i in range(12 if variant=='train' else 10):
        n=(8,10,12,14)[i%4]
        m=round(4.25*n)
        clauses=[tuple(v if rng.randrange(2) else -v
                 for v in rng.sample(range(1,n+1),3)) for _ in range(m)]
        result.append((f'random-small-{i}',clauses,n))
    for i in range(6):
        n=(9,11,13)[i%3]
        planted=rng.getrandbits(n)
        clauses=[]
        for j in range(round(4.4*n)):
            vs=rng.sample(range(1,n+1),3)
            choices=tuple(v if rng.randrange(2) else -v for v in vs)
            if not any(((planted>>(abs(v)-1))&1)==int(v>0) for v in choices):
                choices=(abs(choices[0]) if (planted>>(abs(choices[0])-1))&1
                         else -abs(choices[0]),)+choices[1:]
            clauses.append(choices)
        result.append((f'planted-{i}',clauses,n))
    for i in range(7 if variant=='train' else 6):
        n=(22,28,34)[i%3]
        clauses=[tuple(v if rng.randrange(2) else -v
                 for v in rng.sample(range(1,n+1),3))
                 for j in range(round(4.26*n))]
        result.append((f'random-large-{i}',clauses,n))
    overlap={'train':(6,12,18,24,30),'validation':(8,14,20,26,32),
             'final':(10,16,22,28,34)}[variant]
    for block in overlap:
        for frustrated in (True,False):
            rows,n=shared_variable_cycle_cnf(block,frustrated=frustrated)
            result.append((f'overlap-{block}-{int(frustrated)}',_from_spn(rows),n))
    parity={'train':(2,5,8),'validation':(3,6,9),'final':(4,7,10)}[variant]
    for block in parity:
        for frustrated in (True,False):
            clauses,n=parity_cycle_family(block,frustrated)
            result.append((f'xor-{block}-{int(frustrated)}',clauses,n))
    return result


def _observations(seed,variant,node_budget):
    observations=[]
    for name,cls,n in fixtures(seed,variant):
        sample=observe(cls,n,node_budget)
        sample['family']=name
        observations.append(sample)
    return observations


def _live_replay(policy,observations,node_budget):
    selected=[]
    for s in observations:
        r=produce_self_use_receipt(s['clauses'],s['n'],policy,node_budget=node_budget)
        status=verify_self_use_receipt(s['clauses'],s['n'],policy,r)
        if status!=s[r['engine']]['result']:
            raise AssertionError('frozen policy dispatch disagrees with source verifier')
        selected.append({'family':s['family'],'n':s['n'],'engine':r['engine'],
                        'status':status,'total_ms':r['producer_ledger']['total_ms'],
                        'proof_bytes':r['producer_ledger']['proof_bytes'],
                        'source_sha256':r['source_sha256']})
    return selected


def _summarize(selected):
    grouped={}
    for row in selected:
        family=row['family'].split('-')[0]
        g=grouped.setdefault(family,{'cases':0,'solved':0,'unknown':0,
                                     'direct':0,'portfolio':0,'elapsed_ms':0})
        g['cases']+=1;g['solved']+=row['status']!='UNKNOWN'
        g['unknown']+=row['status']=='UNKNOWN'
        g[row['engine']]+=1
        g['elapsed_ms']+=row['total_ms']
    for g in grouped.values():g['elapsed_ms']=round(g['elapsed_ms'],4)
    return {'total_ms':round(sum(x['total_ms'] for x in selected),4),
            'solved':sum(x['status']!='UNKNOWN' for x in selected),
            'unknown':sum(x['status']=='UNKNOWN' for x in selected),
            'families':grouped}


def run():
    # A three-way split: construct on train, admit/refuse on validation, report
    # evidence only on untouched final. Final results never change the policy.
    node_budget=8
    started=perf_counter_ns()
    training=_observations(110010,'train',node_budget)
    training_observation_ms=(perf_counter_ns()-started)/1e6
    candidate,audit=train_policy(training,max_rules=2)
    validation=_observations(220020,'validation',node_budget)
    validation_replay=evaluate_frozen(candidate,validation)
    candidate_live=_live_replay(candidate,validation,node_budget)
    candidate_live_summary=_summarize(candidate_live)
    # Coverage-first: don't admit a policy that solves fewer cases; otherwise
    # require either more verified decisions, or a >=5% matched speed gain.
    more_coverage=validation_replay['decision_coverage']>validation_replay['direct_coverage']
    equal_coverage=validation_replay['decision_coverage']==validation_replay['direct_coverage']
    cheaper=(validation_replay['selected_total_ms'] <=
             0.95*validation_replay['direct_total_ms'])
    admitted=bool(more_coverage or (equal_coverage and cheaper))
    if admitted:
        policy=candidate
    else:
        policy={k:candidate[k] for k in ('version','training_digest','training_sources')}
        policy['selected_rules']=[]
        policy['policy_sha256']=_hash(policy)
    validate_policy(policy)
    final=_observations(330030,'final',node_budget)
    final_comparison=evaluate_frozen(policy,final)
    live=_live_replay(policy,final,node_budget)
    if any(s['source_sha256'] in set(candidate['training_sources']) for s in final):
        raise AssertionError('final test overlaps with training set')
    return {'schema':'SPN-010-self-use-three-way-v1',
            'environment':{'python':platform.python_version(),
              'measurement':'single host, uncalibrated, full source-verifier cost included'},
            'node_budget':node_budget,
            'training_source_count':len(training),
            'validation_source_count':len(validation),
            'final_source_count':len(final),
            'training_observation_ms':round(training_observation_ms,4),
            'candidate':candidate,'deployed_policy':policy,
            'admission':{'accepted':admitted,
                 'reason':'verified_coverage_or_5pct_speed_threshold' if admitted
                          else 'candidate_not_improved_on_validation',
                 'validation_coverage':validation_replay['decision_coverage'],
                 'direct_coverage':validation_replay['direct_coverage'],
                 'candidate_observed_total_ms':validation_replay['selected_total_ms'],
                 'direct_observed_total_ms':validation_replay['direct_total_ms'],
                 'candidate_live':candidate_live_summary},
            'meta_compilation':audit,
            'final_matched_observations':{k:v for k,v in final_comparison.items() if k!='rows'},
            'final_live_selected':_summarize(live),
            'selected_rows':live,
            'evidence':'All accepted SAT/UNSAT decisions source-replayed.\n'
               'Training, validation and final-source identities disjoint.\n'
               'Elapsed time observational; improvement admission not a theorem.'}


if __name__=='__main__':
    r=run()
    target=Path(__file__).with_name('self_use_results.json')
    target.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r[k] for k in ('training_source_count','validation_source_count',
      'final_source_count','candidate','admission','meta_compilation',
      'final_matched_observations','final_live_selected')},indent=2))
