"""Independent CIG-021 inverse check using graph positions, not local simulation."""
from math import gcd,lcm
from verify_temporal_ground import verify_transport,read_code


def verify_seek(source,k,w,g,initial,mask,value,start,r,*,max_local=2_000_000,max_pairs=200_000):
    try:
        if not verify_transport(source,k,w,g) or not all(read_code(x,k) for x in (initial,mask,value)) or value&~mask or type(start)is not int or start<0 or start.bit_length()>4096:return False
        if any(type(x)is not int or x<1 for x in (max_local,max_pairs)):return False
        if r['schema']!='ifs.cig021.seek.v1' or r['ground']!=g['key'] or [r[x] for x in ('initial','mask','value','start')]!=list(map(str,(initial,mask,value,start))):return False
        a=2**w;m=k//w;v=[i*a+(initial//2**(i*w))%a for i in range(m)];d=g['depth'];D=max(d[x] for x in v)
        if type(r['transient'])is not int or r['transient']!=D:return False
        pos={x:(c,j) for c in g['cycles'] for j,x in enumerate(c)};edges={i*a+b:j*a+g['tables'][j][b] for j,i in enumerate(g['pred']) for b in range(a)}
        def at(x,t):
            if t<d[x]:
                for _ in range(t):x=edges[x]
                return x
            c,j=pos[g['entry'][x]];return c[(j+t-d[x])%len(c)]
        def packed(indices,t):
            code=0
            for i in indices:
                j,b=divmod(at(v[i],t),a);code+=b*2**(j*w)
            return code
        local=0;pairs=0
        for t in range(start,D):
            local+=m
            if local>max_local:return False
            if packed(range(m),t)&mask==value:
                return r['status']=='FOUND' and r['method']=='transient' and r['time']==str(t) and r['groups']==[] and r['local_steps']==local and r['pairs']==0
        pending=set(range(m));groups=[];R={0};M=1
        while pending:
            # Independent cycle discovery by forward destination mapping.
            j=min(pending);c=set();forward={p:i for i,p in enumerate(g['pred'])}
            while j not in c:c.add(j);j=forward[j]
            pending-=c;gm=sum(mask&( (a-1)<<(i*w)) for i in c)
            if not gm:continue
            L=lcm(*(len(pos[g['entry'][v[i]]][0]) for i in c));local+=L*len(c)
            if local>max_local:return False
            S=sorted((D+t)%L for t in range(L) if packed(c,D+t)&gm==value&gm)
            groups.append(dict(blocks=sorted(c),period=L,residues=S));pairs+=len(R)*len(S)
            if pairs>max_pairs:return False
            d0=gcd(M,L);joint=lcm(M,L);new=set()
            for x in R:
                for y in S:
                    if (y-x)%d0:continue
                    # Solve x+M*j=y mod L via extended modular arithmetic.
                    q=L//d0;j=0 if q==1 else ((y-x)//d0)*pow(M//d0,-1,q)%q;new.add((x+M*j)%joint)
            M,R=joint,new
            if not R:break
        if r['groups']!=groups or r['method']!='periodic' or r['local_steps']!=local or r['pairs']!=pairs or r['modulus']!=str(M) or r['residues']!=list(map(str,sorted(R))):return False
        if not R:return r['status']=='UNREACHABLE' and 'time' not in r
        lo=max(start,D);t=min(lo+(x-lo)%M for x in R)
        return t.bit_length()<=4096 and r['status']=='FOUND' and r['time']==str(t) and packed(range(m),t)&mask==value
    except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError):return False
