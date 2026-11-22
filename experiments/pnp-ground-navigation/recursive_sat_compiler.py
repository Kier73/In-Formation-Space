"""SFI-003: let the existing SFI-002 interpreter improve its own construction.

A bounded set of *source-discovered* local Boolean functions becomes an ordinary
CNF meta-problem: select non-overlapping, output-distinct acyclic gates, and
maximize the number of derived registers. The existing SFI-002 CNF compiler
and executable interpreter solve these meta-formulas; an independently written
exhaustive checker audits the result and certifies the best bounded covering.

This does not infer general program semantics, improve arbitrary SAT complexity,
or give a source-generated program external execution authority. Every limited
or unqualified meta-search returns the previously verified greedy Ground.
"""
from __future__ import annotations

from itertools import combinations
from time import perf_counter

from morphic_sat import (compile_ground as greedy_compile, discover, normalize,
                        execute as run_interpreter, digest, _topological)
from morphic_verifier import verify as verify_ground, check_partition

SCHEMA = 'sfi.recursive-interpreter-refinement.v1'
MAX_GATES = 10
MAX_META_STATES = 1 << MAX_GATES
MAX_META_CLAUSES = 512
MAX_META_ROUNDS = 32


def _candidates(source, n, candidate_budget):
    discovered, stats = discover(source, n, max_candidates=candidate_budget)
    discovered.sort(key=lambda g:(-len(g['clauses']),-len(g['inputs']),
                                  -g['output'], tuple(g['inputs'])))
    return discovered, stats


def _conflicts(candidates):
    blocks = [{tuple(c) for c in gate['clauses']} for gate in candidates]
    return [(-(i+1),-(j+1))
            for i in range(len(candidates))
            for j in range(i+1,len(candidates))
            if candidates[i]['output']==candidates[j]['output'] or
               not blocks[i].isdisjoint(blocks[j])]


def _at_least(k, threshold):
    # Cardinality without auxiliary variables: for every (k-threshold+1)-subset,
    # at least one selection variable must be true. This is deliberately capped.
    return [tuple(i+1 for i in group)
            for group in combinations(range(k),k-threshold+1)]


def _build(source, n, chosen):
    ordered=_topological(chosen)
    if ordered is None:
        raise ValueError('candidate meta solution contains a dependency cycle')
    used={tuple(c) for g in ordered for c in g['clauses']}
    outputs={g['output'] for g in ordered}
    ground={'schema':'sfi.problem-formed-boolean-interpreter.v2',
            'n':n,'source_clauses':[list(c) for c in source],
            'instructions':ordered,
            'residual':[list(c) for c in source if c not in used],
            'registers':[v for v in range(1,n+1) if v not in outputs],
            'scope':'exact finite local functional rewrite; no source-independent execution claim'}
    ground['digest']=digest(ground)
    verify_ground(ground,max_free=256)
    return ground


def _meta_attempt(candidates, threshold, blockers, *, meta_budget, compilation_budget):
    k=len(candidates)
    cnf=_conflicts(candidates)+_at_least(k,threshold)+blockers
    if len(cnf)>MAX_META_CLAUSES:
        return None,{'status':'REFUSED','reason':'meta CNF clause budget'}
    # Bootstrapping is finite: use the prior SFI-002 compiler directly, not
    # this recursive optimizer, so no unbounded self-invocation is possible.
    meta_ground,_=greedy_compile(cnf,k,max_candidates=compilation_budget)
    audit=verify_ground(meta_ground,max_free=MAX_GATES)
    if not audit['proven']:
        raise ValueError('existing SAT interpreter refused meta Ground')
    result=run_interpreter(meta_ground,intent='SAT',
                           max_coordinates=meta_budget,partition_size=meta_budget)
    for part in result.get('partition_receipts',[]):
        check_partition(meta_ground,part,maximum=meta_budget,partition_size=meta_budget)
    row={'status':result['status'],'threshold':threshold,
         'meta_cnf_digest':digest({'n':k,'cnf':[list(c) for c in cnf]}),
         'meta_ground_digest':meta_ground['digest'],
         'meta_registers':len(meta_ground['registers']),
         'meta_coordinates_checked':result['checked'],
         'meta_clauses':len(cnf), 'cycle_blockers':len(blockers),
         'meta_partitions_verified':len(result.get('partition_receipts',[]))}
    if result['status']=='SAT':
        mask=int(result['witness_decimal'])
        if not 0<=mask<1<<k or not all(
            any(((mask>>(abs(l)-1))&1)==(l>0) for l in clause)
            for clause in cnf):
            raise ValueError('meta-SAT answer disagrees with its original CNF')
        row['witness_decimal']=str(mask)
        return mask,row
    if result['status']=='UNSAT':
        return None,row
    return None,{**row,'status':'UNKNOWN'}


