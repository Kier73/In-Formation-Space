import unittest,random,copy,json
from shared_proof import synthesize_shared,evaluate
from verify_shared_proof import verify
from test_global_sufficiency import oracle
from test_interpolant_ground import chain
from verify_global_sufficiency import value

class SharedTests(unittest.TestCase):
    def check(self,n,s,q,fs):
        r=synthesize_shared(n,s,q,fs);self.assertTrue(verify(n,s,q,fs,r),r)
        for j,f in enumerate(fs):
            expected=oracle(n,s,q,f);self.assertEqual(r['goals'][j]['status'],'INSUFFICIENT' if expected is None else 'SUFFICIENT')
            if expected is not None:
                for code,b in expected.items():self.assertEqual(evaluate(r['circuit'],code,len(q))[j],b)
        return r
    def test_chain(self):
        n,s,q,f=chain(3);self.check(n,s,q,[f,(-f[0],),q[0]])
    def test_random(self):
        rng=random.Random(1900)
        for _ in range(350):
            n=rng.randint(1,6)
            def c():return tuple(v*rng.choice((-1,1)) for v in sorted(rng.sample(range(1,n+1),rng.randint(1,min(n,3)))))
            s=[c() for _ in range(rng.randrange(12))];q=list(dict.fromkeys(c() for _ in range(rng.randrange(5))));fs=list(dict.fromkeys(c() for _ in range(3)))
            self.check(n,s,q,fs)
    def test_unsat(self):self.check(2,[()],[],[(1,),(-2,)])
    def test_mixed_status(self):self.check(3,[(-1,2),(1,-2)],[(1,)],[(2,),(3,),(-2,)])
    def test_no_observers(self):self.check(2,[(1,)],[],[(1,),(2,)])
    def test_signed_union(self):self.check(3,[],[(1,),(-2,)],[(1,-2),(2,)])
    def test_duplicate(self):
        with self.assertRaises(ValueError):synthesize_shared(2,[],[],[(1,),(1,)])
    def test_budget(self):
        n,s,q,f=chain(4);r=synthesize_shared(n,s,q,[f],max_pairs=1);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(verify(n,s,q,[f],r,max_pairs=1))
    def test_forged_prefix(self):
        n,s,q,f=chain(3);r=self.check(n,s,q,[f,(-f[0],)]);z=copy.deepcopy(r);z['prefix'][0][2]=True;self.assertFalse(verify(n,s,q,[f,(-f[0],)],z))
    def test_forged_suffix(self):
        n,s,q,f=chain(3);fs=[f,(-f[0],)];r=self.check(n,s,q,fs);z=copy.deepcopy(r);z['goals'][0]['steps'][0][0]=999999;self.assertFalse(verify(n,s,q,fs,z))
    def test_forged_circuit(self):
        n,s,q,f=chain(3);fs=[f,(-f[0],)];r=self.check(n,s,q,fs);z=copy.deepcopy(r);z['circuit']['outputs'][0]=1;self.assertFalse(verify(n,s,q,fs,z));self.assertFalse(verify(n,s[:-1],q,fs,r));self.assertFalse(verify(n,s,q,fs[::-1],r))
    def test_json(self):
        n,s,q,f=chain(3);fs=[f,(-f[0],)];r=self.check(n,s,q,fs);self.assertTrue(verify(n,s,q,fs,json.loads(json.dumps(r))))
    def test_complement(self):
        n,s,q,f=chain(3);r=self.check(n,s,q,[f,(-f[0],)]);self.assertEqual(len(r['circuit']['outputs']),2)
        for code in range(8):a,b=evaluate(r['circuit'],code,3);self.assertEqual(a+b,1)

if __name__=='__main__':unittest.main()
