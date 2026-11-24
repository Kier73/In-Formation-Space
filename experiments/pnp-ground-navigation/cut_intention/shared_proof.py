"""CIG-019: shared, target-independent colored resolution prefix.
Each goal has its own assumptions and suffix; prefix is checked once by receiver.
CIG-020: compact multi-output decoder by structural sharing and liveness.
"""
from collections import defaultdict
from heapq import heappush, heappop
from composed_ground import digest
from verify_global_sufficiency import contract
from interpolant_ground import partitions

SCHEMA='ifs.cig019.shared.v1'

def base_rows(n,s,q):
    # Build paired observation premises, omitting each side's target clauses.
    a,b=partitions(n,s,q,(1,))
    return [(0,c) for c in a[:-1]]+[(1,c) for c in b[:-1]]

def target_rows(n,f):
    return [(0,frozenset(f))]+[(1,frozenset(((-1 if l>0 else 1)*(abs(l)+n),))) for l in f]

class Eliminate:
    def __init__(self,clauses,active=None,saved=()):
        self.rows=list(clauses);self.active={};self.occ=defaultdict(set);self.steps=[];self.saved=list(saved);self.pairs=0;self.root=None
        for i in range(len(clauses)) if active is None else active:
            self.add(i)
    def add(self,i):
        c=self.rows[i]
        if c in self.active:return
        self.active[c]=i
        for l in c:self.occ[l].add(i)
        if not c:self.root=i
    def remove(self,i):
        c=self.rows[i];del self.active[c]
        for l in c:self.occ[l].remove(i)
    def run(self,allowed,max_pairs,max_steps,max_width,scope_limit=None):
        heap=[]
        def score(v):
            p,m=self.occ[v],self.occ[-v];cost=len(p)*len(m)
            return (len({abs(l) for i in p|m for l in self.rows[i]}) if cost else 0,cost,len(p)+len(m),v)
        def push(v):
            if v in allowed and (self.occ[v] or self.occ[-v]):heappush(heap,score(v))
        for v in allowed:push(v)
        while self.root is None and heap:
            entry=heappop(heap);v=entry[-1];p,m=self.occ[v],self.occ[-v]
            if not (p or m) or entry!=score(v):continue
            if scope_limit is not None and entry[0]>scope_limit:return True
            pos,neg=sorted(p),sorted(m);removed=pos+neg
            if self.pairs+len(pos)*len(neg)>max_pairs: return False
            self.pairs+=len(pos)*len(neg);self.saved.append((v,removed));changed={abs(l) for i in removed for l in self.rows[i]}
            for i in removed:self.remove(i)
            for a in pos:
                for b in neg:
                    c=(self.rows[a]-{v})|(self.rows[b]-{-v})
                    if any(-l in c for l in c) or c in self.active:continue
                    if len(c)>max_width or len(self.steps)>=max_steps:return False
                    i=len(self.rows);self.rows.append(c);self.steps.append([a,b,v]);self.add(i);changed.update(map(abs,c))
                    if self.root is not None:break
                if self.root is not None:break
            for w in changed:push(w)
        return True
    def witness(self,n):
        values={}
        for v,ids in reversed(self.saved):
            for b in (0,1):
                values[v]=b
                if all(any(values.get(abs(l),0)==int(l>0) for l in self.rows[i]) for i in ids):break
            else:raise AssertionError('reconstruction failed')
        return [str(sum(values.get(side*n+i,0)<<(i-1) for i in range(1,n+1))) for side in (0,1)]

