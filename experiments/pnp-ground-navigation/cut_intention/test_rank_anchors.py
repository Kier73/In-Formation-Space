import unittest,random,copy
from math import prod
from test_output_time import prepare
import test_temporal_rank
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from partial_rank import PartialRank
from rank_anchors import Anchors
from verify_rank_anchors import CheckedAnchors
from run_temporal_ground import step
from run_output_time import expr_eval

class AnchorTests(unittest.TestCase):
    def fixture(self):
        l,a=test_temporal_rank.RankTests().fixture();return l,a,Anchors(l,0),CheckedAnchors(a,0)
    def test_seeds(self):
        l,a,p,v=self.fixture();full=Rank(l,0)
        for phase in range(p.P+1):
            z=p.seed(phase,exact=full);self.assertTrue(v.admit_seed(z));p.commit_seed(z)
        self.assertEqual(p.anchors,v.anchors)
        self.assertEqual(p.anchors,{t:full.rank(p.D+t)-p.before for t in range(p.P+1)})
        z=p.seed(2,partial=PartialRank(l,0));self.assertTrue(v.admit_seed(z));p.commit_seed(z)
    def test_compare(self):
        l,a,p,v=self.fixture();full=Rank(l,0)
        for phase in (1,3):
            z=p.seed(phase,exact=full);self.assertTrue(v.admit_seed(z));p.commit_seed(z)
        for t in range(30):
            e=full.rank(t)
            for k in (0,e,e+1):
                z=p.compare(t,k);self.assertTrue(v.verify_compare(t,k,z));self.assertLessEqual(int(z['lower']),e);self.assertGreaterEqual(int(z['upper']),e)
                bad=copy.deepcopy(z);bad['upper']=str(e+999);self.assertFalse(v.verify_compare(t,k,bad))
                self.assertFalse(v.verify_compare(t,k+1,z))
    def test_span_request_and_progress(self):
        l,a,p,v=self.fixture();full=Rank(l,0)
        for target in (2,4,0,3):
            z=p.span(target,budget=1)
            self.assertFalse(v.admit_span(target+1,z,budget=1))
            self.assertTrue(v.admit_span(target,z,budget=1));p.commit(z)
            self.assertEqual(int(z['rank']),full.rank(p.D+int(z['end']))-p.before)
        for k in (1,10**900+3):
            for _ in range(p.P+1):
                z=p.select(k,budget=1);self.assertTrue(v.admit_select(k,z,budget=1));p.commit(z)
                if z['status']!='UNKNOWN':break
            self.assertEqual(z['time'],full.select(k)['time'])
    def test_random_qualified(self):
        rng=random.Random(2929)
        for _ in range(100):
            w=rng.choice([1,2]);k=w*rng.randrange(2,6);p=list(range(k//w));rng.shuffle(p)
            f=[[rng.randrange(2**w) for j in range(2**w)] for i in p];initial=rng.getrandbits(k)
            expr=[('xor',0,k-1),('or',0,k-1)]
            nav,rec=prepare(k,w,p,f,initial,expr);d,r=compile_algebra(nav,initial);a=Admission(rec,r);l=Language(d,r)
            i=l.extend('shift',0,3);a.extend(l.export())
            u=initial;rows=[]
            for t in range(l.D+3*prod(d.base)+3):rows.append([expr_eval(e,u) for e in expr]);u=step(u,k,w,p,f)
            for i in range(3):
                x=Anchors(l,i);v=CheckedAnchors(a,i);full=Rank(l,i)
                values=[row[i] if i<2 else rows[t+3][0] for t,row in enumerate(rows[:-3])];hits=[t for t,b in enumerate(values) if b]
                phase=rng.randrange(x.P+1);z=x.seed(phase,exact=full);self.assertTrue(v.admit_seed(z));x.commit_seed(z)
                for j in range(6):
                    phase=rng.randrange(x.P+1);z=x.span(phase,budget=rng.randrange(5));self.assertTrue(v.admit_span(phase,z,budget=4));x.commit(z)
                    self.assertEqual(int(z['rank']),sum(values[x.D:x.D+int(z['end'])]));self.assertEqual(x.anchors,v.anchors)
                for ordinal in (1,max(1,len(hits)),10**900+173):
                    for attempt in range(x.P+2):
                        z=x.select(ordinal,budget=1);self.assertTrue(v.admit_select(ordinal,z,budget=1));x.commit(z)
                        if z['status']!='UNKNOWN':break
                    self.assertEqual(z['status'],full.select(ordinal)['status']);self.assertEqual(z['time'],full.select(ordinal)['time'])
                    if ordinal<=len(hits):self.assertEqual(int(z['time']),hits[ordinal-1])
                self.assertEqual(x.anchors,v.anchors)
    def test_forged_seed(self):
        l,a,p,v=self.fixture();z=p.seed(2,exact=Rank(l,0));old=v.anchors
        for key,val in [('rank','999'),('phase','02'),('index',True),('method','invalid'),('proof',{})]:
            bad=copy.deepcopy(z);bad[key]=val;self.assertFalse(v.admit_seed(bad),key);self.assertEqual(old,v.anchors)
        z=p.seed(2,partial=PartialRank(l,0));z['proof']['time']='3';self.assertFalse(v.admit_seed(z));self.assertEqual(old,v.anchors)
    def test_forged_transition(self):
        l,a,p,v=self.fixture();z=p.span(2,budget=1);old=v.anchors
        for key,val in [('anchor','2'),('end','4'),('rank','3'),('steps',True),('status','EXACT'),('target','0')]:
            bad=copy.deepcopy(z);bad[key]=val;self.assertFalse(v.admit_span(2,bad,budget=1),key);self.assertEqual(old,v.anchors)
        self.assertTrue(v.admit_span(2,z,budget=1));p.commit(z)
        z=p.select(10**900+3,budget=5);self.assertEqual(z['status'],'FOUND');old=v.anchors
        for key,val in [('time',str(int(z['time'])+1)),('ordinal','1'),('status','UNKNOWN'),('rank','999'),('index',True)]:
            bad=copy.deepcopy(z);bad[key]=val;self.assertFalse(v.admit_select(10**900+3,bad,budget=5),key);self.assertEqual(old,v.anchors)
        self.assertTrue(v.admit_select(10**900+3,z,budget=5))
    def test_no_progress_zero_budget(self):
        l,a,p,v=self.fixture();z=p.select(2,budget=0);self.assertEqual(z['status'],'UNKNOWN');self.assertTrue(v.admit_select(2,z,budget=0))
        self.assertEqual(p.anchors,v.anchors)
    def test_transient_and_empty(self):
        nav,rec=prepare(3,1,[0,2,1],[[0,0],[0,1],[0,1]],3,[0]);d,r=compile_algebra(nav,3);a=Admission(rec,r);l=Language(d,r);p=Anchors(l,0);v=CheckedAnchors(a,0)
        for k in [1,2,10**900]:
            z=p.select(k);self.assertTrue(v.admit_select(k,z));self.assertEqual(z['time'],Rank(l,0).select(k)['time'])
    def test_compact_receipt(self):
        l,a,p,v=self.fixture();full=Rank(l,0)
        for k in (1,10**900+173,10**1000+1):
            z=p.compact(k,budget=10);self.assertNotIn('time',z);self.assertNotIn('ordinal',z)
            old=v.anchors
            # Same phase proof is intentionally reusable at another period.
            self.assertEqual(v.admit_compact(k+p.N,z,budget=10)['time'],full.select(k+p.N)['time'])
            old=v.anchors
            bad=copy.deepcopy(z);bad['rank']='999';self.assertIsNone(v.admit_compact(k,bad,budget=10));self.assertEqual(old,v.anchors)
            got=v.admit_compact(k,z,budget=10);self.assertEqual(got['time'],full.select(k)['time']);p.commit(z)
        self.assertEqual(p.anchors,v.anchors)
        z=p.compact(2,budget=0);self.assertEqual(v.admit_compact(2,z,budget=0),{'status':'UNKNOWN','time':None})
    def test_compact_wrong_residue(self):
        l,a=test_temporal_rank.RankTests().fixture();p=Anchors(l,1);v=CheckedAnchors(a,1)
        self.assertGreater(p.N,1);z=p.compact(1,budget=10);old=v.anchors
        self.assertIsNone(v.admit_compact(2,z,budget=10));self.assertEqual(old,v.anchors)
        self.assertEqual(v.admit_compact(1,z,budget=10)['time'],Rank(l,1).select(1)['time'])
    def test_invalid(self):
        l,a,p,v=self.fixture()
        for k in [0,-1,True,2**4096]:self.assertRaises(ValueError,p.select,k)
        for b in [-1,True,100001]:self.assertRaises(ValueError,p.select,1,budget=b)
        for t in [-1,True,p.P+1]:self.assertRaises(ValueError,p.span,t)

if __name__=='__main__':unittest.main()
