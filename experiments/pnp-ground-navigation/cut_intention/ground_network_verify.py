"""Independent semantic qualification and path replay for ground_network.

No producer discovery, rank, planner or view-membership method is called.
"""
from collections import deque
from math import prod
try:
    from .ground_network import View, Edge, Route, MAX_BITS
except ImportError:
    from ground_network import View, Edge, Route, MAX_BITS


def _int(x,lo=None):
    return type(x) is int and x.bit_length()<=MAX_BITS and (lo is None or x>=lo)


def _bit(v,t):
    if t<v.cutoff: return (v.prefix//(2**t))%2
    root=v.root
    while root>1:
        j,children=v.nodes[root-2]; root=children[t%v.base[j]]
    return root


def _count_rank(v,t,charge):
    if t<=v.cutoff:
        charge(t)
        return sum((v.prefix>>j)&1 for j in range(t))
    total=sum((v.prefix>>j)&1 for j in range(v.cutoff)); charge(v.cutoff)
    # Rebuild period count from independent suffix multiplicities.
    vals=[0,1]; levels=[len(v.base)]*2
    for j,kids in v.nodes:
        charge(len(kids)); vals.append(sum(vals[x]*prod(v.base[j+1:levels[x]]) for x in kids)); levels.append(j)
    P=prod(v.base); whole,rem=divmod(t-v.cutoff,P)
    total+=whole*vals[v.root]*prod(v.base[:levels[v.root]])
    if not rem: return total
    lo=v.cutoff; hi=lo+rem; q=deque([(v.root,0,1)])
    while q:
        x,r,m=q.popleft(); charge(1)
        count=(hi-1-r)//m-(lo-1-r)//m
        if x==0 or count==0: continue
        if x==1: total+=count; continue
        j,kids=v.nodes[x-2]; b=v.base[j]; charge(b)
        # Independent CRT form: lift the new residue into old congruence.
        inv=pow(b,-1,m) if m>1 else 0
        for a,z in enumerate(kids):
            if z: q.append((z,a+b*((r-a)*inv%m),b*m))
    return total


def verify_edge(views,e,*,max_work=500_000):
    try:
        if type(e) is not Edge or not _int(max_work,1) or not _int(e.shift) or not _int(e.start,0) or not _int(e.start+e.shift,0) or not all(_int(x,0) for x in (e.source_before,e.target_before,e.cost)):
            return False
        a,b=views[e.source],views[e.target]
        if type(a) is not View or type(b) is not View or a.key!=e.source or b.key!=e.target: return False
        used=0
        def charge(n):
            nonlocal used
            used+=n
            if used>max_work: raise ValueError('budget')
        cutoff=max(e.start,b.cutoff,a.cutoff-e.shift)
        if not _int(cutoff+e.shift,0):return False
        charge(cutoff-e.start)
        if any(_bit(a,t+e.shift)!=_bit(b,t) for t in range(e.start,cutoff)):return False
        # Walk prime coordinates in order, memoizing successful subrelations.
        def factors(base):
            out=[]
            for n in base:
                p=2
                while n%p:p+=1
                out.append(p)
            return out
        ap,bp=factors(a.base),factors(b.base); primes=sorted(set(ap+bp)); memo=set()
        def check(x,y,i):
            if (x,y,i) in memo:return True
            charge(1)
            if x<2 and y<2:return x==y
            if i==len(primes):return False
            p=primes[i]; j=ap.index(p) if p in ap else -1; k=bp.index(p) if p in bp else -1
            aa=a.nodes[x-2][1] if x>=2 and a.nodes[x-2][0]==j else (x,)
            bb=b.nodes[y-2][1] if y>=2 and b.nodes[y-2][0]==k else (y,)
            n=max(len(aa),len(bb)); charge(n)
            for r in range(n):
                if not check(aa[(r+e.shift)%len(aa)],bb[r%len(bb)],i+1):return False
            memo.add((x,y,i)); return True
        if not check(a.root,b.root,0): return False
        return _count_rank(a,e.start+e.shift,charge)==e.source_before and _count_rank(b,e.start,charge)==e.target_before
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError):return False


def replay(network,target,k,route,*,max_hops=64):
    """Independently reconstruct translated ordinal and shift from admitted edges.
    Cost is deliberately not a mathematical assertion; it is a planner estimate.
    """
    try:
        if type(route) is not Route or not _int(k,1) or route.target!=target or type(route.ordinal) is not int or route.ordinal!=k or type(route.edges) is not tuple or len(route.edges)>max_hops or target not in network.views:return None
        node=target; q=k; shift=0; chain=[]; edges=network.edges
        for eid in route.edges:
            e=edges[eid]
            if e.target!=node or q<=e.target_before:return None
            q=q-e.target_before+e.source_before;shift+=e.shift;node=e.source
            if not _int(q,1) or not _int(shift):return None
            chain.append(e)
        if (route.source,route.source_ordinal,route.shift)!=(node,q,shift) or type(route.source_ordinal) is not int or type(route.shift) is not int:return None
        return node,q,tuple(chain)
    except (TypeError,ValueError,KeyError,IndexError):return None


def lift_time(network,target,k,route,source_time):
    """Translate an independently qualified *source* ordinal witness.
    This does not itself qualify the source ordinal. The caller must do so.
    """
    r=replay(network,target,k,route)
    if r is None or not _int(source_time,0):return None
    t=source_time; views=network.views
    for e in reversed(r[2]):
        t-=e.shift
        if not _int(t,0) or t<e.start or _bit(views[e.target],t)!=1:return None
    return t if _bit(views[target],t)==1 else None


def verify_selection(view,k,t,*,max_work=500_000):
    """Native endpoint proof for bounded exact ranks (no external authority)."""
    try:
        if type(view) is not View or not _int(k,1) or not _int(t,0) or not _int(max_work,1):return False
        used=0
        def charge(n):
            nonlocal used
            used+=n
            if used>max_work:raise ValueError('budget')
        return _bit(view,t)==1 and _count_rank(view,t,charge)==k-1
    except (ValueError,TypeError,KeyError,IndexError,OverflowError):return False


def verify_realization(network,target,k,route,source_time,*,max_work=500_000):
    """Self-contained native endpoint check and path transfer."""
    path=replay(network,target,k,route)
    if path is None or not verify_selection(network.views[path[0]],path[1],source_time,max_work=max_work):return None
    return lift_time(network,target,k,route,source_time)


def verify_composite(network,edge,path):
    """Independent pairwise proof replay, using no source rank or MDD evaluation."""
    try:
        if type(edge) is not Edge or type(path) is not tuple or not 2<=len(path)<=64 or not _int(edge.cost,0):return False
        edges=network.edges; first=edges[path[0]]; source=first.source; target=first.target
        dt=first.shift; start=first.start; src=first.source_before; dst=first.target_before
        for eid in path[1:]:
            nxt=edges[eid]
            if nxt.target!=source:return False
            old_offset=src-dst
            if start+dt<nxt.start:
                start=nxt.start-dt;dst=nxt.target_before-old_offset;src=nxt.target_before
            src=src+nxt.source_before-nxt.target_before
            dt+=nxt.shift;source=nxt.source
        if not all(_int(x,0) for x in (start,src,dst,start+dt)) or not _int(dt):return False
        if not all(type(x) is int for x in (edge.shift,edge.start,edge.source_before,edge.target_before)):return False
        return (edge.source,edge.target,edge.shift,edge.start,edge.source_before,edge.target_before)==(source,target,dt,start,src,dst)
    except (KeyError,TypeError,ValueError,IndexError):return False
