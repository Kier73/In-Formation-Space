"""Exact characteristic-two distinctness via the MMG-002 Pfaffian verifier."""
from itertools import product
from random import Random
from time import perf_counter
import json
from mmg002_verify import pfaffian

def distinctness_pfaffian(words):
    n=len(words)
    if n%2:raise ValueError('even list length required')
    m=[[int(x!=y) for y in words] for x in words]
    return pfaffian(m,2)

def run():
    start=perf_counter();exhaustive=0;random_checks=0;rng=Random(20261125)
    for words in product(range(16),repeat=4):
        assert distinctness_pfaffian(words)==int(len(set(words))==4);exhaustive+=1
    per_size=[]
    for w in range(1,7):
        n=2**w;universe=n*n;checks=0
        for _ in range(30):
            a=rng.sample(range(universe),n)
            assert distinctness_pfaffian(a)==1;checks+=1
            i,j=rng.sample(range(n),2);a[i]=a[j]
            assert distinctness_pfaffian(a)==0;checks+=1
            a=[rng.randrange(universe) for _ in range(n)]
            assert distinctness_pfaffian(a)==int(len(set(a))==n);checks+=1
        random_checks+=checks;per_size.append(dict(w=w,n=n,checks=checks))
    return dict(exhaustive=exhaustive,random_checks=random_checks,per_size=per_size,seconds=perf_counter()-start)
if __name__=='__main__':print(json.dumps(run(),indent=2))