def refine(clauses,n, *,candidate_budget=4000,max_gates=MAX_GATES,
           meta_budget=MAX_META_STATES,max_rounds=MAX_META_ROUNDS,
           max_meta_clauses=MAX_META_CLAUSES):
    """Run one bounded self-application of the previously built SAT machine.

    Claimed optimality is *only* among the exact candidate pool discovered by
    SFI-002, and only if every higher threshold was completely decided.
    All refusals preserve the original greedy result; never infer UNSAT.
    """
    if (type(candidate_budget) is not int or not 1<=candidate_budget<=4000 or
        type(max_gates) is not int or not 1<=max_gates<=MAX_GATES or
        type(meta_budget) is not int or not 1<=meta_budget<=MAX_META_STATES or
        type(max_rounds) is not int or not 1<=max_rounds<=MAX_META_ROUNDS or
        type(max_meta_clauses) is not int or not 1<=max_meta_clauses<=MAX_META_CLAUSES):
        raise ValueError('invalid finite self-refinement budget')
    t0=perf_counter()
    source=normalize(clauses,n)
    baseline,baseline_ledger=greedy_compile(source,n,max_candidates=candidate_budget)
    verify_ground(baseline,max_free=256)
    candidates,discovery=_candidates(source,n,candidate_budget)
    k=len(candidates)
    steps=[]
    best=baseline
    outcome='PRESERVED_BASELINE'
    complete=False
    reason=None
    if discovery['cutoff']:
        reason='candidate discovery budget reached; pool cannot be claimed complete'
    elif k>max_gates:
        reason='candidate selection exceeds bounded meta-interpreter register budget'
    elif k<=len(baseline['instructions']):
        reason='baseline already selects all discovered candidates'
        complete=True
    else:
        remaining=max_rounds
        complete=True
        for threshold in range(k,len(baseline['instructions']),-1):
            blockers=[]
            while True:
                if remaining<=0:
                    complete=False;reason='self-application round budget';break
                # The local call is additionally subject to caller-specific
                # meta-clause bounds before any constructed search is admitted.
                if (len(_conflicts(candidates))+
                    len(_at_least(k,threshold))+len(blockers)>max_meta_clauses):
                    complete=False;reason='meta clause budget';break
                remaining-=1
                mask,row=_meta_attempt(candidates,threshold,blockers,
                                        meta_budget=meta_budget,
                                        compilation_budget=candidate_budget)
                steps.append(row)
                if row['status'] not in ('SAT','UNSAT'):
                    complete=False;reason='meta SAT refused complete search';break
                if row['status']=='UNSAT':break
                selected=[candidates[i] for i in range(k) if mask>>i&1]
                if _topological(selected) is None:
                    # A selected directed cycle remains cyclic in every
                    # superset. This clause soundly excludes the found mask
                    # and all of its supersets, never a valid architecture.
                    blockers.append(tuple(-(i+1) for i in range(k) if mask>>i&1))
                    row['rejected_for_cycle']=True
                    continue
                candidate=_build(source,n,selected)
                if len(candidate['registers'])>=len(baseline['registers']):
                    raise ValueError('selection SAT produced no asserted improvement')
                best=candidate
                outcome='IMPROVED_BY_OWN_SAT_INTERPRETER'
                reason=None
                break
            if not complete or outcome!='PRESERVED_BASELINE':break
        if complete and outcome=='PRESERVED_BASELINE':
            reason='bounded candidate-cover optimum is the baseline'
    report={'schema':SCHEMA,'source_sha256':digest({'n':n,'clauses':[list(c) for c in source]}),
            'candidate_pool_sha256':digest(candidates),
            'candidate_budget':candidate_budget,
            'candidate_pool_size':k,'baseline_ground_sha256':baseline['digest'],
            'refined_ground_sha256':best['digest'],
            'baseline_registers':len(baseline['registers']),
            'refined_registers':len(best['registers']),
            'baseline_coordinates':1<<len(baseline['registers']),
            'refined_coordinates':1<<len(best['registers']),
            'outcome':outcome,
            'candidate_optimum_certified_by_meta_search':complete and not discovery['cutoff'],
            'meta_attempts':steps,'reason':reason,
            'baseline_ledger':baseline_ledger,
            'candidate_discovery_ledger':discovery,
            'elapsed_ms':round((perf_counter()-t0)*1000,3),
            'claim_scope':'optimal only in bounded discovered candidate-gate pool, not general SAT'}
    report['digest']=digest(report)
    return best,report


