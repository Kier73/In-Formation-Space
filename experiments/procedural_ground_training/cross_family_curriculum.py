"""PGT-002: finite mathematical families with partial observation and exact held-out teachers.

The model's input is only a bounded subset of each source Ground. Full-source
labels and counterexamples are held by a separate teacher and never pass to
its encoder at inference. A complete source table is an EXPERIMENTAL reference,
not an authority claim about arbitrary external Grounds.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

import numpy as np

from procedural_ground_training import World, canonical, encode, exact_plan, can_resolve, make_world

FAMILIES = ("boolean", "affine_orbit", "http_path", "finite_automaton")
TRAIN_FAMILIES = FAMILIES[:-1]


def _bits(x: int, width: int) -> tuple[int, ...]:
    return tuple((x >> j) & 1 for j in range(width))


def _affine_jump(a: int, c: int, mod: int, x: int, tick: int) -> int:
    """Independent affine transform composition using O(log tick) modular arithmetic."""
    p, q, u, v = 1, 0, a % mod, c % mod
    while tick:
        if tick & 1:
            p, q = (u * p) % mod, (u * q + v) % mod
        u, v = (u * u) % mod, (u * v + v) % mod
        tick >>= 1
    return (p*x + q) % mod


def _finite_jump(transition: tuple[int, ...], state: int, tick: int) -> int:
    """Finite functional graph: follow only the preperiod and a single cycle."""
    seen: dict[int, int] = {}
    orbit = []
    while state not in seen:
        seen[state] = len(orbit)
        orbit.append(state)
        state = transition[state]
    mu, lam = seen[state], len(orbit)-seen[state]
    return orbit[tick] if tick < len(orbit) else orbit[mu+(tick-mu)%lam]


def _boolean_op(i: int, j: int, k: int, mode: int) -> int:
    if mode == 0: return i ^ j
    if mode == 1: return i & j
    if mode == 2: return i | j
    if mode == 3: return i ^ j ^ k
    if mode == 4: return (i | j) & k
    if mode == 5: return i
    if mode == 6: return j
    return int(not (i & j))


def world_for(family: str, rng: np.random.Generator, ident: int, nstates: int) -> World:
    if family not in FAMILIES or nstates not in (16,32):
        raise ValueError("unsupported Ground family or size")
    if family == "boolean":
        return make_world(rng, ident, nstates=nstates, extended=nstates==32)
    bits = 4 if nstates==16 else 5
    states = np.arange(nstates)
    costs = tuple(int(v) for v in rng.integers(1,8,size=3))
    # All source names, orderings, and numeric values stay source-relative.
    if family == "affine_orbit":
        a = int(rng.choice(np.arange(1,nstates,2)))
        c = int(rng.integers(0,nstates))
        steps = [int(rng.integers(0,20)) for _ in range(3)]
        proj_bits = [int(rng.integers(0,bits)) for _ in range(3)]
        feats = [tuple((_affine_jump(a,c,nstates,int(x),steps[k])>>proj_bits[k])&1
                       for k in range(3)) for x in states]
        horizon = 10**15 + int(rng.integers(0,1000))
        target_bit = int(rng.integers(0,bits))
        targets=[(_affine_jump(a,c,nstates,int(x),horizon)>>target_bit)&1 for x in states]
        # A mix of exact observation sufficiency and unavailable hidden distinctions.
        mode=int(rng.integers(0,6))
        if mode==0: targets=[f[0] for f in feats]
        elif mode==1: targets=[f[0]^f[1] for f in feats]
        elif mode==2: targets=[f[0]&f[2] for f in feats]
        elif mode==3: targets=[1 for _ in states]
    elif family == "http_path":
        # This is a *modeled* finite retrieval Ground, not a live HTTP source.
        # Bits: origin-A reachable, origin-B reachable, digest intact,
        # policy permits reads, and optional cache-presence.
        latent=[_bits(int(x),bits) for x in states]
        origin_a=[row[0] for row in latent]
        origin_b=[row[1] for row in latent]
        digest_ok=[row[2] for row in latent]
        permitted=[row[3] for row in latent]
        cache=[row[4] if bits==5 else 0 for row in latent]
        projections=[origin_a,origin_b,digest_ok,permitted,cache,
                     [a|b for a,b in zip(origin_a,origin_b)],
                     [a&d for a,d in zip(origin_a,digest_ok)],
                     [a|b|c for a,b,c in zip(origin_a,origin_b,cache)]]
        chosen=rng.integers(0,len(projections),size=3)
        feats=[tuple(int(projections[int(chosen[k])][i]) for k in range(3)) for i in range(nstates)]
        mode=int(rng.integers(0,7))
        if mode==0:
            targets=[int(bool((origin_a[i] or origin_b[i] or cache[i]) and digest_ok[i] and permitted[i])) for i in range(nstates)]
        elif mode==1: targets=[int((origin_a[i] or origin_b[i]) and digest_ok[i]) for i in range(nstates)]
        elif mode==2: targets=[f[0] for f in feats]
        elif mode==3: targets=[f[0]^f[1] for f in feats]
        elif mode==4: targets=[f[0]&f[2] for f in feats]
        elif mode==5: targets=[1]*nstates
        else: targets=[int(digest_ok[i]&permitted[i]) for i in range(nstates)]
    else:
        # Unseen training family: random finite state transition graph with
        # time-delayed binary observers. Its target is a later observation.
        permutation = [int(z) for z in rng.permutation(nstates)]
        # For some instances introduce branches/mergers, not only cycles.
        if int(rng.integers(0,2)):
            for _ in range(nstates//5):
                permutation[int(rng.integers(0,nstates))]=int(rng.integers(0,nstates))
        transition=tuple(permutation)
        offsets=[int(rng.integers(0,2*nstates)) for _ in range(3)]
        masks=[int(rng.integers(0,bits)) for _ in range(3)]
        feats=[tuple((_finite_jump(transition,int(x),offsets[k])>>masks[k])&1 for k in range(3)) for x in states]
        horizon=10**12+int(rng.integers(0,3000))
        target_bit=int(rng.integers(0,bits))
        targets=[(_finite_jump(transition,int(x),horizon)>>target_bit)&1 for x in states]
        mode=int(rng.integers(0,6))
        if mode==0: targets=[f[0] for f in feats]
        elif mode==1: targets=[f[0]^f[1] for f in feats]
        elif mode==2: targets=[f[0]|f[2] for f in feats]
        elif mode==3: targets=[1]*nstates
    order = rng.permutation(nstates)
    return World(tuple(feats[int(i)] for i in order),tuple(int(targets[int(i)]) for i in order),costs,ident)


def partial(world: World, indices: Sequence[int]) -> World:
    selected=tuple(int(i) for i in indices)
    if len(set(selected))!=len(selected) or not 2<=len(selected)<=len(world.targets):
        raise ValueError("invalid or repeated source state samples")
    if any(i<0 or i>=len(world.targets) for i in selected):
        raise ValueError("source state coordinate out of bounds")
    return World(tuple(world.features[i] for i in selected),tuple(world.targets[i] for i in selected),world.costs,world.source_seed)


def sample_observations(world: World, rng: np.random.Generator, size: int) -> tuple[World, tuple[int,...]]:
    if not 2<=size<=len(world.targets):
        raise ValueError("invalid observation budget")
    selected=tuple(int(x) for x in rng.choice(len(world.targets),size=size,replace=False))
    return partial(world,selected),selected


def world_digest(world: World) -> str:
    """Row-order independent semantic identity excluding instance/split ID."""
    facts=sorted((list(f),int(y)) for f,y in zip(world.features,world.targets))
    return hashlib.sha256(canonical({"facts":facts,"costs":list(world.costs)})).hexdigest()


def build_examples(seed: int, total: int, *, families: tuple[str,...], nstates: int,
                   observed: int | tuple[int,int], excluded: set[str] | None = None) -> tuple[np.ndarray,np.ndarray,np.ndarray,list[str]]:
    rng=np.random.default_rng(seed)
    inp=np.zeros((total,20),dtype=np.float32)
    labels=np.zeros(total,dtype=np.int64)
    partial_labels=np.zeros(total,dtype=np.int64)
    digests=[]
    seen = excluded if excluded is not None else set()
    for i in range(total):
        family=families[i%len(families)]
        for attempt in range(200):
            w=world_for(family,rng,seed*10**7+i+attempt*10**9,nstates)
            key=world_digest(w)
            if key not in seen:
                seen.add(key)
                break
        else:
            raise RuntimeError("duplicate-free semantic Ground exhausted")
        k=int(rng.integers(observed[0],observed[1]+1)) if isinstance(observed,tuple) else observed
        view,_=sample_observations(w,rng,k)
        inp[i]=encode(view)
        labels[i]=exact_plan(w)
        partial_labels[i]=exact_plan(view)
        digests.append(key)
    return inp,labels,partial_labels,digests


def proposed_action_status(full: World, action:int) -> str:
    if action==8:
        return "abstained" if exact_plan(full)!=8 else "correct_refusal"
    return "sufficient" if can_resolve(full,action) else "insufficient"


def counterexample(full: World, mask: int) -> tuple[int,int] | None:
    """An independent complete-domain checker returns a failing state pair."""
    if not 0<=mask<=7:
        return None
    seen:dict[tuple[int,...],tuple[int,int]]={}
    chosen=tuple(i for i in range(3) if mask&(1<<i))
    for i,(f,t) in enumerate(zip(full.features,full.targets)):
        signature=tuple(f[k] for k in chosen)
        existing=seen.get(signature)
        if existing is not None and existing[1]!=t:
            return existing[0],i
        seen.setdefault(signature,(i,t))
    return None
