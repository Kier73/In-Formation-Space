import unittest,random,copy,json
from test_output_time import prepare
from run_output_time import expr_eval
from run_temporal_ground import step
from disjunctive_time import seek
from verify_disjunctive_time import verify

class DisjunctiveTests(unittest.TestCase):
    def test_random(self):
        rng=random.Random(23023)
        for _ in range(40):
            k=rng.randrange(3,9);w=1;p=list(range(k));rng.shuffle(p);f=[[rng.randrange(2) for j in range(2)] for i in p];initial=rng.getrandbits(k)
            # distinct leaves per immediate gate to avoid degenerate generator rows
            e=[('xor',('and',0,1),k-1),('or',('xor',0,k-1),1)]
            nav,rec=prepare(k,w,p,f,initial,e)
            for _ in range(10):
                targets=[rng.choice([0,1,None]) for j in e];start=rng.randrange(25);u=initial
                for t in range(start):u=step(u,k,w,p,f)
                t=start;seen=set();expected=None
                while u not in seen:
                    if all(b is None or expr_eval(x,u)==b for x,b in zip(e,targets)):expected=t;break
                    seen.add(u);u=step(u,k,w,p,f);t+=1
                for mode in (0,2,16):
                    r=seek(nav,initial,targets,start,interval_steps=mode)
                    self.assertTrue(verify(rec,targets,start,r,interval_steps=mode),(r,mode))
                    self.assertEqual(int(r['time']) if r['status']=='FOUND' else None,expected)
    def test_width_two_random(self):
        rng=random.Random(9023)
        for _ in range(20):
            k=6;w=2;p=list(range(3));rng.shuffle(p);f=[[rng.randrange(4) for j in range(4)] for i in p];initial=rng.getrandbits(k)
            e=[('xor',('and',0,2),4),('or',1,5)]
            nav,rec=prepare(k,w,p,f,initial,e)
            for _ in range(5):
                targets=[rng.choice([0,1,None]) for j in e];start=rng.randrange(12);u=initial
                for t in range(start):u=step(u,k,w,p,f)
                t=start;seen=set();expected=None
                while u not in seen:
                    if all(b is None or expr_eval(x,u)==b for x,b in zip(e,targets)):expected=t;break
                    seen.add(u);u=step(u,k,w,p,f);t+=1
                for mode in (0,2,16):
                    r=seek(nav,initial,targets,start,interval_steps=mode)
                    self.assertTrue(verify(rec,targets,start,r,interval_steps=mode))
                    self.assertEqual(int(r['time']) if r['status']=='FOUND' else None,expected)
    def test_second_alternative_forced(self):
        # Two cycles of lengths 3 and 5, one marker each. A is at t=0 mod 15,
        # B at t=1 mod 15. The second output excludes A.
        p=[2,0,1,7,3,4,5,6];initial=(1<<0)|(1<<3)
        e=[('or',('and',0,3),('and',1,4)),0]
        nav,rec=prepare(8,1,p,[[0,1]]*8,initial,e)
        for mode in (0,16):
            r=seek(nav,initial,[1,0],0,interval_steps=mode)
            self.assertEqual(r['time'],'1');self.assertTrue(verify(rec,[1,0],0,r,interval_steps=mode))
    def test_forgeries(self):
        nav,rec=prepare(3,1,[2,0,1],[[0,1]]*3,1,[('xor',0,1)])
        r=seek(nav,1,[0],interval_steps=0);self.assertTrue(verify(rec,[0],0,r,interval_steps=0));self.assertTrue(r['trace'])
        for key,value in [('time','5'),('initial','2'),('key','bad'),('nodes',True),('pairs',0),('trace',r['trace'][:-1]),('trace',r['trace']+r['trace'][:1]),('trace',[[0,999]]),('status','UNREACHABLE')]:
            z=copy.deepcopy(r);z[key]=value;self.assertFalse(verify(rec,[0],0,z,interval_steps=0),key)
        z=copy.deepcopy(r);z['terminal']['code']='0';self.assertFalse(verify(rec,[0],0,z,interval_steps=0))
        self.assertTrue(verify(rec,[0],0,json.loads(json.dumps(r)),interval_steps=0))
        r=seek(nav,1,[0]);z=copy.deepcopy(r);z['leaps'][0]='2';self.assertFalse(verify(rec,[0],0,z))
        z=copy.deepcopy(r);z['leaps'].pop();self.assertFalse(verify(rec,[0],0,z))
    def test_budgets(self):
        nav,rec=prepare(3,1,[2,0,1],[[0,1]]*3,1,[('xor',0,1)])
        for kw in [dict(max_cells=1),dict(max_pairs=1,interval_steps=0),dict(max_nodes=1,interval_steps=0)]:
            r=seek(nav,1,[0],**kw);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(verify(rec,[0],0,r,**kw))
    def test_contradiction(self):
        nav,rec=prepare(3,1,[2,0,1],[[0,1]]*3,1,[('and',0,1)])
        for mode in (0,2,16):
            r=seek(nav,1,[1],interval_steps=mode);self.assertEqual(r['status'],'UNREACHABLE');self.assertTrue(verify(rec,[1],0,r,interval_steps=mode))
    def test_transient_and_huge_time(self):
        nav,rec=prepare(2,1,[0,1],[[0,0],[0,1]],3,[('and',0,1)])
        for start,expected in [(0,0),(1,None),(10**1000+173,None)]:
            r=seek(nav,3,[1],start);self.assertTrue(verify(rec,[1],start,r));self.assertEqual(int(r['time']) if r['status']=='FOUND' else None,expected)
    def test_contract(self):
        nav,rec=prepare(2,1,[1,0],[[0,1]]*2,1,[('or',0,1)])
        for x in [[],[True],[2],(1,)]:self.assertRaises(ValueError,seek,nav,1,x)
        self.assertRaises(ValueError,seek,nav,1,[1],interval_steps=-1)
        self.assertRaises(ValueError,seek,nav,1,[1],max_nodes=True)
        r=seek(nav,1,[None],10**1000);self.assertTrue(verify(rec,[None],10**1000,r))
    def test_overlap_and_mixed_sign(self):
        nav,rec=prepare(4,1,[3,0,1,2],[[0,1]]*4,1,[('or',0,1),('xor',1,2)])
        for targets in [[1,1],[1,0],[0,1],[0,0]]:
            r=seek(nav,1,targets,0,interval_steps=0);self.assertTrue(verify(rec,targets,0,r,interval_steps=0))
            e=[i for i in range(4) if all(b==expr_eval(x,nav.jump(1,i)) for b,x in zip(targets,[('or',0,1),('xor',1,2)]))];self.assertEqual(int(r['time']) if r['status']=='FOUND' else None,min(e) if e else None)

if __name__=='__main__':unittest.main()
