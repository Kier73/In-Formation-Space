"""MMG-004: transform a correlated tensor train without expanding its state space."""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from math import prod
import hashlib,json,time
import numpy as np
from mmg003_order import ground,realize,plan


def make_train(k,d,r,p,rng):
    return [rng.integers(0,p,size=(1 if i==0 else r,d,1 if i==k-1 else r),dtype=np.int64) for i in range(k)]


def coordinate(cores,idx,p):
    v=np.ones((1,),dtype=np.int64)
    for a,j in zip(cores,idx):v=v@a[:,j,:]%p
    return int(v[0])


def translate(job):
    i,a,m,p=job
    b=np.einsum('oi,lir->lor',m%p,a)%p
    return i,b


def digest(cores):
    h=hashlib.sha256()
    for a in cores:
        h.update(np.array(a.shape,dtype='<i8').tobytes());h.update(a.astype('<i8').tobytes())
    return h.hexdigest()


def translate_all(cores,m,p,workers=0):
    jobs=[(i,a,m,p) for i,a in enumerate(cores)]
    if workers:
        with ProcessPoolExecutor(max_workers=workers) as pool: rows=list(pool.map(translate,jobs))
    else: rows=list(map(translate,jobs))
    assert sorted(i for i,b in rows)==list(range(len(cores)))
    return [b for i,b in sorted(rows)]


def run():
    rng=np.random.default_rng(20261125);checks=0
    for p in (2,3,5,7,11):
        _,m,inv=ground(p)
        for k in (2,3,4):
            a=make_train(k,6,3,p,rng);b=translate_all(a,m,p)
            x=np.array([coordinate(a,q,p) for q in product(range(6),repeat=k)]).reshape((6,)*k)
            y=realize(x,[m%p]*k,plan([m%p]*k),p)
            assert all(coordinate(b,q,p)==y[q] for q in product(range(6),repeat=k));checks+=6**k
            assert digest(translate_all(b,inv,p))==digest(a)
    p=11;_,m,inv=ground(p);k=64;r=4;a=make_train(k,6,r,p,rng)
    t=time.perf_counter();b=translate_all(a,m,p);elapsed=time.perf_counter()-t
    t=time.perf_counter();c=translate_all(a,m,p,4);distributed=time.perf_counter()-t
    assert digest(b)==digest(c);assert digest(translate_all(b,inv,p))==digest(a)
    # Verify selected transformed coordinates by an independent contraction order:
    # choose output row, contract it with each input core, then contract the bond chain.
    for _ in range(200):
        q=rng.integers(0,6,size=k);v=np.ones((1,),dtype=np.int64)
        for i,j in enumerate(q):
            v=sum((int(m[j,s])*(v@a[i][:,s,:]) for s in range(6)),np.zeros(a[i].shape[-1],dtype=np.int64))%p
        assert int(v[0])==coordinate(b,q,p)
    # Verify true correlation: flattening of a short four-core train has rank > 1.
    aa=make_train(4,6,4,p,rng);flat=np.array([coordinate(aa,q,p) for q in product(range(6),repeat=4)]).reshape(36,36)
    # A nonzero 2x2 minor certifies nonseparability across the central cut.
    witness=next(( [i,j,s,t] for i in range(36) for j in range(i+1,36) for s in range(36) for t in range(s+1,36) if (int(flat[i,s])*int(flat[j,t])-int(flat[i,t])*int(flat[j,s]))%p),None)
    assert witness is not None
    # For the actual large train, contract left/right halves against distinct exterior assignments.
    # Search for a nonzero minor of its cut flattening without materializing it.
    left=[tuple(map(int,rng.integers(0,6,size=k//2))) for _ in range(12)];right=[tuple(map(int,rng.integers(0,6,size=k//2))) for _ in range(12)]
    f=np.array([[coordinate(a,l+rr,p) for rr in right] for l in left]);large_minor=next(([i,j,s,t] for i in range(12) for j in range(i+1,12) for s in range(12) for t in range(s+1,12) if (int(f[i,s])*int(f[j,t])-int(f[i,t])*int(f[j,s]))%p),None);assert large_minor is not None
    stored=sum(x.size for x in a);terms=sum(x.shape[0]*x.shape[2]*np.count_nonzero(m%p) for x in a)
    # einsum actually uses dense core multiplication, including zeros; charge dense terms.
    dense_terms=sum(x.shape[0]*x.shape[2]*36 for x in a)
    return dict(fields=[2,3,5,7,11],exhaustive_small_coordinates=checks,k=k,bond=r,logical_coordinates=str(6**k),stored_input_scalars=stored,stored_output_scalars=sum(x.size for x in b),sparse_theoretical_terms=int(terms),dense_terms=int(dense_terms),serial_seconds=elapsed,process_pool_seconds=distributed,workers=4,full_core_roundtrip=True,independent_coordinate_checks=200,small_nonseparability_minor=witness,large_nonseparability_minor=large_minor,source_sha256=digest(a),output_sha256=digest(b))

if __name__=='__main__':print(json.dumps(run(),indent=2))
