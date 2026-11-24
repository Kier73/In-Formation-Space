"""Independent CIG-015 verifier. Old seed must be receiver-admitted.
The semantic checker uses tuple assignments; no producer import.
"""
from collections import Counter
from itertools import product
from regional_memory import identity, wire
from verify_composed_ground import normal


def check_extension(old, clause, receipt, new):
    try:
        d=old['descriptor']; n=d['n']; s=d['scope']; v=d['visible']; p=d['predicates']; width=len(v)+len(p)
        if normal([clause],n)!=[tuple(clause)] or any(abs(l) not in s for l in clause):return False
        if old['key']!=identity(d) or clause in p or len(p)>=32:return False
        nd=dict(d,predicates=p+[clause]); hist={k:int(z) for k,z in old['bins']}
        if len(hist)!=len(old['bins']) or any(type(k)is not int or not 0<=k<2**width or z<=0 for k,z in hist.items()):return False
        method=receipt['method']; counts=Counter(); witnesses={}
        if method in ('cover','equivalent'):
            if set(receipt)!={'method','parts','splits','pairs'}:return False
            # Independent transitive closure, rather than producer graph traversal.
            rep={l:l for u in s for l in (u,-u)}
            if method=='equivalent':
                relation={(l,l) for l in rep}
                for row in d['source']:
                    if len(row)==2:
                        a,b=row;relation.update(((-a,b),(-b,a)))
                for mid in rep:
                    incoming=[a for a in rep if (a,mid) in relation]
                    outgoing=[b for b in rep if (mid,b) in relation]
                    relation.update((a,b) for a in incoming for b in outgoing)
                rep={l:min(x for x in rep if (l,x) in relation and (x,l) in relation) for l in rep}
            lits=set()
            for kind,i in receipt['parts']:
                if type(kind)is not int or type(i)is not int or i<0:return False
                if kind==0 and i<len(p):lits.update(p[i])
                elif kind in (1,2) and i<len(v):lits.add(v[i] if kind==1 else -v[i])
                elif kind==3 and method=='equivalent' and i<len(p) and len(p[i])==1:lits.add(-p[i][0])
                else:return False
            if {rep[l] for l in lits}!={rep[l] for l in clause}:return False
            for k,z in hist.items():
                truth=any(((k//2**(len(v)+i))%2)==int(kind==0) if kind in (0,3) else ((k//2**i)%2)==int(kind==1) for kind,i in receipt['parts'])
                counts[k+int(truth)*2**width]+=z
        elif method=='semantic':
            if set(receipt)!={'method','splits','pairs'}:return False
            for vals in product((0,1),repeat=len(s)):
                a=dict(zip(s,vals))
                def sat(row):return any(a[abs(l)]==int(l>0) for l in row)
                if not all(sat(row) for row in d['source']):continue
                bits=tuple(a[u] for u in v)+tuple(int(sat(row)) for row in p)
                k=sum(bit*2**i for i,bit in enumerate(bits)); bit=int(sat(clause));counts[k+bit*2**width]+=1
            # Independently establish conservation on every original fiber.
            projected=Counter()
            for k,z in counts.items():projected[k%2**width]+=z
            if dict(projected)!=hist:return False
        else:return False
        splits=sorted(k for k in hist if counts[k] and counts[k+2**width])
        if any(type(k)is not int for k in receipt['splits']) or receipt['splits']!=splits or len(receipt['pairs'])!=len(splits):return False
        # One concrete source-model pair per split; verify both source and signature.
        for k,pair in zip(splits,receipt['pairs']):
            if len(pair)!=2:return False
            for expected,x in enumerate(pair):
                if type(x)is not int or not 0<=x<2**len(s):return False
                a={u:(x//2**i)%2 for i,u in enumerate(s)}
                def sat(row):return any(a[abs(l)]==int(l>0) for l in row)
                if not all(sat(c) for c in d['source']) or int(sat(clause))!=expected:return False
                bits=[a[u] for u in v]+[int(sat(c)) for c in p]
                if sum(z*2**i for i,z in enumerate(bits))!=k:return False
        expected=dict(descriptor=nd,key=identity(nd),bins=[[k,str(z)] for k,z in sorted(counts.items()) if z],bits=max(0,len([z for z in counts.values() if z])-1).bit_length())
        return wire(new)==wire(expected)
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False
