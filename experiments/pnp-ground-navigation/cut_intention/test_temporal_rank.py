import unittest,random,copy
from math import prod
from temporal_algebra import Diagram,Language,compile_algebra,Budget
from verify_temporal_algebra import Admission
from temporal_rank import Rank,expand
from verify_temporal_rank import CheckedRank
from test_output_time import prepare
from run_temporal_ground import step
from run_output_time import expr_eval

class RankTests(unittest.TestCase):
    def test_random_qualified(self):
        rng=random.Random(25025)
        for _ in range(100):
            w=rng.choice([1,2]);k=w*rng.randrange(3,6);p=list(range(k//w));rng.shuffle(p)
            f=[[rng.randrange(2**w) for j in range(2**w)] for i in p];initial=rng.getrandbits(k)
            expr=[('xor',0,k-1),('or',1,k-1)]
            nav,rec=prepare(k,w,p,f,initial,expr);d,r=compile_algebra(nav,initial);a=Admission(rec,r);l=Language(d,r)
            j=l.extend('shift',0,7);h=l.extend('and',j,1);a.extend(l.export());D=l.D;P=prod(d.base);u=initial;rows=[]
            for t in range(D+3*P+7):rows.append([expr_eval(e,u) for e in expr]);u=step(u,k,w,p,f)
            expected=[[row[0],row[1],rows[t+7][0],rows[t+7][0]&row[1]] for t,row in enumerate(rows[:-7])]
            for i in range(4):
                x=Rank(l,i);y=CheckedRank(a,x.packet());running=0;hits=[]
                for t,row in enumerate(expected):
                    self.assertEqual(x.rank(t),running);self.assertEqual(y.rank(t),running)
                    if row[i]:running+=1;hits.append(t)
                for ordinal in ([1,len(hits)] if hits else [1]):
                    z=x.select(ordinal);self.assertTrue(y.verify_select(ordinal,z));self.assertEqual(z['time'],str(hits[ordinal-1]) if hits else None);self.assertEqual(z['time'],x.select(ordinal,bounded=False)['time'])
                if x.total:
                    ordinal=10**900+1;z=x.select(ordinal);self.assertTrue(y.verify_select(ordinal,z))
    def test_arbitrary_mdd(self):
        rng=random.Random(91)
        for _ in range(100):
            d=Diagram([2,3,5]);truth=[rng.randrange(2) for t in range(30)];r=d.atom(30,{t for t,v in enumerate(truth) if v});terms,_=expand(d,r)
            for t in range(60):self.assertEqual(sum(c for a,m,c in terms if t%m==a),truth[t%30])
    def fixture(self):
        nav,rec=prepare(5,1,[4,0,1,2,3],[[0,1]]*5,1,[0,('xor',0,1)]);d,r=compile_algebra(nav,1);a=Admission(rec,r);l=Language(d,r);return l,a
    def test_forgery(self):
        l,a=self.fixture();x=Rank(l,0)
        for key,value in [('root',0),('index',1),('work',0),('terms',[]),('terms',[[0,1,True]])]:
            p=copy.deepcopy(x.packet());p[key]=value;self.assertRaises(ValueError,CheckedRank,a,p)
        y=CheckedRank(a,x.packet());z=x.select(5);z['time']=str(int(z['time'])+5);self.assertFalse(y.verify_select(5,z))
        z=x.select(5);z['time']='0'+z['time'];self.assertFalse(y.verify_select(5,z))
    def test_budget(self):
        l,a=self.fixture();self.assertRaises(Budget,Rank,l,0,1);x=Rank(l,0);self.assertRaises(ValueError,CheckedRank,a,x.packet(),1)
    def test_transient_only(self):
        nav,rec=prepare(3,1,[0,2,1],[[0,0],[0,1],[0,1]],3,[0]);d,r=compile_algebra(nav,3);a=Admission(rec,r);x=Rank(Language(d,r),0);y=CheckedRank(a,x.packet());self.assertEqual(x.select(1)['time'],'0');self.assertTrue(y.verify_select(1,x.select(1)));self.assertEqual(x.select(2)['status'],'UNREACHABLE');self.assertTrue(y.verify_select(2,x.select(2)))
    def test_complement_and_all(self):
        l,a=self.fixture();j=l.extend('not',0);h=l.extend('or',j,0);a.extend(l.export());x=Rank(l,h);y=CheckedRank(a,x.packet());self.assertEqual(x.terms,[[0,1,1]]);k=10**1000;z=x.select(k);self.assertEqual(z['time'],str(k-1));self.assertTrue(y.verify_select(k,z))
    def test_dense_compression_budget(self):
        d=Diagram([2,3,5,7,11,13]);P=prod(d.base);rng=random.Random(25025)
        truth={t for t in range(P) if rng.getrandbits(1)};r=d.atom(P,truth)
        self.assertRaises(Budget,expand,d,r,10000)
        terms,_=expand(d,r);self.assertGreater(len(terms),len(d.nodes))
        for t in random.Random(7).sample(range(P),50):
            self.assertEqual(sum(c for a,m,c in terms if t%m==a),int(t in truth))
    def test_bad_arguments(self):
        l,a=self.fixture();x=Rank(l,0);y=CheckedRank(a,x.packet())
        for k in [0,-1,True,2**4096]:self.assertRaises(ValueError,x.select,k);self.assertFalse(y.verify_select(k,{}))
        for t in [-1,True,2**4096]:self.assertRaises(ValueError,x.rank,t);self.assertRaises(ValueError,y.rank,t)
if __name__=='__main__':unittest.main()
