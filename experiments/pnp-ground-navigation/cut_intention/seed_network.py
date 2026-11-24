"""CIG-034A adapter: native temporal relationship graph + actual CIG rank Seeds.

The graph's views are snapshots of independently admitted source observations.
The producer/receiver Seed books remain CIG-029A/032A objects. No external
physical authority or arbitrary state-space equivalence is asserted.
"""
from ground_network import View, Network, discover, compose, integer
from ground_network_verify import replay, lift_time
from verify_temporal_algebra import Admission
from verify_temporal_ground import Receiver, digest
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver


def snapshot(lang, index, identity):
    if type(index) is not int or not 0<=index<len(lang.roots):raise ValueError('output')
    # Drop unrelated nodes, and canonicalize the reachable subgraph in the
    # existing topological order. Later unrelated expressions do not change it.
    root=lang.roots[index];todo=[root];live=set()
    while todo:
        r=todo.pop()
        if r<2 or r in live:continue
        live.add(r);todo.extend(lang.d.nodes[r-2][1])
    trans={0:0,1:1};nodes=[]
    for r in sorted(live):
        j,z=lang.d.nodes[r-2];nodes.append((j,tuple(trans[k] for k in z)));trans[r]=len(nodes)+1
    return View(identity,tuple(lang.d.base),tuple(nodes),trans[root],lang.D,lang.prefix[index])


class SeedNetwork:
    def __init__(self):
        self.graph=Network();self.admissions={};self.seeds={}
    def register(self,receiver,receipt,index):
        if type(receiver) is not Receiver:raise ValueError('source receiver')
        a=Admission(receiver,receipt)
        identity=digest(['CIG-034A',receiver.key,str(receiver.initial),index])
        view=snapshot(a,index,identity);self.graph.register(view)
        self.admissions[view.key]=(a,index)
        return view.key
    def attach(self,key,memory,checked):
        if key not in self.admissions or type(memory) is not Memory or type(checked) is not MemoryReceiver:raise ValueError('Seed')
        _,i=self.admissions[key];v=self.graph.views[key]
        if snapshot(memory.lang,i,v.source)!=v or snapshot(checked.a,i,v.source)!=v:
            raise ValueError('Seed Ground mismatch')
        self.seeds[key]=(memory.book(i),checked.book(i))
    def link(self,source,target,candidates,*,cost=1,max_work=500000):
        views=self.graph.views;e,work=discover(views[source],views[target],candidates,cost=cost,max_work=max_work)
        if e is None or not self.graph.admit(e,max_work=max_work):return None,work
        return e,work
    def shortcut(self,path,*,cost=1):
        e=compose(self.graph,path,cost=cost)
        if not self.graph.admit_composite(e,path):raise ValueError('composition')
        return e
    def accept(self,target,k,route,rank_packet,*,budget=128):
        """Only a checked endpoint ordinal can be transferred through a path."""
        bound=replay(self.graph,target,k,route)
        if bound is None or bound[0] not in self.seeds:return None
        book=self.seeds[bound[0]][1];res=book.admit_compact(bound[1],rank_packet,budget=budget)
        if res is None:return None
        if res['status']=='FOUND':
            t=lift_time(self.graph,target,k,route,int(res['time']))
            if t is None:return None
            return dict(status='FOUND',time=str(t))
        if res['status']=='UNREACHABLE':return dict(status='UNREACHABLE',time=None)
        return dict(status='UNKNOWN',time=None)
    def activate(self,target,k,*,budget=128,max_hops=8,max_states=10000,max_attempts=4):
        integer(k,1);integer(max_attempts,1)
        if type(budget) is not int or not 0<=budget<=100000 or max_attempts>64:raise ValueError('budget')
        attempts=[];excluded=set()
        def offer(key,ordinal):
            if key not in self.seeds or (key,ordinal) in excluded:return None
            book=self.seeds[key][0]
            if ordinal<=book.before or not book.N:return 0
            _,j=divmod(ordinal-book.before-1,book.N);j+=1
            # Rank distance is only a heuristic; the independent proof decides.
            est=min((j-r if r<j else r-j+1) for r in book.anchors.values())
            return min(est,budget+1)
        for _ in range(max_attempts):
            route,states=self.graph.plan(target,k,offer,max_hops=max_hops,max_states=max_states)
            if route is None:break
            b=self.seeds[route.source][0];z=b.compact(route.source_ordinal,budget=budget)
            res=self.accept(target,k,route,z,budget=budget)
            if res is None:raise ValueError('independent endpoint/route refusal')
            b.commit(z);attempts.append((route,z,states))
            if res['status']!='UNKNOWN':return res,attempts
            excluded.add((route.source,route.source_ordinal))
        return dict(status='UNKNOWN',time=None),attempts
