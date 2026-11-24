"""Independent replay of a signed residual-cover certificate on CIG-024 admission."""
from math import prod
from collections import Counter
from verify_temporal_algebra import Admission

class CheckedPartial:
    def __init__(self,a):
        if type(a) is not Admission:raise ValueError('receiver admission')
        self.a=a;self.d=a.d;self.P=prod(a.d.base);self.D=a.D
        self.suffix=[prod(self.d.base[j:]) for j in range(len(self.d.base)+1)]
        self.N=[0,1];self.E=[0,1];self.defaults={};self.tables={0:{},1:{(0,1):1}}
        for v,(j,children) in enumerate(self.d.nodes,2):
            freq=Counter(children);h=max(dict.fromkeys(children),key=freq.get);self.defaults[v]=h
            self.N.append(sum(self.N[u]*(self.suffix[j+1]//self.suffix[self.d.level(u)]) for u in children))
            self.E.append((1+len(children)-freq[h])*self.E[h]+sum(self.E[u] for u in children if u!=h))
    def table(self,v):
        if v not in self.tables:
            j,kids=self.d.nodes[v-2];b=self.d.base[j];h=self.defaults[v];old=self.table(h);out=Counter(old)
            for a,u in enumerate(kids):
                if u==h:continue
                for terms,sign in ((self.table(u),1),(old,-1)):
                    for (r,m),c in terms.items():
                        x=a+b*((r-a)*pow(b,-1,m)%m) if m>1 else a
                        out[x,m*b]+=sign*c
            self.tables[v]={key:c for key,c in out.items() if c}
        return self.tables[v]
    @staticmethod
    def hits(r,m,l,h):
        first=l+(r-l)%m
        return max(0,(h-first+m-1)//m)
    def join(self,r,m,a,b):return a+b*((r-a)*pow(b,-1,m)%m) if m>1 else a
    def verify(self,p,*,budget=20000):
        try:
            if type(p) is not dict or set(p)!={'index','root','time','threshold','policy','trace','lower','upper','status','work','terms','scans'}:return False
            if type(budget) is not int or not 0<=budget<=1_000_000:return False
            i=p['index'];v=p['root']
            if type(i) is not int or not 0<=i<len(self.a.roots) or type(v) is not int or v!=self.a.roots[i]:return False
            def nat(x):
                if type(x) is not str or len(x)>1234:raise ValueError('integer')
                y=int(x)
                if y<0 or y.bit_length()>4096 or str(y)!=x:raise ValueError('integer')
                return y
            t=nat(p['time']);k=None if p['threshold'] is None else nat(p['threshold']);policy=p['policy']
            if type(policy)is not list or len(policy)!=2 or any(type(x)is not int or not 0<=x<=4096 for x in policy):return False
            suffix_mass,scan=policy;trace=p['trace']
            if type(trace)is not list or len(trace)>budget:return False
            D=self.D;P=self.P;prefix=self.a.prefix[i];total=self.N[v]*(P//self.suffix[self.d.level(v)])
            offset=(prefix&((1<<min(t,D))-1)).bit_count();l=h=D;sign=1
            if t>D:
                q,s=divmod(t-D,P);offset+=q*total;h=D+s
                if 2*s>P:l,h=h,D+P;offset+=total;sign=-1
            states=[];active=set();lower=upper=offset;work=terms=scans=0
            def append(v,r,m,c):
                nonlocal lower,upper
                n=self.hits(r,m,l,h);Q=self.suffix[self.d.level(v)];N=self.N[v];full,rest=divmod(n,Q)
                a=full*N+max(0,rest-Q+N);b=full*N+min(rest,N)
                if v>=2:
                    err=self.E[v];a=max(a,(n*N+Q-1)//Q-err);b=min(b,n*N//Q+err)
                aa,bb=min(c*a,c*b),max(c*a,c*b);idx=len(states);states.append((v,r,m,c,aa,bb));lower+=aa;upper+=bb
                if aa<bb:active.add(idx)
            append(v,0,1,sign);L=max(0,lower);U=min(t,upper)
            for row in trace:
                if type(row)is not list or len(row)!=2 or type(row[0])is not int or row[0] not in active or L==U or (k is not None and (U<k or L>=k)):return False
                idx,method=row;active.remove(idx);v,r,m,c,aa,bb=states[idx];lower-=aa;upper-=bb;n=self.hits(r,m,l,h)
                if method=='scan':
                    if n>scan:return False
                    z=sum(self.d.value(v,l+(r-l)%m+m*j) for j in range(n));work+=n;scans+=n
                elif method=='signed':
                    if not suffix_mass or self.E[v]>suffix_mass:return False
                    tab=self.table(v);work+=self.E[v];terms+=len(tab)
                    z=sum(coef*self.hits(self.join(r,m,a,b) if b>1 else r,m*b,l,h) for (a,b),coef in tab.items())
                elif method in ('split','default'):
                    if v<2:return False
                    j,kids=self.d.nodes[v-2];b=self.d.base[j];default=self.defaults[v]
                    if method=='default':
                        work+=b+1+2*sum(u!=default for u in kids);append(default,r,m,c)
                    else:work+=b+sum(u!=0 for u in kids)
                    for digit,u in enumerate(kids):
                        if method=='default' and u==default:continue
                        rr=self.join(r,m,digit,b)
                        if u:append(u,rr,m*b,c)
                        if method=='default' and default:append(default,rr,m*b,-c)
                    z=None
                else:return False
                if z is not None:lower+=c*z;upper+=c*z
                if work>budget:return False
                L=max(L,lower);U=min(U,upper)
                if L>U:return False
            status='EXACT' if L==U else 'BELOW' if k is not None and U<k else 'AT_LEAST' if k is not None and L>=k else 'UNKNOWN'
            return all(type(p[x]) is int and p[x]==y for x,y in [('work',work),('terms',terms),('scans',scans)]) and nat(p['lower'])==L and nat(p['upper'])==U and p['status']==status
        except (ValueError,TypeError,KeyError,IndexError,OverflowError,AttributeError):return False
    def verify_select(self,i,k,result,*,budget=20000):
        try:
            if type(i)is not int or not 0<=i<len(self.a.roots) or type(k)is not int or not 1<=k or k.bit_length()>4096 or type(result)is not dict or set(result)!={'status','time','proofs','probes','work'}:return False
            if any(type(result[x])is not int or result[x]<0 for x in ('probes','work')):return False
            if result['status']=='UNREACHABLE':return result['time'] is None and result['proofs']==[] and self.a.count(i)==0 and k>self.a.prefix[i].bit_count()
            if result['status']!='FOUND' or type(result['time'])is not str or type(result['proofs'])is not list or len(result['proofs'])!=2:return False
            t=int(result['time']);a,b=result['proofs']
            return str(t)==result['time'] and a['index']==b['index']==i and a['time']==str(t) and b['time']==str(t+1) and a['threshold']==b['threshold']==str(k) and self.verify(a,budget=budget) and self.verify(b,budget=budget) and int(a['upper'])<k<=int(b['lower'])
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):return False
