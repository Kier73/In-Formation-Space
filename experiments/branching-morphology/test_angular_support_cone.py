"""Independent finite audits of the all-depth stochastic-support theorem."""
from fractions import Fraction
import math
import unittest

import angular_support_cone as cone
import depth6_phase
import all_depth_law
from tip_exposure import tip_index
from canopy import grammar, trace


class AngularSupportingConeTests(unittest.TestCase):
    def test_tip_histogram_matches_independent_symbolic_turtle(self):
        for n in range(1, 7):
            with self.subTest(depth=n):
                labels = depth6_phase.signatures(n)
                a = cone.nested_tip_headings(n)
                self.assertEqual(labels[tip_index(n)], a)
                self.assertEqual(sum(count for _, count in a), 3**n)
                for j in range(1, n+1):
                    self.assertEqual(cone.tail_counts(a, -j), 3**(n-j))
                self.assertEqual(cone.normalized_left_tail_defects(a,n), (0,)*n)

    def test_all_endpoint_tail_inequalities_exact_through_depth_six(self):
        for n in range(1,7):
            with self.subTest(depth=n):
                labels = depth6_phase.signatures(n)
                equal = []
                for i,signature in enumerate(labels):
                    slacks = cone.normalized_left_tail_defects(signature,n)
                    self.assertTrue(all(x >= 0 for x in slacks))
                    if i > 0 and all(x == 0 for x in slacks):
                        equal.append(i)
                self.assertEqual(equal,[tip_index(n)])

    def test_affine_copy_tail_transform_respects_invariant(self):
        # Reconstruct all five copies from the signed-heading histograms.
        def transform(signature, shift, trunk):
            counts = {shift+h:v for h,v in signature}
            counts[0] = counts.get(0, 0) + trunk
            return tuple(sorted((h,c) for h,c in counts.items() if c))
        for n in range(1,6):
            old = depth6_phase.signatures(n)
            s = 3**n
            for signature in old:
                for shift,trunk in ((0,0),(1,s),(0,s),(-1,2*s),(0,2*s)):
                    projected = transform(signature,shift,trunk)
                    self.assertTrue(all(x >= 0 for x in
                                        cone.normalized_left_tail_defects(projected,n+1)))

    def test_support_gap_and_cross_bound_across_every_endpoint(self):
        report = cone.certificate()
        self.assertEqual(len(report['finite_audits']),6)
        self.assertEqual([r['total_endpoints'] for r in report['finite_audits']],
                         [6,26,126,626,3126,15626])
        self.assertEqual([r['minimum_support_derivative_gap'] for r in report['finite_audits']],
                         [3**n for n in range(6)])

    def test_direct_turtle_geometry_against_new_support_margin(self):
        for n in range(1,7):
            theta = cone.guaranteed_angle(n)
            tip = tip_index(n)
            direct = [(0.,0.)] + [(x2,y2) for _,_,x2,y2 in trace(grammar(n), math.degrees(theta))]
            ax,ay = direct[tip]
            bound = cone.quantitative_cross_lower_bound(n,theta)
            for i,(x,y) in enumerate(direct):
                if i in (0,tip):
                    continue
                actual = ax*y-ay*x
                self.assertGreaterEqual(actual + 1e-8*max(1,abs(actual)),bound,(n,i))
            self.assertGreater(bound,0)

    def test_angle_interval_improves_previous_all_depth_bound(self):
        for n in range(1,40):
            new = cone.guaranteed_angle(n)
            previous = math.sqrt(Fraction(1,4*n**3*3**n))
            self.assertGreater(new,previous)
            self.assertAlmostEqual(math.degrees(new),45/n,places=12)
            self.assertGreater(cone.quantitative_cross_lower_bound(n,new),0)
        self.assertGreater(cone.guaranteed_angle(6) /
                           math.sqrt(Fraction(1,4*6**3*3**6)),100)

    def test_guaranteed_interval_is_below_candidate_zero(self):
        for n in range(2,31):
            self.assertLess(cone.guaranteed_angle(n),all_depth_law.first_candidate_zero(n))

    def test_fake_path_counterexample_is_not_in_grammar_cone(self):
        fake = ((-2,1),(0,1))
        self.assertLess(cone.normalized_left_tail_defects(fake,2)[1],0)
        self.assertEqual(cone.first_order_gap(cone.nested_tip_headings(4),4),0)
        for n in range(1,7):
            a = cone.nested_tip_headings(n)
            self.assertEqual(cone.cross_from_histograms(a,a,cone.guaranteed_angle(n)),0.)

    def test_closed_form_tip_distribution_at_large_depth(self):
        n = 1000
        a = cone.nested_tip_headings(n)
        self.assertEqual(len(a),n+1)
        self.assertEqual(sum(v for _,v in a),3**n)
        for j in (1,2,3,100,999,1000):
            self.assertEqual(cone.tail_counts(a,-j)*3**j,3**n)
        self.assertEqual(cone.normalized_left_tail_defects(a,n), (0,)*n)

    def test_guardrails(self):
        for bad in (0,-1,True,1.1):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError): cone.nested_tip_headings(bad)
                with self.assertRaises(ValueError): cone.guaranteed_angle(bad)
                with self.assertRaises(ValueError): cone.normalized_left_tail_defects((),bad)
        for bad in (0,-1,7,True):
            with self.subTest(value=bad),self.assertRaises(ValueError):
                cone.audit_depth(bad)
        for bad in (-0.1,0,math.pi,math.inf,math.nan):
            with self.subTest(theta=bad),self.assertRaises(ValueError):
                cone.quantitative_cross_lower_bound(4,bad)
        with self.assertRaises(ValueError):
            cone.normalized_left_tail_defects(((0,-1),),2)


if __name__ == '__main__':
    unittest.main()
