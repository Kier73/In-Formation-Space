"""CIG-009: verified, sparse conditional-count messages on a frozen region tree.

No persistent trust or host authority is implied by a content hash. The session
admits a message only after independent checking against its expected source
and admitted child messages. Revisions rebind the entire original source.
"""
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import product
from time import perf_counter_ns
import json
from composed_ground import canonical, extract, project

VERSION = 'ifs.cig009.count-message.v1'
MAX_LEAF = 10
MAX_JOIN = 12
MAX_LEAVES = 8192


def wire(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def identity(obj):
    return sha256(wire(obj)).hexdigest()


def discover(clauses, n, width=8):
    """Source biconnected regions, bounded greedy block packing. No fixture labels."""
    if type(width) is not int or not 1 <= width <= MAX_LEAF:
        raise ValueError('leaf width')
    rows = canonical(clauses, n)
    graph = [set() for _ in range(n+1)]
    for row in rows:
        s = set(map(abs, row))
        if len(s) > width:
            raise OverflowError('clause exceeds leaf budget')
        for v in s:
            graph[v].update(s-{v})
    # Iterative Tarjan edge-stack biconnected decomposition of the primal
    # graph. Every clause clique belongs to one block. Postorder keeps the
    # branches of a block-cut tree adjacent; no recursion-depth assumption.
    tick=0; seen={}; low={}; parent={}; edges=[]; blocks=[]
    for start in range(1,n+1):
        if start in seen: continue
        tick+=1; seen[start]=low[start]=tick; parent[start]=None
        if not graph[start]: blocks.append([start]); continue
        stack=[(start,iter(sorted(graph[start])))]
        while stack:
            v,it=stack[-1]
            try: w=next(it)
            except StopIteration:
                stack.pop(); p=parent[v]
                if p is not None:
                    low[p]=min(low[p],low[v])
                    if low[v]>=seen[p]:
                        block=set()
                        while edges:
                            e=edges.pop(); block.update(e)
                            if e==(p,v):break
                        blocks.append(sorted(block))
                continue
            if w not in seen:
                parent[w]=v; tick+=1; seen[w]=low[w]=tick
                edges.append((v,w)); stack.append((w,iter(sorted(graph[w]))))
            elif w!=parent[v] and seen[w]<seen[v]:
                edges.append((v,w)); low[v]=min(low[v],seen[w])
    if any(len(s)>width for s in blocks):
        raise OverflowError('biconnected region exceeds leaf budget')
    leaves=[]; scope=set()
    for block in blocks:
        if len(scope|set(block))>width:
            leaves.append(sorted(scope)); scope=set()
        scope.update(block)
    if scope: leaves.append(sorted(scope))
    return {'n':n,'leaves':leaves}


def bind(clauses,n,plan):
    """Rebind *all* clauses to a frozen layout; fail if no leaf owns a clause."""
    rows=canonical(clauses,n)
    leaves=plan['leaves']
    if type(plan['n']) is not int or plan['n']!=n or not 1<=len(leaves)<=MAX_LEAVES:
        raise ValueError('plan domain')
    owners=defaultdict(list); sets=[]
    for i,s in enumerate(leaves):
        if type(s) is not list or len(s)>MAX_LEAF or any(type(v) is not int or not 1<=v<=n for v in s) or s!=sorted(set(s)):
            raise ValueError('leaf scope')
        sets.append(set(s))
        for v in s: owners[v].append(i)
    if len(owners)!=n: raise ValueError('missing source coordinates')
    assigned=[[] for _ in leaves]
    for row in rows:
        s=set(map(abs,row))
        possible=owners[min(s,key=lambda v:(len(owners[v]),v))] if s else range(len(leaves))
        for i in possible:
            if s<=sets[i]: assigned[i].append(list(row)); break
        else: raise OverflowError('revision crosses region layout; replan required')
    totals=Counter(v for s in leaves for v in s)
    def tree(a,b):
        if b-a==1:
            f=Counter(leaves[a]); children=None
        else:
            m=(a+b)//2; left,lf=tree(a,m); right,rf=tree(m,b)
            f=lf+rf; children=(left,right)
        boundary=tuple(sorted(v for v,k in f.items() if k<totals[v]))
        if len(boundary)>MAX_JOIN: raise OverflowError('boundary budget')
        if children and len(set(children[0]['boundary'])|set(children[1]['boundary']))>MAX_JOIN:
            raise OverflowError('join budget')
        return {'span':(a,b),'boundary':boundary,'children':children},f
    root,_=tree(0,len(leaves))
    return rows,assigned,root


def descriptor(node,plan,assigned,children):
    a,b=node['span']; boundary=list(node['boundary'])
    if children is None:
        return {'version':VERSION,'boundary':boundary,'scope':plan['leaves'][a], 'clauses':assigned[a]}
    return {'version':VERSION,'boundary':boundary,'children':[identity(c) for c in children]}


def index(scope, a):
    return sum(a[v]<<j for j,v in enumerate(scope))


def produce(desc, children):
    boundary=desc['boundary']; counts=[0]*(1<<len(boundary))
    if children is None:
        scope=desc['scope']; local={v:i+1 for i,v in enumerate(scope)}
        rows=sorted([tuple((local[abs(l)] if l>0 else -local[abs(l)]) for l in c) for c in desc['clauses']],key=lambda c:(len(c),c))
        eqs,residual=extract(rows)
        if not residual:
            hidden=sorted(set(local.values())-{local[v] for v in boundary})
            pivots,projected,_=project(eqs,hidden)
            for z in range(len(counts)):
                x=sum((z>>j&1)<<(local[v]-1) for j,v in enumerate(boundary))
                if all((m&x).bit_count()%2==rhs for m,rhs in projected):
                    counts[z]=1<<(len(hidden)-len(pivots))
            route='affine'; work=len(counts)
        else:
            route='boolean'; work=1<<len(scope)
            masks=[[(1<<(abs(l)-1),l>0) for l in c] for c in rows]
            for x in range(work):
                if all(any(bool(x&m)==sign for m,sign in c) for c in masks):
                    z=sum((x>>(local[v]-1)&1)<<j for j,v in enumerate(boundary)); counts[z]+=1
    else:
        route='join'; scope=sorted(set().union(*(c['boundary'] for c in children))); work=1<<len(scope)
        for x in range(work):
            a={v:x>>j&1 for j,v in enumerate(scope)}
            counts[index(boundary,a)]+=int(children[0]['counts'][index(children[0]['boundary'],a)])*int(children[1]['counts'][index(children[1]['boundary'],a)])
    return {'key':identity(desc),'boundary':boundary,'counts':[str(c) for c in counts]},route,work


class VerifiedMemory:
    """Receiver-owned RAM cache. No API admitting a hash as proof."""
    def __init__(self): self.__admitted={}
    def obtain(self,desc,children,incoming=None):
        from verify_regional_memory import verify_message
        if children is not None:
            if any(self.__admitted.get(c['key'])!=wire(c) for c in children):
                raise ValueError('child message not independently admitted')
        key=identity(desc)
        if key in self.__admitted:
            return json.loads(self.__admitted[key]),'reuse',0,0,0
        t=perf_counter_ns()
        if incoming is None:
            msg,route,work=produce(desc,children)
        else:
            msg=incoming[key]; route='received'; work=0
        compile_ns=perf_counter_ns()-t
        t=perf_counter_ns()
        if not verify_message(desc,children,msg): raise ValueError('message failed independent check')
        verify_ns=perf_counter_ns()-t
        self.__admitted[key]=wire(msg)
        return json.loads(self.__admitted[key]),route,work,compile_ns,verify_ns


def realize(clauses,n,plan,memory=None,*,incoming=None,witness=True):
    """Count from scratch or reuse only independently admitted exact messages."""
    memory=VerifiedMemory() if memory is None else memory
    t=perf_counter_ns(); rows,assigned,root=bind(clauses,n,plan)
    from verify_regional_memory import audit_layout
    if not audit_layout(clauses,n,plan,assigned,root):raise ValueError('layout failed independent source audit')
    bound=perf_counter_ns()-t
    records={}; metrics=Counter(); message_for={}
    def visit(node):
        children=None if node['children'] is None else [visit(c) for c in node['children']]
        d=descriptor(node,plan,assigned,children)
        msg,route,work,comp,check=memory.obtain(d,children,incoming)
        metrics[route]+=1; metrics['producer_cells']+=work; metrics['compile_ns']+=comp; metrics['check_ns']+=check
        records[msg['key']]=msg; message_for[node['span']]=msg
        return msg
    t=perf_counter_ns(); final=visit(root); navigation_ns=perf_counter_ns()-t
    count=int(final['counts'][0]); state=None
    t=perf_counter_ns()
    if count and witness:
        a={}
        def descend(node):
            if node['children'] is None:
                i=node['span'][0]; s=plan['leaves'][i]; unknown=[v for v in s if v not in a]
                for bits in product((0,1),repeat=len(unknown)):
                    a.update(zip(unknown,bits))
                    if all(any(a[abs(l)]==int(l>0) for l in c) for c in assigned[i]): return
                raise AssertionError('missing leaf witness')
            left,right=node['children']; lc,rc=[message_for[c['span']] for c in (left,right)]
            unknown=sorted((set(lc['boundary'])|set(rc['boundary']))-set(a))
            for bits in product((0,1),repeat=len(unknown)):
                a.update(zip(unknown,bits))
                if int(lc['counts'][index(lc['boundary'],a)]) and int(rc['counts'][index(rc['boundary'],a)]):
                    descend(left); descend(right); return
            raise AssertionError('missing join witness')
        descend(root)
        if set(a)!=set(range(1,n+1)) or not all(any(a[abs(l)]==int(l>0) for l in c) for c in rows): raise AssertionError('invalid source witness')
        state=''.join(str(a[v]) for v in range(1,n+1))
    reconstruction=perf_counter_ns()-t
    return {'source':identity([n,rows]),'plan':identity(plan),'root':identity(final),'count':str(count),'witness':state,
            'messages':records,'metrics':dict(metrics),'bind_ns':bound,'navigation_ns':navigation_ns,'witness_ns':reconstruction}
