"""TCN-002 reproducible, qualified projective-operator navigation experiment."""
import hashlib
import json
import platform
import sys
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np

from bridge import InitialPhaseWitness
from transfer import (Ground, direct_transfer, fidelity, diagnose_quadratic_ray,
                      quadratic_frame_audit, verify_receipt)


def _timed(fn, repeats=3):
    observations=[]
    result=None
    for _ in range(repeats):
        start=perf_counter_ns()
        result=fn()
        observations.append((perf_counter_ns()-start)/1e6)
    return result, float(median(observations))


def run():
    p, pattern, source = 101, (7,13,29), 33
    ground=Ground(p,pattern)
    huge=10**100+123
    receipt=ground.receipt(huge,source)
    alias=ground.find_operator_coordinate(receipt['matrix'])
    ray,m,count=ground.navigate(huge,source)
    short=ground.navigate(alias,source)[0]
    assert ray==short and verify_receipt(receipt)

    small_p, steps=127,4096
    small=Ground(small_p,(7,13,29))
    dense,dense_ms=_timed(lambda:direct_transfer(small_p,small.pattern,steps,12))
    compact,compact_ms=_timed(lambda:small.navigate(steps,12))
    comp_ray,comp_matrix,comp_products=compact
    score=fidelity(comp_ray,dense)
    assert score>1-1e-9

    x=np.arange(31,dtype=np.int64)
    quadratic=np.exp(2j*np.pi*((7*x*x+11*x+4)%31)/31)/np.sqrt(31)
    cubic=np.exp(2j*np.pi*(x**3%31)/31)/np.sqrt(31)
    rng=np.random.default_rng(2026)
    random_phases=np.exp(2j*np.pi*rng.random(31))/np.sqrt(31)
    frames={name:quadratic_frame_audit(wave,31) for name,wave in
            [('quadratic',quadratic),('cubic',cubic),('random',random_phases)]}
    classifier={name:diagnose_quadratic_ray(wave,31) for name,wave in
                [('quadratic',quadratic),('cubic',cubic),('random',random_phases)]}

    # Deliberately unobserved change in transfer schedule, a negative control.
    incorrect=Ground(p,(5,11)).navigate(12,3)[0]
    actual=direct_transfer(p,(5,11,17),12,3)
    bad_fidelity=fidelity(incorrect,actual)

    root=Path(__file__).resolve().parent
    result={
        'experiment':'TCN-002',
        'framework':'finite odd-prime projective Clifford/metaplectic, declared schedule',
        'environment':{'python':sys.version.split()[0], 'numpy':np.__version__,
                       'platform':platform.platform(),
                       'OPENBLAS_NUM_THREADS':'user environment controlled'},
        'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                         for name in ('transfer.py','bridge.py','run_experiment.py')},
        'huge_operator':{'steps_digits':len(str(huge)),'matrix':receipt['matrix'],
                         'matrix_products':count,'period_bound':ground.operator_period_bound(),
                         'earliest_equal_operator_step':alias,'relative_state':ray.description(),
                         'same_projective_state_as_earliest':ray==short,
                         'receipt_sha256':receipt['sha256'],
                         'recomputation_verified':verify_receipt(receipt)},
        'direct_fft_comparison':{'prime':small_p,'steps':steps,
                                 'fidelity_up_to_global_phase':score,
                                 'modular_matrix_products':comp_products,
                                 'direct_fft_median_ms':dense_ms,
                                 'compact_median_ms':compact_ms,
                                 'timing_scope':'single host, three repeats, illustrative only; excludes discovery'},
        'quadratic_frame_audit':frames,
        'complete_vector_shape_diagnostic':classifier,
        'unobserved_schedule_change':{'fidelity_to_wrong_declared_schedule':bad_fidelity,
                                      'internal_receipt_does_not_validate_external_schedule':True},
        'optimization_no_go':{'prime':p,'flat_marked_set_size':6,
                              'marked_set_mass_exact':'6/101',
                              'scope':'basis input, quadratic chirps/Fourier only; no arbitrary objective amplification'},
        'cost_scope':{'forward':'O(L+log n) modular 2x2 products, then O(1) for one coordinate',
                      'inverse_operator':'O(L*sqrt(operator order)) group products plus order factoring',
                      'quadratic_frame_scan':'p FFTs of length p, O(p^2 log p)',
                      'dense_baseline':'O(n*p*log p) floating FFT operations',
                      'physical_provenance':'none; conditional mathematics, not a deployed fabric observation'},
    }
    return result


if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
