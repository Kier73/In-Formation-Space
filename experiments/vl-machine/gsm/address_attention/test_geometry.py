import copy,unittest
import numpy as np
from geometry import *
class Geometry(unittest.TestCase):
    def test_partitions(self):
        self.assertEqual(len(set(GEOMS)),105)
        for g in GEOMS:self.assertEqual(len({tuple(x) for x in digits(g)}),256)
    def test_recovery(self):
        r=campaign();a,b,c=r['records'];self.assertEqual(tuple(a['geometry']),GEOMS[27]);self.assertEqual(tuple(b['geometry']),GEOMS[82]);self.assertEqual(b['admission']['exceptions'],8);self.assertEqual(c['admission']['mode'],'dense');self.assertLess(b['compact_query_error'],1e-10)
    def test_tamper(self):
        src=generated(GEOMS[27],44);g=GEOMS[27];c=fit(g,IDS,src,True);r,_=qualify(src,g,c);bad=copy.deepcopy(r);bad['coefficients'][0][0]+=1
        with self.assertRaises(ValueError):reconstruct(bad,digest(src))
    def test_dense_refusal(self):
        s=np.random.default_rng(43).normal(size=(N,D));g=GEOMS[0];c=fit(g,IDS,s);r,_=qualify(s,g,c);self.assertEqual(r['mode'],'dense')
if __name__=='__main__':unittest.main()
