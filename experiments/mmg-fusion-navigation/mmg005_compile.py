"""Compile exact rank grounds with MMG-003 ordering and MMG-004 core translation."""
import hashlib, json, time
from itertools import product
from math import comb
import numpy as np
from mmg003_order import ground, plan, cost, realize
from mmg004_core import translate_all

STRASSEN=[[9,9,9],[12,1,12],[1,10,10],[8,5,5],[3,8,3],[5,3,8],[10,12,1]]
WALK3=[[224,385,82],[216,24,18],[72,36,391],[56,8,26],[438,390,437],[40,9,90],[192,390,144],[200,63,18],[438,130,439],[27,32,405],[65,292,5],[32,65,72],[288,256,55],[146,146,2],[446,6,437],[195,32,37],[128,54,130],[288,457,64],[3,325,1],[211,290,437],[7,320,1],[365,2,439],[101,256,432],[392,9,64],[2,45,1],[448,384,194]]

def maps(base,terms):
    d=base*base
    if any(len(t)!=3 or any(type(x)!=int or not 0<x<1<<d for x in t) for t in terms):raise ValueError('bad rank terms')
    u,v,w=(np.array([[(t[a]>>i)&1 for i in range(d)] for t in terms],dtype=np.int64) for a in range(3))
    expected=np.zeros((d,d,d),dtype=np.int64)
    for i,j,k in product(range(base),repeat=3):expected[i*base+j,j*base+k,i*base+k]=1
    if not np.array_equal(np.einsum('ta,tb,tc->abc',u,v,w)%2,expected):raise ValueError('formal tensor mismatch')
    return u,v,w.T,expected

def pack(x,b,k):
    return x.reshape((b,)*(2*k)).transpose(tuple(j for i in range(k) for j in (i,k+i))).reshape((b*b,)*k)

def unpack(x,b,k):
    return x.reshape((b,)*(2*k)).transpose(tuple(range(0,2*k,2))+tuple(range(1,2*k,2))).reshape((b**k,b**k))

def compile_product(a,b,base,k,terms):
    u,v,w,_=maps(base,terms)
    fs=lambda m:[m]*k
    trans=lambda x,m:realize(x,fs(m),plan(fs(m)),2)
    left=trans(pack(a,base,k),u);right=trans(pack(b,base,k),v)
    c=unpack(trans(left*right,w),base,k)
    linear_terms,adds=0,0
    for m in (u,v,w):
        t,s,_=cost(fs(m),plan(fs(m)));linear_terms+=t;adds+=s
    return c,dict(products=len(terms)**k,linear_terms=linear_terms,linear_additions=adds,total_field_ops=len(terms)**k+adds)

def core_control():
    _,m,inv=ground(2);_,_,_,t=maps(2,STRASSEN)
    padded=np.zeros((6,6,6),dtype=np.int64);padded[:4,:4,:4]=t
    f=np.kron(np.kron(m%2,m%2),m%2)%2;g=np.kron(np.kron(inv%2,inv%2),inv%2)%2
    assert np.array_equal(f@g%2,np.eye(216,dtype=np.int64))
    out=realize(padded,[m%2]*3,plan([m%2]*3),2)
    cores=[padded.reshape(1,216,1).copy() for _ in range(32)]
    translated=translate_all(cores,f,2);assert all(np.array_equal(x.reshape(6,6,6),out) for x in translated)
    back=translate_all(translated,g,2);assert all(np.array_equal(a,b) for a,b in zip(cores,back))
    return dict(factors=32,represented_padded_coefficients=str(216**32),unpadded_coefficients=str(64**32),stored_core_scalars=32*216,roundtrip=True,rank_invariant=True)

def run():
    rng=np.random.default_rng(20261125);out=[]
    for b,ts,ks in ((2,STRASSEN,range(1,8)),(3,WALK3,range(1,5))):
        maps(b,ts)
        bad=[x.copy() for x in ts];bad[0][0]^=1
        try:maps(b,bad);raise AssertionError('tamper accepted')
        except ValueError:pass
        for k in ks:
            n=b**k;a=rng.integers(0,2,size=(n,n),dtype=np.int64);bb=rng.integers(0,2,size=(n,n),dtype=np.int64)
            t=time.perf_counter();c,costs=compile_product(a,bb,b,k,ts);elapsed=time.perf_counter()-t
            assert np.array_equal(c,a@bb%2)
            out.append(dict(base=b,k=k,n=n,**costs,naive_products=n**3,naive_field_ops=n*n*(2*n-1),strict_target=(len(ts)**k)**4<n**9,seconds=elapsed,sha256=hashlib.sha256(c.astype('<i8').tobytes()).hexdigest()))
    controls=[dict(w=w,bond_lower_bound=str(comb(2**w,2**(w-1)))) for w in range(1,9)]
    return dict(dense_products=out,core_control=core_control(),list_distinctness_record_cut=controls)

if __name__=='__main__':print(json.dumps(run(),indent=2))
