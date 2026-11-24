"""Independent resolution and interpolation replay. No producer import.
Invariant: A entails C_A-local OR I; B entails C_non-A-local OR NOT I.
Only the shared observer variables can occur in I.
"""
from hashlib import sha256
import json
from verify_global_sufficiency import contract, value
from verify_composed_ground import accepted
from verify_proof_refinement import Receiver, predicate, signature, MAX_PREDICATES


def replay_source(n,source,q,f):
    rows=[];sides=[]
    for left in (True,False):
        def move(l):return l if left else (abs(l)+n)*(1 if l>0 else -1)
        part=[set(map(move,c)) for c in source]
        for i,obs in enumerate(q,1):
            u=2*n+i;terms=[move(l) for l in obs]
            part.append(set(terms+[-u]))
            for l in terms:part.append({u,-l})
        if left:part.append(set(f))
        else:part.extend({-move(l)} for l in f)
        rows.extend(part);sides.extend([left]*len(part))
    return rows,sides


def decoder_replay(n,k,rows,sides,steps,root):
    gates=[];indices={}
    def combine(op,x,y):
        if op=='and':
            if -1 in (x,y) or x==-y:return -1
            if x==1:return y
            if y==1:return x
        else:
            if 1 in (x,y) or x==-y:return 1
            if x==-1:return y
            if y==-1:return x
        if x==y:return x
        item=(op,min(x,y),max(x,y))
        if item not in indices:
            indices[item]=len(gates)+k+2;gates.append(list(item))
        return indices[item]
    refs=[]
    for row,left in zip(rows,sides):
        ref=-1 if left else 1
        if left:
            for l in sorted(row,key=lambda z:abs(z)):
                if abs(l)>2*n:
                    ref=combine('or',ref,(abs(l)-2*n+1) if l>0 else -(abs(l)-2*n+1))
        refs.append(ref)
    for x,y,p in steps:refs.append(combine('or' if 1<=p<=n else 'and',refs[x],refs[y]))
    return {'gates':gates,'output':refs[root]}


def decode(circuit,code,k):
    vals={1:True,**{i+2:bool(code//2**i%2) for i in range(k)}}
    def read(i):return vals[abs(i)]==(i>0)
    for i,(op,x,y) in enumerate(circuit['gates'],k+2):
        vals[i]=all((read(x),read(y))) if op=='and' else any((read(x),read(y)))
    return int(read(circuit['output']))


def verify(n,source,q,f,r,*,max_pairs=500000,max_steps=200000,max_width=32,ordering="scope"):
    try:
        s,q,f=contract(n,source,q,f)
        if any(type(z)is not int or z<1 for z in (max_pairs,max_steps,max_width)) or ordering not in ("scope","pairs"):return False
        key=sha256(json.dumps([n,s,q,f],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if r['schema']!='ifs.cig018.interpolant.v1' or r['contract']!=key:return False
        if r['status']=='INSUFFICIENT':
            w=r['witness']
            if len(w)!=2 or any(type(z)is not str or not z.isascii() or not z.isdecimal() or str(int(z))!=z for z in w):return False
            x,y=map(int,w)
            return all(0<=z<2**n and accepted(s,z) for z in (x,y)) and all(value(c,x)==value(c,y) for c in q) and value(f,x)!=value(f,y)
        if r['status']!='SUFFICIENT':return False
        rows,sides=replay_source(n,s,q,f);base=len(rows);steps=r['steps']
        if len(steps)>min(max_steps,max_pairs):return False
        original=rows.copy()
        for item in steps:
            a,b,p=item
            if any(type(z)is not int for z in item) or not 0<=a<len(rows) or not 0<=b<len(rows) or not 1<=p<=2*n+len(q):return False
            if p not in rows[a] or -p not in rows[b]:return False
            c=(rows[a]|rows[b])-{p,-p}
            if len(c)>max_width or any(-l in c for l in c):return False
            rows.append(c)
        root=r['root']
        if type(root)is not int or not 0<=root<len(rows) or rows[root]:return False
        expected=decoder_replay(n,len(q),original,sides,steps,root)
        d=r['decoder']
        if type(d['output']) is not int or any(type(z)is not int for g in d['gates'] for z in g[1:]):return False
        return d==expected
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False

class InterpolantReceiver(Receiver):
    def accept_interpolant(self,f,r,**budget):
        q,old=self.snapshot();f=predicate(self.n,f)
        if f in q or len(q)>=MAX_PREDICATES:raise ValueError('extension contract')
        if not verify(self.n,self.source,q,f,r,**budget):raise ValueError('unverified interpolant')
        if r['status']!='SUFFICIENT':return False
        new={}
        for code,(count,witness) in old.items():
            b=decode(r['decoder'],code,len(q))
            if not accepted(self.source,witness) or signature(q,witness)!=code or value(f,witness)!=b:raise ValueError('representative mismatch')
            new[code|(b<<len(q))]=(count,witness)
        self._predicates=q+(f,);self._fibers=new;self.stats['interpolant_admissions']+=1
        return True
