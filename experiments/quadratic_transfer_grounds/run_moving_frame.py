"""Deterministic TCN-006 report: phase echoes, refusal, and independent FFT."""
from __future__ import annotations

import json
import time
import numpy as np

from cocycle import ExactOperator, ExactSchedule
from moving_frame import (MovingFrameGround, cubic_echo_strength,
                          dense_reference, first_native_cubic_echo)
from receipt import make_receipt, verify_receipt


def run():
    out={'experiment':'TCN-006','question':'Can nonquadratic phase generators cancel after a large Clifford transport?',
         'premise':'declared operators; phase-frame closure; independent numerical short reference',
         'echo':{},'noncommuting':{},'search':{},'receipts':{}}
    long_n=10**100+2
    for p in (31,127,257):
        source=11
        t0=time.perf_counter()
        op,products=ExactSchedule(p,(0,)).navigate(long_n)
        counter=cubic_echo_strength(op,7)
        g=MovingFrameGround.start(p,source).after_cubic(7).after_clifford(op,products).after_cubic(counter)
        build_us=(time.perf_counter()-t0)*1e6
        direct=dense_reference(p,source,[{'kind':'cubic','c':7},
                {'kind':'transfer','a':0},{'kind':'transfer','a':0},
                {'kind':'cubic','c':counter}])
        short=MovingFrameGround.start(p,source).after_cubic(7).after_schedule((0,),2).after_cubic(counter)
        short_error=max(abs(short.amplitude(y)-direct[y]) for y in range(p))
        out['echo'][str(p)]={'huge_index_decimal_digits':len(str(long_n)),
                 'symbolic_operator_products':products,'total_recorded_products':g.clifford_products,
                 'countergate_coefficient':counter, 'remaining_nonlinear_blocks':len(g.blocks),
                 'estimated_single_query_work':g.estimated_work(),
                 'max_abs_error_short_echo_vs_independent_FFT':short_error,
                 'huge_operator_equals_short_operator':g.core==short.core,
                 'local_build_microseconds':build_us,
                 'scope':'long jump checked algebraically against short equivalent, not physically replayed'}
    p=31
    op=ExactOperator.transfer(p,0)
    g=MovingFrameGround.start(p,5).after_cubic(7).after_clifford(op).after_cubic(7)
    refused=g.admission((3,),max_work=100)
    ref=dense_reference(p,5,[{'kind':'cubic','c':7},{'kind':'transfer','a':0},{'kind':'cubic','c':7}])
    expanded=[g.amplitude(y,max_work=100000) for y in range(p)]
    out['noncommuting']={'blocks':len(g.blocks), 'all_commute':g.all_commute,
                         'cost_budget_100':refused, 'max_abs_error_with_explicit_full_budget':
                         max(abs(z-t) for z,t in zip(expanded,ref))}
    out['search']={'p':31,'pattern':[0], 'first_echo':first_native_cubic_echo(ExactSchedule(31,(0,)),7,max_steps=10),
                   'single_step_budget':first_native_cubic_echo(ExactSchedule(31,(0,)),7,max_steps=1)}
    small={'p':31,'source':11,'events':[{'kind':'cubic','coefficient':7},
           {'kind':'schedule','pattern':[0],'steps_decimal':'2'},
           {'kind':'cubic','coefficient':7}], 'coordinates':[0,20,21], 'max_work':3}
    large={'p':31,'source':11,'events':[{'kind':'cubic','coefficient':7},
           {'kind':'schedule','pattern':[0],'steps_decimal':str(long_n)},
           {'kind':'cubic','coefficient':7}], 'coordinates':[20], 'max_work':1}
    r1,r2=make_receipt(small),make_receipt(large)
    out['receipts']={'short_verified':verify_receipt(r1),'long_math_replay_verified':verify_receipt(r2),
                     'short_sha256':r1['sha256'],'long_sha256':r2['sha256'],
                     'short_independent_dense_error':r1['independent_short_dense_max_error'],
                     'long_dense_check':'not performed at huge coordinate'}
    return out

if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
