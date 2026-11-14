"""Independent reconstruction tests for BMO-008 exact depth-six hull phases."""
from fractions import Fraction as F
import math
import unittest

import depth6_phase as phase
import depth5_phase as previous
from depth4_phase import transform_signature
from all_depth_law import new_corner_polynomial
from angle_transitions import endpoint_polynomials, oriented_cross, evaluate
from canopy import grammar, trace


class DepthSixPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signatures=phase.signatures(6)
        cls.points=tuple(map(endpoint_polynomials,cls.signatures))

    def test_full_continuum_certificate(self):
        report=phase.certificate(verify_previous=True)
        self.assertEqual(report['drawn_segments'],15625)
        self.assertEqual(report['symbolic_endpoints'],15626)
        self.assertEqual(report['exact_containment_checks'],2483)
        self.assertEqual(report['exact_corner_checks'],73)
        self.assertEqual(report['naive_full_endpoint_checks'],1140698)
        self.assertEqual(report['inherited_hull_regimes'],9)
        self.assertEqual(report['inherited_vertex_polynomial_identifications'],63)
        self.assertEqual(report['outside_tip_witness_bernstein_signs'],[0,1,1,1,1,1])
        self.assertEqual([r['vertices'] for r in report['regimes']],
                         [4,5,6,7,7,8,8,9,9,10])
        self.assertEqual([r['inherited_candidates'] for r in report['regimes']],
                         [16,21,26,31,31,36,36,41,41,41])
        self.assertEqual([r['vertices'] for r in report['boundaries']],
                         [4,5,6,7,8,9])

    def test_quintic_root_isolation_and_arithmetic(self):
        self.assertTrue(phase.quintic_irreducible_mod_7())
        lo,hi=phase.isolate_quintic(130)
        self.assertLess(lo,phase.LAMBDA)
        self.assertGreater(hi,phase.LAMBDA)
        self.assertEqual(evaluate(phase.QUINTIC,phase.LAMBDA),phase.QuinticRoot((0,)))
        self.assertTrue(F(951,1000)<phase.LAMBDA<F(952,1000))
        self.assertEqual(phase.LAMBDA**5,
                         (F(97,5184)-F(1108,5184)*phase.LAMBDA
                          -F(1248,5184)*phase.LAMBDA**2
                          +F(5472,5184)*phase.LAMBDA**3
                          +F(1728,5184)*phase.LAMBDA**4))
        self.assertTrue(phase.LAMBDA**2>F(9,10))
        self.assertTrue(phase.LAMBDA<1)
        self.assertTrue(1-phase.LAMBDA>0)
        with self.assertRaises(ValueError):
            phase.LAMBDA**(-1)

    def test_five_affine_copies_recover_all_sixth_level_points(self):
        old=previous.signatures(5)
        copies=((0,0),(1,243),(0,243),(-1,486),(0,486))
        images={transform_signature(s,turn,up) for s in old for turn,up in copies}
        self.assertEqual(images,set(self.signatures))
        self.assertEqual([len(phase.inherited_candidates(k,self.signatures)) for k in range(8)],
                         [16,21,26,31,31,36,36,41])
        for i,old_signature in enumerate(old):
            self.assertEqual(self.signatures[5*i],
                             tuple((heading,3*n) for heading,n in old_signature))

    def test_full_endpoint_hulls_against_reduced_candidates(self):
        # Exact rational samples independently falsify the inherited candidates.
        # All-angle verification is supplied separately by the Bernstein certificate.
        probes=((F(1,8),0,4),(F(3,8),1,5),(F(3,5),2,6),
                (F(4,5),4,7),(F(9,10),5,8),
                (F(927,1000),7,9),(F(945,1000),7,9),
                (F(952,1000),7,10))
        for cosine,stage,vertices in probes:
            with self.subTest(cosine=str(cosine)):
                candidates=phase.inherited_candidates(stage,self.signatures)
                direct=phase.exact_hull(self.points,range(len(self.points)),cosine)
                inherited=phase.exact_hull(self.points,candidates,cosine)
                self.assertEqual(set(direct),set(inherited))
                self.assertEqual(len(direct),vertices)

    def test_exposure_witness_and_prior_scaled_hull(self):
        a,b=11719,11720
        polynomial=oriented_cross(self.points[0],self.points[a],self.points[b])
        self.assertEqual(polynomial,new_corner_polynomial(6))
        self.assertEqual(polynomial,tuple(3*x for x in phase.QUINTIC))
        self.assertEqual(evaluate(polynomial,phase.LAMBDA),phase.QuinticRoot((0,)))
        self.assertLess(evaluate(polynomial,F(95,100)),0)
        self.assertGreater(evaluate(polynomial,F(96,100)),0)
        self.assertNotIn(a,phase.exact_hull(self.points,
                             phase.inherited_candidates(7,self.signatures),F(95,100)))
        self.assertIn(a,phase.exact_hull(self.points,
                             phase.inherited_candidates(7,self.signatures),F(96,100)))
        at_root=phase.exact_hull(self.points,
                                 phase.inherited_candidates(7,self.signatures),phase.LAMBDA)
        self.assertEqual(len(at_root),9)
        self.assertNotIn(a,at_root)

    def test_symbolic_endpoints_match_independent_float_turtle(self):
        word=grammar(6)
        self.assertEqual(word.count('F'),15625)
        for theta in (12.,18.,35.,65.,84.):
            with self.subTest(angle=theta):
                rad=math.radians(theta)
                cosine=math.cos(rad);sine=math.sin(rad)
                turtle=[(0.,0.)]+[(x2,y2) for _,_,x2,y2 in trace(word,theta)]
                self.assertEqual(len(turtle),len(self.points))
                for (x,y),(xp,yp) in zip(turtle,self.points):
                    cx=sine*sum(v*cosine**j for j,v in enumerate(xp))
                    cy=sum(v*cosine**j for j,v in enumerate(yp))
                    self.assertLess(math.hypot(cx-x,cy-y),1e-8)

    def test_invalid_inputs_and_modular_root_check(self):
        self.assertEqual(len(phase.signatures(6)),15626)
        for bad in (-1,7,True,2.5):
            with self.subTest(bad=bad),self.assertRaises(ValueError):phase.signatures(bad)
        for bad in (0,True,-1,1.1):
            with self.subTest(bad=bad),self.assertRaises(ValueError):phase.isolate_quintic(bad)
        self.assertTrue(all(phase.rational_poly_at(phase.QUINTIC,x)%7 for x in range(7)))


if __name__=='__main__':
    unittest.main()
