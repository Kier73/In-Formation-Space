"""PGI-003: transport signed rank knowledge through a learned pullback.
The seed is a source-bound exact arithmetic expression. The receiver admits
it once and reconstructs derived expressions from compact recipes.
"""
from collections import Counter
from math import gcd
from ground_network import View,integer,Work,Exhausted,digest
from temporal_rank import expand
from verify_skill_language import verify_pullback


def seed_packet(source,*,max_work=2_000_000):
    if type(source) is not View:raise ValueError('view')
    terms,work=expand(source,source.root,max_work)
    return {'schema':'pgi.rank-family.seed.v1','source':source.key,'terms':terms,'work':work}


def recipe(source,target,form):
    a,b,c=form;integer(a,1);integer(b,0)
    if type(c) is not int or c not in (0,1):raise ValueError('polarity')
    return {'schema':'pgi.rank-family.recipe.v1','source':source.key,'target':target.key,'form':[str(a),str(b),c]}


def transport(terms,form,*,max_work=2_000_000):
    a,b,c=form;integer(a,1);integer(b,0)
    if type(c) is not int or c not in (0,1):raise ValueError('polarity')
    w=Work(max_work);out=Counter({(0,1):1}) if c else Counter()
    for r,m,n in terms:
        w.charge();d=gcd(a,m)
        if (r-b)%d:continue
        q=m//d;x=((r-b)//d*pow(a//d,-1,q))%q if q>1 else 0
        out[x,q]+=(-n if c else n)
    return tuple((r,m,n) for (r,m),n in sorted(out.items()) if n),w.used


class TransportedRank:
    def __init__(self,source,target,packet,form,*,max_work=2_000_000):
        if packet['source']!=source.key or target.period!=source.period//gcd(source.period,form[0]):raise ValueError('period/source')
        ok,checked=verify_pullback(source,target,form,max_work=max_work)
        if not ok:raise ValueError('relation')
        self.target=target;self.recipe=recipe(source,target,form)
        self.terms,self.work=transport(packet['terms'],form,max_work=max_work);self.relation_work=checked
        self.D=target.cutoff;self.P=target.period;self.N=target.total;self.before=target.prefix.bit_count();self.anchor=self.raw(self.D)
        if self.raw(self.D+self.P)-self.anchor!=self.N:raise ValueError('count')
        self.lower=self.upper=0
        for r,m,c in self.terms:
            if self.P%m:raise ValueError('period')
            a=(self.D-1-r)%m;u=c*a*(self.P//m);v=c*(a-m+1)*(self.P//m)
            self.lower+=min(u,v);self.upper+=max(u,v)
    def raw(self,t):return sum(c*((t-1-r)//m+1) for r,m,c in self.terms)
    def select(self,k,*,max_probes=4096):
        integer(k,1);integer(max_probes,0)
        if k<=self.before:
            t=next(t for t in range(self.D) if (self.target.prefix&((1<<(t+1))-1)).bit_count()>=k)
            return {'status':'FOUND','time':str(t),'probes':0}
        if not self.N:return {'status':'UNREACHABLE','time':None,'probes':0}
        q,j=divmod(k-self.before-1,self.N)
        lo=max(self.D,self.D-((self.upper-self.P*j)//self.N));hi=min(self.D+self.P-1,self.D+(self.P*j-self.lower)//self.N)
        if lo>hi:raise ValueError('discrepancy')
        probes=0
        while lo<hi:
            if probes>=max_probes:return {'status':'UNKNOWN','time':None,'probes':probes}
            mid=(lo+hi)//2;probes+=1
            if self.raw(mid+1)-self.anchor>j:hi=mid
            else:lo=mid+1
        t=lo+q*self.P
        if (t+1).bit_length()>4096:return {'status':'UNKNOWN','time':None,'probes':probes}
        return {'status':'FOUND','time':str(t),'probes':probes}
