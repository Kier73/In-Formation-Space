"""CIG-020: event-directed execution of a source-verified multi-output circuit.
The circuit is immutable per session. Signed references are interpreted on read.
No source claims are made for observation codes outside the source image.
"""
from heapq import heappush,heappop
from copy import deepcopy
from composed_ground import digest


def validate_code(code,k):
    if type(code)is not int or not 0<=code<1<<k:raise ValueError('observation code')

class DecoderState:
    """Untrusted producer; receiver must separately admit each event."""
    def __init__(self,circuit,k,code):
        validate_code(code,k);self.k=k;self.circuit=deepcopy(circuit);self.code=code;self.epoch=0;self.key=digest([k,self.circuit]);self.values=[False,True]+[bool(code>>i&1) for i in range(k)];self.fanout=[[] for _ in range(k+2+len(circuit['gates']))]
        for j,(op,a,b) in enumerate(self.circuit['gates'],k+2):
            self.values.append(self.gate(op,a,b));self.fanout[abs(a)].append(j);self.fanout[abs(b)].append(j)
    def read(self,r):return self.values[abs(r)] if r>0 else not self.values[-r]
    def gate(self,op,a,b):return self.read(a) and self.read(b) if op=='and' else self.read(a) or self.read(b)
    def outputs(self):return [None if r is None else int(self.read(r)) for r in self.circuit['outputs']]
    def full(self,code,attempted=0):
        self.values=[False,True]+[bool(code>>i&1) for i in range(self.k)]
        for op,a,b in self.circuit['gates']:self.values.append(self.gate(op,a,b))
        self.code=code;self.epoch+=1
        return {'schema':'ifs.cig020.event.v1','circuit':self.key,'epoch':self.epoch,'code':str(code),'mode':'full','attempted':attempted,'checks':[],'outputs':self.outputs()}
    def update(self,code,mode='delta'):
        validate_code(code,self.k)
        if mode not in ('delta','full','auto'):raise ValueError('mode')
        diff=self.code^code
        if mode=='full' or (mode=='auto' and diff.bit_count()>max(1,self.k//8)):return self.full(code)
        cap=max(1,len(self.circuit['gates'])//8) if mode=='auto' else None
        todo=[];pending=set();steps=[]
        def activate(v):
            for g in self.fanout[v]:
                if g not in pending:heappush(todo,g);pending.add(g)
        while diff:
            m=diff&-diff;diff-=m;v=m.bit_length()+1;self.values[v]=not self.values[v];activate(v)
        while todo:
            if cap is not None and len(steps)>=cap:return self.full(code,len(steps))
            g=heappop(todo);pending.remove(g);bit=self.gate(*self.circuit['gates'][g-self.k-2]);steps.append([g,int(bit)])
            if self.values[g]!=bit:self.values[g]=bit;activate(g)
        self.code=code;self.epoch+=1
        return {'schema':'ifs.cig020.event.v1','circuit':self.key,'epoch':self.epoch,'code':str(code),'checks':steps,'outputs':self.outputs()}
