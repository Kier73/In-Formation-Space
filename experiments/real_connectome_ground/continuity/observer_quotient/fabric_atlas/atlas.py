"""RCG-007: universal, multi-intention exact observable atlas over RCG-006.

A source-bound microstate quotient P M = Q P permits arbitrary source mixtures and
all declared readouts of P x. Characteristic polynomial of Q is an all-state,
all-future-time certificate. This code imports the existing RCG-005 polynomial
navigator and RCG-006 full-source verification; it does NOT infer arbitrary
pretrained networks, invent an E-CPU transport, or claim physical host authority.
"""
from __future__ import annotations
from typing import Any
from temporal_ground import MAX_TICK, hash_object
from conjugate_ground import quotient_power
from observer_quotient import ExpandedSyntheticGround, QuotientRefused, verify

SCHEMA='ifs.rcg007.compositional-observer-atlas.v1'
MAX_QUERIES=64
MAX_SOURCES=64


def require(flag: bool, why: str) -> None:
    if not flag: raise QuotientRefused(why)


def matrix_from_columns(columns: tuple, field: int) -> list[list[int]]:
    n=len(columns)
    require(1<=n<=64,'invalid quotient dimension')
    matrix=[[0]*n for _ in range(n)]
    for col,edges in enumerate(columns):
        for dst,weight in edges:
            require(type(dst) is int and 0<=dst<n and type(weight) is int and 0<=weight<field,
                    'invalid quotient coefficient')
            matrix[dst][col]=(matrix[dst][col]+weight)%field
    return matrix


def multiply(a: list[list[int]],b: list[list[int]],p:int)->list[list[int]]:
    n=len(a)
    c=[[0]*n for _ in range(n)]
    for i in range(n):
        for k,v in enumerate(a[i]):
            if v:
                for j,w in enumerate(b[k]):
                    c[i][j]=(c[i][j]+v*w)%p
    return c


def characteristic_recurrence(matrix:list[list[int]],p:int)->list[int]:
    """Faddeev-LeVerrier: q(X)=X^k-c[0]X^(k-1)-...-c[k-1]."""
    n=len(matrix)
    require(1<=n<=64 and all(len(row)==n for row in matrix) and p>n,
            'cannot construct quotient polynomial')
    b=[[int(i==j) for j in range(n)] for i in range(n)]
    coeff=[]
    for k in range(1,n+1):
        b=multiply(matrix,b,p)
        term=(-sum(b[i][i] for i in range(n))*pow(k,-1,p))%p
        coeff.append((-term)%p)
        for i in range(n):b[i][i]=(b[i][i]+term)%p
    require(all(not v for row in b for v in row),
            'characteristic residual not zero')
    return coeff


def independent_full_matrix_proof(m:list[list[int]],coeff:list[int],p:int)->None:
    """Horner check q(Q)=0 from basis action, separate from Faddeev producer."""
    n=len(m)
    require(type(coeff) is list and len(coeff)==n and
            all(type(z) is int and 0<=z<p for z in coeff),
            'malformed full-state recurrence')
    residual=[[int(i==j) for j in range(n)] for i in range(n)]
    for c in coeff:
        residual=multiply(m,residual,p)
        for i in range(n):residual[i][i]=(residual[i][i]-c)%p
    require(all(not v for row in residual for v in row),
            'full-state recurrence annihilator fails')


def prepare_atlas(op:ExpandedSyntheticGround,quotient_certificate:dict[str,Any])->dict[str,Any]:
    _,columns=verify(op,quotient_certificate,replay_observations=True)
    matrix=matrix_from_columns(columns,op.field)
    coefficients=characteristic_recurrence(matrix,op.field)
    independent_full_matrix_proof(matrix,coefficients,op.field)
    body={
      'schema':SCHEMA+'.certificate.v1',
      'source_ground':op.source_fingerprint,
      'source_blob':op.source_blob,
      'expanded_ground':op.fingerprint,
      'quotient_certificate':quotient_certificate['digest'],
      'microstate_count':op.n,
      'dimension':len(columns),
      'field':op.field,
      'coefficients':coefficients,
      'readouts':['class','linear','sum_squares','shear_pair'],
      'guarantee':'P M = Q P and q(Q)=0 for every initial vector and future tick',
      'source_scope':'synthetic expansion of observed connectome statistics, not biological dynamics',
    }
    return {**body,'digest':hash_object(body)}


def verify_atlas(op:ExpandedSyntheticGround,quotient_certificate:dict[str,Any],
                 atlas:dict[str,Any],*,deep:bool=True)->tuple[list[int],tuple]:
    require(type(atlas) is dict and set(atlas)=={
      'schema','source_ground','source_blob','expanded_ground','quotient_certificate',
      'microstate_count','dimension','field','coefficients','readouts','guarantee',
      'source_scope','digest'},'malformed atlas contract')
    require(atlas['digest']==hash_object({k:v for k,v in atlas.items() if k!='digest'}),
            'atlas content digest mismatch')
    part,columns=verify(op,quotient_certificate,replay_observations=deep)
    matrix=matrix_from_columns(columns,op.field)
    independent_full_matrix_proof(matrix,atlas['coefficients'],op.field)
    expected={k:v for k,v in prepare_atlas_identity(op,quotient_certificate,
                                                    atlas['coefficients'],len(columns)).items()}
    require(atlas==expected,'atlas source, observer, or semantic contract differs')
    return part,columns


