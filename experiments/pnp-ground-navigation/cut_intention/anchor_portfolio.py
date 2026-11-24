"""CIG-030A: cost-directed exact anchor acquisition and bounded hot memory.
Planning costs are explicit proxy units, never mathematical evidence.
"""
from collections import Counter, deque
from time import perf_counter
from rank_anchors import Anchors
from temporal_rank import Rank
from partial_rank import PartialRank
from temporal_algebra import Budget
from temporal_ground import contract_time
import json


def wire_size(obj):
    return len(json.dumps(obj,separators=(',',':')).encode())


def residual(book,k):
    contract_time(k)
    if k<1:raise ValueError('ordinal')
    return (k-book.before-1)%book.N+1 if k>book.before and book.N else None


def distance(j,r):
    # Necessary number of event crossings to select j from an anchor of rank r.
    return j-r if r<j else r-j+1


def choose(anchors, pins, history, capacity, *, recent=()):
    """Greedy facility retention on ordinal-distance objective; no correctness role.
    Fixed endpoint anchors are not charged against the interior capacity.
    """
    if type(capacity)is not int or capacity<0:raise ValueError('capacity')
    if not set(pins)<=anchors.keys():raise ValueError('pins')
    weights=Counter(history); candidates=set(anchors)-set(pins); chosen=set(pins)
    best={j:min(distance(j,anchors[p]) for p in pins) for j in weights}
    age={p:i for i,p in enumerate(recent)}
    while candidates and len(chosen)-len(pins)<capacity:
        def score(p):
            return (sum(w*max(0,best[j]-distance(j,anchors[p])) for j,w in weights.items()),age.get(p,-1),-p)
        p=max(candidates,key=score);candidates.remove(p);chosen.add(p)
        for j in best:best[j]=min(best[j],distance(j,anchors[p]))
    return sorted(chosen)


def plan_seeds(book, forecast, *, slots, scan, full_cost, seed_cost, retention_price=0):
    """Greedy weighted coverage with declared prices and density estimate.
    An acquired ordinal j contributes the exact post-event anchor of rank j.
    Prices and coverage are estimates; execution always independently checked.
    """
    if any(type(x)is not int or x<0 for x in (slots,scan,full_cost,seed_cost,retention_price)):raise ValueError('prices')
    if not book.N:return []
    h=Counter(j for k in forecast if (j:=residual(book,k)) is not None)
    if len(h)>256:raise ValueError('forecast size')
    def price(d):
        phases=(d*book.P+book.N-1)//book.N
        return min(full_cost,phases) if phases<=scan else full_cost
    best={j:min(price(distance(j,r)) for r in book.anchors.values()) for j in h}
    out=[]
    for _ in range(min(slots,len(h))):
        def gain(r):return sum(w*max(0,best[j]-price(distance(j,r))) for j,w in h.items())-seed_cost-retention_price
        if not h.keys()-set(out):break
        r=max(h.keys()-set(out),key=lambda r:(gain(r),-r))
        if gain(r)<=0:break
        out.append(r)
        for j in best:best[j]=min(best[j],price(distance(j,r)))
    return out


