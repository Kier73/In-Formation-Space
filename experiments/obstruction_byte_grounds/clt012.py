"""CLT-012: failed byte representations form new segmentation sensors."""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

# Import the pinned VLM-007 implementation, not a second codec library.
parser = argparse.ArgumentParser()
parser.add_argument('--vlm', required=True)
parser.add_argument('--artifacts', action='store_true')
args = parser.parse_args()
sys.path.insert(0, args.vlm)
import byte_ground as bg


class Memory:
    def __init__(self, data, retain=True):
        self.source = bg.Source(data)
        self.n = self.source.n
        self.retain = retain
        self.values = bytearray(self.n) if retain else None
        self.seen = bytearray(self.n) if retain else None
        self.requested = 0
        self.hits = 0
        self.splits = 0
        self.witnesses = []
        self.peak_cache = 2*self.n if retain else 0

    def read(self, a, b):
        assert 0 <= a <= b <= self.n
        self.requested += b-a
        if not self.retain:
            return self.source.read(a,b)
        i = a
        while i < b:
            if self.seen[i]:
                self.hits += 1
                i += 1
                continue
            j = i+1
            while j < b and not self.seen[j]:
                j += 1
            self.values[i:j] = self.source.read(i,j)
            self.seen[i:j] = b'\x01'*(j-i)
            i = j
        return bytes(self.values[a:b])


class Window:
    def __init__(self, memory, start, end):
        self.memory, self.start, self.n = memory, start, end-start
        self.last = None

    def read(self, a, b):
        assert 0 <= a <= b <= self.n
        data = self.memory.read(self.start+a,self.start+b)
        self.last = (a,data)
        return data


def size(parts):
    # One u32 part count, four bytes per start offset; original Ground sizes.
    return 4+sum(4+g.size() for _,g in parts)


def split(memory, start, end, depth=0):
    w = Window(memory,start,end)
    kind = {'zero':'ramp','constant':'ramp','ramp':'ramp','repeat':'period'}.get(bg.sensor(w,'prefix'))
    if kind is not None:
        g = bg.propose(w,kind)
        if g is not None:
            if bg.admit(w,g):
                return [(start,g)]
            # Native verifier stops on the first nonmatching block. Its last
            # actual observation becomes a new sensor: exact discrepancy index.
            a, observed = w.last
            expected = g.read(a,a+len(observed))
            cut = a+next(i for i,(x,y) in enumerate(zip(observed,expected)) if x!=y)
            memory.witnesses.append((start+cut,kind))
            if depth < 4 and 64 <= cut <= w.n-64:
                memory.splits += 1
                left = Window(memory,start,start+cut)
                # Reuse the rejected descriptor restricted to the prefix;
                # independent VLM admission of the shorter domain.
                prefix = bg.Ground(g.kind,cut,g.payload)
                assert bg.admit(left,prefix)
                right = split(memory,start+cut,end,depth+1)
                parts = [(start,prefix)]+right
                if size(parts) < 4+4+5+w.n:
                    return parts
    return [(start,bg.exact(w))]


def realize(data, route):
    m = Memory(data,route not in ('global','split_uncached'))
    if route in ('global','global_cached'):
        parts = [(0,bg.exact(Window(m,0,m.n)))]
    elif route == 'fixed':
        parts = [(i,bg.exact(Window(m,i,min(i+256,m.n)))) for i in range(0,m.n,256)]
    else:
        parts = split(m,0,m.n)
    # Verify source coverage and contents independently, not via cache.
    pos = 0
    for start,g in parts:
        assert start == pos and bg.valid(g)
        assert g.read(0,g.n) == data[start:start+g.n]
        pos += g.n
    assert pos == len(data)
    rng = random.Random(9)
    for _ in range(12):
        a,b = sorted((rng.randrange(m.n+1),rng.randrange(m.n+1)))
        total = sum(g.total(max(a,s)-s,min(b,s+g.n)-s) for s,g in parts if max(a,s)<min(b,s+g.n))
        assert total == sum(data[a:b])
    return {'reads':m.source.reads,'requested':m.requested,'hits':m.hits,'encoded':size(parts),
            'parts':len(parts),'splits':m.splits,'witnesses':len(m.witnesses),'peak_cache':m.peak_cache,
            'audit_bytes':m.n,'range_checks':12}


def corpus(seed, count):
    r = random.Random(seed)
    for i in range(count):
        n = r.randrange(128,600)
        a = bytes((17+3*j)&255 for j in range(n))
        b = (b'AZQ'*300)[:r.randrange(128,600)]
        if i%4==0:
            yield 'mixed',a+b+bytes([r.randrange(256)])*r.randrange(128,600)
        elif i%4==1:
            yield 'mixed_random',a+r.randbytes(r.randrange(128,600))
        elif i%4==2:
            yield 'uniform',a
        else:
            yield 'random',r.randbytes(n+len(b))


def campaign(items):
    result = {}
    routes = ('global','global_cached','fixed','split_uncached','split_cached')
    for family,data in items:
        row = result.setdefault(family,{r:Counter() for r in routes})
        outcomes = {r:realize(data,r) for r in routes}
        assert outcomes['split_cached']['encoded']==outcomes['split_uncached']['encoded']
        for r in ('global_cached','fixed','split_cached'):
            assert outcomes[r]['reads']==len(data)
        for r,o in outcomes.items():
            row[r].update(o)
            row[r]['cases']+=1
    return result


report={'synthetic':campaign(corpus(20261126,160))}
if args.artifacts:
    files = ('core.c','application.c','neural.c','capsule.py','policy_weights.json','vlm64.elf')
    report['artifacts']=campaign((name,(Path(args.vlm)/name).read_bytes()) for name in files)
print(json.dumps(report,sort_keys=True,indent=2))
