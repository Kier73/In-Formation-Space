"""Independent finite checks of BMO-009's all-depth integer cone proof."""
from fractions import Fraction
import math
import unittest

import tip_exposure as t
from all_depth_law import endpoint_pair, first_candidate_zero
from canopy import grammar, trace
from angle_transitions import endpoint_polynomials, oriented_cross, evaluate
from depth6_phase import signatures as prior_signatures


class TipExposureTests(unittest.TestCase):
    def test_five_copy_moment_maps_against_independent_word_turtle(self):
        for depth in range(8):
            with self.subTest(depth=depth):
                word_points = t.literal_turtle_moments(depth)
                affine_points = t.moment_frontier(depth)
                self.assertEqual(len(word_points), 5**depth + 1)
                self.assertEqual(set(word_points), set(affine_points))

    def test_all_five_slack_transform_identities(self):
        for depth in range(1, 6):
            trunk = 3**depth
            for moment in t.moment_frontier(depth):
                old_t, _ = moment
                if old_t == 0:
                    self.assertEqual(moment, (0, 0))
                    continue
                slack = t.cone_slack(moment)
                expected = [slack, slack + trunk + 2*old_t, slack + trunk,
                            slack + 2*(trunk-old_t), slack + 2*trunk]
                observed = [t.cone_slack(t.affine_moment(moment, trunk, i))
                            for i in range(5)]
                self.assertEqual(observed, expected)

    def test_zero_slack_characterization_and_sharp_gap(self):
        for depth in range(1, 9):
            with self.subTest(depth=depth):
                report = t.verify_finite_moment_invariant(depth)
                self.assertEqual(report['tip_T_K'], list(t.tip_moments(depth)))
                self.assertEqual(report['unique_full_depth_tip_index'], t.tip_index(depth))
                self.assertEqual(report['min_first_order_support_gap'], 3**(depth-1))
                self.assertEqual(report['zero_slack_path_lengths'],
                                 [3**j for j in range(depth+1)])

    def test_nested_tip_exact_index_and_heading_counts(self):
        for depth in range(1, 7):
            with self.subTest(depth=depth):
                labels = prior_signatures(depth)
                at = t.tip_index(depth)
                self.assertEqual(at, endpoint_pair(depth)[0])
                signature = labels[at]
                direct = (sum(count for _, count in signature),
                          -sum(heading*count for heading, count in signature))
                self.assertEqual(direct, t.tip_moments(depth))
                self.assertEqual(t.literal_turtle_moments(depth)[at], direct)

    def test_cross_product_derivative_against_exact_polynomials(self):
        for depth in range(1, 7):
            labels = prior_signatures(depth)
            selected = [0, 1, t.tip_index(depth), 5**depth]
            if depth >= 2:
                selected += [t.tip_index(depth-1), t.tip_index(depth)+1]
            points = {i:endpoint_polynomials(labels[i]) for i in set(selected)}
            origin = points[0]
            tip = points[t.tip_index(depth)]
            from_word = t.literal_turtle_moments(depth)
            for i in selected:
                derivative = evaluate(oriented_cross(origin, tip, points[i]), Fraction(1))
                self.assertEqual(derivative, t.support_gap(from_word[i], depth))

    def test_numerical_turtle_strictly_on_supported_side_in_proven_interval(self):
        # Independent falsification probes, not the all-depth proof.
        for depth in range(1, 7):
            theta = math.sqrt(t.small_angle_squared_bound(depth)) * 0.99
            segments = trace(grammar(depth), math.degrees(theta))
            points = [(0., 0.)] + [(x2, y2) for _, _, x2, y2 in segments]
            ax, ay = points[t.tip_index(depth)]
            lower = 3**depth * theta/16
            for index, (x, y) in enumerate(points):
                if index in (0, t.tip_index(depth)):
                    continue
                self.assertGreaterEqual(ax*y - ay*x, lower*(1-1e-6),
                                        (depth,index,x,y))

    def test_bound_is_not_claim_at_candidate_transition(self):
        for depth in range(2, 7):
            self.assertLess(math.sqrt(t.small_angle_squared_bound(depth)),
                            first_candidate_zero(depth))
        self.assertEqual(t.certificate(3)['finite_audits'][2]['depth'], 3)

    def test_closed_form_at_large_depth_without_building_tree(self):
        for depth in (1,2,6,15,100,1000):
            s, k = t.tip_moments(depth)
            self.assertEqual(s, 3**depth)
            self.assertEqual(2*k, s-1)
            self.assertEqual(t.cone_slack((s,k)), 0)
            self.assertEqual(t.tip_index(depth),
                             5*t.tip_index(depth-1)-1 if depth>1 else 4)
            self.assertEqual(t.small_angle_squared_bound(depth),
                             Fraction(1,4*depth**3*s))

    def test_invalid_inputs(self):
        for bad in (0, -1, True, 2.5):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): t.tip_index(bad)
                with self.assertRaises(ValueError): t.tip_moments(bad)
                with self.assertRaises(ValueError): t.small_angle_squared_bound(bad)
        for bad in (-1, 21, True, 3.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                t.moment_frontier(bad)
        for bad in (-1, 8, True, 2.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                t.literal_turtle_moments(bad)
        for bad in (0, 21, True, 1.2):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                t.certificate(bad)
        with self.assertRaises(ValueError): t.affine_moment((1,0),0,0)
        with self.assertRaises(ValueError): t.affine_moment((1,0),1,5)
        with self.assertRaises(ValueError): t.affine_moment((2,0),1,0)


if __name__ == '__main__':
    unittest.main()
