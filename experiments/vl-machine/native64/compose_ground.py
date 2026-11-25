"""VLM-008: bounded compositional byte Grounds with canonical wire encoding."""
from bisect import bisect_right
from dataclasses import dataclass
from hashlib import sha256
from struct import pack, unpack_from
from byte_ground import Ground, Source, valid, propose, admit

MAGIC=b'VLG1'
KINDS=('raw','period','ramp','sparse')
MAX=65536

@dataclass(frozen=True)
class Composite:
    leaves:tuple
    def __post_init__(self):
        if type(self.leaves) is not tuple or not self.leaves or not all(valid(g) for g in self.leaves):raise ValueError('leaves')
        ends=[]
        for g in self.leaves:ends.append((ends[-1] if ends else 0)+g.n)
        if ends[-1]>MAX:raise ValueError('extent')
        object.__setattr__(self,'ends',tuple(ends))
        totals=[0]
        for g in self.leaves:totals.append(totals[-1]+g.total(0,g.n))
        object.__setattr__(self,'totals',tuple(totals))
    @property
    def n(self):return self.ends[-1]
    def parts(self,a,b):
        if not 0<=a<=b<=self.n:raise ValueError('range')
        i=bisect_right(self.ends,a)
        while a<b:
            start=self.ends[i-1] if i else 0;end=min(b,self.ends[i])
            yield self.leaves[i],a-start,end-start
            a=end;i+=1
    def read(self,a,b):return b''.join(g.read(x,y) for g,x,y in self.parts(a,b))
    def prefix(self,t):
        if not 0<=t<=self.n:raise ValueError('range')
        i=bisect_right(self.ends,t)
        if i==len(self.leaves):return self.totals[i]
        return self.totals[i]+self.leaves[i].total(0,t-(self.ends[i-1] if i else 0))
    def total(self,a,b):
        if not 0<=a<=b<=self.n:raise ValueError('range')
        return self.prefix(b)-self.prefix(a)
    def encode(self):
        out=bytearray(MAGIC+pack('<II',self.n,len(self.leaves)))
        for g in self.leaves:
            out+=pack('<BI',KINDS.index(g.kind),g.n)
            if g.kind=='raw':out+=g.payload[0]
            elif g.kind=='period':out+=bytes([len(g.payload[0])])+g.payload[0]
            elif g.kind=='ramp':out+=bytes(g.payload)
            else:
                e,=g.payload;out+=pack('<I',len(e))
                for i,v in e:out+=pack('<IB',i,v)
        return bytes(out)

def decode(raw):
    if type(raw) is not bytes or not 12<=len(raw)<=12+14*MAX or raw[:4]!=MAGIC:raise ValueError('wire')
    n,k=unpack_from('<II',raw,4);pos=12;leaves=[];extent=0
    if not 1<=k<=n<=MAX:raise ValueError('header')
    def take(m):
        nonlocal pos
        if m<0 or pos+m>len(raw):raise ValueError('truncated')
        p=raw[pos:pos+m];pos+=m;return p
    for _ in range(k):
        kind,l=unpack_from('<BI',take(5));extent+=l
        if kind>=len(KINDS) or not l or extent>n:raise ValueError('leaf extent')
        if kind==0:p=(take(l),)
        elif kind==1:p=(take(take(1)[0]),)
        elif kind==2:p=tuple(take(2))
        else:
            count,=unpack_from('<I',take(4))
            if count>l:raise ValueError('sparse count')
            p=(tuple(unpack_from('<IB',take(5)) for _ in range(count)),)
        g=Ground(KINDS[kind],l,p)
        if not valid(g):raise ValueError('invalid leaf')
        leaves.append(g)
    if pos!=len(raw) or extent!=n:raise ValueError('trailing or missing bytes')
    return Composite(tuple(leaves))

def certify(src,g):
    if src.n!=g.n:raise ValueError('extent')
    h=sha256()
    for a in range(0,src.n,64):
        b=min(src.n,a+64);p=src.read(a,b)
        if p!=g.read(a,b):raise ValueError('source mismatch')
        h.update(p)
    return h.hexdigest()

def restore(wire,expected_sha):
    g=decode(wire);h=sha256()
    for a in range(0,g.n,64):h.update(g.read(a,min(a+64,g.n)))
    if h.hexdigest()!=expected_sha:raise ValueError('source identity')
    return g

def work(g):
    # Full-range sum proxy: byte terms, plus per-leaf dispatch.
    return 1+({'raw':lambda:g.n,'period':lambda:len(g.payload[0]),'ramp':lambda:256,'sparse':lambda:len(g.payload[0])}[g.kind]())

def compose(src,minimum=64,weight=0,prune=True):
    """Exact DP over midpoint splits and supported leaf proposals, not arbitrary partitions."""
    if type(minimum) is not int or minimum<1 or type(weight) is not int or weight<0:raise ValueError('objective')
    data=src.read(0,src.n);cost={'candidate_read_bytes':0,'intervals':0,'pruned':0}
    def solve(a,b):
        sub=Source(data[a:b]);candidates=[propose(sub,'raw')]
        for kind in KINDS[1:]:
            g=propose(sub,kind)
            if g is not None and admit(sub,g):candidates.append(g)
        cost['candidate_read_bytes']+=sub.reads;cost['intervals']+=1
        g=min(candidates,key=lambda x:x.size()+weight*work(x))
        best=(g.size()+weight*work(g),(g,))
        if b-a>=2*minimum:
            # Any split costs >= two 6-byte leaves and two dispatches.
            if prune and best[0]<=12+2*weight:
                cost['pruned']+=1;return best
            mid=(a+b)//2;l=solve(a,mid);r=solve(mid,b)
            if l[0]+r[0]<best[0]:best=(l[0]+r[0],l[1]+r[1])
        return best
    _,leaves=solve(0,src.n);return Composite(leaves),cost
