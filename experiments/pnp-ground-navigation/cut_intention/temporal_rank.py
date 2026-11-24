"""CIG-025: signed congruence expansion of an admitted temporal diagram.
Terms encode exact indicator functions, not probabilities. Budgeted expansion.
"""
from collections import Counter
from math import prod
from temporal_algebra import Budget
from temporal_ground import contract_time


def expand(d, root, max_work=2_000_000):
    if type(max_work) is not int or max_work < 1: raise ValueError('budget')
    memo={0:{},1:{(0,1):1}}; work=0
    def charge(n):
        nonlocal work
        work+=n
        if work>max_work: raise Budget('signed expansion')
    def visit(v):
        if v in memo:return memo[v]
        j,kids=d.nodes[v-2]; b=d.base[j]; default=Counter(kids).most_common(1)[0][0]
        base=visit(default); out=base.copy();charge(len(base)+len(kids))
        for a,u in enumerate(kids):
            if u==default:continue
            diff=visit(u).copy();charge(len(diff)+len(base))
            for key,c in base.items():diff[key]=diff.get(key,0)-c
            for (r,m),c in diff.items():
                if c:
                    x=r+m*((a-r)*pow(m,-1,b)%b);key=(x,m*b)
                    out[key]=out.get(key,0)+c
        memo[v]={k:c for k,c in out.items() if c};return memo[v]
    terms=visit(root)
    return [[r,m,c] for (r,m),c in sorted(terms.items())],work

class Rank:
    def __init__(self,lang,i,max_work=2_000_000):
        if type(i) is not int or not 0<=i<len(lang.roots):raise ValueError('root')
        self.D=lang.D;self.prefix=lang.prefix[i];self.P=prod(lang.d.base);self.i=i;self.root=lang.roots[i]
        self.terms,self.work=expand(lang.d,self.root,max_work)
        self.total=lang.count(i);self.before=self.prefix.bit_count()
        self.anchor=self.raw(self.D)
        # Exact discrepancy bounds: P*R_tail(s) - s*N is a sum of
        # integer-scaled per-congruence floor errors.
        self.lower=self.upper=0
        for r,m,c in self.terms:
            a=(self.D-1-r)%m;u=c*a*(self.P//m);v=c*(a-m+1)*(self.P//m)
            self.lower+=min(u,v);self.upper+=max(u,v)
        if self.raw(self.D+self.P)-self.anchor!=self.total:raise AssertionError('period count')
    def packet(self):return dict(index=self.i,root=self.root,terms=self.terms,work=self.work)
    def raw(self,t):return sum(c*((t-1-r)//m+1) for r,m,c in self.terms)
    def rank(self,t):
        contract_time(t)
        if t<=self.D:return (self.prefix&((1<<t)-1)).bit_count()
        q,s=divmod(t-self.D,self.P)
        return self.before+q*self.total+self.raw(self.D+s)-self.anchor
    def select(self,k,*,bounded=True):
        if type(k) is not int or k<1 or k.bit_length()>4096:raise ValueError('ordinal')
        if k<=self.before:
            return dict(status='FOUND',time=str(next(t for t in range(self.D) if self.rank(t+1)>=k)),probes=0)
        if not self.total:return dict(status='UNREACHABLE',time=None,probes=0)
        q,j=divmod(k-self.before-1,self.total);lo=self.D;hi=self.D+self.P-1;probes=0
        if bounded:
            lo=max(lo,self.D-((self.upper-self.P*j)//self.total))
            hi=min(hi,self.D+(self.P*j-self.lower)//self.total)
            if lo>hi:raise AssertionError('rank discrepancy')
        while lo<hi:
            mid=(lo+hi)//2;probes+=1
            if self.raw(mid+1)-self.anchor>j:hi=mid
            else:lo=mid+1
        t=lo+q*self.P
        if (t+1).bit_length()>4096:return dict(status='UNKNOWN',time=None,probes=probes)
        return dict(status='FOUND',time=str(t),probes=probes)
