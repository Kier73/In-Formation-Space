import itertools,unittest
import numpy as np
from address_attention import rectangles,fixture,Ground

class AddressAttention(unittest.TestCase):
    def test_cover(self):
        for lo in range(28):
            for hi in range(lo,28):
                xs=[]
                for box in rectangles(lo,hi,3,3):
                    xs += [9*a+3*b+c for a,b,c in itertools.product(*(range(i,j) for i,j in box))]
                self.assertEqual(sorted(xs),list(range(lo,hi)))
    def test_dense(self):
        r=np.random.default_rng(99)
        for radix in (3,5,8):
            g=fixture(radix,3,patches=8)
            for stop in (1,radix-1,radix,radix+1,g.n//2,g.n-1,g.n):
                for scale in (1,50):
                    q=r.normal(size=8)*scale
                    a,w=g.query(q,stop);b=g.dense(q,stop,chunk=17)
                    np.testing.assert_allclose(a,b,atol=1e-10,rtol=1e-10)
    def test_validation(self):
        g=fixture(3,3);q=np.ones(8)
        for t in (0,-1,g.n+1,True):
            with self.assertRaises(ValueError):g.query(q,t)
        with self.assertRaises(ValueError):g.query(np.ones(7),1)
        with self.assertRaises(ValueError):Ground(g.k,g.v,g.p,{g.n:(q,np.ones(4))})
    def test_full_address(self):
        g=fixture(64,4);q=np.zeros(8);a,w=g.query(q,g.n)
        expect=g.v.mean(axis=1).sum(axis=0)+g.p.mean(axis=1).prod(axis=0)
        for addr,(_,v) in g.overrides.items():
            digits=[(addr//64**(3-j))%64 for j in range(4)]
            old=sum(g.v[j,d] for j,d in enumerate(digits))+np.prod([g.p[j,d] for j,d in enumerate(digits)],axis=0)
            expect+=(v-old)/g.n
        np.testing.assert_allclose(a,expect,atol=1e-12);self.assertEqual(w['logical_addresses'],2**24)
if __name__=='__main__':unittest.main()
