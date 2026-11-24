import copy,random,unittest
from math import prod,lcm
from run_cross_ground_seed import make,expand
from run_disjunctive_time import fold
from run_temporal_ground import step
from shared_proof import evaluate
from temporal_algebra import compile_algebra,Language
from verify_temporal_algebra import Admission
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from test_adaptive_seed import seed_facts
from cross_ground_seed import discover,cycles
from verify_cross_ground_seed import verify_bridge,BridgeAdmission
from trajectory_bridge import discover_trajectory
from verify_trajectory_bridge import verify_shift,TrajectoryAdmission
from adaptive_seed import Seed
from verify_adaptive_seed import restore_capsule
from temporal_rank import Rank
from verify_temporal_rank import CheckedRank


def language(nav,rec):
    d,r=compile_algebra(nav,rec.initial);return Language(d,r),Admission(rec,r),r


def mapped(code,new,old,z):
    return sum(z['maps'][i][code//new.a**j%new.a]*old.a**i for i,j in enumerate(z['align']))


def fixture(w,p,f,u,live,extra=1,seed=33):
    k=w*len(p);e=fold('xor',live) if len(live)>1 else live[0];on,old=make(k,w,p,f,u,[e])
    nw,pp,ff,uu,ports,_,_=expand(w,p,f,u,live,seed=seed,extra=extra)
    ne=[nw*j+b for _,_,j,b,_ in ports];ne=fold('xor',ne) if len(ne)>1 else ne[0]
    nn,new=make(nw*len(pp),nw,pp,ff,uu,[ne],seed=44)
    return on,old,nn,new,ports


class CrossGroundTests(unittest.TestCase):
    def test_random_uniform_commuting_square(self):
        rng=random.Random(330033);checked=0
        for n in range(80):
            w=rng.choice((1,2));m=rng.randrange(2,5);p=list(range(m));rng.shuffle(p);f=[[rng.randrange(1<<w) for _ in range(1<<w)] for _ in p];u=rng.getrandbits(w*m)
            live=[w*z[0]+rng.randrange(w) for z in cycles(p)]
            on,o,nn,b,ports=fixture(w,p,f,u,live,extra=rng.randrange(2),seed=n)
            z=discover(o,b,0,0,ports=ports);self.assertEqual(z['status'],'FOUND',z);z=z['proof'];self.assertTrue(verify_bridge(o,b,z))
            self.assertEqual(mapped(b.initial,b,o,z),o.initial)
            # Independently check every small new cube, or 64 random larger codes.
            xs=range(1<<b.k) if b.k<=9 else [rng.getrandbits(b.k) for _ in range(64)]
            for x in xs:
                y=mapped(x,b,o,z);yp=step(y,o.k,o.w,o.g['pred'],o.g['tables']);xp=step(x,b.k,b.w,b.g['pred'],b.g['tables'])
                self.assertEqual(mapped(xp,b,o,z),yp);self.assertEqual(evaluate(o.circuit,y,o.k),evaluate(b.circuit,x,b.k));checked+=1
            # Same output sequence for multiple future coordinates.
            for t in (0,1,2,11,10**100+7):
                self.assertEqual(on.result(o.initial,t)['outputs'],nn.result(b.initial,t)['outputs'])
        self.assertGreater(checked,3000)
    def test_unpinned_cycle_and_extra(self):
        # Single old cycle, two new cycles. No hints required in this control.
        on,o=make(2,1,[1,0],[[0,1],[0,1]],1,[0]);nn,b=make(3,1,[1,0,2],[[0,1],[0,1],[0,1]],1,[0]);z=discover(o,b,0,0)
        self.assertEqual(z['status'],'FOUND');self.assertTrue(verify_bridge(o,b,z['proof']))
    def test_corrupt_bridge_and_output(self):
        on,o,nn,b,ports=fixture(2,[1,0,2],[[0,1,3,2],[0,1,2,3],[0,1,0,1]],7,[0,4]);z=discover(o,b,0,0,ports=ports)['proof'];self.assertTrue(verify_bridge(o,b,z))
        bads=[dict(z,old='bad'),dict(z,new_initial='0'),dict(z,old_output=True),dict(z,align=[z['align'][0]]*len(z['align'])),dict(z,maps=[[0]*b.a]+z['maps'][1:]),dict(z,old_refs=[[1,1],[-1,0]])]
        h=copy.deepcopy(z);h['maps'][0][0]=(h['maps'][0][0]+1)%o.a;bads.append(h)
        h=copy.deepcopy(z);h['new_refs'][-1][1]=1-h['new_refs'][-1][1];bads.append(h)
        for bad in bads:self.assertFalse(verify_bridge(o,b,bad))
        self.assertFalse(verify_bridge(o,b,z,max_work=1));self.assertEqual(discover(o,b,0,0,ports=ports,max_work=1)['status'],'UNKNOWN')
        # Real decoder that observes an additional independent bit is not compatible.
        nn2,b2=make(b.k,b.w,b.g['pred'],b.g['tables'],b.initial,[('xor',b.w*ports[0][2]+ports[0][3],b.w*ports[-1][2]+ports[-1][3]),0]);self.assertFalse(verify_bridge(o,b2,z))
        self.assertEqual(discover(o,b2,0,1,ports=ports)['status'],'UNKNOWN')
    def test_seed_transfer_and_request_binding(self):
        on,o,nn,b,ports=fixture(1,[1,0,4,2,3],[[0,1]]*5,5,[0,2]);l,a,r=language(on,o);m=Memory(l);v=MemoryReceiver(a);seed_facts(m,v,0,range(m.P+1));z=discover(o,b,0,0,ports=ports)['proof'];ad=BridgeAdmission(o,b,r,v,z)
        ll,aa,rr=language(nn,b);rank=Rank(ll,0);cr=CheckedRank(aa,rank.packet())
        for k in (1,2,3,10**100+17):
            p=dict(bridge=ad.key,output=0,ordinal=str(k),rank=m.book(0).compact(k,budget=16));want=rank.select(k);self.assertTrue(cr.verify_select(k,want));self.assertEqual(ad.accept(k,p,budget=16),dict(status=want['status'],time=want['time']))
            self.assertIsNone(ad.accept(k+1,p,budget=16));self.assertIsNone(ad.accept(k,dict(p,bridge='bad'),budget=16));self.assertIsNone(ad.accept(k,dict(p,output=True),budget=16))
        # Memory cannot be substituted by an unrelated admitted output.
        other,oc=make(2,1,[0,1],[[0,1],[0,1]],1,[0]);_,av,ar=language(other,oc)
        with self.assertRaises(ValueError):BridgeAdmission(o,b,r,MemoryReceiver(av),z)
    def test_topology_free_shift(self):
        # Old 2-location transport; new one location, four-state cycle. A
        # spatial injection cannot exist, but the two output streams shift.
        on,o=make(2,1,[1,0],[[0,1],[0,1]],1,[0]);nn,b=make(2,2,[0],[[1,2,3,0]],0,[0]);l,a,r=language(on,o);ll,aa,rr=language(nn,b)
        self.assertEqual(discover(o,b,0,0)['status'],'UNKNOWN');q=discover_trajectory(l,0,ll,0);self.assertEqual(q['delta'],1);self.assertTrue(verify_shift(a,0,aa,0,1));self.assertFalse(verify_shift(a,0,aa,0,0));self.assertFalse(verify_shift(a,0,aa,0,1,max_work=1))
        m=Memory(l);v=MemoryReceiver(a);seed_facts(m,v,0,range(m.P+1));ad=TrajectoryAdmission(o,b,r,rr,v,0,0,1)
        for k in (1,2,3,10**100+9):
            z=dict(bridge=ad.key,output=0,ordinal=str(k),rank=m.book(0).compact(k+ad.offset));res=ad.accept(k,z);self.assertEqual(res,dict(status='FOUND',time=str(2*k-1)))
            self.assertIsNone(ad.accept(k+1,z))
    def test_restore_seed_into_bridge(self):
        on,o,nn,b,ports=fixture(1,[1,0],[[0,1],[0,1]],1,[0]);l,a,r=language(on,o);m=Memory(l);v=MemoryReceiver(a);seed_facts(m,v,0,range(m.P+1))
        recipe=Seed(m,[0]).recipe();fresh=Admission(o,r);restored=restore_capsule(fresh,recipe);self.assertIsNotNone(restored);rv,_=restored
        z=discover(o,b,0,0,ports=ports)['proof'];ad=BridgeAdmission(o,b,r,rv,z)
        k=10**900+3;p=dict(bridge=ad.key,output=0,ordinal=str(k),rank=m.book(0).compact(k))
        self.assertEqual(ad.accept(k,p),dict(status='FOUND',time=str(2*k-2)))
        bad=copy.deepcopy(recipe);bad['descriptor']['members'][0]['anchors'][1][1]='9';self.assertIsNone(restore_capsule(fresh,bad))
    def test_trajectory_is_not_uniform_compatibility(self):
        on,o=make(1,1,[0],[[0,1]],0,[0]);nn,b=make(2,2,[0],[[0,1,2,3]],0,[('or',0,1)])
        self.assertEqual(discover(o,b,0,0)['status'],'UNKNOWN')
        l,a,r=language(on,o);ll,aa,rr=language(nn,b);self.assertTrue(verify_shift(a,0,aa,0,0))
        m=Memory(l);v=MemoryReceiver(a);ad=TrajectoryAdmission(o,b,r,rr,v,0,0,0)
        k=3;z=dict(bridge=ad.key,output=0,ordinal=str(k),rank=m.book(0).compact(k));self.assertEqual(ad.accept(k,z),dict(status='UNREACHABLE',time=None))
        # The equality above is valid only at the admitted anchors: other initial codes disagree.
        self.assertEqual(on.result(0,0)['outputs'],[0]);self.assertEqual(nn.result(2,0)['outputs'],[1])
    def test_shift_removes_transient_event(self):
        on,o=make(1,1,[0],[[0,0]],1,[0]);nn,b=make(1,1,[0],[[0,0]],0,[0]);l,a,r=language(on,o);ll,aa,rr=language(nn,b)
        self.assertFalse(verify_shift(a,0,aa,0,0));self.assertTrue(verify_shift(a,0,aa,0,1));self.assertEqual(discover_trajectory(l,0,ll,0)['delta'],1)
        m=Memory(l);v=MemoryReceiver(a);ad=TrajectoryAdmission(o,b,r,rr,v,0,0,1);self.assertEqual(ad.offset,1)
        z=dict(bridge=ad.key,output=0,ordinal='1',rank=m.book(0).compact(2));self.assertEqual(ad.accept(1,z),dict(status='UNREACHABLE',time=None))
    def test_random_cross_basis_equivalence_oracle(self):
        rng=random.Random(3303)
        for _ in range(100):
            # Distinct random finite maps, initial codes, and periods.
            w1,w2=rng.choice((1,2)),rng.choice((1,2));m1,m2=rng.randrange(1,4),rng.randrange(1,4)
            def random_ground(w,m):
                p=list(range(m));rng.shuffle(p);f=[[rng.randrange(1<<w) for _ in range(1<<w)] for _ in p];u=rng.getrandbits(w*m);nav,rec=make(w*m,w,p,f,u,[0]);l,a,r=language(nav,rec);return l,a,rec
            l,a,o=random_ground(w1,m1);ll,aa,b=random_ground(w2,m2)
            for dt in (0,1,3):
                cutoff=max(ll.D,l.D-dt,0);P=lcm(prod(l.d.base),prod(ll.d.base));end=cutoff+P
                # Independent direct chronological oracle, including transient.
                x=o.initial;y=b.initial
                for _ in range(dt):x=step(x,o.k,o.w,o.g['pred'],o.g['tables'])
                good=True
                for _ in range(end):
                    if evaluate(o.circuit,x,o.k)!=evaluate(b.circuit,y,b.k):good=False;break
                    x=step(x,o.k,o.w,o.g['pred'],o.g['tables']);y=step(y,b.k,b.w,b.g['pred'],b.g['tables'])
                self.assertEqual(verify_shift(a,0,aa,0,dt),good)
                self.assertEqual(discover_trajectory(l,0,ll,0,deltas=(dt,))['status']=='FOUND',good)

if __name__=='__main__':unittest.main()
