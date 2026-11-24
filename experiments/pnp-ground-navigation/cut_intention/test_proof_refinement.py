"""Independent finite oracle, certificate mutation, and budget regressions."""
import unittest, random
from collections import Counter
from itertools import product
from proof_refinement import ProofLanguage,obligation
from verify_proof_refinement import Receiver,signature
from composed_ground import compile_ground
from heavy_ground import dpll,normalize,xor_encoding
from run_architecture_navigation import cycle,oracle


def brute(n,rows,predicates):
    result=Counter()
    for vals in product((0,1),repeat=n):
        def sat(c):return any(vals[abs(l)-1]==int(l>0) for l in c)
        if all(sat(c) for c in rows):result[sum(int(sat(c))*2**j for j,c in enumerate(predicates))]+=1
    return dict(result)

class ProofRefinementTests(unittest.TestCase):
    def exact(self,l):
        p,h=l.snapshot();self.assertEqual({k:c for k,(c,w) in h.items()},brute(l.n,l.source,p))
        for k,(c,w) in h.items():self.assertEqual(signature(p,w),k)
    def test_alias_and_split(self):
        l=ProofLanguage(4,[(1,-2),(-1,2),(-2,3),(-3,2)])
        self.assertEqual(l.extend([1])['status'],{0:'REFINE'})
        for p in ([3],[-2]):self.assertEqual(set(l.extend(p)['status'].values()),{'DECODE'})
        self.assertEqual(set(l.extend([4])['status'].values()),{'REFINE'});self.exact(l)
    def test_nonunit_affine_alias(self):
        l=ProofLanguage(4,xor_encoding((1,2,3),0)+xor_encoding((1,2,4),0));l.extend([3],nodes=0)
        self.assertEqual(set(l.extend([4],nodes=0)['status'].values()),{'DECODE'});self.exact(l)
        self.assertEqual(l.stats['decision_attempts'],0)
    def test_one_count(self):
        l=ProofLanguage(5,[]);before=l.stats['count_attempts'];self.assertTrue(l.extend([1,2,3],nodes=0)['complete'])
        self.assertEqual(l.stats['count_attempts']-before,1);self.assertEqual(sorted(c for c,_ in l.snapshot()[1].values()),[4,28]);self.exact(l)
    def test_unknown_then_resume(self):
        l=ProofLanguage(5,[]);old=l.snapshot();r=l.extend([1,2,3],width=1,nodes=0)
        self.assertEqual(r['status'],{0:'UNRESOLVED'});self.assertFalse(r['complete']);self.assertEqual(l.snapshot(),old)
        self.assertTrue(l.extend([1,2,3],width=3,nodes=0)['complete']);self.exact(l)
    def test_uncounted_then_resume(self):
        l=ProofLanguage(5,[]);old=l.snapshot();r=l.extend([1,2,3],width=1,nodes=8)
        self.assertEqual(r['status'],{0:'SPLIT_UNCOUNTED'});self.assertFalse(r['complete']);self.assertEqual(l.snapshot(),old)
        before=l.stats['decision_attempts'];self.assertTrue(l.extend([1,2,3],width=3)['complete']);self.assertEqual(l.stats['decision_attempts'],before);self.exact(l)
    def test_forced_no_count(self):
        l=ProofLanguage(4,[]);l.extend([1]);before=l.stats['count_attempts'];self.assertEqual(set(l.extend([-1])['status'].values()),{'DECODE'});self.assertEqual(l.stats['count_attempts'],before)
    def test_empty_model_set(self):
        l=ProofLanguage(4,[()]);self.assertEqual(l.snapshot()[1],{});self.assertTrue(l.extend([1])['complete']);self.exact(l)
    def test_no_unproved_seed(self):
        with self.assertRaises(ValueError):Receiver(3,[]).seed()
    def test_count_forgery_and_source_swap(self):
        r=Receiver(4,[(1,)]);p=compile_ground([(1,)],4);p['count']='9'
        with self.assertRaises(ValueError):r.admit([(1,)],'count',p)
        p=compile_ground([(1,)],4)
        with self.assertRaises(ValueError):r.admit([(-1,)],'count',p)
        r.admit([(1,)],'count',p);r.seed();self.assertEqual(r.snapshot()[1][0][0],8)
    def test_forged_unsat(self):
        r=Receiver(3,[]);p=dpll(normalize([(1,),(-1,)],3),3)
        with self.assertRaises(ValueError):r.admit([(1,)],'decision',p)
    def test_decision_count_forgery(self):
        r=Receiver(3,[]);p=dpll(normalize([(1,2,3)],3),3);p['count']='7'
        with self.assertRaises(ValueError):r.admit([(1,2,3)],'decision',p)
    def test_missing_fiber_and_forged_histogram(self):
        l=ProofLanguage(3,[]);l.extend([1]);p,h=l.snapshot()
        with self.assertRaises(ValueError):l.receiver.check([2],{},None)
        for k,(total,w) in h.items():l._count(obligation(l.source,p,k,(2,),1-((w>>1)&1)),12,2000000)
        with self.assertRaises(ValueError):l.receiver.check([2],{k:'REFINE' for k in h},{0:(8,0)})
        self.assertEqual(l.snapshot(),(p,h))
    def test_retry_reuses_proofs(self):
        l=ProofLanguage(5,[(1,-2),(1,-3),(1,-4)]);l.extend([1]);old=l.snapshot()
        r=l.extend([2,3,4],width=1,nodes=8);self.assertFalse(r['complete']);self.assertEqual(l.snapshot(),old)
        self.assertIn('DECODE',r['status'].values());hits=l.stats['decision_hits'];self.assertTrue(l.extend([2,3,4],width=5)['complete']);self.assertGreater(l.stats['decision_hits'],hits);self.exact(l)
    def test_randomized(self):
        rng=random.Random(1616)
        for _ in range(180):
            n=rng.randint(2,7)
            def clause():return tuple(sorted((v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),rng.randint(1,min(3,n)))),key=abs))
            l=ProofLanguage(n,[clause() for i in range(rng.randrange(10))]);p=[]
            for j in range(4):
                f=clause()
                if f in p:continue
                self.assertTrue(l.extend(f)['complete']);p.append(f);self.exact(l)
    def test_connected_cycle(self):
        n,rows,x=cycle(12);l=ProofLanguage(n,rows)
        for f in [(x[0],),(x[1],),(x[2],),(x[3],)]:self.assertTrue(l.extend(f)['complete'])
        expected={k:oracle(12,{i:k>>i&1 for i in range(4)}) for k in range(16)}
        self.assertEqual({k:c for k,(c,w) in l.snapshot()[1].items()},{k:c for k,c in expected.items() if c})

    def test_retained_novel_union(self):
        l=ProofLanguage(6,[(-1,2)])
        l.extend([1,2]);l.extend([3,4]);before=l.stats['count_attempts']
        r=l.query([[1,2,3,4]])
        self.assertEqual(int(r['count']),sum(brute(6,[(-1,2),(1,2,3,4)],[]).values()))
        self.assertEqual(l.query([[1,2],[3,4]])['count'],str(sum(brute(6,[(-1,2),(1,2),(3,4)],[]).values())))
        self.assertEqual(l.query([[5]])['status'],'UNRESOLVED')
        self.assertEqual(l.stats['count_attempts'],before)

if __name__=='__main__':unittest.main()
