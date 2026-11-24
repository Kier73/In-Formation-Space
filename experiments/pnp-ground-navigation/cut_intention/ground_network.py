"""Exact ultimately-periodic observation Grounds and costed knowledge routes.

A Ground here is a mathematical observation language, not a claim of external
source provenance. Adapters must qualify that provenance before registration.
Edges point from the requested target to a reusable source. Costs are declared
nonnegative estimates; only admitted mathematical relations authorize transfer.
"""
from dataclasses import dataclass, field
from hashlib import sha256
from heapq import heappop, heappush
from itertools import count
from math import prod
import json

MAX_BITS = 4096
MAX_ARCS = 2_000_000

class Exhausted(ValueError):
    """Declared work budget exceeded, not a mathematical obstruction."""


def integer(v, lower=None):
    if type(v) is not int or v.bit_length() > MAX_BITS or (lower is not None and v < lower):
        raise ValueError('integer contract')
    return v


def digest(v):
    return sha256(json.dumps(v, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def prime_power(n):
    p = 2
    while p*p <= n and n % p:
        p += 1
    if p*p > n:
        return n
    while n % p == 0:
        n //= p
    if n != 1:
        raise ValueError('not a prime power')
    return p


class Work:
    def __init__(self, limit):
        self.limit = integer(limit, 1)
        self.used = 0
    def charge(self, n=1):
        self.used += n
        if self.used > self.limit:
            raise Exhausted('work budget')


@dataclass(frozen=True)
class View:
    source: str
    base: tuple
    nodes: tuple
    root: int
    cutoff: int = 0
    prefix: int = 0
    primes: tuple = field(init=False)
    period: int = field(init=False)
    total: int = field(init=False)
    key: str = field(init=False)

    def __post_init__(self):
        if type(self.source) is not str or not self.source or len(self.source) > 1024:
            raise ValueError('source identity')
        if type(self.base) is not tuple or len(self.base) > 256 or any(type(b) is not int or not 2 <= b <= 4096 for b in self.base):
            raise ValueError('CRT basis')
        primes = tuple(prime_power(b) for b in self.base)
        if tuple(sorted(set(primes))) != primes:
            raise ValueError('ordered coprime prime powers')
        integer(self.cutoff, 0); integer(self.prefix, 0)
        if self.cutoff > 4096 or self.prefix.bit_length() > self.cutoff:
            raise ValueError('prefix contract')
        if type(self.nodes) is not tuple or len(self.nodes) > MAX_ARCS:
            raise ValueError('nodes')
        arcs = 0; levels = [len(self.base)]*2; counts = [0,1]; unique = set()
        tails = [prod(self.base[j:]) for j in range(len(self.base)+1)]
        integer(tails[0], 1)
        for idx, row in enumerate(self.nodes, 2):
            if type(row) is not tuple or len(row) != 2:
                raise ValueError('node')
            j, kids = row
            if type(j) is not int or not 0 <= j < len(self.base) or type(kids) is not tuple or len(kids) != self.base[j]:
                raise ValueError('node shape')
            arcs += len(kids)
            if arcs > MAX_ARCS or any(type(k) is not int or not 0 <= k < idx or levels[k] <= j for k in kids):
                raise ValueError('node order/budget')
            if len(set(kids)) < 2 or row in unique:
                raise ValueError('unreduced node')
            unique.add(row); levels.append(j)
            counts.append(sum(counts[k]*(tails[j+1]//tails[levels[k]]) for k in kids))
        if type(self.root) is not int or not 0 <= self.root < len(levels):
            raise ValueError('root')
        object.__setattr__(self,'primes',primes)
        object.__setattr__(self,'period',tails[0])
        object.__setattr__(self,'total',counts[self.root]*(tails[0]//tails[levels[self.root]]))
        object.__setattr__(self,'key',digest(['temporal-view.v1',self.source,self.base,self.nodes,self.root,self.cutoff,str(self.prefix)]))

    def bit(self,t):
        integer(t,0)
        if t < self.cutoff:
            return (self.prefix >> t) & 1
        x = self.root
        while x >= 2:
            j,kids = self.nodes[x-2]; x = kids[t % self.base[j]]
        return x

    def rank(self,t,work=None):
        """Exclusive chronological rank using complete periods and CRT cover."""
        integer(t,0); work = Work(MAX_ARCS) if work is None else work
        if t <= self.cutoff:
            return (self.prefix & ((1<<t)-1)).bit_count()
        q, rem = divmod(t-self.cutoff,self.period)
        out = self.prefix.bit_count()+q*self.total
        if not rem:
            return out
        lo, hi = self.cutoff, self.cutoff+rem
        todo = [(self.root,0,1)]
        while todo:
            x,r,m = todo.pop(); work.charge()
            first = lo+(r-lo)%m
            if x == 0 or first >= hi:
                continue
            if x == 1:
                out += 1+(hi-1-first)//m; continue
            j,kids = self.nodes[x-2]; b = self.base[j]; inv = pow(m,-1,b)
            work.charge(b)
            todo.extend((z,r+m*((a-r)*inv%b),m*b) for a,z in enumerate(kids) if z)
        return out


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    shift: int
    start: int
    source_before: int
    target_before: int
    cost: int = 1
    @property
    def offset(self):
        return self.source_before-self.target_before
    @property
    def key(self):
        return digest(['temporal-edge.v1',self.source,self.target,str(self.shift),str(self.start),str(self.source_before),str(self.target_before),str(self.cost)])


def equal_suffix(source,target,shift,start,work):
    """Propose target(t)=source(t+shift) on t>=start, in common CRT space."""
    integer(shift); integer(start,0); integer(start+shift,0)
    cutoff=max(start,target.cutoff,source.cutoff-shift)
    integer(cutoff+shift,0)
    work.charge(cutoff-start)
    for t in range(start,cutoff):
        if source.bit(t+shift) != target.bit(t):
            return False
    todo=[(source.root,target.root)]; seen=set()
    while todo:
        a,b=todo.pop()
        if (a,b) in seen: continue
        seen.add((a,b)); work.charge()
        if a<2 and b<2:
            if a!=b: return False
            continue
        p=source.primes[source.nodes[a-2][0]] if a>=2 else float('inf')
        q=target.primes[target.nodes[b-2][0]] if b>=2 else float('inf')
        r=min(p,q)
        ak=source.nodes[a-2][1] if p==r else (a,)
        bk=target.nodes[b-2][1] if q==r else (b,)
        n=max(len(ak),len(bk)); work.charge(n)
        todo.extend((ak[(x+shift)%len(ak)],bk[x%len(bk)]) for x in range(n))
    return True


def discover(source,target,candidates,*,cost=1,max_work=500_000):
    """Try explicit (shift,start) grammar; failure is UNKNOWN, not no bridge."""
    integer(cost,0); work=Work(max_work); candidates=tuple(candidates)
    if len(candidates)>64: raise ValueError('candidate budget')
    try:
        for shift,start in candidates:
            work.charge()
            if equal_suffix(source,target,shift,start,work):
                s=source.rank(start+shift,work); t=target.rank(start,work)
                return Edge(source.key,target.key,shift,start,s,t,cost),work.used
    except Exhausted:
        pass
    return None,work.used


@dataclass(frozen=True)
class Route:
    target: str
    ordinal: int
    edges: tuple
    source: str
    source_ordinal: int
    shift: int
    cost: int


class Network:
    """Local registry of immutable views and independently verified edges."""
    def __init__(self):
        self._views={}; self._edges={}; self._incoming={}; self._origins={}
    @property
    def views(self): return dict(self._views)
    @property
    def edges(self): return dict(self._edges)
    @property
    def origins(self): return dict(self._origins)
    def register(self,view):
        if type(view) is not View: raise ValueError('view')
        self._views[view.key]=view
        return view.key
    def admit(self,edge,*,max_work=500_000):
        # Local import permits the separate checker to import only value types.
        try:
            from .ground_network_verify import verify_edge
        except ImportError:
            from ground_network_verify import verify_edge
        if type(edge) is not Edge or not verify_edge(self._views,edge,max_work=max_work):
            return False
        return self._insert(edge,())
    def _insert(self,edge,path):
        if edge.key not in self._edges:
            self._edges[edge.key]=edge
            self._origins[edge.key]=path
            self._incoming.setdefault(edge.target,[]).append(edge.key)
        return True
    def admit_composite(self,edge,path):
        """Qualify a new edge by transitivity of already admitted edges."""
        try:
            from .ground_network_verify import verify_composite
        except ImportError:
            from ground_network_verify import verify_composite
        if not verify_composite(self,edge,path):return False
        return self._insert(edge,path)
    def plan(self,target,ordinal,offer,*,max_hops=8,max_states=10000):
        """Least declared cost among bounded walks if search completes.

        offer(node, translated_ordinal) -> nonnegative estimated cost or None.
        It must be a stable, side-effect-free estimate within a plan call.
        Returns (route or None, expanded states). No route is UNKNOWN.
        """
        integer(ordinal,1); integer(max_states,1); integer(max_hops,0)
        if target not in self._views or max_hops>64: raise ValueError('route contract')
        serial=count(); queue=[(0,next(serial),False,target,ordinal,0,())]; best={}; expanded=0; pushed=1
        while queue:
            c,_,done,node,k,shift,path=heappop(queue)
            if done: return Route(target,ordinal,path,node,k,shift,c),expanded
            sig=node,k,shift,len(path)
            if sig in best and best[sig]<=c: continue
            best[sig]=c; expanded+=1
            if expanded>max_states: return None,expanded
            quote=offer(node,k)
            if quote is not None:
                integer(quote,0); pushed+=1
                heappush(queue,(c+quote,next(serial),True,node,k,shift,path))
            if len(path)>=max_hops: continue
            for eid in sorted(self._incoming.get(node,())):
                e=self._edges[eid]
                if k<=e.target_before: continue
                j=k+e.offset; dt=shift+e.shift
                if j<1 or j.bit_length()>MAX_BITS or dt.bit_length()>MAX_BITS: continue
                pushed+=1
                if pushed>max_states*4: return None,expanded
                heappush(queue,(c+e.cost,next(serial),False,e.source,j,dt,path+(eid,)))
        return None,expanded


def select(view,k,*,max_work=500_000):
    """Native exact ordinal selection, or UNKNOWN on charged budget exhaustion.

    Full periods are skipped arithmetically. Partial rank evaluation uses CRT
    cover, so a dense irregular language can still require substantial work.
    """
    integer(k,1); work=Work(max_work); before=view.prefix.bit_count()
    if k<=before:
        z=view.prefix
        for _ in range(k-1):z&=z-1
        return {'status':'FOUND','time':(z&-z).bit_length()-1,'work':0}
    if not view.total:return {'status':'UNREACHABLE','time':None,'work':0}
    q,j=divmod(k-before-1,view.total); j+=1
    lo,hi=0,view.period
    try:
        while hi-lo>1:
            mid=(lo+hi)//2;work.charge()
            if view.rank(view.cutoff+mid,work)-before>=j:hi=mid
            else:lo=mid
        t=view.cutoff+q*view.period+hi-1
        integer(t,0)
        return {'status':'FOUND','time':t,'work':work.used}
    except (Exhausted,ValueError):
        return {'status':'UNKNOWN','time':None,'work':work.used}


def compose(network,path,*,cost=1):
    """Propose a retained path summary; the checker replays pairwise composition.

    Each edge is oriented from target to reusable source. The largest
    translated cutoff is active. Its admitted prefix rank gives the composite
    prefix rank without a fresh rank computation or endpoint diagram traversal.
    """
    integer(cost,0)
    if type(path) is not tuple or not 2<=len(path)<=64:raise ValueError('path')
    edges=network.edges; first=edges[path[0]]; node=first.target; shift=offset=0
    active=None
    for key in path:
        e=edges[key]
        if e.target!=node:raise ValueError('path order')
        candidate=(e.start-shift,e.target_before-offset)
        if active is None or candidate[0]>active[0]:active=candidate
        shift+=e.shift;offset+=e.offset;node=e.source
    start,before=active
    for x in (start,before,before+offset,start+shift):integer(x,0)
    integer(shift)
    return Edge(node,first.target,shift,start,before+offset,before,cost)
