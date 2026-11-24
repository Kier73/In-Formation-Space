"""CIG-021: exact logical-time jumps of a proof-derived language.

A separately declared CNF relates old and new observation coordinates. A
receiver-qualified block-permutation law lifts symbols to a functional graph.
No temporal law is inferred from a static decoder source. See verifier.
"""
from collections import defaultdict
from composed_ground import canonical, digest
from shared_proof import evaluate

SCHEMA = 'ifs.cig021.transport.v1'
MAX_WIDTH = 4
MAX_TIME_BITS = 4096


def compile_transport(source, k, width):
    if type(k) is not int or type(width) is not int or not 1 <= width <= MAX_WIDTH or not 1 <= k <= 4096 or k % width:
        raise ValueError('transport contract')
    rows = canonical(source, 2*k)
    m, a = k//width, 1 << width
    grouped = defaultdict(list)
    for row in rows:
        out = {(abs(l)-k-1)//width for l in row if abs(l)>k}
        if len(out)!=1: raise ValueError('every clause must own one next block')
        grouped[out.pop()].append(row)
    pred, tables = [], []
    for j in range(m):
        local = grouped[j]
        inp = {(abs(l)-1)//width for c in local for l in c if abs(l)<=k}
        if len(inp)!=1: raise ValueError('one predecessor block required')
        i=inp.pop(); pred.append(i)
        # Literal masks in a 2w-bit local coordinate system.
        masks=[[(1 << ((abs(l)-1)%width+(width if abs(l)>k else 0)),l>0) for l in c] for c in local]
        table=[]
        for x in range(a):
            valid=[y for y in range(a) if all(any(bool((x | y<<width)&b)==s for b,s in c) for c in masks)]
            if len(valid)!=1: raise ValueError('transition not total and unique')
            table.append(valid[0])
        tables.append(table)
    if sorted(pred)!=list(range(m)): raise ValueError('transport is not a spatial permutation')
    edges=[0]*(m*a)
    for j,i in enumerate(pred):
        for x,y in enumerate(tables[j]):edges[i*a+x]=j*a+y
    # Each pair (block location, local symbol) has one successor, even when
    # several symbols have the same successor. Walk to an old node or a cycle.
    depth=[-1]*len(edges); entry=[-1]*len(edges); cycles=[]
    for v in range(len(edges)):
        if depth[v]>=0: continue
        stack=[]; position={}; x=v
        while depth[x]<0 and x not in position:
            position[x]=len(stack);stack.append(x);x=edges[x]
        if x in position:
            c=stack[position[x]:];cycles.append(c)
            for u in c:depth[u]=0;entry[u]=u
            stack=stack[:position[x]]
        for u in reversed(stack):depth[u]=depth[edges[u]]+1;entry[u]=entry[edges[u]]
    return dict(schema=SCHEMA, key=digest([k,width,rows]), pred=pred,tables=tables,depth=depth,entry=entry,cycles=cycles)


def contract_code(code,k):
    if type(code) is not int or not 0<=code<1<<k: raise ValueError('observation code')


def contract_time(t):
    if type(t) is not int or t<0 or t.bit_length()>MAX_TIME_BITS: raise ValueError('logical time')


class Navigator:
    """Producer. The receiver must admit the transport and shared proof separately."""
    def __init__(self,k,width,ground,decoder):
        self.k=k;self.w=width;self.a=1<<width;self.g=ground;self.decoder=decoder
        self.edges=[0]*(k//width*self.a)
        for j,i in enumerate(ground['pred']):
            for x,y in enumerate(ground['tables'][j]):self.edges[i*self.a+x]=j*self.a+y
        self.pos={v:(c,i) for c in ground['cycles'] for i,v in enumerate(c)}
        self.powers=[self.edges]
        for _ in range(1,max(ground['depth']).bit_length()):
            p=self.powers[-1];self.powers.append([p[x] for x in p])
        self.key=digest([ground['key'],decoder['contract'],decoder['circuit']])
    def jump(self,code,t):
        contract_code(code,self.k);contract_time(t)
        out=0;seen=set();a=self.a
        for i in range(self.k//self.w):
            v=i*a+((code>>(i*self.w))&(a-1));d=self.g['depth'][v]
            if t>=d:
                c,p=self.pos[self.g['entry'][v]];v=c[(p+(t-d)%len(c))%len(c)]
            else:
                for b in range(t.bit_length()):
                    if t>>b&1:v=self.powers[b][v]
            j,x=divmod(v,a)
            if j in seen:raise AssertionError('transport collision')
            seen.add(j);out|=x<<(j*self.w)
        return out
    def result(self,code,t,terminal_witness=None):
        out=self.jump(code,t)
        return dict(schema='ifs.cig021.jump.v1',key=self.key,initial=str(code),time=str(t),code=str(out),outputs=evaluate(self.decoder['circuit'],out,self.k),witness=None if terminal_witness is None else str(terminal_witness))
