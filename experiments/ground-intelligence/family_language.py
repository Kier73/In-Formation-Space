"""PGI-003: qualified parametric temporal pullback families.
Discovery uses structure; the PGI-002 independent checker authorizes results.
No target history or target namespace is used by the discovery procedures.
"""
from dataclasses import dataclass
from itertools import product, permutations
from collections import Counter
from math import gcd, prod
from ground_network import View, Work, Exhausted, integer, digest
from skill_language import normalize, PRIMITIVES
from verify_skill_language import verify_pullback


def crt(parts):
    r,m=0,1
    for x,n in parts:
        r+=m*((x-r)*pow(m,-1,n)%n);m*=n
    return r


def event_phases(v, polarity, w, limit):
    """List only a bounded minority set over one period, with CRT skipping."""
    count=v.total if polarity else v.period-v.total
    if count>limit:return None
    out=[];todo=[(v.root,0,1)]
    while todo:
        x,r,m=todo.pop();w.charge()
        if x<2:
            if x==polarity:
                n=v.period//m;w.charge(n)
                out.extend(range(r,v.period,m))
            continue
        j,kids=v.nodes[x-2];q=v.base[j];inv=pow(m,-1,q);w.charge(q)
        todo.extend((child,r+m*((i-r)*inv%q),m*q) for i,child in enumerate(kids) if child!=1-polarity)
    assert len(out)==count
    return sorted(out)


