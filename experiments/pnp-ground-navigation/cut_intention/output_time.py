"""CIG-022: exact inverse time for a proof-derived Boolean output intention.

Split mandatory AND (including negated OR) requirements, form periodic
factors on the spatial cycles in each remaining circuit cone, then join
absolute time residues. Budget failure is UNKNOWN, not unreachability.
"""
from math import lcm
from inverse_time import spatial_groups, merge
from temporal_ground import contract_code, contract_time
from shared_proof import evaluate

SCHEMA = 'ifs.cig022.output-time.v1'


def target_contract(circuit, targets):
    if type(targets) is not list or len(targets) != len(circuit['outputs']) or any(x is not None and (type(x) is not int or x not in (0,1)) for x in targets):
        raise ValueError('output intention')
    if any(r is None for r in circuit['outputs']):
        raise ValueError('incomplete decoder')


def mandatory(circuit, k, targets):
    """Signed references that must all be true. Do not split disjunctions."""
    pending=[r if b else -r for r,b in zip(circuit['outputs'],targets) if b is not None]
    done=set();out=set()
    while pending:
        r=pending.pop()
        if r in done:continue
        done.add(r)
        if abs(r)>k+1:
            op,a,b=circuit['gates'][abs(r)-k-2]
            if r>0 and op=='and':pending.extend((a,b));continue
            if r<0 and op=='or':pending.extend((-a,-b));continue
        if r!=1:out.add(r)
    return sorted(out)


def cone(circuit,k,root):
    todo=[abs(root)];seen=set();inputs=set();gates=set()
    while todo:
        r=todo.pop()
        if r in seen:continue
        seen.add(r)
        if 2<=r<=k+1:inputs.add(r-2)
        elif r>k+1:
            gates.add(r);todo.extend(map(abs,circuit['gates'][r-k-2][1:]))
    return inputs,sorted(gates)


def seek_outputs(nav,initial,targets,start=0,*,max_cells=2_000_000,max_pairs=200_000,grouped=True):
    k,w,a,g,c=nav.k,nav.w,nav.a,nav.g,nav.decoder['circuit']
    contract_code(initial,k);contract_time(start);target_contract(c,targets)
    if type(grouped)is not bool or any(type(x)is not int or x<1 for x in (max_cells,max_pairs)):raise ValueError('budget/mode')
    vertices=[i*a+((initial>>(i*w))&(a-1)) for i in range(k//w)]
    D=max(g['depth'][v] for v in vertices)
    r=dict(schema=SCHEMA,key=nav.key,initial=str(initial),targets=targets[:],start=str(start),grouped=grouped,transient=D,local_cells=0,pairs=0,factors=[],status='UNKNOWN')
    def finish(t,method):
        if t.bit_length()>4096:return r
        return r|dict(status='FOUND',method=method,time=str(t),terminal=nav.result(initial,t))
    for t in range(start,D):
        r['local_cells']+=1+len(vertices)+len(c['gates'])
        if r['local_cells']>max_cells:return r
        out=evaluate(c,nav.jump(initial,t),k)
        if all(b is None or b==v for b,v in zip(targets,out)):return finish(t,'transient')
    groups=spatial_groups(g['pred']);owner={i:j for j,z in enumerate(groups) for i in z}
    periods=[lcm(*(len(nav.pos[g['entry'][vertices[i]]][0]) for i in z)) for z in groups]
    anchor=nav.jump(initial,D)
    batches={}
    for root in mandatory(c,k,targets):
        ins,gates=cone(c,k,root);gs=tuple(sorted({owner[i//w] for i in ins}));key=(gs,None if grouped else root)
        batch=batches.setdefault(key,([],set(),set()));batch[0].append(root);batch[1].update(ins);batch[2].update(gates)
    for (gs,_),(roots,ins,gate_set) in sorted(batches.items(),key=lambda item:item[1][0]):
        gates=sorted(gate_set);blocks=sorted(i for j in gs for i in groups[j]);L=lcm(*(periods[j] for j in gs))
        cost=L*(len(roots)+len(blocks)+len(gates)+len(ins));r['local_cells']+=cost
        if r['local_cells']>max_cells:return r
        local={i:(anchor>>(i*w))&(a-1) for i in blocks};allowed=[]
        for t in range(L):
            vals={1:True,**{i+2:bool(local[i//w]>>(i%w)&1) for i in ins}}
            def read(v):return vals[abs(v)] if v>0 else not vals[-v]
            for j in gates:
                op,x,y=c['gates'][j-k-2];vals[j]=read(x) and read(y) if op=='and' else read(x) or read(y)
            if all(read(root) for root in roots):allowed.append((D+t)%L)
            local={j:g['tables'][j][local[g['pred'][j]]] for j in blocks}
        r['factors'].append(dict(roots=roots,groups=list(gs),period=L,residues=sorted(allowed)))
    # Avoid expanding universal factors. Prefer restrictive factors first.
    R={0};M=1
    for f in sorted(r['factors'],key=lambda f:(len(f['residues']),f['period'],f['roots'])):
        S=f['residues'];L=f['period']
        if len(S)==L:continue
        r['pairs']+=len(R)*len(S)
        if r['pairs']>max_pairs:return r
        R={v for x in R for y in S if (v:=merge(x,M,y,L)) is not None};M=lcm(M,L)
        if not R:break
    r.update(method='periodic',modulus=str(M),residues=list(map(str,sorted(R))))
    if not R:return r|dict(status='UNREACHABLE')
    lo=max(start,D);return finish(min(lo+(x-lo)%M for x in R),'periodic')
