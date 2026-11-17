"""PGT-001: supervised learning from synthetic Ground observation semantics.

Training source and labels are explicit finite mathematical worlds. The neural
model is ONLY an advisory candidate: exact IOS-001-style replay remains the
admission authority. HTTP location and model semantic identity are separate.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from typing import Iterable

import numpy as np

SCHEMA = "ifs.pgt001.intention-relative-ground-embedding.v1"
ACTIONS = tuple(f"measure-mask-{i}" for i in range(8)) + ("refuse",)
FEATURES = 3
EMBEDDING_SIZE = 20


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


@dataclass(frozen=True)
class World:
    """A finite Ground: states share public observation; target and features are declared."""
    features: tuple[tuple[int,int,int], ...]
    targets: tuple[int,...]
    costs: tuple[int,int,int]
    source_seed: int

    def __post_init__(self):
        if not (2 <= len(self.features) <= 64 and len(self.features) == len(self.targets)):
            raise ValueError("finite state table invalid")
        if any(len(row) != FEATURES or any(type(v) is not int or v not in (0,1) for v in row)
               for row in self.features):
            raise ValueError("features must be three exact Boolean observations")
        if any(type(t) is not int or t not in (0,1) for t in self.targets):
            raise ValueError("target must be an exact Boolean intention")
        if len(self.costs) != FEATURES or any(type(c) is not int or not 1 <= c <= 9 for c in self.costs):
            raise ValueError("costs must be bounded nonnegative integer symbols")

    def record(self):
        return {"schema":SCHEMA+".world","features":[list(x) for x in self.features],
                "targets":list(self.targets),"costs":list(self.costs),"source_seed":self.source_seed}


def exact_plan(world: World) -> int:
    """Independent finite-model oracle: enumerate all feature masks and prove sufficiency.

    This finite function has the same minimum (cost, feature-count, identifiers)
    policy as E-CPU IOS-001 plan_sufficiency, and is checked against native E-CPU in CI.
    It never infers from a fitted model.
    """
    best: tuple[int,int,tuple[int,...],int] | None = None
    for mask in range(8):
        chosen = tuple(i for i in range(FEATURES) if mask & (1 << i))
        seen = {}
        sufficient = True
        for row,target in zip(world.features,world.targets):
            key=tuple(row[i] for i in chosen)
            if key in seen and seen[key] != target:
                sufficient = False
                break
            seen[key] = target
        if sufficient:
            candidate=(sum(world.costs[i] for i in chosen), len(chosen), chosen,mask)
            if best is None or candidate<best:
                best=candidate
    return 8 if best is None else best[-1]


def encode(world:World) -> np.ndarray:
    """Observation-relative relational embedding, not a label or plan encoding.

    Each unordered state pair contributes only its target agreement and the mask
    of features capable of distinguishing the states. This is a 16-bin
    permutation-invariant description of candidate observation relationships.
    No optimal mask, sufficient-set flag or planner output appears here.
    """
    hist=np.zeros((2,8),dtype=np.float32)
    n=len(world.targets)
    for i in range(n):
        f,t=world.features[i],world.targets[i]
        for j in range(i+1,n):
            d=sum((f[k]^world.features[j][k])<<k for k in range(3))
            hist[int(t!=world.targets[j]),d]+=1
    hist=hist/(n*(n-1)/2)
    return np.concatenate((hist.reshape(-1), np.array(world.costs,dtype=np.float32)/9.,
                           np.array([float(n)/64],dtype=np.float32))).astype(np.float32)


def boolean_library(bits:tuple[int,...], extended:bool) -> tuple[int,...]:
    a,b,c,d=bits[:4]
    base=(a,b,c,d,a^b,b^c,a^c,a&b,a|b,b&c,a^b^c,1-a,1-b,1-c,0,1)
    if not extended:
        return base
    e=bits[4] if len(bits)>4 else d
    return base+(e,a^d,c^d,a^b^d,a&c,a|c,b^d,(a&b)^c)


def make_world(rng:np.random.Generator, identity:int, *, nstates:int=16,
               extended:bool=False, mode:int|None=None) -> World:
    """Generate worlds by composing Boolean observations and intentions.

    No source record or target label is retrieved from the Internet. The
    synthetic source is a finite exactly enumerable mathematical Ground.
    """
    if nstates not in (16,32):
        raise ValueError("only complete 4-/5-bit synthetic state-spaces are declared")
    width=4 if nstates==16 else 5
    raw=[tuple((k>>i)&1 for i in range(width)) for k in range(nstates)]
    columns=list(zip(*(boolean_library(b,extended) for b in raw)))
    feature_idx=rng.integers(0,len(columns),size=3)
    feat=[tuple(int(columns[int(k)][i]) for k in feature_idx) for i in range(nstates)]
    kind=int(rng.integers(0,8)) if mode is None else mode
    if kind==0:
        tar=[int(rng.integers(0,2))]*nstates
    elif kind in (1,2,3):
        j=int(rng.integers(0,3))
        tar=[row[j] for row in feat]
    elif kind in (4,5):
        i,j=sorted(rng.choice(3,2,replace=False).tolist())
        operation=int(rng.integers(0,3))
        tar=[(r[i]^r[j]) if operation==0 else ((r[i]&r[j]) if operation==1 else (r[i]|r[j])) for r in feat]
    elif kind==6:
        tar=[r[0]^r[1]^r[2] for r in feat]
    else:
        # A hidden distinction purposely beyond the offered three features.
        # May sometimes be recoverable through a correlated offered feature:
        # the exact oracle, not the generator's intent, assigns the label.
        bit=int(rng.integers(0,width))
        tar=[raw[i][bit]^feat[i][0] for i in range(nstates)]
    # Reorder the rows to prevent ordered-position memorization.
    perm=rng.permutation(nstates)
    costs=tuple(int(v) for v in rng.integers(1,7,size=3))
    return World(tuple(feat[int(i)] for i in perm),tuple(int(tar[int(i)]) for i in perm),
                 costs,identity)


def dataset(seed:int,n:int,*,nstates:int=16,extended:bool=False):
    rng=np.random.default_rng(seed)
    x=np.empty((n,EMBEDDING_SIZE),dtype=np.float32)
    y=np.empty((n,),dtype=np.int64)
    ids=[]
    for i in range(n):
        w=make_world(rng,seed*10000000+i,nstates=nstates,extended=extended)
        x[i]=encode(w)
        y[i]=exact_plan(w)
        ids.append(sha(w.record()))
    return x,y,ids


def can_resolve(world:World,mask:int) -> bool:
    """A verifier for a model proposal, using rows, not teacher labels."""
    if mask==8:
        return True # Absent features imply conservative abstention.
    if not 0<=mask<=7:
        return False
    selected=tuple(i for i in range(3) if mask & (1<<i))
    seen={}
    for features,t in zip(world.features,world.targets):
        key=tuple(features[i] for i in selected)
        if key in seen and seen[key]!=t:
            return False
        seen[key]=t
    return True
