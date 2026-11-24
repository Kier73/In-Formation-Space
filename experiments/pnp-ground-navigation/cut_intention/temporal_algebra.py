"""CIG-024: reduced ordered multi-valued decision diagrams of CRT time sets.
Periodic tails are encoded over pairwise coprime prime-power coordinates.
Finite transient prefixes are kept separately. All budgets are explicit.
"""
from math import lcm,prod
from heapq import heappush,heappop
from inverse_time import spatial_groups,merge
from temporal_ground import contract_code,contract_time

class Budget(Exception): pass

def factors(n):
    out={};p=2
    while p*p<=n:
        while n%p==0:out[p]=out.get(p,1)*p;n//=p
        p+=1
    if n>1:out[n]=n
    return out

def radices(periods):
    f={}
    for L in periods:
        for p,q in factors(L).items():f[p]=max(f.get(p,1),q)
    return tuple(f[p] for p in sorted(f))

class Diagram:
    def __init__(self,base,max_work=2_000_000):
        self.base=tuple(base);self.nodes=[];self.unique={};self.cache={};self.work=0;self.limit=max_work
    def charge(self,n=1):
        self.work+=n
        if self.work>self.limit:raise Budget('diagram work')
    def level(self,i):return len(self.base) if i<2 else self.nodes[i-2][0]
    def at(self,i,j,a):return self.nodes[i-2][1][a] if self.level(i)==j else i
    def node(self,j,kids):
        self.charge(len(kids));kids=tuple(kids)
        if len(set(kids))==1:return kids[0]
        key=(j,kids)
        if key not in self.unique:self.unique[key]=len(self.nodes)+2;self.nodes.append(key)
        return self.unique[key]
    def apply(self,op,x,y=0):
        if op!='not' and x>y:x,y=y,x
        key=(op,x,y)
        if key in self.cache:return self.cache[key]
        self.charge()
        if x<2 and (op=='not' or y<2):z=(1-x if op=='not' else x&y if op=='and' else x|y if op=='or' else x^y)
        elif op!='not' and x==y:z=0 if op=='xor' else x
        elif op=='and' and x==0:z=0
        elif op=='and' and x==1:z=y
        elif op=='or' and x==0:z=y
        elif op=='or' and x==1:z=1
        elif op=='xor' and x==0:z=y
        else:
            j=self.level(x) if op=='not' else min(self.level(x),self.level(y))
            z=self.node(j,[self.apply(op,self.at(x,j,a),self.at(y,j,a)) for a in range(self.base[j])])
        self.cache[key]=z;return z
    def atom(self,L,yes):
        from math import gcd
        ls=[(j,gcd(b,L)) for j,b in enumerate(self.base) if gcd(b,L)>1]
        def visit(i,r,m):
            self.charge()
            if i==len(ls):return int(r in yes)
            j,d=ls[i];sub=[visit(i+1,merge(r,m,a,d),m*d) for a in range(d)]
            return self.node(j,[sub[a%d] for a in range(self.base[j])])
        return visit(0,0,1)
    def value(self,x,t):
        while x>=2:
            j,kids=self.nodes[x-2];x=kids[t%self.base[j]]
        return x
    def shift(self,x,delta):
        # Pullback: output set contains t iff old set contains t+delta.
        key=('shift',x,delta%prod(self.base))
        if key in self.cache:return self.cache[key]
        self.charge()
        if x<2:return x
        j,kids=self.nodes[x-2];z=self.node(j,[self.shift(kids[(a+delta)%self.base[j]],delta) for a in range(self.base[j])]);self.cache[key]=z;return z
    def count(self,x):
        cache={0:0,1:1};N=len(self.base)
        def sub(i):
            if i not in cache:
                j,kids=self.nodes[i-2];cache[i]=sum(prod(self.base[j+1:self.level(v)])*sub(v) for v in kids)
            return cache[i]
        return prod(self.base[:self.level(x)])*sub(x)
    def next(self,x,start,max_states=100_000):
        # A partial path constrains a CRT class. The minimum of that class
        # is an admissible lower bound; terminal one is an entire feasible class.
        q=[];states=[];trace=[]
        def add(v,r,m):
            if v==0:return
            i=len(states);states.append((v,r,m));heappush(q,(start+(r-start)%m,i))
        add(x,0,1)
        while q:
            if len(states)>max_states:return None,trace,'UNKNOWN'
            t,i=heappop(q);v,r,m=states[i]
            if v==1:return t,trace,'FOUND'
            trace.append(i);j,kids=self.nodes[v-2];b=self.base[j]
            for a,u in enumerate(kids):
                if u:add(u,merge(r,m,a,b),m*b)
        return None,trace,'UNREACHABLE'

