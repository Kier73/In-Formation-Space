"""PGT-002: observer-addressed active learning without an omniscient equivalence oracle.

Only feature projections are visible before each query; target outcomes are
revealed one coordinate at a time by the source. A finite admitted hypothesis
language is explicit. Global truth is checked *after* acquisition for audit.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from procedural_ground_training import canonical
from cross_family_curriculum import world_for, TRAIN_FAMILIES


def _signature(row):
    return row[0] | (row[1]<<1) | (row[2]<<2)


def hypothesis_library():
    funcs=[]
    def add(fn):
        truth=tuple(int(bool(fn(a,b,c))) for a in (0,1) for b in (0,1) for c in (0,1))
        if truth not in funcs:funcs.append(truth)
    add(lambda a,b,c:0);add(lambda a,b,c:1)
    for k in range(3):
        add(lambda a,b,c,k=k:(a,b,c)[k])
        add(lambda a,b,c,k=k:1-(a,b,c)[k])
    for i,j in ((0,1),(0,2),(1,2)):
        for mode in ('and','or','xor','nand','nor','xnor'):
            add(lambda a,b,c,i=i,j=j,mode=mode:
                ({'and': lambda x,y:x&y, 'or':lambda x,y:x|y,
                  'xor':lambda x,y:x^y, 'nand':lambda x,y:1-(x&y),
                  'nor':lambda x,y:1-(x|y),'xnor':lambda x,y:1-(x^y)}[mode])((a,b,c)[i],(a,b,c)[j]))
    add(lambda a,b,c:a^b^c)
    add(lambda a,b,c:(a&b)|c)
    add(lambda a,b,c:(a|b)&c)
    add(lambda a,b,c:(a&b)|(a&c)|(b&c))
    return tuple(funcs)

HYPOTHESES=hypothesis_library()


def _label(fn, features):
    a,b,c=features
    return fn[4*a+2*b+c]


class TargetSource:
    """Opaque, bounded target observer; it does not export a source table."""
    def __init__(self, world):
        self._world=world
        self.calls=0
        self.seen=set()
    def observe(self, index:int) -> int:
        if type(index) is not int or not 0<=index<len(self._world.targets) or index in self.seen:
            raise ValueError('duplicate or inadmissible observation coordinate')
        self.seen.add(index);self.calls+=1
        return int(self._world.targets[index])


def surviving(features,observations):
    return tuple(h for h in HYPOTHESES if all(_label(h,features[i])==v for i,v in observations.items()))


def next_query(features,known,candidates,rng,method):
    free=[i for i in range(len(features)) if i not in known]
    if not free:return None
    if method=='random':return int(rng.choice(free))
    if method!='active':raise ValueError('unknown policy')
    if not candidates:return None
    # Maximize binary disagreement across *remaining* candidate laws; no hidden
    # target or full-source equivalence oracle consulted. Tie by coordinate.
    def value(i):
        one=sum(_label(h,features[i]) for h in candidates)
        return min(one,len(candidates)-one)
    return max(free,key=lambda i:(value(i),-i))


def acquire(world, seed, initial, budget, method):
    rng=np.random.default_rng(seed)
    src=TargetSource(world)
    # Fixed matching initial coordinates for the active and random arms.
    observations={i:src.observe(i) for i in initial}
    candidates=surviving(world.features,observations)
    while len(observations)<budget and candidates:
        chosen=next_query(world.features,observations,candidates,rng,method)
        if chosen is None:break
        observations[chosen]=src.observe(chosen)
        candidates=surviving(world.features,observations)
    # One unique relation *on the known finite source's public feature domain*
    # suffices; multiple rules can agree on all actually addressable points.
    signatures={tuple(row) for row in world.features}
    candidate_outputs={tuple(_label(h,s) for s in sorted(signatures)) for h in candidates}
    status=('contradicted' if not candidates else
            'candidate' if len(candidate_outputs)==1 else 'unknown')
    if status=='candidate':
        h=candidates[0]
        correct=all(_label(h,features)==truth for features,truth in zip(world.features,world.targets))
    else:correct=False
    return {'status':status,'correct':correct,'used':src.calls,'remaining_hypotheses':len(candidates),
            'observed_coordinates':list(observations),'nontraining_source_evidence':True}


def audit(seed=7631, cases=1200, initial_count=2, budget=6):
    if not 2<=initial_count<=budget<=16:raise ValueError('invalid budget')
    rng=np.random.default_rng(seed)
    reports={key:{'correct':0,'false_claims':0,'candidate':0,'contradicted':0,
                  'unknown':0,'observed':0,'remaining_hypotheses':0}
             for key in ('in_family_active','in_family_random','heldout_active','heldout_random')}
    for i in range(cases):
        family=TRAIN_FAMILIES[i%len(TRAIN_FAMILIES)] if i%2==0 else 'finite_automaton'
        nstates=16 if i%4<2 else 32
        world=world_for(family,rng,seed*10**7+i,nstates)
        initial=tuple(int(v) for v in rng.choice(nstates,size=initial_count,replace=False))
        for method in ('active','random'):
            r=acquire(world,seed*10**8+i+123,initial,budget,method)
            group='heldout' if family=='finite_automaton' else 'in_family'
            out=reports[group+'_'+method]
            out['correct']+=int(r['correct'])
            out['false_claims']+=int(r['status']=='candidate' and not r['correct'])
            out[r['status']]+=1
            out['observed']+=r['used']
            out['remaining_hypotheses']+=r['remaining_hypotheses']
    denom=cases//2
    for group in reports.values():
        group['correct_rate']=round(group['correct']/denom,5)
        group['mean_observations']=round(group['observed']/denom,3)
    return {'schema':'ifs.pgt002.teacher-free-version-space.v1',
            'hypothesis_count':len(HYPOTHESES), 'cases':cases,'cases_per_distribution':denom,
            'initial_observations':initial_count,'max_observations':budget,
            'public_information':'3 observed feature projections at every source coordinate',
            'private_information':'target labels accessible only per selected coordinate',
            'prior_scope':'finite declared Boolean function family; not arbitrary future laws',
            'receiver_admitted_predictions':0,
            'candidate_status_is_only_a_proposal':True,
            'groups':reports}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=1200)
    p.add_argument('--budget',type=int,default=6)
    p.add_argument('--output',type=Path,default=Path('results/teacher-free-active.json'))
    args=p.parse_args();r=audit(cases=args.cases,budget=args.budget)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(canonical(r))
    print(json.dumps(r,indent=2))
