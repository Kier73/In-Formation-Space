import unittest,random,copy,json
from collections import Counter
from global_sufficiency import synthesize,evaluate,GlobalLanguage,paired,truth
from verify_global_sufficiency import verify,pair_source,contract
from verify_composed_ground import accepted,normal
from heavy_ground import xor_encoding
from test_proof_refinement import brute


def oracle(n,source,q,f):
    values={}
    for x in range(1<<n):
        if not accepted(source,x):continue
        code=sum(truth(c,x)<<i for i,c in enumerate(q));b=truth(f,x)
        if code in values and values[code]!=b:return None
        values[code]=b
    return values


class GlobalSufficiencyTests(unittest.TestCase):
    def check(self,n,s,q,f,mode='auto',**kw):
        r=synthesize(n,s,q,f,mode=mode,**kw);self.assertNotEqual(r['status'],'UNKNOWN');self.assertTrue(verify(n,s,q,f,r,**kw))
        expected=oracle(n,s,q,f);self.assertEqual(r['status'],'INSUFFICIENT' if expected is None else 'SUFFICIENT')
        if expected is not None and r['decoder'] is not None:
            for code,b in expected.items():self.assertEqual(evaluate(q,f,r,code),b)
        return r
    def test_affine_nonlocal(self):
        s=xor_encoding((1,2,3),0)+xor_encoding((1,2,4),0)
        r=self.check(4,s,[(3,)],(4,));self.assertEqual(r['route'],'affine');self.assertEqual(len(r['decoder']['equations']),2)
    def test_signed_affine(self):
        self.check(3,xor_encoding((1,2,3),1),[(-1,),(2,)],(-3,))
    def test_nonlinear_circuit(self):
        s=[(-1,-2,3),(1,-3),(2,-3),(-3,-4,5),(3,-5),(4,-5)]
        r=self.check(5,s,[(1,),(2,),(4,)],(5,));self.assertEqual(r['route'],'circuit');self.assertEqual(len(r['decoder']['gates']),2)
    def test_paired_anf(self):
        s=[(-1,2,3),(-1,2,-3),(1,-2,3),(1,-2,-3)]
        r=self.check(3,s,[(1,)],(2,),'paired');self.assertEqual(r['decoder']['anf'],[1])
    def test_nonlinear_observations(self):
        r=self.check(4,[],[(1,2),(-3,4)],(1,2,-3,4),'paired');self.assertEqual(r['decoder']['anf'],[1,2,3])
    def test_existing_union_route(self):
        q=[(1,2),(-3,4)];f=(1,2,-3,4);r=self.check(4,[],q,f);self.assertEqual(r['route'],'union')
        r['decoder']['inputs']=[0];self.assertFalse(verify(4,[],q,f,r))
    def test_paired_nonliteral_semantics(self):
        s=[(-1,3),(-2,3),(1,2,-3)];q=[(1,2)];f=(3,);r=self.check(3,s,q,f,'paired');self.assertEqual(r['decoder']['anf'],[1])
        bad=copy.deepcopy(r);bad['proof']['count']='1';self.assertFalse(verify(3,s,q,f,bad))
    def test_counterexample(self):
        r=self.check(3,[],[(1,2)],(1,));self.assertEqual(r['status'],'INSUFFICIENT')
        r['witness'][1]=r['witness'][0];self.assertFalse(verify(3,[],[(1,2)],(1,),r))
    def test_empty_source_domain(self):
        self.check(3,[()],[(1,)],(2,),'paired')
    def test_empty_observation(self):
        self.check(3,[(2,)],[],(2,));self.check(3,[],[],(2,))
    def test_budget_and_decoder_separation(self):
        r=self.check(4,[],[(1,2),(-3,4)],(1,2,-3,4),'paired',decoder_bits=0);self.assertIsNone(r['decoder'])
        r=synthesize(4,[],[(1,2)],(1,),mode='paired',width=1);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(verify(4,[],[(1,2)],(1,),r,width=1))
    def test_affine_forgery(self):
        s=xor_encoding((1,2,3),0);q=[(1,),(2,)];f=(3,);r=self.check(3,s,q,f)
        bad=copy.deepcopy(r);bad['decoder']['terms'][0]['constant']^=1;self.assertFalse(verify(3,s,q,f,bad))
        bad=copy.deepcopy(r);bad['decoder']['equations'][0][1]^=1;self.assertFalse(verify(3,s,q,f,bad))
        self.assertFalse(verify(3,s[:-1],q,f,r));self.assertFalse(verify(3,s,q,(-3,),r))
    def test_gate_forgery(self):
        s=[(-1,-2,3),(1,-3),(2,-3)];q=[(1,),(2,)];f=(3,);r=self.check(3,s,q,f)
        bad=copy.deepcopy(r);bad['decoder']['gates'][0]['table'][0]=1;self.assertFalse(verify(3,s,q,f,bad))
    def test_anf_forgery(self):
        r=self.check(3,[],[(1,2)],(1,2),'paired');r['decoder']['anf']=[0];self.assertFalse(verify(3,[],[(1,2)],(1,2),r))
    def test_pair_reconstruction(self):
        s,q,f=contract(4,[(-1,3),(2,)],[(1,2),(-3,4)],(-1,4));n,a=paired(4,s,q,f);m,b=pair_source(4,s,q,f);self.assertEqual(n,m);self.assertEqual(normal(a,n),normal(b,m))
    def test_random(self):
        rng=random.Random(1717)
        for i in range(260):
            n=rng.randrange(2,7)
            def clause():return tuple(sorted((v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),rng.randint(1,min(3,n)))),key=abs))
            s=[clause() for _ in range(rng.randrange(10))];q=list(dict.fromkeys(clause() for _ in range(rng.randrange(4))));f=clause()
            self.check(n,s,q,f,'paired' if i%3==0 else 'auto')
    def test_receiver_integration(self):
        s=xor_encoding((1,2,3),0)+xor_encoding((1,2,4),0);l=GlobalLanguage(5,s)
        l.extend([3]);before=l.stats['count_attempts'];r,ok=l.global_extend([4]);self.assertTrue(ok);self.assertEqual(l.stats['count_attempts'],before)
        p,h=l.snapshot();self.assertEqual({k:c for k,(c,w) in h.items()},brute(5,s,p));self.assertEqual(l.query([[4]])['count'],'4')
        old=l.snapshot();r,ok=l.global_extend([5]);self.assertFalse(ok);self.assertEqual(r['status'],'INSUFFICIENT');self.assertEqual(l.snapshot(),old)
        self.assertTrue(l.extend([5])['complete'])
    def test_json_roundtrip(self):
        s=xor_encoding((1,2,3),0);q=[(1,),(2,)];f=(3,);r=synthesize(3,s,q,f);self.assertTrue(verify(3,s,q,f,json.loads(json.dumps(r))))

if __name__=='__main__':unittest.main()
