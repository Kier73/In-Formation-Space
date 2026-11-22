#!/usr/bin/env python3
"""SPN-010: use proof-carrying SAT machinery to select its own execution policy.

A bounded meta-SAT search chooses a set of *source-only* guard predicates
that decide when to spend extra effort on SPN-009 rather than SPN-008. All
training labels come from independently source-checked executions, not a hidden
answer oracle. Frozen guards use neither past solutions nor future outcomes.

The meta-CNF and every candidate outcome are checked by the existing SAT proof
verifier. This is a narrow, inspectable self-use loop, not automatic code editing,
not a proof of P=NP, and not general learned program synthesis.
"""
from __future__ import annotations

from hashlib import sha256
from itertools import combinations
from statistics import median
from time import perf_counter_ns
import json

from direct_sat_compiler import (produce_direct_sat, verify_direct_sat,
                                 source_digest, validate_cnf)
from language_choice_sat import (compile_language, verify_language_receipt)

VERSION = "SPN-010-self-use-v1"
RULES = ("many_variables", "high_hub", "scope_repetition",
         "sparse_large", "hub_and_repeated", "dense_large")


def _hash(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode()).hexdigest()


def source_features(clauses,n):
    """One O(m*k) source scan; no Fourier transform or solver calls."""
    validate_cnf(clauses,n)
    frequency={};scopes={}
    for clause in clauses:
        scope=frozenset(abs(v) for v in clause)
        scopes[scope]=scopes.get(scope,0)+1
        for v in scope:frequency[v]=frequency.get(v,0)+1
    m=len(clauses)
    hub=bool(m and 8*max(frequency.values(),default=0)>=m)
    repeated=any(v>=4 and len(k)>=2 for k,v in scopes.items())
    return {
        "many_variables":n>=20,
        "high_hub":n>=20 and hub,
        "scope_repetition":n>=20 and repeated,
        "sparse_large":n>=20 and m<=3*n,
        "hub_and_repeated":n>=20 and hub and repeated,
        "dense_large":n>=20 and m>3*n,
    }


def chosen_engine(clauses,n,policy):
    """Decide strictly from source and frozen rules, never an outcome label."""
    validate_policy(policy)
    feature=source_features(clauses,n)
    return "portfolio" if any(feature[k] for k in policy['selected_rules']) else "direct"


def validate_policy(policy):
    if not isinstance(policy,dict) or policy.get('version')!=VERSION:
        raise ValueError('invalid policy version')
    names=policy.get('selected_rules')
    if (not isinstance(names,list) or any(x not in RULES for x in names)
            or names!=sorted(set(names)) or len(names)>2):
        raise ValueError('policy rules invalid or exceed declared budget')
    if (not isinstance(policy.get('training_digest'),str)
            or len(policy['training_digest'])!=64):
        raise ValueError('missing pinned training digest')
    sources=policy.get('training_sources')
    if (not isinstance(sources,list) or sources!=sorted(set(sources)) or
        any(not isinstance(x,str) or len(x)!=64 for x in sources)):
        raise ValueError('invalid source-disjointness record')
    if policy.get('policy_sha256') != _hash({k:v for k,v in policy.items() if k!='policy_sha256'}):
        raise ValueError('policy identity mismatch')
    return True


def run_engine(clauses,n,engine,node_budget=32):
    """Fully measured execution including receipt construction and verification."""
    started=perf_counter_ns()
    if engine=='direct':
        receipt=produce_direct_sat(clauses,n,node_budget=node_budget)
        result=verify_direct_sat(clauses,n,receipt)
    elif engine=='portfolio':
        receipt=compile_language(clauses,n,goal='decision',node_budget=node_budget,
                rank_cap=3,allow_sfi=False)
        result=verify_language_receipt(clauses,n,receipt)
    else:raise ValueError('unsupported execution engine')
    elapsed=(perf_counter_ns()-started)/1e6
    if result not in ('SAT','UNSAT','UNKNOWN'):
        raise AssertionError('unsupported verified outcome')
    return {"result":result,"receipt":receipt,"elapsed_ms":elapsed,
            "receipt_bytes":len(json.dumps(receipt,separators=(',',':')).encode())}


def produce_self_use_receipt(clauses,n,policy,node_budget=32):
    """Source-only policy dispatch plus independently checked proof receipt."""
    validate_cnf(clauses,n)
    started=perf_counter_ns()
    engine=chosen_engine(clauses,n,policy)
    observation=run_engine(clauses,n,engine,node_budget)
    receipt={"version":VERSION,"source_sha256":source_digest(clauses,n),
             "policy_sha256":policy['policy_sha256'],"engine":engine,
             "result":observation['result'],"proof":observation['receipt'],
             "producer_ledger":{"node_budget":node_budget,
                 "engine_elapsed_ms":round(observation['elapsed_ms'],5),
                 "proof_bytes":observation['receipt_bytes'],
                 "total_ms":round((perf_counter_ns()-started)/1e6,5)}}
    assert verify_self_use_receipt(clauses,n,policy,receipt)==receipt['result']
    return receipt


