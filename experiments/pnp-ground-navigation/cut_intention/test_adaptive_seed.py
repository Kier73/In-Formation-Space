import copy,random,unittest
from math import prod
from adaptive_seed import Seed,Work,joint_count
from verify_adaptive_seed import SeedReceiver,restore_capsule
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from test_output_time import prepare
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from temporal_rank import Rank
from run_temporal_ground import step
from run_output_time import expr_eval

def setup(k,w,p,f,u,expr):
    nav,rec=prepare(k,w,p,f,u,expr);d,r=compile_algebra(nav,u);l=Language(d,r);a=Admission(rec,r)
    return l,a,Memory(l),MemoryReceiver(a)

def seed_facts(m,v,i,phases):
    r=m.open(i);assert v.book(i).open_rank(r.packet());m.commit_open(r)
    for p in phases:
        z=m.fact(i,p);assert v.admit_fact(i,p,z);m.commit_fact(z)
    m.close(i);v.book(i).close_rank()

def adopt(m,v,seed,sr,proposal):
    z=seed.activate(proposal);assert z is not None
    if z['kind']=='residual':v.a.extend(m.lang.export())
    assert sr.admit(z)
    if z['kind']=='shift':m.commit_link(z)
    elif z['kind']=='residual':m.commit_link(z['link'])
    return z

def transfer(m,v,seed,sr,z,p):
    if z['kind']=='span':
        r=seed.transfer_span(z,p);assert sr.verify_span(len(sr.relations)-1,p,r);seed.commit_span(z,r)
    else:
        i=z['target'] if z['kind']=='shift' else z['link']['target'];r=m.transfer(i,p,links=[len(m.links)-1]);assert v.verify(i,p,None,r);m.commit_transfer(r)
    return r

def majority(a,b,c):return ('or',('or',('and',a,b),('and',a,c)),('and',b,c))

