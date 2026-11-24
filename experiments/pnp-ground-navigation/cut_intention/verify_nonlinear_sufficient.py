"""Separate tuple-domain source checker and symbolic predicate-translation checker.

check_translation assumes the exact seed was independently admitted by receiver.
It is NOT a public seed-admission function. check_seed binds external contract.
"""
from itertools import product
from collections import Counter
from verify_composed_ground import normal
from regional_memory import identity


def check_seed(n,scope,source,visible,predicates,seed):
    try:
        s=list(scope);v=list(visible);c=normal(source,n);p=normal(predicates,n)
        if s!=sorted(set(s)) or len(s)>10 or any(type(x)is not int or not 1<=x<=n for x in s):return False
        if v!=sorted(set(v)) or not set(v)<=set(s) or any(type(x)is not int for x in v):return False
        if len(p)>32 or any(abs(l) not in s for row in c+p for l in row):return False
        d=dict(schema='ifs.cig014.predicate-fiber.v1',n=n,scope=s,source=[list(r) for r in c],visible=v,predicates=[list(r) for r in p])
        if seed['descriptor']!=d or seed['key']!=identity(d):return False
        counts=Counter()
        for vals in product((0,1),repeat=len(s)):
            a=dict(zip(s,vals))
            def sat(row):return any(a[abs(l)]==int(l>0) for l in row)
            if all(sat(row) for row in c):
                signature=tuple(a[u] for u in v)+tuple(int(sat(row)) for row in p)
                counts[signature]+=1
        expect=sorted([[sum(bit*2**i for i,bit in enumerate(sig)),str(count)] for sig,count in counts.items()])
        return (set(seed)=={'descriptor','key','bins','bits'} and all(type(k)is int and type(z)is str for k,z in seed['bins']) and seed['bins']==expect and type(seed['bits'])is int and seed['bits']==max(0,len(counts)-1).bit_length())
    except (ValueError,KeyError,TypeError,IndexError,AttributeError):return False


def check_translation(n,seed,desc,cover,msg):
    try:
        d=seed['descriptor'];s=d['scope'];v=d['visible'];p=d['predicates'];b=desc['boundary']
        if d['n']!=n or seed['key']!=identity(d) or s!=desc['scope'] or b!=sorted(set(b)) or not set(b)<=set(v):return False
        old=set(normal(d['source'],n));new=set(normal(desc['clauses'],n))
        if not old<=new or any(abs(l) not in s for row in new for l in row):return False
        if [tuple(c) for c,_ in cover]!=sorted(new-old,key=lambda c:(len(c),c)):return False
        # Every output clause must be exactly the disjunction of its cited predicates/literals.
        for clause,parts in cover:
            literals=set()
            for kind,i in parts:
                if type(kind)is not int or type(i)is not int or i<0:return False
                if kind==0 and i<len(p):literals.update(p[i])
                elif kind in (1,2) and i<len(v):literals.add(v[i] if kind==1 else -v[i])
                else:return False
            if literals!=set(clause):return False
        sums=Counter();seen=set()
        for k,z in seed['bins']:
            if type(k)is not int or not 0<=k<2**(len(v)+len(p)) or k in seen:return False
            if type(z)is not str or not z.isascii() or not z.isdecimal() or str(int(z))!=z or int(z)<=0:return False
            seen.add(k);bits=tuple((k//2**i)%2 for i in range(len(v)+len(p)))
            def read(term):
                kind,i=term
                return bits[len(v)+i] if kind==0 else (bits[i] if kind==1 else 1-bits[i])
            if all(any(read(term) for term in parts) for _,parts in cover):
                sums[tuple(bits[v.index(u)] for u in b)]+=int(z)
        expect=[str(sums[tuple((i//2**j)%2 for j in range(len(b)))]) for i in range(2**len(b))]
        return msg==dict(key=identity(desc),boundary=b,counts=expect)
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False
