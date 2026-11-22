"""SFI-002 exact problem-guided interpreter selection.

The compiler independently attempts two bounded, source-qualified architectures:
  - non-affine local functional DAG of truth-table instructions;
  - PNG-003 proof-carrying finite-field affine coordinate machine.
It compares their *verified* semantic capacity under the same coordinate budget.
The selection is heuristic, all source/verification costs are recorded, and
neither candidate is assumed to exist on arbitrary CNF descriptions.
"""
from __future__ import annotations
from time import perf_counter

from morphic_sat import compile_ground, execute
from morphic_verifier import verify,check_partition
from derived_ground import compile_proven_ground
from self_forming_sat import form,verify_program,execute_partition,aggregate


def choose(clauses,n,*,intention='#SAT',maximum_coordinates=65536,
           maximum_free=16,partition_size=1024,resolution_attempts=5000,
           self_refine=False):
    if intention not in ('SAT','#SAT') or type(maximum_free) is not int or \
       not 0<=maximum_free<=20 or type(maximum_coordinates) is not int or \
       not 0<=maximum_coordinates<=1<<20:
        raise ValueError('invalid observer intention or finite budgets')
    if type(self_refine) is not bool:
        raise ValueError('self-refinement must be an explicit Boolean option')
    start=perf_counter()
    improvement=None
    if self_refine:
        from recursive_sat_compiler import refine, audit_refinement
        gate,improvement=refine(clauses,n)
        audit_refinement(clauses,n,gate,improvement)
        gate_ledger={**improvement['baseline_ledger'],
                     'recursive_refinement_receipt':improvement['digest'],
                     'recursive_refinement_ms':improvement['elapsed_ms'],
                     'recursive_meta_attempts':len(improvement['meta_attempts'])}
    else:
        gate,gate_ledger=compile_ground(clauses,n)
    gate_audit=verify(gate,max_free=maximum_free)
    gate_space=1 << len(gate['registers'])
    gate_feasible=(len(gate['registers'])<=maximum_free and
                   gate_space<=maximum_coordinates and
                   (gate_space+partition_size-1)//partition_size<=128)
    affine_start=perf_counter()
    affine_receipt=compile_proven_ground(clauses,n,
        max_resolution_attempts=resolution_attempts)
    affine,astats=form(affine_receipt,intention=intention,
                       maximum_free=maximum_free,partition_size=partition_size)
    verify_program(affine,affine_receipt)
    affine_ms=round((perf_counter()-affine_start)*1000,3)
    affine_mode=affine['mode']
    affine_space=(1<<affine['free_dimension']) if affine['free_dimension'] is not None else 0
    affine_feasible=affine_mode=='refutation' or (
        affine_mode=='constructed-search' and affine_space<=maximum_coordinates)
    # Preference is semantic (verified ability to conclude) and then finite
    # coordinate cost. No SAT answer is used to choose an interpreter.
    competitors=[]
    if gate_feasible:competitors.append((gate_space,1,'local-Boolean-functions'))
    if affine_feasible:competitors.append((affine_space,0,'affine-proof-ground'))
    selected=min(competitors)[2] if competitors else 'undetermined'
    result={'selected':selected,'machine_ground_digest':gate['digest'],
            'affine_program_digest':affine['digest'],
            'constructive_candidates':{
                'local-Boolean-functions':{'status':'admitted' if gate_feasible else 'budget-refusal',
                    'registers':len(gate['registers']),
                    'candidate_coordinates':gate_space,
                    'instructions':len(gate['instructions']),
                    'proof_verified':gate_audit['proven'],
                    'construction_ledger':gate_ledger},
                'affine-proof-ground':{'status':affine_mode if affine_feasible else 'budget-refusal',
                    'registers':affine['free_dimension'],
                    'candidate_coordinates':affine_space if affine_feasible else None,
                    'proof_verified':True,
                    'construction_and_check_ms':affine_ms,
                    'proof_steps':astats['proof_steps']}},
            'construction_and_selection_ms':round((perf_counter()-start)*1000,3),
            'source_variables':n,'intention':intention,
            '_local_ground':gate,'_affine_program':affine,'_affine_receipt':affine_receipt}
    if self_refine:
        result['self_refinement']={
            'receipt_digest':improvement['digest'],
            'outcome':improvement['outcome'],
            'baseline_registers':improvement['baseline_registers'],
            'refined_registers':improvement['refined_registers'],
            'independently_audited':True}
    return result


def realize(plan,*,maximum_coordinates=65536,partition_size=1024):
    start=perf_counter()
    kind=plan['selected']
    if kind=='undetermined':
        return {'status':'UNKNOWN','count':None,'witness':None,'checked':0,
                'architecture':'undetermined','reason':'No proved feasible candidate under budget'}
    if kind=='local-Boolean-functions':
        ground=plan['_local_ground']
        verify(ground)
        r=execute(ground,intent='COUNT' if plan['intention']=='#SAT' else 'SAT',
                  max_coordinates=maximum_coordinates,partition_size=partition_size)
        for partition in r.get('partition_receipts',[]):
            check_partition(ground,partition,maximum=maximum_coordinates,
                            partition_size=partition_size)
        return {'status':r['status'],'count':r['models'],'witness':r['witness_decimal'],
                'checked':r['checked'],'architecture':kind,
                'execution_and_check_ms':round((perf_counter()-start)*1000,3)}
    if kind=='affine-proof-ground':
        p=plan['_affine_program'];receipt=plan['_affine_receipt']
        verify_program(p,receipt)
        parts=[execute_partition(p,index) for index in range(len(p['partitions']))]
        result=aggregate(p,parts,source_receipt=receipt)
        return {'status':result['status'],'count':result['count'],
                'witness':result['witness'],'checked':result['evaluated'],
                'architecture':kind,'execution_and_check_ms':round((perf_counter()-start)*1000,3)}
    raise ValueError('unknown architecture')


def _decompose(clauses,n):
    """Exact connected components of the clause-variable incidence graph.

    Every original variable occurs exactly once in one component. Every
    nonempty source clause belongs wholly to one component. Isolated variables
    are not discarded: each contributes its own free Boolean coordinate.
    """
    from morphic_sat import normalize
    source=normalize(clauses,n)
    if () in source:return None
    parent=list(range(n+1))
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def union(x,y):
        a=find(x);b=find(y)
        if a!=b:parent[max(a,b)]=min(a,b)
    for clause in source:
        ids=[abs(l) for l in clause]
        for v in ids[1:]:union(ids[0],v)
    groups={}
    for v in range(1,n+1):groups.setdefault(find(v),[]).append(v)
    assignments={root:[] for root in groups}
    for clause in source:
        assignments[find(abs(clause[0]))].append(clause)
    components=[]
    for root,variables in sorted(groups.items(),key=lambda kv:min(kv[1])):
        lookup={v:i+1 for i,v in enumerate(variables)}
        local=[[lookup[abs(l)] if l>0 else -lookup[abs(l)] for l in clause]
               for clause in assignments[root]]
        components.append({'source_variables':variables,'local_clauses':local,
                           'original_clauses':assignments[root]})
    # Reassemble the original CNF and variable universe explicitly.
    reconstructed=[tuple(c) for item in components for c in item['original_clauses']]
    if set(reconstructed)!=set(source) or sorted(v for item in components for v in item['source_variables'])!=list(range(1,n+1)):
        raise ValueError('decomposition proof cannot reconstruct source')
    return components


def choose_composite(clauses,n,*,intention='#SAT',maximum_coordinates=65536,
                     maximum_free=16,partition_size=1024,resolution_attempts=5000,
                     self_refine=False):
    """Form a composite interpreter of independently selectable sub-machines.

    Standard CNF component factoring, not a new worst-case SAT method. Exact
    #SAT counts multiply only because the source supports are disjoint.
    """
    components=_decompose(clauses,n)
    if components is None:
        return {'status':'UNSAT','count':0,'selected':[],'components':[],
                'reason':'explicit empty clause with all-assignment contradiction',
                'original_variables':n}
    results=[];plans=[]
    for component in components:
        p=choose(component['local_clauses'],len(component['source_variables']),
                 intention=intention,maximum_coordinates=maximum_coordinates,
                 maximum_free=maximum_free,partition_size=partition_size,
                 resolution_attempts=resolution_attempts,
                 self_refine=self_refine)
        r=realize(p,maximum_coordinates=maximum_coordinates,
                  partition_size=partition_size)
        plans.append({'source_variables':component['source_variables'],
                      'selected':p['selected'],
                      'registers':p['constructive_candidates'][p['selected']]['registers']
                        if p['selected']!='undetermined' else None,
                      'local_result':r,'construction_and_selection_ms':p['construction_and_selection_ms']})
        results.append(r)
    if any(r['status']=='UNSAT' for r in results):
        status='UNSAT';count=0
    elif any(r['status']=='UNKNOWN' for r in results):
        status='UNKNOWN';count=None
    else:
        status='SAT'
        count=__import__('math').prod(r['count'] for r in results) if intention=='#SAT' else None
    return {'status':status,'count':count,'original_variables':n,
            'component_count':len(components),'selected':[p['selected'] for p in plans],
            'components':plans,'source_factorization_verified':True,
            'claim':'exact on disjoint variable components only; no combined-host authority'}
