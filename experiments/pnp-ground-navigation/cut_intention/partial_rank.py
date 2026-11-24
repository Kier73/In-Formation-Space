"""CIG-028B: bounded rank comparisons on a qualified temporal DAG.
No complete signed expansion is required. Frontier terms are signed conditional
functions on CRT cylinders; each split is an exact Boolean identity.
"""
from collections import Counter
from heapq import heappush, heappop
from math import prod
from temporal_ground import contract_time
from temporal_rank import expand
from temporal_algebra import Budget


def ceildiv(a,b): return -((-a)//b)

def copies(r,m,lo,hi): return (hi-1-r)//m-(lo-1-r)//m

class PartialRank:
    def __init__(self,lang,i,*,suffix_mass=32,scan=64):
        if type(i) is not int or not 0<=i<len(lang.roots):raise ValueError('index')
        if any(type(v) is not int or not 0<=v<=4096 for v in (suffix_mass,scan)):raise ValueError('policy')
        self.d=lang.d;self.i=i;self.root=lang.roots[i];self.D=lang.D;self.prefix=lang.prefix[i];self.before=self.prefix.bit_count();self.P=prod(self.d.base);self.total=lang.count(i)
        self.suffix_mass=suffix_mass;self.scan=scan;self.tail=[prod(self.d.base[j:]) for j in range(len(self.d.base)+1)]
        self.count=[0,1];self.mass=[0,1];self.default={};self.cache={};self.compiled_work=0
        for v,(j,kids) in enumerate(self.d.nodes,2):
            default=Counter(kids).most_common(1)[0][0];self.default[v]=default
            self.count.append(sum(self.count[u]*self.tail[j+1]//self.tail[self.d.level(u)] for u in kids))
            self.mass.append(self.mass[default]+sum(self.mass[u]+self.mass[default] for u in kids if u!=default))
        assert self.count[self.root]*self.P//self.tail[self.d.level(self.root)]==self.total
    def _bounds(self,v,r,m,lo,hi):
        n=copies(r,m,lo,hi)
        if v<2:return v*n,v*n
        Q=self.tail[self.d.level(v)];N=self.count[v];q,s=divmod(n,Q)
        # Each congruence term in the unexpanded signed identity has rounding
        # error of magnitude <1 on this coprime cylinder. Triangle inequality.
        E=self.mass[v]
        low=max(q*N+max(0,s-(Q-N)),ceildiv(n*N,Q)-E)
        high=min(q*N+min(s,N),n*N//Q+E)
        return low,high
    def _exact(self,v,r,m,lo,hi,method):
        if method=='scan':
            return sum(self.d.value(v,t) for t in range(lo+(r-lo)%m,hi,m)),0
        if v not in self.cache:
            terms,w=expand(self.d,v,max_work=2_000_000);self.cache[v]=terms;self.compiled_work+=w
        terms=self.cache[v];n=0
        for a,b,c in terms:
            x=r+m*((a-r)*pow(m,-1,b)%b) if b>1 else r
            n+=c*copies(x,m*b,lo,hi)
        return n,len(terms)
    def compare(self,t,k=None,*,budget=20000):
        contract_time(t)
        if k is not None and (type(k) is not int or k<0 or k.bit_length()>4096):raise ValueError('threshold')
        if type(budget) is not int or not 0<=budget<=1_000_000:raise ValueError('budget')
        trace=[];work=0;terms=0;scans=0
        if t<=self.D: offset=(self.prefix&((1<<t)-1)).bit_count();lo=hi=self.D;sign=1
        else:
            q,s=divmod(t-self.D,self.P);offset=self.before+q*self.total;lo=self.D;hi=lo+s;sign=1
            if s>self.P-s:lo=hi;hi=self.D+self.P;offset+=self.total;sign=-1
        lower=upper=offset;states=[];queue=[]
        def add(v,r,m,c):
            nonlocal lower,upper
            a,b=self._bounds(v,r,m,lo,hi);a,b=sorted((c*a,c*b));lower+=a;upper+=b
            idx=len(states);states.append((v,r,m,c,a,b));
            if a!=b:heappush(queue,(-(b-a),idx))
        add(self.root,0,1,sign);L=max(0,lower);U=min(t,upper)
        while True:
            if L==U or (k is not None and (U<k or L>=k)) or not queue:break
            _,idx=heappop(queue);v,r,m,c,a,b=states[idx];n=copies(r,m,lo,hi)
            if n<=self.scan:method='scan';charge=n
            elif self.suffix_mass and self.mass[v]<=self.suffix_mass:method='signed';charge=self.mass[v]
            else:
                j,kids=self.d.nodes[v-2];default=self.default[v];width=self.d.base[j]
                # Choose cheap exact disjoint decomposition or signed default identity.
                nonzero=sum(u!=0 for u in kids);exceptions=sum(u!=default for u in kids)
                method='split' if nonzero<=1+2*exceptions else 'default';charge=width+ (nonzero if method=='split' else 1+2*exceptions)
            if work+charge>budget:break
            work+=charge;trace.append([idx,method]);lower-=a;upper-=b
            if method in ('scan','signed'):
                z,e=self._exact(v,r,m,lo,hi,method);lower+=c*z;upper+=c*z;terms+=e;scans+=n if method=='scan' else 0
            else:
                if method=='default':add(default,r,m,c)
                for digit,u in enumerate(kids):
                    if method=='default' and u==default:continue
                    x=r+m*((digit-r)*pow(m,-1,width)%width)
                    if u:add(u,x,m*width,c)
                    if method=='default' and default:add(default,x,m*width,-c)
            L=max(L,lower);U=min(U,upper)
            if L>U:raise AssertionError('invalid refinement')
        status='EXACT' if L==U else 'BELOW' if k is not None and U<k else 'AT_LEAST' if k is not None and L>=k else 'UNKNOWN'
        return dict(index=self.i,root=self.root,time=str(t),threshold=None if k is None else str(k),policy=[self.suffix_mass,self.scan],trace=trace,lower=str(L),upper=str(U),status=status,work=work,terms=terms,scans=scans)
    def select(self,k,*,budget=20000):
        if type(k) is not int or k<1 or k.bit_length()>4096:raise ValueError('ordinal')
        probes=work=0
        if k<=self.before:lo=0;hi=self.D-1
        elif not self.total:return dict(status='UNREACHABLE',time=None,proofs=[],probes=0,work=0)
        else:
            q,j=divmod(k-self.before-1,self.total);anchor=self.D+q*self.P
            # Error bound is derived from the unexpanded signed DAG, not its terms.
            E=self.mass[self.root];lo=anchor+max(0,ceildiv((j-E)*self.P,self.total));hi=anchor+min(self.P-1,(j+E)*self.P//self.total)
            # Try a cheap endpoint-relative obligation before navigating the
            # potentially wide global discrepancy interval. The other endpoint
            # is already exact from full-period cardinality.
            span=min(self.P,self.scan)
            if span and j<span:
                edge=anchor+span
                if edge.bit_length()<=4096:
                    z=self.compare(edge,k,budget=budget);probes+=1;work+=z['work']
                    if int(z['lower'])>=k:hi=min(hi,edge-1)
            elif span and self.total-j<=span:
                edge=anchor+self.P-span
                if edge.bit_length()<=4096:
                    z=self.compare(edge,k,budget=budget);probes+=1;work+=z['work']
                    if int(z['upper'])<k:lo=max(lo,edge)
        if hi.bit_length()>4096 or (hi+1).bit_length()>4096:return dict(status='UNKNOWN',time=None,proofs=[],probes=0,work=0)
        while lo<hi:
            mid=(lo+hi)//2;r=self.compare(mid+1,k,budget=budget);probes+=1;work+=r['work']
            if int(r['upper'])<k:lo=mid+1
            elif int(r['lower'])>=k:hi=mid
            else:return dict(status='UNKNOWN',time=None,proofs=[],probes=probes,work=work)
        a=self.compare(lo,k,budget=budget);b=self.compare(lo+1,k,budget=budget);work+=a['work']+b['work']
        if int(a['upper'])<k<=int(b['lower']):return dict(status='FOUND',time=str(lo),proofs=[a,b],probes=probes,work=work)
        return dict(status='UNKNOWN',time=None,proofs=[],probes=probes,work=work)
