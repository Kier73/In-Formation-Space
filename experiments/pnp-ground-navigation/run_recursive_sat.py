"""Reproduce SFI-003 direct self-application and its construction/evaluation ledger."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from time import perf_counter

from morphic_sat import compile_ground, execute, seeded_circuit
from recursive_sat_compiler import refine, audit_refinement
from test_recursive_sat_compiler import REPAIRABLE, reference_count


def measure(case, source, n, *, count_budget=65536, repeats=3):
    start=perf_counter()
    baseline,baseline_ledger=compile_ground(source,n)
    baseline_build_ms=round((perf_counter()-start)*1000,3)
    improved,refinement=refine(source,n)
    audit=audit_refinement(source,n,improved,refinement)
    results=[]
    for name,g in (('baseline',baseline),('self-refined',improved)):
        times=[];answer=None
        for _ in range(repeats):
            clock=perf_counter()
            r=execute(g,intent='COUNT',max_coordinates=count_budget,partition_size=1024)
            times.append(round((perf_counter()-clock)*1000,3))
            if answer is not None:assert r['models']==answer
            answer=r['models']
        results.append({'name':name,'registers':len(g['registers']),
                        'exact_coordinates_evaluated':r['checked'],
                        'source_solutions':answer,
                        'execution_median_ms':round(median(times),3),
                        'execution_samples_ms':times})
    assert results[0]['source_solutions']==results[1]['source_solutions']
    return {'case':case,'original_variables':n,'source_clauses':len(source),
            'exact_source_count_checked_bruteforce':reference_count(source,n) if n<=10 else None,
            'baseline':results[0],'self_refined':results[1],
            'candidate_gate_pool':refinement['candidate_pool_size'],
            'bounded_optimum_audited':audit['candidate_pool_optimum_checked'],
            'meta_sat_attempts':[{'threshold':v['threshold'],'outcome':v['status'],
                                  'coordinates_checked':v['meta_coordinates_checked'],
                                  'meta_ground_digest':v['meta_ground_digest']}
                                 for v in refinement['meta_attempts']],
            'baseline_compile_ms':baseline_build_ms,
            'refinement_compile_ms':refinement['elapsed_ms'],
            'extra_compile_ms':round(refinement['elapsed_ms']-baseline_build_ms,3),
            'measured_query_time_saved_ms':round(results[0]['execution_median_ms']-
                                                 results[1]['execution_median_ms'],3),
            'measured_break_even_query_uses':(
                round(max(0,refinement['elapsed_ms']-baseline_build_ms)/
                      (results[0]['execution_median_ms']-results[1]['execution_median_ms']),3)
                if results[0]['execution_median_ms']>results[1]['execution_median_ms'] else None),
            'report_digest':refinement['digest'],
            'exact_source_semantics_verified':True,
            'no_p_np_claim':True}


def run():
    fixtures=[('satisfiable-overlap-6',REPAIRABLE,6,64),
              ('satisfiable-overlap-with-11-free-bits',REPAIRABLE,17,65536)]
    reports=[measure(label,clauses,n,count_budget=budget)
             for label,clauses,n,budget in fixtures]
    broad,n,_=seeded_circuit(9,gates=12)
    other,r=refine(broad,n)
    assert audit_refinement(broad,n,other,r)['source_equivalence_verified']
    reports.append({'case':'large-candidate-budget-refusal','original_variables':n,
                    'candidate_pool_size':r['candidate_pool_size'],
                    'retained_verified_baseline':r['outcome']=='PRESERVED_BASELINE',
                    'reason':r['reason']})
    return {'schema':'sfi.recursive-meta-sat-benchmark.v1',
            'environment':'CPU Python standard library; localhost; no distributed execution',
            'runs':reports,'scope':'single-host measured performance, no global optimality claim'}


if __name__=='__main__':
    result=run()
    destination=Path(__file__).with_name('SFI-003-results.json')
    destination.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps(result,sort_keys=True,indent=2))
