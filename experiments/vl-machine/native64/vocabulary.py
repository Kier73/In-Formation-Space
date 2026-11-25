"""VLM-009: learned shared byte operators, charged vocabulary and exact receiver."""
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from struct import pack, unpack_from
from byte_ground import Ground, Source, valid
from compose_ground import Composite, compose, decode, restore

MAX=65536
KINDS=('raw','period','ramp','sparse')

@dataclass(frozen=True)
class Vocabulary:
    words:tuple
    def __post_init__(self):
        if type(self.words) is not tuple or len(self.words)>64 or any(type(w) is not bytes or not 8<=len(w)<=32 for w in self.words) or len(set(self.words))!=len(self.words):raise ValueError('vocabulary')
    def encode(self):return b'VLV1'+bytes([len(self.words)])+b''.join(bytes([len(w)])+w for w in self.words)
    @property
    def digest(self):return sha256(self.encode()).digest()
    @classmethod
    def decode(cls,wire):
        if type(wire) is not bytes or not 5<=len(wire)<=5+64*33 or wire[:4]!=b'VLV1' or wire[4]>64:raise ValueError('vocabulary header')
        p=5;words=[]
        for _ in range(wire[4]):
            if p==len(wire):raise ValueError('truncated')
            n=wire[p];p+=1
            if not 8<=n<=32 or p+n>len(wire):raise ValueError('word length')
            words.append(wire[p:p+n]);p+=n
        if p!=len(wire):raise ValueError('trailing bytes')
        return cls(tuple(words))

@dataclass(frozen=True)
class Ref:
    index:int
    word:bytes
    @property
    def n(self):return len(self.word)
    def read(self,a,b):return self.word[a:b]
    def total(self,a,b):return sum(self.word[a:b])

@dataclass(frozen=True)
class Program:
    vocab:Vocabulary
    leaves:tuple
    def __post_init__(self):
        if type(self.leaves) is not tuple or not self.leaves:raise ValueError('leaves')
        ends=[];sums=[0];n=0
        for g in self.leaves:
            if isinstance(g,Ref):
                if type(g.index) is not int or not 0<=g.index<len(self.vocab.words) or g.word!=self.vocab.words[g.index]:raise ValueError('reference')
            elif not valid(g):raise ValueError('leaf')
            n+=g.n;ends.append(n);sums.append(sums[-1]+g.total(0,g.n))
        if n>MAX:raise ValueError('extent')
        object.__setattr__(self,'ends',tuple(ends));object.__setattr__(self,'sums',tuple(sums))
    @property
    def n(self):return self.ends[-1]
    def read(self,a,b):
        if not 0<=a<=b<=self.n:raise ValueError('range')
        i=bisect_right(self.ends,a);out=[]
        while a<b:
            start=self.ends[i-1] if i else 0;end=min(b,self.ends[i]);out.append(self.leaves[i].read(a-start,end-start));a=end;i+=1
        return b''.join(out)
    def prefix(self,t):
        if not 0<=t<=self.n:raise ValueError('range')
        i=bisect_right(self.ends,t)
        if i==len(self.leaves):return self.sums[i]
        return self.sums[i]+self.leaves[i].total(0,t-(self.ends[i-1] if i else 0))
    def total(self,a,b):
        if not 0<=a<=b<=self.n:raise ValueError('range')
        return self.prefix(b)-self.prefix(a)
    def encode(self):
        return b'VLP1'+pack('<II',self.n,len(self.leaves))+self.vocab.digest+b''.join(bytes([4,g.index]) if isinstance(g,Ref) else Composite((g,)).encode()[12:] for g in self.leaves)

def decode_program(wire,vocab):
    if type(wire) is not bytes or not 44<=len(wire)<=44+14*MAX or wire[:4]!=b'VLP1' or wire[12:44]!=vocab.digest:raise ValueError('program header or vocabulary identity')
    n,k=unpack_from('<II',wire,4);p=44;extent=0;leaves=[]
    if not 1<=k<=n<=MAX:raise ValueError('header bounds')
    for _ in range(k):
        if p>=len(wire):raise ValueError('truncated')
        kind=wire[p]
        if kind==4:
            if p+2>len(wire) or wire[p+1]>=len(vocab.words):raise ValueError('reference')
            i=wire[p+1];g=Ref(i,vocab.words[i]);p+=2
        else:
            if kind>3 or p+5>len(wire):raise ValueError('leaf')
            size=unpack_from('<I',wire,p+1)[0]
            if not 1<=size<=n-extent:raise ValueError('length')
            end=p+5
            if kind==0:end+=size
            elif kind==1:
                if end>=len(wire):raise ValueError('period')
                end+=1+wire[end]
            elif kind==2:end+=2
            else:
                if end+4>len(wire):raise ValueError('sparse')
                c=unpack_from('<I',wire,end)[0]
                if c>size:raise ValueError('sparse count')
                end+=4+5*c
            if end>len(wire):raise ValueError('truncated leaf')
            g=decode(b'VLG1'+pack('<II',size,1)+wire[p:end]).leaves[0];p=end
        extent+=g.n
        if extent>n:raise ValueError('extent')
        leaves.append(g)
    if p!=len(wire) or extent!=n:raise ValueError('trailing or missing bytes')
    return Program(vocab,tuple(leaves))

