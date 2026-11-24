"""Independent CIG-021 source, functional-graph and terminal decoder receiver."""
from hashlib import sha256
from itertools import product
from copy import deepcopy
import json
from verify_composed_ground import normal, accepted
from verify_shared_proof import verify as verify_shared
from verify_global_sufficiency import value
from verify_source_section import verify_section


def digest(obj):return sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def verify_transport(source,k,w,g):
    try:
        if type(k)is not int or type(w)is not int or not 1<=w<=4 or not 1<=k<=4096 or k%w:return False
        rows=normal(source,2*k);m=k//w;a=2**w;N=m*a
        if set(g)!={'schema','key','pred','tables','depth','entry','cycles'} or g['schema']!='ifs.cig021.transport.v1' or g['key']!=digest([k,w,rows]):return False
        p=g['pred'];tables=g['tables']
        if type(p)is not list or any(type(i)is not int for i in p) or sorted(p)!=list(range(m)) or len(tables)!=m:return False
        group=[[] for _ in range(m)]
        for c in rows:
            outs={ (abs(l)-k-1)//w for l in c if abs(l)>k }
            if len(outs)!=1:return False
            j=next(iter(outs));allowed=set(range(p[j]*w+1,(p[j]+1)*w+1))|set(range(k+j*w+1,k+(j+1)*w+1))
            if any(abs(l) not in allowed for l in c):return False
            group[j].append(c)
        edges=[None]*N
        for j,cs in enumerate(group):
            i=p[j];table=tables[j]
            if not cs or not any(abs(l)<=k for c in cs for l in c) or len(table)!=a or any(type(v)is not int or not 0<=v<a for v in table):return False
            old=list(range(i*w+1,(i+1)*w+1));new=list(range(k+j*w+1,k+(j+1)*w+1))
            # Separate tuple evaluation of every local source relation.
            for bits in product((0,1),repeat=2*w):
                env=dict(zip(old+new,bits));x=sum(bits[z]*2**z for z in range(w));y=sum(bits[w+z]*2**z for z in range(w))
                if all(any(env[abs(l)]==int(l>0) for l in c) for c in cs)!=(table[x]==y):return False
            for x,y in enumerate(table):edges[i*a+x]=j*a+y
        d,e=g['depth'],g['entry']
        if len(d)!=N or len(e)!=N or any(type(x)is not int or not 0<=x<N for x in d+e):return False
        seen=set()
        for c in g['cycles']:
            if type(c)is not list or not c:return False
            for i,v in enumerate(c):
                if type(v)is not int or not 0<=v<N or v in seen or d[v]!=0 or e[v]!=v or edges[v]!=c[(i+1)%len(c)]:return False
                seen.add(v)
        for v,u in enumerate(edges):
            if d[v]==0:
                if v not in seen:return False
            elif d[v]!=d[u]+1 or e[v]!=e[u] or e[v] not in seen:return False
        return True
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False


def read_code(x,k):
    return type(x)is int and 0<=x<2**k


def check_witness(n,source,q,code,witness):
    return read_code(witness,n) and accepted(source,witness) and all(value(c,witness)==((code>>i)&1) for i,c in enumerate(q))


class Receiver:
    """Checks source proofs once. Pure time queries anchored at an admitted initial code.

    Decoder guarantee is on the original source image. A target witness is
    mandatory unless an independently checked total observation section proves
    that every code is in the source image. Only the latter route proves that
    all intermediate codes have source realizations.
    """
    def __init__(self,n,source,q,targets,decoder,transition,w,g,initial,witness=None,*,section=None):
        if not verify_shared(n,source,q,targets,decoder) or any(x['status']!='SUFFICIENT' for x in decoder['goals']):raise ValueError('decoder proof')
        k=len(q)
        if not verify_transport(transition,k,w,g):raise ValueError('transition proof')
        if not read_code(initial,k):raise ValueError('initial code')
        self.total_image=section is not None
        if self.total_image:
            if not verify_section(n,source,q,section):raise ValueError('source section')
        elif not check_witness(n,source,q,initial,witness):raise ValueError('initial source witness')
        self.n=n;self.source=normal(source,n);self.q=deepcopy(q);self.k=k;self.w=w;self.a=2**w;self.g=deepcopy(g);self.initial=initial;self.circuit=deepcopy(decoder['circuit']);self.key=digest([g['key'],decoder['contract'],self.circuit]);self.pos={v:(c,i) for c in self.g['cycles'] for i,v in enumerate(c)}
        self.edges=[0]*(k//w*self.a)
        for j,i in enumerate(self.g['pred']):
            for x,y in enumerate(self.g['tables'][j]):self.edges[i*self.a+x]=j*self.a+y
    def accept(self,t,r):
        try:
            if type(t)is not int or t<0 or t.bit_length()>4096:return False
            if set(r)!={'schema','key','initial','time','code','outputs','witness'} or r['schema']!='ifs.cig021.jump.v1' or r['key']!=self.key or r['initial']!=str(self.initial) or r['time']!=str(t):return False
            # Use ordinary transient walks, then independently qualified cycle residue.
            result=0;locations=set()
            for i in range(self.k//self.w):
                v=i*self.a+((self.initial//2**(i*self.w))%self.a);d=self.g['depth'][v]
                if t<d:
                    for _ in range(t):v=self.edges[v]
                else:
                    c,p=self.pos[self.g['entry'][v]];v=c[(p+t-d)%len(c)]
                j,x=divmod(v,self.a)
                if j in locations:return False
                locations.add(j);result+=x*2**(j*self.w)
            if r['code']!=str(result):return False
            if self.total_image:
                if r['witness'] is not None:return False
            else:
                if type(r['witness'])is not str:return False
                witness=int(r['witness'])
                if str(witness)!=r['witness'] or not check_witness(self.n,self.source,self.q,result,witness):return False
            vals={1:1,**{i+2:(result//2**i)%2 for i in range(self.k)}}
            def read(x):return vals[abs(x)] if x>0 else 1-vals[abs(x)]
            for j,(op,a,b) in enumerate(self.circuit['gates'],self.k+2):vals[j]=min(read(a),read(b)) if op=='and' else max(read(a),read(b))
            want=[read(x) for x in self.circuit['outputs']]
            return type(r['outputs'])is list and all(type(x)is int for x in r['outputs']) and r['outputs']==want
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError):return False
