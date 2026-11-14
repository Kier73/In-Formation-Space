"""BMO-006: independent tests of inherited depth-five hull certification."""

from fractions import Fraction as F
import math
import unittest

import depth5_phase as phase
from angle_transitions import endpoint_polynomials, oriented_cross, evaluate
from canopy import grammar, trace


class DepthFivePhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labels = phase.signatures(5)
        cls.points = tuple(map(endpoint_polynomials, cls.labels))

    def test_all_angle_exact_certificate(self):
        report = phase.certificate()
        self.assertEqual(report['drawn_segments'], 3125)
        self.assertEqual(report['symbolic_endpoints'], 3126)
        self.assertEqual(report['certified_halfplane_checks'], 1659)
        self.assertEqual(report['strict_convexity_checks'], 54)
        self.assertEqual(report['naive_all_endpoints_checks'], 168804)
        self.assertEqual([r['hull_vertices'] for r in report['continuous_regimes']],
                         [4, 5, 6, 7, 7, 8, 8, 9])
        self.assertEqual([r['hull_vertices'] for r in report['exact_boundaries']],
                         [4, 5, 6, 7, 8])
        self.assertEqual([r['recursion_candidates'] for r in report['continuous_regimes']],
                         [16, 21, 26, 31, 31, 36, 36, 36])

    def test_mod_17_irreducibility_and_quartic_arithmetic(self):
        self.assertTrue(phase.quartic_irreducible_mod_17())
        self.assertEqual(phase.poly_mod_remainder((1, 0, 1), (1, 1), 17), (2,))
        self.assertEqual(phase.poly_mod_remainder((1, 2, 1), (1, 1), 17), ())
        self.assertEqual(evaluate(phase.QUARTIC, phase.SIGMA), phase.QuarticRoot((0,)))
        s = phase.SIGMA
        self.assertEqual(s**4, F(-65, 864) + F(-136,864)*s +
                         F(696, 864)*s**2 + F(288, 864)*s**3)
        self.assertTrue(F(23,25) < s < F(93,100))
        self.assertTrue(s*s > F(4,5))
        self.assertTrue(1 - s > 0)
        self.assertTrue(s-F(23,25)>0)
        self.assertTrue(s-F(93,100)<0)
        with self.assertRaises(ValueError):
            _ = s**(-1)

    def test_unique_root_rational_isolation(self):
        a,b = phase.isolate_quartic(120)
        self.assertTrue(F(23,25)<a<phase.SIGMA<b<F(93,100))
        self.assertLess(phase.rational_poly_at(phase.QUARTIC,a),0)
        self.assertGreater(phase.rational_poly_at(phase.QUARTIC,b),0)
        self.assertGreater(3456*F(23,25)**3-864*F(93,100)**2-
                           1392*F(93,100)+136, 0)
        # A quartic can have other real roots; the *local* isolator is unique.
        self.assertNotEqual(phase.rational_poly_at(phase.QUARTIC,F(1,2)),0)

    def test_five_affine_copies_reconstruct_entire_endpoint_set(self):
        old=phase.previous_signatures(4)
        all_images=set()
        for signature in old:
            for turn,up in ((0,0),(1,81),(0,81),(-1,162),(0,162)):
                all_images.add(phase.transform_signature(signature,turn,up))
        self.assertEqual(all_images,set(self.labels))
        self.assertEqual([len(phase.recursive_candidates(k,self.labels))
                          for k in range(6)], [16,21,26,31,31,36])

    def test_full_endpoint_hulls_agree_with_reduced_candidates(self):
        # Exact rational samples, not substitutes for the universal
        # polynomial-interval proof in certificate().
        for cosine, stage, count in ((F(1,8),0,4),(F(3,8),1,5),
                                      (F(3,5),2,6),(F(37,50),3,7),
                                      (F(4,5),4,7),(F(9,10),5,8),
                                      (F(19,20),5,9)):
            with self.subTest(cosine=str(cosine)):
                reduced=phase.recursive_candidates(stage,self.labels)
                full=phase.hull(self.points,tuple(range(len(self.points))),cosine)
                small=phase.hull(self.points,reduced,cosine)
                self.assertEqual(set(full),set(small))
                self.assertEqual(len(full),count)

    def test_new_boundary_collinearity_and_sign_change(self):
        triple=(0,2344,2345)
        cross_poly=oriented_cross(*(self.points[i] for i in triple))
        self.assertEqual(cross_poly,tuple(3*x for x in phase.QUARTIC))
        self.assertEqual(evaluate(cross_poly,phase.SIGMA),phase.QuarticRoot((0,)))
        self.assertLess(evaluate(cross_poly,F(23,25)),0)
        self.assertGreater(evaluate(cross_poly,F(93,100)),0)
        self.assertEqual(phase.hull(self.points,phase.recursive_candidates(5,self.labels),
                                    phase.SIGMA),
                         (2345,2350,2375,2500,3125,1250,875,0))

    def test_symbolic_points_agree_with_independent_float_turtle(self):
        word=grammar(5)
        self.assertEqual(word.count('F'),3125)
        for angle_deg in (10,22,35,51,72,85):
            with self.subTest(angle=angle_deg):
                theta=math.radians(angle_deg)
                c=math.cos(theta);s=math.sin(theta)
                traced=[(0.,0.)]+[(x2,y2) for _,_,x2,y2 in trace(word,angle_deg)]
                self.assertEqual(len(traced),len(self.points))
                for (x,y),(xp,yp) in zip(traced,self.points):
                    symbolic_x=s*sum(a*c**i for i,a in enumerate(xp))
                    symbolic_y=sum(a*c**i for i,a in enumerate(yp))
                    self.assertLess(math.hypot(x-symbolic_x,y-symbolic_y),2e-9)

    def test_validation(self):
        for invalid in (-1,6,2.1,True):
            with self.subTest(depth=invalid),self.assertRaises(ValueError):
                phase.signatures(invalid)
        self.assertEqual([len(phase.signatures(k)) for k in range(6)],
                         [2,6,26,126,626,3126])
        with self.assertRaises(ZeroDivisionError):
            phase.poly_mod_remainder((1,2),(0,))


if __name__=='__main__':unittest.main()