def lifts(a,b,p,cutoff):
    """Finite representatives for all positive stride/nonnegative offset lifts.
    Beyond the source cutoff the periodic residues alone determine behavior.
    """
    aa=a or p
    bs=list(range(b,cutoff,p))+[b+max(0,(cutoff-b+p-1)//p)*p]
    aa_choices=list(range(aa,cutoff+1,p))+[aa+max(0,(cutoff+1-aa+p-1)//p)*p]
    for x,y in product(dict.fromkeys(aa_choices),dict.fromkeys(bs)):yield x,y


def sparse_candidates(source,target,w,limit):
    p,q=source.period,target.period
    if p%q:return
    d=p//q
    for pol in (1,0):
        old=event_phases(source,pol,w,limit)
        if old is None or not old:continue
        for c in (0,1):
            new=event_phases(target,pol^c,w,limit)
            if new is None or len(new)>len(old):continue
            if not new:
                # The image a*t+b visits precisely the residue class b mod d.
                # A missing class gives an exact constant periodic observation.
                used={s%d for s in old};w.charge(len(old))
                missing=0
                while missing in used:w.charge();missing+=1
                if missing<d:
                    # Try one canonical missing class and finite-prefix offsets.
                    yield d%p,missing,c
                    for b in range(min(source.cutoff,p)):
                        w.charge()
                        if b%d not in used:yield d%p,b,c
                continue
            r=new[0]
            if len(new)==1:
                # A single phase in the compact period needs no pair fitting.
                # Other units may be required for finite-prefix agreement.
                for s in old:
                    w.charge();yield d%p,(s-d*r)%p,c
                continue
            delta=new[1]-r;g=gcd(delta,q);m=q//g
            for s,t in permutations(old,2):
                w.charge();e=(t-s)%p
                if e%d or (e//d)%g:continue
                u0=((e//d//g)*pow(delta//g,-1,m))%m if m>1 else 0
                for u in range(u0,q,m):
                    w.charge()
                    if gcd(u,q)!=1:continue
                    a=d*u;yield a,(s-a*r)%p,c


def partitions(v,w):
    """Exact cofactor equivalence on each residue coordinate.
    For a reduced ordered MDD two residues have identical cofactors iff their
    child-ID vectors match at every reachable node at that level.
    """
    by=[[] for _ in v.base];seen=set();stack=[v.root]
    while stack:
        x=stack.pop();w.charge()
        if x<2 or x in seen:continue
        seen.add(x);j,kids=v.nodes[x-2];by[j].append(kids);w.charge(len(kids));stack.extend(kids)
    out=[]
    for m,rows in zip(v.base,by):
        ids={};labels=[]
        for r in range(m):
            w.charge(len(rows)+1);key=tuple(row[r] for row in rows)
            if key not in ids:ids[key]=len(ids)
            labels.append(ids[key])
        out.append(tuple(labels))
    return out


def local_maps(old,new,w):
    m=len(old);w.charge(2*m);oc=Counter(old);nc=Counter(new)
    if sorted(oc.values())!=sorted(nc.values()):return []
    # Start at the least-populated class to prune the translation coordinate.
    r=min(range(m),key=lambda i:nc[new[i]])
    anchors=[s for s in range(m) if oc[old[s]]==nc[new[r]]];out=[]
    for a in range(1,m):
        w.charge()
        if gcd(a,m)!=1:continue
        for s in anchors:
            b=(s-a*r)%m;forward={};reverse={};ok=True
            for i in range(m):
                w.charge();j=new[i];k=old[(a*i+b)%m]
                if oc[k]!=nc[j] or (j in forward and forward[j]!=k) or (k in reverse and reverse[k]!=j):ok=False;break
                forward[j]=k;reverse[k]=j
            if ok:out.append((a,b))
    return out


def cofactor_candidates(source,target,w):
    if source.base!=target.base:return
    if source.total not in (target.total, target.period-target.total):return
    pp=partitions(source,w);qq=partitions(target,w);maps=[]
    for x,y in zip(pp,qq):
        local=local_maps(x,y,w)
        if not local:return
        maps.append(local)
    for combo in product(*maps):
        w.charge();a=crt(zip((x[0] for x in combo),source.base));b=crt(zip((x[1] for x in combo),source.base))
        # Read one periodic coordinate to choose polarity, avoiding an extra proof.
        t=max(source.cutoff,target.cutoff);w.charge(1+len(source.base)+len(target.base))
        at=(a or source.period)*t+b
        # The selected periodic sample can be reduced before reading the source.
        at=source.cutoff+(at-source.cutoff)%source.period
        c=source.bit(at)^target.bit(t)
        yield a,b,c


@dataclass(frozen=True)
class Family:
    """A learned dispatch family, not an assertion about all future inputs."""
    method:str
    examples:tuple
    @property
    def key(self):return digest(['pgi.family.v1',self.method,self.examples])


class FamilyIntelligence:
    def __init__(self):self.examples={};self.families={}
    def observe(self,source,target,trace):
        from verify_family_language import verify_example
        form=normalize(trace)
        if not verify_example(source,target,form):return False
        if source.key in self.examples or len(self.examples)>=128:return False
        self.examples[source.key]=(source,target,form)
        return True
    def induce(self):
        from verify_family_language import qualify_family
        for method in ('sparse','cofactor'):
            keys=tuple(k for k,(a,b,f) in self.examples.items() if eligible(method,a,b,f))
            if len(keys)<3:continue
            # Require variation in both time coefficients, not repeated calls.
            if len({self.examples[k][2][0] for k in keys})<2 or len({self.examples[k][2][1] for k in keys})<2:continue
            f=Family(method,keys)
            if qualify_family(f,self.examples):self.families[method]=f
        return tuple(self.families.values())
    def discover(self,source,target,*,max_work=2_000_000,max_candidates=1024,event_limit=32,primitive_first=False):
        """Finite proposal grammar. UNKNOWN is not a nonexistence certificate."""
        integer(max_candidates,1);integer(event_limit,1)
        if max_candidates>100000 or event_limit>32:raise ValueError('budget')
        w=Work(max_work);seen=set();attempts=0;methods=[]
        try:
            if primitive_first:
                methods.append('primitive')
                for op in PRIMITIVES:
                    if attempts>=max_candidates:return None,dict(work=w.used,attempts=attempts,methods=methods)
                    form=normalize((op,));seen.add(form);attempts+=1;w.charge()
                    if w.used>=max_work:raise Exhausted('budget')
                    ok,cost=verify_pullback(source,target,form,max_work=max_work-w.used);w.charge(cost)
                    if ok:return form,dict(work=w.used,attempts=attempts,methods=methods)
            for method in ('sparse','cofactor'):
                if method not in self.families:continue
                if method=='sparse' and min(source.total,source.period-source.total)>event_limit:continue
                methods.append(method);candidates=sparse_candidates(source,target,w,event_limit) if method=='sparse' else cofactor_candidates(source,target,w)
                for a,b,c in candidates:
                    for x,y in lifts(a,b,source.period,source.cutoff):
                        form=(x,y,c);w.charge()
                        if form in seen:continue
                        if attempts>=max_candidates:return None,dict(work=w.used,attempts=attempts,methods=methods)
                        seen.add(form);attempts+=1
                        if w.used>=max_work:raise Exhausted('budget')
                        ok,cost=verify_pullback(source,target,form,max_work=max_work-w.used);w.charge(cost)
                        if ok:return form,dict(work=w.used,attempts=attempts,methods=methods)
        except Exhausted:pass
        return None,dict(work=min(w.used,max_work),attempts=attempts,methods=methods)
    def instantiate(self,source,method,form,*,max_work=500000):
        """Call an admitted family on a new source, independently check result."""
        from skill_language import compile_view
        if method not in self.families:raise ValueError('unlearned family')
        try:
            v,work=compile_view(source,form,max_work=max_work)
            if not eligible(method,source,v,form):return None
            ok,checked=verify_pullback(source,v,form,max_work=max_work)
            return (v,dict(compile_work=work,qualification_work=checked)) if ok else None
        except Exhausted:return None
    def packet(self):
        # Source Views supplied separately and independently admitted on restore.
        return {'schema':'pgi.family-memory.v1','examples':[[k,b.key,[str(f[0]),str(f[1]),f[2]]] for k,(a,b,f) in self.examples.items()], 'families':[[f.key,f.method,list(f.examples)] for f in self.families.values()]}
    @classmethod
    def restore(cls,packet,views):
        from verify_family_language import restore
        return restore(packet,views)


def eligible(method,a,b,f):
    if method=='sparse':return min(a.total,a.period-a.total)<=32 and a.period%b.period==0 and b.period==a.period//gcd(a.period,f[0])
    if method=='cofactor':return a.base==b.base and gcd(a.period,f[0])==1
    return False


def express(source,target,form,ordinal,*,max_work=500000):
    from ground_network import select
    from ground_network_verify import verify_selection
    if not verify_pullback(source,target,form,max_work=max_work)[0]:return None
    r=select(target,ordinal,max_work=max_work)
    if r['status']!='FOUND' or not verify_selection(target,ordinal,r['time'],max_work=max_work):return None
    return {'schema':'pgi.family-expression.v1','source':source.key,'target':target.key,'form':[str(form[0]),str(form[1]),form[2]],'ordinal':str(ordinal),'time':str(r['time'])}
