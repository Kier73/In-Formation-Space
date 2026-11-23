"""CIG-001 independent source-and-claim checker (no compiler import).

Receives the original source object and a claimed Ground; it independently
reconstructs all clauses, node grouping, rank exponent, and hub coefficients.
This is source-level replay, not a formal Lean/kernel proof.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json


class GroundVerificationError(ValueError):
    pass


def _fail(msg):
    raise GroundVerificationError(msg)


def _hash(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf-8')).hexdigest()


def verify(source, cert):
    if not isinstance(source, dict) or not isinstance(cert, dict):
        _fail('source and certificate must be objects')
    if set(source) != {'schema','n','clauses','nodes'} or source['schema'] != 'ifs.cut-intention-source.v1':
        _fail('unexpected source format')
    n, nodes = source['n'],source['nodes']
    if type(n) is not int or n < 2 or n > 18720 or not isinstance(nodes,list) or not 2<=len(nodes)<=40:
        _fail('invalid source size')
    if any(not isinstance(g,list) or any(type(v) is not int for v in g) for g in nodes):
        _fail('malformed node partition')
    if sorted(v for group in nodes for v in group) != list(range(1,n+1)):
        _fail('node partition does not cover original variables exactly once')
    groups = {v:i for i,group in enumerate(nodes) for v in group}
    clauses = source['clauses']
    if not isinstance(clauses,list):
        _fail('clauses must be a list')
    clause_set = set()
    for cl in clauses:
        if (not isinstance(cl,list) or len(cl)!=2 or
                any(type(x) is not int or x==0 or abs(x)>n for x in cl)):
            _fail('unsupported clause')
        key = tuple(sorted(cl))
        if key in clause_set:
            _fail('duplicate clause')
        clause_set.add(key)
    if len(clause_set) != n:
        _fail('not exactly one equivalence pair per two variables')
    adjacency = {v:set() for v in range(1,n+1)}
    for cl in clauses:
        x,y=map(abs,cl)
        if x == y or cl[0]*cl[1]>=0:
            _fail('not a directional equality clause')
        adjacency[x].add(y)
        adjacency[y].add(x)
    if any(len(v)!=1 for v in adjacency.values()):
        _fail('source is not disjoint equality copies')
    pairs=sorted((v,next(iter(ns))) for v,ns in adjacency.items() if v<next(iter(ns)))
    expected=set()
    for x,y in pairs:
        expected.add(tuple(sorted((-x,y))))
        expected.add(tuple(sorted((x,-y))))
    if expected != clause_set or len(pairs)*2!=n:
        _fail('failed original-CNF equality reconstruction')
    k=len(nodes)
    hist=Counter(tuple(sorted((groups[x],groups[y]))) for x,y in pairs)
    if any(groups[x]==groups[y] for x,y in pairs):
        _fail('equality contained in one node')
    sizes=[hist.get((a,b),0) for a in range(k) for b in range(a+1,k)]
    if not sizes or min(sizes)<1 or len(set(sizes))!=1:
        _fail('source is not a uniformly labeled complete graph')
    l=sizes[0]
    intent=cert.get('intention')
    if intent not in ('SAT','#SAT','CUT_RANK'):
        _fail('unknown intent')
    if intent=='CUT_RANK':
        cut=cert.get('cut')
        if (not isinstance(cut,list) or any(type(v) is not int for v in cut)
                or cut!=sorted(set(cut)) or not 0<len(cut)<k or
                cut[0]<0 or cut[-1]>=k):
            _fail('invalid cut')
        s=set(cut)
        crossing=sum((groups[x] in s)!=(groups[y] in s) for x,y in pairs)
        if crossing!=l*len(cut)*(k-len(cut)):
            _fail('crossing edge mismatch')
        hub=[sum(j not in s for j in range(i+1,k)) if i in s
             else -sum(j in s for j in range(i+1,k)) for i in range(k)]
        norm=sum(v*v for v in hub)
        if sum(abs(v) for v in hub) != len(cut)*(k-len(cut)) or k*norm < sum(abs(v) for v in hub)**2:
            _fail('geometric identity invalid')
        geometry={'hub_twice':hub,'hub_norm_sq_numerator':norm,
                  'hub_norm_sq_denominator':4,
                  'hub_l1_twice':len(cut)*(k-len(cut)),
                  'geometric_cauchy_checked':True}
        result={'rank':str(1<<crossing),'log2_rank':crossing,
                'flattening_row_bits':sum(len(nodes[i]) for i in cut),
                'flattening_col_bits':sum(len(nodes[i]) for i in range(k) if i not in s),
                'matrix_entry_log2':n}
        cross_edges=len(cut)*(k-len(cut))
    else:
        if cert.get('cut') is not None:
            _fail('unexpected cut')
        cross_edges=0
        geometry=None
        if intent=='SAT':
            witness=[0]*n
            if not all(any(witness[abs(lit)-1]==int(lit>0) for lit in cl) for cl in clauses):
                _fail('not SAT with constructed witness')
            result={'status':'SAT','witness':witness}
        else:
            result={'status':'SAT','count':str(1<<len(pairs)),
                    'free_label_bits':len(pairs)}
    expectation={'schema':'ifs.cut-intention-ground.v1','source_digest':_hash(source),
                 'intention':intent,'cut':cert.get('cut'),
                 'proof':{'variable_equalities':[list(x) for x in pairs],
                          'node_count':k,'label_bits_per_edge':l,
                          'crossing_edges':cross_edges},
                 'result':result,'geometry':geometry}
    if cert != expectation:
        _fail('Ground does not match independent original-source replay')
    return True
