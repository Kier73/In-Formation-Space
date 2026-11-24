"""CIG-005 source-verified multi-intention benchmark, local measured timings."""
from __future__ import annotations
from statistics import median
from time import perf_counter_ns
import json,platform,sys

from joint_intention_ground import (make_branching_source,compile_ground,DEFAULT_PRICES)
from verify_joint_intention import verify


def execute(repetitions=5):
    source=make_branching_source()
    cut=[0,1,2,3,4]
    profiles=[('default',dict(DEFAULT_PRICES)),
              ('raw-observation-free',{'y':0,'j':0,'z':0,'y_xor_j':200,'y_and_j':200}),
              ('derived-observation-unavailable',{'y':3,'j':2,'z':6,'y_xor_j':999,'y_and_j':999})]
    results=[]
    for name,prices in profiles:
        build=[];audit=[];certificate=None
        for _ in range(repetitions):
            candidate,elapsed=compile_ground(source,cut,prices=prices,initial=3,
                                              steps=10**100+173)
            before=perf_counter_ns()
            assert verify(source,candidate,expected_prices=prices)
            audit.append((perf_counter_ns()-before)/1e6)
            build.append(elapsed['producer_ns']/1e6)
            if certificate is None:certificate=candidate
            else:
                # Construction receipts contain no timing-dependent mathematical
                # identity, so repeated runs are bit-for-bit reproducible.
                assert candidate==certificate
        results.append({'case':name,
            'producer_median_ms':round(median(build),4),
            'receiver_median_ms':round(median(audit),4),
            'chosen_measurements':certificate['policy']['selected'],
            'declared_price':certificate['policy']['declared_cost'],
            'whole_future_shared_features':certificate['whole_future']['dimension'],
            'separate_feature_dimensions':certificate['individual_dimensions'],
            'eventual_linear_dimension':certificate['eventual']['stable_linear_dimension'],
            'eventual_nonlinear_quotient_bits':certificate['quotient']['minimum_binary_bits'],
            'eventual_quotient_states':certificate['quotient']['image_size'],
            'support_states_evaluated_for_quotient':certificate['ledger']['quotient_local_state_visits'],
            'policy_state_evaluations':certificate['ledger']['policy_local_evaluations'],
            'symbolic_matrix_products':certificate['navigation']['matrix_products'],
            'source_witness_validated':True,
            'original_sat_count':certificate['source_result']['count']})
    return {'schema':'ifs.cig005.joint-observer-campaign.v1',
            'environment':{'python':platform.python_version(),'platform':platform.platform()},
            'repetitions_per_case':repetitions,
            'original_endpoint_variables':source['base']['n'],
            'original_source_clauses':len(source['base']['clauses'])+len(source['coupling']),
            'logical_time_decimal':str(10**100+173),
            'cases':results,
            'evidence_scope':'local Python timing; symbolic finite source; no physical observer acquisition',
            'budget_status':'bounded feature closure and at most 8 local support states per decoder check'}


if __name__=='__main__':print(json.dumps(execute(),indent=2))
