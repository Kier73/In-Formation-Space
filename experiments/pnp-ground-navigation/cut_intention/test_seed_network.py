import unittest
from dataclasses import replace
from run_cross_ground_seed import make
from test_cross_ground_seed import language
from compositional_rank import Memory
from verify_compositional_rank import MemoryReceiver
from test_adaptive_seed import seed_facts
from seed_network import SeedNetwork
from temporal_rank import Rank
from adaptive_seed import Seed
from verify_adaptive_seed import restore_capsule


class SeedNetworkTests(unittest.TestCase):
    def setup_chain(self):
        # A: alternating 1,0. B: shifted 0,1. C: same as B shifted by
        # one, but with an independently irreversible bit flipping t=0.
        on,o=make(2,1,[1,0],[[0,1]]*2,1,[0]);l,a,r=language(on,o)
        bn,b=make(2,2,[0],[[1,2,3,0]],0,[0]);ll,aa,rr=language(bn,b)
        cn,c=make(3,1,[1,0,2],[[0,1],[0,1],[0,0]],5,[('xor',0,2)]);cl,ca,cr=language(cn,c)
        m=Memory(l);v=MemoryReceiver(a);seed_facts(m,v,0,range(m.P+1))
        g=SeedNetwork();x=g.register(o,r,0);y=g.register(b,rr,0);z=g.register(c,cr,0);g.attach(x,m,v)
        ab,_=g.link(x,y,[(0,0),(1,0)],cost=3);bc,_=g.link(y,z,[(1,0),(1,1)],cost=4)
        self.assertIsNotNone(ab);self.assertIsNotNone(bc);self.assertEqual(bc.start,1)
        return g,x,y,z,ab,bc,m,v,cl
    def test_route_and_composite(self):
        g,x,y,z,a,b,m,v,l=self.setup_chain()
        self.assertEqual(g.activate(z,1)[0]['time'],'2')
        k=10**900+11;out,attempts=g.activate(z,k);r,p,_=attempts[0]
        self.assertEqual(r.edges,(b.key,a.key));self.assertEqual(out['time'],Rank(l,0).select(k)['time'])
        self.assertIsNone(g.accept(z,k+1,r,p));self.assertIsNone(g.accept(z,k,replace(r,source_ordinal=r.source_ordinal+1),p));self.assertIsNone(g.accept(y,k,r,p))
        s=g.shortcut((b.key,a.key),cost=1);out,attempts=g.activate(z,k);self.assertEqual(attempts[0][0].edges,(s.key,));self.assertEqual(out['time'],Rank(l,0).select(k)['time'])
        self.assertEqual(s.shift,2);self.assertEqual(s.start,1)
    def test_seed_binding_and_restore(self):
        g,x,y,z,a,b,m,v,l=self.setup_chain()
        with self.assertRaises(ValueError):g.attach(y,m,v)
        restored=restore_capsule(v.a,Seed(m,[0]).recipe());self.assertIsNotNone(restored)
        rv,_=restored;g.attach(x,m,rv);self.assertEqual(g.activate(z,10**100+9)[0]['status'],'FOUND')
        self.assertEqual(g.activate(z,5,max_hops=0)[0]['status'],'UNKNOWN')
    def test_unreachable_through_suffix(self):
        on,o=make(1,1,[0],[[0,0]],1,[0]);l,a,r=language(on,o)
        nn,n=make(1,1,[0],[[0,0]],0,[0]);ll,aa,rr=language(nn,n)
        g=SeedNetwork();x=g.register(o,r,0);y=g.register(n,rr,0);g.attach(x,Memory(l),MemoryReceiver(a))
        e,_=g.link(x,y,[(1,0)]);self.assertEqual(e.offset,1);self.assertEqual(g.activate(y,1)[0],dict(status='UNREACHABLE',time=None))

if __name__=='__main__':unittest.main()