class Portfolio:
    """Local producer/receiver driver; every fact admitted before use.
    full_mode: retain, ephemeral (drop after use), or adaptive (priced retention).
    """
    def __init__(self,lang,receiver,*,capacity=16,scan=128,policy='demand',full_mode='retain',partial_budget=0,max_work=2_000_000,retention_price_ns=5,window=8):
        if type(capacity)is not int or capacity<0 or type(scan)is not int or not 0<=scan<=100000 or policy not in ('demand','lru','full') or full_mode not in ('retain','ephemeral','adaptive') or type(partial_budget)is not int or not 0<=partial_budget<=1000000 or type(retention_price_ns)is not int or retention_price_ns<0 or type(window)is not int or not 1<=window<=64:raise ValueError('policy')
        self.x=Anchors(lang,receiver.i);self.v=receiver
        if self.x.anchors!=self.v.anchors:raise ValueError('initial book')
        self.capacity=capacity;self.scan=scan;self.policy=policy;self.full_mode=full_mode;self.partial_budget=partial_budget;self.max_work=max_work
        self.full=None;self.partial=None;self.failed_full=False;self.history=deque(maxlen=64);self.recent={};self.clock=0
        self.misses=deque(maxlen=window);self.retention_price_ns=retention_price_ns;self.window=window
        self.stats=Counter();self.stats['peak_anchor_bytes']=wire_size(self.x.anchors)
    def _time(self,key,fn,*a,**kw):
        t=perf_counter();r=fn(*a,**kw);self.stats[key+'_ms']+=(perf_counter()-t)*1000;return r
    def _open(self):
        if self.full is not None:return True
        if self.failed_full:return False
        try:
            candidate=self._time('compile',Rank,self.x.lang,self.x.i,max_work=self.max_work)
        except Budget:
            self.failed_full=True;self.stats['compile_refused']+=1;return False
        p=candidate.packet()
        if not self._time('audit',self.v.open_rank,p):raise ValueError('rank admission')
        self.full=candidate
        self.stats['rank_opens']+=1;self.stats['rank_wire_bytes']+=wire_size(p);self.stats['rank_work']+=self.full.work
        self.rank_bytes=wire_size(p);self.stats['peak_rank_bytes']=max(self.stats['peak_rank_bytes'],self.rank_bytes);return True
    def drop_rank(self):
        self.full=None;self.v.close_rank()
    def _put_select(self,k,z):
        if z['status']=='FOUND' and int(z['time'])>=self.x.D:
            p=(int(z['time'])-self.x.D)%self.x.P;j=residual(self.x,k)
            self.x._anchors.update({p:j-1,p+1:j});self._touch(p);self._touch(p+1)
    def _touch(self,p):
        self.clock+=1;self.recent[p]=self.clock
    def _trim(self,forecast=()):
        pins={0,self.x.P};a=self.x.anchors
        if len(a)-2>self.capacity:
            recent=sorted(self.recent,key=self.recent.get)
            if self.policy=='demand': keep=self._time('plan',choose,a,pins,list(self.history)+list(forecast),self.capacity,recent=recent)
            else:keep=sorted(pins|set(sorted(set(a)-pins,key=lambda p:(self.recent.get(p,-1),p),reverse=True)[:self.capacity]))
            if not self.v.retain(keep,self.capacity):raise AssertionError('retention')
            self.stats['evicted']+=len(a)-len(keep);self.x._anchors={p:a[p] for p in keep};self.recent={p:self.recent[p] for p in keep if p in self.recent}
        assert self.x.anchors==self.v.anchors
        self.stats['peak_anchor_bytes']=max(self.stats['peak_anchor_bytes'],wire_size(self.x.anchors))
    def acquire(self,forecast,*,slots,full_cost,seed_cost,retention_price=0):
        forecast=tuple(forecast)
        if slots>self.capacity//2:raise ValueError('seed capacity')
        chosen=self._time('plan',plan_seeds,self.x,forecast,slots=slots,scan=self.scan,full_cost=full_cost,seed_cost=seed_cost,retention_price=retention_price)
        if not chosen or not self._open():return []
        # One rank proof, many independently verified ordinal anchors.
        for j in chosen:
            k=self.x.before+j;z=self._time('seed',self.full.select,k)
            if not self._time('seed_verify',self.v.admit_exact,k,z):raise AssertionError('seed')
            self.stats['seed_probes']+=z['probes'];self.stats['seed_wire_bytes']+=wire_size(z);self.stats['seeds']+=1;self._put_select(k,z)
        self._trim([j for k in forecast if (j:=residual(self.x,k)) is not None])
        if self.full_mode=='ephemeral':self.drop_rank()
        return chosen
    def _finish(self,result,miss):
        self.misses.append(int(miss))
        if self.full is not None and self.full_mode=='adaptive' and len(self.misses)==self.window:
            # Expected cold reacquisition cost vs declared memory price.  This
            # is an empirical policy; exactness is independent of its choice.
            avg_ns=int(1_000_000*(self.stats['compile_ms']+self.stats['audit_ms'])/max(1,self.stats['rank_opens']))
            if sum(self.misses)*avg_ns < self.window*self.rank_bytes*self.retention_price_ns:
                self.drop_rank();self.stats['adaptive_drops']+=1
        self.stats['resident_rank_byte_queries']+=self.rank_bytes if self.full is not None else 0
        self.stats['resident_anchor_byte_queries']+=wire_size(self.x.anchors)
        return result
    def query(self,k):
        j=residual(self.x,k)
        if j is not None:self.history.append(j)
        self.stats['queries']+=1
        if self.policy!='full' and j is not None:
            book=self.x.anchors
            phase=next((p for p,r in book.items() if r==j-1 and book.get(p+1)==j),None)
            if phase is not None:
                receipt={'index':self.x.i,'phase':str(phase)}
                got=self._time('hit_verify',self.v.admit_hit,k,receipt)
                if got is not None:
                    self._touch(phase);self._touch(phase+1);self.stats['anchor_hits']+=1;self.stats['local_wire_bytes']+=wire_size(receipt);return self._finish(got,False)
        # Necessary rank-distance gate avoids obviously futile local scans.
        if self.policy!='full' and (j is None or min(distance(j,r) for r in self.x.anchors.values())<=self.scan):
            z=self._time('local',self.x.compact,k,budget=self.scan);got=self._time('local_verify',self.v.admit_compact,k,z,budget=self.scan)
            if got is None:raise AssertionError('local receipt')
            self.x.commit(z);self.stats['local_steps']+=z['steps'];self.stats['local_wire_bytes']+=wire_size(z)
            for field in ('anchor','end'):
                if z[field] is not None:self._touch(int(z[field]))
            if got['status']!='UNKNOWN':
                self.stats['local_hits']+=1;self._trim();return self._finish(got,False)
            self.stats['local_misses']+=1
        if self.partial_budget and self.full is None and self.policy!='full':
            if self.partial is None:self.partial=self._time('partial_setup',PartialRank,self.x.lang,self.x.i,suffix_mass=0,scan=min(128,self.scan))
            z=self._time('partial',self.partial.select,k,budget=self.partial_budget);self.stats['partial_work']+=z['work']
            if z['status']!='UNKNOWN':
                if not self._time('partial_verify',self.v.admit_partial,k,z,budget=self.partial_budget):raise AssertionError('partial receipt')
                self._put_select(k,z);self.stats['partial_hits']+=1;self.stats['partial_wire_bytes']+=wire_size(z);self._trim();return self._finish({f:z[f] for f in ('status','time')},False)
            self.stats['partial_misses']+=1
        if self._open():
            z=self._time('full',self.full.select,k);self.stats['full_probes']+=z['probes']
            if z['status']!='UNKNOWN':
                if not self._time('full_verify',self.v.admit_exact,k,z):raise AssertionError('exact receipt')
                self._put_select(k,z) # mirror receiver, then enforce capacity
                self.stats['full_hits']+=1;self.stats['full_wire_bytes']+=wire_size(z)
            self._trim()
            if self.full_mode=='ephemeral':self.drop_rank()
            return self._finish({f:z[f] for f in ('status','time')},True)
        self._trim();self.stats['unknown']+=1;return self._finish({'status':'UNKNOWN','time':None},True)
