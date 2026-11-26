import unittest,itertools
import numpy as np
from interaction import *

class Interaction(unittest.TestCase):
    def test_orders(self):
        r=np.random.default_rng(9);u=r.normal(size=(4,3,8));q=r.normal(size=4)
        for edges in ((),((0,1),(1,2),(2,3)),EDGES):
            p={e:r.normal(size=(3,3,8)) for e in edges}
            for stop in (1,17,80,81):
                b=enumerate_softmax(u,p,q,stop)
                for order in itertools.permutations(range(4)):
                    a,_=contract(u,p,q,stop,order);np.testing.assert_allclose(a,b,atol=1e-11,rtol=1e-11)
    def test_acquisition(self):
        r=np.random.default_rng(501);e=MODELS[3];s=DESIGNS[e]@r.integers(-4,5,(22,8));pool=r.permutation(256)[:192];seen=[]
        def read(i):seen.append(i);return s[i].copy()
        edge,c,trace=learn(read,pool,pool[:12],32,'active',700)
        self.assertEqual(len(seen),32);self.assertEqual(len(set(seen)),32);self.assertTrue(set(seen)<=set(pool));self.assertEqual(edge,e);np.testing.assert_array_equal(DESIGNS[edge]@np.rint(c),s)
    def test_negative(self):
        r=np.random.default_rng(42);s=r.normal(size=(256,8));e,c,t=learn(lambda i:s[i],range(192),range(12),32,'active',1);self.assertFalse(np.array_equal(DESIGNS[e]@c,s))
    def test_cost(self):
        self.assertEqual(order_for(((0,1),(1,2),(2,3)),64)[1],(12352,4096));self.assertEqual(order_for(EDGES,64)[1][1],2**24)
        with self.assertRaises(ValueError):contract(np.zeros((4,4,8)),{},np.ones(4),0)
if __name__=='__main__':unittest.main()
