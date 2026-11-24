"""CIG-023: interval exclusion and lazy AND/OR CRT proof search.

A completed receipt covers every earlier time, not just a witness. Budget
exhaustion is UNKNOWN. The receiver independently reconstructs the coverage.
"""
from bisect import bisect_left
from heapq import heappush, heappop
from math import lcm
from inverse_time import spatial_groups, merge
from temporal_ground import contract_code, contract_time
from output_time import target_contract

SCHEMA='ifs.cig023.disjunctive-time.v1'


def normalize(roots):
    s=set(roots);s.discard(1)
    return None if -1 in s or any(-x in s for x in s) else tuple(sorted(s))


def seek(nav, initial, targets, start=0, *, max_cells=2_000_000, max_pairs=200_000, max_nodes=50_000, interval_steps=16, telemetry=None):
    k,w,a,g,c=nav.k,nav.w,nav.a,nav.g,nav.decoder['circuit']
    contract_code(initial,k);contract_time(start);target_contract(c,targets)
    if any(type(v)is not int or v<1 for v in (max_cells,max_pairs,max_nodes)) or type(interval_steps)is not int or interval_steps<0:raise ValueError('budget')
    if telemetry is not None:
        telemetry.clear();telemetry.update(point_evals=0,point_gate_evals=0,point_input_reads=0)
    vertices=[i*a+((initial>>(i*w))&(a-1)) for i in range(k//w)]
    D=max(g['depth'][v] for v in vertices);lo=max(start,D)
    r=dict(schema=SCHEMA,key=nav.key,initial=str(initial),targets=targets[:],start=str(start),transient=D,status='UNKNOWN',local_cells=0,pairs=0,nodes=0,leaps=[],trace=[])
    def finish(t):
        if t.bit_length()>4096:return r
        return r|dict(status='FOUND',time=str(t),terminal=nav.result(initial,t))
    # Explicit finite transient scan, charged before evaluation.
    for t in range(start,D):
        r['local_cells']+=1+len(vertices)+len(c['gates'])
        if r['local_cells']>max_cells:return r
        out=nav.result(initial,t)['outputs']
        if all(b is None or b==v for b,v in zip(targets,out)):return finish(t)
    roots=normalize(v if b else -v for v,b in zip(c['outputs'],targets) if b is not None)
    if roots is None:return r|dict(status='UNREACHABLE')
    # Only bits in the requested circuit cones require local tables.
    live=set(map(abs,roots))
    for j in range(k+1+len(c['gates']),k+1,-1):
        if j in live:live.update(map(abs,c['gates'][j-k-2][1:]))
    bits=sorted(x-2 for x in live if 2<=x<=k+1)
    groups=spatial_groups(g['pred']);owner={i:j for j,z in enumerate(groups) for i in z}
    periods=[lcm(*(len(nav.pos[g['entry'][vertices[i]]][0]) for i in z)) for z in groups]
    anchor=nav.jump(initial,D);atom={};P=1
    for j in sorted({owner[i//w] for i in bits}):
        z=groups[j];L=periods[j];P=lcm(P,L);selected=[i for i in bits if owner[i//w]==j]
        r['local_cells']+=L*(len(z)+len(selected))
        if r['local_cells']>max_cells:return r
        local={i:(anchor>>(i*w))&(a-1) for i in z};yes={i:[] for i in selected};no={i:[] for i in selected}
        for dt in range(L):
            for i in selected:(yes if local[i//w]>>(i%w)&1 else no)[i].append((D+dt)%L)
            local={i:g['tables'][i][local[g['pred'][i]]] for i in z}
        for i in selected:atom[i+2]=(L,sorted(yes[i]));atom[-i-2]=(L,sorted(no[i]))
    horizon=lo+P # one period of every relevant atom suffices
    def next_atom(v,t):
        L,S=atom[v]
        if not S:return None
        q,b=divmod(t,L);i=bisect_left(S,b)
        return q*L+S[i] if i<len(S) else (q+1)*L+S[0]
    def gate_bound(t):
        # None = infinity. Dual bounds for positive and negative references.
        b={1:t,-1:None}
        for v in atom:b[v]=next_atom(v,t)
        def AND(x,y):return None if x is None or y is None else max(x,y)
        def OR(x,y):return y if x is None else x if y is None else min(x,y)
        for j,(op,x,y) in enumerate(c['gates'],k+2):
            if j in live:
                b[j]=(AND if op=='and' else OR)(b[x],b[y]);b[-j]=(OR if op=='and' else AND)(b[-x],b[-y])
        out=t
        for v in roots:out=AND(out,b[v])
        return out
    for _ in range(interval_steps):
        r['nodes']+=1
        if r['nodes']>max_nodes:return r
        b=gate_bound(lo);r['leaps'].append(None if b is None else str(b-lo))
        if b is None or b>=horizon:return r|dict(status='UNREACHABLE')
        if b==lo:return finish(lo)
        lo=b
    # Lazy cover of the residual time interval: disjunction creates alternative
    # obligations, conjunction adds both, signed atom intersects a local period.
    queue=[];states=[];seen=set()
    def add(x,m,pending):
        if pending is None:return
        lower=lo+(x-lo)%m
        if lower>=horizon:return
        state=(x,m,pending)
        if state in seen:return
        seen.add(state);i=len(states);states.append(state);heappush(queue,(lower,len(pending),i))
    add(0,1,roots)
    last_t=None;vals={}
    while queue:
        t,_,i=heappop(queue);x,m,pending=states[i];r['nodes']+=1
        if r['nodes']>max_nodes:return r
        if t.bit_length()>4096:return r
        def read(v):return vals[abs(v)] if v>0 else not vals[-v]
        if t!=last_t:
            # Every live input already has a qualified periodic table. The
            # search need not reconstruct unrelated symbols or gates, and
            # consecutive queue states often share the same lower time.
            last_t=t;vals={1:True}
            for j in bits:
                L,S=atom[j+2];phase=t%L;idx=bisect_left(S,phase)
                vals[j+2]=idx<len(S) and S[idx]==phase
            for j,(op,u,v) in enumerate(c['gates'],k+2):
                if j in live:vals[j]=read(u) and read(v) if op=='and' else read(u) or read(v)
            if telemetry is not None:
                telemetry['point_evals']+=1;telemetry['point_gate_evals']+=len(live)-len(bits)-int(1 in live);telemetry['point_input_reads']+=len(bits)
        false=[v for v in pending if not read(v)]
        if not false:return finish(t)
        # Prefer sparse atomic restrictions; then conjunctions, then disjunctions.
        def rank(v):
            if abs(v)<=k+1:return (0,len(atom[v][1]) if v in atom else 0,abs(v))
            op=c['gates'][abs(v)-k-2][0];return (1 if (op=='and')==(v>0) else 2,0,-abs(v))
        v=min(false,key=rank);r['trace'].append([i,v]);rest=tuple(z for z in pending if z!=v)
        if abs(v)<=k+1:
            L,S=atom[v];r['pairs']+=len(S)
            if r['pairs']>max_pairs:return r
            for y in S:
                b=merge(x,m,y,L)
                if b is not None:add(b,lcm(m,L),rest)
        else:
            op,u,z=c['gates'][abs(v)-k-2];conj=(op=='and')==(v>0)
            if v<0:u,z=-u,-z
            if conj:add(x,m,normalize((*rest,u,z)))
            else:
                add(x,m,normalize((*rest,u)));add(x,m,normalize((*rest,z)))
        # Charge generated states too, to bound the retained frontier.
        if len(states)>max_nodes:return r
    return r|dict(status='UNREACHABLE')
