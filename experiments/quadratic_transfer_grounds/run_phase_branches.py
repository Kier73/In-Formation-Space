"""TCN-004 reproducible comparison of procedural, frame-search and dense routes."""
import hashlib
import json
import math
from statistics import median
from time import perf_counter_ns
import sys

import numpy as np
from branch import (StructuredState, SparseGround, dense_quadratic_reference,
                    gate_phases, fit_frame)
from cocycle import ExactSchedule


def timed(f, repeat=7):
    outputs=[]
    measurements=[]
    for _ in range(repeat):
        start=perf_counter_ns()
        value=f()
        measurements.append(perf_counter_ns()-start)
        outputs.append(value)
    return outputs[-1],median(measurements)/1e6


def run():
    result={'schema':'ifs.tcn004-experiment.v1',
            'numpy_version':np.__version__,
            'premises':'declared finite-field quadratic schedules and synthetic diagonal gates',
            'external_observation':False,
            'models':{}}
    for p in (31,127,257):
        init=StructuredState.flat(p,7,13)
        pattern=(2,7,9)
        # moderate block for independent dense FFT; very long extension checks
        # exact group period reduction instead of pretending 10**100 FFTs run.
        after,products=init.after_schedule(pattern,37)
        dense_ref=dense_quadratic_reference(p,pattern,37,init.dense())
        err1=float(np.linalg.norm(after.dense()-dense_ref))
        scope={}
        for strength in (0.2,0.7,1.2):
            op,ms=timed(lambda:after.after_harmonic(strength,taylor_order=14,
                                                    max_terms=7,absolute_error_budget=.15))
            state,receipt=op
            true=gate_phases(p,'harmonic',strength)*dense_ref
            general,gms=timed(lambda:fit_frame(true,p=p,max_terms=7,
                                                  max_relative_omission=.15))
            scope[f'harmonic_{strength}']={
                'accepted':state is not None, 'rank':len(state.terms) if state else None,
                'ideal_l2_bound':receipt['cumulative_error_bound_ideal'],
                'actual_l2_error':float(np.linalg.norm(state.dense()-true)) if state else None,
                'full_search_selected_rank':general.rank,
                'full_search_omitted_l2':general.omitted_l2,
                'full_search_candidate_frames':general.candidates,
                'taylor_modes_constructed':receipt['generated_taylor_modes'],
                'median_procedural_ms':ms,'median_full_scan_ms':gms}
        cubic,cm=timed(lambda:SparseGround.quadratic(p,7,13).after_gate(
            'cubic',5,max_terms=8,max_omission=.1))
        _,c_receipt=cubic
        period=ExactSchedule(p,pattern).full_period_bound()
        big=10**100+1234567
        long,prod_long=init.after_schedule(pattern,big)
        reduced,_=init.after_schedule(pattern,big%period)
        scope['cubic']={'status':c_receipt['status'],
                        'rank_required_for_10pct_l2':c_receipt['minimum_rank_over_scanned_frames'],
                        'omitted_l2_at_8_terms':c_receipt['omitted_l2'],
                        'median_global_frame_search_ms':cm}
        result['models'][str(p)]={'direct_vs_phase_branch_l2':err1,
                   'moderate_steps':37,'operator_products':products,
                   'long_step_decimal_digits':len(str(big)),
                   'long_step_exact_schedule_products':prod_long,
                   'long_equals_reduced_projective_vector_max_abs':float(
                       np.max(abs(long.dense()-reduced.dense()))),
                   'period':period,'gate_cases':scope}
    # p-independent procedural branch complexity assertion includes p=1009.
    p=1009
    st=StructuredState.flat(p,7,13)
    comp,proof=st.after_harmonic(.7,taylor_order=12,max_terms=7,
                                  absolute_error_budget=.01)
    truth=gate_phases(p,'harmonic',.7)*st.dense()
    result['large_field_procedural']={'p':p,
        'generated_taylor_modes':proof['generated_taylor_modes'],
        'retained_terms':len(comp.terms) if comp else None,
        'observed_l2_error':float(np.linalg.norm(comp.dense()-truth)) if comp else None,
        'ideal_l2_bound':proof['cumulative_error_bound_ideal'],
        'scope':'no curvature scan; full p-vector used for independent test only'}
    raw=json.dumps(result,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
    result['sha256']=hashlib.sha256(raw).hexdigest()
    return result


if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True,allow_nan=False))
