import unittest,random,copy,json
from interpolant_ground import synthesize,evaluate,InterpolantLanguage
from verify_interpolant_ground import verify,decode
from test_global_sufficiency import oracle
from verify_composed_ground import accepted
from heavy_ground import xor_encoding
from test_proof_refinement import brute


def chain(k,mixed=True,seed=73):
    # Observations are OR predicates, no supplied observed singleton variables.
    # Local OR aliases feed a chain of XOR / AND functions. Shuffle all labels.
    n=4*k-1;s=[];q=[];prev=None
    for i in range(k):
        a,b,z=3*i+1,3*i+2,3*i+3;q.append((a,b));s.extend([(-a,z),(-b,z),(a,b,-z)])
        if prev is None:prev=z;continue
        t=3*k+i
        if mixed and i%2:s.extend([(-prev,-z,t),(prev,-t),(z,-t)])
        else:s.extend(xor_encoding((prev,z,t),0))
        prev=t
    rng=random.Random(seed);labels=list(range(1,n+1));rng.shuffle(labels)
    def move(c):return tuple(sorted(((1 if l>0 else -1)*labels[abs(l)-1] for l in c),key=abs))
    s=list(map(move,s));rng.shuffle(s);return n,s,list(map(move,q)),move((prev,))

class InterpolantTests(unittest.TestCase):
    def check(self,n,s,q,f,**kw):
        r=synthesize(n,s,q,f,**kw);self.assertTrue(verify(n,s,q,f,r,**kw),r)
        expected=oracle(n,s,q,f)
        self.assertEqual(r['status'],'INSUFFICIENT' if expected is None else 'SUFFICIENT')
        if expected is not None:
            for code,b in expected.items():
                self.assertEqual(evaluate(r['decoder'],code,len(q)),b);self.assertEqual(decode(r['decoder'],code,len(q)),b)
        return r
    def test_alias(self):self.check(3,[(-1,3),(-2,3),(1,2,-3)],[(1,2)],(3,))
    def test_signed(self):self.check(3,[(-1,3),(-2,3),(1,2,-3)],[(1,2)],(-3,))
    def test_hidden(self):self.check(3,[],[(1,2)],(1,))
    def test_empty_domain(self):self.check(3,[()],[],(1,))
    def test_constant(self):self.check(3,[(2,)],[],(2,));self.check(3,[(-2,)],[],(2,))
    def test_empty_observations(self):self.check(3,[],[],(2,))
    def test_mixed(self):self.check(*chain(3))
    def test_parity(self):self.check(*chain(3,False))
    def test_random(self):
        rng=random.Random(1818)
        for i in range(500):
            n=rng.randrange(1,7)
            def clause():return tuple(sorted((v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),rng.randint(1,min(n,3)))),key=abs))
            s=[clause() for _ in range(rng.randrange(12))];q=list(dict.fromkeys(clause() for _ in range(rng.randrange(5))));f=clause()
            self.check(n,s,q,f)
    def test_budget(self):
        n,s,q,f=chain(4);r=synthesize(n,s,q,f,max_pairs=1);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(verify(n,s,q,f,r,max_pairs=1))
    def test_forgery(self):
        n,s,q,f=chain(3);r=self.check(n,s,q,f)
        for key,change in [('root',0),('decoder',{'gates':[],'output':1}),('contract','0')]:
            z=copy.deepcopy(r);z[key]=change;self.assertFalse(verify(n,s,q,f,z))
        z=copy.deepcopy(r);z['steps'][0][0]=len(z['steps'])+100000;self.assertFalse(verify(n,s,q,f,z))
        z=copy.deepcopy(r);z['steps'][0][2]=True;self.assertFalse(verify(n,s,q,f,z))
        self.assertFalse(verify(n,s[:-1],q,f,r));self.assertFalse(verify(n,s,q,(-f[0],),r))
    def test_witness_forgery(self):
        r=self.check(3,[],[(1,2)],(1,));r['witness'][1]=r['witness'][0];self.assertFalse(verify(3,[],[(1,2)],(1,),r))
    def test_both_orders(self):
        for mode in ('scope','pairs'):self.check(*chain(4,False),ordering=mode)
    def test_large_scope(self):
        n,s,q,f=chain(128,False);r=synthesize(n,s,q,f,max_pairs=10000);self.assertEqual(r['status'],'SUFFICIENT');self.assertTrue(verify(n,s,q,f,r,max_pairs=10000))
        self.assertEqual(synthesize(n,s,q,f,max_pairs=10000,ordering='pairs')['status'],'UNKNOWN')
    def test_json(self):
        n,s,q,f=chain(3);r=synthesize(n,s,q,f);self.assertTrue(verify(n,s,q,f,json.loads(json.dumps(r))))
    def test_receiver(self):
        n,s,q,f=chain(3);l=InterpolantLanguage(n,s)
        for c in q:self.assertTrue(l.extend(c)['complete'])
        before=l.stats['count_attempts'];r,ok=l.interpolate_extend(f);self.assertTrue(ok);self.assertEqual(l.stats['count_attempts'],before)
        obs,h=l.snapshot();self.assertEqual({k:c for k,(c,w) in h.items()},brute(n,s,obs))
    def test_receiver_failure(self):
        l=InterpolantLanguage(3,[]);l.extend((1,2));old=l.snapshot();r,ok=l.interpolate_extend((1,));self.assertFalse(ok);self.assertEqual(old,l.snapshot())

if __name__=='__main__':unittest.main()
