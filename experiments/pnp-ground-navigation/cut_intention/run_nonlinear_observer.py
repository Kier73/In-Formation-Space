"""CIG-003 producer+independent receiver benchmark with explicit scope ledger."""
from __future__ import annotations
import json,platform
from statistics import median
from time import perf_counter_ns
from pathlib import Path

from nonlinear_observer_ground import make_gated_source,compile_ground,source_reduce
from verify_nonlinear_observer import verify


def campaign():
    rows=[]
    for groups in (2,4,8):
        source,cut=make_gated_source(groups=groups)
        for native,anf in ((2,0),(0,2),(4,3)):
            prod=[];check=[]
            sample=None
            for _ in range(9):
                start=perf_counter_ns()
                cert,timing=compile_ground(source,cut,native_price=native,anf_price=anf)
                mid=perf_counter_ns()
                assert verify(source,cert)
                end=perf_counter_ns()
                prod.append((mid-start)/1e6)
                check.append((end-mid)/1e6)
                sample=cert
            p=sample['observation_policy']
            rows.append({'groups':groups,'source_original_variables':source['base']['n'],
                'source_original_clauses':len(source['base']['clauses'])+len(source['coupling']),
                'source_active_labels':len(sample['active_labels']),
                'source_active_truth_table_size':sample['ledger']['global_active_state_count'],
                'bounded_local_states_per_count':sample['ledger']['enumerated_component_states'],
                'local_component_widths':[len(c['variables']) for c in sample['components']],
                'nonlinear_source_proved_gates':sample['nonlinear_gate_count'],
                'source_model_count':sample['result']['count'],
                'cut_rank':sample['result']['rank'],
                'native_output_declared_cost':native,'derived_anf_declared_cost':anf,
                'observer_candidates':p['candidate_indices'],
                'observer_selected':p['selected'],
                'median_compile_ms':round(median(prod),4),
                'median_independent_verify_ms':round(median(check),4),
                'all_runs_receiver_replayed':True})
    return {'schema':'ifs.cig003.nonlinear-observer-benchmark.v1',
            'python':platform.python_version(), 'platform':platform.platform(),
            'samples_each':9,'wall_times':'single-process local, not network or sensor latency',
            'measured_source_only_no_real_sensors':True,'rows':rows}


if __name__=='__main__':print(json.dumps(campaign(),indent=2))