def compile_algebra(nav,initial,*,max_cells=2_000_000,max_work=2_000_000):
    k,w,a,g,c=nav.k,nav.w,nav.a,nav.g,nav.decoder['circuit'];contract_code(initial,k)
    vs=[i*a+(initial>>(i*w)&(a-1)) for i in range(k//w)];D=max(g['depth'][v] for v in vs)
    groups=spatial_groups(g['pred']);periods=[lcm(*(len(nav.pos[g['entry'][vs[i]]][0]) for i in z)) for z in groups]
    owner={i:j for j,z in enumerate(groups) for i in z};live={abs(v) for v in c['outputs']}
    for j in reversed(range(k+2,k+2+len(c['gates']))):
        if j in live:live.update(map(abs,c['gates'][j-k-2][1:]))
    bits=sorted(v-2 for v in live if 2<=v<=k+1);base=radices(periods);d=Diagram(base,max_work);refs={1:1};cells=D*(len(vs)+len(c['gates'])+1)
    if cells>max_cells:raise Budget('prefix')
    prefix=[nav.result(initial,t)['outputs'] for t in range(D)]
    anchor=nav.jump(initial,D)
    for j,z in enumerate(groups):
        selected=[i for i in bits if owner[i//w]==j]
        if not selected:continue
        L=periods[j];cells+=L*(len(z)+len(selected))
        if cells>max_cells:raise Budget('local cells')
        cur={i:anchor>>(i*w)&(a-1) for i in z};yes={i:set() for i in selected}
        for dt in range(L):
            for i in selected:
                if cur[i//w]>>(i%w)&1:yes[i].add((D+dt)%L)
            cur={i:g['tables'][i][cur[g['pred'][i]]] for i in z}
        for i in selected:refs[i+2]=d.atom(L,yes[i])
    def get(v):return refs[v] if v>0 else d.apply('not',refs[-v])
    for j,(op,x,y) in enumerate(c['gates'],k+2):
        if j in live:refs[j]=d.apply(op,get(x),get(y))
    outputs=[get(v) for v in c['outputs']]
    return d,dict(schema='ifs.cig024.algebra.v1',key=nav.key,initial=str(initial),cutoff=D,base=list(base),refs=[[i,v] for i,v in sorted(refs.items())],outputs=outputs,prefix=prefix,nodes=[[j,list(z)] for j,z in d.nodes],cells=cells,work=d.work)

class Language:
    """Producer-side temporal algebra, including exact transient prefixes."""
    def __init__(self,d,receipt):
        self.d=d;self.D=receipt['cutoff'];self.roots=list(receipt['outputs']);self.prefix=[sum(row[i]<<t for t,row in enumerate(receipt['prefix'])) for i in range(len(self.roots))];self.ops=[]
    def extend(self,op,x,y=None):
        d=self.d
        if type(x)is not int or not 0<=x<len(self.roots):raise ValueError('operand')
        a=self.roots[x];p=self.prefix[x];mask=(1<<self.D)-1
        if op=='shift':
            contract_time(y)
            r=d.shift(a,y);z=sum(((p>>(t+y)&1) if t+y<self.D else d.value(a,t+y))<<t for t in range(self.D))
        elif op=='not':
            if y is not None:raise ValueError('not operand')
            r=d.apply(op,a);z=p^mask
        else:
            if op not in ('and','or','xor') or type(y)is not int or not 0<=y<len(self.roots):raise ValueError('operation')
            r=d.apply(op,a,self.roots[y]);q=self.prefix[y];z=p&q if op=='and' else p|q if op=='or' else p^q
        self.ops.append([op,x,y,r,str(z)]);self.roots.append(r);self.prefix.append(z);return len(self.roots)-1
    def count(self,i):return self.d.count(self.roots[i])
    def membership(self,i,t):
        contract_time(t);return self.prefix[i]>>t&1 if t<self.D else self.d.value(self.roots[i],t)
    def next(self,i,start,max_states=100_000):
        contract_time(start)
        for t in range(start,self.D):
            if self.membership(i,t):return dict(status='FOUND',time=str(t),trace=[])
        t,trace,status=self.d.next(self.roots[i],max(start,self.D),max_states)
        if t is not None and t.bit_length()>4096:return dict(status='UNKNOWN',time=None,trace=trace)
        return dict(status=status,time=None if t is None else str(t),trace=trace)
    def interval(self,i,lo,hi,max_states=100_000):
        """Count in [lo,hi), using complete-period arithmetic and residual CRT cover."""
        contract_time(lo);contract_time(hi)
        if hi<lo or type(max_states)is not int or max_states<1:raise ValueError('interval contract')
        total=sum(self.prefix[i]>>t&1 for t in range(lo,min(hi,self.D)))
        lo=max(lo,self.D);P=prod(self.d.base)
        if hi<=lo:return dict(status='EXACT',count=str(total),states=0)
        q,rem=divmod(hi-lo,P);total+=q*self.count(i);hi=lo+rem
        stack=[(self.roots[i],0,1)] if rem else [];states=0
        while stack:
            v,r,m=stack.pop();states+=1
            if states>max_states:return dict(status='UNKNOWN',count=None,states=states)
            t=lo+(r-lo)%m
            if not v or t>=hi:continue
            if v==1:total+=1+(hi-1-t)//m;continue
            j,kids=self.d.nodes[v-2];b=self.d.base[j]
            for x,z in enumerate(kids):
                if z:stack.append((z,merge(r,m,x,b),m*b))
        return dict(status='EXACT',count=str(total),states=states)
    def export(self):return dict(nodes=[[j,list(z)] for j,z in self.d.nodes],ops=[row[:] for row in self.ops])
