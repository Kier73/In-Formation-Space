"""CIG-032A: bounded activation of source-admitted temporal memory seeds.
Discovery is advisory; every relation and transferred fact needs receiver admission.
No reliance on target construction history or full-period enumeration.
"""
from fractions import Fraction
from math import prod,lcm
from compositional_rank import make_link
from temporal_algebra import Budget

class Work:
    def __init__(self,limit):
        if type(limit) is not int or limit<1:raise ValueError('budget')
        self.limit=limit;self.used=0
    def charge(self,n=1):
        self.used+=n
        if self.used>self.limit:raise Budget('seed discovery')

def solve(rows,n,work):
    """Exact rational elimination; free coefficients set to zero."""
    a=[list(map(Fraction,row)) for row in rows];p=[];i=0
    for j in range(n):
        k=next((k for k in range(i,len(a)) if a[k][j]),None)
        work.charge(len(a))
        if k is None:continue
        a[i],a[k]=a[k],a[i];v=a[i][j];a[i]=[x/v for x in a[i]]
        for k in range(len(a)):
            if k!=i and a[k][j]:
                v=a[k][j];a[k]=[x-v*y for x,y in zip(a[k],a[i])];work.charge(n+1)
        p.append(j);i+=1
    if any(not any(row[:n]) and row[n] for row in a):return None
    x=[Fraction(0)]*n
    for i,j in enumerate(p):x[j]=a[i][n]
    return x

def row_at(l,ids,t):
    return (1,)+tuple(l.membership(i,t) for i in ids)

def counterexample(l,ids,coef,work):
    """Find a terminal pattern violating the candidate on the full qualified domain."""
    for t in range(l.D):
        work.charge(len(ids));r=row_at(l,ids,t)
        if sum(x*y for x,y in zip(coef,r[:-1]))!=r[-1]:return r
    d=l.d;todo=[tuple(l.roots[i] for i in ids)];seen=set()
    while todo:
        s=todo.pop()
        if s in seen:continue
        seen.add(s);work.charge();j=min(map(d.level,s))
        if j==len(d.base):
            r=(1,)+s
            if sum(x*y for x,y in zip(coef,r[:-1]))!=r[-1]:return r
        else:
            work.charge(d.base[j]*len(s));todo.extend(tuple(d.at(v,j,r) for v in s) for r in range(d.base[j]))
    return None

