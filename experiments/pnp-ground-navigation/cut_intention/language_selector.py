"""CIG-006: source-only bounded language selection and temporal-ambiguity audit.

The source CNF fixes a set of admissible states, NOT off-equilibrium time.
This compiler finds a finite class of total local Boolean interpretations,
checks each against every source clause, constructs exact ANF/Koopman Grounds,
and distinguishes class-consensus observations from conditional predictions.

Uses existing CIG-003/004/005 mathematical producers; no external host claim.
"""
from __future__ import annotations

from itertools import product
from time import perf_counter_ns

from cut_intention import GroundRefusal, digest
from nonlinear_observer_ground import source_reduce
from chain_observer_ground import _pullback, _eval, _navigate, _compose
from joint_intention_ground import _closure

SCHEMA='ifs.cig006.source-selected-temporal-language.v1'
MAX_ACTIVE=12
MAX_CANDIDATES=64
MAX_FEATURES=24
MAX_TIME_BITS=4096


def _satisfies(clauses, bits):
    return all(any(((bits>>(abs(l)-1))&1)==int(l>0) for l in clause)
               for clause in clauses)


def _anf(inputs, table):
    coefficients=list(table)
    for bit in range(len(inputs)):
        for mask in range(1<<len(inputs)):
            if mask&(1<<bit):coefficients[mask]^=coefficients[mask^(1<<bit)]
    return tuple(sorted(sum(1<<inputs[j] for j in range(len(inputs)) if mask&(1<<j))
                        for mask,v in enumerate(coefficients) if v))


def _group_options(clauses,n):
    grouped={}
    for raw in clauses:
        if len(raw)!=3 or len({abs(v) for v in raw})!=3:
            raise GroundRefusal('temporal interpretations require complete three-variable relation blocks')
        scope=tuple(sorted(abs(l)-1 for l in raw))
        grouped.setdefault(scope,[]).append(tuple(raw))
    options=[]
    for scope,rows in sorted(grouped.items()):
        choices=[]
        for output in scope:
            inputs=tuple(v for v in scope if v!=output)
            truth=[]
            for coordinate in range(4):
                found=[]
                for outbit in (0,1):
                    assignment=(outbit<<output)|sum(((coordinate>>j)&1)<<v for j,v in enumerate(inputs))
                    if _satisfies(rows,assignment):found.append(outbit)
                if len(found)!=1:break
                truth.append(found[0])
            if len(truth)==4:
                choices.append({'output':output,'inputs':list(inputs),'table':truth,
                                'anf_masks':list(_anf(inputs,truth)),
                                'source_clauses':[list(c) for c in sorted(rows)]})
        if not choices:
            raise GroundRefusal('source relation lacks a total Boolean functional orientation')
        options.append(tuple(sorted(choices,key=lambda g:g['output'])))
    if not options:raise GroundRefusal('no source-proved relation blocks')
    return options


def _candidate_orientations(options,limit):
    total=1
    for group in options:total*=len(group)
    if total>limit:raise GroundRefusal('full orientation search budget exceeded; no consensus claim')
    orientations=[]
    for gates in product(*options):
        if len(set(g['output'] for g in gates))!=len(gates):continue
        orientations.append(list(gates))
    if not orientations:raise GroundRefusal('no conflict-free complete source interpretation')
    return orientations,total


def _operator(gates,n):
    rows=[(1<<i,) for i in range(n)]
    for gate in gates:rows[gate['output']]=tuple(gate['anf_masks'])
    return tuple(rows)


def _matrix_power(matrix,steps):
    n=len(matrix);result=tuple(1<<i for i in range(n));power=tuple(matrix)
    products=0
    while steps:
        if steps&1:
            result=_compose(power,result);products+=1
        steps>>=1
        if steps:
            power=_compose(power,power);products+=1
    return result,products


def _observe_polynomials(feature,targets,steps):
    powered,multiplies=_matrix_power(feature['matrix_rows'],steps)
    basis=[tuple(r) for r in feature['basis']]
    observations=[]
    for read in feature['read_masks']:
        coeff=0
        for j,row in enumerate(powered):
            if (read>>j)&1:coeff ^= row
        terms=set()
        for j,poly in enumerate(basis):
            if (coeff>>j)&1:terms.symmetric_difference_update(poly)
        observations.append(sorted(terms))
    return observations,multiplies


