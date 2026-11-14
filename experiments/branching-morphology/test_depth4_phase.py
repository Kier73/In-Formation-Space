"""Independent checks of the BMO-005 exact recursive depth-four hull proof."""
from fractions import Fraction as F
import math
import unittest
import depth4_phase as m
from angle_transitions import endpoint_polynomials, oriented_cross, evaluate
from depth3_phase import ALPHA
from canopy import grammar, trace


class DepthFourRegimes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labels=m.signatures(4)
        cls.points=tuple(map(endpoint_polynomials,cls.labels))

    def test_exact_continuum_certificate(self):
        cert=m.certificate()
        self.assertEqual(cert['symbolic_endpoints'],626)
        self.assertEqual(cert['exact_halfplane_constraints'],1007)
        self.assertEqual(cert['full_endpoint_naive_constraints'],23162)
        self.assertEqual(cert['exact_strict_convexity_checks'],37)
        self.assertEqual([r['hull_vertices'] for r in cert['regimes']],[4,5,6,7,7,8])
        self.assertEqual([r['hull_vertices'] for r in cert['boundaries']],[4,5,6,7])
        self.assertEqual([r['recursive_candidates'] for r in cert['regimes']],[16,21,26,31,31,31])

    def test_cubic_unique_isolator_and_irreducibility(self):
        lo,hi=m.isolate_cubic(120)
        self.assertLess(m.rational_poly_at(m.CUBIC,lo),0)
        self.assertGreater(m.rational_poly_at(m.CUBIC,hi),0)
        self.assertLess(lo,m.RHO)
        self.assertGreater(hi,m.RHO)
        self.assertEqual(m.evaluate(m.CUBIC,m.RHO),m.CubicRoot((F(0),)))
        self.assertTrue(F(87,100)<m.RHO<F(88,100))
        self.assertEqual([x for x in range(5) if m.rational_poly_at(m.CUBIC,x)%5==0],[])
        self.assertEqual(m.RHO**3, F(-11,144)+F(80,144)*m.RHO+F(1,3)*m.RHO**2)
        self.assertTrue(m.RHO-F(87,100)>0)
        self.assertTrue(m.RHO-F(88,100)<0)

    def test_affine_copy_is_exact_endpoint_decomposition(self):
        old=m.previous_signatures(3)
        expected=set(self.labels)
        total=set()
        for signature in old:
            for turn, steps in ((0,0),(1,27),(0,27),(-1,54),(0,54)):
                total.add(m.transform_signature(signature,turn,steps))
        self.assertEqual(total,expected)
        self.assertEqual([len(m.recursive_candidate_indices(min(k,3),self.labels))
                          for k in range(6)],[16,21,26,31,31,31])

    def test_independent_full_hulls_inside_regimes(self):
        angles=(F(1,10),F(3,8),F(5,8),F(37,50),F(4,5),F(17,20),F(9,10))
        counts=(4,5,6,7,7,7,8)
        for c,count in zip(angles,counts):
            with self.subTest(c=str(c)):
                self.assertEqual(len(m.exact_hull_at(self.points,c)),count)
        for c,count in ((F(1,4),4),(F(1,2),5),(ALPHA,6),(m.RHO,7)):
            with self.subTest(c=str(c)):
                self.assertEqual(len(m.exact_hull_at(self.points,c)),count)

    def test_false_positive_is_identically_collinear(self):
        self.assertEqual(oriented_cross(self.points[0],self.points[94],self.points[470]),(0,))
        self.assertNotIn(94,m.exact_hull_at(self.points,F(4,5)))

    def test_symbolic_endpoint_coordinates_agree_with_original_turtle(self):
        word=grammar(4)
        for angle in (12.0,30.0,45.0,65.0,80.0):
            with self.subTest(angle=angle):
                c=math.cos(math.radians(angle))
                sine=math.sin(math.radians(angle))
                turtle=[(0.,0.)]+[(x2,y2) for _,_,x2,y2 in trace(word,angle)]
                self.assertEqual(len(turtle),len(self.points))
                for (x,y),(xp,yp) in zip(turtle,self.points):
                    xx=sine*sum(coef*c**i for i,coef in enumerate(xp))
                    yy=sum(coef*c**i for i,coef in enumerate(yp))
                    self.assertLess(math.hypot(x-xx,y-yy),1e-9)

    def test_invalid_depth_and_interval(self):
        for bad in (-1,5,3.5,True):
            with self.subTest(bad=bad),self.assertRaises(ValueError):m.signatures(bad)
        for polynomial in ((1,),(0,),(1,-1)):
            self.assertEqual(m.rational_poly_at(polynomial,F(1,3)),evaluate(polynomial,F(1,3)))


if __name__=='__main__':unittest.main()
