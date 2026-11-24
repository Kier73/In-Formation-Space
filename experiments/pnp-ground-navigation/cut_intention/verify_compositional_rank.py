"""Independent receiver. Links checked against admitted temporal set identities.
No producer imports. Caller owns the local admission and verifier objects.
"""
from math import prod
from copy import deepcopy
from verify_rank_anchors import nat
from verify_anchor_portfolio import PortfolioReceiver
from verify_temporal_algebra import Admission

class MemoryReceiver:
    def __init__(self,a):
        if type(a) is not Admission:raise ValueError('admission')
        self.a=a;self.P=prod(a.d.base);self.books={};self.links=[];self.counts={}
    def book(self,i):
        if i not in self.books:self.books[i]=PortfolioReceiver(self.a,i)
        return self.books[i]
    def count(self,i):
        if i not in self.counts:self.counts[i]=self.a.count(i)
        return self.counts[i]
    def admit_fact(self,i,p,z):
        try:
            if type(i) is not int or not 0<=i<len(self.a.roots) or type(p) is not int or not 0<=p<=self.P or type(z) is not dict or set(z)!={'index','phase','rank'} or type(z['index']) is not int or z['index']!=i or nat(z['phase'])!=p:return False
            b=self.book(i);r=nat(z['rank'])
            if b.exact is None or b.exact.rank(b.D+p)-b.before!=r:return False
            b._put(p,r);return True
        except (TypeError,ValueError,IndexError,KeyError,OverflowError):return False
    def admit_link(self,z):
        try:
            if type(z) is not dict or set(z)!={'base','target','flip','view','opposite','nt','plus','minus'} or type(z['flip']) is not bool:return False
            if any(type(z[k]) is not int or not 0<=z[k]<len(self.a.roots) for k in z if k!='flip'):return False
            a=self.a;d=a.d;r=a.roots;p=a.prefix;mask=(1<<a.D)-1
            b,t,v,o,n,x,y=(z[k] for k in ('base','target','view','opposite','nt','plus','minus'))
            def neg(i,j):
                d.relation('not',r[i],0,r[j]);return p[j]==(mask^p[i])
            def intersect(i,j,k):
                d.relation('and',r[i],r[j],r[k]);return p[k]==p[i]&p[j]
            if not (neg(b,v) if z['flip'] else b==v):return False
            if not (neg(v,o) and neg(t,n) and intersect(t,o,x) and intersect(v,n,y)):return False
            if self.count(t)!=self.count(v)+self.count(x)-self.count(y):return False
            self.links.append(dict(z));return True
        except (TypeError,ValueError,IndexError,KeyError,OverflowError):return False
    def admit_shift(self,z):
        try:
            if type(z) is not dict or set(z)!={'kind','base','target','delta'} or z['kind']!='shift':return False
            b,t,delta=z['base'],z['target'],z['delta'];a=self.a;d=a.d
            if any(type(i) is not int or not 0<=i<len(a.roots) for i in (b,t)) or type(delta) is not int or delta<0 or delta.bit_length()>4096:return False
            d.relation('shift',a.roots[b],0,a.roots[t],delta)
            prefix=sum(((a.prefix[b]>>(p+delta)&1) if p+delta<a.D else d.value(a.roots[b],p+delta))<<p for p in range(a.D))
            if a.prefix[t]!=prefix or self.count(t)!=self.count(b):return False
            self.links.append(dict(z));return True
        except (ValueError,TypeError,IndexError,KeyError,OverflowError):return False
    def admit_linear(self,z,*,max_work=200000):
        """Check pointwise integer identity over the synchronized diagram product.
        A linear relation is a source theorem; no statistical assumption.
        """
        try:
            if type(max_work) is not int or max_work<1 or type(z) is not dict or set(z)!={'kind','target','constant','terms'} or z['kind']!='linear':return False
            t=z['target'];c=z['constant'];terms=z['terms'];a=self.a;d=a.d
            if type(t) is not int or not 0<=t<len(a.roots) or type(c) is not int or not -1<=c<=1 or type(terms) is not list or not 1<=len(terms)<=8:return False
            if any(type(row) is not list or len(row)!=2 or type(row[0]) is not int or not 0<=row[0]<len(a.roots) or row[0]==t or type(row[1]) is not int or row[1] not in (-2,-1,1,2) for row in terms):return False
            if [i for i,_ in terms]!=sorted(set(i for i,_ in terms)):return False
            # Finite prefix verified independently, although phase transfers
            # only need the periodic tail.
            for p in range(a.D):
                if (a.prefix[t]>>p&1)!=c+sum(v*(a.prefix[i]>>p&1) for i,v in terms):return False
            pending=[tuple([a.roots[t]]+[a.roots[i] for i,v in terms])];seen=set();work=0
            while pending:
                state=pending.pop()
                if state in seen:continue
                seen.add(state);work+=1
                j=min(d.level(v) for v in state)
                if j==len(d.base):
                    if state[0]!=c+sum(v*b for b,(_,v) in zip(state[1:],terms)):return False
                else:
                    work+=d.base[j]*len(state)
                    if work>max_work:return False
                    pending.extend(tuple(d.arc(v,j,r) for v in state) for r in range(d.base[j]))
                if work>max_work:return False
            self.links.append(deepcopy(z));return True
        except (ValueError,TypeError,IndexError,KeyError,OverflowError):return False
    def bounds(self,i,p):
        b=self.book(i)
        if b.exact is not None:
            c=b.exact.rank(b.D+p)-b.before;return c,c
        # All admitted anchors constrain rank (not just the nearest pair).
        # For valid monotone 1-Lipschitz ranks this agrees with nearest pair.
        L=max(r-max(0,t-p) for t,r in b.anchors.items())
        U=min(r+max(0,p-t) for t,r in b.anchors.items())
        return L,U
    def verify(self,target,p,threshold,z,*,commit=True):
        try:
            if type(target) is not int or not 0<=target<len(self.a.roots) or type(p) is not int or not 0<=p<=self.P or (threshold is not None and (type(threshold) is not int or threshold<0 or threshold.bit_length()>4096)):return False
            if type(z) is not dict or set(z)!={'target','phase','threshold','links','lower','upper','status'} or type(z['target']) is not int or z['target']!=target or nat(z['phase'])!=p or z['threshold']!=(None if threshold is None else str(threshold)):return False
            ids=z['links']
            if type(ids) is not list or any(type(j) is not int or not 0<=j<len(self.links) for j in ids) or len(ids)!=len(set(ids)):return False
            L,U=self.bounds(target,p)
            for j in ids:
                d=self.links[j]
                if d['target']!=target:return False
                if d.get('kind')=='shift':
                    b=d['base'];delta=d['delta'];q0,p0=divmod(delta,self.P);q1,p1=divmod(delta+p,self.P)
                    offset=(q1-q0)*self.count(b)
                    if p0==p1:lo=hi=offset
                    else:
                        a0,b0=self.bounds(b,p0);a1,b1=self.bounds(b,p1)
                        lo=offset+a1-b0;hi=offset+b1-a0
                    L=max(L,lo);U=min(U,hi);continue
                if d.get('kind')=='linear':
                    intervals=[(v,self.bounds(i,p)) for i,v in d['terms']]
                    L=max(L,d['constant']*p+sum(v*(a if v>0 else b) for v,(a,b) in intervals))
                    U=min(U,d['constant']*p+sum(v*(b if v>0 else a) for v,(a,b) in intervals))
                    continue
                l,h=self.bounds(d['base'],p)
                if d['flip']:l,h=p-h,p-l
                pos,neg=d['plus'],d['minus'];ap, bp=self.bounds(pos,p);am,bm=self.bounds(neg,p)
                n=self.count(d['view']);np=self.count(pos);nm=self.count(neg)
                # Four disjoint cells: retained-and-target, retained-only,
                # target-only, neither. Capacity of the outside interval bounds
                # the target-only cell from below; inside bounds it from above.
                common=n-nm;neither=self.P-n-np
                guaranteed_common=max(0,l-nm)
                guaranteed_new=max(0,p-h-neither)
                possible_common=min(h,common)
                possible_new=min(p-l,np)
                L=max(L,l+ap-bm,guaranteed_common+guaranteed_new)
                U=min(U,h+bp-am,possible_common+possible_new)
            if L>U:return False
            status='EXACT' if L==U else 'BELOW' if threshold is not None and U<threshold else 'AT_LEAST' if threshold is not None and L>=threshold else 'UNKNOWN'
            if (nat(z['lower']),nat(z['upper']),z['status'])!=(L,U,status):return False
            if commit and L==U:self.book(target)._put(p,L)
            return True
        except (ValueError,TypeError,IndexError,KeyError,OverflowError):return False
