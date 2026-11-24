import random,unittest,json
from itertools import product
from dataclasses import replace
from ground_network import View,select,Work
from ground_network_verify import verify_selection
from coordinate_language import CoordinateSkill,compile_view,discover,compose,Vocabulary
from verify_coordinate_language import verify_pullback,verify_composition
from family_language import crt
from test_skill_language import random_view


def arbitrary(seed,base=(3,5,7),cutoff=0):
    rng=random.Random(seed);nodes=[];unique={}
    def build(j):
        if j==len(base):return rng.randrange(2)
        ch=tuple(build(j+1) for _ in range(base[j]))
        if len(set(ch))==1:return ch[0]
        row=(j,ch)
        if row not in unique:unique[row]=len(nodes)+2;nodes.append(row)
        return unique[row]
    root=build(0)
    return View('arbitrary:'+str(seed),base,tuple(nodes),root,cutoff,rng.getrandbits(cutoff))


def permutation(a,seed,flip=0):
    r=random.Random(seed);return CoordinateSkill(a.base,tuple(tuple(r.sample(range(m),m)) for m in a.base),flip)


def oracle(a,s,t):
    if t<a.cutoff:return a.bit(t)^s.flip
    x=crt((row[t%m],m) for m,row in zip(s.base,s.maps))
    return a.bit(x+max(0,(a.cutoff-x+a.period-1)//a.period)*a.period)^s.flip


class CoordinateTests(unittest.TestCase):
    def test_random_coupled(self):
        for i in range(120):
            a=arbitrary(i,(3,5,7),i%5);s=permutation(a,i+100,i%2);b,_=compile_view(a,s);b=replace(b,source='anonymous')
            found,stats=discover(a,b);self.assertIsNotNone(found,stats);self.assertTrue(verify_pullback(a,b,found)[0])
            for t in range(a.period+a.cutoff):self.assertEqual(oracle(a,found,t),oracle(a,s,t));self.assertEqual(b.bit(t),oracle(a,s,t))
    def test_random_parity(self):
        for i in range(100):
            a=random_view(i,(4,9,5,7),i%4);s=permutation(a,i,i%2);b,_=compile_view(a,s);z,d=discover(a,b);self.assertIsNotNone(z,d);self.assertTrue(verify_pullback(a,b,z)[0])
    def test_composition_arbitrary_maps(self):
        r=random.Random(57)
        for i in range(100):
            a=arbitrary(i,(3,5,7),i%4);s,u=(CoordinateSkill(a.base,tuple(tuple(r.randrange(m) for _ in range(m)) for m in a.base),r.randrange(2)) for _ in range(2));b,_=compile_view(a,s);c,_=compile_view(b,u);v=compose(s,u);z,_=compile_view(a,v)
            self.assertTrue(verify_composition(s,u,v));self.assertTrue(verify_pullback(a,c,v)[0]);self.assertTrue(verify_pullback(a,z,v)[0])
            self.assertEqual([c.bit(t) for t in range(a.period+a.cutoff)],[oracle(a,v,t) for t in range(a.period+a.cutoff)])
    def test_forgeries_and_budgets(self):
        a=arbitrary(19);s=permutation(a,21);b,_=compile_view(a,s)
        self.assertFalse(verify_pullback(a,b,replace(s,flip=1))[0]);self.assertFalse(verify_pullback(a,b,replace(s,maps=((0,),)+s.maps[1:]))[0]);self.assertFalse(verify_pullback(a,b,s,max_work=1)[0]);self.assertIsNone(discover(a,b,max_work=1)[0])
        self.assertIsNone(discover(a,View('constant',a.base,(),0))[0])
        self.assertFalse(verify_composition(s,s,replace(compose(s,s),flip=1)))
    def test_vocabulary_restore_transfer(self):
        a=arbitrary(1);s=permutation(a,11);b,_=compile_view(a,s);v=Vocabulary();self.assertTrue(v.observe(a,b,s));self.assertFalse(v.observe(a,b,replace(s,flip=1)))
        p=json.loads(json.dumps(v.packet()));views={a.key:a,b.key:b};w=Vocabulary.restore(p,views);u=arbitrary(2);z,_=w.activate(u,s.key);self.assertTrue(verify_pullback(u,z,s)[0]);p['skills'][0][3]^=1
        with self.assertRaises(ValueError):Vocabulary.restore(p,views)
    def test_nonlinear_nonaffine(self):
        # 0,1,2 is an arithmetic progression modulo 11; 0,1,3 is not.
        a=View('a',(11,),((0,tuple(int(x in (0,1,2)) for x in range(11))),),2)
        b=View('b',(11,),((0,tuple(int(x in (0,1,3)) for x in range(11))),),2)
        s,d=discover(a,b);self.assertIsNotNone(s,d);self.assertTrue(verify_pullback(a,b,s)[0])
        self.assertFalse(any(all(b.bit(t)==a.bit(x*t+y) for t in range(11)) for x in range(1,11) for y in range(11)))
        k=10**900+19;r=select(b,k);q,i=divmod(k-1,3);self.assertEqual(int(r['time']),q*11+(0,1,3)[i]);self.assertTrue(verify_selection(b,k,r['time']))
    def test_exhaustive_small_existence(self):
        # Exhaustive comparison for arbitrary unrelated functions and all local permutations.
        from itertools import permutations
        for i in range(40):
            a=arbitrary(i,(2,3));b=arbitrary(i+100,(2,3))
            possible=any(all(b.bit(t)==oracle(a,CoordinateSkill(a.base,(p,q),c),t) for t in range(6)) for p,q,c in product(permutations(range(2)),permutations(range(3)),(0,1)))
            z,_=discover(a,b);self.assertEqual(z is not None,possible)
    def test_induced_many_to_one(self):
        from coordinate_language import discover_collapsing
        rng=random.Random(132)
        for i in range(80):
            a=arbitrary(i,(3,5,7),i%3);s=CoordinateSkill(a.base,tuple(tuple(rng.randrange(m) for _ in range(m)) for m in a.base),i%2);b,_=compile_view(a,s);z,d=discover_collapsing(a,b,max_work=2000000);self.assertIsNotNone(z,d);self.assertTrue(verify_pullback(a,b,z)[0]);self.assertEqual([b.bit(t) for t in range(a.period+a.cutoff)],[oracle(a,z,t) for t in range(a.period+a.cutoff)])
        # Completely erase an observed dimension; permutation discovery cannot.
        a=View('one',(7,),((0,(1,0,0,0,0,0,0)),),2);b=View('empty',(7,),(),0)
        self.assertIsNone(discover(a,b)[0]);z,_=discover_collapsing(a,b);self.assertIsNotNone(z);self.assertTrue(verify_pullback(a,b,z)[0])
        self.assertIsNone(discover_collapsing(a,b,max_work=1)[0])
    def test_exhaustive_collapse_existence(self):
        from coordinate_language import discover_collapsing
        for i in range(30):
            a=arbitrary(i,(2,3));b=arbitrary(i+100,(2,3));possible=any(all(b.bit(t)==oracle(a,CoordinateSkill(a.base,(p,q),c),t) for t in range(6)) for p,q,c in product(product(range(2),repeat=2),product(range(3),repeat=3),(0,1)))
            z,_=discover_collapsing(a,b);self.assertEqual(z is not None,possible)
