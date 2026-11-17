"""PGT-003: Cost-aware, intention-conditioned experimental design.

A finite hypothesis *language* is a proposal, not an admitted representation
of an unknown external source. Only reported queried observations are facts.
The policy may predict future observations, but cannot publish them as trusted.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
import math
import numpy as np
from active_version_space import HYPOTHESES

N=len(HYPOTHESES)
H=np.asarray(HYPOTHESES,dtype=np.int8)
ALL=(1<<N)-1
MASK1=tuple(sum((1<<i) for i in range(N) if H[i,q]) for q in range(8))


def canonical(v):
    return json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()

def fingerprint(v):return sha256(canonical(v)).hexdigest()

@dataclass(frozen=True)
class Context:
    target: int
    costs: tuple[int,...]
    weights: tuple[float,...]
    def __post_init__(self):
        if type(self.target) is not int or not 0<=self.target<8:raise ValueError('invalid target')
        if len(self.costs)!=8 or any(type(v) is not int or not 1<=v<=40 for v in self.costs):raise ValueError('costs out of range')
        if len(self.weights)!=N or any(not math.isfinite(v) or v<=0 for v in self.weights):raise ValueError('invalid prior')


def indices(mask):
    return [i for i in range(N) if mask&(1<<i)]


def split(mask,action):
    m1=mask&MASK1[action]
    return mask^m1,m1


def posterior(ctx,mask):
    return sum(ctx.weights[i] for i in indices(mask))


def terminal(ctx,mask):
    a,b=split(mask,ctx.target)
    return bool(mask and (not a or not b))


def features(ctx,mask,used):
    if mask<=0:raise ValueError('inconsistent hypotheses cannot be encoded')
    active=np.fromiter(indices(mask),dtype=np.int64)
    weights=np.asarray(ctx.weights,dtype=np.float64)[active]
    weights=weights/weights.sum()
    target=H[active,ctx.target]
    pgoal=float(weights[target==1].sum())
    global_features=np.array([len(active)/N, pgoal, pgoal*(1-pgoal)*4,
                              len([j for j in range(8) if used>>j&1])/8],dtype=np.float32)
    matrix=[]
    for q in range(8):
        bits=H[active,q]
        p=float(weights[bits==1].sum())
        good=0.
        for result in (0,1):
            keep=bits==result
            if keep.any():
                sub=weights[keep];sub/=sub.sum()
                sub_goal=target[keep]
                g=float(sub[sub_goal==1].sum())
                good+=float(weights[keep].sum())*(g*(1-g))
        # Conditional variance reduction measures how much *this intention* benefits.
        gain=pgoal*(1-pgoal)-good
        matrix.append([p,p*(1-p)*4,ctx.costs[q]/40, float(q==ctx.target),
                       float((used>>q)&1), max(0.,gain)*4,
                       len(active[bits==0])/N,len(active[bits==1])/N,
                       (q&1),((q>>1)&1),((q>>2)&1),
                       *(global_features.tolist())])
    return np.asarray(matrix,dtype=np.float32)


def optimal_action(ctx,mask=ALL,used=0,depth=4):
    """Exact cost-minimal Bayes-adaptive finite decision tree within depth.

    The source isn't consulted. This is only an optimal *experiment proposal*
    under the declared finite hypothesis prior, not an equivalence proof.
    """
    if not 1<=depth<=8:raise ValueError('unsupported horizon')
    @lru_cache(None)
    def value(m,u,left):
        if terminal(ctx,m):return (0.,None)
        if left<=0:return (float('inf'),None)
        total=posterior(ctx,m)
        best=(float('inf'),None)
        for q in range(8):
            if u>>q&1:continue
            m0,m1=split(m,q)
            if not m0 or not m1:continue
            expected=float(ctx.costs[q])
            if q!=ctx.target:
                future=0.
                for sub in (m0,m1):
                    pc=posterior(ctx,sub)/total
                    v,_=value(sub,u|(1<<q),left-1)
                    future+=pc*v
                expected+=future
            # Ties resolve to cheaper and then lower coordinate.
            key=(expected,ctx.costs[q],q)
            if best[1] is None or key < (best[0],ctx.costs[best[1]],best[1]):best=(expected,q)
        return best
    return value(mask,used,depth)


def greedy_action(ctx,mask,used,method='gain'):
    if terminal(ctx,mask):return None
    base=features(ctx,mask,used)
    valid=[q for q in range(8) if not(used>>q&1) and all(split(mask,q))]
    if not valid:return None
    if method=='gain':
        return max(valid,key=lambda q:((base[q,5]+1e-9)/ctx.costs[q],-ctx.costs[q],-q))
    if method=='disagreement':
        return max(valid,key=lambda q:((base[q,1]+1e-9)/ctx.costs[q],-ctx.costs[q],-q))
    if method=='direct':return ctx.target
    raise ValueError('unknown policy')


def context(rng,training=True):
    target=int(rng.integers(8))
    costs=tuple(int(z) for z in rng.integers(1,11,size=8))
    # Make direct targets costly enough that other observations may be useful.
    costs=tuple(int(rng.integers(13,37)) if q==target else c for q,c in enumerate(costs))
    # Training priors: two to four posterior clusters, positive mass for all candidates.
    weights=np.asarray(rng.dirichlet(np.full(N, rng.choice([0.4,1.0,2.5]))),dtype=np.float64)
    if not training:
        # Shift concentration to mimic a different host population.
        weights=np.asarray(rng.dirichlet(np.full(N,0.18)),dtype=np.float64)
    return Context(target,costs,tuple(float(v+1e-6) for v in weights))


def sampled_initial(rng,truth,ctx,limit=2):
    """Initial evidence is selected without reading the hidden law in advance."""
    used=0; mask=ALL; observed={}
    for q in rng.choice(8,size=int(rng.integers(limit+1)),replace=False):
        q=int(q); v=int(H[truth,q])
        used|=1<<q; mask=split(mask,q)[v]
        observed[q]=v
    return mask,used,observed


def rollout(ctx,truth,choose,seed,initial=(ALL,0,{}),horizon=6):
    mask,used,original=initial;observed=dict(original)
    trace=[]; cost=0; status='candidate'
    while not terminal(ctx,mask) and len(trace)<horizon:
        q=choose(ctx,mask,used)
        if q is None:status='unknown';break
        if q<0 or q>7 or used>>q&1:raise ValueError('unsafe query proposal')
        v=int(H[truth,q]);before=len(indices(mask))
        new=split(mask,q)[v]
        trace.append({'query':q,'observation':v,'cost':ctx.costs[q],
                      'candidates_before':before,'candidates_after':len(indices(new))})
        mask=new;used|=1<<q;observed[q]=v;cost+=ctx.costs[q]
        if not mask:status='contradicted';break
    if not terminal(ctx,mask) and status=='candidate':status='unknown'
    proposal=(int(H[indices(mask)[0],ctx.target]) if terminal(ctx,mask) else None)
    return {'status':status,'target_candidate':proposal,'target_true':int(H[truth,ctx.target]),
            'cost':cost,'queries':len(trace),'trace':trace,'observations':observed,
            'hypotheses_remaining':len(indices(mask))}


def out_of_family_audit(model,propose,seed=911,cases=1000):
    """Deliberately violate the 30-function assumption and expose false candidates.

    The complete mapping is accessed by the *independent audit* only; online
    policy sees queried target bits. Every candidate remains inadmissible.
    """
    rng=np.random.default_rng(seed)
    known={tuple(row) for row in H.tolist()}
    stats={'cases':cases,'candidate':0,'false_candidates':0,'contradictions':0,
           'unknown':0,'target_directly_witnessed':0,'physical_calls':0,
           'neural_predictions_admitted':0,'terminal_ground_admitted':0,'verified_target_reads':0,
           'extra_verified_read_cost':0,'source_verified_target_results_correct':0,'total_observed_cost_including_initial':0}
    for case in range(cases):
        ctx=context(rng,training=False)
        while True:
            truth=tuple(int(v) for v in rng.integers(0,2,size=8))
            if truth not in known:break
        mask=ALL;used=0;received={}
        # Two initial observations, not chosen using hidden truth.
        for q in rng.choice(8,size=2,replace=False):
            q=int(q);v=truth[q]
            received[q]=v;used|=1<<q;mask=split(mask,q)[v]
        for _ in range(6):
            if not mask or terminal(ctx,mask):break
            q=propose(ctx,mask,used)
            if q is None:break
            v=truth[q];stats['physical_calls']+=1
            received[q]=v;used|=1<<q;mask=split(mask,q)[v]
        stats['total_observed_cost_including_initial']+=sum(ctx.costs[q] for q in received)
        if not mask:stats['contradictions']+=1
        elif terminal(ctx,mask):
            stats['candidate']+=1
            result=int(H[indices(mask)[0],ctx.target])
            stats['false_candidates']+=int(result!=truth[ctx.target])
        else:stats['unknown']+=1
        stats['target_directly_witnessed']+=int(ctx.target in received)
        # An unknown external law has no full-domain certificate. A direct read
        # of this target is required to make a target-specific witnessed claim.
        if ctx.target not in received:
            stats['verified_target_reads']+=1
            stats['extra_verified_read_cost']+=ctx.costs[ctx.target]
            received[ctx.target]=truth[ctx.target]
        stats['source_verified_target_results_correct']+=int(received[ctx.target]==truth[ctx.target])
    return stats
