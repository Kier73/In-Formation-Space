"""COG-007 active predictive cognitive states, auditable scale and cold handoff."""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
from time import perf_counter
from cognitive_grounds import canonical,digest,GroundRefused
from predictive_state import (Teacher,ActiveMachineLearner,source_fixture,
                              conformance,receipt,restore,minimality)


def fit(n,k,named=False):
    g,l=source_fixture(n,k)
    teacher=Teacher(g,l,named=named)
    solver=ActiveMachineLearner(teacher)
    machine,proof=solver.learn()
    return teacher,solver,machine,proof


def audit():
    cases=[]
    for n,k,named in [(16,4,False),(32,8,False),(32,8,True),
                      (64,8,False),(128,8,False),(256,8,False),(512,8,False)]:
        begin=perf_counter()
        teacher,learner,machine,proof=fit(n,k,named)
        duration=perf_counter()-begin
        test_rng=random.Random(n*997+int(named))
        heldout=1500
        good=0
        for _ in range(heldout):
            seq=tuple(test_rng.choice(teacher.alphabet) for _ in range(test_rng.randrange(1,12)))
            good+=int(machine.run(seq)==teacher.query(seq))
        cases.append({'subjects':n,'distinct_duration_classes':k,'requires_identity':named,
                      'raw_reachable_states':proof.source_states,
                      'learned_exact_states':len(machine.representatives),
                      'compression_ratio':round(proof.source_states/len(machine.representatives),3),
                      'distinct_counterexamples':len(learner.counterexamples),
                      'active_oracle_traces':teacher.calls,
                      'exhaustive_check_edges':proof.checked_edges,
                      'heldout_correct':good,'heldout_total':heldout,
                      'learn_wall_seconds':round(duration,3),
                      'globally_minimal_in_contract':minimality(teacher,machine)})
    return {'schema':'COG-007/predictive-structure-audit/v1',
            'cases':cases,
            'source':'COG006 typed synthetic fact/procedure Grounds',
            'independent_conformance':'exhaustive source-state by inferred-state product BFS, bounded finite alphabet',
            'generalization':'held-out symbolic conversations, not unrepresented natural language',
            'not_claimed':['PyBot reproduction','unbounded-language equivalence',
                           'neural learning','host authentication','E-CPU-native execution']}


def prepare(path:Path):
    teacher,learner,machine,proof=fit(12,4)
    doc=receipt(teacher,machine,proof,learner)
    prefix=('mention:topic_0001','minutes')
    state=machine.state_after(prefix)
    core={'schema':'COG-007/checkpoint/1','machine':doc,
          'continuation':{'source_root':teacher.source_root,
                          'state_id':state,'prefix':list(prefix),
                          'prefix_observed_outputs':[list(x) for x in machine.run(prefix)]}}
    checkpoint={**core,'digest':digest(core)}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(canonical(checkpoint))
    # Separate external high-water file: must be held independently by receiver
    # in actual deployment (same machine here is NOT fault isolation).
    pin={'machine_digest':doc['digest'],'checkpoint_digest':checkpoint['digest']}
    path.with_suffix('.pins.json').write_bytes(canonical(pin))
    return {'digest':checkpoint['digest'],'machine':doc['digest'],'states':len(machine.representatives),
            'memory_state':state,'source_query_calls':teacher.calls}


def resume(path:Path):
    saved=json.loads(path.read_bytes());pin=json.loads(path.with_suffix('.pins.json').read_bytes())
    if digest({k:v for k,v in saved.items() if k!='digest'})!=saved['digest'] or pin['checkpoint_digest']!=saved['digest']:
        raise GroundRefused('checkpoint high-water pin changed')
    g,l=source_fixture(12,4)
    teacher=Teacher(g,l)
    machine=restore(teacher,saved['machine'],external_digest=pin['machine_digest'])
    checkpoint=saved['continuation']
    prior=tuple(checkpoint['prefix'])
    if (checkpoint['source_root']!=teacher.source_root or
            checkpoint['prefix_observed_outputs']!=[list(x) for x in machine.run(prior)] or
            checkpoint['state_id']!=machine.state_after(prior)):
        raise GroundRefused('session state not justified by current structural evidence')
    # Execute ONLY successor actions from retained state; no original oracle
    # queries and no replay of the prior semantic turn.
    continuation,state=machine.run_from(checkpoint['state_id'],('repeat','seconds'))
    return {'digest':saved['digest'],'final_response':list(continuation[-1]),
            'continuation_outputs':[list(x) for x in continuation],
            'independent_conformance':True,'query_calls_for_recovery':teacher.calls,
            'resumed_from_state_id':checkpoint['state_id'],'new_state_id':state}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['audit','prepare','resume'])
    parser.add_argument('--path',type=Path)
    args=parser.parse_args()
    if args.command in ('prepare','resume') and args.path is None:parser.error('--path required')
    print(json.dumps(audit() if args.command=='audit' else prepare(args.path) if args.command=='prepare' else resume(args.path),
                     indent=2,sort_keys=True))
