import unittest,random,copy
from math import prod
from anchor_portfolio import Portfolio,choose,plan_seeds
from verify_anchor_portfolio import PortfolioReceiver
from temporal_rank import Rank
from test_output_time import prepare
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from run_output_time import expr_eval
from run_temporal_ground import step
import test_temporal_rank

class PortfolioTests(unittest.TestCase):
    def fixture(self):return test_temporal_rank.RankTests().fixture()
    def test_batch_single_audit(self):
        l,a=self.fixture();v=PortfolioReceiver(a,1);p=Portfolio(l,v,capacity=4,scan=1,full_mode='ephemeral')
        # Forecast at a distant residual; endpoint proximity may make acquisition unnecessary.
        p.acquire([10**900+1]*20,slots=2,full_cost=100,seed_cost=1)
        self.assertLessEqual(p.stats['rank_opens'],1);self.assertIsNone(p.full);self.assertIsNone(v.exact)
        # Explicitly qualify the exact basis once, then admit many results.
        x=Rank(l,1);self.assertTrue(v.open_rank(x.packet()))
        for k in range(1,10):self.assertTrue(v.admit_exact(k,x.select(k)))
        self.assertGreater(len(v.anchors),2);v.close_rank();self.assertFalse(v.admit_exact(1,x.select(1)))
    def test_reject_and_atomic(self):
        l,a=self.fixture();v=PortfolioReceiver(a,1);x=Rank(l,1);self.assertTrue(v.open_rank(x.packet()));old=v.anchors
        bad=copy.deepcopy(x.packet());bad['terms']=[];self.assertFalse(v.open_rank(bad));self.assertIsNotNone(v.exact)
        z=x.select(1);z['time']=str(int(z['time'])+1);self.assertFalse(v.admit_exact(1,z));self.assertEqual(v.anchors,old)
        self.assertFalse(v.retain([0,v.P,3],1));self.assertFalse(v.retain([0],0));self.assertEqual(v.anchors,old)
    def test_hit_and_wrong_ordinal(self):
        l,a=self.fixture();v=PortfolioReceiver(a,1);x=Rank(l,1);self.assertTrue(v.open_rank(x.packet()));k=1;z=x.select(k);self.assertTrue(v.admit_exact(k,z));p=(int(z['time'])-v.D)%v.P
        h={'index':1,'phase':str(p)};self.assertEqual(v.admit_hit(k+v.N*10**900,h)['time'],x.select(k+v.N*10**900)['time']);self.assertIsNone(v.admit_hit(k+1,h));self.assertIsNone(v.admit_hit(k,dict(h,index=0)))
    def test_retention_policy(self):
        a={0:0,100:50,20:10,21:11,80:40};self.assertEqual(choose(a,{0,100},[11]*10+[40],1),[0,20,100]);self.assertEqual(choose(a,{0,100},[],0),[0,100]);self.assertRaises(ValueError,choose,a,{0,100},[],-1)
    def test_forecast_prices(self):
        l,a=self.fixture();p=Portfolio(l,PortfolioReceiver(a,1),capacity=4,scan=0)
        self.assertEqual(plan_seeds(p.x,[1]*10,slots=2,scan=0,full_cost=100,seed_cost=1),[])
        self.assertEqual(plan_seeds(p.x,[1]*10,slots=2,scan=3,full_cost=100,seed_cost=10000),[])
    def test_refusal_and_local(self):
        l,a=self.fixture();p=Portfolio(l,PortfolioReceiver(a,1),capacity=1,scan=0,max_work=1)
        self.assertEqual(p.query(2)['status'],'UNKNOWN');self.assertEqual(p.stats['compile_refused'],1)
        self.assertEqual(p.query(3)['status'],'UNKNOWN');self.assertEqual(p.stats['compile_refused'],1)
        l,a=self.fixture();p=Portfolio(l,PortfolioReceiver(a,1),capacity=1,scan=10,max_work=1);self.assertEqual(p.query(1)['status'],'FOUND');self.assertEqual(p.stats['rank_opens'],0)
    def test_random_qualified_usage(self):
        rng=random.Random(3030)
        for _ in range(60):
            w=rng.choice([1,2]);k=w*rng.randrange(2,7);per=list(range(k//w));rng.shuffle(per);f=[[rng.randrange(2**w) for _ in range(2**w)] for _ in per];initial=rng.getrandbits(k);expr=[('xor',0,k-1),('or',0,k-1)]
            nav,rec=prepare(k,w,per,f,initial,expr);d,r=compile_algebra(nav,initial);a=Admission(rec,r);l=Language(d,r)
            for i in range(2):
                D=l.D;P=prod(d.base);u=initial;hits=[];tail=[]
                for t in range(D+P):
                    if expr_eval(expr[i],u):(hits if t<D else tail).append(t)
                    u=step(u,k,w,per,f)
                def expected(k):
                    if k<=len(hits):return str(hits[k-1])
                    if not tail:return None
                    q,j=divmod(k-len(hits)-1,len(tail));return str(tail[j]+q*P)
                for policy in ('demand','lru','full'):
                    p=Portfolio(l,PortfolioReceiver(a,i),capacity=0 if policy=='full' else rng.randrange(1,6),scan=rng.randrange(0,5),policy=policy,full_mode=rng.choice(['retain','ephemeral']),partial_budget=32)
                    for j in [rng.randrange(1,30) for _ in range(8)]+[10**900+1]:
                        got=p.query(j);t=expected(j);self.assertEqual(got,{'status':'FOUND' if t is not None else 'UNREACHABLE','time':t});self.assertLessEqual(len(p.x.anchors)-2,p.capacity);self.assertEqual(p.x.anchors,p.v.anchors)
    def test_adaptive_retention_and_reopen(self):
        l,a=self.fixture();p=Portfolio(l,PortfolioReceiver(a,1),capacity=4,scan=0,full_mode='adaptive',retention_price_ns=1,window=2)
        self.assertEqual(p.query(1)['status'],'FOUND');self.assertIsNotNone(p.full)
        p.query(1);p.query(1);self.assertIsNone(p.full);self.assertIsNone(p.v.exact);self.assertEqual(p.stats['adaptive_drops'],1)
        self.assertEqual(p.query(2)['status'],'FOUND');self.assertEqual(p.stats['rank_opens'],2);self.assertEqual(p.x.anchors,p.v.anchors)
    def test_explicit_seed_plan(self):
        l,a=self.fixture();p=Portfolio(l,PortfolioReceiver(a,1),capacity=4,scan=1)
        # On this fixture the closest anchors can already serve all requested ordinals.
        for k in (1,2,3):
            z=p.query(k);self.assertEqual(z['time'],Rank(l,1).select(k)['time'])
        self.assertEqual(p.x.anchors,p.v.anchors)

if __name__=='__main__':unittest.main()
