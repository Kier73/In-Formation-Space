"""Construct a total observation section via the actual CIG-017 circuit compiler.

For disjoint nonempty observation clauses, choose one literal to carry the
observation, set the others false, and fill all remaining source variables
through source-supported total local Boolean gates. Every original clause must
be covered; the receiver independently checks this existential construction.
"""
from composed_ground import digest
from global_sufficiency import circuit_decoder
from verify_global_sufficiency import contract
from verify_source_section import verify_section


def compile_section(n,source,q):
    s,q,_=contract(n,source,q,(1,))
    known=set()
    for c in q:
        if not c or known.intersection(map(abs,c)):return None
        known.update(map(abs,c))
    used={abs(l) for c in s for l in c};free=sorted(set(range(1,n+1))-used-known)
    seeds=known|set(free)
    d=circuit_decoder(s,[(v,) for v in sorted(seeds)],tuple(range(1,n+1)))
    if d is None:return None
    r=dict(schema='ifs.cig021.section.v1',key=digest([n,s,q]),free=free,gates=d['gates'])
    # Do not publish a partial clause cover as a universal section.
    if set(map(tuple,s))!=set(tuple(c) for g in r['gates'] for c in g['clauses']):return None
    return r


def section_witness(n,q,r,code):
    if type(code)is not int or not 0<=code<2**len(q):raise ValueError('code')
    vals={v:0 for v in r['free']}
    for j,c in enumerate(q):
        vals[abs(c[0])]=((code>>j)&1)^int(c[0]<0)
        for l in c[1:]:vals[abs(l)]=int(l<0)
    for g in r['gates']:vals[g['output']]=g['table'][sum(vals[v]<<i for i,v in enumerate(g['inputs']))]
    return sum(b<<(v-1) for v,b in vals.items())
