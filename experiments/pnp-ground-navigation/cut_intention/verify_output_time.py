"""Independent output-time replay using the admitted CIG-021 receiver.

The receiver independently admits original decoder proof, transport CNF and
universal source section. Reconstruct mandatory circuit factors via reverse
traversal, evaluate local residues from certified graph positions, and check
all CRT classes and earliest time. No imports from the CIG-022 producer.
"""
import json
from math import gcd,lcm
from verify_temporal_ground import Receiver,read_code


def verify_output_seek(receiver,targets,start,r,*,max_cells=2_000_000,max_pairs=200_000,grouped=True):
    try:
        if type(receiver)is not Receiver or not receiver.total_image:return False
        k,w,a,g,c,initial=receiver.k,receiver.w,receiver.a,receiver.g,receiver.circuit,receiver.initial
        if type(targets)is not list or len(targets)!=len(c['outputs']) or any(b is not None and (type(b)is not int or b not in (0,1)) for b in targets):return False
        if type(grouped)is not bool or not read_code(initial,k) or type(start)is not int or start<0 or start.bit_length()>4096 or any(type(v)is not int or v<1 for v in (max_cells,max_pairs)):return False
        if r['status'] not in ('FOUND','UNREACHABLE'):return False
        vertices=[i*a+initial//2**(i*w)%a for i in range(k//w)];depth=g['depth'];D=max(depth[v] for v in vertices)
        def position(v,t):
            if t<depth[v]:
                for _ in range(t):v=receiver.edges[v]
                return v
            cy,i=receiver.pos[g['entry'][v]];return cy[(i+t-depth[v])%len(cy)]
        def code_at(blocks,t):
            code=0
            for i in blocks:
                j,b=divmod(position(vertices[i],t),a);code+=b*2**(j*w)
            return code
        def gate_values(code,gates):
            vals={1:1}
            def read(v):
                x=abs(v);b=vals[x] if x in vals else code//2**(x-2)%2
                return b if v>0 else 1-b
            for j in gates:
                op,x,y=c['gates'][j-k-2];vals[j]=min(read(x),read(y)) if op=='and' else max(read(x),read(y))
            return read
        expected=dict(schema='ifs.cig022.output-time.v1',key=receiver.key,initial=str(initial),targets=targets[:],start=str(start),grouped=grouped,transient=D,local_cells=0,pairs=0,factors=[],status='UNKNOWN')
        def equal(x,y):return json.dumps(x,sort_keys=True,separators=(',',':'))==json.dumps(y,sort_keys=True,separators=(',',':'))
        def finish(t,method):
            if t.bit_length()>4096:return False
            z=r['terminal']
            if not receiver.accept(t,z) or not all(b is None or b==v for b,v in zip(targets,z['outputs'])):return False
            return equal(r,expected|dict(status='FOUND',method=method,time=str(t),terminal=z))
        for t in range(start,D):
            expected['local_cells']+=1+len(vertices)+len(c['gates'])
            if expected['local_cells']>max_cells:return False
            read=gate_values(code_at(range(len(vertices)),t),range(k+2,k+2+len(c['gates'])))
            if all(b is None or read(v)==b for v,b in zip(c['outputs'],targets)):return finish(t,'transient')
        # Reverse-topological decomposition of the conjunction of desired outputs.
        needed={v if b else -v for v,b in zip(c['outputs'],targets) if b is not None}
        for j in range(k+1+len(c['gates']),k+1,-1):
            op,x,y=c['gates'][j-k-2]
            if op=='and' and j in needed:needed.remove(j);needed.update((x,y))
            if op=='or' and -j in needed:needed.remove(-j);needed.update((-x,-y))
        needed.discard(1)
        # Independent cycle discovery via the forward block permutation.
        pending=set(range(len(vertices)));forward={i:j for j,i in enumerate(g['pred'])};groups=[]
        while pending:
            j=min(pending);z=set()
            while j not in z:z.add(j);j=forward[j]
            pending-=z;groups.append(sorted(z))
        owners={i:j for j,z in enumerate(groups) for i in z}
        periods=[lcm(*(len(receiver.pos[g['entry'][vertices[i]]][0]) for i in z)) for z in groups]
        batches={}
        for root in sorted(needed):
            live={abs(root)};used=[]
            for j in range(abs(root),k+1,-1):
                if j in live:used.append(j);live.update(map(abs,c['gates'][j-k-2][1:]))
            bits={x-2 for x in live if 2<=x<=k+1};gs=tuple(sorted({owners[i//w] for i in bits}));key=(gs,None if grouped else root)
            roots,inputs,gate_set=batches.setdefault(key,([],set(),set()));roots.append(root);inputs.update(bits);gate_set.update(used)
        for (gs,_),(roots,bits,used) in sorted(batches.items(),key=lambda item:item[1][0]):
            blocks=[i for j in gs for i in groups[j]];L=lcm(*(periods[j] for j in gs))
            expected['local_cells']+=L*(len(roots)+len(blocks)+len(used)+len(bits))
            if expected['local_cells']>max_cells:return False
            S=[]
            for dt in range(L):
                read=gate_values(code_at(blocks,D+dt),sorted(used))
                if all(read(root) for root in roots):S.append((D+dt)%L)
            expected['factors'].append(dict(roots=roots,groups=list(gs),period=L,residues=sorted(S)))
        M,R=1,{0}
        for f in sorted(expected['factors'],key=lambda f:(len(f['residues']),f['period'],f['roots'])):
            L,S=f['period'],f['residues']
            if len(S)==L:continue
            expected['pairs']+=len(R)*len(S)
            if expected['pairs']>max_pairs:return False
            d=gcd(M,L);q=L//d;joint=M*q;new=set()
            for x in R:
                for y in S:
                    if (y-x)%d==0:
                        j=0 if q==1 else ((y-x)//d)*pow(M//d,-1,q)%q
                        new.add((x+M*j)%joint)
            M,R=joint,new
            if not R:break
        expected.update(method='periodic',modulus=str(M),residues=list(map(str,sorted(R))))
        if not R:return equal(r,expected|dict(status='UNREACHABLE'))
        lo=max(start,D);return finish(min(lo+(x-lo)%M for x in R),'periodic')
    except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError):return False
