"""CIG-031A: rank transfer across source-admitted temporal intentions.
All facts are proposals until independently accepted. No source states enumerated.
"""
from math import prod
from copy import deepcopy
from rank_anchors import Anchors
from temporal_rank import Rank
from temporal_ground import contract_time


def make_link(lang, base, target, flip=False):
    """Register B = view + (B minus view) - (view minus B), using CIG-024 operations."""
    if type(flip) is not bool or any(type(i) is not int or not 0<=i<len(lang.roots) for i in (base,target)):
        raise ValueError('link')
    view=lang.extend('not',base) if flip else base
    opposite=lang.extend('not',view)
    nt=lang.extend('not',target)
    plus=lang.extend('and',target,opposite)
    minus=lang.extend('and',view,nt)
    return dict(base=base,target=target,flip=flip,view=view,opposite=opposite,nt=nt,plus=plus,minus=minus)


class Memory:
    def __init__(self,lang):
        self.lang=lang;self.P=prod(lang.d.base);self.books={};self.ranks={};self.links=[];self.counts={}
    def book(self,i):
        if i not in self.books:self.books[i]=Anchors(self.lang,i)
        return self.books[i]
    def count(self,i):
        if i not in self.counts:self.counts[i]=self.lang.count(i)
        return self.counts[i]
    def open(self,i,*,max_work=2_000_000):
        r=Rank(self.lang,i,max_work=max_work);return r
    def commit_open(self,r):self.ranks[r.i]=r
    def fact(self,i,p):
        contract_time(p)
        if p>self.P or i not in self.ranks:raise ValueError('rank fact')
        x=self.ranks[i];return dict(index=i,phase=str(p),rank=str(x.rank(x.D+p)-x.before))
    def commit_fact(self,z):self.book(z['index'])._anchors[int(z['phase'])]=int(z['rank'])
    def close(self,i):self.ranks.pop(i,None)
    def commit_link(self,z):
        self.links.append(deepcopy(z));return len(self.links)-1
    def bounds(self,i,p):
        if not 0<=p<=self.P:raise ValueError('phase')
        if i in self.ranks:
            r=self.ranks[i];v=r.rank(r.D+p)-r.before;return v,v
        b=self.book(i);z=b.compare(b.D+p,0);return int(z['lower'])-b.before,int(z['upper'])-b.before
    def transfer(self,target,phase,*,threshold=None,links=None):
        contract_time(phase)
        if phase>self.P or type(target) is not int or not 0<=target<len(self.lang.roots):raise ValueError('query')
        if threshold is not None:contract_time(threshold)
        chosen=[j for j,z in enumerate(self.links) if z['target']==target] if links is None else list(links)
        if len(chosen)!=len(set(chosen)):raise ValueError('duplicate link')
        L,U=self.bounds(target,phase);evidence=[]
        for j in chosen:
            if type(j) is not int or not 0<=j<len(self.links):raise ValueError('link')
            z=self.links[j]
            if z['target']!=target:raise ValueError('target')
            if z.get('kind')=='shift':
                b=z['base'];delta=z['delta'];q0,s0=divmod(delta,self.P);q1,s1=divmod(delta+phase,self.P)
                if s0==s1:lo=hi=(q1-q0)*self.count(b)
                else:
                    l0,h0=self.bounds(b,s0);l1,h1=self.bounds(b,s1);offset=(q1-q0)*self.count(b)
                    lo,hi=offset+l1-h0,offset+h1-l0
                L=max(L,lo);U=min(U,hi);evidence.append(j);continue
            if z.get('kind')=='linear':
                lo=hi=z['constant']*phase
                for i,c in z['terms']:
                    l,h=self.bounds(i,phase);lo+=min(c*l,c*h);hi+=max(c*l,c*h)
                L=max(L,lo);U=min(U,hi);evidence.append(j);continue
            b,v,x,y=z['base'],z['view'],z['plus'],z['minus'];l,h=self.bounds(b,phase)
            if z['flip']:l,h=phase-h,phase-l
            A,X,Y=self.count(v),self.count(x),self.count(y)
            pl,ph=self.bounds(x,phase);ml,mh=self.bounds(y,phase)
            # Signed residual interval, and sharper contingency-capacity bounds.
            lo=max(l+pl-mh,max(0,l-Y)+max(0,X-(self.P-A-phase+h)))
            hi=min(h+ph-ml,min(h,A-Y)+min(phase-l,X))
            L=max(L,lo);U=min(U,hi);evidence.append(j)
        if L>U:raise ValueError('inconsistent memory')
        status='EXACT' if L==U else 'BELOW' if threshold is not None and U<threshold else 'AT_LEAST' if threshold is not None and L>=threshold else 'UNKNOWN'
        return dict(target=target,phase=str(phase),threshold=None if threshold is None else str(threshold),links=evidence,lower=str(L),upper=str(U),status=status)
    def commit_transfer(self,z):
        if z['status']=='EXACT':self.book(z['target'])._anchors[int(z['phase'])]=int(z['lower'])
