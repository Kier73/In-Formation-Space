"""CIG-006 heavy SAT/#SAT source-ground dispatcher, standard library.

Three exact architectures: fully re-encoded XOR/GF(2), independently factored
connected CNF components, and complete bounded unit-propagating DPLL.
UNKNOWN is a distinct budget outcome. UNSAT DPLL publishes a checkable binary
branch proof whose leaves are original-clause contradictions after independently
recomputed unit propagation. No universal complexity claim.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from hashlib import sha256
from itertools import combinations
import json,time,random

SCHEMA='ifs.cig006.source-formed-heavy-ground.v1'

class Refusal(ValueError):pass
class Budget(Exception):pass

def _hash(o):return sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def normalize(clauses,n):
    if (type(n)is not int or not 1<=n<=1024 or not isinstance(clauses,(list,tuple))
        or len(clauses)>10000):raise Refusal('invalid bounded CNF')
    rows=set()
    for row in clauses:
        if not isinstance(row,(list,tuple)) or len(row)>32 or any(type(v)is not int or v==0 or abs(v)>n for v in row):
            raise Refusal('malformed source literal')
        term=set(row)
        if any(-v in term for v in term):continue
        rows.add(tuple(sorted(term,key=lambda v:(abs(v),v<0))))
    return tuple(sorted(rows,key=lambda r:(len(r),r)))

def accepts(clauses,assignment):
    return all(any(((assignment>>(abs(l)-1))&1)==int(l>0) for l in row) for row in clauses)

def xor_encoding(scope,rhs):
    # Full source CNF forbids the *opposite* parity assignments.
    return tuple(tuple((v if not ((pattern>>j)&1) else -v) for j,v in enumerate(scope))
       for pattern in range(1<<len(scope)) if (pattern.bit_count()&1)!=rhs)

def detect_xor(clauses):
    byscope=defaultdict(set)
    for row in clauses:
        scope=tuple(sorted(abs(x) for x in row))
        if len(scope)>3 or not scope:return None
        byscope[scope].add(row)
    equations=[];assembled=set()
    for scope,rows in sorted(byscope.items()):
        choice=[]
        for rhs in (0,1):
            # Original forbidden-pattern clause semantics, independent of signs.
            expected=set(xor_encoding(scope,rhs))
            # Source normalization sort key (variable index then sign).
            canonical=set(tuple(sorted(r,key=lambda v:(abs(v),v<0))) for r in expected)
            if rows==canonical:choice.append(rhs)
        if len(choice)!=1:return None
        rhs=choice[0];equations.append((sum(1<<(v-1) for v in scope),rhs))
        assembled.update(rows)
    if assembled!=set(clauses):return None
    return tuple(equations)

def solve_linear(equations,n):
    basis={};provenance=[]
    for mask,rhs in equations:
        row=mask;bit=rhs;origin=1<<len(provenance);provenance.append((mask,rhs))
        while row:
            pivot=row.bit_length()-1
            if pivot in basis:
                m,b,old=basis[pivot];row^=m;bit^=b;origin^=old
            else:
                basis[pivot]=(row,bit,origin);break
        if row==0 and bit:
            return {'status':'UNSAT','rank':len(basis),'count':0,
                    'xor_contradiction_sources':[i for i in range(len(provenance)) if origin>>i&1]}
    state=0
    for pivot in sorted(basis):
        mask,rhs,_=basis[pivot]
        value=rhs^((mask&state).bit_count()&1)
        state |= value<<pivot
    return {'status':'SAT','rank':len(basis),'count':1<<(n-len(basis)),'witness':state}

def components(clauses,n):
    parent=list(range(n+1))
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    for row in clauses:
        vs=[abs(l) for l in row]
        for v in vs[1:]:
            a,b=find(vs[0]),find(v)
            if a!=b:parent[max(a,b)]=min(a,b)
    groups={}
    for x in range(1,n+1):groups.setdefault(find(x),[]).append(x)
    output=[]
    for _,variables in sorted(groups.items(),key=lambda item:item[1][0]):
        remap={v:i+1 for i,v in enumerate(variables)}
        rows=[tuple((1 if l>0 else -1)*remap[abs(l)] for l in row)
              for row in clauses if row and abs(row[0]) in remap]
        output.append((tuple(variables),tuple(rows)))
    return output

def _propagate(clauses,assign):
    # Direct original-clause scans: exact unit propagation, never inferred SAT.
    scans=0;assignment=dict(assign)
    while True:
        changed=False
        for row in clauses:
            scans+=len(row)
            possible=[];satisfied=False
            for lit in row:
                v=abs(lit)
                if v not in assignment:possible.append(lit)
                elif assignment[v]==int(lit>0):satisfied=True;break
            if satisfied:continue
            if not possible:return None,scans,'contradiction'
            if len(possible)==1:
                lit=possible[0];v=abs(lit);b=int(lit>0)
                if v in assignment and assignment[v]!=b:return None,scans,'contradiction'
                if v not in assignment:assignment[v]=b;changed=True
        if not changed:break
    if all(any((v:=abs(l)) in assignment and assignment[v]==int(l>0) for l in row) for row in clauses):
        return assignment,scans,'satisfied'
    return assignment,scans,'pending'

def dpll(clauses,n,intent='SAT',*,max_nodes=5000,seconds=3.0,with_proof=True):
    started=time.perf_counter();nodes=0;literal_checks=0
    if intent not in ('SAT','#SAT'):raise Refusal('unknown exact DPLL intention')
    def visit(partial):
        nonlocal nodes,literal_checks
        nodes+=1
        if nodes>max_nodes or time.perf_counter()-started>seconds:raise Budget()
        current,scans,status=_propagate(clauses,partial);literal_checks+=scans
        if status=='contradiction':return 0,None,{'leaf':'conflict'}
        if status=='satisfied':
            witness=sum(b<<(v-1) for v,b in current.items())
            return (1<<(n-len(current))) if intent=='#SAT' else 1,witness,{'leaf':'sat'}
        # Weighted appearance in live clauses, with deterministic ties.
        scores=Counter()
        for row in clauses:
            if any(abs(l) in current and current[abs(l)]==int(l>0) for l in row):continue
            remaining=[abs(l) for l in row if abs(l) not in current]
            if not remaining:raise AssertionError('propagation missed contradiction')
            weight=1<<max(0,4-min(len(remaining),4))
            for v in remaining:scores[v]+=weight
        variable=min(scores,key=lambda v:(-scores[v],v))
        low,wa,pl=visit({**current,variable:0})
        if intent=='SAT' and low:return 1,wa,None
        high,wb,ph=visit({**current,variable:1})
        if intent=='SAT' and high:return 1,wb,None
        return low+high,wa if wa is not None else wb,{'branch':variable,'zero':pl,'one':ph}
    try:
        count,witness,proof=visit({})
    except Budget:
        return {'status':'UNKNOWN','reason':'node_or_wall_budget',
                'nodes':nodes,'literal_checks':literal_checks,'wall_ms':round(1000*(time.perf_counter()-started),3)}
    if witness is not None and not accepts(clauses,witness):raise AssertionError('DPLL witness failed source')
    result={'status':'SAT' if count else 'UNSAT','count':str(count) if intent=='#SAT' else None,
            'witness':str(witness) if witness is not None else None,
            'nodes':nodes,'literal_checks':literal_checks,'wall_ms':round(1000*(time.perf_counter()-started),3)}
    if not count and with_proof:result['unsat_proof']=proof
    return result

def compile_ground(clauses,n,*,intent='SAT',max_nodes=5000,wall_seconds=3.0):
    start=time.perf_counter_ns()
    if intent not in ('SAT','#SAT') or type(max_nodes)is not int or not 1<=max_nodes<=100000 or not 0<wall_seconds<=60:
        raise Refusal('invalid intention or budget')
    raw=[list(row) for row in clauses]
    normalized=normalize(clauses,n)
    if () in normalized:
        result={'status':'UNSAT','count':'0' if intent=='#SAT' else None,'witness':None}
        family='explicit-contradiction';info={}
    else:
        equations=detect_xor(normalized)
        if equations is not None:
            linear=solve_linear(equations,n)
            result={'status':linear['status'],
                'count':str(linear['count']) if intent=='#SAT' else None,
                'witness':str(linear['witness']) if linear.get('witness') is not None else None}
            family='exact-source-XOR-GF2';info={'rank':linear['rank'],
                 'equations':[[str(m),rhs] for m,rhs in equations],
                 'contradiction_sources':linear.get('xor_contradiction_sources')}
        else:
            comps=components(normalized,n)
            if len(comps)>1:
                family='source-connected-components';info={'sizes':[len(v) for v,_ in comps]}
                counts=[];witness=0;cases=[];any_unknown=False;any_unsat=False
                for variables,local in comps:
                    r=dpll(local,len(variables),intent,max_nodes=max_nodes,seconds=wall_seconds)
                    cases.append({'variables':list(variables),'result':r})
                    if r['status']=='UNSAT':any_unsat=True
                    elif r['status']=='UNKNOWN':any_unknown=True
                    else:
                        counts.append(int(r['count']) if intent=='#SAT' else 1)
                        w=int(r['witness'])
                        witness |= sum(((w>>i)&1)<<(v-1) for i,v in enumerate(variables))
                info['components']=cases
                status='UNSAT' if any_unsat else 'UNKNOWN' if any_unknown else 'SAT'
                result={'status':status,'count':('0' if any_unsat else (str(__import__('math').prod(counts)) if not any_unknown else None))
                        if intent=='#SAT' else None,
                        'witness':str(witness) if status=='SAT' else None}
            else:
                family='bounded-source-DPLL';info={'search':dpll(normalized,n,intent,max_nodes=max_nodes,seconds=wall_seconds)}
                r=info['search'];result={'status':r['status'],'count':r.get('count'),'witness':r.get('witness')}
    if result['status']=='SAT' and not accepts(normalized,int(result['witness'])):
        raise AssertionError('chosen source Ground published invalid witness')
    report={'schema':SCHEMA,'source_digest':_hash({'n':n,'clauses':raw}),
        'intention':intent,'budgets':{'max_nodes':max_nodes,'wall_seconds':wall_seconds},
        'normalized_source':[list(c) for c in normalized],
        'chosen_family':family,'evidence':info,'result':result,
        'provenance':'original CNF; no uncharged oracle, materialized advice or external hosts'}
    return report,{'full_construction_ns':time.perf_counter_ns()-start}
