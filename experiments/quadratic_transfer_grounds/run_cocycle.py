"""TCN-003 deterministic exact-Gauss-cocycle evidence and illustrative timings."""
import hashlib
import json
import math
import platform
import sys
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
from cocycle import ExactSchedule, verify_receipt


def _measure(action,n=3):
    result=None
    times=[]
    for _ in range(n):
        start=perf_counter_ns()
        result=action()
        times.append((perf_counter_ns()-start)/1e6)
    return result,median(times)


def _direct(p,pattern,n,state):
    x=np.arange(p,dtype=np.int64)
    v=np.array(state,dtype=complex)
    for i in range(n):
        v=np.fft.ifft(v)*np.sqrt(p)
        v*=np.exp(2j*np.pi*((pattern[i%len(pattern)]*x*x)%p)/p)
    return v


def run():
    p=101
    s=ExactSchedule(p,(7,13,29))
    huge=10**100+123
    op,products=s.navigate(huge)
    first=s.find_exact_operator_coordinate(op)
    half=s.navigate(first+153)[0]
    period=s.full_period_bound()
    src,dest=33,3
    phase=op.basis_amplitude(src,dest)
    receipt=s.receipt(huge,src,dest)
    assert verify_receipt(receipt)
    assert op==s.navigate(first)[0]
    assert op.m==half.m and op!=half

    p2,pattern,n=127,(7,13,29),4096
    rng=np.random.default_rng(2026)
    initial=rng.normal(size=p2)+1j*rng.normal(size=p2)
    initial=initial/np.linalg.norm(initial)
    s2=ExactSchedule(p2,pattern)
    direct,t_direct=_measure(lambda:_direct(p2,pattern,n,initial))
    (op2,product_count),t_model=_measure(lambda:s2.navigate(n))
    query,t_query=_measure(lambda:op2.apply_coordinate(initial,34))
    all_values,t_full=_measure(lambda:op2.apply_full(initial))
    max_error=float(np.max(np.abs(all_values-direct)))
    query_error=float(abs(query-direct[34]))
    assert max_error<1e-10 and query_error<1e-10

    x=np.arange(31)
    cubic=np.exp(2j*np.pi*((x**3)%31)/31)/np.sqrt(31)
    s3=ExactSchedule(31,(2,5,7))
    op3,_=s3.navigate(77)
    check=_direct(31,s3.pattern,77,cubic)
    cubic_error=float(np.max(np.abs(op3.apply_full(cubic)-check)))

    path=Path(__file__).resolve().parent
    return {'experiment':'TCN-003',
            'source_sha256':{name:hashlib.sha256((path/name).read_bytes()).hexdigest()
                             for name in ('cocycle.py','run_cocycle.py')},
            'environment':{'python':sys.version.split()[0], 'numpy':np.__version__,
                           'platform':platform.platform()},
            'exact_long_jump':{'p':p,'pattern':list(s.pattern),'index_digits':len(str(huge)),
                               'matrix_products':products,
                               'exact_operator':op.signature(),
                               'basis_amplitude':phase.description(),
                               'receipt_sha256':receipt['sha256'],
                               'recomputation_verified':verify_receipt(receipt),
                               'earliest_full_operator_step':first,
                               'full_operator_period_bound':period,
                               'half_period_same_symplectic':op.m==half.m,
                               'half_period_different_scalar':op.quadrant!=half.quadrant},
            'arbitrary_complex_input':{'p':p2,'n':n,'vector_entries_supplied':p2,
                                       'modular_products':product_count,
                                       'query_coordinate':34,'absolute_query_error':query_error,
                                       'max_full_output_absolute_error':max_error,
                                       'direct_fft_median_ms':float(t_direct),
                                       'operator_construction_median_ms':float(t_model),
                                       'one_coordinate_median_ms':float(t_query),
                                       'full_p_coordinates_median_ms':float(t_full),
                                       'benchmark_scope':'single host, three repetitions; excludes discovery and source acquisition'},
            'nonquadratic_input':{'source':'cubic phase over F_31 as full 31-value input',
                                  'steps':77,'full_output_max_absolute_error':cubic_error,
                                  'input_compressed':False},
            'meaning':'Exact symbolic kernel and central Gauss phase for declared periodic quadratic operators; arbitrary input vectors still require O(p) data per coordinate and O(p^2) for full output; no external witnesses.'}


if __name__=='__main__':
    print(json.dumps(run(),sort_keys=True,indent=2))
