"""TCN-007 deterministic reproduction: inverse actuator, controls, refusal, huge time."""
from __future__ import annotations

import json
import statistics
import time

import numpy as np

from cocycle import ExactSchedule
from inverse_ground import (find_weyl_coordinate, synthesize_native_cubic,
                            make_receipt, verify_receipt)
from moving_frame import dense_reference, _matvec


def dense_echo_check(p, pattern, n, incoming, target, control):
    out = {}
    for source in (0, 3, p//3):
        events = [{'kind': 'transfer', 'a': pattern[i % len(pattern)]} for i in range(n)]
        direct = dense_reference(p, source, [{'kind': 'cubic', 'c': incoming}] + events +
                                 [{'kind': 'cubic', 'c': control}])
        requested = dense_reference(p, source, events + [{'kind': 'cubic', 'c': target}])
        out[str(source)] = float(np.max(np.abs(direct - requested)))
    return out


def median_ms(f, reps=7):
    samples = []
    for _ in range(reps):
        start = time.perf_counter_ns()
        f()
        samples.append((time.perf_counter_ns()-start) / 1e6)
    return statistics.median(samples)


def run():
    field = 127
    schedule = ExactSchedule(field, (1, 2))
    free = synthesize_native_cubic(schedule, 7, 0)
    self_test = dense_echo_check(field, schedule.pattern, int(free['coordinate_decimal']),
                                 7, 0, free['countergate_cubic'])
    # One residual target plus a constrained alphabet: exact, not merely echo.
    controlled = synthesize_native_cubic(ExactSchedule(31,(0,)), 7, 5,
                                          allowed_controls=(12,))
    residual_error = dense_echo_check(31,(0,),int(controlled['coordinate_decimal']),
                                      7,5,controlled['countergate_cubic'])
    huge_min = 10**100 + 37
    future_schedule = ExactSchedule(257,(1,2,3))
    future = synthesize_native_cubic(future_schedule, 7, 0, min_step=huge_min)
    receipt = make_receipt({
        'p': 257, 'pattern': [1,2,3], 'incoming_cubic': 7, 'target_cubic': 0,
        'allowed_controls': None, 'min_step_decimal': str(huge_min),
        'max_step_decimal': None, 'max_babies': 10000, 'max_probes': 100000})
    # A general inverse Weyl query tests nonvertical operator goals as well.
    target_operator, _ = schedule.navigate(23)
    nonvertical_vector = _matvec(target_operator.m, (0,1), field)
    inverse_vector = find_weyl_coordinate(schedule, nonvertical_vector, projective=False)
    timer_schedule = ExactSchedule(1009,(1,))
    timer_solution = synthesize_native_cubic(timer_schedule,7,0)
    def timer_forward():
        # Deliberately compare to sequentially scanning the known orbit;
        # discovery must not be confused with direct execution.
        current = ((1,0),(0,1))
        from transfer import _mm
        from cocycle import ExactOperator
        one = ExactOperator.transfer(1009,1).m
        for _ in range(int(timer_solution['coordinate_decimal'])):
            current = _mm(one,current,1009)
            if current[0][1] == 0:
                return
    return {
        'experiment':'TCN-007',
        'algebra':'single odd-prime qudit / declared periodic quadratic Clifford schedule / native cubic actions',
        'echo_nontrivial_schedule': {'plan':free,'dense_short_amplitude_max_error_by_source':self_test},
        'restricted_residual_operation':{'plan':controlled,'dense_short_amplitude_max_error_by_source':residual_error},
        'high_coordinate': {'plan':future,'distance_past_requested_minimum':int(future['coordinate_decimal'])-huge_min,
                            'receipt_sha256':receipt['sha256'],'reconstruction_verified':verify_receipt(receipt),
                            'not_independently_physically_observed':True},
        'inverse_weyl_target': {'wanted_vector':list(nonvertical_vector),'plan':inverse_vector},
        'negative_controls':{
            'prohibited_control':synthesize_native_cubic(ExactSchedule(31,(0,)),7,5,allowed_controls=(5,))['status'],
            'premature_time':synthesize_native_cubic(ExactSchedule(31,(0,)),7,0,min_step=1,max_step=1)['status'],
            'insufficient_memory_budget':synthesize_native_cubic(future_schedule,7,0,max_babies=1)['status'],
            'unreachable_axis':find_weyl_coordinate(ExactSchedule(31,(0,)),(1,1))['status']},
        'local_timing_illustration':{'p':1009, 'single_chirp_1_earliest_n':timer_solution['coordinate_decimal'],
                'inverse_median_ms':median_ms(lambda:synthesize_native_cubic(timer_schedule,7,0)),
                'sequential_median_ms':median_ms(timer_forward),
                'caveat':'one Python process, 7 medians, no generalized speedup or physical event timing claim'},
        'search_accounting':'factor finite orbit order + baby-step/giant-step on vector; candidate controls and schedule remainders charged; O(log n) is evaluation only',
        'model_scope':'exact only for declared algebra, not an observed outside process or proof of RH',
    }


if __name__ == '__main__':
    print(json.dumps(run(),sort_keys=True,indent=2))
