"""Independent CIG-006 SAT/#SAT verifier: source re-encoding, independent
GF(2) elimination, CNF component audit, checked DPLL conflict trees.
No import from the heavy-ground producer; no trust in measured wall time.
"""
from __future__ import annotations
from collections import defaultdict
from itertools import combinations
from hashlib import sha256
import json

SCHEMA='ifs.cig006.source-formed-heavy-ground.v1'

class Reject(ValueError):pass

def _hash(x):return sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def _source(clauses,n):
    if type(n)is not int or not 1<=n<=1024 or len(clauses)>10000:raise Reject('source dimension')
    unique=set()
    for raw in clauses:
        if not isinstance(raw,(list,tuple)) or len(raw)>32 or any(type(x)is not int or x==0 or abs(x)>n for x in raw):
            raise Reject('malformed original CNF')
        c=set(raw)
        if any(-x in c for x in c):continue
        unique.add(tuple(sorted(c,key=lambda l:(abs(l),l<0))))
    return tuple(sorted(unique,key=lambda c:(len(c),c)))

def _true(clauses,mask):
    for c in clauses:
        if not any(bool(mask&(1<<(abs(l)-1)))==(l>0) for l in c):return False
    return True

def _xor_by_source(rows):
    groups={}
    for row in rows:
        scope=tuple(sorted(abs(l) for l in row))
        if not scope or len(scope)>3:return None
        groups.setdefault(scope,set()).add(tuple(row))
    result=[]
    for scope,clauses in sorted(groups.items()):
        found=[]
        for rhs in (0,1):
            forbidden=set()
            for bits in range(1<<len(scope)):
                if bits.bit_count()%2!=rhs:
                    cl=tuple(sorted(((-v if bits&(1<<i) else v)
                                     for i,v in enumerate(scope)),key=lambda l:(abs(l),l<0)))
                    forbidden.add(cl)
            if forbidden==clauses:found.append(rhs)
        if len(found)!=1:return None
        result.append((sum(1<<(v-1) for v in scope),found[0]))
    return tuple(result)

def _rank_and_inconsistency(equations):
    # Independent forward Gaussian elimination with ascending pivot, not the
    # producer's descending-pivot partial reduction.
    pivots={};first_bad=None
    for index,(mask,b) in enumerate(equations):
        row=mask;bit=b
        for p in sorted(pivots):
            if row&(1<<p):row^=pivots[p][0];bit^=pivots[p][1]
        if not row:
            if bit:first_bad=index;break
            continue
        pivot=(row&-row).bit_length()-1
        pivots[pivot]=(row,bit)
    return len(pivots),first_bad

def _parts(clauses,n):
    graph=[set() for _ in range(n+1)]
    for row in clauses:
        scope=set(abs(l) for l in row)
        for v in scope:graph[v].update(scope-{v})
    pending=set(range(1,n+1));parts=[]
    while pending:
        start=min(pending);pending.remove(start);nodes={start};stack=[start]
        while stack:
            for nxt in graph[stack.pop()]:
                if nxt in pending:pending.remove(nxt);nodes.add(nxt);stack.append(nxt)
        order=tuple(sorted(nodes));translate={v:i+1 for i,v in enumerate(order)}
        local=tuple(tuple((1 if l>0 else -1)*translate[abs(l)] for l in clause)
          for clause in clauses if clause and abs(clause[0]) in nodes)
        parts.append((order,local))
    return sorted(parts,key=lambda item:item[0][0])

def _reduce_units(source,partial):
    a=dict(partial)
    while True:
        changed=False
        for row in source:
            good=False;free=[]
            for l in row:
                v=abs(l)
                if v in a:
                    if a[v]==int(l>0):good=True;break
                else:free.append(l)
            if good:continue
            if not free:return None,'conflict'
            if len(free)==1:
                l=free[0];v=abs(l);b=int(l>0)
                if v not in a:a[v]=b;changed=True
                elif a[v]!=b:return None,'conflict'
        if not changed:break
    complete=all(any(abs(l) in a and a[abs(l)]==int(l>0) for l in row) for row in source)
    return a,'sat' if complete else 'open'

def _check_unsat_tree(source,n,tree):
    steps=[0]
    def walk(node,partial):
        steps[0]+=1
        if steps[0]>200001:raise Reject('excessive contradiction proof size')
        a,status=_reduce_units(source,partial)
        if status=='conflict':
            if node!={'leaf':'conflict'}:raise Reject('false conflict leaf')
            return
        if status=='sat':raise Reject('UNSAT tree contains satisfiable partial assignment')
        if type(node)is not dict or set(node)!={'branch','zero','one'}:
            raise Reject('incomplete nonconflicting proof branch')
        v=node['branch']
        if type(v)is not int or not 1<=v<=n or v in a:
            raise Reject('branch does not cover a fresh variable')
        walk(node['zero'],{**a,v:0});walk(node['one'],{**a,v:1})
    walk(tree,{})
    return steps[0]

