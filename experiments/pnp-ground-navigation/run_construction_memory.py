"""SFI-004 measured cost campaign; reports actual full audit overhead."""
from __future__ import annotations
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import json
import platform

from construction_memory import ConstructionMemory, verify_memory
from morphic_sat import compile_ground, execute
from morphic_verifier import check_partition, verify
from recursive_sat_compiler import refine, audit_refinement
from test_recursive_sat_compiler import REPAIRABLE


def time_call(fn):
    t=perf_counter_ns();value=fn()
    return value, round((perf_counter_ns()-t)/1e6,4)


def count_checked(ground, budget, partition_size=1024):
    verify(ground,max_free=256)
    result=execute(ground,intent='COUNT',max_coordinates=budget,partition_size=partition_size)
    if result['status']!='UNKNOWN':
        for part in result['partition_receipts']:
            check_partition(ground,part,maximum=budget,partition_size=partition_size)
    return {'status':result['status'],'models':result['models'],'checked':result['checked']}


def main():
    data={'schema':'sfi.construction-memory-campaign.v1',
          'environment':{'python':platform.python_version(),'platform':platform.platform(),
                         'execution':'single local CPU; independent Python process recovery tested by unittest'},
          'cases':[],'limitations':['wall timing is observational, not authenticated',
                                   'old source is a normalized clause subset of new source',
                                   'structural memory is not a quorum or a remote execution authority',
                                   'no uniform polynomial SAT inference claim']}
    for n, extra, label in [(6,[(-1,2)],'six-variable-monotone-extension'),
                            (17,[(-1,2)],'seventeen-variable-monotone-extension'),
                            (6,[(1,),(-1,)],'new-contradiction'),
                            (6,[], 'same-source-replay')]:
        new=[*REPAIRABLE,*extra]
        with TemporaryDirectory() as d:
            memory=ConstructionMemory(Path(d)/'memory.json')
            prior,bootstrap_ms=time_call(lambda:memory.bootstrap(REPAIRABLE,n))
            revived,reuse_ms=time_call(lambda:memory.extend(new,n))
            def fresh_greedy():
                ground,ledger=compile_ground(new,n)
                verify(ground,max_free=256)
                return ground,ledger
            def fresh_meta():
                ground,report=refine(new,n)
                audit_refinement(new,n,ground,report)
                return ground,report
            rebuilt,greedy_ms=time_call(fresh_greedy)
            optimized,meta_ms=time_call(fresh_meta)
            assert len(revived['ground']['registers']) <= len(rebuilt[0]['registers'])
            budget=65536 if n==17 else 64
            # Execution+source verifier is deliberately included on BOTH.
            old_runs=[];new_runs=[]
            for _ in range(3):
                ro,ms=time_call(lambda:count_checked(rebuilt[0],budget))
                old_runs.append(ms)
                rn,ms=time_call(lambda:count_checked(revived['ground'],budget))
                new_runs.append(ms)
                assert ro['models']==rn['models']
                assert rn['status']==ro['status']
            observed,observation_ms=time_call(lambda:memory.observe(
                revived['digest'],intention='#SAT',coordinate_budget=budget,
                partition_size=1024))
            checked,read_ms=time_call(lambda:verify_memory(memory.read()))
            assert checked['qualified_constructions']==2
            data['cases'].append({
                'name':label,'source_variables':n,
                'source_clauses':len(revived['source_clauses']),
                'prior_ground':prior['ground']['digest'],
                'prior_bootstrap_and_audit_ms':bootstrap_ms,
                'reuse_mode':revived['method'],
                'fresh_greedy_registers':len(rebuilt[0]['registers']),
                'remembered_registers':len(revived['ground']['registers']),
                'fresh_meta_registers':len(optimized[0]['registers']),
                'greedy_compilation_and_proof_audit_ms':greedy_ms,
                'fresh_meta_compilation_and_proof_audit_ms':meta_ms,
                'memory_reuse_with_qualified_predecessor_cache_ms':reuse_ms,
                'greedy_execute_and_verify_median_ms':median(old_runs),
                'remembered_execute_and_verify_median_ms':median(new_runs),
                'greedy_verified_samples_ms':old_runs,
                'remembered_verified_samples_ms':new_runs,
                'memory_observe_and_persist_with_replay_ms':observation_ms,
                'full_image_source_and_observation_reaudit_ms':read_ms,
                'exact_models':observed['result']['models'],
                'coordinates_verified':observed['result']['checked'],
                'source_checked':True})
    out=Path(__file__).with_name('SFI-004-results.json')
    out.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    print(json.dumps(data,indent=2,sort_keys=True))
    return data


if __name__=='__main__':main()