def receive(wire,vocab,expected_sha):
    if wire[:4]==b'VLG1':return restore(wire,expected_sha)
    g=decode_program(wire,vocab);h=sha256()
    for a in range(0,g.n,64):h.update(g.read(a,min(a+64,g.n)))
    if h.hexdigest()!=expected_sha:raise ValueError('source identity')
    return g

def tokenize(data,vocab):
    """Exact shortest path through raw runs and known word references."""
    n=len(data);byfirst={}
    for i,w in enumerate(vocab.words):byfirst.setdefault(w[0],[]).append((i,w))
    dp=[0]*(n+1);choice=[None]*n;best=n;end=n
    for i in range(n-1,-1,-1):
        dp[i]=5+best-i;choice[i]=(end,None)
        for j,w in byfirst.get(data[i],()):
            if data.startswith(w,i) and 2+dp[i+len(w)]<dp[i]:dp[i]=2+dp[i+len(w)];choice[i]=(i+len(w),j)
        if dp[i]+i<=best:best=dp[i]+i;end=i
    out=[];i=0
    while i<n:
        end,j=choice[i];out.append(Ground('raw',end-i,(data[i:end],)) if j is None else Ref(j,vocab.words[j]));i=end
    return tuple(out)

def apply(base,vocab):
    if not vocab.words:return base.encode()
    leaves=[]
    for g in base.leaves:leaves.extend(tokenize(g.payload[0],vocab) if g.kind=='raw' else (g,))
    p=Program(vocab,tuple(leaves));a=base.encode();b=p.encode()
    return b if len(b)<len(a) else a

def discover(training,limit=64):
    """Mine byte substrings from training raw leaves; greedily cover nonoverlapping uses."""
    if type(limit) is not int or not 0<=limit<=64:raise ValueError('limit')
    blocks=[g.payload[0] for b in training for g in b.leaves if g.kind=='raw'];counts=Counter()
    for p in blocks:
        for n in (8,16,32):counts.update(p[i:i+n] for i in range(len(p)-n+1))
    ranked=sorted((w for w,c in counts.items() if c>1),key=lambda w:(-((counts[w]-1)*(len(w)-2)-len(w)),w))[:512]
    positions={}
    for w in ranked:
        hits=[]
        for j,p in enumerate(blocks):
            i=p.find(w)
            while i>=0:hits.append((j,i));i=p.find(w,i+len(w))
        positions[w]=hits
    covered=[bytearray(len(b)) for b in blocks];words=[]
    for _ in range(limit):
        best=0;winner=None;uses=[]
        for w,hits in positions.items():
            live=[(j,i) for j,i in hits if not any(covered[j][i:i+len(w)])]
            # Approximate raw-split cost; actual DP and validation decide admission.
            gain=len(live)*(len(w)-7)-len(w)-1
            if gain>best:best=gain;winner=w;uses=live
        if winner is None:break
        words.append(winner);del positions[winner]
        for j,i in uses:covered[j][i:i+len(winner)]=b'\1'*len(winner)
    return Vocabulary(tuple(words))

def qualify(candidate,validation):
    """Freeze a prefix by exact validation wire cost, including vocabulary bytes."""
    options=[]
    for n in sorted(set([0,8,16,32,64,len(candidate.words)])):
        if n>len(candidate.words):continue
        v=Vocabulary(candidate.words[:n]);size=sum(len(apply(b,v)) for b in validation)+(len(v.encode()) if n else 0)
        options.append((size,n,v))
    return min(options,key=lambda x:(x[0],x[1]))[2],[(n,size) for size,n,_ in options]

def compile_source(data):return compose(Source(data))[0]
