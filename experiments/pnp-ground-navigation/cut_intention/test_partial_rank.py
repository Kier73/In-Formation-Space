import unittest,random,copy
from math import prod
from test_output_time import prepare
from run_temporal_ground import step
from run_output_time import expr_eval
from temporal_algebra import compile_algebra,Language,Diagram,Budget
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from partial_rank import PartialRank
from verify_partial_rank import CheckedPartial
import test_temporal_rank

class PartialTests(unittest.TestCase):
    def test_random_sources(self):
        rng=random.Random(26026)
        for _ in range(120):
            w=rng.choice([1,2]);k=w*rng.randrange(2,6);p=list(range(k//w));rng.shuffle(p);f=[[rng.randrange(2**w) for j in range(2**w)] for i in p];initial=rng.getrandbits(k)
            expr=[('xor',0,k-1),('or',0,k-1)]
            nav,rec=prepare(k,w,p,f,initial,expr);d,r=compile_algebra(nav,initial);a=Admission(rec,r);l=Language(d,r)
            j=l.extend('shift',0,3);l.extend('xor',j,1);a.extend(l.export());c=CheckedPartial(a);P=prod(d.base);D=l.D;u=initial;rows=[]
            for t in range(D+3*P+3):rows.append([expr_eval(e,u) for e in expr]);u=step(u,k,w,p,f)
            for i in range(4):
                x=PartialRank(l,i,suffix_mass=rng.choice([0,4,32]),scan=rng.choice([0,2,8]));hits=[];running=0
                for t,row in enumerate(rows[:-3]):
                    for threshold in (None,running,running+1):
                        z=x.compare(t,threshold,budget=rng.choice([0,1,20,20000]));self.assertTrue(c.verify(z));self.assertLessEqual(int(z['lower']),running);self.assertGreaterEqual(int(z['upper']),running)
                    exact=x.compare(t);self.assertEqual(exact['lower'],str(running));self.assertEqual(exact['upper'],str(running));self.assertTrue(c.verify(exact))
                    future=rows[t+3][0];value=([*row,future,future^row[1]])[i]
                    if value:running+=1;hits.append(t)
                for ordinal in [1,max(1,len(hits)),10**900+173]:
                    s=x.select(ordinal);self.assertTrue(c.verify_select(i,ordinal,s));
                    if ordinal<=len(hits):self.assertEqual(int(s['time']),hits[ordinal-1])
    def test_zero_budget(self):
        l,a=test_temporal_rank.RankTests().fixture();x=PartialRank(l,0,suffix_mass=0,scan=0);c=CheckedPartial(a)
        for t in range(60):
            exact=Rank(l,0).rank(t);r=x.compare(t,exact+2,budget=0);self.assertTrue(c.verify(r,budget=0));self.assertLessEqual(int(r['lower']),exact);self.assertGreaterEqual(int(r['upper']),exact)
    def test_forgery(self):
        l,a=test_temporal_rank.RankTests().fixture();x=PartialRank(l,0);c=CheckedPartial(a);r=x.compare(4)
        self.assertTrue(c.verify(r));
        for key,val in [('index',True),('root',0),('lower','999'),('upper','999'),('time','04'),('status','BELOW'),('work',False),('trace',[[999,'scan']]),('policy',[True,8])]:
            bad=copy.deepcopy(r);bad[key]=val;self.assertFalse(c.verify(bad),key)
        s=x.select(5);self.assertTrue(c.verify_select(0,5,s));bad=copy.deepcopy(s);bad['time']=str(int(s['time'])+1);self.assertFalse(c.verify_select(0,5,bad));bad=copy.deepcopy(s);bad['proofs'].pop();self.assertFalse(c.verify_select(0,5,bad))
    def test_transient_and_empty(self):
        nav,rec=prepare(3,1,[0,2,1],[[0,0],[0,1],[0,1]],3,[0]);d,r=compile_algebra(nav,3);a=Admission(rec,r);l=Language(d,r);x=PartialRank(l,0);c=CheckedPartial(a)
        for t in (0,1,10**1000):self.assertTrue(c.verify(x.compare(t)))
        for k in (1,2,10**900):self.assertTrue(c.verify_select(0,k,x.select(k)))
    def test_random_diagram_bounds(self):
        rng=random.Random(26);base=[2,3,5,7];P=prod(base)
        for _ in range(40):
            truth=[rng.randrange(2) for _ in range(P)];d=Diagram(base);r=d.atom(P,{i for i,v in enumerate(truth) if v});l=Language(d,dict(cutoff=0,outputs=[r],prefix=[]));x=PartialRank(l,0,suffix_mass=4,scan=3)
            for t in rng.sample(range(P*2),20):
                exact=sum(truth[j%P] for j in range(t));old=(0,t)
                for budget in [0,10,100,20000]:
                    z=x.compare(t,budget=budget);bounds=int(z['lower']),int(z['upper']);self.assertLessEqual(bounds[0],exact);self.assertGreaterEqual(bounds[1],exact);self.assertGreaterEqual(bounds[0],old[0]);self.assertLessEqual(bounds[1],old[1]);old=bounds
                self.assertEqual(old,(exact,exact))
    def test_bad_args(self):
        l,a=test_temporal_rank.RankTests().fixture();x=PartialRank(l,0)
        for t in [-1,True,2**4096]:self.assertRaises(ValueError,x.compare,t)
        for k in [-1,True,2**4096]:self.assertRaises(ValueError,x.compare,1,k)
        for k in [0,-1,True,2**4096]:self.assertRaises(ValueError,x.select,k)
if __name__=='__main__':unittest.main()
