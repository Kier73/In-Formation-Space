"""Discover a matching Ground from CNF alone; produce Hall obstruction or model.
Disjoint positive demands and complete pairwise exclusion components suffice.
Extra constraints never invalidate a Hall refutation; SAT witnesses check all.
"""
from collections import deque
from itertools import combinations


def normalize(clauses,n):
    if type(n) is not int or not 1<=n<=8192 or not isinstance(clauses,(list,tuple)) or len(clauses)>300000:
        raise ValueError('bounded CNF expected')
    rows=set()
    for r in clauses:
        if not isinstance(r,(list,tuple)) or len(r)>128 or any(type(v) is not int or not 1<=abs(v)<=n for v in r):
            raise ValueError('invalid source clause')
        c=set(r)
        if not any(-v in c for v in c):rows.add(tuple(sorted(c)))
    return sorted(rows,key=lambda r:(len(r),r))


def accepts(rows,x):
    return all(any(bool(x&(1<<(abs(l)-1)))==(l>0) for l in r) for r in rows)


def compile_hall(clauses,n):
    rows=normalize(clauses,n)
    demands=[r for r in rows if r and all(v>0 for v in r)]
    used=set()
    for r in demands:
        if used.intersection(r):return {'status':'UNKNOWN','reason':'overlapping demands'}
        used.update(r)
    if not demands:return {'status':'UNKNOWN','reason':'no positive demand'}
    graph={v:set() for v in used}
    for r in rows:
        if len(r)==2 and all(v<0 and -v in used for v in r):
            a,b=map(abs,r);graph[a].add(b);graph[b].add(a)
    groups=[];pending=set(used)
    while pending:
        first=min(pending);stack=[first];pending.remove(first);part={first}
        while stack:
            for v in graph[stack.pop()] & pending:
                pending.remove(v);part.add(v);stack.append(v)
        if any(len(graph[v])!=len(part)-1 for v in part):return {'status':'UNKNOWN','reason':'non-clique exclusion component'}
        groups.append(sorted(part))
    owner={v:i for i,g in enumerate(groups) for v in g}
    edges=[sorted({owner[v] for v in r}) for r in demands]
    match={};left={};scans=0
    for root in range(len(demands)):
        parent={root:None};q=deque([root]);seen_right=set();end=None
        while q and end is None:
            u=q.popleft()
            for v in edges[u]:
                scans+=1
                if v in seen_right:continue
                seen_right.add(v)
                if v not in match:end=(u,v);break
                w=match[v]
                if w not in parent:parent[w]=(u,v);q.append(w)
        if end is None:
            subset=sorted(parent);neighbors=sorted({v for u in subset for v in edges[u]})
            assert len(neighbors)<len(subset)
            chosen=set(v for u in subset for v in demands[u])
            return {'status':'UNSAT','demands':[list(demands[u]) for u in subset],
                    'exclusions':[sorted(chosen.intersection(groups[v])) for v in neighbors],
                    'edge_scans':scans}
        u,v=end
        while True:
            match[v]=u;left[u]=v
            if parent[u] is None:break
            u,v=parent[u]
    witness=sum(1<<(next(v for v in demands[u] if owner[v]==h)-1) for u,h in left.items())
    if accepts(rows,witness):return {'status':'SAT','witness':str(witness),'edge_scans':scans}
    return {'status':'UNKNOWN','reason':'matching does not satisfy additional clauses','edge_scans':scans}


def verify_hall(clauses,n,receipt):
    """Check the small source proof, without matching or discovery."""
    try:
        if type(n) is not int or not 1<=n<=8192 or not isinstance(clauses,(list,tuple)) or len(clauses)>300000:return False
        source=set()
        for r in clauses:
            if not isinstance(r,(list,tuple)) or len(r)>128 or any(type(l) is not int or not 1<=abs(l)<=n for l in r):return False
            source.add(frozenset(r))
        if receipt['status']=='SAT':
            x=int(receipt['witness']);return 0<=x<1<<n and all(any(bool(x&(1<<(abs(l)-1)))==(l>0) for l in r) for r in source)
        if receipt['status']!='UNSAT':return False
        ds=receipt['demands'];gs=receipt['exclusions']
        if not 0<=len(gs)<len(ds) or any(not r for r in ds+gs):return False
        flat=[v for r in ds for v in r];other=[v for r in gs for v in r]
        if any(type(v) is not int or not 1<=v<=n for v in flat+other):return False
        if len(flat)!=len(set(flat)) or sorted(flat)!=sorted(other):return False
        if any(frozenset(r) not in source for r in ds):return False
        return all(frozenset((-a,-b)) in source for r in gs for a,b in combinations(r,2))
    except (ValueError,TypeError,KeyError,IndexError):return False