def prepare_atlas_identity(op,cert,coeff,n):
    body={
      'schema':SCHEMA+'.certificate.v1','source_ground':op.source_fingerprint,
      'source_blob':op.source_blob,'expanded_ground':op.fingerprint,
      'quotient_certificate':cert['digest'],'microstate_count':op.n,
      'dimension':n,'field':op.field,'coefficients':coeff,
      'readouts':['class','linear','sum_squares','shear_pair'],
      'guarantee':'P M = Q P and q(Q)=0 for every initial vector and future tick',
      'source_scope':'synthetic expansion of observed connectome statistics, not biological dynamics',
    }
    return {**body,'digest':hash_object(body)}


def _project(part:list[int],n:int,terms:list,p:int)->list[int]:
    require(type(terms) is list and 1<=len(terms)<=MAX_SOURCES,'source mixture outside bounds')
    state=[0]*n
    for item in terms:
        require(type(item) is list and len(item)==2 and type(item[0]) is int and
                0<=item[0]<len(part) and type(item[1]) is int and
                0<=item[1]<p,'invalid typed microstate coefficient')
        state[part[item[0]]]=(state[part[item[0]]]+item[1])%p
    return state


def _step(columns:tuple,state:list[int],p:int)->list[int]:
    out=[0]*len(columns)
    for src,x in enumerate(state):
        if x:
            for dst,w in columns[src]:out[dst]=(out[dst]+x*w)%p
    return out


def _readout(state:list[int],intent:dict,p:int)->int:
    require(type(intent) is dict and type(intent.get('kind')) is str,
            'readout must be a typed object')
    kind=intent['kind'];n=len(state)
    if kind=='class':
        require(set(intent)=={'kind','index'} and type(intent['index']) is int and
                0<=intent['index']<n,'invalid class channel')
        return state[intent['index']]
    if kind=='linear':
        weights=intent.get('weights')
        require(set(intent)=={'kind','weights'} and type(weights) is list and len(weights)==n and
                all(type(v) is int and 0<=v<p for v in weights),'invalid linear observable')
        return sum(a*b for a,b in zip(weights,state))%p
    if kind=='sum_squares':
        indices=intent.get('indices')
        require(set(intent)=={'kind','indices'} and type(indices) is list and
                1<=len(indices)<=n and len(indices)==len(set(indices)) and
                all(type(v) is int and 0<=v<n for v in indices),'invalid squared observable')
        return sum(state[j]*state[j] for j in indices)%p
    if kind=='shear_pair':
        a,b=intent.get('left'),intent.get('right');gain=intent.get('gain')
        require(set(intent)=={'kind','left','right','gain'} and type(a) is int and
                type(b) is int and type(gain) is int and
                0<=a<n and 0<=b<n and a!=b and 0<gain<p,'invalid quadratic shear')
        return (state[a]+gain*state[b]*state[b])%p
    raise QuotientRefused('unsupported readout contract')


def execute_batch(op:ExpandedSyntheticGround,cert:dict,atlas:dict,
                  batch:list[dict[str,Any]],*,trusted:tuple|None=None)->dict[str,Any]:
    part,cols=trusted if trusted is not None else verify_atlas(op,cert,atlas,deep=True)
    p=op.field
    require(type(batch) is list and 1<=len(batch)<=MAX_QUERIES,
            'unbounded or empty batch')
    ticks={item.get('tick') for item in batch if type(item) is dict}
    require(len(ticks)==1,'one temporal polynomial per batch; mixed ticks refused')
    tick=next(iter(ticks))
    require(type(tick) is int and 0<=tick<=MAX_TICK,'invalid logical time')
    polynomial,products=quotient_power(tuple(atlas['coefficients']),p,tick)
    results=[]
    for item in batch:
        require(type(item) is dict and set(item)=={'sources','readout','tick'},
                'invalid query intention fields')
        current=_project(part,len(cols),item['sources'],p)
        accumulated=[0]*len(cols)
        for w in polynomial:
            if w:
                for j,value in enumerate(current):
                    accumulated[j]=(accumulated[j]+w*value)%p
            current=_step(cols,current,p)
        result=_readout(accumulated,item['readout'],p)
        results.append(result)
    body={
        'schema':SCHEMA+'.batch-observation.v1',
        'atlas_digest':atlas['digest'],
        'expanded_ground':op.fingerprint,
        'quotient_certificate':cert['digest'],
        'tick':tick,
        'batch_digest':hash_object(batch),
        'values':results,
        'query_count':len(batch),
        'polynomial_products':products,
        'intermediate_microstates_realized':0,
        'scope':'source-bound finite-field synthetic model; no transport authorization',
    }
    return {**body,'digest':hash_object(body)}


def verify_batch(op,cert,atlas,batch,received,*,trusted=None):
    require(type(received) is dict and received==execute_batch(op,cert,atlas,batch,trusted=trusted),
            'received multi-intention result disagrees with independently reconstructed Ground')
