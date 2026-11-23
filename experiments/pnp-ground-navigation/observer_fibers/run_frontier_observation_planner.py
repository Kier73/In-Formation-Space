"""OFG-003 matched policy experiment (declared costs vs measured local time)."""
from __future__ import annotations

import json
import platform
from statistics import median
from time import perf_counter_ns

from frontier_observation_planner import (Intention, compile_plan, verify_plan,
                                          decode, encode, observe_source_state,
                                          requested_projection)
from separator_fiber_ground import source_accepts


def timed(f):
    start=perf_counter_ns()
    output=f()
    return output,(perf_counter_ns()-start)/1e6


def q1(blocks,cost):
    return Intention(blocks+1,((1,-2),(-1,-3)),tuple(range(2,blocks+2)),((1,cost),))


def q2(blocks,c1,c2):
    clauses=tuple(cl for v in range(3,blocks+3) for cl in ((1,v),(2,-v)))
    return Intention(blocks+2,clauses,tuple(range(3,blocks+3)),((1,c1),(2,c2)))


def run():
    results=[]
    cases=[(f'one-hub-{b}-{mode}',q1(b,0 if mode=='free' else 10**9))
           for b in (8,32,128,256) for mode in ('free','expensive')]
    cases.extend((f'two-hub-{mode}',q2(24,*costs)) for mode,costs in
                 [('free',(0,0)),('mixed',(10**9,0)),('expensive',(10**9,10**9))])
    for label,q in cases:
        plan,compile_ms=timed(lambda:compile_plan(q,max_separator=2,max_bag=4))
        approved,verify_ms=timed(lambda:verify_plan(q,plan))
        assert approved
        # Already-known test state, not a claimed SAT-search or external sensor.
        assignment=(1<<q.n)-1 if label.startswith('two-hub') else 0
        assert source_accepts(__import__('frontier_observation_planner')._source(q,plan['geometry']),assignment)
        outcome=observe_source_state(q,plan,assignment)
        repeats=[]
        for _ in range(7):
            code,enc_ms=timed(lambda:encode(q,plan,assignment,outcome))
            reconstructed,dec_ms=timed(lambda:decode(q,plan,outcome,code))
            assert requested_projection(q,reconstructed)==requested_projection(q,assignment)
            repeats.append((enc_ms,dec_ms))
        selected=plan['selected_policy']
        results.append({'case':label,'n':q.n,'separator':plan['geometry']['separator'],
            'bags':len(plan['geometry']['bags']),
            'candidate_count':plan['geometry']['candidate_count'],
            'local_source_evaluations':plan['ground']['local_states_checked'],
            'source_models':str(plan['ground']['models']),
            'observed_variables':selected['observe'],
            'observation_cost_declared':selected['observation_cost'],
            'costed_navigation_probe_upper':selected['worst_navigation_work_upper'],
            'costed_total_declared':selected['total_declared_cost'],
            'additional_bits_worst':selected['minimum_aux_bits_worst'],
            'cold_compile_with_independent_verification_ms':round(compile_ms,4),
            'independent_plan_reverification_ms':round(verify_ms,4),
            'encode_median_ms':round(median(x[0] for x in repeats),4),
            'decode_median_ms':round(median(x[1] for x in repeats),4),
            'certificate_bytes':len(json.dumps(plan,separators=(',',':')).encode())})
    return {'schema':'ifs.ofg.frontier-observation-benchmark.v3','python':platform.python_version(),
            'host':platform.system(),'pricing':'declared nonphysical integer units per bounded symbolic intersection probe',
            'notes':'Single local run, simulated observation values from supplied source witness. Cold compilation includes search, verified Ground, and policy selection; times not complexity bounds.',
            'rows':results}


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
