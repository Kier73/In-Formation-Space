"""Independent rank checker: replay default-child identity bottom-up on root cone.
Admission must be the receiver-owned, source-qualified CIG-024 object.
"""
from collections import Counter
from math import prod
from verify_temporal_algebra import Admission

class CheckedRank:
    def __init__(self,a,packet,max_work=4_000_000):
        if type(a) is not Admission or type(max_work) is not int or max_work<1:raise ValueError('admission')
        if type(packet) is not dict or set(packet)!={'index','root','terms','work'}:raise ValueError('packet')
        i=packet['index'];v=packet['root'];d=a.d
        if type(i) is not int or not 0<=i<len(a.roots) or type(v) is not int or v!=a.roots[i]:raise ValueError('root')
        live={v};todo=[v]
        while todo:
            z=todo.pop()
            if z>=2:
                for u in d.nodes[z-2][1]:
                    if u not in live:live.add(u);todo.append(u)
        tab={0:Counter(),1:Counter({(0,1):1})};work=0
        for z in sorted(live-{0,1}):
            j,kids=d.nodes[z-2];b=d.base[j];freq=Counter(kids);default=max(dict.fromkeys(kids),key=freq.get)
            old=tab[default];out=old.copy();work+=len(old)+len(kids)
            for digit,u in enumerate(kids):
                if u==default:continue
                new=tab[u];work+=len(new)+len(old)
                if work>max_work:raise ValueError('work')
                # Independently distribute positive and negative terms, using
                # the symmetric CRT formula rather than producer difference join.
                for source,sign in ((new,1),(old,-1)):
                    for (r,m),c in source.items():
                        x=(digit+b*((r-digit)*pow(b,-1,m)%m))%(b*m) if m>1 else digit
                        out[x,b*m]+=sign*c
            if work>max_work:raise ValueError('work')
            tab[z]=Counter({key:c for key,c in out.items() if c})
        expected=[[r,m,c] for (r,m),c in sorted(tab[v].items())]
        terms=packet['terms']
        if type(terms) is not list or any(type(row) is not list or len(row)!=3 or any(type(x) is not int for x in row) for row in terms) or terms!=expected or type(packet['work']) is not int or packet['work']!=work:raise ValueError('expansion')
        self.terms=tuple(map(tuple,expected));self.D=a.D;self.prefix=a.prefix[i];self.before=self.prefix.bit_count();self.P=prod(d.base);self.total=a.count(i);self.d=d;self.root=v
        if sum(c*(self.P//m) for r,m,c in self.terms)!=self.total:raise ValueError('count')
    def rank(self,t):
        if type(t) is not int or t<0 or t.bit_length()>4096:raise ValueError('time')
        p=(self.prefix&((1<<min(t,self.D))-1)).bit_count()
        if t<=self.D:return p
        q,s=divmod(t-self.D,self.P);hi=self.D+s
        return p+q*self.total+sum(c*((hi-1-r)//m-(self.D-1-r)//m) for r,m,c in self.terms)
    def verify_select(self,k,r):
        try:
            if type(k) is not int or k<1 or k.bit_length()>4096 or set(r)!={'status','time','probes'} or type(r['probes']) is not int or not 0<=r['probes']<=self.P.bit_length():return False
            if r['status']=='UNREACHABLE':return r['time'] is None and self.total==0 and k>self.before
            if r['status']!='FOUND' or type(r['time']) is not str:return False
            t=int(r['time'])
            return str(t)==r['time'] and self.rank(t)==k-1 and self.rank(t+1)==k
        except (TypeError,ValueError,OverflowError):return False
