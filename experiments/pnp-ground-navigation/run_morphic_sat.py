"""Reproduce SFI-002 non-affine and heterogeneous interpreter campaign."""
from __future__ import annotations
from pathlib import Path
import json
import platform

from morphic_sat import seeded_circuit
from self_selecting_sat import choose,realize,choose_composite
from algebraic_ground import random_cubic_tseitin,planted_dense
from frontier_ground import random_3cnf,brute_count


def mixed_case():
    nonlinear,base,_=seeded_circuit(5,gates=56)
    linear,_,_=planted_dense(40,4,22,False)
    return (nonlinear + [tuple((abs(l)+base)*(1 if l>0 else -1) for l in clause)
                         for clause in linear],base+40)


def campaign():
    dense64,n64,_=seeded_circuit(5,gates=56)
    dense128,n128,_=seeded_circuit(17,gates=120)
    tseitin,nt,_=random_cubic_tseitin(40)
    mixed,nmixed=mixed_case()
    random16=random_3cnf(16,64,73)
    random35=random_3cnf(35,140,73)
    cases=[('nonaffine-64',dense64,n64,'single'),
           ('nonaffine-128',dense128,n128,'single'),
           ('parity-global-unsat-60',tseitin,nt,'single'),
           ('heterogeneous-disjoint-104',mixed,nmixed,'composite'),
           ('heterogeneous-bridged-104',mixed+[(1,65)],nmixed,'composite'),
           ('general-random-16',random16,16,'single'),
           ('general-random-35',random35,35,'single')]
    results=[]
    for name,source,n,kind in cases:
        if kind=='single':
            plan=choose(source,n)
            outcome=realize(plan)
            operators=plan['constructive_candidates']
            item={'case':name,'source_variables':n,'source_clauses':len(source),
                  'selected':plan['selected'],
                  'nonaffine_registers':operators['local-Boolean-functions']['registers'],
                  'nonaffine_instructions':operators['local-Boolean-functions']['instructions'],
                  'affine_registers':operators['affine-proof-ground']['registers'],
                  'nonaffine_support_attempts':operators['local-Boolean-functions']['construction_ledger']['support_attempts'],
                  'nonaffine_scanned_literals':operators['local-Boolean-functions']['construction_ledger']['local_literal_scans'],
                  'construction_and_selection_ms':plan['construction_and_selection_ms'],
                  'execution_and_verification_ms':outcome.get('execution_and_check_ms'),
                  'status':outcome['status'],'count':outcome['count'],'coordinates_checked':outcome['checked']}
        else:
            outcome=choose_composite(source,n)
            item={'case':name,'source_variables':n,'source_clauses':len(source),
                  'selected':outcome['selected'],
                  'component_count':outcome['component_count'],
                  'component_registers':[s['registers'] for s in outcome['components']],
                  'construction_and_selection_ms':round(sum(c['construction_and_selection_ms']
                       for c in outcome['components']),3),
                  'status':outcome['status'],'count':outcome['count'],
                  'component_counts':[c['local_result']['count'] for c in outcome['components']]}
        if n<=16 and item['status']!='UNKNOWN':
            assert item['count']==brute_count(source,n),name
        results.append(item)
    assert results[0]['count']==168
    assert results[3]['count']==2688
    assert results[3]['selected']==['local-Boolean-functions','affine-proof-ground']
    assert results[4]['status']=='UNKNOWN'
    assert results[2]['status']=='UNSAT'
    return {'schema':'sfi-002.problem-selected-heterogeneous-sat.v1',
            'environment':{'python':platform.python_version(),
                           'substrate':'single-host ordinary CPU, standard Python'},
            'cases':results,
            'limits':{'maximum_search_coordinates':65536,
                      'maximum_free_bits':16,
                      'local_function_support_variables':4,
                      'per_component_execution':True,
                      'physical_remote_execution_proven':False}}


if __name__=='__main__':
    report=campaign()
    path=Path(__file__).parent/'SFI-002-results.json'
    path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True))
