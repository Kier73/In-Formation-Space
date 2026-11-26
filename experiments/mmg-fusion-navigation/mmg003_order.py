"""MMG-003: exact tensor-product ground navigation, charged scalar work."""
from itertools import combinations, permutations
from fractions import Fraction
from math import prod
import hashlib, json, time
import numpy as np
from mmg002_fusion import wedges, coeff
from sympy import Matrix


def ground(p):
    pairs = [(a,b) for a in wedges(12) for b in wedges(11)]
    labels = [l for h in range(1,16,2) for l in wedges(h)]
    rows = [[coeff(l,b,a) for a,b in pairs] for l in labels]
    for ids in combinations(range(len(rows)), len(pairs)):
        m = Matrix([rows[i] for i in ids])
        if int(m.det()) % p:
            # columns are generator coordinates, rows are operator coordinates
            return [labels[i] for i in ids], np.array(m.T.tolist(),dtype=np.int64), np.array([[int(v.p)*pow(int(v.q),-1,p)%p for v in row] for row in m.T.inv().tolist()],dtype=np.int64)
    raise AssertionError('no invertible subset')


def plan(factors):
    def key(i):
        a=factors[i]; o,n=a.shape; c=Fraction(np.count_nonzero(a),n); r=Fraction(o,n)
        return (0,c/(1-r)) if r<1 else (2,c/(1-r)) if r>1 else (1,Fraction(0))
    return tuple(sorted(range(len(factors)),key=key))


def cost(factors, order):
    size=prod(a.shape[1] for a in factors); peak=size; terms=0; adds=0
    for i in order:
        a=factors[i]; o,n=a.shape; fibers=size//n; nz=int(np.count_nonzero(a)); occupied=int(np.count_nonzero(np.any(a,axis=1)))
        terms+=fibers*nz; adds+=fibers*(nz-occupied); size=fibers*o; peak=max(peak,size)
    return terms,adds,peak


def realize(x,factors,order,p):
    for i in order:
        a=factors[i]%p; v=np.moveaxis(x,i,-1); shape=v.shape; flat=v.reshape(-1,shape[-1]); out=np.zeros((len(flat),a.shape[0]),dtype=np.int64)
        # Explicit sparse terms, including actual materialization and additions.
        for j,row in enumerate(a):
            inds=np.flatnonzero(row)
            if len(inds):
                k=inds[0]; out[:,j]=flat[:,k]*row[k]
                for k in inds[1:]: out[:,j]+=flat[:,k]*row[k]
        x=np.moveaxis((out%p).reshape(shape[:-1]+(a.shape[0],)),-1,i)
    return x


def dense(factors,p):
    m=np.array([[1]],dtype=np.int64)
    for a in factors:m=np.kron(m,a)%p
    return m


def run():
    rng=np.random.default_rng(20261124); start=time.perf_counter(); checks=0
    for p in (2,3,5,7,11):
        labels,m,inv=ground(p)
        for k in range(1,4):
            fs=[m%p]*k; x=rng.integers(0,p,size=(6,)*k,dtype=np.int64)
            y=realize(x,fs,plan(fs),p); assert np.array_equal(y.ravel(),dense(fs,p)@x.ravel()%p); assert np.array_equal(realize(y,[inv%p]*k,tuple(reversed(range(k))),p),x); checks+=2
    # Heterogeneous factors: exact output restrictions and generator embeddings.
    mixed=0; trials=0; max_gain=0; example=None
    for _ in range(100):
        p=11; fs=[]
        for _ in range(5):
            o,n=map(int,rng.integers(1,7,size=2)); fs.append(m[:o,:n]%p)
        order=plan(fs); c=cost(fs,order)[0]; brute=min(cost(fs,q)[0] for q in permutations(range(5))); assert c==brute; trials+=120
        x=rng.integers(0,p,size=tuple(a.shape[1] for a in fs),dtype=np.int64); y=realize(x,fs,order,p); assert np.array_equal(y.ravel(),dense(fs,p)@x.ravel()%p); mixed+=1
        bad=max(cost(fs,q)[0] for q in permutations(range(5))); gain=bad/max(c,1)
        if gain>max_gain:max_gain=gain;example=dict(shapes=[list(a.shape) for a in fs],order=order,best_terms=c,worst_terms=bad,planned_peak=cost(fs,order)[2])
    p=11;k=8;fs=[m%p]*k; n=6**k; x=rng.integers(0,p,size=(6,)*k,dtype=np.int64); t=time.perf_counter();y=realize(x,fs,plan(fs),p); forward=time.perf_counter()-t; t=time.perf_counter();z=realize(y,[inv%p]*k,tuple(reversed(range(k))),p); reverse=time.perf_counter()-t; assert np.array_equal(z,x)
    # Independently compute selected full rows by separable weights; no reuse of realize.
    probes=8
    for _ in range(probes):
        idx=tuple(map(int,rng.integers(0,6,size=k))); w=np.array([1],dtype=np.int64)
        for j in idx:w=np.kron(w,m[j]%p)%p
        assert int(w@x.ravel()%p)==y[idx]
    terms,adds,peak=cost(fs,plan(fs)); dense_nz=int(np.count_nonzero(m%p))**k
    return dict(labels=labels, matrix=m.tolist(), inverse=inv.tolist(), dense_checks=checks, mixed_checks=mixed, permutation_cases=trials, max_order_gain=max_gain, order_example=example, large=dict(p=p,k=k,coordinates=n,implicit_matrix_entries=n*n,implicit_nonzero_entries=dense_nz,local_fibers_per_axis=n//6,terms=terms,adds=adds,peak_logical_coordinates=peak,forward_seconds=forward,reverse_seconds=reverse,full_roundtrip=True,independent_row_checks=probes,output_sha256=hashlib.sha256(y.astype('<i8').tobytes()).hexdigest()),seconds=time.perf_counter()-start)

if __name__=='__main__':
    print(json.dumps(run(),indent=2))
