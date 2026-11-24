import unittest,random,copy
from math import prod
import test_temporal_rank
from test_output_time import prepare
from temporal_algebra import compile_algebra,Language,Budget
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from compositional_rank import Memory,make_link
from verify_compositional_rank import MemoryReceiver
from run_temporal_ground import step
from run_output_time import expr_eval


def open_rank(m,v,i,limit=2_000_000):
    r=m.open(i,max_work=limit);assert v.book(i).open_rank(r.packet());m.commit_open(r);return r

def seed(m,v,i,p,r):
    b=m.book(i);z=b.seed(p,exact=r);assert v.book(i).admit_seed(z);b.commit_seed(z)

def transfer(m,v,i,p,k=None):
    z=m.transfer(i,p,threshold=k);assert v.verify(i,p,k,z);m.commit_transfer(z);return z

class CompositionTests(unittest.TestCase):
    def fixture(self,flip=False):
        l,a=test_temporal_rank.RankTests().fixture();t=l.extend('xor',0,1);link=make_link(l,0,t,flip);a.extend(l.export());m=Memory(l);v=MemoryReceiver(a);assert v.admit_link(link);m.commit_link(link);return l,a,m,v,t,link
    def test_residual_transfer(self):
        for flip in (False,True):
            l,a,m,v,t,z=self.fixture(flip);r=Rank(l,0);full=Rank(l,t)
            for p in range(m.P+1):seed(m,v,0,p,r)
            for i in (z['plus'],z['minus']):open_rank(m,v,i)
            for p in range(m.P+1):
                x=transfer(m,v,t,p);self.assertEqual(x['status'],'EXACT');self.assertEqual(int(x['lower']),full.rank(l.D+p)-full.before)
            self.assertEqual(m.book(t).anchors,v.book(t).anchors);self.assertNotIn(t,m.ranks);self.assertNotIn(0,m.ranks)
    def test_linear_joint(self):
        l,a=test_temporal_rank.RankTests().fixture();u=l.extend('or',0,1);t=l.extend('and',0,1);x=l.extend('xor',0,1);a.extend(l.export());m=Memory(l);v=MemoryReceiver(a)
        for i in (0,1,u):open_rank(m,v,i)
        z=dict(kind='linear',target=t,constant=0,terms=[[0,1],[1,1],[u,-1]]);self.assertTrue(v.admit_linear(z));m.commit_link(z)
        for p in range(m.P+1):self.assertEqual(int(transfer(m,v,t,p)['lower']),Rank(l,t).rank(l.D+p))
        # A new exact relation may use facts learned from a previous relation.
        z=dict(kind='linear',target=x,constant=0,terms=[[0,1],[1,1],[t,-2]]);self.assertTrue(v.admit_linear(z));m.commit_link(z)
        for p in range(m.P+1):
            r=transfer(m,v,x,p);self.assertEqual(r['status'],'EXACT');self.assertEqual(int(r['lower']),Rank(l,x).rank(l.D+p))
        self.assertNotIn(t,m.ranks);self.assertNotIn(x,m.ranks)
    def test_ordinal_after_transfer(self):
        l,a,m,v,t,z=self.fixture();r=Rank(l,0);full=Rank(l,t)
        for i in (z['plus'],z['minus']):open_rank(m,v,i)
        for p in range(m.P+1):seed(m,v,0,p,r);transfer(m,v,t,p)
        b=m.book(t);c=v.book(t)
        for j in (1,10**900+173):
            y=b.select(j,budget=1);self.assertTrue(c.admit_select(j,y,budget=1));b.commit(y);self.assertEqual(y['time'],full.select(j)['time'])
    def test_forgery(self):
        l,a,m,v,t,z=self.fixture();r=Rank(l,0);seed(m,v,0,3,r);x=m.transfer(t,3,threshold=1);old=v.book(t).anchors
        for key,value in [('phase','02'),('target',True),('threshold','2'),('links',[99]),('links',[0,0]),('lower','999'),('upper','999'),('status','EXACT' if x['status']!='EXACT' else 'UNKNOWN')]:
            bad=copy.deepcopy(x);bad[key]=value;self.assertFalse(v.verify(t,3,1,bad));self.assertEqual(v.book(t).anchors,old)
        for key,val in [('flip',True),('plus',z['view']),('nt',z['target']),('base',True)]:
            bad=copy.deepcopy(z);bad[key]=val;self.assertFalse(v.admit_link(bad))
        bad=dict(kind='linear',target=t,constant=0,terms=[[0,1],[1,1]]);self.assertFalse(v.admit_linear(bad));self.assertFalse(v.admit_linear(bad,max_work=1))
    def test_random_sources(self):
        rng=random.Random(31031)
        for _ in range(120):
            w=rng.choice([1,2]);k=w*rng.randrange(2,6);p=list(range(k//w));rng.shuffle(p);f=[[rng.randrange(2**w) for _ in range(2**w)] for _ in p];u=rng.getrandbits(k);expr=[('xor',0,k-1),('or',0,k-1)]
            nav,rec=prepare(k,w,p,f,u,expr);d,r=compile_algebra(nav,u);a=Admission(rec,r);l=Language(d,r)
            t=l.extend(rng.choice(['and','or','xor']),0,1);op=l.ops[-1][0];link=make_link(l,0,t,bool(rng.randrange(2)));a.extend(l.export());m=Memory(l);v=MemoryReceiver(a);self.assertTrue(v.admit_link(link));m.commit_link(link)
            # Independent direct trajectory, including finite transient.
            values=[];src=u
            for q in range(l.D+m.P):
                b,c=[expr_eval(e,src) for e in expr];values.append((b,c,b&c if op=='and' else b|c if op=='or' else b^c));src=step(src,k,w,p,f)
            rr=Rank(l,0);phases=sorted(set([0,m.P]+[rng.randrange(m.P+1) for _ in range(5)]))
            for q in phases:seed(m,v,0,q,rr)
            for q in range(m.P+1):
                exact=sum(row[2] for row in values[l.D:l.D+q]);z=transfer(m,v,t,q,exact+1);self.assertLessEqual(int(z['lower']),exact);self.assertGreaterEqual(int(z['upper']),exact)
            for i in (link['plus'],link['minus']):open_rank(m,v,i)
            for q in phases:
                z=transfer(m,v,t,q);self.assertEqual(z['status'],'EXACT');self.assertEqual(int(z['lower']),sum(row[2] for row in values[l.D:l.D+q]))
            self.assertEqual(m.book(t).anchors,v.book(t).anchors)
    def test_linear_complement_with_transient(self):
        nav,rec=prepare(3,1,[0,2,1],[[0,0],[0,1],[0,1]],3,[0,1]);d,r=compile_algebra(nav,3);l=Language(d,r);a=Admission(rec,r);t=l.extend('not',0);a.extend(l.export());m=Memory(l);v=MemoryReceiver(a);open_rank(m,v,0)
        z=dict(kind='linear',target=t,constant=1,terms=[[0,-1]]);self.assertTrue(v.admit_linear(z));m.commit_link(z)
        for p in range(m.P+1):self.assertEqual(transfer(m,v,t,p)['lower'],str(p))
    def test_closed_rank_refuses_old_receipt(self):
        l,a,m,v,t,z=self.fixture();r=open_rank(m,v,0);open_rank(m,v,z['plus']);open_rank(m,v,z['minus']);p=3;x=m.transfer(t,p);self.assertEqual(x['status'],'EXACT');v.book(0).close_rank();m.close(0);self.assertFalse(v.verify(t,p,None,x));self.assertTrue(v.verify(t,p,None,m.transfer(t,p)))
    def test_shift_transfer(self):
        rng=random.Random(312)
        for _ in range(80):
            w=rng.choice([1,2]);k=w*rng.randrange(2,6);p=list(range(k//w));rng.shuffle(p);f=[[rng.randrange(2**w) for _ in range(2**w)] for _ in p];u=rng.getrandbits(k)
            nav,rec=prepare(k,w,p,f,u,[('xor',0,k-1)]);d,r=compile_algebra(nav,u);a=Admission(rec,r);l=Language(d,r);m=Memory(l);v=MemoryReceiver(a)
            delta=10**900+rng.randrange(100);t=l.extend('shift',0,delta);a.extend(l.export());z=dict(kind='shift',base=0,target=t,delta=delta);self.assertTrue(v.admit_shift(z));m.commit_link(z)
            rr=open_rank(m,v,0)
            for phase in range(m.P+1):
                fact=m.fact(0,phase);self.assertTrue(v.admit_fact(0,phase,fact));m.commit_fact(fact)
                bad=dict(fact,rank=str(int(fact['rank'])+1));self.assertFalse(v.admit_fact(0,phase,bad))
            m.close(0);v.book(0).close_rank()
            old=v.book(0).anchors;self.assertFalse(v.admit_fact(0,0,dict(index=0,phase='0',rank='0')));self.assertEqual(v.book(0).anchors,old)
            full=Rank(l,t)
            for phase in range(m.P+1):
                got=transfer(m,v,t,phase);self.assertEqual(got['status'],'EXACT');self.assertEqual(int(got['lower']),full.rank(l.D+phase)-full.before)
            bad=dict(z,delta=-1);self.assertFalse(v.admit_shift(bad));self.assertFalse(v.admit_shift(dict(z,target=True)))
if __name__=='__main__':unittest.main()
