"""CIG-021 inverse temporal navigation: partial code targets, exact residue join.
The finite local periods are covered, not the full joint temporal period.
UNKNOWN denotes exhausted local or CRT budgets, never unreachability.
"""
from math import lcm,gcd
from temporal_ground import contract_code,contract_time


def spatial_groups(pred):
    seen=set();out=[]
    for i in range(len(pred)):
        if i in seen:continue
        c=[];j=i
        while j not in seen:c.append(j);seen.add(j);j=pred[j]
        out.append(sorted(c))
    return out


def merge(a,m,b,n):
    d=gcd(m,n)
    if (b-a)%d:return None
    q=n//d
    return (a+m*((b-a)//d*pow(m//d,-1,q)%q))%lcm(m,n) if q>1 else a%lcm(m,n)


def seek(nav,initial,mask,value,start=0,*,max_local=2_000_000,max_pairs=200_000):
    k,w,a=nav.k,nav.w,nav.a
    for x in (initial,mask,value):contract_code(x,k)
    contract_time(start)
    if value&~mask or any(type(x)is not int or x<1 for x in (max_local,max_pairs)):raise ValueError('target/budget')
    g=nav.g;vertices=[i*a+((initial>>(i*w))&(a-1)) for i in range(k//w)];D=max(g['depth'][v] for v in vertices)
    r=dict(schema='ifs.cig021.seek.v1',ground=g['key'],initial=str(initial),mask=str(mask),value=str(value),start=str(start),transient=D,groups=[],status='UNKNOWN',local_steps=0,pairs=0)
    for t in range(start,D):
        r['local_steps']+=len(vertices)
        if r['local_steps']>max_local:return r
        if nav.jump(initial,t)&mask==value:return r|dict(status='FOUND',time=str(t),method='transient')
    anchor=nav.jump(initial,D);mod=1;residues={0}
    for group in spatial_groups(g['pred']):
        gm=sum(((mask>>(i*w))&(a-1))<<(i*w) for i in group)
        if gm==0:continue
        L=lcm(*(len(nav.pos[g['entry'][vertices[i]]][0]) for i in group));local={i:(anchor>>(i*w))&(a-1) for i in group};allowed=[]
        r['local_steps']+=L*len(group)
        if r['local_steps']>max_local:return r
        for dt in range(L):
            if all((local[i]&((mask>>(i*w))&(a-1)))==((value>>(i*w))&(a-1)) for i in group):allowed.append((D+dt)%L)
            local={j:g['tables'][j][local[g['pred'][j]]] for j in group}
        allowed.sort();r['groups'].append(dict(blocks=group,period=L,residues=allowed));r['pairs']+=len(residues)*len(allowed)
        if r['pairs']>max_pairs:return r
        nxt={z for x in residues for y in allowed if (z:=merge(x,mod,y,L)) is not None};mod=lcm(mod,L);residues=nxt
        if not residues:return r|dict(status='UNREACHABLE',method='periodic',modulus=str(mod),residues=[])
    lower=max(start,D)
    t=min(lower+(x-lower)%mod for x in residues)
    if t.bit_length()>4096:return r
    return r|dict(status='FOUND',method='periodic',modulus=str(mod),residues=list(map(str,sorted(residues))),time=str(t))
