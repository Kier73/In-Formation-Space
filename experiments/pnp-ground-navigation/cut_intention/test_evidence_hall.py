"""CIG-007 independent controls and adversarial certificate tests."""
import unittest, random, copy
from itertools import combinations
from joint_intention_ground import make_branching_source
from language_selector import compile_language
from evidence_ground import compile_policy,apply_transcript
from verify_evidence_ground import verify
from hall_ground import compile_hall,verify_hall
from heavy_campaign import pigeonhole

class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=make_branching_source();cls.g,_=compile_language(cls.s,[0,1,2,3,4],steps=3,initial=4)
        cls.q=cls.g['intent'];cls.offers=[[x,b,1] for x in range(32) for b in range(7)]
    def plan(self,offers=None,identify=False):
        if offers is None:offers=self.offers
        p=compile_policy(self.s,self.g,self.q,offers,identify=identify)
        self.assertTrue(verify(self.s,self.g,self.q,offers,identify,p));return p
    def test_intention_not_identification(self):
        p=self.plan();i=self.plan(identify=True)
        self.assertEqual((p['worst_cost'],i['worst_cost']),(1,2))
        self.assertEqual(len(p['tree']['one']['candidates']),3)
    def test_both_outcomes(self):
        p=self.plan();j=p['tree']['probe']
        self.assertEqual(apply_transcript(p,[(j,0)])['result'],[0,0,0])
        self.assertEqual(apply_transcript(p,[(j,1)])['result'],[0,1,0])
    def test_missing_evidence(self):self.assertEqual(apply_transcript(self.plan(),[])['status'],'NEEDS_EVIDENCE')
    def test_insufficient_offers(self):self.assertEqual(self.plan([[0,0,1]])['status'],'UNRESOLVED')
    def test_price_bound(self):
        offers=[[x,b,5 if b==4 else 1] for x,b,_ in self.offers];p=self.plan(offers)
        self.assertFalse(verify(self.s,self.g,self.q,self.offers,False,p))
    def test_forged_branch(self):
        p=self.plan();p['tree']['one']['result']=[1,1,1]
        self.assertFalse(verify(self.s,self.g,self.q,self.offers,False,p))
    def test_forged_cost(self):
        p=self.plan();p['worst_cost']=0
        self.assertFalse(verify(self.s,self.g,self.q,self.offers,False,p))
    def test_wrong_transcript(self):
        p=self.plan()
        with self.assertRaises(ValueError):apply_transcript(p,[(p['tree']['probe']+1,1)])
    def test_zero_cost(self):self.assertEqual(self.plan([[x,b,0] for x,b,_ in self.offers])['worst_cost'],0)
    def test_duplicate_offer(self):
        with self.assertRaises(ValueError):self.plan([[0,0,1],[0,0,2]])

class HallTests(unittest.TestCase):
    def check(self,n,r,expected):
        p=compile_hall(r,n);self.assertEqual(p['status'],expected)
        if expected!='UNKNOWN':self.assertTrue(verify_hall(r,n,p))
        return p
    def test_previous_failure(self):
        n,r,_=pigeonhole(8,7);self.check(n,r,'UNSAT')
    def test_large(self):
        n,r,_=pigeonhole(32,31);self.check(n,r,'UNSAT')
    def test_sat(self):
        n,r,_=pigeonhole(7,7);self.check(n,r,'SAT')
    def test_rename(self):
        n,r,_=pigeonhole(8,7);v=list(range(1,n+1));random.Random(17).shuffle(v)
        r=[tuple((1 if l>0 else -1)*v[abs(l)-1] for l in c) for c in r];self.check(n,r,'UNSAT')
    def test_local_deficiency(self):
        # Three demands compete for two cliques; three independent resource
        # groups elsewhere ensure global resource count is not deficient.
        n=9;r=[(1,2),(3,4),(5,6),(7,8,9)]
        r.extend((-a,-b) for group in [(1,3,5),(2,4,6)] for a,b in combinations(group,2))
        p=self.check(n,r,'UNSAT');self.assertEqual(len(p['demands']),3)
    def test_missing_exclusion(self):
        n,r,_=pigeonhole(3,2);p=self.check(n,r,'UNSAT')
        a,b=p['exclusions'][0][:2];r.remove(tuple(sorted((-a,-b),reverse=True))) if tuple(sorted((-a,-b),reverse=True)) in r else r.remove((-b,-a))
        self.assertFalse(verify_hall(r,n,p));self.check(n,r,'UNKNOWN')
    def test_forged_partition(self):
        n,r,_=pigeonhole(3,2);p=self.check(n,r,'UNSAT');p['exclusions']=[p['exclusions'][0]+p['exclusions'][1]]
        self.assertFalse(verify_hall(r,n,p))
    def test_extra_clause(self):self.check(2,[(1,2),(-1,),(-2,)],'UNKNOWN')
    def test_overlap(self):self.check(3,[(1,2),(2,3)],'UNKNOWN')
    def test_small_random_matching(self):
        rng=random.Random(71)
        for _ in range(60):
            p,h=rng.randint(1,4),rng.randint(1,4);domains=[rng.sample(range(h),rng.randint(1,h)) for i in range(p)]
            groups=[[] for j in range(h)];r=[];n=0
            for d in domains:
                row=[]
                for j in d:n+=1;row.append(n);groups[j].append(n)
                r.append(tuple(row))
            r.extend((-a,-b) for g in groups for a,b in combinations(g,2))
            expected='SAT' if any(all(any(bool(x&(1<<(abs(l)-1)))==(l>0) for l in c) for c in r) for x in range(1<<n)) else 'UNSAT'
            self.check(n,r,expected)

if __name__=='__main__':unittest.main()