def verify_self_use_receipt(clauses,n,policy,receipt):
    """Proof semantics come from the original CNF, not the selected policy."""
    validate_policy(policy)
    if (not isinstance(receipt,dict) or receipt.get('version')!=VERSION
          or receipt.get('source_sha256')!=source_digest(clauses,n)
          or receipt.get('policy_sha256')!=policy['policy_sha256']):
        raise ValueError('source or policy binding failed')
    engine=chosen_engine(clauses,n,policy)
    if receipt.get('engine')!=engine:
        raise ValueError('selected engine does not match source-only policy')
    nested=receipt.get('proof')
    result=(verify_direct_sat(clauses,n,nested) if engine=='direct' else
            verify_language_receipt(clauses,n,nested))
    if receipt.get('result')!=result:
        raise ValueError('unverified self-use result')
    return result


def compile_meta_cnf(training,max_rules=2):
    """Encode required decision coverage with at-most-2 selected rules.

    Variables select source-feature rules. A positive training case requires
    one selected applicable rule if only portfolio resolved it. A reverse
    case forbids every applicable rule. Neither side implies SAT truth.
    """
    if max_rules not in (0,1,2):
        raise ValueError('max_rules must be 0, 1 or 2')
    clauses=[]
    next_aux=len(RULES)+1
    def require_any(active):
        nonlocal next_aux
        if len(active)<=3:
            clauses.append(tuple(active));return
        # Equisatisfiable 3-CNF under each fixed guard assignment.
        y=next_aux;next_aux+=1
        clauses.append((active[0],active[1],y))
        for literal in active[2:-2]:
            newer=next_aux;next_aux+=1
            clauses.append((-y,literal,newer))
            y=newer
        clauses.append((-y,active[-2],active[-1]))
    for sample in training:
        direct=sample['direct']['result'];portfolio=sample['portfolio']['result']
        applicable=[i+1 for i,k in enumerate(RULES) if sample['features'][k]]
        if portfolio in ('SAT','UNSAT') and direct=='UNKNOWN':
            require_any(applicable) # empty clause => no feasible rule
        elif direct in ('SAT','UNSAT') and portfolio=='UNKNOWN':
            clauses.extend([(-i,) for i in applicable])
        elif (direct in ('SAT','UNSAT') and portfolio in ('SAT','UNSAT')
              and direct!=portfolio):
            raise AssertionError('source-verified solvers disagree')
    if max_rules==0:
        clauses.extend([(-i,) for i in range(1,len(RULES)+1)])
    elif max_rules==1:
        clauses.extend([(-i,-j) for i,j in combinations(range(1,len(RULES)+1),2)])
    else:
        clauses.extend([(-i,-j,-k) for i,j,k in combinations(range(1,len(RULES)+1),3)])
    return clauses


def observe(clauses,n,node_budget):
    """Build one paired trace, with all statuses independently checked."""
    features=source_features(clauses,n)
    direct=run_engine(clauses,n,'direct',node_budget)
    portfolio=run_engine(clauses,n,'portfolio',node_budget)
    if (direct['result']!=portfolio['result']
          and direct['result']!='UNKNOWN' and portfolio['result']!='UNKNOWN'):
        raise AssertionError('verified solvers disagree on SAT decision')
    return {"source_sha256":source_digest(clauses,n),"n":n,
            "clauses":[list(c) for c in clauses],"features":features,
            "direct":{**{k:direct[k] for k in ('result','elapsed_ms','receipt_bytes')},
                      'proof':direct['receipt']},
            "portfolio":{**{k:portfolio[k] for k in ('result','elapsed_ms','receipt_bytes')},
                         'proof':portfolio['receipt']}}


