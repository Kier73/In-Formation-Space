import random,unittest
from dataclasses import replace
from math import prod,lcm
from ground_network import View,Network,discover,select
from ground_network_verify import verify_selection
from ground_intelligence import Policy,Intelligence,Intention,cycle_reduction
from verify_ground_intelligence import admit_reduction


def pulse(name,r,*,grow=False,cutoff=0,prefix=0):
    return View(name,(31,37) if grow else (31,),((0,tuple(int(i==r%31) for i in range(31))),),2,cutoff,prefix)


def pattern(name,base,shift=0,cutoff=0,prefix=0):
    # f(t) = (t mod 2 == 0 and t mod 3 != 1), shifted.
    z=tuple(int((r+shift)%3!=1) for r in range(base[1]))
    return View(name,base,((1,z),(0,tuple(2 if (r+shift)%2==0 else 0 for r in range(base[0])))),3,cutoff,prefix)


def learn_pair(policy,i,shift,grow,*,train=False,learned=True,limit=64,prefix=False):
    g=Intelligence(policy=policy);a=pulse('A'+str(i),i%31);b=pulse('B'+str(i),i%31-shift,grow=grow,cutoff=3 if prefix else 0,prefix=5 if prefix else 0)
    A=g.observe(a,memory=True);B=g.observe(b)
    k=10**100+17;z=g.realize(Intention(B,k,max_candidates=limit),train=train,learned=learned)
    return g,a,b,z


