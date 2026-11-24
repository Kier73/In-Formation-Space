import random
import unittest
from dataclasses import replace
from itertools import product
from math import lcm,prod
from ground_network import View, Edge, Network, discover, Work, select, Exhausted, compose
from ground_network_verify import verify_edge, replay, lift_time, verify_realization, verify_selection, verify_composite


def word(name,base,values,cutoff=0,prefix=0):
    """Test-only construction by explicit small-period truth table."""
    nodes=[]; unique={}; P=prod(base)
    def visit(j,r,m):
        if j==len(base):return int(values[r])
        b=base[j]; kids=tuple(visit(j+1,r+m*((a-r)*pow(m,-1,b)%b),m*b) for a in range(b))
        if len(set(kids))==1:return kids[0]
        row=(j,kids)
        if row not in unique:unique[row]=len(nodes)+2;nodes.append(row)
        return unique[row]
    assert len(values)==P
    root=visit(0,0,1)
    return View(name,tuple(base),tuple(nodes),root,cutoff,prefix)


def relation(source,target,shift,start,cost=1):
    e,w=discover(source,target,[(shift,start)],cost=cost)
    assert e is not None,(source.source,target.source,shift,start,w)
    return e


class GroundNetworkTests(unittest.TestCase):
    def test_random_rank_and_edge_oracle(self):
        rng=random.Random(3401); comparisons=0
        bases=[(),(2,),(4,),(3,),(2,3),(4,3),(2,9),(2,3,5)]
        for n in range(240):
            a,b=rng.choice(bases),rng.choice(bases)
            v=word('a'+str(n),a,[rng.randrange(2) for _ in range(prod(a))],rng.randrange(5),0)
            d=rng.randrange(5); z=word('b'+str(n),b,[rng.randrange(2) for _ in range(prod(b))],d,rng.getrandbits(d))
            for g in (v,z):
                for t in range(60):self.assertEqual(g.rank(t),sum(g.bit(j) for j in range(t)))
                ts=[t for t in range(150) if g.bit(t)]
                for k,t in enumerate(ts[:5],1):
                    self.assertEqual(select(g,k)['time'],t);self.assertTrue(verify_selection(g,k,t))
            for dt in (-3,0,2):
                s=max(0,-dt)+rng.randrange(4)
                end=max(s,z.cutoff,v.cutoff-dt)+lcm(v.period,z.period)
                good=all(v.bit(t+dt)==z.bit(t) for t in range(s,end));comparisons+=1
                e,_=discover(v,z,[(dt,s)])
                self.assertEqual(e is not None,good)
                claim=Edge(v.key,z.key,dt,s,v.rank(s+dt),z.rank(s))
                self.assertEqual(verify_edge({v.key:v,z.key:z},claim),good)
        self.assertEqual(comparisons,720)

    def test_random_compatible_suffix_and_composition(self):
        rng=random.Random(3402)
        for n in range(160):
            base=rng.choice([(2,3),(4,3),(2,9),(2,3,5)]);P=prod(base)
            root=word('root',base,[rng.randrange(2) for _ in range(P)],2,rng.getrandbits(2))
            views=[root]; graph=Network();graph.register(root)
            for j in range(3):
                old=views[-1];dt=rng.randrange(-3,4);start=max(old.cutoff-dt,0,-dt)+rng.randrange(3)
                new=word(str(j),base,[old.bit((t+dt)%P+P*5) for t in range(P)],start,rng.getrandbits(start))
                graph.register(new);e=relation(old,new,dt,start);self.assertTrue(graph.admit(e));views.append(new)
            target=views[-1]
            path=tuple(reversed(list(graph.edges)))
            edge=compose(graph,path,cost=0)
            self.assertTrue(verify_composite(graph,edge,path));self.assertTrue(verify_edge(graph.views,edge))
            self.assertFalse(graph.admit_composite(replace(edge,source_before=edge.source_before+1),path))
            self.assertTrue(graph.admit_composite(edge,path));self.assertEqual(graph.origins[edge.key],path)
            for k in (1,5,20,10**100+17):
                r,_=graph.plan(target.key,k,lambda key,q:0 if key==root.key else None)
                if r is None:continue
                expected=select(target,k);source=select(root,r.source_ordinal)
                if expected['status']=='FOUND':
                    self.assertEqual(verify_realization(graph,target.key,k,r,source['time']),expected['time'])
                self.assertIsNone(replay(graph,target.key,k,replace(r,shift=r.shift+1)))

    def test_costed_paths_and_scope(self):
        a=word('a',(2,3),[1,0,0,1,0,0]);b=word('b',(3,),[0,0,1]);c=word('c',(2,3),[0,1,0,0,1,0],2,3)
        graph=Network();[graph.register(v) for v in (a,b,c)]
        # B(t)=A(t+1), C(t)=B(t+1) only after C's independent prefix.
        ab=relation(a,b,1,0,2);bc=relation(b,c,1,2,3);ac=relation(a,c,2,2,9)
        for e in (ab,bc,ac):self.assertTrue(graph.admit(e))
        offer=lambda node,k:4 if node==a.key else None
        self.assertIsNone(graph.plan(c.key,1,offer)[0]);self.assertIsNone(graph.plan(c.key,2,offer)[0])
        r,_=graph.plan(c.key,10**900+9,offer);self.assertEqual(r.edges,(bc.key,ab.key));self.assertEqual(r.cost,9)
        s=select(a,r.source_ordinal);self.assertEqual(verify_realization(graph,c.key,r.ordinal,r,s['time']),select(c,r.ordinal)['time'])
        self.assertIsNone(replay(graph,c.key,r.ordinal,replace(r,edges=(ab.key,bc.key))))
        self.assertIsNone(replay(graph,c.key,r.ordinal+1,r));self.assertIsNone(replay(graph,c.key,r.ordinal,replace(r,source_ordinal=r.source_ordinal+1)))
        self.assertIsNone(verify_realization(graph,c.key,r.ordinal,r,s['time']+3))
        self.assertFalse(graph.admit(replace(bc,source_before=bc.source_before+1)))
        self.assertFalse(graph.admit(replace(bc,start=0)))
        self.assertFalse(graph.admit(replace(bc,cost=-1)))
        self.assertFalse(graph.admit(bc,max_work=1));self.assertIsNone(graph.plan(c.key,r.ordinal,offer,max_hops=0)[0])
        self.assertIsNone(graph.plan(c.key,r.ordinal,offer,max_states=1)[0])
        # The direct route becomes cheaper if a different endpoint is available.
        r2,_=graph.plan(c.key,r.ordinal,lambda node,k:0 if node==b.key else 4 if node==a.key else None)
        self.assertEqual(r2.edges,(bc.key,))
        composite=compose(graph,(bc.key,ab.key),cost=1)
        self.assertTrue(graph.admit_composite(composite,(bc.key,ab.key)))
        self.assertEqual(graph.plan(c.key,r.ordinal,offer)[0].edges,(composite.key,))
        self.assertFalse(graph.admit_composite(replace(composite,start=1),(bc.key,ab.key)))
        self.assertFalse(graph.admit_composite(composite,(ab.key,bc.key)))
        self.assertFalse(graph.admit_composite(composite,('fake',ab.key)))

    def test_bounded_cost_optimality_and_cycles(self):
        rng=random.Random(341)
        for n in range(60):
            g=Network();vs=[View(str(j),(),(),1) for j in range(5)]
            for v in vs:g.register(v)
            adj={v.key:[] for v in vs}
            for a,b in product(vs,repeat=2):
                if rng.random()<.35:
                    c=rng.randrange(5);e=relation(a,b,0,0,c);self.assertTrue(g.admit(e));adj[b.key].append((a.key,c))
            costs={v.key:rng.randrange(8) for v in vs if rng.random()<.4}
            def enumerate_walks(node,h):
                vals=[costs[node]] if node in costs else []
                if h:
                    vals.extend(c+u for dest,c in adj[node] for u in enumerate_walks(dest,h-1))
                return vals
            ans=enumerate_walks(vs[0].key,4);r,_=g.plan(vs[0].key,100,lambda v,k:costs.get(v),max_hops=4)
            self.assertEqual(r.cost if r else None,min(ans) if ans else None)
        g=Network();a=View('cycle',(),(),1);g.register(a);e=relation(a,a,2,0);self.assertTrue(g.admit(e))
        r,_=g.plan(a.key,1,lambda node,k:0 if k==5 else None,max_hops=3)
        self.assertEqual(r.edges,(e.key,e.key));self.assertEqual(r.source_ordinal,5);self.assertEqual(verify_realization(g,a.key,1,r,4),0)


    def test_reverse_time_suffix_and_finite_events(self):
        a=word('a',(2,),[1,0],1,0);b=word('b',(4,),[1,0,1,0],3,5)
        e=relation(a,b,-2,3);g=Network();g.register(a);g.register(b);self.assertTrue(g.admit(e))
        r,_=g.plan(b.key,5,lambda node,k:0 if node==a.key else None);self.assertEqual(r.shift,-2)
        self.assertEqual(verify_realization(g,b.key,5,r,select(a,r.source_ordinal)['time']),select(b,5)['time'])
        finite=View('finite',(),(),0,3,5)
        self.assertEqual(select(finite,2)['time'],2);self.assertEqual(select(finite,3)['status'],'UNREACHABLE')
        self.assertFalse(verify_selection(finite,3,2))

    def test_large_sparse_crt(self):
        base=(2,3,5,7,11,13,17,19,23,29,31,37,41,43,47)
        def atom(name,shift,extra=False):
            bs=base+((53,) if extra else ());nodes=[];root=1
            for j in reversed(range(len(base))):
                kids=tuple(root if r==(-shift)%bs[j] else 0 for r in range(bs[j]));nodes.append((j,kids));root=len(nodes)+1
            return View(name,bs,tuple(nodes),root)
        a,b,c=atom('a',0),atom('b',1,True),atom('c',3)
        g=Network();[g.register(v) for v in (a,b,c)]
        for x,y,d in ((a,b,1),(b,c,2)):
            e,w=discover(x,y,[(0,0),(d,0)]);self.assertIsNotNone(e);self.assertLess(w,20000);self.assertTrue(g.admit(e))
        k=10**900+17;r,_=g.plan(c.key,k,lambda node,q:0 if node==a.key else None)
        self.assertEqual(r.shift,3);s=select(a,r.source_ordinal);self.assertEqual(verify_realization(g,c.key,k,r,s['time']),select(c,k)['time'])
        self.assertEqual(a.period,614889782588491410)

    def test_schema_and_budget(self):
        for base in ((6,),(2,4),(3,2)):
            with self.assertRaises(ValueError):View('bad',base,(),0)
        with self.assertRaises(ValueError):View('bad',(2,),((0,(0,2)),),2)
        with self.assertRaises(ValueError):View('bad',(2,),((0,(1,1)),),2)
        v=word('a',(2,3),[1,0,1,0,0,1]);z=word('b',(2,3),[1,0,1,0,0,1]);e,w=discover(v,z,[(0,0)],max_work=1);self.assertIsNone(e)
        self.assertEqual(select(v,3,max_work=1)['status'],'UNKNOWN')

if __name__=='__main__':unittest.main()
