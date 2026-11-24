"""CIG-033A: cross-Ground Seed activation via signed local projections.
Discovery is budgeted and incomplete; only an independent bridge admits use.
"""
from itertools import permutations, product
from temporal_algebra import Diagram, Budget
from adaptive_seed import Work
from verify_temporal_ground import digest


def cycles(pred):
    succ={i:j for j,i in enumerate(pred)};seen=set();out=[]
    for i in range(len(pred)):
        if i in seen:continue
        c=[];j=i
        while j not in seen:seen.add(j);c.append(j);j=succ[j]
        out.append(c)
    return out


def symbol(code,w,i):return (code>>(w*i))&((1<<w)-1)


def candidate_tables(w,v):
    for perm in permutations(range(v),w):
        for mask in range(1<<w):
            yield tuple(sum(((x>>j&1)^(mask>>i&1))<<i for i,j in enumerate(perm)) for x in range(1<<v))


def align_cycle(old,new,c,z,ports,tables,work):
    """Search a ring of finite domains by keyed successor compatibility."""
    ow,nw=old.w,new.w;oa,na=old.a,new.a
    options=[];lookup=[];out=[]
    for i,j in zip(c,z):
        # Port hints are discovery constraints, not verification authority.
        relevant=[(ob,nb,flip) for oi,ob,nj,nb,flip in ports if oi==i and nj==j]
        if any(oi==i and nj!=j for oi,ob,nj,nb,flip in ports):return None
        a,b=symbol(old.initial,ow,i),symbol(new.initial,nw,j)
        work.charge(len(tables)*na)
        opts=[h for h in tables if h[b]==a and all(all((h[x]>>ob&1)==((x>>nb&1)^flip) for x in range(na)) for ob,nb,flip in relevant)]
        if not opts:return None
        options.append(opts)
        f=new.g['tables'][j];g=old.g['tables'][i];d={}
        for h in opts:d.setdefault(tuple(h[y] for y in f),[]).append(h)
        lookup.append(d);out.append(g)
    for h0 in options[0]:
        paths={h0:[h0]}
        for s in range(1,len(c)):
            nxt={}
            for h,path in paths.items():
                work.charge(na)
                key=tuple(out[s][x] for x in h)
                for hh in lookup[s].get(key,()):
                    work.charge();nxt.setdefault(hh,path+[hh])
            paths=nxt
            if not paths:break
        for h,path in paths.items():
            work.charge(na)
            if tuple(h0[y] for y in new.g['tables'][z[0]])==tuple(out[0][x] for x in h):return path
    return None


def circuit_diagram(d,rec,output,align=None,maps=None):
    """Full-cube output proof using local-symbol variables, not temporal residues."""
    c=rec.circuit;k=rec.k;w=rec.w;root=c['outputs'][output];live={abs(root)}
    for i in range(k+1+len(c['gates']),k+1,-1):
        if i in live:live.update(map(abs,c['gates'][i-k-2][1:]))
    refs={1:1,-1:0}
    def get(x):
        if x not in refs:refs[x]=d.apply('not',refs[-x])
        return refs[x]
    for i in sorted(live):
        if i==1:continue
        if i<=k+1:
            j,b=divmod(i-2,w)
            if align is None:refs[i]=d.node(j,[(x>>b)&1 for x in range(rec.a)])
            else:refs[i]=d.node(align[j],[(x>>b)&1 for x in maps[j]])
        else:
            op,a,b=c['gates'][i-k-2];refs[i]=d.apply(op,get(a),get(b))
    r=get(root)
    return r,[[i,refs[i]] for i in sorted(refs)]


def discover(old,new,old_output,new_output,*,ports=(),max_work=4_000_000,diagram_work=2_000_000):
    """Return one candidate or UNKNOWN, never a proof of impossibility.
    Ports: (old block, old bit, new block, new bit, invert). They may be sparse.
    Unmatched new cycles are allowed. Each old cycle maps to a distinct new one.
    """
    work=Work(max_work)
    if not old.total_image or not new.total_image:raise ValueError('total source image required')
    if old.w>new.w:return dict(status='UNKNOWN',reason='projection grammar width',work=0,attempts=0)
    if type(diagram_work)is not int or diagram_work<1:raise ValueError('diagram budget')
    if not (type(old_output)is int and 0<=old_output<len(old.circuit['outputs']) and type(new_output)is int and 0<=new_output<len(new.circuit['outputs'])):raise ValueError('output')
    ports=tuple(ports);m=len(old.g['pred']);n=len(new.g['pred'])
    if any(len(p)!=5 or any(type(x)is not int for x in p) or not (0<=p[0]<m and 0<=p[1]<old.w and 0<=p[2]<n and 0<=p[3]<new.w and p[4] in (0,1)) for p in ports):raise ValueError('ports')
    a=[None]*m;h=[None]*m;used=set();attempts=0
    try:
        ts=list(candidate_tables(old.w,new.w));work.charge(len(ts)*new.a)
        newcycles=cycles(new.g['pred'])
        # Prioritize semantically pinned rings before unconstrained rings.
        for c in sorted(cycles(old.g['pred']),key=lambda c:(-sum(p[0] in c for p in ports),len(c),c[0])):
            found=False
            for z0 in newcycles:
                if len(z0)!=len(c) or z0[0] in used:continue
                for r in range(len(z0)):
                    work.charge();z=z0[r:]+z0[:r]
                    if any(p[0] in c and z[c.index(p[0])]!=p[2] for p in ports):continue
                    attempts+=1;hs=align_cycle(old,new,c,z,ports,ts,work)
                    if hs is None:continue
                    for i,j,f in zip(c,z,hs):a[i]=j;h[i]=list(f)
                    used.add(z0[0]);found=True;break
                if found:break
            if not found:return dict(status='UNKNOWN',reason='mapping',work=work.used,attempts=attempts)
        d=Diagram([new.a]*n,diagram_work)
        x,orfs=circuit_diagram(d,old,old_output,a,h);y,nrfs=circuit_diagram(d,new,new_output)
        if x!=y:return dict(status='UNKNOWN',reason='output compatibility',work=work.used,attempts=attempts,diagram_work=d.work)
        proof=dict(schema='ifs.cig033.bridge.v1',old=old.key,new=new.key,old_initial=str(old.initial),new_initial=str(new.initial),old_output=old_output,new_output=new_output,align=a,maps=h,nodes=[[j,list(k)] for j,k in d.nodes],old_refs=orfs,new_refs=nrfs)
        return dict(status='FOUND',proof=proof,work=work.used,attempts=attempts,diagram_work=d.work)
    except (Budget,RecursionError):return dict(status='UNKNOWN',reason='budget',work=work.used,attempts=attempts)
