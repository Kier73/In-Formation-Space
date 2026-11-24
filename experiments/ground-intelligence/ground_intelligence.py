"""PGI-001: a procedural, trainable controller for admitted temporal Grounds.

Learned policy is a heuristic, never evidence.  The CIG-034A Network owns
mathematical admissions; source-specific adapters retain source qualification.
"""
from dataclasses import dataclass
from math import gcd, prod
from ground_network import View, Edge, Network, discover, compose, integer
from ground_network_verify import verify_realization, verify_selection


class Policy:
    """Small contextual success table. No hidden model or external dependencies."""
    def __init__(self, shifts=tuple(range(-8,9))):
        if type(shifts) is not tuple or not shifts or len(shifts)>64 or len(set(shifts))!=len(shifts):
            raise ValueError('shift grammar')
        for d in shifts: integer(d)
        self.shifts=shifts; self.hits={}; self.attempts={}

    @staticmethod
    def context(a,b):
        # Period ratio and relative transient shape are observable, not proof.
        return ('same' if a.period==b.period else 'grow' if a.period<b.period else 'shrink',
                'prefix' if a.cutoff or b.cutoff else 'tail')

    def order(self,a,b):
        c=self.context(a,b)
        # Laplace-smoothed empirical success, then original palette order.
        from fractions import Fraction
        return tuple(sorted(self.shifts,key=lambda d:(-Fraction(1+self.hits.get((c,d),0),2+self.attempts.get((c,d),0)),self.shifts.index(d))))

    def feedback(self,a,b,d,success):
        if d not in self.shifts or type(success) is not bool:raise ValueError('feedback')
        key=(self.context(a,b),d);self.attempts[key]=self.attempts.get(key,0)+1
        if success:self.hits[key]=self.hits.get(key,0)+1

    def packet(self):
        return {'schema':'pgi.policy.v1','shifts':list(self.shifts),'records':[
            [list(c),d,n,self.hits.get((c,d),0)] for (c,d),n in sorted(self.attempts.items())]}

    @classmethod
    def restore(cls,p):
        if type(p) is not dict or set(p)!={'schema','shifts','records'} or p['schema']!='pgi.policy.v1':raise ValueError('policy packet')
        obj=cls(tuple(p['shifts'])); rows=p['records']
        if type(rows) is not list or len(rows)>6*len(obj.shifts):raise ValueError('policy rows')
        for c,d,n,h in rows:
            c=tuple(c);key=(c,d)
            if len(c)!=2 or c[0] not in ('same','grow','shrink') or c[1] not in ('prefix','tail') or type(d) is not int or d not in obj.shifts or key in obj.attempts:raise ValueError('policy key')
            integer(n,1);integer(h,0)
            if h>n:raise ValueError('policy counts')
            obj.attempts[key]=n;obj.hits[key]=h
        return obj


@dataclass(frozen=True)
class Intention:
    target: str
    ordinal: int
    max_candidates: int=64
    max_work: int=500000
    max_hops: int=8
    acquire: bool=False