def audit_refinement(clauses,n,ground,report, *,max_gates=MAX_GATES):
    """Check the source rewrite, construction identity and claimed finite optimum.

    Independent of the meta-SAT solver: enumerate bounded gate subsets via a
    distinct bitmask cycle/dependency test and exact conflict predicates.
    This is an audit of an optimization proof, not an off-host authority grant.
    """
    if type(report) is not dict or report.get('schema')!=SCHEMA or \
       report.get('digest')!=digest({k:v for k,v in report.items() if k!='digest'}):
        raise ValueError('invalid self-refinement receipt')
    source=normalize(clauses,n)
    if report.get('source_sha256')!=digest({'n':n,'clauses':[list(c) for c in source]}):
        raise ValueError('self-refinement source has changed')
    verify_ground(ground,max_free=256)
    if [list(c) for c in source]!=ground['source_clauses'] or \
       report.get('refined_ground_sha256')!=ground['digest'] or \
       report.get('refined_registers')!=len(ground['registers']):
        raise ValueError('refinement changed source Ground or register declaration')
    candidate_budget=report.get('candidate_budget')
    if type(candidate_budget) is not int or not 1<=candidate_budget<=4000:
        raise ValueError('invalid recorded bounded discovery budget')
    baseline,_=greedy_compile(source,n,max_candidates=candidate_budget)
    if report.get('baseline_ground_sha256')!=baseline['digest'] or \
       report.get('baseline_registers')!=len(baseline['registers']):
        raise ValueError('refinement baseline is not reproducible')
    # Redo source candidate discovery to check the claimed exact pool identity.
    discovered,_= _candidates(source,n,candidate_budget)
    if digest(discovered)!=report.get('candidate_pool_sha256') or \
       report.get('candidate_pool_size')!=len(discovered):
        raise ValueError('candidate pool is not independently reproducible')
    if report['outcome'] not in ('PRESERVED_BASELINE','IMPROVED_BY_OWN_SAT_INTERPRETER'):
        raise ValueError('invalid self-improvement status')
    changed=len(ground['registers'])<len(baseline['registers'])
    if (report['outcome']=='IMPROVED_BY_OWN_SAT_INTERPRETER') != changed:
        raise ValueError('self-improvement claim contradicts generated machine')
    if not changed and ground!=baseline:
        raise ValueError('non-improved compiler must retain its verified baseline')
    # Independently replay the meta-problem obligations using exhaustive source
    # assignments, NOT the SFI-002 meta-interpreter or its algebraic decoder.
    # A cycle cut is qualified only if its witness really contains a cycle.
    blockers=[]
    last_threshold=None
    conflicts=_conflicts(discovered)
    for row in report.get('meta_attempts',[]):
        if (type(row) is not dict or type(row.get('threshold')) is not int or
            row['threshold']<=len(baseline['instructions']) or
            row['threshold']>len(discovered) or
            row.get('status') not in ('SAT','UNSAT','UNKNOWN','REFUSED')):
            raise ValueError('invalid meta search row')
        if last_threshold is None or row['threshold']!=last_threshold:
            blockers=[]
            if last_threshold is not None and row['threshold']>=last_threshold:
                raise ValueError('meta optimization threshold did not decrease')
            last_threshold=row['threshold']
        constraints=conflicts+_at_least(len(discovered),row['threshold'])+blockers
        if row.get('meta_cnf_digest')!=digest({'n':len(discovered),'cnf':[list(c) for c in constraints]}):
            raise ValueError('meta CNF evidence changed')
        if row.get('cycle_blockers')!=len(blockers):
            raise ValueError('meta nogood count changed')
        def accepts(mask):
            return all(any(bool(mask>>(abs(l)-1)&1)==(l>0) for l in clause)
                       for clause in constraints)
        if row['status']=='UNSAT':
            if any(accepts(mask) for mask in range(1<<len(discovered))):
                raise ValueError('self-compiler falsely declared meta UNSAT')
        if row['status']=='SAT':
            if type(row.get('witness_decimal')) is not str or not row['witness_decimal'].isdigit():
                raise ValueError('missing exact meta witness')
            witness=int(row['witness_decimal'])
            if not 0<=witness<(1<<len(discovered)) or not accepts(witness):
                raise ValueError('forged meta optimizer witness')
            selected=[discovered[i] for i in range(len(discovered)) if witness>>i&1]
            if row.get('rejected_for_cycle'):
                # Reimplement cycle detection without using the producer helper.
                pending={g['output']:set(g['inputs']) for g in selected}
                while pending:
                    ready=[out for out,v in pending.items() if not v.intersection(pending)]
                    if not ready:break
                    for out in ready:del pending[out]
                if not pending:raise ValueError('acyclic candidate was blocked')
                blockers.append(tuple(-(i+1) for i in range(len(discovered)) if witness>>i&1))
            else:
                if {g['output'] for g in selected}!={g['output'] for g in ground['instructions']}:
                    raise ValueError('winning meta witness differs from generated architecture')
    if (report.get('candidate_optimum_certified_by_meta_search') and
        len(discovered)<=max_gates):
        optimum=0
        blocks=[set(tuple(c) for c in x['clauses']) for x in discovered]
        for mask in range(1<<len(discovered)):
            subset=[discovered[i] for i in range(len(discovered)) if mask>>i&1]
            outputs=[g['output'] for g in subset]
            if len(outputs)!=len(set(outputs)):continue
            if any(not blocks[i].isdisjoint(blocks[j])
                   for i in range(len(discovered)) for j in range(i+1,len(discovered))
                   if mask>>i&1 and mask>>j&1):continue
            # Independent cycle check: build selected-variable precedences
            # and repeatedly remove currently source-independent outputs.
            pending={g['output']:set(g['inputs']) for g in subset}
            while pending:
                ready=[out for out,inputs in pending.items() if not inputs.intersection(pending)]
                if not ready:break
                for out in ready:del pending[out]
            if pending:continue
            optimum=max(optimum,len(subset))
        if optimum!=len(ground['instructions']):
            raise ValueError('self-refinement candidate-optimum claim is false')
    if len(ground['registers'])>len(baseline['registers']):
        raise ValueError('refinement regressed executable coordinate dimension')
    if (report.get('baseline_coordinates'),report.get('refined_coordinates')) != \
       (1<<len(baseline['registers']),1<<len(ground['registers'])):
        raise ValueError('refinement search-cost evidence has changed')
    return {'source_equivalence_verified':True,
            'non_regression_verified':True,
            'candidate_pool_optimum_checked':bool(report['candidate_optimum_certified_by_meta_search'] and len(discovered)<=max_gates),
            'verified_register_reduction':len(baseline['registers'])-len(ground['registers'])}
