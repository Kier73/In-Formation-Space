"""SFI-001 reproducible generated-interpreter SAT/#SAT campaign."""
from __future__ import annotations
import json
import platform
from time import perf_counter
from pathlib import Path

from algebraic_ground import planted_dense,random_cubic_tseitin,encode_xor
from derived_ground import compile_proven_ground,split_guard,implication_equalities
from frontier_ground import random_3cnf,brute_count
from self_forming_sat import form,verify_program,execute_partition,aggregate


def cases():
    pure,_,_=planted_dense(48,8,22,False)
    mixed,_,_=planted_dense(48,8,22,True)
    contradiction,n,_=random_cubic_tseitin(24,7301)
    indirect,ni=implication_equalities(12)
    hidden=split_guard(split_guard(encode_xor(0b1111,1),guard_id=5),guard_id=6)
    return [('dense-48',pure,48,{}),('dense-mixed-48',mixed,48,{}),
            ('tseitin-36-unsat',contradiction,n,{}),
            ('implication-23',indirect,ni,{}),
            ('guarded-parity-6',hidden,6,{}),
            ('incomplete-guard-5',split_guard(encode_xor(0b1111,1),guard_id=5)[:-1],5,{}),
            ('random-16',random_3cnf(16,64,73),16,{}),
            ('random-35-refusal',random_3cnf(35,140,73),35,{'max_resolution_attempts':1})]


def campaign():
    report={'schema':'sfi.direct-sat-campaign.v1','environment':{'python':platform.python_version(),'host':'local single-process CPU'},'cases':[]}
    for name,cls,n,compiler_args in cases():
        construction=perf_counter()
        evidence=compile_proven_ground(cls,n,**compiler_args)
        program,stats=form(evidence,intention='#SAT',partition_size=1024)
        assert verify_program(program,evidence)
        build_ms=round((perf_counter()-construction)*1000,3)
        t=perf_counter()
        results=[execute_partition(program,i) for i in range(len(program['partitions']))]
        result=aggregate(program,results,source_receipt=evidence)
        search_ms=round((perf_counter()-t)*1000,3)
        count=result['count']
        if n<=16: assert count==brute_count(cls,n)
        if evidence['result']['status']=='exact':
            assert count==evidence['result']['count']
        report['cases'].append({'name':name,'source_vars':n,'source_clauses':len(cls),
            'construction_and_check_ms':build_ms,'search_and_independent_recheck_ms':search_ms,
            'source_ground_producer_ms':stats['source_ground_compilation_elapsed_ms'],
            'registers':stats['generated_registers'],'generated_gates':stats['generated_gates'],
            'partitions':stats['generated_hosts'],'coordinates_checked':result['evaluated'],
            'mode':program['mode'],'status':result['status'],'count':count,
            'program_digest':program['digest']})
    return report

if __name__=='__main__':
    data=campaign()
    (Path(__file__).parent/'SFI-001-results.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data,indent=2))