def _snapshot_encoding(futures,n):
    """Construct the smallest-bit lossless nonlinear code for one-time output.

    Full source-state image is enumerated only inside the declared <=12-bit
    active support budget. Each encoder bit is an exact source ANF.
    """
    support_mask=0
    for poly in futures:
        for mon in poly:support_mask|=mon
    support=tuple(i for i in range(n) if support_mask&(1<<i))
    if len(support)>MAX_ACTIVE:raise GroundRefusal('snapshot support exceeds exact proof budget')
    out=[]
    for coordinate in range(1<<len(support)):
        x=sum(((coordinate>>j)&1)<<v for j,v in enumerate(support))
        out.append(sum(_eval(tuple(p),x)<<i for i,p in enumerate(futures)))
    values=sorted(set(out));ident={v:j for j,v in enumerate(values)}
    bits=(len(values)-1).bit_length();polys=[]
    for bit in range(bits):
        table=[(ident[v]>>bit)&1 for v in out]
        coeff=list(table)
        for j in range(len(support)):
            for mask in range(1<<len(support)):
                if mask&(1<<j):coeff[mask]^=coeff[mask^(1<<j)]
        polys.append([sum(1<<support[j] for j in range(len(support)) if mask&(1<<j))
             for mask,value in enumerate(coeff) if value])
    return {'support':list(support),'linear_rank':_linear_rank(futures),
        'image_size':len(values),'minimum_binary_bits':bits,
        'decoder':values,'encoder_anf':polys,
        'source_support_assignments':len(out)}


def _linear_rank(polys):
    pivots={};rank=0
    for poly in polys:
        row=set(poly)
        for pivot in sorted(pivots,reverse=True):
            if pivot in row:row.symmetric_difference_update(pivots[pivot])
        if row:
            pivots[max(row)]=row;rank+=1
    return rank


def _disagreement(first,second,n):
    for state in range(1<<n):
        a=tuple(_eval(tuple(p),state) for p in first)
        b=tuple(_eval(tuple(p),state) for p in second)
        if a!=b:return {'initial':state,'first':list(a),'second':list(b)}
    raise AssertionError('distinct exact ANF polynomial functions must differ on Boolean cube')


