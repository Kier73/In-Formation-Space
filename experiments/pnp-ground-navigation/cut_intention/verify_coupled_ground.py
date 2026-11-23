"""CIG-002 receiver-side checker. No producer import or trusted result fields.

Reconstructs equalities and residual constraints from ORIGINAL source clauses;
computes exact counting and rank via a different column-basis implementation.
It does not claim Lean/kernel proof or a separate independently implemented CNF solver.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from math import gcd


class VerificationFailure(ValueError):
    pass


def _canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)


def _prove_source(src):
    if type(src) is not dict or set(src)!={'schema','base','coupling'} or src['schema']!='ifs.cut-intention-coupled-source.v1':
        raise VerificationFailure('source schema')
    base=src['base']
    if type(base) is not dict or set(base)!={'schema','n','nodes','clauses'} or base['schema']!='ifs.cut-intention-source.v1':
        raise VerificationFailure('base schema')
    n=base['n'];nodes=base['nodes'];clauses=base['clauses']
    if (type(n) is not int or not 2<=n<=40*39*12 or type(nodes) is not list or
            not 2<=len(nodes)<=40 or any(type(xs) is not list for xs in nodes) or
            any(type(v) is not int for xs in nodes for v in xs) or
            sorted(v for xs in nodes for v in xs)!=list(range(1,n+1)) or
            type(clauses) is not list or len(clauses)!=n):
        raise VerificationFailure('base bounds or variable partition')
    origins={v:i for i,g in enumerate(nodes) for v in g}
    edges=defaultdict(set)
    for cl in clauses:
        if (type(cl) is not list or len(cl)!=2 or any(type(v) is not int or not 1<=abs(v)<=n for v in cl)
                or sum(1 for x in cl if x>0)!=1 or abs(cl[0])==abs(cl[1])):
            raise VerificationFailure('source equality clause')
        x=abs(next(v for v in cl if v<0));y=next(v for v in cl if v>0)
        edges[tuple(sorted((x,y)))].add((x,y))
    pairs=sorted(edges)
    if len(pairs)*2!=n or Counter(v for e in pairs for v in e)!=Counter({v:1 for v in range(1,n+1)}):
        raise VerificationFailure('not disjoint equality pairs')
    bins=Counter()
    for a,b in pairs:
        if edges[a,b]!={(a,b),(b,a)} or origins[a]==origins[b]:
            raise VerificationFailure('missing reverse source implication')
        bins[tuple(sorted((origins[a],origins[b])))] +=1
    widths=[bins[a,b] for a in range(len(nodes)) for b in range(a+1,len(nodes))]
    if not widths or min(widths)<1 or len(set(widths))!=1:
        raise VerificationFailure('not a uniform complete graph')
    extra=src['coupling']
    if type(extra) is not list or len(extra)>128 or any(type(cl) is not list or len(cl)>3
              or any(type(v) is not int or not 1<=abs(v)<=n for v in cl) for cl in extra):
        raise VerificationFailure('invalid coupling')
    pair_by_var={v:i for i,e in enumerate(pairs) for v in e}
    reduced_clauses=set()
    for cl in extra:
        # Preserve ordinary CNF truth across both endpoint copies by substitution.
        literals={pair_by_var[abs(l)]+1 if l>0 else -(pair_by_var[abs(l)]+1) for l in cl}
        if any(-l in literals for l in literals):
            continue
        reduced_clauses.add(tuple(sorted(literals,key=lambda l:(abs(l),l<0))))
    clauses_sorted=sorted(reduced_clauses,key=lambda c:(len(c),c))
    active=sorted({abs(l)-1 for c in clauses_sorted for l in c})
    if len(active)>14: raise VerificationFailure('active domain exceeds admission limit')
    renumber={v:i+1 for i,v in enumerate(active)}
    lifted=[[renumber[abs(l)-1]*(1 if l>0 else -1) for l in c] for c in clauses_sorted]
    return pairs,origins,active,lifted


def _holds(cnf,assignment):
    for cl in cnf:
        if not any(((assignment>>(abs(l)-1))&1)==int(l>0) for l in cl):
            return False
    return True


def _decode(active_bits,active,pairs,n):
    a={v:(active_bits>>i)&1 for i,v in enumerate(active)}
    full=[0]*n
    for j,(x,y) in enumerate(pairs):
        full[x-1]=full[y-1]=a.get(j,0)
    return full


def _check_original(src,w):
    return all(any(w[abs(v)-1]==int(v>0) for v in c) for c in src['base']['clauses']+src['coupling'])


def _column_rank(columns):
    pivots={}
    for vector in columns:
        while vector:
            smallest=(vector&-vector).bit_length()-1
            if smallest not in pivots:
                pivots[smallest]=vector;break
            vector ^= pivots[smallest]
    return len(pivots)


def verify(src,certificate):
    try:
        pairs,origins,active,lifted=_prove_source(src)
        if type(certificate) is not dict or certificate.get('schema')!='ifs.cut-intention-coupled-ground.v1':
            raise VerificationFailure('unknown Ground schema')
        intention=certificate.get('intention')
        if intention not in ('SAT','#SAT','CUT_RANK'):
            raise VerificationFailure('unknown observer intention')
        cut=certificate.get('cut')
        n=src['base']['n'];k=len(src['base']['nodes'])
        source_id=hashlib.sha256(_canonical(src).encode()).hexdigest()
        base_id=hashlib.sha256(_canonical(src['base']).encode()).hexdigest()
        if intention=='CUT_RANK':
            if (type(cut) is not list or not cut or len(cut)>=k or
                any(type(x) is not int for x in cut) or cut!=sorted(set(cut)) or
                cut[0]<0 or cut[-1]>=k):
                raise VerificationFailure('cut contract')
            S=set(cut)
            side=[]
            for x,y in pairs:
                left=origins[x] in S;right=origins[y] in S
                side.append('C' if left!=right else ('L' if left else 'R'))
            active_sides=[side[a] for a in active]
            Cs=[i for i,s in enumerate(active_sides) if s=='C']
            Ls=[i for i,s in enumerate(active_sides) if s=='L']
            Rs=[i for i,s in enumerate(active_sides) if s=='R']
            cross_total=side.count('C')
            total_rank=0
            for ct in range(1<<len(Cs)):
                pinned=sum(((ct>>i)&1)<<v for i,v in enumerate(Cs))
                columns=[]
                for rv in range(1<<len(Rs)):
                    right_mask=pinned|sum(((rv>>i)&1)<<v for i,v in enumerate(Rs))
                    col=0
                    for lv in range(1<<len(Ls)):
                        full=right_mask|sum(((lv>>i)&1)<<v for i,v in enumerate(Ls))
                        if _holds(lifted,full): col|=1<<lv
                    columns.append(col)
                total_rank+=_column_rank(columns)
            rank=total_rank << (cross_total-len(Cs))
            baseline=1<<cross_total
            g=gcd(rank,baseline)
            result={'rank':str(rank),'baseline_rank':str(baseline),
                    'rank_ratio':[rank//g,baseline//g],
                    'active_block_rank_sum':total_rank,
                    'unrestricted_cross_labels':cross_total-len(Cs),
                    'crossing_labels':cross_total}
            work={'active_side_labels':{'L':len(Ls),'R':len(Rs),'C':len(Cs)},
                  'evaluated_reduced_assignments':1<<len(active),
                  'matrix_rows_visited':(1<<len(Cs))*(1<<len(Ls)),
                  'enumeration_cost_bound':1<<len(active)}
        else:
            if cut is not None:raise VerificationFailure('cut only for rank')
            first=None;count=0;checked=0
            for mask in range(1<<len(active)):
                checked+=1
                if _holds(lifted,mask):
                    count+=1
                    if first is None:
                        first=mask
                    if intention=='SAT':break
            w=_decode(first,active,pairs,n) if first is not None else None
            if w is not None and not _check_original(src,w):
                raise VerificationFailure('source witness invalid')
            status='SAT' if first is not None else 'UNSAT'
            if intention=='SAT':result={'status':status,'witness':w}
            else: result={'status':status,'count':str(count << (len(pairs)-len(active))),
                          'free_unconstrained_labels':len(pairs)-len(active),'witness':w}
            work={'active_side_labels':None,'evaluated_reduced_assignments':checked,
                  'matrix_rows_visited':0,'enumeration_cost_bound':1<<len(active)}
        expected={'schema':'ifs.cut-intention-coupled-ground.v1','source_digest':source_id,
                  'base_digest':base_id,'intention':intention,'cut':cut,
                  'label_pairs':[list(p) for p in pairs],
                  'active_labels':active,'reduced_cnf':lifted,'result':result,'work':work}
        if _canonical(certificate)!=_canonical(expected):
            raise VerificationFailure('certificate mismatch against original CNF')
        return True
    except (KeyError,IndexError,TypeError,OverflowError,RecursionError) as e:
        raise VerificationFailure('malformed source or certificate') from e
