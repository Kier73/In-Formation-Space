"""VLM-007: observer-relative byte Grounds; exact admission, learned sensing."""
from dataclasses import dataclass
from hashlib import sha256
from bisect import bisect_left
from collections import Counter
import random
import json

KINDS=('raw','period','ramp','sparse')
SENSORS=('prefix','tail','middle','stride')

class Source:
    def __init__(self,data):
        if type(data) is not bytes or not 1<=len(data)<=65536:raise ValueError('bounded immutable bytes required')
        self.data=data;self.n=len(data);self.reads=0
    def read(self,start,end):
        if not 0<=start<=end<=self.n:raise ValueError('range')
        self.reads+=end-start;return self.data[start:end]

@dataclass(frozen=True)
class Ground:
    kind:str
    n:int
    payload:tuple
    def size(self):
        # Logical encoded bytes: kind u8, length u32, payload.
        return 5+({'raw':lambda:len(self.payload[0]),'period':lambda:len(self.payload[0])+1,'ramp':lambda:2,'sparse':lambda:4+5*len(self.payload[0])}[self.kind]())
    def read(self,start,end):
        if not 0<=start<=end<=self.n:raise ValueError('range')
        if self.kind=='raw':return self.payload[0][start:end]
        if self.kind=='period':
            p=self.payload[0];return bytes(p[i%len(p)] for i in range(start,end))
        if self.kind=='ramp':
            a,d=self.payload;return bytes((a+d*i)&255 for i in range(start,end))
        if self.kind=='sparse':
            entries,=self.payload;out=bytearray(end-start)
            for i,v in entries[bisect_left(entries,(start,0)):bisect_left(entries,(end,0))]:out[i-start]=v
            return bytes(out)
        raise ValueError('kind')
    def total(self,start,end):
        if not 0<=start<=end<=self.n:raise ValueError('range')
        if self.kind in ('period','ramp'):
            p=self.payload[0] if self.kind=='period' else bytes((self.payload[0]+i*self.payload[1])&255 for i in range(256))
            def prefix(t):q,r=divmod(t,len(p));return q*sum(p)+sum(p[:r])
            return prefix(end)-prefix(start)
        if self.kind=='sparse':
            e,=self.payload;return sum(v for i,v in e[bisect_left(e,(start,0)):bisect_left(e,(end,0))])
        return sum(self.read(start,end))

def valid(g):
    if not isinstance(g,Ground) or type(g.n) is not int or not 1<=g.n<=65536 or type(g.payload) is not tuple:return False
    p=g.payload
    if g.kind=='raw':return len(p)==1 and type(p[0]) is bytes and len(p[0])==g.n
    if g.kind=='period':return len(p)==1 and type(p[0]) is bytes and 1<=len(p[0])<=min(16,g.n)
    if g.kind=='ramp':return len(p)==2 and all(type(v) is int and 0<=v<256 for v in p)
    if g.kind=='sparse':
        return len(p)==1 and type(p[0]) is tuple and all(type(e) is tuple and len(e)==2 and type(e[0]) is int and type(e[1]) is int and 0<=e[0]<g.n and 0<e[1]<256 for e in p[0]) and all(a[0]<b[0] for a,b in zip(p[0],p[0][1:]))
    return False

def admit(src,g):
    if not valid(g) or g.n!=src.n:return False
    for i in range(0,src.n,64):
        end=min(i+64,src.n)
        if src.read(i,end)!=g.read(i,end):return False
    return True

def propose(src,kind):
    n=src.n
    if kind=='raw':return Ground(kind,n,(src.read(0,n),))
    if kind=='ramp':
        p=src.read(0,min(n,2));return Ground(kind,n,(p[0],(p[-1]-p[0])&255))
    if kind=='period':
        p=src.read(0,min(n,64))
        for k in range(1,min(16,n)+1):
            if all(v==p[i%k] for i,v in enumerate(p)):return Ground(kind,n,(p[:k],))
        return None
    if kind=='sparse':
        e=[]
        for i in range(0,n,64):
            e.extend((i+j,v) for j,v in enumerate(src.read(i,min(i+64,n))) if v)
            if 4+5*len(e)>=n:return None
        return Ground(kind,n,(tuple(e),))
    raise ValueError('kind')