class IntelligenceTests(unittest.TestCase):
    def test_policy_training_and_generalization(self):
        p=Policy();rng=random.Random(8151)
        for i in range(80):
            grow=bool(i%2);shift=(5 if grow else -3) if rng.random()<.9 else (-3 if grow else 5)
            _,a,b,z=learn_pair(p,i,shift,grow,train=True)
            self.assertEqual(z['time'],select(b,10**100+17)['time'])
        restored=Policy.restore(p.packet());self.assertEqual(restored.packet(),p.packet())
        learned=base=0
        for i in range(80,120):
            grow=bool(i%2);d=5 if grow else -3
            _,a,b,z=learn_pair(restored,i,d,grow);_,_,_,q=learn_pair(restored,i,d,grow,learned=False)
            self.assertEqual(z['time'],q['time']);learned+=z['attempts'];base+=q['attempts']
        self.assertLess(learned,base//2)
        self.assertEqual(restored.packet(),p.packet()) # frozen held-out policy

    def test_wrong_hint_and_budget(self):
        p=Policy();a=pulse('A',0);b=pulse('B',-5)
        for _ in range(20):p.feedback(a,b,-8,True) # malicious but well-formed heuristic
        g=Intelligence(policy=p);A=g.observe(a,memory=True);B=g.observe(b)
        q=g.realize(Intention(B,5,max_candidates=1));self.assertEqual(q['status'],'UNKNOWN');self.assertFalse(g.graph.edges)
        q=g.realize(Intention(B,5));self.assertEqual(q['time'],select(b,5)['time'])
        c=View('incompatible',(31,),((0,tuple(int(i in (1,2)) for i in range(31))),),2)
        C=g.observe(c);self.assertEqual(g.realize(Intention(C,2))['status'],'UNKNOWN')
        packet=p.packet();packet['records'][0][3]=packet['records'][0][2]+1
        with self.assertRaises(ValueError):Policy.restore(packet)

    def test_cycles_and_reduction(self):
        base=(8,9,5,7,11,13,17,19,23,29,31,37,41,43,47)
        a,b,c=[pattern(x,base,j,3,1<<j) for x,j in [('A',0),('B',1),('C',2)]]
        g=Intelligence();A,B,C=[g.observe(x) for x in (a,b,c)]
        def edge(x,y,d):
            e,_=discover(g.graph.views[x],g.graph.views[y],[(d,3)]);self.assertIsNotNone(e);self.assertTrue(g.graph.admit(e));return e.key
        edge(B,A,29);edge(A,B,1);edge(C,A,40);edge(A,C,2)
        learned,_=g.discover_cycles(A);e1,e2=sorted((g.graph.edges[e] for e in learned),key=lambda e:e.shift)
        self.assertEqual((e1.shift,e2.shift),(30,42))
        self.assertEqual(cycle_reduction(g.graph,A,(e1.key,)).period,30)
        reduced=cycle_reduction(g.graph,A,(e1.key,e2.key));self.assertEqual(reduced.period,6)
        self.assertFalse(admit_reduction(g.graph,A,(e1.key,),reduced))
        forged=View(reduced.source,reduced.base,(),0,reduced.cutoff,reduced.prefix)
        self.assertFalse(admit_reduction(g.graph,A,(e1.key,e2.key),forged))
        self.assertTrue(admit_reduction(g.graph,A,(e1.key,e2.key),reduced))
        g.memories.add(reduced.key)
        for k in (1,2,10,10**900+173):
            z=g.realize(Intention(A,k));self.assertEqual(z['time'],select(a,k)['time'])
            self.assertTrue(verify_selection(a,k,z['time']))

    def test_random_reduction(self):
        rng=random.Random(822)
        for i in range(100):
            # small independent truth-table oracle; pulse pattern depends on mod p
            p=rng.choice((2,3,5,7));b=p**2;d=rng.randrange(1,p);prefix=rng.getrandbits(4)
            a=View(str(i),(b,),((0,tuple(int(j%p==d) for j in range(b))),),2,4,prefix)
            graph=Network();graph.register(a)
            e,_=discover(a,a,[(p,4)]);self.assertTrue(graph.admit(e));z=cycle_reduction(graph,a.key,(e.key,))
            self.assertEqual(z.period,p);self.assertTrue(admit_reduction(graph,a.key,(e.key,),z))
            for t in range(100):self.assertEqual(z.bit(t),(prefix>>t)&1 if t<4 else int(t%p==d))
            for k in (1,2,8,10**50+3):self.assertEqual(select(z,k),{**select(z,k),'time':select(a,k)['time']})

    def test_negative_cycle(self):
        a=View('negative',(8,),((0,(1,0,1,0,1,0,1,0)),),2)
        graph=Network();graph.register(a);e,_=discover(a,a,[(-2,2)]);self.assertTrue(graph.admit(e))
        z=cycle_reduction(graph,a.key,(e.key,));self.assertEqual(z.period,2);self.assertTrue(admit_reduction(graph,a.key,(e.key,),z))

    def test_acquisition_is_independently_qualified(self):
        g=Intelligence();v=pulse('cold',3);k=g.observe(v)
        self.assertEqual(g.realize(Intention(k,10))['status'],'UNKNOWN')
        self.assertEqual(g.realize(Intention(k,10,max_work=1,acquire=True))['status'],'UNKNOWN')
        self.assertFalse(g.memories)
        z=g.realize(Intention(k,10,acquire=True));self.assertTrue(z['acquired']);self.assertEqual(z['time'],282)
        self.assertIn(k,g.memories)
        self.assertEqual(g.realize(Intention(k,11))['time'],313)

    def test_typed_expression(self):
        from ground_intelligence import express
        from verify_ground_intelligence import verify_expression
        import copy,json
        g,a,b,z=learn_pair(Policy(),5,5,True)
        k=10**100+17;q=Intention(b.key,k);p=express(q,z)
        self.assertTrue(verify_expression(g.graph,b.key,k,json.loads(json.dumps(p))))
        self.assertFalse(verify_expression(g.graph,b.key,k+1,p))
        bad=copy.deepcopy(p);bad['time']=str(int(bad['time'])+31)
        self.assertFalse(verify_expression(g.graph,b.key,k,bad))
        bad=copy.deepcopy(p);bad['route']['shift']='4'
        self.assertFalse(verify_expression(g.graph,b.key,k,bad))
        c=Intelligence();C=c.observe(pulse('cold',3));r=Intention(C,10,acquire=True)
        self.assertTrue(verify_expression(c.graph,C,10,express(r,c.realize(r))))
        u=Intelligence();U=u.observe(pulse('unknown',5));r=Intention(U,3)
        self.assertFalse(verify_expression(u.graph,U,3,express(r,u.realize(r))))

    def test_checkpoint_replays_proofs(self):
        from ground_intelligence import checkpoint
        from verify_ground_intelligence import restore_checkpoint
        from ground_network import digest
        import copy
        agent,a,b,z=learn_pair(Policy(),5,5,True,train=True)
        packet=checkpoint(agent);restored=restore_checkpoint(packet,expected_views=agent.graph.views)
        self.assertEqual(restored.realize(Intention(b.key,10**100+19))['time'],select(b,10**100+19)['time'])
        self.assertEqual(checkpoint(restored),packet)
        bad=copy.deepcopy(packet);bad['payload']['edges'][0][3]='6';bad['digest']=digest(bad['payload'])
        with self.assertRaises(ValueError):restore_checkpoint(bad)
        with self.assertRaises(ValueError):restore_checkpoint(packet,expected_views=[a.key])
        bad=copy.deepcopy(packet);bad['payload']['memories']=['unknown'];bad['digest']=digest(bad['payload'])
        with self.assertRaises(ValueError):restore_checkpoint(bad)

if __name__=='__main__':unittest.main()