class SeedTests(unittest.TestCase):
    def fixture(self):
        k=10;p=[1,0,3,4,2,6,7,8,9,5];u=(1<<0)|(1<<2)|(1<<5);f=[[0,1]]*k
        return setup(k,1,p,f,u,[0,2,5,('xor',('xor',0,2),5),majority(0,2,5)])
    def test_rational_majority(self):
        l,a,m,v=self.fixture();P=m.P
        for i in range(4):seed_facts(m,v,i,range(P+1))
        s=Seed(m,[0,1]).combine(Seed(m,[2,3]));sr=SeedReceiver(v,s.members);self.assertTrue(sr.verify_descriptor(s.descriptor()))
        pr=s.discover(4,deltas=());z=adopt(m,v,s,sr,pr);self.assertEqual(z['den'],2);self.assertEqual(z['terms'],[[0,1],[1,1],[2,1],[3,-1]])
        r=Rank(l,4)
        for p in range(P+1):
            y=transfer(m,v,s,sr,z,p);self.assertEqual(y['status'],'EXACT');self.assertEqual(int(y['lower']),r.rank(l.D+p)-r.before)
        self.assertNotIn(4,m.ranks);self.assertEqual(m.book(4).anchors,v.book(4).anchors)
        # Learn a new seed and activate it on an unfamiliar complement.
        t=l.extend('not',4);a.extend(l.export());s2=Seed(m,[4]);sr2=SeedReceiver(v,s2.members);z2=adopt(m,v,s2,sr2,s2.discover(t,deltas=()));self.assertEqual(z2['terms'],[[4,-1]])
        for p in range(P+1):self.assertEqual(int(transfer(m,v,s2,sr2,z2,p)['lower']),p-m.book(4).anchors[p])
    def test_shift_no_construction_history(self):
        l,a,m,v=self.fixture();t=l.extend('shift',3,3);a.extend(l.export());seed_facts(m,v,3,range(m.P+1));s=Seed(m,[3]);sr=SeedReceiver(v,s.members)
        z=adopt(m,v,s,sr,s.discover(t));self.assertEqual(z['kind'],'shift');self.assertEqual(z['delta'],3)
        r=Rank(l,t)
        for p in range(m.P+1):self.assertEqual(int(transfer(m,v,s,sr,z,p)['lower']),r.rank(l.D+p)-r.before)
    def test_sparse_residual(self):
        l,a,m,v=self.fixture();rare=l.extend('and',0,1);rare=l.extend('and',rare,2);t=l.extend('xor',3,rare);a.extend(l.export());seed_facts(m,v,3,range(m.P+1));s=Seed(m,[3]);sr=SeedReceiver(v,s.members)
        z=adopt(m,v,s,sr,s.discover(t,deltas=(),max_difference=2));self.assertEqual(z['kind'],'residual');self.assertEqual(z['disagreement'],'1')
        for i in (z['link']['plus'],z['link']['minus']):
            r=m.open(i);self.assertTrue(v.book(i).open_rank(r.packet()));m.commit_open(r)
        r=Rank(l,t)
        for p in range(m.P+1):self.assertEqual(int(transfer(m,v,s,sr,z,p)['lower']),r.rank(l.D+p)-r.before)
    def test_partial_bounds_and_forgery(self):
        l,a,m,v=self.fixture()
        for i in range(4):seed_facts(m,v,i,[2,5])
        s=Seed(m,range(4));sr=SeedReceiver(v,s.members);z=s.discover(4,deltas=())['relation']
        for key,val in [('den',1),('constant',1),('terms',[[0,1]]),('target',True)]:
            bad=copy.deepcopy(z);bad[key]=val;self.assertFalse(sr.admit(bad));self.assertFalse(sr.relations)
        self.assertFalse(sr.admit(z,max_work=1));self.assertTrue(sr.admit(z));r=Rank(l,4)
        for p in range(m.P+1):
            q=s.transfer_span(z,p);truth=r.rank(l.D+p)-r.before;self.assertLessEqual(int(q['lower']),truth);self.assertGreaterEqual(int(q['upper']),truth)
            bad=dict(q,upper=str(int(q['upper'])+1));self.assertFalse(sr.verify_span(0,p,bad));self.assertTrue(sr.verify_span(0,p,q));s.commit_span(z,q)
        bad=s.descriptor();bad['members'][0]['anchors'][0][1]='1';self.assertFalse(sr.verify_descriptor(bad));self.assertTrue(sr.verify_descriptor(s.descriptor()))
    def test_budget_and_unrelated(self):
        l,a,m,v=self.fixture();seed_facts(m,v,0,[5]);s=Seed(m,[0]);sr=SeedReceiver(v,s.members)
        before=(len(l.roots),len(l.d.nodes),m.book(0).anchors)
        for pr in (s.discover(4,max_work=1),s.discover(4,deltas=(),max_difference=0)):
            self.assertEqual(pr['status'],'UNKNOWN');self.assertIsNone(s.activate(pr))
        self.assertEqual(before,(len(l.roots),len(l.d.nodes),m.book(0).anchors));self.assertFalse(sr.relations)
        other=self.fixture()[2];other.book(0);self.assertRaises(ValueError,s.combine,Seed(other,[0]))
    def test_random_exact_and_partial(self):
        rng=random.Random(32032)
        for _ in range(120):
            w=rng.choice([1,2]);k=w*rng.randrange(2,6);p=list(range(k//w));rng.shuffle(p);f=[[rng.randrange(2**w) for _ in range(2**w)] for _ in p];u=rng.getrandbits(k);expr=[0,k-1,('or',0,k-1),('and',0,k-1)]
            l,a,m,v=setup(k,w,p,f,u,expr);P=m.P;phases=range(P+1)
            # Independent chronological oracle; raw bits and AND/OR computed directly.
            vals=[];c=u
            for j in range(l.D+P):vals.append([expr_eval(e,c) for e in expr]);c=step(c,k,w,p,f)
            for i in range(3):seed_facts(m,v,i,phases)
            s=Seed(m,[0,1,2]);sr=SeedReceiver(v,s.members);z=adopt(m,v,s,sr,s.discover(3,deltas=()))
            self.assertEqual(z['kind'],'span')
            for p in phases:
                r=transfer(m,v,s,sr,z,p);self.assertEqual(r['status'],'EXACT');self.assertEqual(int(r['lower']),sum(row[3] for row in vals[l.D:l.D+p]))
            self.assertEqual(joint_count(l,0,1,Work(100000)),sum(row[0]*row[1] for row in vals[l.D:]))
    def test_transient_shift(self):
        l,a,m,v=setup(3,1,[0,2,1],[[0,0],[0,1],[0,1]],3,[('xor',0,1)])
        t=l.extend('shift',0,1);a.extend(l.export());seed_facts(m,v,0,range(m.P+1));s=Seed(m,[0]);sr=SeedReceiver(v,s.members);z=adopt(m,v,s,sr,s.discover(t));r=Rank(l,t)
        for p in range(m.P+1):self.assertEqual(int(transfer(m,v,s,sr,z,p)['lower']),r.rank(l.D+p)-r.before)
        self.assertGreater(l.D,0)
    def test_capsule_restart(self):
        l,a,m,v=self.fixture();proofs={}
        for i in range(4):
            r=Rank(l,i);proofs[i]=r.packet();seed_facts(m,v,i,[2,5,13])
        s=Seed(m,range(4));packet=s.capsule(proofs)
        # Rebuild the admitted source independently, with no retained ranks.
        ll,aa,mm,vv=self.fixture();restored=restore_capsule(aa,packet)
        self.assertIsNotNone(restored);rv,rs=restored
        self.assertTrue(rs.verify_descriptor(s.descriptor()));self.assertFalse(any(b.exact is not None for b in rv.books.values()))
        # Producer reconstruction is only a proposal; the new receiver has
        # independently established the same book contents from the proofs.
        for i in rs.members:mm.book(i)._anchors=rv.book(i).anchors
        ss=Seed(mm,range(4));self.assertTrue(rs.verify_descriptor(ss.descriptor()))
        z=adopt(mm,rv,ss,rs,ss.discover(4,deltas=()))
        self.assertEqual(z['den'],2);r=Rank(ll,4)
        for p in [2,5,13]:self.assertEqual(int(transfer(mm,rv,ss,rs,z,p)['lower']),r.rank(ll.D+p)-r.before)
        for mode in ['rank','proof','identity','missing','duplicate']:
            bad=copy.deepcopy(packet)
            if mode=='rank':bad['descriptor']['members'][0]['anchors'][1][1]='999'
            if mode=='proof':bad['proofs'][0][1]['terms'][0][2]+=1
            if mode=='identity':bad['descriptor']['identity']='x'
            if mode=='missing':bad['proofs'].pop()
            if mode=='duplicate':bad['descriptor']['members'][0]['anchors'].insert(1,bad['descriptor']['members'][0]['anchors'][0])
            self.assertIsNone(restore_capsule(aa,bad),mode)
        self.assertIsNone(restore_capsule(aa,packet,max_terms=1));self.assertIsNone(restore_capsule(aa,packet,max_facts=1))
        self.assertFalse(vv.books)
        recipe=s.recipe();rr=restore_capsule(aa,recipe);self.assertIsNotNone(rr);self.assertTrue(rr[1].verify_descriptor(s.descriptor()))
        self.assertIsNone(restore_capsule(aa,recipe,max_work=1))
        bad=copy.deepcopy(recipe);bad['descriptor']['members'][0]['anchors'][1][1]='999';self.assertIsNone(restore_capsule(aa,bad))
        # A correctly recomputed digest still cannot qualify an invented rank.
        from hashlib import sha256
        from json import dumps
        q=bad['descriptor'];body={k:v for k,v in q.items() if k!='identity'};q['identity']=sha256(dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertIsNone(restore_capsule(aa,bad))
    def test_discovery_prefers_available_rank_coordinates(self):
        l,a,m,v=self.fixture();alias=l.extend('xor',3,3);alias=l.extend('xor',0,alias);t=l.extend('not',0);a.extend(l.export())
        seed_facts(m,v,0,[1]);seed_facts(m,v,alias,[10,20]);s=Seed(m,[0,alias]);sr=SeedReceiver(v,s.members)
        z=adopt(m,v,s,sr,s.discover(t,deltas=(),phases=[10,20]));self.assertEqual(z['terms'],[[alias,-1]])
        for p in [10,20]:self.assertEqual(transfer(m,v,s,sr,z,p)['status'],'EXACT')
if __name__=='__main__':unittest.main()