def exact(src):
    # Exhaustive over supported proposal routes, not all possible codecs.
    best=propose(src,'raw')
    for k in KINDS[1:]:
        g=propose(src,k)
        if g is not None and (best is None or g.size()<best.size()) and admit(src,g):best=g
    return best

def sensor(src,name):
    n=src.n
    if name=='prefix':p=src.read(0,min(16,n))
    elif name=='tail':p=src.read(max(0,n-16),n)
    elif name=='middle':p=src.read(n//2,min(n,n//2+16))
    elif name=='stride':p=bytes(src.read(i,i+1)[0] for i in range(0,n,max(1,(n+15)//16)))
    else:raise ValueError('sensor')
    # Bounded categorical observation, not a truth claim.
    if all(v==0 for v in p):return 'zero'
    if len(set(p))==1:return 'constant'
    if len(p)>2 and len({(b-a)&255 for a,b in zip(p,p[1:])})==1:return 'ramp'
    if p.count(0)*2>=len(p):return 'sparse'
    if any(all(v==p[i%k] for i,v in enumerate(p)) for k in range(1,min(8,len(p)//2)+1)):return 'repeat'
    return 'other'

def fit(rows,remaining=SENSORS,depth=3):
    # Learn sensors and action jointly. Optimize empirical route correctness,
    # charging each extra sensor 0.02 error-equivalent per encounter.
    counts=Counter(y for x,y in rows);leaf=min(KINDS,key=lambda k:(-counts[k],KINDS.index(k)))
    best=(len(rows)-counts[leaf],{'action':leaf})
    if depth and len(counts)>1:
        for s in remaining:
            groups={}
            for x,y in rows:groups.setdefault(x[s],[]).append((x,y))
            if len(groups)<2:continue
            branches={v:fit(z,tuple(k for k in remaining if k!=s),depth-1) for v,z in groups.items()}
            cost=.02*len(rows)+sum(c for c,t in branches.values())
            if cost<best[0]:best=(cost,{'sensor':s,'default':leaf,'branches':{v:t for v,(c,t) in branches.items()}})
    return best

def select(src,tree):
    while 'sensor' in tree:
        v=sensor(src,tree['sensor']);tree=tree['branches'].get(v,{'action':tree['default']})
    return tree['action']

def realize(src,tree):
    k=select(src,tree);g,fallback=route(src,k)
    return g,k,fallback

def corpus(seed,count):
    r=random.Random(seed)
    for _ in range(count):
        n=r.randrange(256,2049);k=r.randrange(8)
        if k==0:p=bytes([r.randrange(256)])*n
        elif k==1:
            q=r.randbytes(r.randrange(2,9));p=(q*((n+len(q)-1)//len(q)))[:n]
        elif k==2:
            a,d=r.randrange(256),r.randrange(256);p=bytes((a+i*d)&255 for i in range(n))
        elif k==3:
            q=bytearray(n)
            for i in r.sample(range(n),r.randrange(1,12)):q[i]=r.randrange(1,256)
            p=bytes(q)
        elif k==4:
            q=bytearray(b'AB'*(n//2)+b'A'*(n%2));q[r.randrange(n//2,n)]^=1;p=bytes(q)
        elif k==5:p=bytes(64)+r.randbytes(n-64)
        elif k==6:p=r.randbytes(n-64)+bytes(64)
        else:p=r.randbytes(n)
        yield p

def train(seed=771,count=400):
    rows=[]
    for p in corpus(seed,count):
        src=Source(p);g=exact(src);x={s:sensor(src,s) for s in SENSORS};rows.append((x,g.kind))
    return fit(rows)[1]

def benchmark(tree,seed=772,count=400):
    stats={k:{'read_bytes':0,'encoded_bytes':0,'matches_exact':0,'fallbacks':0,'sum_match':0} for k in ('exact','adaptive','raw','prefix')}
    for p in corpus(seed,count):
        src=Source(p);best=exact(src);base=src.reads
        for k,s in stats.items():
            src=Source(p)
            if k=='exact':g=best;src.reads=base;fallback=False
            elif k=='raw':g,_,fallback=realize(src,{'action':'raw'})
            elif k=='prefix':g,_,fallback=realize(src,{'sensor':'prefix','default':'raw','branches':{'zero':{'action':'sparse'},'constant':{'action':'ramp'},'ramp':{'action':'ramp'},'repeat':{'action':'period'}}})
            else:g,_,fallback=realize(src,tree)
            assert g.read(0,len(p))==p
            assert g.total(13,len(p)-7)==sum(p[13:-7])
            s['read_bytes']+=src.reads;s['encoded_bytes']+=g.size();s['matches_exact']+=g.size()==best.size();s['fallbacks']+=fallback;s['sum_match']+=1
    return stats


# A second training objective learns the value of an action, not its label.
def route(src,k):
    g=propose(src,k)
    if g is not None and (k=='raw' or admit(src,g)):return g,False
    return propose(src,'raw'),True

def fit_cost(rows,weight,remaining=SENSORS,depth=3):
    totals={k:sum(cost[k][0]+weight*cost[k][1] for x,cost in rows) for k in KINDS}
    leaf=min(KINDS,key=totals.get);best=(totals[leaf],{'action':leaf})
    if depth:
        for s in remaining:
            groups={}
            for x,cost in rows:groups.setdefault(x[s],[]).append((x,cost))
            if len(groups)<2:continue
            branches={v:fit_cost(z,weight,tuple(k for k in remaining if k!=s),depth-1) for v,z in groups.items()}
            cost=16*len(rows)+sum(c for c,t in branches.values())
            if cost<best[0]:best=(cost,{'sensor':s,'default':leaf,'branches':{v:t for v,(c,t) in branches.items()}})
    return best

def train_cost(weight,seed=771,count=400):
    rows=[]
    for p in corpus(seed,count):
        x={s:sensor(Source(p),s) for s in SENSORS};cost={}
        for k in KINDS:
            src=Source(p);g,_=route(src,k);cost[k]=(src.reads,g.size())
        rows.append((x,cost))
    return fit_cost(rows,weight)[1]

def cost_campaign(tree,seed=772,count=400):
    s={'read_bytes':0,'encoded_bytes':0,'fallbacks':0,'matches_exact':0,'sum_match':0}
    for p in corpus(seed,count):
        best=exact(Source(p));src=Source(p);g,k,fallback=realize(src,tree)
        assert g.read(0,len(p))==p and g.total(13,len(p)-7)==sum(p[13:-7])
        s['read_bytes']+=src.reads;s['encoded_bytes']+=g.size();s['fallbacks']+=fallback;s['matches_exact']+=g.size()==best.size();s['sum_match']+=1
    return s

def certify(src,g):
    """Bind the representation to its original bytes in one exact pass."""
    if not valid(g) or g.n!=src.n:raise ValueError('invalid Ground')
    digest=sha256()
    for i in range(0,src.n,64):
        end=min(i+64,src.n);observed=src.read(i,end)
        if observed!=g.read(i,end):raise ValueError('Ground not source-equivalent')
        digest.update(observed)
    return digest.hexdigest()

def actual_sources(tree):
    from pathlib import Path
    root=Path(__file__).resolve().parent
    report={}
    for name in ('core.c','application.c','neural.c','capsule.py','policy_weights.json','vlm64.elf'):
        p=(root/name).read_bytes();src=Source(p);g,k,f=realize(src,tree)
        assert g.read(0,len(p))==p and g.total(0,len(p))==sum(p)
        proof=Source(p);digest=certify(proof,g)
        report[name]={'sha256':digest,'source_bytes':len(p),'kind':g.kind,'encoded_bytes':g.size(),'read_bytes':src.reads,'certificate_read_bytes':proof.reads,'fallback':f}
    return report

if __name__=='__main__':
    tree=train();policies={str(w):train_cost(w) for w in (1,4,16)}
    print(json.dumps({'tree':tree,'heldout':benchmark(tree),'actual_sources':actual_sources(policies['4']),'cost_policies':{w:{'tree':t,'heldout':cost_campaign(t)} for w,t in policies.items()}},indent=2,sort_keys=True))
