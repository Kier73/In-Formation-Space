"""TCN-007: independent brute-force witnesses, dense FFT, adversarial admission."""
import copy
import json
import random
import unittest

import numpy as np

from cocycle import ExactOperator, ExactSchedule
from moving_frame import _matvec, dense_reference
from inverse_ground import (find_weyl_coordinate, synthesize_native_cubic,
                            make_receipt, verify_receipt)


def brute_axis(schedule, target, projective, minimum, maximum):
    p = schedule.p
    key = (lambda v: (v[0] * pow(v[1], -1, p) % p, 1)
           if v[0] == 0 and v[1] else v)
    # For arbitrary targets use a canonical axis without assuming second entry.
    from moving_frame import canonical_axis
    for n in range(minimum, maximum + 1):
        m, _ = schedule.navigate(n)
        v = _matvec(m.m, (0, 1), p)
        if ((canonical_axis(v, p)[0] == canonical_axis(target, p)[0])
            if projective else v == target):
            return n
    return None


def brute_cubic(schedule, incoming, target, controls, minimum, maximum):
    p = schedule.p
    for n in range(minimum, maximum + 1):
        op, _ = schedule.navigate(n)
        v = _matvec(op.m, (0, 1), p)
        if incoming % p == 0:
            g = target % p
        elif v[0] == 0:
            g = (target - incoming * pow(v[1], 3, p)) % p
        else:
            continue
        if controls is None or g in controls:
            return n, g
    return None


def make_spec(p=31, pattern=(0,), c=7, target=5, controls=(12,), minimum=1):
    return dict(p=p, pattern=list(pattern), incoming_cubic=c, target_cubic=target,
                allowed_controls=list(controls) if controls is not None else None,
                min_step_decimal=str(minimum), max_step_decimal=None,
                max_babies=10000, max_probes=100000)


