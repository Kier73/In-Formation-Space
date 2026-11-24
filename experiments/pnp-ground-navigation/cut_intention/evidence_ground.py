"""CIG-007: exact finite-class intention resolution by costed probes.
A probe is a stipulated reset to an active state followed by one synchronous
step and reading one active bit. No physical observation is manufactured.
"""
from functools import lru_cache
from hashlib import sha256
import json
from verify_language_selector import verify as verify_language


def digest(x):
    return sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def compile_policy(source, language, intention, offers, *, identify=False):
    if not verify_language(source,language,intention=intention):
        raise ValueError('unverified language')
    candidates=language['candidates']
    n=len(language['source_model']['active_labels'])
    if not language['candidate_class']['complete_qualification'] or not 1<=len(candidates)<=12:
        raise ValueError('incomplete or excessive candidate class')
    if type(identify) is not bool or not isinstance(offers,list) or len(offers)>256:
        raise ValueError('invalid policy contract')
    seen=set()
    for p in offers:
        if (not isinstance(p,list) or len(p)!=3 or any(type(v) is not int for v in p)
            or not 0<=p[0]<1<<n or not 0<=p[1]<n or p[2]<0 or tuple(p[:2]) in seen):
            raise ValueError('invalid or duplicate probe')
        seen.add(tuple(p[:2]))
    goals=[i if identify else tuple(c['conditional_observation']) for i,c in enumerate(candidates)]
    masks=[]
    for state,bit,cost in offers:
        masks.append(sum((sum((state&m)==m for m in c['operator_rows'][bit])%2)<<i
                         for i,c in enumerate(candidates)))
    @lru_cache(None)
    def solve(mask):
        ids=[i for i in range(len(candidates)) if mask>>i&1]
        if len({goals[i] for i in ids})==1:
            return 0,{'candidates':ids,'result':ids[0] if identify else list(goals[ids[0]])}
        best=None
        for j,m in enumerate(masks):
            a=mask&~m;b=mask&m
            if not a or not b:continue
            left=solve(a);right=solve(b)
            if left is None or right is None:continue
            cost=offers[j][2]+max(left[0],right[0])
            if best is None or cost<best[0]:
                best=cost,{'candidates':ids,'probe':j,'zero':left[1],'one':right[1]}
        return best
    result=solve((1<<len(candidates))-1)
    return {'schema':'ifs.cig007.evidence-policy.v1','language_digest':digest(language),
            'offers':offers,'identify':identify,'status':'RESOLVABLE' if result else 'UNRESOLVED',
            'worst_cost':result[0] if result else None,'tree':result[1] if result else None,
            'planning_states':solve.cache_info().currsize}


def apply_transcript(policy, outcomes):
    """Replay hypothetical externally supplied outcomes in exact policy order.
    Caller must separately qualify their evidence/host/reset semantics.
    """
    node=policy['tree']
    if node is None:return {'status':'UNRESOLVED'}
    for probe,value in outcomes:
        if 'probe' not in node or probe!=node['probe'] or type(value) is not int or value not in (0,1):
            raise ValueError('invalid transcript')
        node=node['one' if value else 'zero']
    return {'status':'CONDITIONAL_CONSENSUS' if 'result' in node else 'NEEDS_EVIDENCE',**node}
