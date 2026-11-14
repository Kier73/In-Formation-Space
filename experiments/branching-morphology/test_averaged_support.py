"""Independent BMO-011 audits of averaged phase and supporting-line bounds."""
from __future__ import annotations

import math
import unittest
from fractions import Fraction

import averaged_support as mean
import angular_support_cone as previous
from all_depth_law import first_candidate_zero, new_corner_polynomial
from canopy import grammar, trace
from depth6_phase import signatures
from tip_exposure import tip_index


class AveragedSupportTests(unittest.TestCase):
    def test_tip_phasor_matches_direct_histogram(self):
        for n in range(1,12):
            with self.subTest(n=n):
                for fraction in (Fraction(1,4),Fraction(1,2),Fraction(1,1)):
                    theta=mean.improved_angle(n)*float(fraction)
                    tip=previous.nested_tip_headings(n)
                    direct=sum(count*complex(math.cos(-heading*theta),math.sin(-heading*theta))
                               for heading,count in tip)/(3**n)
                    self.assertLess(abs(mean.normalized_tip_phasor(n,theta)-direct),2e-15)

    def test_phase_is_inside_a_half_step(self):
        for n in range(1,51):
            for fraction in (0.1,0.5,1.0):
                theta=mean.improved_angle(n)*fraction
                phi, bound=mean.phase_enclosure(n,theta)
                self.assertGreater(phi,0)
                self.assertLess(phi,bound+1e-15)
                self.assertGreater(mean.normalized_tip_phasor(n,theta).real,2/3-1e-14)

    def test_averaged_kernel_is_monotonic_over_all_integer_headings(self):
        for n in range(1,16):
            for fraction in (0.25,1.0):
                theta=mean.improved_angle(n)*fraction
                W=mean.normalized_tip_phasor(n,theta)
                prev = None
                lower=(4/3)*math.sin(theta/2)*math.cos(n*theta)
                for k in range(-n,n+1):
                    value=(W*complex(math.cos(k*theta),math.sin(k*theta))).imag
                    if prev is not None:
                        self.assertGreaterEqual(value-prev+1e-14,lower)
                    prev=value

    def test_full_symbolic_endpoints_match_sharper_margin(self):
        for n in range(1,7):
            labels=signatures(n)
            a=previous.nested_tip_headings(n)
            for fraction in (0.25,0.75,1.0):
                theta=mean.improved_angle(n)*fraction
                bound=mean.quantitative_cross_lower_bound(n,theta)
                self.assertGreater(bound,0)
                for i,b in enumerate(labels):
                    if i in (0,tip_index(n)):
                        continue
                    actual=previous.cross_from_histograms(a,b,theta)
                    self.assertGreaterEqual(actual+1e-8*max(1,abs(actual)),bound,
                                            (n,i,fraction,actual,bound))

    def test_original_turtle_at_new_upper_endpoint(self):
        for n in range(1,7):
            theta=mean.improved_angle(n)
            drawing=[(0,0)]+[(x2,y2) for _,_,x2,y2 in trace(grammar(n),math.degrees(theta))]
            x,y=drawing[tip_index(n)]
            bound=mean.quantitative_cross_lower_bound(n,theta)
            for index,(px,py) in enumerate(drawing):
                if index not in (0,tip_index(n)):
                    det=x*py-y*px
                    self.assertGreaterEqual(det+1e-8*max(1,abs(det)),bound)

    def test_guaranteed_lower_bound_improves_old_bound(self):
        for n in range(1,300):
            improved=mean.improved_angle(n)
            old=previous.guaranteed_angle(n)
            self.assertGreater(improved,old)
            self.assertAlmostEqual(improved/old,4*n/(2*n+1),places=12)
            self.assertGreater(mean.quantitative_cross_lower_bound(n,improved),0)

    def test_loss_bracket_contains_candidate_zero(self):
        for n in range(2,201):
            lo,hi=mean.first_loss_bracket(n)
            self.assertAlmostEqual(lo,mean.improved_angle(n),places=14)
            self.assertGreater(hi,lo)
            self.assertLess(hi,math.pi/2)
            self.assertGreater(hi,math.pi/(2*n-1))

    def test_asymptotic_bracket_closes_relatively(self):
        for n in (10,20,50,100,1000):
            lower,upper=mean.first_loss_bracket(n)
            self.assertLess(lower/upper,1)
            self.assertGreater(lower/upper,1-2.0/n)
        lower,upper=mean.first_loss_bracket(1000)
        self.assertGreater(lower/upper,.998)
        self.assertLess(abs(1000*lower-math.pi/2),.001)
        self.assertLess(abs(1000*upper-math.pi/2),.002)

    def test_collinearity_upper_obstacle_is_exact_candidate_root(self):
        # The existing exact P_n recurrence supplies the upper obstruction.
        for n in range(2,7):
            c=math.cos(first_candidate_zero(n))
            coeffs=new_corner_polynomial(n)
            p=sum(v*c**i for i,v in enumerate(coeffs))
            self.assertLess(abs(p),1e-7*3**n)

    def test_certificate_and_validation(self):
        report=mean.certificate(6)
        self.assertEqual(report['experiment'],'BMO-011')
        self.assertEqual(len(report['finite_audits']),6)
        self.assertEqual([r['endpoints'] for r in report['finite_audits']],[6,26,126,626,3126,15626])
        for bad in (-1,0,True,1.2):
            with self.assertRaises(ValueError): mean.improved_angle(bad)
            with self.assertRaises(ValueError): mean.normalized_tip_phasor(bad,.1)
            with self.assertRaises(ValueError): mean.first_loss_bracket(bad)
        for bad in (math.nan,math.inf,-1,0):
            with self.assertRaises(ValueError): mean.quantitative_cross_lower_bound(4,bad)
        with self.assertRaises(ValueError): mean.quantitative_cross_lower_bound(4,1)
        with self.assertRaises(ValueError): mean.certificate(7)


if __name__=='__main__':
    unittest.main()