def span_relation(l,members,target,work):
    ids=tuple(members)+(target,);P=prod(l.d.base)
    # Global hot observation: only a proposal, never an admission.
    phases=sorted({0,l.D,*[l.D+P*j//7 for j in range(7)]})
    rows=[]
    for t in phases:
        work.charge(len(ids));r=row_at(l,ids,t)
        if r not in rows:rows.append(r)
    for attempt in range(len(members)+3):
        c=solve(rows,len(members)+1,work)
        if c is None:return None,len(rows)
        r=counterexample(l,ids,c,work)
        if r is None:
            den=lcm(*(x.denominator for x in c));v=[int(x*den) for x in c]
            if den>16 or any(abs(x)>32 for x in v):return None,len(rows)
            return dict(kind='span',target=target,den=den,constant=v[0],terms=sorted([[i,w] for i,w in zip(members,v[1:]) if w])),len(rows)
        if r in rows:raise AssertionError('repeated counterexample')
        rows.append(r)
    return None,len(rows)

def shifted(l,i,j,delta,work):
    d=l.d
    for t in range(l.D):
        work.charge()
        if l.membership(i,t+delta)!=l.membership(j,t):return False
    todo=[(l.roots[i],l.roots[j])];seen=set()
    while todo:
        x,y=todo.pop()
        if (x,y) in seen:continue
        seen.add((x,y));work.charge();k=min(d.level(x),d.level(y))
        if k==len(d.base):
            if x!=y:return False
        else:
            work.charge(2*d.base[k]);todo.extend((d.at(x,k,(r+delta)%d.base[k]),d.at(y,k,r)) for r in range(d.base[k]))
    return True

def joint_count(l,i,j,work):
    d=l.d;tail=[prod(d.base[k:]) for k in range(len(d.base)+1)];memo={}
    def rec(x,y):
        key=(x,y)
        if key in memo:return memo[key]
        work.charge();k=min(d.level(x),d.level(y))
        if k==len(d.base):z=x*y
        else:
            work.charge(2*d.base[k]);z=0
            for r in range(d.base[k]):
                a,b=d.at(x,k,r),d.at(y,k,r);h=min(d.level(a),d.level(b));z+=rec(a,b)*tail[k+1]//tail[h]
        memo[key]=z;return z
    x,y=l.roots[i],l.roots[j];return rec(x,y)*tail[0]//tail[min(d.level(x),d.level(y))]

class Seed:
    """A local capability: a set of already admitted intention books in one Ground.
    Composition is union, never importing facts from an unrelated source.
    """
    def __init__(self,m,members):
        self.m=m;members=tuple(members)
        if any(type(i) is not int for i in members):raise ValueError('members')
        self.members=tuple(sorted(set(members)))
        if not self.members or len(self.members)>12 or any(type(i) is not int or not 0<=i<len(m.lang.roots) for i in self.members):raise ValueError('members')
        if any(i not in m.books for i in self.members):raise ValueError('unretained seed')
    def combine(self,other):
        if other.m is not self.m:raise ValueError('different Ground')
        return Seed(self.m,self.members+other.members)
    def discover(self,target,*,deltas=range(1,9),max_work=500000,max_difference=16,phases=()):
        l=self.m.lang;P=self.m.P;w=Work(max_work)
        if type(target) is not int or not 0<=target<len(l.roots):raise ValueError('target')
        ds=tuple(deltas)
        if len(ds)>64 or any(type(s) is not int or s<1 or s.bit_length()>4096 for s in ds):raise ValueError('shifts')
        phases=tuple(phases)
        if len(phases)>128 or any(type(p) is not int or not 0<=p<=P for p in phases) or type(max_difference) is not int or max_difference<0:raise ValueError('demand')
        def priority(i):
            anchors=self.m.book(i).anchors
            return (sum(p not in anchors and i not in self.m.ranks for p in phases),i in self.m.ranks,-len(anchors),i)
        members=tuple(sorted((i for i in self.members if i!=target),key=priority));rows=0;attempts=0
        if not members:return dict(status='UNKNOWN',work=0,rows=0,attempts=0,relation=None)
        try:
            # Cheap exact equality/complement; canonical nodes from same archive.
            for i in members:
                w.charge();
                if l.roots[i]==l.roots[target] and l.prefix[i]==l.prefix[target]:
                    return dict(status='FOUND',work=w.used,rows=0,attempts=0,relation=dict(kind='span',target=target,den=1,constant=0,terms=[[i,1]]))
            # Shift palette before residual discovery. Sample only to reject.
            N=self.m.count(target);samples=sorted({0,l.D,*[l.D+P*j//13 for j in range(13)]})
            for delta in ds:
                if (max(samples)+delta).bit_length()>4096:continue
                for i in members:
                    w.charge()
                    if self.m.count(i)!=N:continue
                    w.charge(len(samples))
                    if any(l.membership(i,t+delta)!=l.membership(target,t) for t in samples):continue
                    attempts+=1
                    if shifted(l,i,target,delta,w):return dict(status='FOUND',work=w.used,rows=0,attempts=attempts,relation=dict(kind='shift',base=i,target=target,delta=delta))
            z,rows=span_relation(l,members,target,w)
            if z is not None:return dict(status='FOUND',work=w.used,rows=rows,attempts=attempts,relation=z)
            # The disagreement volume selects a local residual seed, not proof of a rank.
            options=[]
            for i in members:
                diff=self.m.count(i)+N-2*joint_count(l,i,target,w)
                options += [(diff,i,False),(P-diff,i,True)]
            diff,i,flip=min(options,key=lambda z:(z[0],priority(z[1]),z[2]))
            if diff<=max_difference:
                return dict(status='FOUND',work=w.used,rows=rows,attempts=attempts,relation=dict(kind='residual',base=i,target=target,flip=flip,disagreement=str(diff)))
        except Budget:pass
        return dict(status='UNKNOWN',work=min(w.used,w.limit),rows=rows,attempts=attempts,relation=None)
    def activate(self,proposal):
        """Construct residual operations only after discovery; no receiver mutation."""
        if proposal['status']!='FOUND':return None
        z=proposal['relation']
        if z['kind']=='residual':
            q=make_link(self.m.lang,z['base'],z['target'],z['flip']);return dict(kind='residual',link=q,disagreement=z['disagreement'])
        return dict(z)
    def transfer_span(self,z,p):
        L,U=self.m.bounds(z['target'],p);lo=hi=z['constant']*p
        for i,c in z['terms']:
            a,b=self.m.bounds(i,p);lo+=min(c*a,c*b);hi+=max(c*a,c*b)
        d=z['den'];L=max(L,-(-lo//d));U=min(U,hi//d)
        if L>U:raise ValueError('inconsistent span')
        return dict(phase=str(p),lower=str(L),upper=str(U),status='EXACT' if L==U else 'UNKNOWN')
    def commit_span(self,z,r):
        if r['status']=='EXACT':self.m.book(z['target'])._anchors[int(r['phase'])]=int(r['lower'])
    def descriptor(self):
        """Portable description, not a portable proof: receiver must hold admission."""
        from hashlib import sha256
        from json import dumps
        l=self.m.lang
        memo={0:sha256(b'false').hexdigest(),1:sha256(b'true').hexdigest()}
        def semantic(i):
            if i not in memo:
                j,kids=l.d.nodes[i-2];memo[i]=sha256(dumps([j,[semantic(v) for v in kids]],separators=(',',':')).encode()).hexdigest()
            return memo[i]
        body=dict(schema='ifs.cig032.seed.v1',base=list(l.d.base),cutoff=l.D,members=[dict(index=i,root=l.roots[i],semantic=semantic(l.roots[i]),prefix=str(l.prefix[i]),anchors=[[str(p),str(r)] for p,r in sorted(self.m.book(i).anchors.items())]) for i in self.members])
        return dict(body,identity=sha256(dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    def capsule(self,proofs):
        """Proof-bearing cold activation. Proofs must come from an earlier
        exact rank acquisition (or be explicitly reconstructed and charged).
        A compact descriptor alone cannot seed a fresh receiver.
        """
        from copy import deepcopy
        if set(proofs)!=set(self.members):raise ValueError('proof coverage')
        return dict(schema='ifs.cig032.capsule.v1',descriptor=self.descriptor(),proofs=[[i,deepcopy(proofs[i])] for i in self.members])
    def recipe(self):
        """Compact cold reconstruction request; the receiver pays for proof work."""
        return dict(schema='ifs.cig032.recipe.v1',descriptor=self.descriptor())
