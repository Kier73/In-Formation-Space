"""Independent source rank admission and affine-recipe reconstruction.
Uses the admitted View rather than a producer-supplied target expansion.
"""
from collections import Counter
from math import gcd
from ground_network import View,Work
from verify_skill_language import verify_pullback,valid
from verify_family_language import readform,readint


def source_terms(v,max_work=4_000_000):
    # Independently reconstruct CIG-025 default-child identity on live nodes.
    w=Work(max_work);seen=set();todo=[v.root]
    while todo:
        x=todo.pop();w.charge()
        if x<2 or x in seen:continue
        seen.add(x);row=v.nodes[x-2][1];w.charge(len(row));todo.extend(row)
    tab={0:Counter(),1:Counter({(0,1):1})};cells=0
    for x in sorted(seen):
        j,ch=v.nodes[x-2];m=v.base[j];freq=Counter(ch);default=max(dict.fromkeys(ch),key=freq.get);base=tab[default];out=base.copy()
        w.charge(m+len(base));cells+=m+len(base)
        for r,y in enumerate(ch):
            if y==default:continue
            w.charge(len(tab[y])+len(base));cells+=len(tab[y])+len(base)
            for terms,sgn in ((tab[y],1),(base,-1)):
                for (z,n),c in terms.items():
                    a=r+m*((z-r)*pow(m,-1,n)%n) if n>1 else r
                    out[a,m*n]+=sgn*c
        tab[x]=Counter({k:c for k,c in out.items() if c})
    return [[r,m,c] for (r,m),c in sorted(tab[v.root].items())],cells,w.used


def bezout(a,b):
    x,y=1,0
    while b:
        q,a,b=a//b,b,a%b;x,y=y,x-q*y
    return a,x


class RankSeedAdmission:
    def __init__(self,source,packet,*,max_work=4_000_000):
        if type(source) is not View or type(packet) is not dict or set(packet)!={'schema','source','terms','work'} or packet['schema']!='pgi.rank-family.seed.v1' or packet['source']!=source.key:raise ValueError('seed')
        expected,work,self.work=source_terms(source,max_work)
        if type(packet['terms']) is not list or any(type(row) is not list or len(row)!=3 or any(type(x) is not int for x in row) for row in packet['terms']) or packet['terms']!=expected or type(packet['work']) is not int or packet['work']!=work:raise ValueError('terms')
        self.source=source;self.terms=tuple(map(tuple,expected))
    def activate(self,target,recipe,*,max_work=2_000_000):
        if type(recipe) is not dict or set(recipe)!={'schema','source','target','form'} or recipe['schema']!='pgi.rank-family.recipe.v1' or recipe['source']!=self.source.key or recipe['target']!=target.key:raise ValueError('recipe')
        a,b,c=readform(recipe['form']);w=Work(max_work)
        if target.period!=self.source.period//gcd(self.source.period,a):raise ValueError('period')
        ok,checked=verify_pullback(self.source,target,(a,b,c),max_work=max_work)
        if not ok:raise ValueError('relation')
        out=Counter({(0,1):1}) if c else Counter()
        for r,m,n in self.terms:
            w.charge();d,x=bezout(a,m);rhs=r-b
            if rhs%d:continue
            q=m//d;z=(x*(rhs//d))%q
            if (a*z+b-r)%m:raise ValueError('congruence')
            out[z,q]+=n*(1-2*c)
        return CheckedTransport(target,tuple((r,m,n) for (r,m),n in sorted(out.items()) if n),w.used,checked)


class CheckedTransport:
    def __init__(self,v,terms,work,relation_work):
        self.view=v;self.terms=terms;self.work=work;self.relation_work=relation_work
        if any(v.period%m for r,m,c in terms) or sum(c*(v.period//m) for r,m,c in terms)!=v.total:raise ValueError('count')
    def rank(self,t):
        if not valid(t):raise ValueError('time')
        v=self.view;total=(v.prefix&((1<<min(v.cutoff,t))-1)).bit_count()
        if t<=v.cutoff:return total
        q,s=divmod(t-v.cutoff,v.period);lo=v.cutoff;hi=lo+s
        return total+q*v.total+sum(c*((hi-1-r)//m-(lo-1-r)//m) for r,m,c in self.terms)
    def verify(self,k,r):
        try:
            if not valid(k,1) or type(r) is not dict or set(r)!={'status','time','probes'} or not valid(r['probes']) or r['probes']>self.view.period.bit_length():return False
            if r['status']=='UNREACHABLE':return r['time'] is None and self.view.total==0 and k>self.view.prefix.bit_count()
            if r['status']!='FOUND':return False
            t=readint(r['time']);return self.rank(t)==k-1 and self.rank(t+1)==k
        except (ValueError,TypeError,KeyError):return False
