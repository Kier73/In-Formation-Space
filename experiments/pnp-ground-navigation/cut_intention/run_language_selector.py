"""CIG-006 local multi-time source-ground ledger with original-CNF replay."""
from __future__ import annotations
import json,platform
from time import perf_counter_ns
from joint_intention_ground import make_branching_source
from language_selector import compile_language
from verify_language_selector import verify

def run():
    source=make_branching_source();cut=[0,1,2,3,4]
    records=[]
    for timepoint in (0,1,3,10**100+173):
        started=perf_counter_ns()
        ground,ledger=compile_language(source,cut,steps=timepoint)
        vstart=perf_counter_ns()
        assert verify(source,ground,intention=ground['intent'])
        verified_ns=perf_counter_ns()-vstart
        chosen=ground['chosen_candidate_index']
        records.append({'time':str(timepoint),'consensus':ground['consensus_status'],
              'total_source_orientations':ground['candidate_class']['cartesian_options'],
              'source_valid_processors':ground['candidate_class']['conflict_free_count'],
              'chosen_orientation':ground['candidates'][chosen]['orientation'] if chosen is not None else None,
              'feature_dimensions':[c.get('feature_dimension') for c in ground['candidates']],
              'intention_nonlinear_code_bits':[c.get('snapshot',{}).get('minimum_binary_bits') for c in ground['candidates']],
              'future_image_sizes':[c.get('snapshot',{}).get('image_size') for c in ground['candidates']],
              'counterexample':ground['disagreement_witness'],
              'full_production_ms':round((perf_counter_ns()-started-verified_ns)/1e6,4),
              'independent_verification_ms':round(verified_ns/1e6,4),
              'source_fixedpoint_models':ground['source_model']['active_fixed_points'],
              'original_source_model_count':ground['source_model']['original_model_count'],
              'total_producer_feature_pullbacks':ground['ledger']['candidate_feature_pullbacks'],
              'total_matrix_products':ground['ledger']['candidate_matrix_products']})
    return {'schema':'ifs.cig006.source-language-campaign.v1',
        'environment':{'python':platform.python_version(),'platform':platform.platform()},
        'source_endpoint_variables':source['base']['n'],
        'source_original_clauses':len(source['base']['clauses'])+len(source['coupling']),
        'cases':records,'scope':'finite complete orientation class, mathematical outcomes; no live host'}
if __name__=='__main__':print(json.dumps(run(),indent=2))