class InverseTests(unittest.TestCase):
    def test_native_echo_and_nonzero_goal_dense(self):
        p, c, target = 31, 7, 5
        schedule = ExactSchedule(p, (0,))
        for allowed, expected in ((None, (2, 12)), ((12,), (2, 12)), ((29,), (4, 29))):
            # For F^4=I, g=target-c=29.
            result = synthesize_native_cubic(schedule, c, target, allowed_controls=allowed)
            self.assertEqual(result['status'], 'found')
            n = int(result['coordinate_decimal'])
            gate = result['countergate_cubic']
            self.assertEqual((n, gate), expected)
            for source in (0, 3, 17):
                left = dense_reference(p, source,
                    [{'kind':'cubic','c':c}]+[{'kind':'transfer','a':0}]*n+
                    [{'kind':'cubic','c':gate}])
                right = dense_reference(p, source,
                    [{'kind':'transfer','a':0}]*n+[{'kind':'cubic','c':target}])
                self.assertLess(np.max(np.abs(left-right)), 2e-13)

    def test_restricted_action_refusal_is_exact_not_budget(self):
        schedule = ExactSchedule(31, (0,))
        self.assertEqual(synthesize_native_cubic(schedule, 7, 5, allowed_controls=(5,))['status'], 'unreachable')
        self.assertEqual(synthesize_native_cubic(schedule, 7, 5, allowed_controls=(12,), max_step=1)['status'], 'outside_window')
        self.assertEqual(synthesize_native_cubic(schedule, 7, 5, allowed_controls=(12,), max_babies=1)['status'], 'refused_budget')
        self.assertEqual(synthesize_native_cubic(schedule, 7, 5, allowed_controls=(12,), max_probes=1)['status'], 'refused_budget')

    def test_noncommuting_single_step_never_falsely_admitted(self):
        s = ExactSchedule(31, (0,))
        result = synthesize_native_cubic(s, 7, 0, min_step=1, max_step=1)
        self.assertEqual(result['status'], 'outside_window')
        self.assertEqual(find_weyl_coordinate(s, (1, 0), projective=False,
                     min_step=0, max_step=0)['status'], 'outside_window')

    def test_genuine_unreachable_weyl_target(self):
        s = ExactSchedule(31, (0,))
        for projective in (True, False):
            self.assertEqual(find_weyl_coordinate(s, (1, 1), projective=projective)['status'], 'unreachable')

    def test_general_axis_inverse_against_exhaustive_orbit(self):
        for p, pattern in ((31, (1, 2)), (31, (1, 2, 3)), (127, (1,)), (257, (2, 4, 1, 3))):
            schedule = ExactSchedule(p, pattern)
            for n in (0, 1, 2, 7, 23, 47):
                op, _ = schedule.navigate(n)
                target = _matvec(op.m, (0, 1), p)
                for projective in (True, False):
                    result = find_weyl_coordinate(schedule, target, projective=projective)
                    self.assertEqual(result['status'], 'found')
                    coordinate = int(result['coordinate_decimal'])
                    self.assertEqual(coordinate, brute_axis(schedule, target, projective, 0, n))
                    self.assertLessEqual(coordinate, n)

    def test_cubic_target_restriction_against_full_brute_period(self):
        for p, pattern in ((31, (1,)), (31, (1, 2)), (31, (1, 2, 3)), (127, (1, 2))):
            schedule = ExactSchedule(p, pattern)
            for incoming, target, allowed in ((7, 0, None), (7, 5, (12,)), (7, 5, (6, 12, 17)), (3, 0, (3, 28))):
                result = synthesize_native_cubic(schedule, incoming, target, allowed_controls=allowed)
                bound = len(pattern) * schedule.full_period_bound()  # redundant upper bound, deliberately finite
                # actual period <= full_period_bound; use at most 2600 steps.
                expected = brute_cubic(schedule,incoming,target,allowed,1,min(bound,2600))
                if expected is None:
                    self.assertEqual(result['status'], 'unreachable', (p,pattern,incoming,target,allowed))
                else:
                    self.assertEqual(result['status'], 'found')
                    self.assertEqual((int(result['coordinate_decimal']),result['countergate_cubic']), expected)

    def test_high_coordinate_uses_period_arithmetic_not_iteration(self):
        s = ExactSchedule(257, (1, 2, 3))
        minimum = 10**100 + 37
        outcome = synthesize_native_cubic(s, 7, 0, min_step=minimum)
        self.assertEqual(outcome['status'],'found')
        n = int(outcome['coordinate_decimal'])
        self.assertGreaterEqual(n, minimum)
        self.assertLess(n-minimum, outcome['period'])
        self.assertLess(outcome['giant_step_probes'],100)
        op, _ = s.navigate(n)
        d = op.m[1][1]
        self.assertEqual(op.m[0][1],0)
        self.assertEqual((7*pow(d,3,257)+outcome['countergate_cubic'])%257,0)
        self.assertEqual(outcome['global_quadrant_mod4'],op.quadrant)
        self.assertLess(outcome['operator_products_at_coordinate'],1000)

    def test_fixed_action_high_coordinate_and_scalar_period(self):
        s=ExactSchedule(31,(0,))
        minimum=10**100+1
        r=synthesize_native_cubic(s,7,5,allowed_controls=(12,),min_step=minimum)
        self.assertEqual(r['status'],'found')
        self.assertEqual(int(r['coordinate_decimal'])%4,2)
        self.assertEqual(r['period'],4)
        self.assertEqual(r['countergate_cubic'],12)
        self.assertEqual(r['orbit_kind'],'exact_weyl_vector')
        free=synthesize_native_cubic(s,7,5,min_step=minimum)
        self.assertEqual(free['orbit_kind'],'projective_axis')
        self.assertEqual(free['period'],2)

    def test_trivial_prior_gate_not_treated_as_orbit_restriction(self):
        s=ExactSchedule(31,(1,))
        r=synthesize_native_cubic(s,0,9,allowed_controls=(9,),min_step=43)
        self.assertEqual(r['coordinate_decimal'],'43')
        self.assertEqual(r['countergate_cubic'],9)
        self.assertEqual(synthesize_native_cubic(s,0,9,allowed_controls=(5,))['status'],'unreachable')

    def test_weyl_targets_bad_inputs(self):
        s=ExactSchedule(31,(0,))
        for target in ((0,0),(1,),('a',1),[1.0,0]):
            with self.assertRaises(ValueError):
                find_weyl_coordinate(s,target)
        with self.assertRaises(ValueError):
            find_weyl_coordinate(s,(0,1),min_step=True)
        with self.assertRaises(ValueError):
            synthesize_native_cubic(s,7,0,allowed_controls=())
        with self.assertRaises(ValueError):
            synthesize_native_cubic(s,7,0,allowed_controls=[1.2])
        with self.assertRaises(ValueError):
            synthesize_native_cubic(s,7,0,max_step=0,min_step=1)
        with self.assertRaises(ValueError):
            synthesize_native_cubic(s,7,0,max_probes=0)

    def test_canonical_receipt_and_tamper(self):
        spec=make_spec(minimum=10**100+1)
        record=make_receipt(spec)
        self.assertTrue(verify_receipt(record))
        self.assertEqual(record['plan']['status'],'found')
        for bad_field in ('sha256','plan','spec'):
            tampered=copy.deepcopy(record)
            if bad_field=='sha256': tampered['sha256']='0'*64
            if bad_field=='plan': tampered['plan']['countergate_cubic']=0
            if bad_field=='spec': tampered['spec']['allowed_controls']=[2]
            self.assertFalse(verify_receipt(tampered))
        malformed=copy.deepcopy(record)
        malformed['spec']['min_step_decimal']='001'
        self.assertFalse(verify_receipt(malformed))
        self.assertFalse(verify_receipt({'schema':'ifs.inverse-native-cubic-ground.v1'}))
        self.assertFalse(record['authenticated_observation'])

    def test_full_operator_global_phase_is_bound_to_selected_time(self):
        for p, pattern in ((31, (0,)),(31,(1,2,3)),(127,(1,))):
            s=ExactSchedule(p,pattern)
            plan=synthesize_native_cubic(s,9,0)
            self.assertEqual(plan['status'],'found')
            op,_=s.navigate(int(plan['coordinate_decimal']))
            self.assertEqual(plan['operator_matrix'],[list(row) for row in op.m])
            self.assertEqual(plan['global_quadrant_mod4'],op.quadrant)


    def test_deterministic_cross_family_orbit_property(self):
        """Brute force is a separate reference, including exact control scope."""
        rng = random.Random(54)
        checked = 0
        from moving_frame import canonical_axis
        for p in (3, 5, 7, 11, 13, 17, 31):
            for _ in range(18):
                pattern = tuple(rng.randrange(p) for _ in range(rng.randint(1, 5)))
                schedule = ExactSchedule(p, pattern)
                horizon = schedule.full_period_bound()
                axis_trace = [_matvec(schedule.navigate(n)[0].m, (0, 1), p)
                              for n in range(horizon + 1)]
                targets = [(rng.randrange(p), rng.randrange(p)) for _ in range(2)]
                for target in targets:
                    if target == (0, 0):
                        continue
                    for projective in (True, False):
                        expected = next((n for n, axis in enumerate(axis_trace)
                            if (canonical_axis(axis, p)[0] == canonical_axis(target, p)[0]
                                if projective else axis == target)), None)
                        result = find_weyl_coordinate(schedule, target, projective=projective)
                        actual = (int(result['coordinate_decimal'])
                                  if result['status'] == 'found' else None)
                        self.assertEqual(actual, expected, (p, pattern, target, projective))
                        checked += 1
                incoming, target = rng.randrange(1, p), rng.randrange(p)
                alphabet = None if rng.randrange(2) else tuple(
                    rng.sample(range(p), rng.randrange(1, p+1)))
                expected = None
                for n, axis in enumerate(axis_trace[1:], 1):
                    if axis[0] != 0:
                        continue
                    gate = (target - incoming * pow(axis[1], 3, p)) % p
                    if alphabet is None or gate in alphabet:
                        expected = n, gate
                        break
                outcome = synthesize_native_cubic(schedule, incoming, target,
                                                   allowed_controls=alphabet)
                actual = ((int(outcome['coordinate_decimal']), outcome['countergate_cubic'])
                          if outcome['status'] == 'found' else None)
                self.assertEqual(actual, expected, (p, pattern, incoming, target, alphabet))
                checked += 1
        self.assertEqual(checked, 620)


if __name__=='__main__':
    unittest.main()
