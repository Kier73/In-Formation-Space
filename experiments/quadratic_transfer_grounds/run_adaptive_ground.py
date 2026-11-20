"""TCN-005 deterministic Ground-selection benchmark, conditional on declared operations."""
import json
import time
import numpy as np
from adaptive_ground import PhaseCarrier, choose_ground, choice_receipt, verify_choice_receipt
from branch import StructuredState, gate_phases, dense_quadratic_reference
from cocycle import ExactSchedule


def run():
    results={'experiment':'TCN-005',
             'premise':'declared polynomial/harmonic phase gates and quadratic schedules',
             'scope':'local synthetic comparison, not inferred dynamics or a physical future',
             'sizes':{}, 'large_coordinate':{}, 'fused_gates':{}, 'receipts':{}}
    for p in (31,127,257):
        base=StructuredState.flat(p,7,13)
        targets=(0,1,3,p//2,p-1)
        start=time.perf_counter()
        cubic=choose_ground(base,'cubic',5,(2,7,9),13,targets,
                            max_terms=7,error_budget=0,
                            max_query_work=7*p*len(targets),cubic_frame_scan=True)
        selection_ms=1000*(time.perf_counter()-start)
        truth=dense_quadratic_reference(p,(2,7,9),13,
                  gate_phases(p,'cubic',5)*base.dense())
        cubic_error=max(abs(z-truth[y]) for z,y in zip(cubic.amplitudes(),targets))
        harmonic=choose_ground(base,'harmonic',.7,(2,7,9),13,targets,
                               max_terms=7,error_budget=.01,
                               max_query_work=7*p*len(targets))
        htruth=dense_quadratic_reference(p,(2,7,9),13,
                 gate_phases(p,'harmonic',.7)*base.dense())
        harmonic_error=max(abs(z-htruth[y]) for z,y in zip(harmonic.amplitudes(),targets))
        results['sizes'][str(p)]={
            'cubic':{'chosen':cubic.representation,'decision':cubic.decision,
                     'minimum_required_rank_in_quadratic_frame':cubic.sparse_probe['minimum_rank'],
                     'query_work_estimate':cubic.estimated_query_work,
                     'max_abs_error_against_direct_FFT':cubic_error,
                     'selection_ms_local':selection_ms},
            'harmonic':{'chosen':harmonic.representation,'decision':harmonic.decision,
                        'ideal_error_bound':harmonic.approximation_error_bound,
                        'query_work_estimate':harmonic.estimated_query_work,
                        'max_abs_error_against_direct_FFT':harmonic_error}}
    p=127
    base=StructuredState.flat(p,7,13)
    fused=PhaseCarrier.start(base)
    for _ in range(100):
        fused=fused.apply_gate('cubic',3).apply_gate('harmonic',.01)
    results['fused_gates']={'declared_interventions':fused.interventions,
                            'stored_gate_parameters':2,
                            'cubic_coefficient':fused.cubic,
                            'harmonic_strength':fused.harmonic}
    n=10**100+123
    schedule=ExactSchedule(p,(2,5,9))
    carrier,products=fused.after_schedule((2,5,9),n)
    oracle=schedule.navigate(n)[0].apply_coordinate(
        gate_phases(p,'cubic',fused.cubic)*
        gate_phases(p,'harmonic',fused.harmonic)*base.dense(),17)
    results['large_coordinate']={'decimal_digits':len(str(n)),
                                 'exact_operator_products':products,
                                 'carrier_terms':len(carrier.base.terms),
                                 'error_against_operator_model':abs(oracle-carrier.amplitude(17)),
                                 'physical_future_witnessed':False}
    accepted=choice_receipt(base,'cubic',5,(2,5),7,(3,10),
                            max_terms=7,error_budget=0,max_query_work=500)
    refused=choice_receipt(base,'cubic',5,(2,5),7,(3,10),
                           max_terms=7,error_budget=0,max_query_work=2)
    results['receipts']={'admitted_rechecks':verify_choice_receipt(accepted),
                         'refusal_rechecks':verify_choice_receipt(refused),
                         'admitted_sha256':accepted['sha256'],
                         'refused_sha256':refused['sha256']}
    return results

if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
