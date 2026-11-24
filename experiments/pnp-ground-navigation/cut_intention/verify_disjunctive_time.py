"""Independent receiver: verify interval exclusion and an AND/OR cover.

Checks the submitted expansion order, not the producer's search heuristic.
The terminal witness and lower bounds of ALL remaining alternatives prove
minimality. No imports from the CIG-023 producer.
"""
import json
from math import gcd,lcm
from verify_temporal_ground import Receiver,read_code


def verify(receiver,targets,start,r,*,max_cells=2_000_000,max_pairs=200_000,max_nodes=50_000,interval_steps=16):
    try:
        if type(receiver)is not Receiver or not receiver.total_image:return False
        k,w,a,g,c,initial=receiver.k,receiver.w,receiver.a,receiver.g,receiver.circuit,receiver.initial
        if not read_code(initial,k) or type(start)is not int or start<0 or start.bit_length()>4096:return False
        if type(targets)is not list or len(targets)!=len(c['outputs']) or any(b is not None and (type(b)is not int or b not in (0,1)) for b in targets):return False
        if any(type(v)is not int or v<1 for v in (max_cells,max_pairs,max_nodes)) or type(interval_steps)is not int or interval_steps<0:return False
        if r['status'] not in ('FOUND','UNREACHABLE'):return False
        if type(r['trace'])is not list or type(r['leaps'])is not list or len(r['trace'])+len(r['leaps'])>max_nodes or len(r['leaps'])>interval_steps:return False
        def same(x,y):return json.dumps(x,sort_keys=True,separators=(',',':'))==json.dumps(y,sort_keys=True,separators=(',',':'))
        vertices=[i*a+initial//2**(i*w)%a for i in range(k//w)];depth=g['depth'];D=max(depth[v] for v in vertices);lo=max(start,D)
        ex=dict(schema='ifs.cig023.disjunctive-time.v1',key=receiver.key,initial=str(initial),targets=targets[:],start=str(start),transient=D,status='UNKNOWN',local_cells=0,pairs=0,nodes=0,leaps=[],trace=[])
        def pos(v,t):
            if t<depth[v]:
                for _ in range(t):v=receiver.edges[v]
                return v
            cy,j=receiver.pos[g['entry'][v]];return cy[(j+t-depth[v])%len(cy)]
        def code_at(blocks,t):
            code=0
            for i in blocks:
                j,b=divmod(pos(vertices[i],t),a);code+=b*2**(j*w)
            return code
        def reads(code):
            vals={1:1,**{i+2:code//2**i%2 for i in range(k)}}
            def value(v):return vals[v] if v>0 else 1-vals[-v]
            for j,(op,x,y) in enumerate(c['gates'],k+2):vals[j]=min(value(x),value(y)) if op=='and' else max(value(x),value(y))
            return value
        def finish(t):
            return t.bit_length()<=4096 and receiver.accept(t,r['terminal']) and all(b is None or b==v for b,v in zip(targets,r['terminal']['outputs'])) and same(r,ex|dict(status='FOUND',time=str(t),terminal=r['terminal']))
        def unreachable():return same(r,ex|dict(status='UNREACHABLE'))
        for t in range(start,D):
            ex['local_cells']+=1+len(vertices)+len(c['gates'])
            if ex['local_cells']>max_cells:return False
            value=reads(code_at(range(len(vertices)),t))
            if all(b is None or b==value(v) for v,b in zip(c['outputs'],targets)):return finish(t)
        def norm(seq):
            a=set(seq)-{1}
            return None if -1 in a or a.intersection(-x for x in a) else tuple(sorted(a))
        roots=norm(v if b==1 else -v for v,b in zip(c['outputs'],targets) if b is not None)
        if roots is None:return unreachable()
        # Independent dependency and spatial-cycle reconstruction.
        live=set(map(abs,roots))
        for j in reversed(range(k+2,k+2+len(c['gates']))):
            if j in live:live.update(abs(x) for x in c['gates'][j-k-2][1:])
        bits={i-2 for i in live if 2<=i<=k+1};forward={i:j for j,i in enumerate(g['pred'])};pending=set(range(len(vertices)));groups=[]
        while pending:
            i=min(pending);z=set()
            while i not in z:z.add(i);i=forward[i]
            pending-=z;groups.append(sorted(z))
        atom={};P=1
        for z in groups:
            selected=sorted(i for i in bits if i//w in z)
            if not selected:continue
            L=lcm(*(len(receiver.pos[g['entry'][vertices[i]]][0]) for i in z));P=lcm(P,L)
            ex['local_cells']+=L*(len(z)+len(selected))
            if ex['local_cells']>max_cells:return False
            yes={i:set() for i in selected};no={i:set() for i in selected}
            for phase in range(L):
                code=code_at(z,D+phase)
                for i in selected:(yes if code//2**i%2 else no)[i].add((D+phase)%L)
            for i in selected:atom[i+2]=(L,yes[i]);atom[-i-2]=(L,no[i])
        horizon=lo+P
        # min/max lower bounds, computed by direct modular minimization rather
        # than producer's binary searches. Positive/negative gate duals.
        def bound(t):
            b={1:t,-1:float("inf")}
            for v,(L,S) in atom.items():b[v]=min((t+(x-t)%L for x in S),default=float("inf"))
            for j,(op,x,y) in enumerate(c['gates'],k+2):
                if j in live:
                    b[j]=max(b[x],b[y]) if op=='and' else min(b[x],b[y]);b[-j]=min(b[-x],b[-y]) if op=='and' else max(b[-x],b[-y])
            return max([t]+[b[v] for v in roots])
        # Infinity is separately tracked to enforce the exact submitted marker.
        for submitted in r['leaps']:
            ex['nodes']+=1
            if ex['nodes']>max_nodes:return False
            impossible={-1}|{v for v,(_,S) in atom.items() if not S}
            for j,(op,x,y) in enumerate(c['gates'],k+2):
                if j not in live:continue
                a0,b0=x in impossible,y in impossible;a1,b1=-x in impossible,-y in impossible
                if (a0 or b0) if op=='and' else (a0 and b0):impossible.add(j)
                if (a1 and b1) if op=='and' else (a1 or b1):impossible.add(-j)
            b=None if any(v in impossible for v in roots) else bound(lo)
            expected=None if b is None else str(b-lo)
            if submitted!=expected:return False
            ex['leaps'].append(expected)
            if b is None or b>=horizon:return unreachable()
            if b==lo:return finish(lo)
            lo=b
        if len(ex['leaps'])!=interval_steps:return False
        # Verify the submitted cover: every active state is an entire congruence
        # class plus outstanding conjuncts. Expanding it preserves their union.
        states=[];seen=set();active=set()
        def add(x,m,roots):
            if roots is None or lo+(x-lo)%m>=horizon:return
            state=(x,m,roots)
            if state not in seen:
                seen.add(state);active.add(len(states));states.append(state)
        add(0,1,roots)
        for row in r['trace']:
            if type(row)is not list or len(row)!=2 or any(type(x)is not int for x in row):return False
            i,v=row
            if i not in active:return False
            active.remove(i);x,m,p=states[i]
            if v not in p:return False
            ex['nodes']+=1;ex['trace'].append(row);rest=tuple(z for z in p if z!=v)
            if abs(v)<=k+1:
                L,S=atom[v];ex['pairs']+=len(S)
                if ex['pairs']>max_pairs:return False
                d=gcd(m,L);q=L//d;joint=m*q
                for y in sorted(S):
                    if (y-x)%d:continue
                    t=0 if q==1 else ((y-x)//d)*pow(m//d,-1,q)%q
                    add((x+m*t)%joint,joint,rest)
            else:
                op,u,z=c['gates'][abs(v)-k-2]
                if v<0:u,z=-u,-z
                if (op=='and' and v>0) or (op=='or' and v<0):add(x,m,norm(rest+(u,z)))
                else:
                    add(x,m,norm(rest+(u,)));add(x,m,norm(rest+(z,)))
            if len(states)>max_nodes or ex['nodes']>max_nodes:return False
        if not active:return unreachable()
        # No need to trust the queue ordering. Check every unexpanded region's
        # lower bound; the separate terminal receiver establishes attainment.
        t=min(lo+(states[i][0]-lo)%states[i][1] for i in active)
        ex['nodes']+=1
        return ex['nodes']<=max_nodes and finish(t)
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False