def train_policy(training,max_rules=2):
    """Use the existing proof-carrying SAT solver as a bounded meta-compiler.

    All 64 possible gate combinations are validated as assignments of a
    6-variable, width-<=3 *meta SAT instance*. Valid gate choices are scored
    using only the TRAINING observations and coverage constraints.
    """
    if not isinstance(training,list) or not training:
        raise ValueError('nonempty training observations required')
    if any(set(s['features'])!=set(RULES) for s in training):
        raise ValueError('unrecognized training features')
    # Independently replay every original-source label before feeding the meta
    # solver. Recorded times remain measurements, NOT mathematical evidence.
    for sample in training:
        cls,n=sample['clauses'],sample['n']
        if (source_digest(cls,n)!=sample['source_sha256'] or
                source_features(cls,n)!=sample['features'] or
                verify_direct_sat(cls,n,sample['direct']['proof'])!=sample['direct']['result'] or
                verify_language_receipt(cls,n,sample['portfolio']['proof'])!=sample['portfolio']['result']):
            raise ValueError('training observation failed source-ground replay')
    source_ids=[s['source_sha256'] for s in training]
    if len(set(source_ids))!=len(source_ids):
        raise ValueError('duplicate training sources')
    started=perf_counter_ns()
    meta=compile_meta_cnf(training,max_rules)
    # Width <=3 is a deliberate compatibility contract with SPN-008.
    if any(len(c)>3 for c in meta):
        raise AssertionError('meta-CNF escaped SPN-008')
    meta_n=max(len(RULES),max((abs(v) for c in meta for v in c),default=0))
    allowed=[];calls=0;proof_bytes=0
    for selected in range(1<<len(RULES)):
        units=[(j+1 if selected>>j&1 else -(j+1),)
               for j in range(len(RULES))]
        instance=meta+units
        proof=produce_direct_sat(instance,meta_n,node_budget=200)
        verdict=verify_direct_sat(instance,meta_n,proof)
        calls+=1
        proof_bytes+=len(json.dumps(proof,separators=(',',':')).encode())
        if verdict=='UNKNOWN':
            raise AssertionError('tiny meta-SAT query exceeded budget')
        if verdict=='UNSAT':continue
        rule_names=[k for j,k in enumerate(RULES) if selected>>j&1]
        total=0.0
        for s in training:
            engine=('portfolio' if any(s['features'][k] for k in rule_names)
                    else 'direct')
            total+=s[engine]['elapsed_ms']
        allowed.append((total,len(rule_names),rule_names))
    if not allowed:
        raise ValueError('no covered policy under declared rule budget')
    _,_,winner=min(allowed,key=lambda v:(v[0],v[1],v[2]))
    digest=_hash([{'source_sha256':s['source_sha256'],'features':s['features'],
                   'direct':{k:s['direct'][k] for k in ('result','elapsed_ms','receipt_bytes')},
                   'portfolio':{k:s['portfolio'][k] for k in ('result','elapsed_ms','receipt_bytes')}}
                  for s in training])
    policy={'version':VERSION,'selected_rules':sorted(winner),
            'training_digest':digest,'training_sources':sorted(source_ids)}
    policy['policy_sha256']=_hash(policy)
    audit={'meta_variables':meta_n,'meta_guard_variables':len(RULES),'meta_clauses':len(meta),
           'meta_proof_calls':calls,'meta_proof_bytes':proof_bytes,
           'admissible_rule_sets':len(allowed),
           'training_examples':len(training),'training_total_ms':round(sum(
              s['portfolio' if any(s['features'][r] for r in winner) else 'direct']['elapsed_ms']
              for s in training),5),
           'training_meta_ms':round((perf_counter_ns()-started)/1e6,5),
           'meta_source_sha256':source_digest(meta,meta_n)}
    validate_policy(policy)
    return policy,audit


def evaluate_frozen(policy,samples):
    """Held-out replay from samples not consulted during policy training."""
    validate_policy(policy)
    overlap=set(policy['training_sources']) & {s['source_sha256'] for s in samples}
    if overlap:
        raise ValueError('held-out evaluation contains training source')
    rows=[]
    for sample in samples:
        engine='portfolio' if any(sample['features'][k]
                for k in policy['selected_rules']) else 'direct'
        chosen=sample[engine]
        rows.append({'source_sha256':sample['source_sha256'],
                     'engine':engine,'result':chosen['result'],
                     'chosen_ms':chosen['elapsed_ms'],
                     'direct_ms':sample['direct']['elapsed_ms'],
                     'portfolio_ms':sample['portfolio']['elapsed_ms'],
                     'direct_result':sample['direct']['result'],
                     'portfolio_result':sample['portfolio']['result']})
    return {'cases':len(rows),
            'selected_engines':{name:sum(s['engine']==name for s in rows)
                                for name in ('direct','portfolio')},
            'decision_coverage':sum(s['result']!='UNKNOWN' for s in rows),
            'direct_coverage':sum(s['direct_result']!='UNKNOWN' for s in rows),
            'portfolio_coverage':sum(s['portfolio_result']!='UNKNOWN' for s in rows),
            'selected_total_ms':round(sum(s['chosen_ms'] for s in rows),5),
            'direct_total_ms':round(sum(s['direct_ms'] for s in rows),5),
            'portfolio_total_ms':round(sum(s['portfolio_ms'] for s in rows),5),
            'rows':rows}
