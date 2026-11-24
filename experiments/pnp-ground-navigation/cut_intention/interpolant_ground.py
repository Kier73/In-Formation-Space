"""CIG-018: bounded Davis-Putnam resolution and proof-derived interpolants.
Source clauses split into two copies with shared observation variables.
No assignment-code enumeration. All proof nodes and executable gates are checked.
"""
from collections import defaultdict, Counter
from heapq import heappush, heappop
from time import perf_counter_ns
from composed_ground import digest
from verify_global_sufficiency import contract
from proof_refinement import ProofLanguage
from verify_interpolant_ground import InterpolantReceiver

SCHEMA='ifs.cig018.interpolant.v1'

def partitions(n,s,q,f):
    halves=[]
    for side in (0,1):
        def shift(l):return (abs(l)+side*n)*(1 if l>0 else -1)
        rows=[frozenset(map(shift,c)) for c in s]
        for j,c in enumerate(q):
            u=2*n+j+1; r=tuple(map(shift,c))
            rows.append(frozenset((-u,*r)));rows.extend(frozenset((u,-l)) for l in r)
        r=tuple(map(shift,f))
        rows.extend([frozenset(r)] if side==0 else [frozenset((-l,)) for l in r])
        halves.append(rows)
    return halves

def interpolate(leaves,steps,n,k,root):
    gates=[];cache={}
    def gate(op,a,b):
        if a==b:return a
        if a==-b:return 1 if op=='or' else -1
        zero,unit=(-1,1) if op=='or' else (1,-1)
        if zero in (a,b):return b if a==zero else a
        if unit in (a,b):return unit
        key=(op,*sorted((a,b)))
        if key not in cache:cache[key]=k+2+len(gates);gates.append(list(key))
        return cache[key]
    vals=[]
    for side,c in leaves:
        v=1 if side else -1
        if not side:
            for l in sorted(c,key=abs):
                if abs(l)>2*n:v=gate('or',v,(abs(l)-2*n+1)*(1 if l>0 else -1))
        vals.append(v)
    for a,b,p in steps:vals.append(gate('or' if p<=n else 'and',vals[a],vals[b]))
    return dict(gates=gates,output=vals[root])

def evaluate(circuit,code,k):
    values=[False,True]+[bool(code>>i&1) for i in range(k)]
    def val(r):return values[abs(r)] if r>0 else not values[-r]
    for op,a,b in circuit['gates']:values.append(val(a) and val(b) if op=='and' else val(a) or val(b))
    return int(val(circuit['output']))

def synthesize(n,source,q,f,*,max_pairs=500000,max_steps=200000,max_width=32,ordering="scope"):
    s,q,f=contract(n,source,q,f)
    if any(type(x)is not int or x<1 for x in (max_pairs,max_steps,max_width)) or ordering not in ('scope','pairs'):raise ValueError('invalid budget')
    a,b=partitions(n,s,q,f);leaves=[(0,c) for c in a]+[(1,c) for c in b];clauses=[c for _,c in leaves]
    r=dict(schema=SCHEMA,contract=digest([n,s,q,f]),status='UNKNOWN',pairs=0,eliminated=0)
    steps=[]; active={};occ=defaultdict(set);heap=[];saved=[];root=None
    def score(v):
        p,m=occ[v],occ[-v];cost=len(p)*len(m)
        # Scope-aware elimination preserves narrow source interfaces; pure literals first.
        width=len({abs(l) for i in p|m for l in clauses[i]}) if cost and ordering=='scope' else 0
        return width,cost,len(p)+len(m),v
    def push(v):
        if occ[v] or occ[-v]:heappush(heap,score(v))
    def add(c,i):
        if c in active:return
        active[c]=i
        for l in c:occ[l].add(i)
    def remove(i):
        c=clauses[i];del active[c]
        for l in c:occ[l].remove(i)
    for i,c in enumerate(clauses):
        if not c:root=i;break
        add(c,i)
    for v in range(1,2*n+len(q)+1):push(v)
    while root is None and active:
        while heap:
            entry=heappop(heap);v=entry[-1];p,m=occ[v],occ[-v]
            if (p or m) and entry==score(v):break
        else:raise AssertionError('lost active variable')
        pos,neg=sorted(p),sorted(m);removed=pos+neg
        if r['pairs']+len(pos)*len(neg)>max_pairs:return r|{'reason':'resolution pair budget'}
        r['pairs']+=len(pos)*len(neg);r['eliminated']+=1
        changed={abs(l) for i in removed for l in clauses[i]};saved.append((v,removed))
        for i in removed:remove(i)
        for i in pos:
            for j in neg:
                c=(clauses[i]-{v})|(clauses[j]-{-v})
                if any(-l in c for l in c) or c in active:continue
                if len(c)>max_width or len(steps)>=max_steps:return r|{'reason':'resolution width/step budget'}
                idx=len(clauses);clauses.append(c);steps.append([i,j,v]);add(c,idx)
                changed.update(map(abs,c))
                if not c:root=idx;break
            if root is not None:break
        for w in changed:push(w)
    if root is None:
        # Reverse elimination, preserving every removed clause. Unconstrained bits default false.
        values={}
        for v,ids in reversed(saved):
            for bit in (0,1):
                values[v]=bit
                if all(any(values.get(abs(l),0)==int(l>0) for l in clauses[i]) for i in ids):break
            else:raise AssertionError('resolution reconstruction failed')
        x=sum(values.get(i,0)<<(i-1) for i in range(1,n+1));y=sum(values.get(n+i,0)<<(i-1) for i in range(1,n+1))
        return r|dict(status='INSUFFICIENT',witness=[str(x),str(y)])
    # Keep only proof ancestors of contradiction; retain the canonical source-leaf index space.
    base=len(leaves);needed=set();todo=[root]
    while todo:
        z=todo.pop()
        if z<base or z in needed:continue
        needed.add(z);todo.extend(steps[z-base][:2])
    mapping={old:base+i for i,old in enumerate(sorted(needed))}
    def mapped(i):return i if i<base else mapping[i]
    proof=[[mapped(i),mapped(j),v] for i,j,v in (steps[z-base] for z in sorted(needed))];root=mapped(root)
    return r|dict(status='SUFFICIENT',steps=proof,root=root,decoder=interpolate(leaves,proof,n,len(q),root),generated_steps=len(steps))

class InterpolantLanguage(ProofLanguage):
    def __init__(self,n,source,*,width=12,cells=2_000_000):
        self.receiver=InterpolantReceiver(n,source);self.n=n;self.source=tuple(self.receiver.source);self.stats=Counter()
        if self._count(self.source,width,cells) is None:raise OverflowError('base count not admitted')
        self.receiver.seed()
    def interpolate_extend(self,f,**budget):
        q,_=self.snapshot();t=perf_counter_ns();r=synthesize(self.n,self.source,q,f,**budget);self.stats['interpolant_compile_ns']+=perf_counter_ns()-t
        if r['status']=='UNKNOWN':return r,False
        t=perf_counter_ns();ok=self.receiver.accept_interpolant(f,r,**budget);self.stats['interpolant_verify_ns']+=perf_counter_ns()-t
        return r,ok