class Circuit:
    def __init__(self,k):self.k=k;self.gates=[];self.index={}
    def combine(self,op,a,b):
        zero,unit=(-1,1) if op=='or' else (1,-1)
        if a==b:return a
        if a==-b or unit in (a,b):return unit
        if zero in (a,b):return b if a==zero else a
        # Canonicalize complementary gates by De Morgan, reducing redundant dual forms.
        sign=1
        if a<0 and b<0:op='and' if op=='or' else 'or';a,b=-a,-b;sign=-1
        key=(op,*sorted((a,b)))
        if key not in self.index:self.index[key]=self.k+2+len(self.gates);self.gates.append(list(key))
        return sign*self.index[key]
    def leaf(self,n,side,c):
        v=1 if side else -1
        if not side:
            for l in sorted(c,key=abs):
                if abs(l)>2*n:v=self.combine('or',v,(abs(l)-2*n+1)*(1 if l>0 else -1))
        return v
    def finish(self,outputs):
        live=set();todo=[abs(v) for v in outputs if v is not None]
        while todo:
            v=todo.pop()
            if v<=self.k+1 or v in live:continue
            live.add(v);todo.extend(abs(x) for x in self.gates[v-self.k-2][1:])
        mapping={v:self.k+2+i for i,v in enumerate(sorted(live))}
        def m(r):return (1 if r>0 else -1)*mapping.get(abs(r),abs(r))
        return {'gates':[[self.gates[v-self.k-2][0],m(self.gates[v-self.k-2][1]),m(self.gates[v-self.k-2][2])] for v in sorted(live)],'outputs':[None if v is None else m(v) for v in outputs]}

def synthesize_shared(n,source,q,targets,*,max_pairs=500000,max_steps=200000,max_width=32):
    if not targets or len(targets)>128 or any(type(x)is not int or x<1 for x in (max_pairs,max_steps,max_width)):raise ValueError('contract/budget')
    s,q,_=contract(n,source,q,targets[0]);fs=[contract(n,[],[],f)[2] for f in targets]
    if len(set(fs))!=len(fs):raise ValueError('duplicate goals')
    base=base_rows(n,s,q);p=Eliminate([c for _,c in base]);protected={abs(l) for f in fs for l in f};allowed={v for v in range(1,2*n+len(q)+1) if v>2*n or (v-1)%n+1 not in protected}
    result={'schema':SCHEMA,'contract':digest([n,s,q,fs]),'status':'UNKNOWN'}
    if not p.run(allowed,max_pairs,max_steps,max_width,scope_limit=8):return result|{'reason':'prefix budget','prefix_pairs':p.pairs}
    # Active residual indices may refer to source leaves or verified prefix steps.
    active=sorted(p.active.values());circuit=Circuit(len(q));refs=[circuit.leaf(n,side,c) for side,c in base]
    for a,b,v in p.steps:refs.append(circuit.combine('or' if v<=n else 'and',refs[a],refs[b]))
    outputs=[];goals=[]
    for f in fs:
        target=target_rows(n,f);e=Eliminate(p.rows+[c for _,c in target],active+list(range(len(p.rows),len(p.rows)+len(target))),p.saved)
        if not e.run(set(range(1,2*n+len(q)+1)),max_pairs,max_steps,max_width):goals.append({'status':'UNKNOWN','pairs':e.pairs});outputs.append(None);continue
        if e.root is None:goals.append({'status':'INSUFFICIENT','witness':e.witness(n),'pairs':e.pairs});outputs.append(None);continue
        rr=refs+[circuit.leaf(n,side,c) for side,c in target]
        for a,b,v in e.steps:rr.append(circuit.combine('or' if v<=n else 'and',rr[a],rr[b]))
        outputs.append(rr[e.root]);goals.append({'status':'SUFFICIENT','steps':e.steps,'root':e.root,'pairs':e.pairs})
    return result|{'status':'COMPLETE','prefix':p.steps,'active':active,'prefix_pairs':p.pairs,'goals':goals,'circuit':circuit.finish(outputs)}

def evaluate(circuit,code,k):
    vals=[False,True]+[bool(code>>i&1) for i in range(k)]
    def read(r):return vals[abs(r)] if r>0 else not vals[-r]
    for op,a,b in circuit['gates']:vals.append(read(a) and read(b) if op=='and' else read(a) or read(b))
    return [None if x is None else int(read(x)) for x in circuit['outputs']]