def _check_solver_result(clauses,n,intent,record):
    if type(record) is not dict or record.get('status') not in ('SAT','UNSAT','UNKNOWN'):
        raise Reject('invalid finite solver status')
    status=record['status']
    if status=='UNKNOWN':
        if record.get('reason')!='node_or_wall_budget' or any(k in record for k in ('count','unsat_proof','witness')):
            raise Reject('UNKNOWN not distinct from a completed result')
        return
    if status=='SAT':
        v=record.get('witness')
        if type(v)is not str or not v.isdecimal() or v!=str(int(v)) or int(v)>=1<<n or not _true(clauses,int(v)):
            raise Reject('bad original-CNF SAT witness')
        if intent=='#SAT':
            # Campaign admits exact non-XOR model counts only on small bags.
            # Independent exhaustive count, rather than trusting producer search.
            if n>18:raise Reject('large #SAT requires a separate admitted proof')
            known=sum(_true(clauses,i) for i in range(1<<n))
            if record.get('count')!=str(known):raise Reject('model count is not source-correct')
    elif status=='UNSAT':
        if intent=='#SAT' and record.get('count')!='0':raise Reject('UNSAT count must be zero')
        if _check_unsat_tree(clauses,n,record.get('unsat_proof')) > 200001:
            raise Reject('incomplete unsat evidence')
    if (type(record.get('nodes')) is not int or record['nodes']<1 or
        type(record.get('literal_checks')) is not int or record['literal_checks']<0 or
        type(record.get('wall_ms')) not in (float,int) or record['wall_ms']<0):
        raise Reject('invalid search ledger')

def verify(clauses,n,packet,*,expected_intention=None):
    try:
        if type(packet)is not dict or packet.get('schema')!=SCHEMA:raise Reject('unknown heavy Ground schema')
        original={'n':n,'clauses':[list(row) for row in clauses]}
        if packet['source_digest']!=_hash(original):raise Reject('source identity changed')
        intent=packet['intention']
        if expected_intention is not None and intent!=expected_intention:raise Reject('receiver changed exact intention')
        if intent not in ('SAT','#SAT'):raise Reject('unsupported heavy intention')
        source=_source(clauses,n)
        if packet['normalized_source']!=[list(c) for c in source]:raise Reject('normalized source altered')
        budgets=packet['budgets']
        if type(budgets.get('max_nodes'))is not int or not 1<=budgets['max_nodes']<=100000 or not 0<budgets.get('wall_seconds',0)<=60:
            raise Reject('unbounded search budget')
        kind=packet['chosen_family'];evidence=packet['evidence'];result=packet['result']
        if () in source:
            if kind!='explicit-contradiction' or evidence!={} or result!={'status':'UNSAT','count':'0' if intent=='#SAT' else None,'witness':None}:
                raise Reject('explicit contradiction source changed')
        else:
            xor=_xor_by_source(source)
            if xor is not None:
                if kind!='exact-source-XOR-GF2' or evidence['equations']!=[[str(a),b] for a,b in xor]:
                    raise Reject('source XOR reconstruction differs')
                rank,bad=_rank_and_inconsistency(xor)
                # For contradictory equations, producer stops at first 0=1.
                if evidence['rank']!=rank:raise Reject('GF2 rank was forged')
                if bad is not None:
                    subset=evidence.get('contradiction_sources')
                    if not isinstance(subset,list) or not subset or any(type(i)is not int or i<0 or i>bad for i in subset):
                        raise Reject('missing GF2 0=1 proof')
                    mask=0;rhs=0
                    for i in subset:mask^=xor[i][0];rhs^=xor[i][1]
                    if mask or rhs!=1:raise Reject('XOR contradiction combination invalid')
                    if result!={'status':'UNSAT','count':'0' if intent=='#SAT' else None,'witness':None}:
                        raise Reject('contradictory XOR source reported SAT')
                else:
                    if result['status']!='SAT' or result['count']!=(str(1<<(n-rank)) if intent=='#SAT' else None):
                        raise Reject('solvable GF2 rank or count forged')
                    witness=result.get('witness')
                    if not isinstance(witness,str) or not witness.isdecimal() or int(witness)>=1<<n or not _true(source,int(witness)):
                        raise Reject('GF2 model is not an original-CNF witness')
            else:
                comp=_parts(source,n)
                if len(comp)>1:
                    if kind!='source-connected-components' or evidence['sizes']!=[len(v) for v,_ in comp]:
                        raise Reject('source structural factorization changed')
                    records=evidence['components']
                    if len(records)!=len(comp):raise Reject('missing exact source component')
                    statuses=[];counts=[];joined=0
                    for ((variables,local),data) in zip(comp,records):
                        if data['variables']!=list(variables):raise Reject('component variable mapping altered')
                        r=data['result'];_check_solver_result(local,len(variables),intent,r)
                        statuses.append(r['status'])
                        if r['status']=='SAT':
                            x=int(r['witness'])
                            joined|=sum(((x>>i)&1)<<(v-1) for i,v in enumerate(variables))
                            if intent=='#SAT':counts.append(int(r['count']))
                    status='UNSAT' if 'UNSAT' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'SAT'
                    expected_count=('0' if status=='UNSAT' else str(__import__('math').prod(counts))) if intent=='#SAT' and status!='UNKNOWN' else None
                    expected_witness=str(joined) if status=='SAT' else None
                    if result!={'status':status,'count':expected_count,'witness':expected_witness}:
                        raise Reject('joined source result or #SAT product invalid')
                    if status=='SAT' and not _true(source,joined):raise Reject('joined model invalid')
                else:
                    if kind!='bounded-source-DPLL':raise Reject('source interpreter family fabricated')
                    record=evidence['search'];_check_solver_result(source,n,intent,record)
                    if result!={'status':record['status'],'count':record.get('count'),'witness':record.get('witness')}:
                        raise Reject('direct DPLL evidence was altered')
        if packet['provenance']!='original CNF; no uncharged oracle, materialized advice or external hosts':
            raise Reject('execution-provenance scope forged')
        return True
    except (KeyError,IndexError,TypeError,ValueError,OverflowError) as error:
        if isinstance(error,Reject):raise
        raise Reject('unverifiable exact source-ground receipt') from error