class Intelligence:
    """Observe -> select -> attempt -> qualify -> retain -> express.

    The native endpoint is an exact mathematical View, not a physical source
    attestation.  CIG's SeedNetwork can supply a separate qualified endpoint.
    """
    def __init__(self,graph=None,policy=None):
        self.graph=Network() if graph is None else graph
        self.policy=Policy() if policy is None else policy
        self.memories=set()

    def observe(self,v,*,memory=False):
        k=self.graph.register(v)
        if memory:self.memories.add(k)
        return k

    def link(self,source,target,*,train=False,learned=True,max_candidates=64,max_work=500000):
        integer(max_candidates,0);integer(max_work,1)
        a,b=self.graph.views[source],self.graph.views[target]
        order=self.policy.order(a,b) if learned else self.policy.shifts
        work=tries=0
        for d in order[:max_candidates]:
            if work>=max_work:break
            # The grammar proposes the earliest shared periodic tail.  It does
            # not claim to find the minimal suffix cutoff or arbitrary mappings.
            s=max(0,b.cutoff,a.cutoff-d,-d)
            e,w=discover(a,b,[(d,s)],cost=1,max_work=max_work-work)
            tries+=1;work+=w
            ok=e is not None and self.graph.admit(e,max_work=max_work)
            if train:self.policy.feedback(a,b,d,ok)
            if ok:return e,{'attempts':tries,'discovery_work':work}
        return None,{'attempts':tries,'discovery_work':work}

    def realize(self,request,*,train=False,learned=True):
        if type(request) is not Intention or request.target not in self.graph.views:raise ValueError('intention')
        integer(request.ordinal,1);integer(request.max_candidates,0);integer(request.max_work,1);integer(request.max_hops,0)
        if type(request.acquire) is not bool:raise ValueError('acquire')
        # One endpoint can fail its rank budget. Try others without mistaking
        # failure for a proof of unreachability.
        excluded=set(); attempts=work=states=0
        def route():
            return self.graph.plan(request.target,request.ordinal,
                lambda key,k:0 if key in self.memories and (key,k) not in excluded else None,
                max_hops=request.max_hops)
        for stage in range(2):
            for _ in range(len(self.memories)+1):
                r,n=route();states+=n
                if r is None:break
                from ground_network import select
                z=select(self.graph.views[r.source],r.source_ordinal,max_work=request.max_work)
                work+=z['work']
                if z['status']=='FOUND':
                    t=verify_realization(self.graph,request.target,request.ordinal,r,z['time'],max_work=request.max_work)
                    if t is not None:return dict(status='FOUND',time=t,route=r,attempts=attempts,work=work,states=states)
                excluded.add((r.source,r.source_ordinal))
            if stage:break
            # Learn bridges only within an explicit global discovery budget.
            for key in sorted(self.memories):
                if key==request.target or attempts>=request.max_candidates or work>=request.max_work:continue
                _,q=self.link(key,request.target,train=train,learned=learned,max_candidates=request.max_candidates-attempts,max_work=request.max_work-work)
                attempts+=q['attempts'];work+=q['discovery_work']
        if request.acquire:
            from ground_network import select
            view=self.graph.views[request.target];z=select(view,request.ordinal,max_work=request.max_work);work+=z['work']
            if z['status']=='FOUND' and verify_selection(view,request.ordinal,z['time'],max_work=request.max_work):
                self.memories.add(view.key)
                return dict(status='FOUND',time=z['time'],route=None,attempts=attempts,work=work,states=states,acquired=True)
        return dict(status='UNKNOWN',time=None,attempts=attempts,work=work,states=states)

    def learn_cycle(self,path,*,cost=1):
        e=compose(self.graph,path,cost=cost)
        if e.source!=e.target or not e.shift:raise ValueError('nonzero closed path required')
        if not self.graph.admit_composite(e,path):raise ValueError('cycle proof refused')
        return e


    def discover_cycles(self,key,*,max_hops=4,max_states=1000):
        """Learn nonzero simple closed paths from admitted edges only."""
        integer(max_hops,2);integer(max_states,1)
        if key not in self.graph.views or max_hops>64:raise ValueError('cycle search')
        incoming={}
        for e in self.graph.edges.values():incoming.setdefault(e.target,[]).append(e)
        todo=[(key,(),frozenset((key,)),0)];used=0;found=[];seen=set()
        while todo and used<max_states:
            node,path,visited,dt=todo.pop();used+=1
            for e in incoming.get(node,()):
                if used>=max_states:break
                used+=1
                nxt=e.source;p=path+(e.key,);d=dt+e.shift
                if nxt==key:
                    if d and d not in seen:
                        proof=e if not path else self.learn_cycle(p)
                        found.append(proof.key);seen.add(d)
                elif nxt not in visited and len(p)<max_hops:
                    todo.append((nxt,p,visited|{nxt},d))
        return tuple(found),used


def cycle_reduction(graph,key,cycles):
    """Propose a reduced observation period from already admitted self edges.

    Tail equality extends to the original periodic cutoff by adding multiples
    of the known ambient period. Bezout gives gcd(P, all shifts) as a period.
    Restrict CRT digits to that period, retaining the original finite prefix.
    """
    old=graph.views[key];g=old.period
    if type(cycles) is not tuple or not cycles or len(cycles)>64:raise ValueError('cycles')
    for eid in cycles:
        e=graph.edges[eid]
        if e.source!=key or e.target!=key or not e.shift:raise ValueError('not a recurrence')
        if e.offset*old.period!=e.shift*old.total:raise ValueError('cycle density')
        g=gcd(g,abs(e.shift))
    rad=[]
    for b in old.base:rad.append(gcd(b,g))
    base=tuple(b for b in rad if b>1);levels={j:i for i,j in enumerate(j for j,b in enumerate(rad) if b>1)}
    nodes=[];unique={};ids={0:0,1:1}
    for i,(j,ks) in enumerate(old.nodes,2):
        z=tuple(ids[k] for k in ks[:rad[j]])
        if len(set(z))==1:ids[i]=z[0];continue
        row=(levels[j],z)
        if row not in unique:unique[row]=len(nodes)+2;nodes.append(row)
        ids[i]=unique[row]
    new=View('pgi-cycle:'+key+':'+str(g),base,tuple(nodes),ids[old.root],old.cutoff,old.prefix)
    return new


def checkpoint(agent):
    """Portable mathematical memory, not host identity or external attestation."""
    from ground_network import digest
    views=agent.graph.views;edges=agent.graph.edges;origins=agent.graph.origins
    payload={'schema':'pgi.checkpoint.v1','policy':agent.policy.packet(),
        'views':[[v.key,v.source,list(v.base),[[j,list(ks)] for j,ks in v.nodes],v.root,v.cutoff,str(v.prefix)] for v in sorted(views.values(),key=lambda v:v.key)],
        'edges':[[e.key,e.source,e.target,str(e.shift),str(e.start),str(e.source_before),str(e.target_before),str(e.cost),list(origins[e.key])] for e in edges.values()],
        'memories':sorted(agent.memories)}
    return {'payload':payload,'digest':digest(payload)}


def express(request,result):
    """Express a typed intention result as a portable, independently checkable record."""
    if type(request) is not Intention or result['status'] not in ('FOUND','UNKNOWN'):
        raise ValueError('expression')
    route=result.get('route')
    return {'schema':'pgi.expression.v1','target':request.target,'ordinal':str(request.ordinal),
        'status':result['status'],'time':None if result['time'] is None else str(result['time']),
        'route':None if route is None else {'edges':list(route.edges),'source':route.source,
            'source_ordinal':str(route.source_ordinal),'shift':str(route.shift),'cost':str(route.cost)}}