def compile_language(source, cut, *, targets=(5,4,6), steps=10**30+17,
                     initial=3, max_candidates=MAX_CANDIDATES,
                     max_features=MAX_FEATURES):
    started=perf_counter_ns()
    if (type(steps)is not int or steps<0 or steps.bit_length()>MAX_TIME_BITS or
        type(max_candidates)is not int or not 1<=max_candidates<=MAX_CANDIDATES or
        type(max_features)is not int or not 1<=max_features<=MAX_FEATURES):
        raise GroundRefusal('invalid bounded temporal intention')
    original,active,clauses=source_reduce(source)
    # CIG-002's actual original-node observer cut qualification.
    from coupled_ground import _cut
    _cut(original,cut)
    n=len(active)
    if not 2<=n<=MAX_ACTIVE:raise GroundRefusal('unadmitted active CNF dimension')
    if (not isinstance(targets,(list,tuple)) or not targets or
        len(set(targets))!=len(targets) or any(type(t)is not int or t<0 or t>=n for t in targets)
        or type(initial)is not int or not 0<=initial<(1<<n)):
        raise GroundRefusal('observer coordinates or initial state invalid')
    options=_group_options(clauses,n)
    gates,attempts=_candidate_orientations(options,max_candidates)
    candidates=[]
    for rows in gates:
        op=_operator(rows,n)
        try:
            span=_closure(op,tuple(targets))
            if span['dimension']>max_features:raise GroundRefusal('feature limit exceeded')
            future,products=_observe_polynomials(span,targets,steps)
            snapshot=_snapshot_encoding(future,n)
            conditional=[_eval(tuple(p),initial) for p in future]
            candidates.append({'orientation':[g['output'] for g in rows],
              'gates':rows,'operator_rows':[list(p) for p in op],
              'feature_basis':span['basis'],'feature_matrix_rows':span['matrix_rows'],
              'feature_read_masks':span['read_masks'],'feature_dimension':span['dimension'],
              'future_anf':future,'snapshot':snapshot,'conditional_observation':conditional,
              'construction_pullbacks':span['closure_pullbacks'],
              'matrix_products':products,'status':'ADMITTED'})
        except GroundRefusal as error:
            candidates.append({'orientation':[g['output'] for g in rows],
                               'gates':rows,'status':'BUDGET_REFUSAL',
                               'reason':str(error)})
    admitted=[(i,c) for i,c in enumerate(candidates) if c['status']=='ADMITTED']
    # A refused candidate cannot silently become evidence for consensus.
    full=len(admitted)==len(candidates)
    if admitted:
        selected=min(admitted,key=lambda item:(item[1]['snapshot']['minimum_binary_bits'],
             item[1]['feature_dimension'],
             sum(len(p) for p in item[1]['feature_basis']),item[1]['orientation']))[0]
        distinct=[]
        for _,c in admitted:
            if c['future_anf'] not in distinct:distinct.append(c['future_anf'])
        if not full:status='UNKNOWN_INCOMPLETE_CANDIDATE_PROOFS'
        elif len(distinct)==1:status='CONSENSUS_IN_DISCOVERED_CLASS'
        else:status='INTERPRETATION_AMBIGUOUS'
    else:selected=None;status='UNKNOWN_NO_ADMITTED_LANGUAGE'
    counterexample=None
    if status=='INTERPRETATION_AMBIGUOUS':
        base=admitted[0][1]['future_anf']
        other=next(c['future_anf'] for _,c in admitted if c['future_anf']!=base)
        counterexample=_disagreement(base,other,n)
    source_count=sum(_satisfies(clauses,state) for state in range(1<<n))
    witness_active=next((x for x in range(1<<n) if _satisfies(clauses,x)),None)
    original_witness=None
    if witness_active is not None:
        active_values={label:(witness_active>>j)&1 for j,label in enumerate(active)}
        original_witness=[0]*source['base']['n']
        for label,(left,right) in enumerate(original['pairs']):
            original_witness[left-1]=original_witness[right-1]=active_values.get(label,0)
        original_clauses=source['base']['clauses']+source['coupling']
        if not all(any(original_witness[abs(l)-1]==int(l>0) for l in clause)
                   for clause in original_clauses):
            raise AssertionError('source reconstruction is not a satisfying original-CNF witness')
    original_count=str(source_count<<(len(original['pairs'])-n))
    proof={'schema':SCHEMA,'source_digest':digest(source),'cut':list(cut),
      'intent':{'targets':list(targets),'steps':str(steps),'initial':initial,
                'max_candidates':max_candidates,'max_features':max_features},
      'source_model':{'active_labels':list(active), 'clauses':[list(c) for c in clauses],
                      'active_fixed_points':source_count,
                     'original_model_count':original_count,
                     'original_source_witness':original_witness},
      'candidate_class':{'name':'complete-triple-relation-functional-orientations',
        'group_count':len(options),'cartesian_options':attempts,
        'conflict_free_count':len(gates),'complete_qualification':full},
      'candidates':candidates,'chosen_candidate_index':selected,
      'consensus_status':status,'disagreement_witness':counterexample,
      'evidence_scope':'finite source-derived orientation class; off-fixedpoint dynamics conditional',
      'ledger':{'candidate_grounds_considered':len(gates),
                'admitted_grounds':len(admitted),
                'candidate_feature_pullbacks':sum(c.get('construction_pullbacks',0) for c in candidates),
                'candidate_matrix_products':sum(c.get('matrix_products',0) for c in candidates),
                'source_active_assignment_checks':1<<n,
                'snapshot_support_checks':sum(c.get('snapshot',{}).get('source_support_assignments',0) for c in candidates)}}
    return proof,{'producer_ns':perf_counter_ns()-started}
