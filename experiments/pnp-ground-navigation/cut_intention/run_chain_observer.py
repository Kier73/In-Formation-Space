"""CIG-004 reproducible bounded source-CNF, temporal-observer and full-cost run.

Run in complete checkout from cut_intention/ with shared prior CIG sources:
    python run_chain_observer.py > CIG-004-results.json
"""
from __future__ import annotations
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import json,platform,sys
from chain_observer_ground import (make_chain_source,compile_ground,_operator,_eval,
                                   _navigate,GroundRefusal)
from verify_chain_observer import verify,Reject


def run():
    records=[]
    for depth in range(2,9):
        source,cut=make_chain_source(depth=depth)
        clock=[];receiver=[];last=None
        for _ in range(3):
            t=perf_counter_ns()
            cert,_=compile_ground(source,cut,steps=10**100+173)
            clock.append(perf_counter_ns()-t)
            t=perf_counter_ns()
            assert verify(source,cert)
            receiver.append(perf_counter_ns()-t)
            last=cert
        n=len(last['active_labels']);L=last['features'];future=last['future_alignment']
        timing=[]
        rows=_operator(last['gates'],n)
        # Diagnostic small original-state trajectory; charged separately.
        state=3
        for t in range(depth+2):
            timing.append((state>>last['observer'])&1)
            state=sum(_eval(poly,state)<<j for j,poly in enumerate(rows))
        records.append({
            'depth':depth,'original_endpoint_variables':source['base']['n'],
            'original_source_clauses':len(source['base']['clauses'])+len(source['coupling']),
            'active_source_variables':n,'source_active_cube':str(1<<n),
            'full_source_count':last['source_result']['count'],
            'source_gates':len(last['gates']),
            'nonlinear_gate_proofs':len(last['gates']),
            'raw_observer_feature_dimension':L['dimension'],
            'minimality_krylov_orbit_source_replayed':True,
            'future_aligned_dimension':future['dimension'],
            'stabilization_time':future['stabilization_steps'],
            'future_anf_monomials':future['anf_masks'],
            'finite_observer_trace':timing,
            'logical_time':last['navigation']['steps'],
            'matrix_products':last['navigation']['matrix_products'],
            'output_at_large_time':last['navigation']['observed'],
            'future_aligned_output':future['observed'],
            'construct_ms_median':round(median(clock)/1e6,4),
            'source_replay_verify_ms_median':round(median(receiver)/1e6,4),
            'total_compiler_and_receiver_ms_median':round((median(clock)+median(receiver))/1e6,4),
            'certificate_bytes':len(json.dumps(last,separators=(',',':')).encode()),
            'certified_by_separate_source_verifier':True,
        })
    return {'schema':'ifs.cig004.chain-campaign.v1',
       'environment':{'python':sys.version.split()[0],'os':platform.platform()},
       'provenance':{'prior':'CIG-001/002/003','external_execution':'none',
          'time':'source law logical time, not wall-clock time',
          'measurements':'local Python process, three timings per depth'},
       'records':records}


if __name__=='__main__':print(json.dumps(run(),indent=2))
